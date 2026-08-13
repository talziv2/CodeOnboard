# Layer B — the goal-agnostic repository survey (Stage 2).
#
# One account of what a repository is and how it is shaped, produced once per
# commit and reusable by every user and every goal. It answers "what exists, and
# what does it do" — never "what matters for this user's goal", which is Layer C.
# That split is what keeps a cached survey valid
# (docs/planning/phases/repo-understanding.md §5.2).
#
# THIS LAYER IS ON TRIAL. H1 asks whether a lightweight, cacheable, goal-agnostic
# survey earns its cost at all, and the honest answers include "make it much
# smaller" and "delete it". So this module is written to be *measured*: it runs in
# isolation through the Stage-1 harness, reports what it cost, and is wired into
# no agent and no pipeline node. Nothing in backend/agents or backend/pipeline
# imports it, and a test enforces that.
#
# The one thing here that is not on trial is the coverage contract (D13). Whatever
# Layer B ends up being — or if it disappears entirely — the account it produces
# is validated against the deterministic skeleton inventory by our code, not
# requested in a prompt. `validate_survey()` is that validation, and it is
# deliberately separable from everything else in this file.

from __future__ import annotations

from dataclasses import dataclass, field

from backend.repo import anchors, explore
from backend.repo.explore import Budget, Exploration, ReportSpec
from backend.repo.skeleton import Skeleton, build_skeleton, normalize_path

# A survey enumerates every subsystem, so its payload is large: on a big library
# that is dozens of subsystem entries plus flows, abstractions and boundaries. The
# Stage-1 default of 4096 output tokens truncates that mid-JSON, which surfaces as
# a hard-to-read validation failure rather than an obvious one.
SURVEY_MAX_TOKENS = 12288

# How many unaccounted names a gap message names before it summarises. A gap that
# lists 28 subsystems is mostly tokens; the model needs to know what is missing,
# not to be handed the list twice.
MAX_NAMED_GAPS = 12


# ── the report contract ───────────────────────────────────────────────────────
#
# Field-level shapes are deliberately narrow. Every field costs output tokens
# once per subsystem, and a survey that lists 28 subsystems at four fields each
# is paying for breadth before it has paid for any depth.

