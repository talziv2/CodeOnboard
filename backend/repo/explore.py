# Exploration harness (Stage 1) — the budgeted agentic loop over backend/repo/tools.py.
#
# This is the mechanism the migration replaces retrieval with: instead of
# computing a fixed slice of evidence before the model reasons, the model asks
# for what it needs, several calls per turn, until its exit criteria are met or
# its budget runs out.
#
# Three properties this module exists to guarantee, none of which can be
# delegated to a prompt (docs/planning/phases/repo-understanding.md §5.4, RK2, RK8):
#
#   1. BUDGETS ARE ENFORCED IN CODE. Turns, tool calls, tool-output volume and
#      wall clock are all checked here. A prompt that says "be brief" is a
#      request; `Budget` is a limit.
#   2. EXHAUSTION IS A RESULT, NOT AN EXCEPTION. Running out of budget yields a
#      partial `Exploration` with `budget_exhausted=True` and an honest
#      `stop_reason`. So does an API failure, and so does a tool crash. Nothing
#      here raises at the caller.
#   3. EVERY CALL IS RECORDED. `Exploration.trace` is the replayable log (OQ5)
#      and `Exploration.usage` is the per-run cost accounting (M9, H6).
#
# Stage 1 wires this into nothing. `project-archive/rag-migration/harnesses/smoke_stage1.py` drives it; the
# Survey (Stage 2) and `goal_investigation` (Stage 3) become callers later.
#
# Model choice follows CLAUDE.md: this is a loop, so it is Haiku. Sonnet in a
# loop is explicitly against the project's LLM rules.

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from backend.repo import tools
from backend.repo.skeleton import Skeleton

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 4096

# USD per million tokens, for M9. Kept here rather than computed elsewhere so a
# run reports its own cost without a second source of truth.
PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
}
CACHE_WRITE_MULTIPLIER = 1.25   # 5-minute TTL
CACHE_READ_MULTIPLIER = 0.10

# Haiku's minimum cacheable prefix. Below this the breakpoint is silently
# ignored — no error, just no cache — so H6's "prompt caching keeps the loop in
# budget" hypothesis depends on the seed being at least this big.
HAIKU_MIN_CACHEABLE_TOKENS = 4096


# ── budget ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Budget:
    """Hard ceilings, checked by this module on every turn.

    ``max_result_chars`` bounds tool *output* rather than tokens, because chars
    are exactly measurable locally and tokens are not. At roughly 4 chars per
    token the default is ~60k tokens of evidence — enough to read a subsystem,
    not enough to read a repository.
    """

    max_turns: int = 12
    max_tool_calls: int = 60
    max_result_chars: int = 240_000
    max_seconds: float = 240.0


# ── recorded output ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ToolCall:
    """One tool invocation, as it happened. The unit of the replayable trace."""

    turn: int
    name: str
    arguments: dict
    ok: bool
    error: str | None
    result_chars: int
    summary: str          # one line, for progress display (OQ3) and logs
    # Tool-specific structured facts about what came back — how many lines a read
    # actually returned, whether it was a whole file, how many matches a search
    # found. Recorded here rather than parsed back out of `summary`, so the
    # exploration-behaviour metrics measure the run instead of a rendered string.
    facts: dict = field(default_factory=dict)


@dataclass
class Usage:
    """Token and cost accounting across every API call in one exploration."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    api_calls: int = 0

    def add(self, raw) -> None:
        """Accumulate one response's ``usage``, tolerating absent cache fields."""
        self.api_calls += 1
        self.input_tokens += int(getattr(raw, "input_tokens", 0) or 0)
        self.output_tokens += int(getattr(raw, "output_tokens", 0) or 0)
        self.cache_creation_input_tokens += int(
            getattr(raw, "cache_creation_input_tokens", 0) or 0
        )
        self.cache_read_input_tokens += int(
            getattr(raw, "cache_read_input_tokens", 0) or 0
        )

    def cost_usd(self, model: str = MODEL) -> float:
        """Cost at list price. Cache reads bill at ~0.1x, writes at ~1.25x."""
        rates = PRICING.get(model)
        if rates is None:
            return 0.0
        per_in, per_out = rates
        billed_input = (
            self.input_tokens
            + self.cache_creation_input_tokens * CACHE_WRITE_MULTIPLIER
            + self.cache_read_input_tokens * CACHE_READ_MULTIPLIER
        )
        return (billed_input * per_in + self.output_tokens * per_out) / 1_000_000

    @property
    def cache_hit_ratio(self) -> float:
        """Share of prompt tokens served from cache — the H6 measurement."""
        total = (
            self.input_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )
        return self.cache_read_input_tokens / total if total else 0.0


