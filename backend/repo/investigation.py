# Layer C — Goal Investigation (Stage 3).
#
# Where repository understanding becomes goal-specific. Given the user's goal —
# and, when one exists, the Layer B survey as a starting map — the investigator
# explores the repository through the Stage-1 tools and produces an Investigation
# Dossier: the grounded, goal-relevant model of what the user actually needs to
# understand, shaped for learning-path construction rather than for documentation.
#
# Division of labour (settled at Stage 2, user-approved):
#   Layer B (survey.py)  breadth — architecture, subsystems, entry points,
#                        testing/docs/infrastructure, needs_investigation
#   Layer C (this file)  depth — goal-relevant components, flows, relationships,
#                        contracts, prerequisites, uncertainty
#
# Rules this module holds itself to:
#
#   1. THE SURVEY IS A MAP, NOT EVIDENCE. It seeds the exploration and is
#      clearly labelled as unverified context; every claim promoted into the
#      dossier must resolve against the repository via the Stage-0 oracle.
#   2. STOPPING IS ABOUT UNDERSTANDING, NOT SPEND. The loop ends when the
#      goal-typed exit criteria are met and every anchor resolves — budgets are
#      safety rails against runaways, not rationing (§0). Remaining uncertainty
#      is recorded in `open_questions`, never papered over.
#   3. NOTHING HERE TOUCHES PRODUCTION. Stage 3 is an experiment: no agent or
#      pipeline module imports this file, and a test enforces it. The chunk-dict
#      rendering below exists so the *experiment* can hand a dossier to the
#      existing Mentor without changing the Mentor.

from __future__ import annotations

from dataclasses import dataclass, field

from backend.repo import anchors, explore
from backend.repo.explore import Budget, Exploration, ReportSpec
from backend.repo.skeleton import Skeleton, build_skeleton

INVESTIGATION_MAX_TOKENS = 12288

# The six goal types the product recognises (CLAUDE.md). Unknown types fall back
# to BASE_CRITERIA rather than failing — a new goal type must not brick Layer C.
GOAL_TYPES = (
    "understand_system", "understand_component", "understand_architecture",
    "contribute_code", "improve_existing_system", "debug_issue",
)


# ── the report contract ───────────────────────────────────────────────────────

_ANCHOR = {
    "file": {"type": "string"},
    "symbol": {"type": "string"},
}

INVESTIGATION_SPEC = ReportSpec(
    name="submit_dossier",
    description=(
        "Submit the investigation dossier. Call this once your grounded "
        "understanding is sufficient to explain the goal-relevant behaviour, its "
        "important dependencies, and the concepts a learning path would need. If "
        "something is missing you will be told what, and may keep investigating."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "understanding": {
                "type": "string",
                "description": (
                    "What someone pursuing this goal needs to understand, in a "
                    "short paragraph: the shape of the answer, not a table of "
                    "contents."
                ),
            },
            "components": {
                "type": "array",
                "description": (
                    "The code that matters for this goal, most important first. "
                    "Only include what you verified; each entry needs a reason "
                    "specific to the goal, not a generic description."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        **_ANCHOR,
                        "role_in_goal": {
                            "type": "string",
                            "description": "What this does in the goal-relevant behaviour.",
                        },
                        "why_it_matters": {
                            "type": "string",
                            "description": "Why the user must understand it for THIS goal.",
                        },
                    },
                    "required": ["file", "symbol", "role_in_goal", "why_it_matters"],
                },
            },
            "entry_points": {
                "type": "array",
                "description": (
                    "Where the goal-relevant behaviour is entered from outside. "
                    "Two perspectives, often different definitions:\n"
                    "  runtime — what invokes the behaviour when the system runs.\n"
                    "  public_api — the name a developer USING this code imports "
                    "and calls to reach it. Claim this only for a symbol you "
                    "verified is actually reachable that way; `neighbors` with "
                    "`exported_by` gives the dotted path a caller types.\n"
                    "Where the goal is about using or extending this code, the "
                    "public_api perspective is the one the learner meets first."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        **_ANCHOR,
                        "perspective": {
                            "type": "string",
                            "enum": ["runtime", "public_api"],
                        },
                        "how_it_enters": {"type": "string"},
                    },
                    "required": ["file", "symbol", "perspective", "how_it_enters"],
                },
            },
            "flows": {
                "type": "array",
                "description": (
                    "The execution or data paths the goal turns on, traced step "
                    "by step through code you actually read."
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
                                    **_ANCHOR,
                                    "what_happens": {"type": "string"},
                                },
                                "required": ["file", "symbol", "what_happens"],
                            },
                        },
                    },
                    "required": ["name", "steps"],
                },
            },
            "relationships": {
                "type": "array",
                "description": "Confirmed connections between goal-relevant components.",
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
            "contracts": {
                "type": "array",
                "description": (
                    "Abstractions and interfaces the goal-relevant code is written "
                    "against — what a caller may assume, what an implementer must "
                    "provide."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        **_ANCHOR,
                        "contract": {"type": "string"},
                    },
                    "required": ["file", "symbol", "contract"],
                },
            },
            "prerequisites": {
                "type": "array",
                "description": (
                    "Concepts someone must already hold for the goal-relevant "
                    "code to make sense. Anchor them to code where an anchor "
                    "exists; a general concept may have none."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "concept": {"type": "string"},
                        "why_needed": {"type": "string"},
                        "file": {"type": "string"},
                        "symbol": {"type": "string"},
                    },
                    "required": ["concept", "why_needed"],
                },
            },
            "evidence_refs": {
                "type": "array",
                "description": (
                    "Tests or documentation that clarify the goal-relevant "
                    "behaviour, when they genuinely do."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "clarifies": {"type": "string"},
                    },
                    "required": ["path", "clarifies"],
                },
            },
            "context": {
                "type": "array",
                "description": (
                    "Useful facts discovered on the way that do not fit above but "
                    "a teacher would want to know."
                ),
                "items": {"type": "string"},
            },
            "open_questions": {
                "type": "array",
                "description": (
                    "What you could not establish, and why it matters. Honest "
                    "uncertainty recorded here is worth more than a guess "
                    "recorded above."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "why_it_matters": {"type": "string"},
                    },
                    "required": ["question", "why_it_matters"],
                },
            },
        },
        "required": ["understanding", "components", "entry_points", "flows",
                     "relationships", "contracts", "prerequisites",
                     "evidence_refs", "context", "open_questions"],
    },
)