SURVEY_SPEC = ReportSpec(
    name="submit_survey",
    description=(
        "Submit the repository survey. Call this once, when every subsystem in the "
        "inventory is either described or explicitly skipped. If anything is "
        "missing you will be told what, and may keep exploring."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "architecture": {
                "type": "string",
                "description": (
                    "What this repository is and how it is put together, in a few "
                    "sentences. Written for someone who has never seen it."
                ),
            },
            "subsystems": {
                "type": "array",
                "description": (
                    "One entry per subsystem in the inventory you were given. This "
                    "is the breadth obligation: every subsystem is accounted for "
                    "here or in `skipped`."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The subsystem name, exactly as the inventory spells it.",
                        },
                        "responsibility": {
                            "type": "string",
                            "description": "What this subsystem is responsible for, in one sentence.",
                        },
                        "key_file": {
                            "type": "string",
                            "description": "The most representative file in this subsystem.",
                        },
                        "key_symbol": {
                            "type": "string",
                            "description": "Optional: the definition that best represents it.",
                        },
                    },
                    "required": ["name", "responsibility", "key_file"],
                },
            },
            "skipped": {
                "type": "array",
                "description": (
                    "Subsystems you are deliberately not describing, with the "
                    "repository-level reason. Only facts about the repository "
                    "count here — vendored code, generated files, packaging."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["name", "reason"],
                },
            },
            "entry_points": {
                "type": "array",
                "description": (
                    "How this system is entered from outside. There are two "
                    "perspectives and they are often different code:\n"
                    "  runtime — what invokes the system (a server, a CLI, a "
                    "__main__, an ASGI/WSGI callable).\n"
                    "  public_api — what a developer USING this repository "
                    "imports and calls. For a library or framework this is "
                    "usually declared by a package's own `__init__`, and the "
                    "name exported there is frequently not the internal type "
                    "the implementation passes around.\n"
                    "Name the SURFACE, not every export: a handful of entries "
                    "that tell a later investigation where to look. Listing an "
                    "inventory of exports is not this field's job."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string"},
                        "symbol": {"type": "string"},
                        "perspective": {
                            "type": "string",
                            "enum": ["runtime", "public_api"],
                        },
                        "what_it_starts": {"type": "string"},
                    },
                    "required": ["file", "symbol", "perspective", "what_it_starts"],
                },
            },
            "core_abstractions": {
                "type": "array",
                "description": "The few types everything else routes through.",
                "items": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string"},
                        "symbol": {"type": "string"},
                        "role": {"type": "string"},
                    },
                    "required": ["file", "symbol", "role"],
                },
            },
            "flows": {
                "type": "array",
                "description": (
                    "Representative end-to-end paths through the system, each "
                    "crossing several files, in execution order."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "steps": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "file": {"type": "string"},
                                    "symbol": {"type": "string"},
                                    "what_happens": {"type": "string"},
                                },
                                "required": ["file", "symbol", "what_happens"],
                            },
                        },
                    },
                    "required": ["name", "steps"],
                },
            },
            "boundaries": {
                "type": "array",
                "description": (
                    "Seams: where this system is extended, and where it hands off "
                    "to something outside itself."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string"},
                        "symbol": {"type": "string"},
                        "kind": {
                            "type": "string",
                            "enum": ["extension_point", "external_dependency", "trust_boundary"],
                        },
                        "note": {"type": "string"},
                    },
                    "required": ["file", "symbol", "kind", "note"],
                },
            },
            "relationships": {
                "type": "array",
                "description": (
                    "How the major components connect. Each edge should be one you "
                    "confirmed, not one the names imply."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "from_file": {"type": "string"},
                        "from_symbol": {"type": "string"},
                        "to_file": {"type": "string"},
                        "to_symbol": {"type": "string"},
                        "kind": {
                            "type": "string",
                            "enum": ["calls", "constructs", "extends", "implements",
                                     "registers", "delegates_to", "configures"],
                        },
                        "note": {"type": "string"},
                    },
                    "required": ["from_file", "from_symbol", "to_file", "to_symbol",
                                 "kind", "note"],
                },
            },
            "needs_investigation": {
                "type": "array",
                "description": (
                    "Areas a later, goal-specific investigation should go deeper on, "
                    "and what question it would need to answer. Say what you did not "
                    "establish — not what a particular reader should study."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "area": {"type": "string"},
                        "open_question": {"type": "string"},
                    },
                    "required": ["area", "open_question"],
                },
            },
            "testing_posture": {
                "type": "string",
                "description": "How this repository is tested, and where the tests live.",
            },
            "infrastructure": {
                "type": "array",
                "description": (
                    "Supporting areas that are not runtime library code: build, "
                    "packaging, CI, tooling, vendored dependencies."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "what_it_does": {"type": "string"},
                    },
                    "required": ["path", "what_it_does"],
                },
            },
            "conventions": {
                "type": "array",
                "description": (
                    "Patterns a newcomer would need to know to read this codebase "
                    "the way its authors intended."
                ),
                "items": {"type": "string"},
            },
            "docs": {
                "type": "array",
                "description": "Documentation that exists in the repository, and what it covers.",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "what_it_covers": {"type": "string"},
                    },
                    "required": ["path", "what_it_covers"],
                },
            },
        },
        "required": [
            "architecture", "subsystems", "skipped", "entry_points",
            "core_abstractions", "relationships", "flows", "boundaries",
            "needs_investigation", "testing_posture", "docs",
        ],
    },
)


# ── the brief ─────────────────────────────────────────────────────────────────
#
# Goal-agnostic by construction: it must never mention a particular repository, a
# framework, or a subsystem that is expected to exist. An improvement that comes
# from naming the answer here is not an improvement to repository exploration.