# Why the loop stopped. `reported` and `answered` are successes; the four
# `*_budget` values are honest partial results; `api_error` is a failure that
# still returns whatever was gathered first.
REPORTED = "reported"              # the model called the report tool
ANSWERED = "answered"              # the model stopped calling tools
NO_REPORT = "no_report"            # a report was required and never arrived
TURN_BUDGET = "turn_budget"
TOOL_CALL_BUDGET = "tool_call_budget"
READ_BUDGET = "read_budget"
TIME_BUDGET = "time_budget"
API_ERROR = "api_error"

BUDGET_STOPS = (TURN_BUDGET, TOOL_CALL_BUDGET, READ_BUDGET, TIME_BUDGET)


@dataclass
class Exploration:
    """What one budgeted loop produced. Always returned; never raised."""

    stop_reason: str
    text: str = ""                       # the model's final prose
    output: dict | None = None           # the report tool's payload, if any
    trace: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    turns: int = 0
    errors: list[str] = field(default_factory=list)
    seconds: float = 0.0
    # Rejected reports, in order: what `validate` said was missing each time it
    # sent the model back to gather more. An empty list means the first submission
    # satisfied the contract.
    rejections: list[str] = field(default_factory=list)
    # Did the returned `output` satisfy `validate`? True when it was accepted on
    # its merits, False when the budget ran out and it was accepted anyway with a
    # known gap (§5.4), None when there was no validator. "Produced a report" and
    # "met the contract" are different facts and must not be conflated.
    contract_met: bool | None = None

    @property
    def ok(self) -> bool:
        return self.stop_reason in (REPORTED, ANSWERED)

    @property
    def budget_exhausted(self) -> bool:
        return self.stop_reason in BUDGET_STOPS

    @property
    def result_chars(self) -> int:
        return sum(c.result_chars for c in self.trace)


# ── the tool surface presented to the model ───────────────────────────────────
#
# `repo_path` is deliberately absent from every schema: it is injected by this
# module, so the model cannot aim a tool at another checkout. Descriptions are
# part of the prompt and live here rather than in tools.py, which stays free of
# model-facing text.

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "list_files",
        "description": (
            "List files in the repository. Returns each file's path, role "
            "(source/test/doc/example/tooling), line count and symbol count, so "
            "you can judge a file's size and kind without reading it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "glob": {
                    "type": "string",
                    "description": "Glob to match, e.g. '**/*.py' or 'security/*.py'. Defaults to '**/*.py'.",
                },
                "role": {
                    "type": "string",
                    "enum": ["source", "test", "doc", "example", "tooling"],
                    "description": "Keep only files with this role.",
                },
                "limit": {"type": "integer", "description": "Max files to return (cap 200)."},
            },
        },
    },
    {
        "name": "symbols",
        "description": (
            "List indexed definitions (functions and classes) with exact line "
            "ranges. This is the cheap way to see what is in a file — prefer it "
            "over read_file when you only need the shape. Pass `path` to outline "
            "one file, or `name` to locate a definition anywhere in the repo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Outline this file."},
                "name": {
                    "type": "string",
                    "description": "Find this symbol. Qualified names work: 'Session.send'.",
                },
                "kind": {"type": "string", "enum": ["function", "class"]},
                "limit": {"type": "integer", "description": "Max symbols to return (cap 200)."},
            },
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read source with line numbers. Give `start` and `end` to read a "
            "range; at most 400 lines per call. Without a range, a file longer "
            "than 400 lines returns its symbol outline instead of its contents, "
            "so pick a range from that and read again."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start": {"type": "integer", "description": "First line, 1-indexed inclusive."},
                "end": {"type": "integer", "description": "Last line, inclusive."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "search_code",
        "description": (
            "Regular-expression search over the repository. Use it to find where "
            "a name is used, which files import something, or where an error "
            "string is raised. A match is a textual fact, not proof the symbol is "
            "the one you meant — read the hit to confirm."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Python regular expression."},
                "glob": {"type": "string", "description": "Restrict to matching paths."},
                "max_results": {"type": "integer", "description": "Max matches to return (cap 50)."},
                "ignore_case": {"type": "boolean"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "neighbors",
        "description": (
            "Relationships around a symbol: the methods a class defines, its base "
            "classes, what its file imports, which files import it, which package "
            "`__init__` re-exports it (`exported_by`, with the dotted path a user "
            "would type), and where its name is referenced. Use this to follow a "
            "flow across files instead of guessing from names, and `exported_by` to "
            "tell what callers of this repository actually reach from what the "
            "internals use. If a symbol name is defined in more than one place you "
            "get the list of definitions; pass `file` to follow one of them."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "file": {"type": "string", "description": "Disambiguate a repeated symbol name."},
                "relations": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": list(tools.RELATIONS),
                    },
                    "description": "Restrict to these relations. Defaults to all.",
                },
                "limit": {"type": "integer", "description": "Max neighbours to return (cap 50)."},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "propose_anchor",
        "description": (
            "Verify a citation against the repository before you rely on it. Give "
            "`file` plus either `symbol` (preferred — the exact line range is "
            "computed for you) or an explicit line range. Returns the verified "
            "range, or an error naming what could not be resolved."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "symbol": {"type": "string"},
                "line_start": {"type": "integer"},
                "line_end": {"type": "integer"},
            },
            "required": ["file"],
        },
    },
]

