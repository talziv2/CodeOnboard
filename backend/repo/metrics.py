# Measurement for the Stage-2 experiment.
#
# Every number the experiment compares is derived here, from an Exploration's
# recorded trace and usage — never from a model's self-report, and never from
# re-parsing rendered prompt text.
#
# The point of separating this from the experiment script is that the definitions
# outlive one experiment. "Source characters actually read" has to mean the same
# thing in Stage 2 as it will in Stage 3, or the comparison rows are not
# comparable.
#
# The optimisation target is NOT minimum cost. It is repository understanding per
# unit of cost and latency, so this module deliberately reports quality, behaviour
# and cost side by side and computes no single blended score — a scalar would hide
# exactly the trade-off the experiment exists to expose.

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from backend.repo.explore import Exploration
from backend.repo.survey import SurveyCheck, SurveyRun

# A read big enough that the structure should have narrowed it first. Not a
# threshold anything is judged against — a counter, so "did policy B stop reading
# whole files" has an answer.
LARGE_READ_LINES = 150

STRUCTURAL_TOOLS = ("symbols", "neighbors", "search_code")
READING_TOOLS = ("read_file",)


@dataclass
class Behavior:
    """How the explorer spent its budget — the exploration-policy comparison."""

    turns: int = 0
    tool_calls: int = 0
    failed_calls: int = 0
    calls_by_tool: dict[str, int] = field(default_factory=dict)

    read_calls: int = 0
    outline_reads: int = 0
    source_lines_read: int = 0
    source_chars_read: int = 0
    largest_read_lines: int = 0
    large_reads: int = 0
    whole_file_reads: int = 0

    structural_calls: int = 0
    tool_output_chars: int = 0

    # ── waste (§0: this is what optimisation may remove) ──────────────────────
    duplicate_calls: int = 0        # identical call the harness refused to re-run
    overlapping_reads: int = 0      # read of lines already returned earlier
    reread_lines: int = 0           # how many of those lines were already held
    # ── did structural navigation actually narrow anything? ───────────────────
    narrowing_structural_calls: int = 0   # followed by a read of a file it surfaced

    @property
    def average_read_lines(self) -> float:
        ranged = self.read_calls - self.outline_reads
        return self.source_lines_read / ranged if ranged else 0.0

    @property
    def structural_share(self) -> float:
        """Structural calls as a share of structural + reading calls.

        The headline number for the policy A/B: does biasing toward structure
        actually shift the mix, or only the prose describing it?
        """
        denominator = self.structural_calls + self.read_calls
        return self.structural_calls / denominator if denominator else 0.0

    @property
    def wasted_calls(self) -> int:
        return self.duplicate_calls + self.overlapping_reads

    @property
    def waste_share(self) -> float:
        """Share of tool calls that gathered nothing new."""
        return self.wasted_calls / self.tool_calls if self.tool_calls else 0.0

    @property
    def narrowing_share(self) -> float:
        """Share of structural calls that a later read actually acted on.

        This is the evidence for or against the structural tools existing at all:
        a call that surfaces files nobody then reads has not narrowed anything.
        """
        return (
            self.narrowing_structural_calls / self.structural_calls
            if self.structural_calls else 0.0
        )


def _read_span(call) -> tuple[str, int, int] | None:
    facts = call.facts or {}
    if call.name != "read_file" or facts.get("outline") or not facts.get("lines"):
        return None
    path = str((call.arguments or {}).get("path") or "")
    start = int((call.arguments or {}).get("start") or 1)
    return (path, start, start + int(facts["lines"]) - 1)