SURVEY_INSTRUCTIONS = """\
You are surveying an unfamiliar codebase to produce the repository's standing
description: one account of what it is and how it is built, which many different
readers with many different goals will later rely on.

Because it is written once and reused, it must be goal-agnostic. Describe what
exists and what it does. Do not decide what is or is not worth learning — you do
not know who is reading, or why.

Two obligations, and they are different in kind.

BREADTH is not optional. You were given a complete inventory of this repository's
subsystems. Every one of them must appear in your report: either described, with
a one-sentence responsibility and a representative file, or listed as skipped
with a reason. A subsystem you never mention is a hole in the account, and the
report will be rejected for it — the check is mechanical, not a matter of taste.
A skip is legitimate only for a fact about the repository itself: vendored
third-party code, generated files, packaging and release scaffolding. "Not
interesting" and "not relevant" are not reasons; you do not know what the reader
needs.

Accounting for a subsystem is not the same as deeply reading it. For breadth, a
one-sentence responsibility supported by its symbol outline is enough, and saying
so plainly is a good answer. What is not acceptable is a confident claim about
behaviour you never looked at, or a subsystem that quietly goes unmentioned.

DEPTH is selective, and this is where judgement belongs. Do not investigate every
subsystem deeply. Spend your reading on what the whole system routes through: the
entry points a caller actually reaches first, the few abstractions everything
else is expressed in terms of, the relationships that connect the major
components, one or two flows traced end to end across several files, and the
seams where the system is extended or hands off to something outside itself.

Two of those entry points are worth separating, because on a library they are
different code: what STARTS this system running, and what a developer USING this
system writes. Where the repository is something other people import, name that
public surface too — a package `__init__` states it structurally, and `neighbors`
with `exported_by` will tell you the dotted path a caller types. Name the surface
and move on; enumerating every export is not breadth, it is an inventory.

Where you could not establish something, say so in `needs_investigation` — the
area and the question still open. An honest gap is more useful than a guess, and
a later investigation will start from it.

HOW TO WORK. Use the deterministic structure to decide *where* to read; use the
source to understand and verify what it *means*. In practice that is a loop: the
inventory suggests likely areas, `symbols`/`neighbors`/`search_code` narrow them
to specific definitions, a targeted read confirms or corrects your hypothesis,
and what you find points at the next thing to follow. Read as much as you
genuinely need — a wide read is fine when the question warrants it. What wastes
your budget is reading a file to discover what is in it when an outline would
have told you, or reading the same thing twice.

Every file and symbol you cite must be real. Verify anchors with `propose_anchor`
before you submit: a symbol that is imported into a file is not defined there,
and citing it as though it were is the most common way a report gets rejected."""


# ── coverage: the part that is not on trial ───────────────────────────────────


@dataclass(frozen=True)
class Coverage:
    """The §5.6 contract, as computed by our code from the skeleton inventory."""

    covered: dict[str, str] = field(default_factory=dict)              # name -> key_file
    skipped_with_reason: dict[str, str] = field(default_factory=dict)  # name -> reason
    unaccounted: list[str] = field(default_factory=list)               # MUST be empty
    unknown: list[str] = field(default_factory=list)                   # named, not in inventory

    @property
    def required(self) -> int:
        return len(self.covered) + len(self.skipped_with_reason) + len(self.unaccounted)

    @property
    def complete(self) -> bool:
        return not self.unaccounted

    @property
    def covered_ratio(self) -> float:
        return len(self.covered) / self.required if self.required else 0.0