# ── the brief ─────────────────────────────────────────────────────────────────

INVESTIGATION_INSTRUCTIONS = """\
You are investigating an unfamiliar codebase on behalf of one person with one
stated goal. Your output is the evidence a teacher will use to build that
person's learning path — so gather what explains the goal-relevant behaviour,
not a general tour of the repository.

WHAT SUFFICIENT LOOKS LIKE. You are done when you can explain, from code you
actually read: how the goal-relevant behaviour works, which components carry it
and why each matters for this goal, how those components connect, where the
behaviour is entered, and which concepts someone must already hold to follow it.
Stop when you have that — do not keep exploring because budget remains. If
something important stays unresolved, record it as an open question with why it
matters; an honest gap is more useful to the teacher than a padded dossier.

Avoid both failure modes: surveying the whole repository (breadth is not your
job), and stopping at the first plausible flow without checking it is the real
one (follow at least the connections that would change the teaching order).

Depth should follow the goal. Understanding a component means its internals,
contracts and callers; understanding a flow means every hop verified in order;
preparing to change code means the seams, contracts and tests around the change;
debugging means the failing path traced precisely. Populate the dossier fields
that serve the goal and leave the rest short — an empty section is fine when the
goal does not need it.

If a repository survey is provided below, treat it as a map drawn by someone
else: use it to decide where to look first, never as evidence. Every claim in
your dossier must be backed by code you read in THIS investigation, and every
file+symbol you cite must be verified — `propose_anchor` before you rely on a
citation. A symbol imported into a file is not defined there; that mistake is
the most common rejection.

Use the deterministic structure to decide where to read; use the source to
understand what it means. `symbols` outlines a file for a fraction of the cost
of reading it; `neighbors` follows real import/definition edges; `search_code`
finds where a name is used across the repository; then read the smallest range
that answers your current question. Read widely when the question genuinely
needs it — waste is re-reading what you already have, not reading what you need."""