def behavior(exploration: Exploration) -> Behavior:
    out = Behavior(turns=exploration.turns)
    read_spans: dict[str, list[tuple[int, int]]] = {}
    # Files a structural call surfaced, and the call index that surfaced them, so a
    # later read can be attributed back to the call that pointed at it.
    surfaced: list[tuple[int, set[str]]] = []
    narrowed: set[int] = set()

    for index, call in enumerate(exploration.trace):
        # The report tool is not exploration — counting it would inflate the
        # call count by one and make policies with more rejections look busier.
        if call.name.startswith("submit_"):
            continue
        facts = call.facts or {}
        out.tool_calls += 1
        out.calls_by_tool[call.name] = out.calls_by_tool.get(call.name, 0) + 1
        out.tool_output_chars += call.result_chars

        if facts.get("duplicate_of") is not None:
            out.duplicate_calls += 1
            continue
        if not call.ok:
            out.failed_calls += 1
            continue

        if call.name in STRUCTURAL_TOOLS:
            out.structural_calls += 1
            paths = {str(p) for p in facts.get("paths") or []}
            if paths:
                surfaced.append((index, paths))

        if call.name in READING_TOOLS:
            out.read_calls += 1
            if facts.get("outline"):
                out.outline_reads += 1
                continue
            lines = int(facts.get("lines") or 0)
            out.source_lines_read += lines
            out.source_chars_read += int(facts.get("source_chars") or 0)
            out.largest_read_lines = max(out.largest_read_lines, lines)
            if lines >= LARGE_READ_LINES:
                out.large_reads += 1
            if facts.get("whole_file"):
                out.whole_file_reads += 1

            span = _read_span(call)
            if span is not None:
                path, start, end = span
                held = read_spans.setdefault(path, [])
                overlap = sum(
                    max(0, min(end, prior_end) - max(start, prior_start) + 1)
                    for prior_start, prior_end in held
                )
                if overlap:
                    out.overlapping_reads += 1
                    out.reread_lines += min(overlap, lines)
                held.append((start, end))
                # Credit the most recent structural call that surfaced this file.
                for call_index, paths in reversed(surfaced):
                    if path in paths and call_index not in narrowed:
                        narrowed.add(call_index)
                        break

    out.narrowing_structural_calls = len(narrowed)
    return out


def coverage_progression(exploration: Exploration, skeleton) -> list[int]:
    """Distinct subsystems the run had touched, cumulatively, by turn.

    Shows *when* breadth was acquired: a run that touches everything early and
    then goes deep looks very different from one still discovering at the buzzer.
    """
    owner = _file_owner(skeleton)
    turns = max((c.turn for c in exploration.trace), default=0)
    seen: set[str] = set()
    progression: list[int] = []
    for turn in range(1, turns + 1):
        for call in exploration.trace:
            if call.turn != turn:
                continue
            for path in _touched_paths(call):
                name = owner.get(path)
                if name:
                    seen.add(name)
        progression.append(len(seen))
    return progression


def _file_owner(skeleton) -> dict[str, str]:
    """file -> the subsystem that contains it."""
    owner: dict[str, str] = {}
    for name, files in skeleton.subsystems().items():
        for path in files:
            owner[path] = name
    return owner


def _touched_paths(call) -> set[str]:
    """Files a call actually engaged with — argument or result."""
    arguments = call.arguments or {}
    paths = {str(p) for p in (call.facts or {}).get("paths") or []}
    for key in ("path", "file"):
        if arguments.get(key):
            paths.add(str(arguments[key]))
    return paths


# Evidence depth per subsystem, derived from the trace rather than self-reported.
# "Accounting" and "deep reading" are different claims, and a survey that says it
# understands a subsystem it never opened should be visibly distinguishable from
# one that read the code.
READ = "source_read"        # source from this subsystem was actually returned
OUTLINED = "outlined"       # its symbols were listed, or an outline was returned
NAMED = "named_only"        # only ever appeared in a file listing or search hit
UNTOUCHED = "untouched"     # never appeared in any tool result