@dataclass(frozen=True)
class SurveyCheck:
    """Everything our code can decide about a submitted survey, without a model."""

    coverage: Coverage
    resolved_anchors: int = 0
    unresolved_anchors: list[str] = field(default_factory=list)
    vacuous: list[str] = field(default_factory=list)   # entries that say nothing
    misfiled: list[str] = field(default_factory=list)  # key_file not in that subsystem

    @property
    def total_anchors(self) -> int:
        return self.resolved_anchors + len(self.unresolved_anchors)

    @property
    def grounding_accuracy(self) -> float:
        return self.resolved_anchors / self.total_anchors if self.total_anchors else 1.0

    @property
    def ok(self) -> bool:
        return (
            self.coverage.complete
            and not self.unresolved_anchors
            and not self.vacuous
            and not self.misfiled
        )

    def gap_message(self) -> str:
        """What to hand back to the model when the contract is not satisfied.

        Names what is missing and nothing else. It must not hint at what the
        answer should be — that would be teaching the model this repository's
        expected result rather than testing whether it can survey a repository.
        """
        parts: list[str] = []
        missing = self.coverage.unaccounted
        if missing:
            shown = ", ".join(missing[:MAX_NAMED_GAPS])
            more = f" (and {len(missing) - MAX_NAMED_GAPS} more)" if len(missing) > MAX_NAMED_GAPS else ""
            parts.append(
                f"{len(missing)} subsystem(s) from the inventory are neither described "
                f"nor skipped: {shown}{more}. Account for each one — describe it, or "
                f"skip it with a repository-level reason."
            )
        if self.unresolved_anchors:
            shown = "; ".join(self.unresolved_anchors[:MAX_NAMED_GAPS])
            parts.append(
                f"{len(self.unresolved_anchors)} citation(s) do not resolve against the "
                f"repository: {shown}. Use `symbols` or `propose_anchor` to find the real "
                f"location, then correct or drop them."
            )
        if self.misfiled:
            shown = "; ".join(self.misfiled[:MAX_NAMED_GAPS])
            parts.append(
                f"{len(self.misfiled)} subsystem(s) cite a representative file that does "
                f"not belong to that subsystem: {shown}."
            )
        if self.vacuous:
            shown = ", ".join(self.vacuous[:MAX_NAMED_GAPS])
            parts.append(f"{len(self.vacuous)} entry(ies) are empty: {shown}.")
        if self.coverage.unknown:
            # Informational: not a rejection on its own, but worth saying so the
            # model can fix a name it invented.
            shown = ", ".join(self.coverage.unknown[:MAX_NAMED_GAPS])
            parts.append(
                f"These names are not subsystems in the inventory and were ignored: {shown}."
            )
        return " ".join(parts) or "The report does not satisfy the coverage contract."


def _normalize(name: str) -> str:
    """Fold a subsystem name to a comparable key."""
    key = normalize_path(str(name or "")).strip().strip("/").lower()
    return key[:-3] if key.endswith(".py") else key


def _name_index(inventory: dict[str, list[str]]) -> dict[str, str]:
    """Lookup keys for inventory names, refusing ambiguity rather than guessing.

    The inventory's spelling and the model's are both reasonable and often differ:
    a subsystem the inventory calls `core` may be written `pkg/core` or `core/`
    from the file listing, and one the inventory spells `src/lib/sessions.py` may
    be written `sessions.py` (root modules become full paths when a stray
    top-level file collapses the source root — OQ7's known wart).

    Matching is therefore two-way: both the full folded name and its last segment
    are indexed, and a lookup falls back to its own last segment. Two subsystems
    that fold to the same key are made unmatchable instead, because coverage
    credited to the wrong subsystem is worse than a reported gap — the contract
    would pass while a subsystem really had disappeared.
    """
    index: dict[str, str] = {}
    collisions: set[str] = set()

    def offer(key: str, name: str) -> None:
        if not key:
            return
        if index.get(key, name) != name:
            collisions.add(key)
        index.setdefault(key, name)

    for name in inventory:
        normalized = _normalize(name)
        offer(normalized, name)
        offer(normalized.rsplit("/", 1)[-1], name)   # basename form
    for key in collisions:
        index.pop(key, None)
    return index


def _match(index: dict[str, str], raw: str) -> str | None:
    """Resolve a submitted name to an inventory name, or None."""
    key = _normalize(raw)
    if key in index:
        return index[key]
    return index.get(key.rsplit("/", 1)[-1])