def survey_context(survey_payload: dict, max_chars: int = 6000) -> str:
    """Render a Layer B survey as seed context for Layer C.

    Deliberately labelled a MAP: the investigator may steer by it, but nothing
    from it may be promoted into the dossier without repository evidence. Only
    the stable-by-measurement breadth fields are included (Stage 2: subsystem
    responsibilities 100% cross-run overlap; flows/relationships 0–63% and
    therefore left out — unstable context would steer differently every run).
    """
    if not survey_payload:
        return ""
    lines = [
        "REPOSITORY SURVEY (a prior goal-agnostic map — context, NOT evidence;",
        "verify anything you take from it before citing it):",
        "",
        f"Architecture: {survey_payload.get('architecture', '')}",
        "",
        "Subsystems and responsibilities:",
    ]
    for entry in survey_payload.get("subsystems") or []:
        lines.append(f"  {entry.get('name')}: {entry.get('responsibility')}")
    skipped = survey_payload.get("skipped") or []
    if skipped:
        lines.append("Not runtime code (per the survey):")
        for entry in skipped:
            lines.append(f"  {entry.get('name')}: {entry.get('reason')}")
    entry_points = survey_payload.get("entry_points") or []
    if entry_points:
        lines.append("Entry points the survey identified:")
        for entry in entry_points:
            lines.append(
                f"  {entry.get('file')}:{entry.get('symbol')} — {entry.get('what_it_starts')}"
            )
    needs = survey_payload.get("needs_investigation") or []
    if needs:
        lines.append("Areas the survey flagged as needing deeper investigation:")
        for entry in needs:
            lines.append(f"  {entry.get('area')}: {entry.get('open_question')}")
    testing = survey_payload.get("testing_posture")
    if testing:
        lines.append(f"Testing posture: {testing}")
    text = "\n".join(lines)
    return text[:max_chars]


# ── goal-typed exit criteria (§5.5, enforced by code) ─────────────────────────
#
# What must be true before the investigation may stop, by goal type. These are
# floors, not targets — the model is told to stop at sufficiency, and these
# catch the premature-stop failure mode ("first plausible flow") mechanically.
# Deliberately modest: a floor set too high forces padding, which is the other
# failure mode.


@dataclass(frozen=True)
class ExitCriteria:
    min_components: int = 3
    min_entry_points: int = 1
    min_flows: int = 1
    min_flow_steps: int = 3      # the longest flow must cross at least this many steps
    min_flow_files: int = 2      # ...spanning at least this many distinct files
    min_relationships: int = 2
    min_contracts: int = 0
    min_prerequisites: int = 1


BASE_CRITERIA = ExitCriteria()

CRITERIA_BY_GOAL_TYPE: dict[str, ExitCriteria] = {
    # A component: internals + contract + who uses it.
    "understand_component": ExitCriteria(min_components=4, min_contracts=1),
    # A system/flow goal: the flow is the deliverable — demand a real trace.
    "understand_system": ExitCriteria(min_flows=1, min_flow_steps=4, min_flow_files=3),
    "understand_architecture": ExitCriteria(
        min_components=4, min_flows=2, min_flow_files=3, min_relationships=3,
    ),
    # Changing code: the seams and contracts around the change are the point.
    "contribute_code": ExitCriteria(min_contracts=2, min_relationships=3),
    "improve_existing_system": ExitCriteria(min_contracts=1, min_relationships=3),
    # Debugging: precision over breadth — fewer components, a precise path.
    "debug_issue": ExitCriteria(min_components=2, min_flow_steps=4),
}