TOOL_NAMES = tuple(schema["name"] for schema in TOOL_SCHEMAS)


@dataclass(frozen=True)
class ReportSpec:
    """The structured output the loop must end with.

    Supplying one turns "the model stops talking" into "the model submitted a
    validated payload", which is what Stages 2 and 3 need for the survey and the
    dossier. Without it the loop returns prose.
    """

    name: str
    description: str
    input_schema: dict

    def as_tool(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


# ── the seed ──────────────────────────────────────────────────────────────────

# ── tool guides — the exploration policy, as prose ────────────────────────────
#
# Two variants, compared as Stage 2's exploration-policy A/B. Both describe the
# same six tools; they differ in what they encourage. Neither prescribes a fixed
# call sequence — a mechanical "symbols then neighbors then read" script would
# stop the model adapting to what it finds, which is the whole reason
# exploration is agentic rather than a pipeline.

TOOL_GUIDE_DEFAULT = """\
You explore a repository through six tools. They report facts derived from the
checkout; none of them judges what matters — that is your job.

How to spend calls well:
- Issue several tool calls in one turn whenever they do not depend on each other.
  Serial calls cost turns; parallel calls do not.
- Reach for `symbols` before `read_file`. An outline answers "what is in here"
  for a fraction of the tokens.
- Read narrow ranges. Two 60-line reads beat one 400-line read.
- Follow structure with `neighbors` rather than inferring it from names.
- `propose_anchor` before citing a file and range, so what you report is verified
  rather than remembered.

Your budget is enforced outside this conversation: turns, tool calls, total tool
output and wall-clock time are all capped. When a limit is reached you will be
asked to report what you have, so gather evidence in priority order and do not
save the important reading for later."""

TOOL_GUIDE_STRUCTURAL = """\
You explore a repository through six tools. They report facts derived from the
checkout; none of them judges what matters — that is your job.

Prefer structural navigation to identify relevant code before reading source.
Use `symbols`, `neighbors` and `search_code` to narrow the investigation, then
read the smallest source ranges necessary to confirm your current hypothesis.
Reading a file to find out what is in it is the expensive way to answer a
question the structure already answers.

In practice that means:
- `symbols` tells you what a file defines and exactly where, without reading it.
  A file's outline is usually enough to decide whether any of it is worth reading.
- `neighbors` follows real edges — what a class defines, what it extends, what its
  file imports, who imports it, where its name appears. Trace a flow by walking
  those edges, not by opening files and guessing what calls what.
- `search_code` locates a name, a raise site or a registration across the whole
  repository in one call.
- Then `read_file` on a specific range, to confirm what the structure implied.
  Prefer a 40-line read of the right function over a 300-line read of its file.

This is a policy, not a fixed sequence. Adapt it: if structure has already told
you what you need, do not read; if a read reveals something the structure did not
predict, follow that instead. What matters is that reading is targeted at a
question you already formed, rather than being how you form it.

Your budget is enforced outside this conversation: turns, tool calls, total tool
output and wall-clock time are all capped. When a limit is reached you will be
asked to report what you have, so gather evidence in priority order and do not
save the important reading for later."""

# The Stage-1 baseline, kept under its original name so existing callers and
# tests keep meaning what they meant.
TOOL_GUIDE = TOOL_GUIDE_DEFAULT

TOOL_GUIDES = {
    "default": TOOL_GUIDE_DEFAULT,
    "structural": TOOL_GUIDE_STRUCTURAL,
}


def skeleton_brief(skeleton: Skeleton, max_subsystems: int = 60) -> str:
    """The deterministic inventory, rendered as prompt text.

    This is the Layer A seed from §5.2: the model never has to *discover* that a
    subsystem exists, because it is handed the complete list and can be held to
    accounting for it. Cheap to compute, stable per commit, and therefore the
    natural head of the cached prefix.
    """
    subsystems = skeleton.subsystems()
    roles: dict[str, int] = {}
    for entry in skeleton.files.values():
        roles[entry.role] = roles.get(entry.role, 0) + 1
    role_line = ", ".join(f"{role} {count}" for role, count in sorted(roles.items()))

    lines = [
        "REPOSITORY INVENTORY (computed from the checkout, not inferred)",
        f"  indexed files : {len(skeleton.files)} ({role_line})",
        f"  symbols       : {len(skeleton.symbols)}",
        f"  source root   : {skeleton.source_root() or '<repository root>'}",
        f"  subsystems    : {len(subsystems)}",
        "",
        "Subsystems, with the source files each contains:",
    ]
    for name, files in list(subsystems.items())[:max_subsystems]:
        shown = ", ".join(f.rsplit("/", 1)[-1] for f in files[:6])
        more = f" (+{len(files) - 6} more)" if len(files) > 6 else ""
        lines.append(f"  {name} [{len(files)}] — {shown}{more}")
    if len(subsystems) > max_subsystems:
        lines.append(f"  ... {len(subsystems) - max_subsystems} further subsystems")
    return "\n".join(lines)


def seed_blocks(
    instructions: str,
    skeleton: Skeleton | None = None,
    tool_guide: str = TOOL_GUIDE_DEFAULT,
) -> list[dict]:
    """System prompt as cacheable blocks: instructions, tool guide, inventory.

    Ordered stable-first and marked with one cache breakpoint on the last block.
    Because tools render before system, that single breakpoint covers the tool
    definitions and the whole seed. Nothing volatile belongs in here — a
    timestamp or a goal string in this prefix would invalidate the cache on every
    call (see repo-understanding.md H6).
    """
    text = [instructions.strip(), tool_guide]
    if skeleton is not None:
        text.append(skeleton_brief(skeleton))
    blocks = [{"type": "text", "text": part} for part in text if part]
    blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


# ── tool-result rendering ─────────────────────────────────────────────────────
#
# Tool output is prompt text, so its shape is a cost decision. JSON would escape
# every newline in a source file; these renderers keep code readable and drop
# keys the model does not need.


def _call_key(name: str, arguments: dict) -> str:
    """Identity of a tool call, for spotting an exact repeat."""
    return name + "|" + json.dumps(arguments, sort_keys=True, default=str)


# Waste elimination, not capability reduction (§0): every tool here is
# deterministic over a pinned checkout, so an identical call cannot return
# anything new. Its result is already in the conversation, so pointing back to it
# is lossless — the model can still read what it read. What it removes is paying
# for the same bytes twice, which on a long run is the single largest avoidable
# cost. Kept switchable so the experiment can measure how often it fires.
_DUPLICATE = "Identical to your turn-{turn} call; its result is above. Not re-run."


def _facts(name: str, result: dict) -> dict:
    """Structured facts about what a call returned, for behaviour measurement.

    The question Stage 2 has to answer is whether structural navigation reduces
    raw source consumption, which needs the *resolved* extent of each read — not
    the arguments asked for. A read with no range returns a whole file or an
    outline; only the result knows which.
    """
    if not result.get("ok"):
        return {}
    if name == "read_file":
        if result.get("content") is None:
            return {"outline": True, "lines": 0, "total_lines": result.get("total_lines", 0)}
        lines = int(result["end"]) - int(result["start"]) + 1
        total = int(result.get("total_lines") or 0)
        return {
            "outline": False,
            "lines": lines,
            "total_lines": total,
            "whole_file": bool(total) and lines >= total,
            "source_chars": len(result.get("content") or ""),
        }
    # `paths` on the structural tools is what makes "did this narrow anything?"
    # answerable: a structural call earns its place if a later read lands on a file
    # it surfaced. Capped, because these facts are held for the whole run.
    if name == "search_code":
        return {
            "matches": result.get("total", 0),
            "files": result.get("files_with_matches", 0),
            "paths": sorted({m["path"] for m in result.get("matches") or []})[:40],
        }
    if name == "symbols":
        return {
            "symbols": result.get("total", 0),
            "paths": sorted({s["file"] for s in result.get("symbols") or []})[:40],
        }
    if name == "neighbors":
        paths = {n["file"] for n in result.get("neighbors") or [] if n.get("file")}
        paths |= {c["file"] for c in result.get("candidates") or [] if c.get("file")}
        return {
            "neighbors": result.get("total", 0),
            "ambiguous": bool(result.get("ambiguous")),
            "paths": sorted(paths)[:40],
        }
    if name == "list_files":
        return {
            "files": result.get("total", 0),
            "paths": [f["path"] for f in result.get("files") or []][:40],
        }
    if name == "propose_anchor":
        return {"verified": True, "symbol": result.get("symbol")}
    return {}


def _render(name: str, result: dict) -> tuple[str, str]:
    """(text for the model, one-line summary for the trace)."""
    if not result.get("ok"):
        detail = result.get("detail") or ""
        code = result.get("error", "error")
        return f"error: {code} — {detail}", f"{code}: {detail[:60]}"

    if name == "read_file":
        return _render_read_file(result)
    if name == "list_files":
        return _render_list_files(result)
    if name == "search_code":
        return _render_search(result)
    if name == "symbols":
        return _render_symbols(result)
    if name == "neighbors":
        return _render_neighbors(result)
    if name == "propose_anchor":
        line = (
            f"verified {result['file']}:{result['line_start']}-{result['line_end']}"
            f" (symbol={result.get('symbol')}, kind={result.get('kind')})"
        )
        return line, line

    payload = {k: v for k, v in result.items() if k != "ok"}
    return json.dumps(payload, indent=None), f"{name} ok"


def _render_read_file(result: dict) -> tuple[str, str]:
    path = result["path"]
    if result.get("content") is None:
        outline = result.get("outline") or []
        body = "\n".join(
            f"  {s['kind']:8s} {s['name']} — lines {s['line_start']}-{s['line_end']}"
            for s in outline
        )
        text = f"{path} ({result['total_lines']} lines) — outline only\n{body}\n{result['hint']}"
        return text, f"read_file {path}: outline, {len(outline)} symbols"
    header = (
        f"{path} lines {result['start']}-{result['end']} "
        f"of {result['total_lines']}"
    )
    shown = result["end"] - result["start"] + 1
    return f"{header}\n{result['content']}", f"read_file {path}:{result['start']}-{result['end']} ({shown} lines)"


def _render_list_files(result: dict) -> tuple[str, str]:
    rows = [
        f"  {f['path']}  role={f['role']}"
        + (f" loc={f['loc']}" if f["loc"] is not None else "")
        + (f" symbols={f['symbol_count']}" if f["symbol_count"] is not None else "")
        for f in result["files"]
    ]
    head = f"{result['total']} file(s)" + (" (truncated)" if result["truncated"] else "")
    return "\n".join([head, *rows]), f"list_files: {len(result['files'])}/{result['total']}"


def _render_search(result: dict) -> tuple[str, str]:
    rows = [f"  {m['path']}:{m['line']}: {m['text']}" for m in result["matches"]]
    head = (
        f"{result['total']} match(es) in {result['files_with_matches']} file(s)"
        + (f" — showing {len(result['matches'])}" if result["truncated"] else "")
    )
    return "\n".join([head, *rows]), f"search_code: {result['total']} matches"


def _render_symbols(result: dict) -> tuple[str, str]:
    rows = [
        f"  {s['kind']:8s} {s['qualified_name']} — {s['file']}:{s['line_start']}-{s['line_end']}"
        for s in result["symbols"]
    ]
    head = f"{result['total']} symbol(s)" + (" (truncated)" if result["truncated"] else "")
    return "\n".join([head, *rows]), f"symbols: {len(result['symbols'])}/{result['total']}"


def _render_neighbors(result: dict) -> tuple[str, str]:
    if result.get("ambiguous"):
        rows = [
            f"  {c['kind']:8s} {c['qualified_name']} — {c['file']}:"
            f"{c['line_start']}-{c['line_end']}"
            for c in result["candidates"]
        ]
        head = (
            f"{result['symbol']} is defined in {len(result['candidates'])} places. "
            f"These are different definitions, not duplicates — check which one "
            f"callers reach. Call `neighbors` again with `file` to follow one."
        )
        return "\n".join([head, *rows]), \
            f"neighbors {result['symbol']}: {len(result['candidates'])} definitions"

    anchor = result["anchor"]
    rows = []
    for n in result["neighbors"]:
        if n.get("import_path"):
            rows.append(
                f"  {n['relation']:12s} importable as `{n['import_path']}`"
                f" — re-exported by {n.get('file')}:{n.get('line_start')}"
            )
            continue
        target = n.get("symbol") or n.get("module") or n.get("file") or "?"
        where = ""
        if n.get("file") and n.get("line_start"):
            where = f" — {n['file']}:{n['line_start']}"
        elif n.get("file"):
            where = f" — {n['file']}"
        approximate = "" if n["exact"] else "  [name-based, verify by reading]"
        rows.append(f"  {n['relation']:12s} {target}{where}{approximate}")
    head = (
        f"{result['symbol']} at {anchor['file']}:{anchor['line_start']}-{anchor['line_end']}"
        f" — {result['total']} neighbour(s)"
        + (" (truncated)" if result["truncated"] else "")
    )
    return "\n".join([head, *rows]), f"neighbors {result['symbol']}: {result['total']}"


# ── the loop ──────────────────────────────────────────────────────────────────

_SALVAGE = (
    "Your exploration budget is now exhausted ({reason}). Do not request any "
    "further tools. Report what you established, and state plainly what you did "
    "not get to — a partial account with an honest gap is worth more than a "
    "confident one that fills the gap by guessing."
)

# Appended to the tool results of the turn that crosses the warning threshold.
# Exploration expands to fill whatever budget exists — measured directly: raising
# the turn budget 12 -> 18 raised source read ~25% and left submission exactly as
# late as before, so the report was still rejected with no turns left to repair
# it. The model cannot plan a repair round-trip around a budget it cannot see, so
# the harness states it (§5.4: exit criteria are stated to the model). One line,
# deterministic, once per run.
_BUDGET_NOTICE = (
    "[budget] {remaining} of {total} turns remain. If a report is required and "
    "your obligations are met, submit on your next turn rather than continuing to "
    "explore — a submission is checked, and you will need at least one spare turn "
    "to repair anything it names. Unverified citations are the most common gap."
)

# Warn when this fraction of the turn budget remains (at least 2 turns, so a
# rejection can still be repaired).
_WARN_REMAINING_FRACTION = 0.25


def explore(
    *,
    client,
    repo_path: str,
    instructions: str,
    task: str,
    skeleton: Skeleton | None = None,
    report: ReportSpec | None = None,
    budget: Budget | None = None,
    model: str = MODEL,
    max_tokens: int = MAX_TOKENS,
    on_call=None,
    tool_guide: str = TOOL_GUIDE_DEFAULT,
    validate=None,
    conversation_breakpoints: int = 2,
    dedupe_identical_calls: bool = True,
) -> Exploration:
    """Run one budgeted exploration and return everything it produced.

    ``instructions`` and ``task`` split the prompt by lifetime: instructions are
    the stable, cacheable brief (what this exploration is for, what must be true
    before it may stop), while ``task`` is the per-run request and stays out of
    the cached prefix.

    ``validate`` closes the loop from §5.4: given the submitted report it returns
    ``None`` to accept, or a message naming what is missing. A rejected report is
    fed back and exploration continues **within the same budget**, so a contract
    can be enforced by our code rather than requested in a prompt (D13). When the
    budget runs out first the report is accepted as-is, with the gap recorded —
    exhaustion yields a partial result, not a discarded one.

    ``tool_guide`` selects the exploration policy and ``conversation_breakpoints``
    the cache strategy; both are Stage-2 experiment variables rather than settings
    anyone should need in production.

    Never raises. Tool failures become tool results the model can recover from;
    an API failure ends the loop with ``stop_reason == "api_error"`` and whatever
    was gathered up to that point. ``on_call`` receives each ``ToolCall`` as it
    completes, which is what makes exploration legible while it runs (OQ3).
    """
    budget = budget or Budget()
    system = seed_blocks(instructions, skeleton, tool_guide)
    tool_defs = list(TOOL_SCHEMAS) + ([report.as_tool()] if report else [])

    result = Exploration(stop_reason=ANSWERED)
    messages: list[dict] = [{"role": "user", "content": task}]
    started = time.monotonic()
    calls_made = 0
    chars_read = 0
    exhausted: str | None = None
    seen_calls: dict[str, int] = {}   # call identity -> turn it first ran
    warned = False                    # the one-shot budget notice

    while True:
        if result.turns >= budget.max_turns:
            exhausted = TURN_BUDGET
            break
        if time.monotonic() - started > budget.max_seconds:
            exhausted = TIME_BUDGET
            break

        response = _call(client, model, max_tokens, system, tool_defs, messages, result)
        if response is None:
            result.stop_reason = API_ERROR
            break
        result.turns += 1

        messages.append({"role": "assistant", "content": _content_params(response)})
        result.text = _text_of(response) or result.text

        uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
        if not uses:
            result.stop_reason = ANSWERED
            break

        blocks: list[dict] = []
        reported = False
        for use in uses:
            arguments = dict(use.input or {})
            if report and use.name == report.name:
                # A submission cut off at max_tokens arrives as mangled JSON.
                # Validating the wreckage produces feedback about the wrong
                # problem ("0 components established"), which sends the model
                # into a resubmit loop that truncates identically every time —
                # observed burning 13 straight rejections. Name the real cause.
                if getattr(response, "stop_reason", None) == "max_tokens":
                    gap = (
                        "Your submission exceeded the output limit and was cut "
                        "off mid-JSON — the payload arrived mangled, so it could "
                        "not be read. Resubmit the SAME findings more compactly: "
                        "one sentence per description field, no repetition, and "
                        "trim `context` first. Do not gather more evidence."
                    )
                # A validator crash must not kill the loop (RK8): a malformed
                # payload is the model's mistake to fix, so it comes back as a
                # rejection naming the problem rather than as our exception.
                elif validate is None:
                    gap = None
                else:
                    try:
                        gap = validate(arguments)
                    except Exception as exc:
                        gap = (
                            f"The report could not be validated: "
                            f"{type(exc).__name__}: {exc}. Check that every entry "
                            f"matches the schema — each list item must be an "
                            f"object with the required fields, not a bare string."
                        )
                        result.errors.append(f"validator raised: {exc}")
                if gap is None:
                    result.output = arguments
                    result.contract_met = None if validate is None else True
                    reported = True
                    verdict, accepted = "recorded", True
                else:
                    # The contract is not satisfied. Hand the gap back and keep
                    # exploring on the remaining budget: this is the difference
                    # between coverage enforced in code and coverage requested in
                    # a prompt.
                    result.rejections.append(gap)
                    verdict, accepted = gap, False
                blocks.append({
                    "type": "tool_result", "tool_use_id": use.id, "content": verdict,
                    **({} if accepted else {"is_error": True}),
                })
                result.trace.append(ToolCall(
                    turn=result.turns, name=use.name, arguments=arguments,
                    ok=accepted, error=None if accepted else "contract_not_met",
                    result_chars=0 if accepted else len(verdict),
                    summary=f"{use.name} {'submitted' if accepted else 'rejected'}",
                    facts={"accepted": accepted},
                ))
                continue

            key = _call_key(use.name, arguments)
            previous = seen_calls.get(key)
            if dedupe_identical_calls and previous is not None:
                text = _DUPLICATE.format(turn=previous)
                summary = f"{use.name} duplicate of turn {previous} — not re-run"
                outcome = {"ok": True}
                facts = {"duplicate_of": previous}
            else:
                seen_calls[key] = result.turns
                outcome = tools.run_tool(use.name, repo_path, **arguments)
                text, summary = _render(use.name, outcome)
                facts = _facts(use.name, outcome)
            calls_made += 1
            chars_read += len(text)
            call = ToolCall(
                turn=result.turns, name=use.name, arguments=arguments,
                ok=bool(outcome.get("ok")), error=outcome.get("error"),
                result_chars=len(text), summary=summary,
                facts=facts,
            )
            result.trace.append(call)
            if on_call is not None:
                on_call(call)
            blocks.append({
                "type": "tool_result", "tool_use_id": use.id, "content": text,
                **({"is_error": True} if not outcome.get("ok") else {}),
            })

        remaining = budget.max_turns - result.turns
        if (
            report is not None
            and not warned
            and remaining <= max(2, int(budget.max_turns * _WARN_REMAINING_FRACTION))
        ):
            warned = True
            blocks.append({
                "type": "text",
                "text": _BUDGET_NOTICE.format(
                    remaining=remaining, total=budget.max_turns
                ),
            })

        messages.append({"role": "user", "content": blocks})
        _mark_conversation_cache(messages, conversation_breakpoints)

        if reported:
            result.stop_reason = REPORTED
            break
        if calls_made >= budget.max_tool_calls:
            exhausted = TOOL_CALL_BUDGET
            break
        if chars_read >= budget.max_result_chars:
            exhausted = READ_BUDGET
            break

    if exhausted:
        result.stop_reason = exhausted
        _salvage(client, model, max_tokens, system, tool_defs, messages, result,
                 report, exhausted, validate)

    # A budget stop keeps its own reason even if salvage produced nothing — the
    # cause of the stop is the useful fact, and `output is None` already tells a
    # caller there is no payload. NO_REPORT is for the other case: the model
    # finished talking and simply never submitted.
    if report and result.output is None and result.stop_reason == ANSWERED:
        result.stop_reason = NO_REPORT
    result.seconds = time.monotonic() - started
    return result


# At most 4 cache breakpoints are allowed per request, and the seed already
# spends one, so this is clamped to 3. Two is the Stage-1 default: the newest is
# where this turn's prefix is written, and the one before it guards against the
# 20-block lookback window being overrun by a turn with many tool results.
#
# Each breakpoint is also a cache *write*, billed at 1.25x against reads at 0.1x,
# so a second one is not free — whether it pays for itself is Stage 2's
# cache-strategy A/B, not something to settle by argument.
_MAX_CONVERSATION_BREAKPOINTS = 3


def _mark_conversation_cache(messages: list[dict], keep_newest: int = 2) -> None:
    """Move the conversation breakpoints to the N newest tool-result turns."""
    budget = max(0, min(int(keep_newest), _MAX_CONVERSATION_BREAKPOINTS))
    marked = 0
    for message in reversed(messages):
        content = message.get("content")
        if not isinstance(content, list):
            continue
        keep = message.get("role") == "user" and marked < budget
        for block in content:
            if not isinstance(block, dict):
                continue
            block.pop("cache_control", None)
        if keep:
            content[-1]["cache_control"] = {"type": "ephemeral"}
            marked += 1


def _salvage(
    client, model, max_tokens, system, tool_defs, messages, result, report, reason,
    validate=None,
) -> None:
    """One final turn after budget exhaustion, so a partial result is still a result.

    Budgeted out is not the same as empty: the model has read real code by this
    point, and the point of §5.4 is that exhaustion yields a partial dossier with
    an enumerated gap. This costs one API call beyond ``max_turns`` — deliberately,
    because the alternative is discarding everything the run paid for.

    A salvaged report is **accepted without being gated** — there is no budget left
    to send it back — but it is still *validated for the record*, so `contract_met`
    and any downstream measurement describe the payload actually returned rather
    than the last one that was rejected.
    """
    messages.append({"role": "user", "content": _SALVAGE.format(reason=reason)})
    response = _call(
        client, model, max_tokens, system, tool_defs, messages, result,
        tool_choice={"type": "tool", "name": report.name} if report else {"type": "none"},
    )
    if response is None:
        return
    result.turns += 1
    result.text = _text_of(response) or result.text
    if not report:
        return
    for block in response.content:
        if getattr(block, "type", None) != "tool_use" or block.name != report.name:
            continue
        result.output = dict(block.input or {})
        gap = validate(result.output) if validate is not None else None
        result.contract_met = None if validate is None else gap is None
        if gap is not None:
            result.rejections.append(gap)
        result.trace.append(ToolCall(
            turn=result.turns, name=block.name, arguments=result.output,
            ok=True, error=None, result_chars=0,
            summary=f"{block.name} submitted after {reason}",
            facts={"accepted": True, "gated": False,
                   "contract_met": result.contract_met},
        ))
        if gap is not None:
            _repair(client, model, max_tokens, system, tool_defs, messages, result,
                    report, validate, response, block)
        return


_SALVAGE_DECLINED = (
    "Not run — the exploration budget is exhausted. Resubmit the report from what "
    "you already have."
)


def _repair(
    client, model, max_tokens, system, tool_defs, messages, result, report,
    validate, response, submission,
) -> None:
    """One re-emission turn when the last submission was *unreadable*, not thin.

    A payload whose arrays arrived as markup carries findings the run already
    paid to gather; discarding them loses real work to a transmission fault, and
    the downstream symptom is a dossier with no resolvable evidence at all —
    which the Mentor can only refuse. This is a re-send, not more exploration:
    forced straight back to the report tool, told not to gather anything, and
    offered exactly once. A dossier that is genuinely thin gets no repair turn,
    because re-emitting it would not make it less thin.
    """
    ask = getattr(validate, "repair_prompt", None)
    message = ask(result.output) if callable(ask) else None
    if not message:
        return

    # EVERY tool_use in the appended assistant turn needs a tool_result, not just
    # the report's. The salvage turn forces the report tool but does not stop the
    # model emitting exploration calls alongside it — observed: nine of them in
    # one turn — and the API rejects the whole request when any is unanswered.
    # Those calls are not run: the budget that ended the loop has not come back.
    messages.append({"role": "assistant", "content": _content_params(response)})
    results = [
        {
            "type": "tool_result", "tool_use_id": block.id,
            "content": (message if block.id == submission.id else _SALVAGE_DECLINED),
            "is_error": True,
        }
        for block in response.content
        if getattr(block, "type", None) == "tool_use"
    ]
    messages.append({"role": "user", "content": results})
    repaired = _call(
        client, model, max_tokens, system, tool_defs, messages, result,
        tool_choice={"type": "tool", "name": report.name},
    )
    if repaired is None:
        return
    result.turns += 1
    for block in repaired.content:
        if getattr(block, "type", None) != "tool_use" or block.name != report.name:
            continue
        payload = dict(block.input or {})
        gap = validate(payload) if validate is not None else None
        still_unreadable = bool(callable(ask) and ask(payload))
        result.trace.append(ToolCall(
            turn=result.turns, name=block.name, arguments=payload,
            ok=True, error=None, result_chars=0,
            summary=f"{block.name} re-emitted after a serialisation fault",
            facts={"repair": True, "readable": not still_unreadable,
                   "contract_met": gap is None},
        ))
        if still_unreadable:
            # The re-send failed the same way. Keep the first payload and the
            # honest stop reason; a second repair turn would be a retry loop.
            result.rejections.append(gap or message)
            return
        result.output = payload
        result.contract_met = None if validate is None else gap is None
        if gap is not None:
            result.rejections.append(gap)
        return


def _call(
    client, model, max_tokens, system, tool_defs, messages, result, tool_choice=None
):
    """One API call. Records usage; converts any failure into None + an error."""
    kwargs = dict(
        model=model, max_tokens=max_tokens, system=system,
        tools=tool_defs, messages=messages,
    )
    if tool_choice is not None:
        kwargs["tool_choice"] = tool_choice
    try:
        response = client.messages.create(**kwargs)
    except Exception as exc:  # RK8 — a failure is a result, never a raise
        result.errors.append(f"explore: API call failed: {type(exc).__name__}: {exc}")
        return None
    usage = getattr(response, "usage", None)
    if usage is not None:
        result.usage.add(usage)
    return response


def _content_params(response) -> list[dict]:
    """The assistant turn, as plain dicts safe to send back.

    Only text and tool_use survive: everything else a response may carry is
    either not replayable or not needed to continue the loop.
    """
    out: list[dict] = []
    for block in response.content:
        kind = getattr(block, "type", None)
        if kind == "text":
            out.append({"type": "text", "text": block.text})
        elif kind == "tool_use":
            out.append({
                "type": "tool_use", "id": block.id,
                "name": block.name, "input": block.input,
            })
    return out


def _text_of(response) -> str:
    return "\n".join(
        block.text for block in response.content
        if getattr(block, "type", None) == "text"
    ).strip()