def validate_survey(skeleton: Skeleton, payload: dict) -> SurveyCheck:
    """Check a submitted survey against the repository. No model involved.

    Three deterministic checks, all from §5.4/§5.6: every required subsystem is
    accounted for, every citation resolves, and no entry is vacuous or misfiled.
    """
    inventory = skeleton.subsystems()
    index = _name_index(inventory)
    files_by_subsystem = {
        name: {normalize_path(f) for f in files} for name, files in inventory.items()
    }

    covered: dict[str, str] = {}
    skipped: dict[str, str] = {}
    unknown: list[str] = []
    vacuous: list[str] = []
    misfiled: list[str] = []

    for entry in payload.get("subsystems") or []:
        raw = str(entry.get("name") or "")
        name = _match(index, raw)
        if name is None:
            unknown.append(raw or "<unnamed>")
            continue
        responsibility = str(entry.get("responsibility") or "").strip()
        key_file = str(entry.get("key_file") or "").strip()
        if not responsibility or not key_file:
            vacuous.append(name)
            continue
        canonical = skeleton.canonical_file(key_file)
        if canonical is None or canonical not in files_by_subsystem[name]:
            misfiled.append(f"{name} -> {key_file}")
            continue
        covered[name] = canonical

    for entry in payload.get("skipped") or []:
        raw = str(entry.get("name") or "")
        name = _match(index, raw)
        if name is None:
            unknown.append(raw or "<unnamed>")
            continue
        reason = str(entry.get("reason") or "").strip()
        if not reason:
            vacuous.append(name)
            continue
        if name not in covered:
            skipped[name] = reason

    unaccounted = [
        name for name in inventory
        if name not in covered and name not in skipped
    ]

    resolved, unresolved = _check_anchors(skeleton, payload)
    return SurveyCheck(
        coverage=Coverage(
            covered=covered, skipped_with_reason=skipped,
            unaccounted=unaccounted, unknown=unknown,
        ),
        resolved_anchors=resolved,
        unresolved_anchors=unresolved,
        vacuous=vacuous,
        misfiled=misfiled,
    )


def cited_anchors(payload: dict) -> list[tuple[str, str, str]]:
    """Every (where, file, symbol) the survey claims. One place, so nothing escapes."""
    cited: list[tuple[str, str, str]] = []
    for entry in payload.get("entry_points") or []:
        cited.append(("entry_point", entry.get("file"), entry.get("symbol")))
    for entry in payload.get("core_abstractions") or []:
        cited.append(("core_abstraction", entry.get("file"), entry.get("symbol")))
    for entry in payload.get("boundaries") or []:
        cited.append(("boundary", entry.get("file"), entry.get("symbol")))
    for entry in payload.get("relationships") or []:
        cited.append(("relationship_from", entry.get("from_file"), entry.get("from_symbol")))
        cited.append(("relationship_to", entry.get("to_file"), entry.get("to_symbol")))
    for flow in payload.get("flows") or []:
        name = flow.get("name") or "flow"
        for step in flow.get("steps") or []:
            cited.append((f"flow:{name}", step.get("file"), step.get("symbol")))
    for entry in payload.get("subsystems") or []:
        if entry.get("key_symbol"):
            cited.append(("subsystem", entry.get("key_file"), entry.get("key_symbol")))
    return [(where, str(f or ""), str(s or "")) for where, f, s in cited]


def _check_anchors(skeleton: Skeleton, payload: dict) -> tuple[int, list[str]]:
    resolved = 0
    unresolved: list[str] = []
    for where, file, symbol in cited_anchors(payload):
        if not file or not symbol:
            unresolved.append(f"{where}: incomplete citation {file or '?'}:{symbol or '?'}")
            continue
        resolution = anchors.resolve(skeleton, file, symbol=symbol)
        if resolution.ok:
            resolved += 1
        else:
            unresolved.append(f"{where}: {file}:{symbol} ({resolution.reason})")
    return resolved, unresolved