@dataclass(frozen=True)
class DossierCheck:
    """Everything our code can decide about a submitted dossier.

    The three failure families are kept apart because they call for opposite
    responses, and conflating them is what turned a transmission error into a
    lost run (see `gap_message`):

      structural       the payload did not arrive in the shape the schema
                       describes. The findings may be fine; the wire is broken.
                       Response: RE-EMIT. Gathering more evidence is wasted.
      unresolved       a citation does not exist in the repository.
                       Response: verify and correct that citation.
      unmet_criteria   the investigation genuinely has not established enough.
                       Response: explore further.
    """

    resolved_anchors: int = 0
    unresolved_anchors: list[str] = field(default_factory=list)
    unmet_criteria: list[str] = field(default_factory=list)
    vacuous: list[str] = field(default_factory=list)
    structural: list[str] = field(default_factory=list)
    # Claims the import graph contradicts: an internal definition cited where a
    # same-named sibling is what callers actually reach. Its own family because
    # the repair is neither "explore more" nor "re-emit" — it is one specific
    # relationship to follow and record.
    surface: list[str] = field(default_factory=list)

    @property
    def total_anchors(self) -> int:
        return self.resolved_anchors + len(self.unresolved_anchors)

    @property
    def grounding_accuracy(self) -> float:
        return self.resolved_anchors / self.total_anchors if self.total_anchors else 1.0

    @property
    def ok(self) -> bool:
        return not (
            self.unresolved_anchors or self.unmet_criteria
            or self.vacuous or self.structural or self.surface
        )

    def repair_message(self) -> str | None:
        """Serialisation-repair instructions, when that is what went wrong.

        Returns None when the shape was fine and the problem is real — a thin
        investigation cannot be repaired by re-emitting it.
        """
        if not self.structural:
            return None
        return (
            "Your submission did not arrive in the shape the schema describes, so "
            "it could not be read: " + "; ".join(self.structural[:6]) + ". This is "
            "a formatting fault, not a gap in what you found — your evidence is "
            "still valid. Do NOT gather more evidence and do NOT re-explore. "
            "Resubmit the SAME findings as a single JSON object, with every list "
            "field as a JSON array of objects (no XML-style tags, no arrays "
            "serialised into one string, no item fields at the top level). The "
            "rest of the contract is checked once the shape is readable."
        )

    def gap_message(self) -> str:
        # A structural fault suppresses the coverage complaints deliberately.
        # Those counts ("0 goal-relevant components established") are artifacts
        # of a payload we could not parse, not findings about the investigation;
        # reporting them tells the model to go exploring when what it needs to do
        # is re-send what it already has. Observed in production: the run spent
        # its remaining turns re-exploring and salvaged the same broken payload.
        repair = self.repair_message()
        if repair:
            return repair
        parts: list[str] = []
        if self.unmet_criteria:
            parts.append(
                "The investigation is not yet sufficient: "
                + "; ".join(self.unmet_criteria[:8])
                + ". Investigate further, or record what blocks you as an open question."
            )
        if self.unresolved_anchors:
            shown = "; ".join(self.unresolved_anchors[:10])
            parts.append(
                f"{len(self.unresolved_anchors)} citation(s) do not resolve against "
                f"the repository: {shown}. Verify with `symbols` or `propose_anchor`, "
                f"then correct or drop them."
            )
        if self.surface:
            parts.append(
                "The repository's import graph contradicts a claim you made: "
                + "; ".join(self.surface[:4]) + "."
            )
        if self.vacuous:
            parts.append(f"Empty entries: {', '.join(self.vacuous[:8])}.")
        return " ".join(parts) or "The dossier does not satisfy its contract."


def _entries(payload: dict, key: str) -> tuple[list[dict], list[str]]:
    """Dict entries of a list field, plus precise descriptions of malformed ones.

    Two failure modes, both observed in real runs, and both of which must become
    feedback the model can act on rather than an exception:

      - one entry is a bare string where the schema wants an object
      - the WHOLE field arrives as a string (the model serialised its array as
        markup inside a single value). Iterating that yields characters, which
        turned a structural error into "0 components established" — feedback
        describing the wrong problem entirely, so the model resubmitted the same
        broken shape until its budget ran out. Name the actual fault instead.
    """
    raw = payload.get(key)
    if raw is None:
        return [], []
    if not isinstance(raw, list):
        return [], [
            f"`{key}` arrived as {type(raw).__name__}, not a list of objects — "
            f"emit it as a JSON array of objects"
        ]
    good: list[dict] = []
    bad: list[str] = []
    for index, entry in enumerate(raw):
        if isinstance(entry, dict):
            good.append(entry)
        else:
            bad.append(f"{key}[{index}] is {type(entry).__name__!s}, not an object")
    return good, bad


# The dossier's list-valued fields, and the field names that may only ever
# appear *inside* one of their items. An item key surfacing at the top level of
# the payload means a nested object was flattened out of its array — the other
# half of the same transmission fault as a whole array arriving as a string, and
# the half that used to go unreported. Observed shape:
#
#   {"understanding": "...",                     <- fine
#    "components": "\n<component>\n<parameter…",  <- array serialised as markup
#    "symbol": "Depends",                         <- item keys stranded at the root
#    "role_in_goal": "...", "why_it_matters": "..."}
#
# Naming the stranded keys is what tells the model its nested objects collapsed,
# rather than leaving it to infer that from a count of zero.
LIST_FIELDS = (
    "components", "entry_points", "flows", "relationships",
    "contracts", "prerequisites", "evidence_refs", "open_questions",
)

_ROOT_KEYS = frozenset(INVESTIGATION_SPEC.input_schema["properties"])
_ITEM_ONLY_KEYS = frozenset({
    "file", "symbol", "role_in_goal", "why_it_matters", "how_it_enters",
    "name", "steps", "what_happens", "from_file", "from_symbol", "to_file",
    "to_symbol", "kind", "note", "contract", "concept", "why_needed",
    "path", "clarifies", "question",
}) - _ROOT_KEYS


# The observed signature of the fault, measured across four consecutive gate
# attempts: the value of a list field is not JSON at all but XML-style tool
# markup — `<component>`, `<parameter name="file">…`. Every occurrence looked
# the same, and the generic "emit it as a JSON array" wording drew twelve
# identical resubmissions in one run. Naming the markup names the mechanism.
_TOOL_MARKUP = ("<parameter", "</parameter", "<component", "<item", "<step")