def subsystem_evidence(exploration: Exploration, skeleton) -> dict[str, str]:
    owner = _file_owner(skeleton)
    depth = {name: UNTOUCHED for name in skeleton.subsystems()}
    rank = {UNTOUCHED: 0, NAMED: 1, OUTLINED: 2, READ: 3}

    def promote(name: str, level: str) -> None:
        if name and rank[level] > rank[depth.get(name, UNTOUCHED)]:
            depth[name] = level

    for call in exploration.trace:
        if not call.ok or call.name.startswith("submit_"):
            continue
        facts = call.facts or {}
        if facts.get("duplicate_of") is not None:
            continue
        arguments = call.arguments or {}
        if call.name == "read_file":
            path = str(arguments.get("path") or "")
            promote(owner.get(path, ""), OUTLINED if facts.get("outline") else READ)
        elif call.name == "symbols":
            for path in _touched_paths(call):
                promote(owner.get(path, ""), OUTLINED)
        elif call.name in ("neighbors", "search_code", "list_files", "propose_anchor"):
            for path in _touched_paths(call):
                promote(owner.get(path, ""), NAMED)
    return depth


@dataclass
class Quality:
    """What our code can decide about a survey's quality, with no model involved."""

    produced: bool = False      # a survey came back
    accepted: bool = False      # ...and satisfied the coverage contract
    rejections: int = 0

    required_subsystems: int = 0
    covered: int = 0
    skipped: int = 0
    unaccounted: int = 0            # M1b silent omissions — must be 0 under D13
    unknown_names: int = 0
    skip_reasons: list[str] = field(default_factory=list)

    # Grounding, measured twice: as submitted the first time (informative) and as
    # finally accepted (100% by construction when the contract is enforced).
    first_grounding: float = 1.0
    first_anchors: int = 0
    first_unresolved: int = 0
    final_grounding: float = 1.0
    final_anchors: int = 0

    entry_points: int = 0
    core_abstractions: int = 0
    flows: int = 0
    flow_steps: int = 0
    widest_flow_files: int = 0
    boundaries: int = 0
    docs: int = 0
    responsibility_chars: int = 0

    @property
    def accounted_ratio(self) -> float:
        total = self.required_subsystems
        return (self.covered + self.skipped) / total if total else 0.0

    @property
    def covered_ratio(self) -> float:
        total = self.required_subsystems
        return self.covered / total if total else 0.0

    @property
    def average_responsibility_chars(self) -> float:
        return self.responsibility_chars / self.covered if self.covered else 0.0


def quality(run: SurveyRun) -> Quality:
    check: SurveyCheck | None = run.check
    payload = run.survey or {}
    out = Quality(
        produced=run.produced,
        accepted=run.accepted,
        rejections=len(run.exploration.rejections),
    )
    if check is not None:
        coverage = check.coverage
        out.required_subsystems = coverage.required
        out.covered = len(coverage.covered)
        out.skipped = len(coverage.skipped_with_reason)
        out.unaccounted = len(coverage.unaccounted)
        out.unknown_names = len(coverage.unknown)
        out.skip_reasons = list(coverage.skipped_with_reason.values())
        out.final_grounding = check.grounding_accuracy
        out.final_anchors = check.total_anchors
    first = run.validator.first
    if first is not None:
        out.first_grounding = first.grounding_accuracy
        out.first_anchors = first.total_anchors
        out.first_unresolved = len(first.unresolved_anchors)

    out.entry_points = len(payload.get("entry_points") or [])
    out.core_abstractions = len(payload.get("core_abstractions") or [])
    flows = payload.get("flows") or []
    out.flows = len(flows)
    for flow in flows:
        steps = flow.get("steps") or []
        out.flow_steps += len(steps)
        files = {str(step.get("file") or "") for step in steps}
        out.widest_flow_files = max(out.widest_flow_files, len(files))
    out.boundaries = len(payload.get("boundaries") or [])
    out.docs = len(payload.get("docs") or [])
    out.responsibility_chars = sum(
        len(str(entry.get("responsibility") or ""))
        for entry in payload.get("subsystems") or []
    )
    return out