class SurveyValidator:
    """`explore(validate=...)` hook that also keeps every attempt, for measurement.

    The accepted survey's grounding accuracy is 100% by construction — the
    contract refuses anything else. The number that carries information is what
    the *first* submission looked like, so every attempt is retained.
    """

    def __init__(self, skeleton: Skeleton, enforce: bool = True):
        self.skeleton = skeleton
        self.enforce = enforce
        self.attempts: list[SurveyCheck] = []
        self.payloads: list[dict] = []

    def __call__(self, payload: dict) -> str | None:
        check = validate_survey(self.skeleton, payload)
        self.attempts.append(check)
        self.payloads.append(payload)
        if check.ok or not self.enforce:
            return None
        return check.gap_message()

    @property
    def first(self) -> SurveyCheck | None:
        return self.attempts[0] if self.attempts else None

    @property
    def last(self) -> SurveyCheck | None:
        return self.attempts[-1] if self.attempts else None


# ── running one ───────────────────────────────────────────────────────────────

SURVEY_TASK = (
    "Survey this repository. Account for every subsystem in the inventory, and go "
    "deep on the entry points, core abstractions, representative flows and "
    "boundaries. Submit the survey when the account is complete."
)


@dataclass
class SurveyRun:
    """One survey attempt: the exploration, the payload, and the verdict on it."""

    exploration: Exploration
    validator: SurveyValidator
    skeleton: Skeleton

    @property
    def survey(self) -> dict | None:
        """The returned survey, or the last attempt when nothing was returned."""
        if self.exploration.output is not None:
            return self.exploration.output
        return self.validator.payloads[-1] if self.validator.payloads else None

    @property
    def check(self) -> SurveyCheck | None:
        """The verdict on whatever `survey` returns.

        Every submission is validated — including one salvaged after budget
        exhaustion — so this always describes the payload actually returned, not
        the last one that happened to be rejected.
        """
        return self.validator.last

    @property
    def produced(self) -> bool:
        """A survey came back at all."""
        return self.exploration.output is not None

    @property
    def accepted(self) -> bool:
        """A survey came back **and** satisfied the coverage contract.

        Distinct from `produced` on purpose: a report salvaged at budget
        exhaustion is returned with its gap recorded, and counting that as a pass
        would report exactly the silent incompleteness D13 exists to prevent.
        """
        return self.exploration.contract_met is True


def run_survey(
    *,
    client,
    repo_path: str,
    skeleton: Skeleton | None = None,
    budget: Budget | None = None,
    tool_guide: str = explore.TOOL_GUIDE_DEFAULT,
    conversation_breakpoints: int = 2,
    enforce_contract: bool = True,
    dedupe_identical_calls: bool = True,
    model: str = explore.MODEL,
    max_tokens: int = SURVEY_MAX_TOKENS,
    on_call=None,
) -> SurveyRun:
    """Produce one repository survey through the Stage-1 exploration harness.

    Runs in isolation: it takes a client and a checkout and returns an artifact.
    It reads no `OnboardState`, writes no database, and is called by no agent —
    Layer B has to earn its place before anything depends on it (H1).
    """
    sk = skeleton if skeleton is not None else build_skeleton(repo_path)
    validator = SurveyValidator(sk, enforce=enforce_contract)
    exploration = explore.explore(
        client=client,
        repo_path=repo_path,
        instructions=SURVEY_INSTRUCTIONS,
        task=SURVEY_TASK,
        skeleton=sk,
        report=SURVEY_SPEC,
        budget=budget,
        model=model,
        max_tokens=max_tokens,
        on_call=on_call,
        tool_guide=tool_guide,
        validate=validator,
        conversation_breakpoints=conversation_breakpoints,
        dedupe_identical_calls=dedupe_identical_calls,
    )
    return SurveyRun(exploration=exploration, validator=validator, skeleton=sk)