def structural_faults(payload: dict) -> list[str]:
    """Ways the payload failed to arrive in the shape the schema describes.

    Distinct from "the investigation is thin": these are transmission faults,
    and the repair is to re-emit, never to explore further.
    """
    faults: list[str] = []
    for key in LIST_FIELDS:
        raw = payload.get(key)
        if isinstance(raw, str) and any(tag in raw for tag in _TOOL_MARKUP):
            faults.append(
                f"`{key}` arrived as XML-style tool markup inside a single string "
                f"value (it begins {raw.strip()[:40]!r}) — the tool input must be "
                f"JSON, so this field has to be a JSON array of objects"
            )
            continue
        faults.extend(_entries(payload, key)[1])
    stranded = sorted(set(payload) & _ITEM_ONLY_KEYS)
    if stranded:
        faults.append(
            "these item-level keys arrived at the top level of the dossier: "
            + ", ".join(f"`{k}`" for k in stranded)
            + " — each belongs inside an object within one of the list fields, so "
            "a nested object was flattened out of its array"
        )
    return faults


def cited_anchors(payload: dict) -> list[tuple[str, str, str]]:
    """Every (where, file, symbol) the dossier claims as code evidence."""
    cited: list[tuple[str, str, str]] = []
    for entry in _entries(payload, "components")[0]:
        cited.append(("component", entry.get("file"), entry.get("symbol")))
    for entry in _entries(payload, "entry_points")[0]:
        cited.append(("entry_point", entry.get("file"), entry.get("symbol")))
    for flow in _entries(payload, "flows")[0]:
        name = flow.get("name") or "flow"
        for step in flow.get("steps") or []:
            if not isinstance(step, dict):
                cited.append((f"flow:{name}", "", ""))   # malformed -> incomplete
                continue
            cited.append((f"flow:{name}", step.get("file"), step.get("symbol")))
    for entry in _entries(payload, "relationships")[0]:
        cited.append(("relationship_from", entry.get("from_file"), entry.get("from_symbol")))
        cited.append(("relationship_to", entry.get("to_file"), entry.get("to_symbol")))
    for entry in _entries(payload, "contracts")[0]:
        cited.append(("contract", entry.get("file"), entry.get("symbol")))
    for entry in _entries(payload, "prerequisites")[0]:
        # Anchors on prerequisites are optional; validate only when offered.
        if entry.get("file") or entry.get("symbol"):
            cited.append(("prerequisite", entry.get("file"), entry.get("symbol")))
    return [(w, str(f or ""), str(s or "")) for w, f, s in cited]


# Sections whose entries are claims about what matters, as opposed to steps in a
# trace. The public-surface check runs over these only: a flow may legitimately
# pass through an internal twin on its way somewhere, but "this is a component
# that matters" and "this is the public entry point" are claims about identity.
_CLAIM_SECTIONS = (
    ("components", "file", "symbol"),
    ("entry_points", "file", "symbol"),
    ("contracts", "file", "symbol"),
)


def public_surface_gaps(skeleton: Skeleton, payload: dict) -> list[str]:
    """Where the dossier cites an internal twin of a name users reach elsewhere.

    Python lets a package re-export one definition of a name while another
    definition of the SAME name lives beside it — a factory next to the class it
    builds, a wrapper next to its implementation. Citing the unexported twin and
    calling it the entry point is a claim the repository contradicts, and it is
    checkable: the import graph says which definition a caller reaches.

    Measured consequence of not checking: three consecutive runs produced a
    learning graph whose first node named an internal dataclass "the user-facing
    declaration", because the exported factory of the same name was never seen.

    Narrow by construction — it fires only when a same-named sibling IS exported
    and the cited one is NOT, so a repository with no such twin never sees it.
    """
    # Citing BOTH definitions is the right answer, not a second offence: it is
    # exactly "establish how the public name and the internal one relate". So
    # the check is satisfied as soon as the exported twin appears anywhere in the
    # dossier, in any section.
    established: set[tuple[str, str]] = set()
    for _, file, symbol in cited_anchors(payload):
        if not (file and symbol):
            continue
        resolution = anchors.resolve(skeleton, file, symbol=symbol)
        if resolution.ok:
            established.add((
                resolution.anchor.file,
                (resolution.anchor.symbol or symbol).rsplit(".", 1)[-1],
            ))

    gaps: list[str] = []
    seen: set[tuple[str, str]] = set()
    for section, file_key, symbol_key in _CLAIM_SECTIONS:
        for entry in _entries(payload, section)[0]:
            file = str(entry.get(file_key) or "")
            symbol = str(entry.get(symbol_key) or "")
            if not file or not symbol or (file, symbol) in seen:
                continue
            seen.add((file, symbol))
            resolution = anchors.resolve(skeleton, file, symbol=symbol)
            if not resolution.ok:
                continue          # unresolvable anchors are a separate failure
            cited = resolution.anchor
            bare = (cited.symbol or symbol).rsplit(".", 1)[-1]
            if skeleton.exports_of(bare, file=cited.file):
                continue          # the cited definition IS the one users reach
            elsewhere = [
                export for export in skeleton.exports_of(bare)
                if export.defined_in != cited.file
                and (export.defined_in, bare) not in established
            ]
            if not elsewhere:
                continue          # no twin, or the twin is already established
            export = elsewhere[0]
            claimed_public = (
                section == "entry_points"
                and str(entry.get("perspective") or "") == "public_api"
            )
            gaps.append(
                f"{section}: you cite {cited.file}:{bare}"
                + (" as a public_api entry point" if claimed_public else "")
                + f", but callers reach `{bare}` as `{export.import_path}`, which "
                f"resolves to {export.defined_in} — a different definition of the "
                f"same name. Establish which one the user actually reaches and how "
                f"the two relate (`neighbors` with `exported_by`), then cite "
                f"accordingly"
            )
    return gaps