@dataclass
class Cost:
    """Tokens, cache behaviour, money and latency for one run."""

    api_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    uncached_cost_usd: float = 0.0
    seconds: float = 0.0

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_write_tokens + self.cache_read_tokens

    @property
    def cache_hit_rate(self) -> float:
        total = self.prompt_tokens
        return self.cache_read_tokens / total if total else 0.0

    @property
    def caching_saved_usd(self) -> float:
        """What caching saved against paying full price for the same prompt.

        Worth reporting explicitly: a run can have a high hit rate and still be
        expensive, because writes bill at 1.25x while reads bill at 0.1x.
        """
        return self.uncached_cost_usd - self.cost_usd

    # ── size-normalised, for comparing cache strategies ───────────────────────
    #
    # Total cost is confounded: a run that happened to explore less writes less
    # cache and looks cheaper, whichever strategy it used. These two normalise it
    # away, so a cache comparison measures the strategy rather than the run.

    @property
    def write_share(self) -> float:
        """Cache-write tokens as a share of all prompt tokens."""
        total = self.prompt_tokens
        return self.cache_write_tokens / total if total else 0.0

    @property
    def cost_per_1k_prompt_tokens(self) -> float:
        """USD per 1k prompt tokens — cost with exploration volume divided out."""
        total = self.prompt_tokens
        return self.cost_usd / total * 1000 if total else 0.0


def cost(exploration: Exploration, model: str) -> Cost:
    usage = exploration.usage
    from backend.repo.explore import PRICING

    per_in, per_out = PRICING.get(model, (0.0, 0.0))
    prompt = usage.input_tokens + usage.cache_creation_input_tokens + usage.cache_read_input_tokens
    return Cost(
        api_calls=usage.api_calls,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_write_tokens=usage.cache_creation_input_tokens,
        cache_read_tokens=usage.cache_read_input_tokens,
        cost_usd=usage.cost_usd(model),
        uncached_cost_usd=(prompt * per_in + usage.output_tokens * per_out) / 1_000_000,
        seconds=exploration.seconds,
    )


# ── consistency across repeats ────────────────────────────────────────────────


def _covered_names(run: SurveyRun) -> set[str]:
    check = run.check
    return set(check.coverage.covered) if check else set()


def _anchor_keys(run: SurveyRun) -> set[str]:
    from backend.repo.survey import cited_anchors

    return {f"{file}:{symbol}" for _, file, symbol in cited_anchors(run.survey or {})}


def _jaccard(sets: list[set[str]]) -> float:
    """Mean pairwise Jaccard overlap. 1.0 means every repeat agreed exactly."""
    pairs = [
        (a, b) for i, a in enumerate(sets) for b in sets[i + 1:]
    ]
    if not pairs:
        return 1.0
    scores = []
    for a, b in pairs:
        union = a | b
        scores.append(len(a & b) / len(union) if union else 1.0)
    return sum(scores) / len(scores)


@dataclass
class Consistency:
    """M10 across repeated runs of the same cell."""

    runs: int = 0
    covered_overlap: float = 1.0
    anchor_overlap: float = 1.0
    cost_spread_usd: float = 0.0
    turn_spread: int = 0


def consistency(runs: list[SurveyRun], model: str) -> Consistency:
    if len(runs) < 2:
        return Consistency(runs=len(runs))
    costs = [cost(r.exploration, model).cost_usd for r in runs]
    turns = [r.exploration.turns for r in runs]
    return Consistency(
        runs=len(runs),
        covered_overlap=_jaccard([_covered_names(r) for r in runs]),
        anchor_overlap=_jaccard([_anchor_keys(r) for r in runs]),
        cost_spread_usd=max(costs) - min(costs),
        turn_spread=max(turns) - min(turns),
    )


# ── what would Goal Investigation otherwise rediscover? ───────────────────────
#
# The Survey's whole claim is build-once / reuse-across-goals. That claim is only
# as good as the knowledge it produces being (a) substantial and (b) *stable* — a
# fact that comes out different every run is not reusable, because a later layer
# could not have relied on it anyway. So each category is scored on both.