def validate_dossier(
    skeleton: Skeleton, goal: dict, payload: dict
) -> DossierCheck:
    """Deterministic checks: anchors resolve, exit criteria met, nothing vacuous."""
    unresolved: list[str] = []
    structural = structural_faults(payload)
    resolved = 0
    for where, file, symbol in cited_anchors(payload):
        if not file or not symbol:
            unresolved.append(f"{where}: incomplete citation {file or '?'}:{symbol or '?'}")
            continue
        resolution = anchors.resolve(skeleton, file, symbol=symbol)
        if resolution.ok:
            resolved += 1
        else:
            unresolved.append(f"{where}: {file}:{symbol} ({resolution.reason})")

    criteria = CRITERIA_BY_GOAL_TYPE.get(str(goal.get("goal_type")), BASE_CRITERIA)
    unmet: list[str] = []

    components = _entries(payload, "components")[0]
    if len(components) < criteria.min_components:
        unmet.append(
            f"{len(components)} goal-relevant component(s) established; at least "
            f"{criteria.min_components} are needed to explain this kind of goal"
        )
    if len(payload.get("entry_points") or []) < criteria.min_entry_points:
        unmet.append("no verified entry point into the goal-relevant behaviour")

    flows = _entries(payload, "flows")[0]
    if len(flows) < criteria.min_flows:
        unmet.append(f"{len(flows)} flow(s) traced; at least {criteria.min_flows} needed")
    else:
        def _steps(flow: dict) -> list[dict]:
            return [s for s in (flow.get("steps") or []) if isinstance(s, dict)]

        best_steps = max((len(_steps(f)) for f in flows), default=0)
        best_files = max(
            (len({str(s.get("file")) for s in _steps(f)}) for f in flows),
            default=0,
        )
        if best_steps < criteria.min_flow_steps:
            unmet.append(
                f"the longest flow has {best_steps} step(s); a real trace of this "
                f"goal needs at least {criteria.min_flow_steps}"
            )
        if best_files < criteria.min_flow_files:
            unmet.append(
                f"no flow crosses more than {best_files} file(s); this goal's "
                f"behaviour spans at least {criteria.min_flow_files}"
            )
    if len(payload.get("relationships") or []) < criteria.min_relationships:
        unmet.append(
            f"{len(payload.get('relationships') or [])} confirmed relationship(s); "
            f"at least {criteria.min_relationships} needed"
        )
    if len(payload.get("contracts") or []) < criteria.min_contracts:
        unmet.append(
            f"{len(payload.get('contracts') or [])} contract(s)/abstraction(s) "
            f"described; at least {criteria.min_contracts} needed for this goal"
        )
    if len(payload.get("prerequisites") or []) < criteria.min_prerequisites:
        unmet.append("no prerequisite concepts identified")
    if not str(payload.get("understanding") or "").strip():
        unmet.append("`understanding` is empty")

    vacuous = [
        f"component {entry.get('symbol')}"
        for entry in components
        if not str(entry.get("why_it_matters") or "").strip()
        or not str(entry.get("role_in_goal") or "").strip()
    ]

    return DossierCheck(
        resolved_anchors=resolved,
        unresolved_anchors=unresolved,
        unmet_criteria=unmet,
        vacuous=vacuous,
        structural=structural,
        # Only meaningful once the payload is readable — a mangled dossier has
        # no claims to contradict, and piling this on would bury the real fault.
        surface=[] if structural else public_surface_gaps(skeleton, payload),
    )


# Repeating a message that has already failed to work is not feedback. Measured:
# one run submitted the identical broken shape twelve times against the identical
# rejection, spending most of its budget on the exchange. On a repeat the advice
# changes to the only lever left — make the payload small enough to emit — and it
# trims the two fields no exit criterion depends on, so shrinking cannot push the
# dossier under its own contract.
_ESCALATION = (
    " This is attempt {n} at the same shape, so repeating the instruction will "
    "not help: emit a SMALLER payload this time. Keep every component, flow and "
    "relationship, but cut each description to one short sentence and send "
    "`context` and `open_questions` empty. A short dossier that arrives beats a "
    "complete one that cannot be read."
)


class DossierValidator:
    """`explore(validate=...)` hook; keeps every attempt for measurement."""

    def __init__(self, skeleton: Skeleton, goal: dict, enforce: bool = True):
        self.skeleton = skeleton
        self.goal = goal
        self.enforce = enforce
        self.attempts: list[DossierCheck] = []
        self.payloads: list[dict] = []

    def _structural_streak(self) -> int:
        """How many submissions in a row have failed on shape, this one included."""
        streak = 0
        for check in reversed(self.attempts):
            if not check.structural:
                break
            streak += 1
        return streak

    def __call__(self, payload: dict) -> str | None:
        check = validate_dossier(self.skeleton, self.goal, payload)
        self.attempts.append(check)
        self.payloads.append(payload)
        if check.ok or not self.enforce:
            return None
        message = check.gap_message()
        streak = self._structural_streak()
        if check.structural and streak > 1:
            message += _ESCALATION.format(n=streak)
        return message

    def repair_prompt(self, payload: dict) -> str | None:
        """`explore`'s opt-in hook: is this payload repairable without exploring?

        Only a serialisation fault qualifies. A dossier that is genuinely thin
        cannot be fixed by re-emitting it, and asking for that would be the
        "pretend the gap is not there" behaviour §5.4 exists to prevent.
        """
        return validate_dossier(self.skeleton, self.goal, payload).repair_message()

    @property
    def first(self) -> DossierCheck | None:
        return self.attempts[0] if self.attempts else None

    @property
    def last(self) -> DossierCheck | None:
        return self.attempts[-1] if self.attempts else None


# ── running one investigation ─────────────────────────────────────────────────


@dataclass
class InvestigationRun:
    exploration: Exploration
    validator: DossierValidator
    skeleton: Skeleton
    goal: dict
    used_survey: bool

    @property
    def dossier(self) -> dict | None:
        if self.exploration.output is not None:
            return self.exploration.output
        return self.validator.payloads[-1] if self.validator.payloads else None

    @property
    def check(self) -> DossierCheck | None:
        return self.validator.last

    @property
    def produced(self) -> bool:
        return self.exploration.output is not None

    @property
    def accepted(self) -> bool:
        return self.exploration.contract_met is True


def _task(goal: dict) -> str:
    """The per-run request. Volatile by nature, so it stays out of the cached seed."""
    parts = [f"The user's goal: {goal.get('primary_goal', '')}"]
    if goal.get("focus_area"):
        parts.append(f"Focus area: {goal['focus_area']}")
    if goal.get("goal_type"):
        parts.append(f"Goal type: {goal['goal_type']}")
    if goal.get("code_depth"):
        parts.append(f"How deep the user asked to go: {goal['code_depth']}")
    parts.append(
        "Investigate the repository until you can explain the goal-relevant "
        "behaviour from verified code, then submit the dossier."
    )
    return "\n".join(parts)