REUSABLE_CATEGORIES = {
    # category: (payload key, how to key one fact for cross-run comparison)
    "subsystem responsibilities": ("subsystems", lambda e: str(e.get("name"))),
    "entry points": ("entry_points", lambda e: f"{e.get('file')}:{e.get('symbol')}"),
    "core abstractions": ("core_abstractions", lambda e: f"{e.get('file')}:{e.get('symbol')}"),
    "component relationships": (
        "relationships",
        lambda e: f"{e.get('from_symbol')}->{e.get('to_symbol')}",
    ),
    "representative flows": ("flows", lambda e: str(e.get("name"))),
    "extension points / boundaries": ("boundaries", lambda e: f"{e.get('file')}:{e.get('symbol')}"),
    "docs inventory": ("docs", lambda e: str(e.get("path"))),
    "infrastructure areas": ("infrastructure", lambda e: str(e.get("path"))),
    "conventions": ("conventions", lambda e: str(e)),
    "open questions for Layer C": ("needs_investigation", lambda e: str(e.get("area"))),
}


@dataclass
class CategoryReuse:
    facts: float = 0.0        # median count across runs
    stability: float = 0.0    # mean pairwise overlap of the same facts across runs
    runs: int = 0

    @property
    def reusable_facts(self) -> float:
        """Facts weighted by how reliably they reappear — the honest figure."""
        return self.facts * self.stability


def reuse(runs: list[SurveyRun]) -> dict[str, CategoryReuse]:
    """Per category: how much the Survey establishes, and how stably."""
    out: dict[str, CategoryReuse] = {}
    payloads = [r.survey or {} for r in runs]
    for label, (key, keyer) in REUSABLE_CATEGORIES.items():
        counts, keysets = [], []
        for payload in payloads:
            entries = payload.get(key) or []
            counts.append(len(entries))
            keysets.append({keyer(e) for e in entries})
        out[label] = CategoryReuse(
            facts=statistics.median(counts) if counts else 0.0,
            stability=_jaccard(keysets) if len(keysets) > 1 else 1.0,
            runs=len(payloads),
        )
    return out


# ── one row of the comparison table ───────────────────────────────────────────


@dataclass
class Row:
    """A single experiment cell, fully measured."""

    repo: str
    policy: str
    cache: str
    behavior: Behavior
    quality: Quality
    cost: Cost
    stop_reason: str
    errors: list[str] = field(default_factory=list)
    evidence: dict[str, str] = field(default_factory=dict)   # subsystem -> depth
    progression: list[int] = field(default_factory=list)     # breadth by turn

    def as_dict(self) -> dict:
        from dataclasses import asdict

        return {
            "repo": self.repo,
            "policy": self.policy,
            "cache": self.cache,
            "stop_reason": self.stop_reason,
            "errors": self.errors,
            "behavior": {
                **asdict(self.behavior),
                "average_read_lines": self.behavior.average_read_lines,
                "structural_share": self.behavior.structural_share,
                "waste_share": self.behavior.waste_share,
                "wasted_calls": self.behavior.wasted_calls,
                "narrowing_share": self.behavior.narrowing_share,
            },
            "evidence": self.evidence,
            "progression": self.progression,
            "quality": {
                **asdict(self.quality),
                "accounted_ratio": self.quality.accounted_ratio,
                "covered_ratio": self.quality.covered_ratio,
                "average_responsibility_chars": self.quality.average_responsibility_chars,
            },
            "cost": {
                **asdict(self.cost),
                "prompt_tokens": self.cost.prompt_tokens,
                "cache_hit_rate": self.cost.cache_hit_rate,
                "caching_saved_usd": self.cost.caching_saved_usd,
                "write_share": self.cost.write_share,
                "cost_per_1k_prompt_tokens": self.cost.cost_per_1k_prompt_tokens,
            },
        }


def row(repo: str, policy: str, cache: str, run: SurveyRun, model: str) -> Row:
    return Row(
        repo=repo,
        policy=policy,
        cache=cache,
        behavior=behavior(run.exploration),
        quality=quality(run),
        cost=cost(run.exploration, model),
        stop_reason=run.exploration.stop_reason,
        errors=list(run.exploration.errors),
        evidence=subsystem_evidence(run.exploration, run.skeleton),
        progression=coverage_progression(run.exploration, run.skeleton),
    )