def run_investigation(
    *,
    client,
    repo_path: str,
    goal: dict,
    survey_payload: dict | None = None,
    skeleton: Skeleton | None = None,
    budget: Budget | None = None,
    tool_guide: str = explore.TOOL_GUIDE_STRUCTURAL,
    model: str = explore.MODEL,
    max_tokens: int = INVESTIGATION_MAX_TOKENS,
    on_call=None,
) -> InvestigationRun:
    """Run one goal investigation through the Stage-1 harness.

    ``survey_payload`` is the A/B lever: with it, the seed carries the Layer B
    map (stable breadth only); without it, the investigator starts from the
    skeleton alone. Everything else is identical between the two arms.
    """
    sk = skeleton if skeleton is not None else build_skeleton(repo_path)
    instructions = INVESTIGATION_INSTRUCTIONS
    if survey_payload:
        instructions = instructions + "\n\n" + survey_context(survey_payload)
    validator = DossierValidator(sk, goal)
    exploration = explore.explore(
        client=client,
        repo_path=repo_path,
        instructions=instructions,
        task=_task(goal),
        skeleton=sk,
        report=INVESTIGATION_SPEC,
        budget=budget or Budget(max_turns=20, max_tool_calls=120,
                                max_result_chars=500_000, max_seconds=720.0),
        model=model,
        max_tokens=max_tokens,
        on_call=on_call,
        tool_guide=tool_guide,
        validate=validator,
    )
    return InvestigationRun(
        exploration=exploration, validator=validator, skeleton=sk,
        goal=goal, used_survey=bool(survey_payload),
    )


# ── the chunk-shape shim (§12 Stage 3, 3b) ────────────────────────────────────
#
# The dossier renders itself in the existing chunk-dict shape so the CURRENT
# Mentor can consume it with zero prompt changes — the smallest clean adapter
# the A/B needs. Content is read from the repository at the resolved anchor, so
# what the Mentor sees is real source, exactly as if retrieval had returned it.


def dossier_as_chunks(
    skeleton: Skeleton, payload: dict, max_chunks: int = 24
) -> list[dict]:
    """Anchored dossier entries as retrieval-shaped chunk dicts.

    Deduplicated by resolved range, ordered components-first (they carry the
    goal reasoning), then entry points, then flow steps and contracts. Entries
    whose anchor does not resolve are dropped — the shim must not launder an
    unverified claim into Mentor evidence.
    """
    seen: set[tuple[str, int, int]] = set()
    chunks: list[dict] = []

    def add(file: str, symbol: str, kind_hint: str) -> None:
        if len(chunks) >= max_chunks or not file or not symbol:
            return
        resolution = anchors.resolve(skeleton, str(file), symbol=str(symbol))
        if not resolution.ok:
            return
        a = resolution.anchor
        key = a.as_tuple()
        if key in seen:
            return
        seen.add(key)
        content = skeleton.read_lines(a.file, a.line_start, a.line_end) or ""
        chunks.append({
            "file": a.file,
            "start_line": a.line_start,
            "end_line": a.line_end,
            "type": kind_hint,
            "name": a.symbol or str(symbol),
            "role": "source",
            "content": content,
        })

    for entry in _entries(payload, "components")[0]:
        add(entry.get("file"), entry.get("symbol"), "function")
    for entry in _entries(payload, "entry_points")[0]:
        add(entry.get("file"), entry.get("symbol"), "function")
    for flow in _entries(payload, "flows")[0]:
        for step in flow.get("steps") or []:
            if isinstance(step, dict):
                add(step.get("file"), step.get("symbol"), "function")
    for entry in _entries(payload, "contracts")[0]:
        add(entry.get("file"), entry.get("symbol"), "class")
    for entry in _entries(payload, "prerequisites")[0]:
        if entry.get("file") and entry.get("symbol"):
            add(entry.get("file"), entry.get("symbol"), "function")
    return chunks


def module_map_from_dossier(payload: dict) -> dict:
    """A module_map-shaped view of the dossier, for the Mentor's prompt.

    The Mentor requires a module map; at Stage 3 the honest one is derived from
    what the investigation established — same treatment in both A/B arms, so the
    survey's influence flows only through investigation quality.
    """
    modules: dict[str, dict] = {}
    for entry in _entries(payload, "components")[0]:
        file = str(entry.get("file") or "")
        name = file.rsplit("/", 1)[-1].removesuffix(".py") or file
        module = modules.setdefault(name, {
            "purpose": "", "key_files": [], "exports": [], "dependencies": [],
        })
        if file and file not in module["key_files"]:
            module["key_files"].append(file)
        symbol = str(entry.get("symbol") or "")
        if symbol and symbol not in module["exports"]:
            module["exports"].append(symbol)
        if not module["purpose"]:
            module["purpose"] = str(entry.get("role_in_goal") or "")
    for entry in _entries(payload, "relationships")[0]:
        from_name = str(entry.get("from_file") or "").rsplit("/", 1)[-1].removesuffix(".py")
        to_name = str(entry.get("to_file") or "").rsplit("/", 1)[-1].removesuffix(".py")
        if from_name in modules and to_name and to_name != from_name:
            deps = modules[from_name]["dependencies"]
            if to_name not in deps:
                deps.append(to_name)
    return modules
