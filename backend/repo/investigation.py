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
            # ── the change boundary (contribution-journey.md A6.2) ────────────
            #
            # For a goal that is MAKING a specific change rather than reading the
            # code: where that change belongs, and what it must not disturb.
            #
            # DELIBERATELY OUT OF `required`. It is offered to every goal type and
            # DEMANDED only by `contribute_code`'s exit criteria, which is what
            # lets a new section arrive without bricking the other six goal types
            # — a required key they have no reason to fill would fail every one of
            # their dossiers on a contract that is not about them.
            "change_boundary": {
                "type": "object",
                "description": (
                    "Only for a goal that makes a specific change. Where the "
                    "change belongs and what it must not disturb. Every file and "
                    "symbol here is checked against the repository exactly like "
                    "every other citation in this dossier."
                ),
                "properties": {
                    "target": {
                        "type": "array",
                        "description": (
                            "Where the change belongs — the symbol it would be "
                            "added to or altered, verified by reading it."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                **_ANCHOR,
                                "why_here": {
                                    "type": "string",
                                    "description": "Why this is the right place for it.",
                                },
                            },
                            "required": ["file", "symbol", "why_here"],
                        },
                    },
                    "must_not_change": {
                        "type": "array",
                        "description": (
                            "Neighbouring code that looks related and is not, or "
                            "that would be unsafe to alter while making this change."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                **_ANCHOR,
                                "why_not": {"type": "string"},
                            },
                            "required": ["file", "symbol", "why_not"],
                        },
                    },
                    "conventions": {
                        "type": "array",
                        "description": (
                            "How this repository writes code of this kind, each "
                            "with a file it can be seen in."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "convention": {"type": "string"},
                                "evidence_file": {"type": "string"},
                            },
                            "required": ["convention", "evidence_file"],
                        },
                    },
                    "existing_tests": {
                        "type": "array",
                        "description": (
                            "The tests that already guard this behaviour. Read "
                            "them: how this repository tests this kind of code is "
                            "part of what the developer needs."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                **_ANCHOR,
                                "what_it_guards": {"type": "string"},
                            },
                            "required": ["file", "symbol", "what_it_guards"],
                        },
                    },
                    "edge_cases": {
                        "type": "array",
                        "description": (
                            "What the change has to respect. Give `file` and "
                            "`symbol` for the code the case lives in wherever you "
                            "can — an anchored edge case is worth five you "
                            "reasoned your way to."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "case": {"type": "string"},
                                "why_it_bites": {"type": "string"},
                                "file": {"type": "string"},
                                "symbol": {"type": "string"},
                            },
                            "required": ["case", "why_it_bites"],
                        },
                    },
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
    # ...spanning at least this many distinct files, or `None` for a goal type
    # where the number is NOT EVIDENCE OF ANYTHING.
    #
    # THE DISTINCTION IS DELIBERATE AND IS NOT A LOW FLOOR. A floor of 1 would
    # say "one file is barely enough"; `None` says "how many files the behaviour
    # touches tells us nothing about whether this investigation is finished".
    # For a contribution correctly scoped to one production file the second is
    # the true statement, and setting 1 instead would leave an arbitrary number
    # in place that happens to pass — which is the thing this project keeps
    # having to remove.
    #
    # Every other criterion here is a floor because more genuinely is better
    # evidence for it. This one is a SHAPE claim: it asserts that the goal's
    # behaviour spans files, and that assertion is simply false for some goals.
    min_flow_files: int | None = 2
    min_relationships: int = 2
    min_contracts: int = 0
    min_prerequisites: int = 1
    # Entry points whose `perspective` is `public_api` — the name a developer
    # USING this code imports and calls, as opposed to whatever invokes the
    # behaviour at runtime.
    #
    # The schema has carried this distinction since Phase A Stage 4b, but no
    # criteria demanded it, so an investigation could satisfy every floor with
    # runtime entry points alone. That is the right answer for most goals and the
    # wrong one for a caller who has to know what to type.
    min_public_api_entry_points: int = 0

    # ── the change boundary, for a goal that MAKES a change ───────────────────
    #
    # Zero by default, so the six goal types that are not making a change are
    # untouched by the section's existence. Only `contribute_code` sets them, and
    # what they demand is the three things a contributor cannot start without:
    # somewhere to write, a test to imitate, and a case the change has to survive.
    min_boundary_targets: int = 0
    min_boundary_tests: int = 0
    # Counted over ANCHORED edge cases only — see `anchored_edge_cases`.
    min_boundary_edge_cases: int = 0
    # Must the boundary be USABLE — not merely present, and not merely large?
    #
    # This is the structural half, and it exists because the counts above are
    # not it. `Locate`, the implementation plan, the scope check and the review
    # all read the boundary, so for a contribution an investigation that did not
    # establish one has not established the thing the rest of the product is
    # built on — however many components and flows it found. See
    # `boundary_usable` for what the word means and why it is deliberately small.
    requires_change_boundary: bool = False


BASE_CRITERIA = ExitCriteria()

CRITERIA_BY_GOAL_TYPE: dict[str, ExitCriteria] = {
    # Using a library: the caller-facing surface is the deliverable. Demand a
    # verified `public_api` entry point (what they import), two contracts (what
    # they must honour and may rely on), and keep the base flow floor so the
    # journey can explain what happens behind the call — without that it degrades
    # into a usage tutorial that cannot say why anything behaves as it does.
    "use_library": ExitCriteria(
        min_public_api_entry_points=1,
        min_entry_points=2,
        min_contracts=2,
    ),
    # A component: internals + contract + who uses it.
    "understand_component": ExitCriteria(min_components=4, min_contracts=1),
    # A system/flow goal: the flow is the deliverable — demand a real trace.
    "understand_system": ExitCriteria(min_flows=1, min_flow_steps=4, min_flow_files=3),
    "understand_architecture": ExitCriteria(
        min_components=4, min_flows=2, min_flow_files=3, min_relationships=3,
    ),
    # Changing code: the seams and contracts around the change are the point.
    #
    # The base floors are UNCHANGED and deliberately so. A contribution journey
    # is meant to come out shorter than an architecture one because the
    # curriculum's REQUIRED SET is smaller, never because the investigation was
    # allowed to establish less (contribution-journey.md A6.3). Lowering a floor
    # here would be exactly the artificial cap this design refuses.
    #
    # `min_flow_files=None` is an EXEMPTION, not a reduction. A contribution may
    # be correctly scoped to a single production file, and how many files its
    # behaviour spans is not evidence about whether the investigation is
    # finished. What IS evidence for this goal type is the boundary: where the
    # change belongs, the contract in force, the cases it must survive, and the
    # tests that already cover it — and those are the criteria below.
    "contribute_code": ExitCriteria(
        min_contracts=2,
        min_relationships=3,
        min_flow_files=None,
        min_boundary_targets=1,
        min_boundary_tests=1,
        min_boundary_edge_cases=2,
        requires_change_boundary=True,
    ),
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
    # Citations of THE SYMBOL THE CONTRIBUTION IS BEING ASKED TO CREATE.
    #
    # A fifth family, and the one that cost the most measured turns. It is a
    # subset of `unresolved` by construction — the symbol is not there, because
    # it has not been written yet — but the repair is the opposite of the
    # generic one. "Verify with `symbols`, then correct or drop it" sends the
    # investigator to look for something that cannot be found; twice in three
    # runs it looked, failed, and re-emitted the same anchor until the budget
    # was gone. What it actually needs to hear is that the citation is not a
    # mistake about the repository at all, and where the intent belongs instead.
    future_symbols: list[str] = field(default_factory=list)

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
        # THE REPAIR LEADS, AND NO LONGER STANDS ALONE.
        #
        # It used to `return` here, which was right about the danger and too
        # broad about the remedy: a report mangled in one field taught the
        # investigator nothing about the rest of its contract, so a submission —
        # roughly a third of a run's feedback — bought only "re-emit". Measured
        # across seven runs, a first submission lost this way predicted refusal
        # in six of six.
        #
        # `validate_dossier` has already dropped the complaints that were mere
        # artifacts of the corruption, so what remains is real. It follows the
        # repair rather than replacing it, and is framed so re-emission stays the
        # first move: the danger the early return guarded against was the model
        # going exploring instead of re-sending what it already had.
        repair = self.repair_message()
        parts: list[str] = []
        if repair:
            parts.append(repair)
            still = [
                m for m in self.unmet_criteria
                # An empty `understanding` alongside a mangled payload is not a
                # separate finding; everything else is.
                if "`understanding` is empty" not in m
            ]
            if still:
                parts.append(
                    "Once it is readable, the contract still needs: "
                    + "; ".join(still[:8])
                    + ". You may already have the evidence for these — include "
                    "them in the SAME resubmission rather than exploring first."
                )
            return " ".join(parts)
        if self.unmet_criteria:
            parts.append(
                "The investigation is not yet sufficient: "
                + "; ".join(self.unmet_criteria[:8])
                + ". Investigate further, or record what blocks you as an open question."
            )
        # THE FUTURE SYMBOL COMES FIRST, AND SUPPRESSES THE GENERIC ADVICE FOR IT.
        #
        # "Verify with `symbols`, then correct or drop them" sends the
        # investigator to look for a method the developer has not written yet.
        # Measured across three runs: twice it looked, failed, and re-emitted the
        # same anchor until the turn budget was gone. The citation is not a
        # mistake about the repository — it is the right idea in the wrong field,
        # and the repair is to move it, not to check it.
        if self.future_symbols:
            parts.append(
                f"{len(self.future_symbols)} citation(s) name the symbol this "
                f"contribution is going to CREATE: "
                + "; ".join(self.future_symbols[:6])
                + ". It does not exist yet, so no anchor on it can ever resolve, "
                "and looking for it will not help. Do not cite it in `flows`, "
                "`relationships`, `components`, `entry_points` or `contracts` — "
                "those describe code that runs TODAY. Put what you wanted to say "
                "about it in prose instead: the intended behaviour belongs in "
                "`understanding`, and where it goes belongs in "
                "`change_boundary.target` (with `why_here`) anchored on the "
                "class or module it will be ADDED TO, which does exist."
            )
        other = [
            entry for entry in self.unresolved_anchors
            if not any(future in entry for future in self.future_symbols)
        ]
        if other:
            shown = "; ".join(other[:10])
            parts.append(
                f"{len(other)} citation(s) do not resolve against "
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


# ── the change boundary ───────────────────────────────────────────────────────
#
# Read through accessors rather than by indexing, for the same reason `_entries`
# exists: a model that serialises `target` as a string must produce FEEDBACK, not
# a TypeError halfway through validation. Every accessor here degrades to empty.

BOUNDARY_LISTS = (
    "target", "must_not_change", "conventions", "existing_tests", "edge_cases",
)


def boundary(payload: dict) -> dict:
    """The change boundary, or `{}` when there is none (or it arrived malformed)."""
    raw = payload.get("change_boundary")
    return raw if isinstance(raw, dict) else {}


def boundary_entries(payload: dict, key: str) -> list[dict]:
    """Dict entries of one change-boundary list; malformed items are dropped."""
    raw = boundary(payload).get(key)
    if not isinstance(raw, list):
        return []
    return [entry for entry in raw if isinstance(entry, dict)]


def boundary_targets(payload: dict) -> list[dict]:
    """Target entries carrying both a file and a symbol."""
    return [
        entry for entry in boundary_entries(payload, "target")
        if str(entry.get("file") or "").strip()
        and str(entry.get("symbol") or "").strip()
    ]


def boundary_usable(skeleton: Skeleton, payload: dict) -> bool:
    """Is there enough here for the contribution stage to stand on?

    **Deliberately the smallest thing that is true**, and stated as a question
    about USE rather than about completeness: at least one `target` naming a file
    and a symbol that RESOLVES against the repository.

    Why that and nothing more. `Locate` opens the target's file at its anchor,
    the implementation plan is written against it, and the scope check compares
    the learner's paths to it. One resolvable target is what all three need. The
    other four sections make a boundary *better* and are held to their own
    counted criteria; requiring them here would be demanding a full schema to
    prove the section is not empty, which is the opposite of a usability test.

    RESOLUTION IS THE LOAD-BEARING WORD. A target naming a file that is not there
    would send the learner to write code in a place that does not exist — and it
    is exactly the failure the anchoring rule in the brief exists to prevent, so
    it must be caught here rather than trusted to prose.
    """
    for entry in boundary_targets(payload):
        resolution = anchors.resolve(
            skeleton, str(entry["file"]), symbol=str(entry["symbol"])
        )
        if resolution.ok:
            return True
    return False


def is_future_symbol(skeleton: Skeleton, goal: dict, symbol: str) -> bool:
    """Is this the symbol the contribution is going to CREATE?

    Three conditions, and the third is what makes it safe:

      1. the goal is a contribution — nothing else is adding a symbol;
      2. the contribution task NAMES this symbol, since the task is the only
         place a symbol that does not exist yet is written down;
      3. the bare name is defined NOWHERE in the repository.

    (3) was learned the hard way. A task reads "add a `get_all` method to `Jar`",
    so it names the container as well as the addition — and a citation of
    `__init__.py:Jar` fails to resolve for an entirely different reason (imported
    there, not defined there, which is the most common citation mistake there
    is). Conditions 1 and 2 alone called that a future symbol and gave it advice
    about prose, when what it needed was "you cited the wrong file".

    A symbol defined somewhere is a misplaced or misspelled citation and gets the
    generic repair. A symbol defined nowhere, that the task names, is the one
    being written.
    """
    if goal.get("goal_type") != "contribute_code":
        return False
    bare = str(symbol or "").rsplit(".", 1)[-1].strip()
    if not bare or bare not in str(goal.get("contribution_context") or ""):
        return False
    return not skeleton.find_symbol(bare)


def anchored_edge_cases(payload: dict) -> list[dict]:
    """Edge cases that point at code the investigation actually read.

    Unanchored edge cases are PERMITTED and deliberately do NOT count toward
    `min_boundary_edge_cases`. That is what turns the brief's "an anchored edge
    case is worth five you reasoned your way to" into a rule the code enforces
    rather than a sentence the model may drift from — a dossier can still record
    a case it could not locate, it just cannot satisfy its contract with one.
    """
    return [
        entry for entry in boundary_entries(payload, "edge_cases")
        if str(entry.get("file") or "").strip()
        and str(entry.get("symbol") or "").strip()
    ]


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


# The observed signature of the fault: the value of a list field is not JSON at
# all but XML-style tool markup — `<component>`, `<parameter name="file">…`.
# Naming the markup names the mechanism, which the generic "emit it as a JSON
# array" wording did not: that drew twelve identical resubmissions in one run.
#
# The RECOVERABLE half of this shape is undone upstream, at the tool-call
# boundary (`explore.repair_tool_input`), so anything still matching here is a
# form no repair can verify — a whole tool call, or items serialised as XML.
_TOOL_MARKUP = ("<parameter", "</parameter", "<component", "<item", "<step")


def corrupted_fields(payload: dict) -> set[str]:
    """List fields that did not arrive readable, by name.

    THE POINT OF NAMING THEM is that a structural fault used to cost the whole
    submission: `gap_message` suppressed every other diagnostic, so a report
    mangled in ONE field taught the investigator nothing about the rest of its
    contract. With the corrupted fields known, the criteria that are mere
    artifacts of the corruption can be skipped while every other shortfall is
    still reported — which is the difference between losing a submission and
    losing a field.
    """
    corrupted: set[str] = set()
    for key in LIST_FIELDS:
        raw = payload.get(key)
        if isinstance(raw, str):
            corrupted.add(key)
        elif not isinstance(raw, (list, type(None))):
            corrupted.add(key)
    return corrupted


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
    # THE SAME FAULT, ONE LEVEL UP, and it went undetected because this function
    # predates `change_boundary`.
    #
    # Observed: a run submitted `existing_tests`, `edge_cases`, `must_not_change`
    # and `conventions` as TOP-LEVEL keys with `change_boundary` empty. The work
    # was done — four tests, six edge cases — and the investigator was told "0
    # entries" for every one of them, which reads as "you did not find any" and
    # sends it back to look for what it had already written down.
    #
    # Reported rather than silently re-nested, like the stranded item keys above:
    # a re-emission is one turn, and a repair that guesses at intent is how a
    # mis-parse becomes evidence.
    unnested = sorted(set(payload) & set(BOUNDARY_LISTS))
    if unnested:
        faults.append(
            "these change-boundary sections arrived at the top level of the "
            "dossier: " + ", ".join(f"`{k}`" for k in unnested)
            + " — they belong INSIDE the `change_boundary` object, as "
            "`change_boundary.target`, `change_boundary.existing_tests` and so "
            "on. Nest them and resubmit; the findings themselves are fine"
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
    # The change boundary is held to the SAME grounding as everything else. A
    # target file that does not resolve is the one error that would send the
    # learner to write code in a place that is not there, so it must fail the
    # dossier rather than reach the product as prose (D2, D3).
    for section in ("target", "must_not_change", "existing_tests"):
        for entry in boundary_entries(payload, section):
            cited.append((f"boundary:{section}", entry.get("file"), entry.get("symbol")))
    for entry in anchored_edge_cases(payload):
        cited.append(("boundary:edge_case", entry.get("file"), entry.get("symbol")))
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
            qualified = cited.symbol or symbol
            # A METHOD IS NOT A TWIN OF A MODULE-LEVEL FUNCTION.
            #
            # The check compares BARE names, which is right for two module-level
            # definitions of one name — the fastapi-di case it was written for.
            # It is wrong for `RequestsCookieJar.get`: stripping the qualifier
            # leaves `get`, `exports_of("get")` finds `requests.get` in
            # `api.py`, and the investigator is told its cookie-jar accessor
            # "is really" the top-level HTTP helper. Measured: it fired on every
            # contribution run against `psf/requests` and cost turns each time.
            #
            # `A.b` and `b` are different names. Only an unqualified citation is
            # asking the question this check answers.
            if "." in qualified:
                continue
            bare = qualified
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
    future: list[str] = []
    structural = structural_faults(payload)
    resolved = 0
    for where, file, symbol in cited_anchors(payload):
        if not file or not symbol:
            unresolved.append(f"{where}: incomplete citation {file or '?'}:{symbol or '?'}")
            continue
        resolution = anchors.resolve(skeleton, file, symbol=symbol)
        if resolution.ok:
            resolved += 1
            continue
        unresolved.append(f"{where}: {file}:{symbol} ({resolution.reason})")
        # Still counted as unresolved — it genuinely does not resolve, and
        # grounding accuracy must not be flattered by it. What changes is the
        # ADVICE, which is the thing that was costing turns.
        if (
            resolution.reason == "unknown_symbol"
            and is_future_symbol(skeleton, goal, symbol)
        ):
            entry = f"{file}:{symbol}"
            if entry not in future:
                future.append(entry)

    criteria = CRITERIA_BY_GOAL_TYPE.get(str(goal.get("goal_type")), BASE_CRITERIA)
    unmet: list[str] = []

    # WHICH COMPLAINTS WOULD BE ARTIFACTS OF THE CORRUPTION, and only those.
    #
    # "0 goal-relevant components established" is not a finding when `components`
    # arrived as an unreadable string — it is a restatement of the transmission
    # fault, and reporting it sends the investigator exploring for evidence it
    # already has. Every OTHER criterion is still a real shortfall and is still
    # reported: a report mangled in one field must cost that field, not the whole
    # submission's worth of feedback.
    broken = corrupted_fields(payload)

    components = _entries(payload, "components")[0]
    if "components" not in broken and len(components) < criteria.min_components:
        unmet.append(
            f"{len(components)} goal-relevant component(s) established; at least "
            f"{criteria.min_components} are needed to explain this kind of goal"
        )
    entry_points = [
        e for e in (payload.get("entry_points") or []) if isinstance(e, dict)
    ]
    if "entry_points" not in broken and len(entry_points) < criteria.min_entry_points:
        unmet.append(
            f"{len(entry_points)} verified entry point(s) into the goal-relevant "
            f"behaviour; at least {criteria.min_entry_points} needed"
        )
    public_api = [
        e for e in entry_points
        if str(e.get("perspective") or "") == "public_api"
    ]
    if (
        "entry_points" not in broken
        and len(public_api) < criteria.min_public_api_entry_points
    ):
        # Named separately from the count above because the fix is different:
        # not "find another way in" but "find the name a CALLER types". The
        # `neighbors` tool with `exported_by` gives the dotted import path.
        unmet.append(
            f"{len(public_api)} entry point(s) with perspective `public_api`; at "
            f"least {criteria.min_public_api_entry_points} needed — this goal is "
            f"about USING this code, so the symbol a developer imports and calls "
            f"must be established, not only what invokes the behaviour at runtime "
            f"(use `neighbors` with `exported_by` for the dotted import path)"
        )

    flows = _entries(payload, "flows")[0]
    if "flows" in broken:
        pass                      # every flow complaint below would be an artifact
    elif len(flows) < criteria.min_flows:
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
        # `None` means the criterion does not apply to this goal type at all —
        # not that its floor is zero. See the field's own note.
        if (
            criteria.min_flow_files is not None
            and best_files < criteria.min_flow_files
        ):
            unmet.append(
                f"no flow crosses more than {best_files} file(s); this goal's "
                f"behaviour spans at least {criteria.min_flow_files}"
            )
    if ("relationships" not in broken
            and len(payload.get("relationships") or []) < criteria.min_relationships):
        unmet.append(
            f"{len(payload.get('relationships') or [])} confirmed relationship(s); "
            f"at least {criteria.min_relationships} needed"
        )
    if ("contracts" not in broken
            and len(payload.get("contracts") or []) < criteria.min_contracts):
        unmet.append(
            f"{len(payload.get('contracts') or [])} contract(s)/abstraction(s) "
            f"described; at least {criteria.min_contracts} needed for this goal"
        )
    if ("prerequisites" not in broken
            and len(payload.get("prerequisites") or []) < criteria.min_prerequisites):
        unmet.append("no prerequisite concepts identified")
    if not str(payload.get("understanding") or "").strip():
        unmet.append("`understanding` is empty")

    # ── the change boundary ───────────────────────────────────────────────────
    #
    # Each message names the LEVER, not the shortfall. "0 targets established" is
    # a count; "say which symbol the change would be added to" is something the
    # investigator can go and do, which is the difference between feedback that
    # moves a run and feedback that repeats it (see `gap_message`).
    # THE STRUCTURAL REQUIREMENT, checked before the counts.
    #
    # Ordered first because it names the lever the counts cannot: an empty
    # `change_boundary` fails three counted criteria at once, and three messages
    # about missing entries do not say "this section is the thing the rest of the
    # product reads". Reported once, in the words of what it blocks.
    if criteria.requires_change_boundary and not boundary_usable(skeleton, payload):
        named = len(boundary_targets(payload))
        unmet.append(
            "`change_boundary` is not usable: "
            + (
                "no `target` entry names both a file and a symbol"
                if named == 0 else
                f"none of its {named} `target` entr(ies) resolve against the "
                f"repository"
            )
            + " — this goal is about making a specific change, and the target is "
            "what says where it belongs. Name the file and the symbol the change "
            "is added to or alters, and verify it by reading it."
        )

    targets = boundary_entries(payload, "target")
    if len(targets) < criteria.min_boundary_targets:
        unmet.append(
            f"`change_boundary.target` has {len(targets)} entry(ies); at least "
            f"{criteria.min_boundary_targets} needed — name the file and symbol "
            f"the change would be added to or alter, verified by reading it"
        )
    boundary_tests = boundary_entries(payload, "existing_tests")
    if len(boundary_tests) < criteria.min_boundary_tests:
        unmet.append(
            f"`change_boundary.existing_tests` has {len(boundary_tests)} "
            f"entry(ies); at least {criteria.min_boundary_tests} needed — find "
            f"the tests that already guard this behaviour and read them, so the "
            f"developer can imitate how this repository tests this kind of code"
        )
    anchored = anchored_edge_cases(payload)
    if len(anchored) < criteria.min_boundary_edge_cases:
        total = len(boundary_entries(payload, "edge_cases"))
        unmet.append(
            f"`change_boundary.edge_cases` has {len(anchored)} case(s) anchored in "
            f"code (of {total} listed); at least "
            f"{criteria.min_boundary_edge_cases} must give `file` and `symbol` — "
            f"a case you can point at (a branch, a raise, a default, a comment "
            f"explaining a subtlety) is worth five you reasoned your way to"
        )

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
        future_symbols=future,
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


# What a contribution goal asks the investigation to establish.
#
# THIS IS THE FIX FOR THE ONE DEFECT THE WHOLE CONTRIBUTION JOURNEY RESTS ON.
# `contribution_context` was collected by the interview, carried through goal
# synthesis, and then dropped right here — so two learners with different
# contribution tasks got the SAME investigation of the same repository, and the
# task first mattered at planning time, by which point the repository
# understanding was already fixed and could only be filtered.
#
# It REDIRECTS, it does not shrink. Nothing below asks for fewer findings, and
# the paragraph before the last says so outright, because the exit criteria are
# what stop a thin dossier and a brief that quietly argued against them would
# just produce rejections. A contribution journey is meant to be shorter because
# the CURRICULUM'S REQUIRED SET is smaller — that is the only place shortness can
# honestly be earned (contribution-journey.md A6.1).
_CONTRIBUTION_BRIEF = """\
THIS IS A CONTRIBUTION, NOT A TOUR. The developer is going to make ONE specific
change to this repository, and they are going to write it themselves.

THE CHANGE THEY INTEND TO MAKE:
{task}
{scope}
Investigate for THAT change. Concretely, this redirects the investigation:

  WHERE IT BELONGS. The file and the symbol the change would be added to or
  alter — verified by reading them, not the subsystem it is vaguely near.

  THE CONTRACT ALREADY IN FORCE. What callers of that code may rely on, what it
  promises, and what an existing caller would notice if it changed.

  THE EDGE CASES IT MUST RESPECT. Prefer cases you can point at in code — a
  branch, a raise, a default, a comment explaining a subtlety — over cases you
  can imagine. An anchored edge case is worth five you reasoned your way to.

  THE TESTS THAT ALREADY GUARD THIS BEHAVIOUR. Read them, and list them in
  `change_boundary.existing_tests` — that field specifically, not only as an
  anchor somewhere else in the dossier. How this repository writes a test for
  this kind of code is part of what the developer needs, and it is the field the
  contract checks.

  WHAT THE CHANGE MUST NOT TOUCH. The neighbouring code that looks related and
  is not, or that would be unsafe to alter while making this change.

THE CHANGE DOES NOT EXIST YET, AND THERE IS A PLACE FOR IT

Every citation you make must resolve against the repository AS IT IS NOW. The
symbol the developer is going to add is not there, so an anchor on it can never
be verified — and looking for it will not help.

This matters most where it is most tempting. `components`, `entry_points`,
`flows`, `relationships` and `contracts` describe CODE THAT RUNS TODAY. Do not
write a flow for the method being added, and do not write a relationship from it
to the helpers it will call. There is no way to ground either.

THEY ARE STILL REQUIRED, AND THEY ARE STILL MOST OF THE DOSSIER. Filling in the
change boundary does not replace them — it sits beside them. Populate them with
THE EXISTING CODE THE CHANGE JOINS: the class it is added to, the sibling methods
it will resemble, the internal helper it will reuse, the contract its neighbours
already honour, the flow that runs through them today. That is the code the
developer has to understand before they can write anything, and a dossier that
omits it has not investigated the repository at all.

What you wanted to say there is still wanted — it goes somewhere else:

  the intended behaviour, and how it should differ from what exists
      -> `understanding`, in prose. No anchors, so say it freely.
  where the new code goes
      -> `change_boundary.target`, anchored on the CLASS OR MODULE IT IS ADDED
         TO, with `why_here` naming the sibling it sits beside. That anchor
         resolves, because the container already exists.
  what it must survive
      -> `change_boundary.edge_cases`, anchored on the existing code that shows
         the case — the branch, the raise, the default.
  what it must not break
      -> `change_boundary.must_not_change`.

So: describe the change in prose and in the boundary; anchor only on code you
can read today.

Breadth for its own sake is now a cost. A subsystem this change does not touch
does not belong in the dossier, however interesting it is. This is NOT a licence
to stop early: the exit criteria still apply in full, and an investigation that
has not established the contract, the edge cases and the guarding tests is not
finished.

Investigate until you could tell this developer exactly where to start, what they
must not break, and how to test it. Then submit the dossier, INCLUDING the
`change_boundary` section."""


def _task(goal: dict) -> str:
    """The per-run request. Volatile by nature, so it stays out of the cached seed."""
    parts = [f"The user's goal: {goal.get('primary_goal', '')}"]
    if goal.get("focus_area"):
        parts.append(f"Focus area: {goal['focus_area']}")
    if goal.get("goal_type"):
        parts.append(f"Goal type: {goal['goal_type']}")
    if goal.get("code_depth"):
        parts.append(f"How deep the user asked to go: {goal['code_depth']}")

    task = str(goal.get("contribution_context") or "").strip()
    if goal.get("goal_type") == "contribute_code" and task:
        scope = str(goal.get("contribution_scope") or "").strip()
        parts.append(_CONTRIBUTION_BRIEF.format(
            task=task,
            scope=f"\nHOW LARGE THEY EXPECT IT TO BE: {scope}\n" if scope else "",
        ))
    else:
        # Every other goal type, and a contribution session whose task went
        # unanswered, take the path this function has always taken.
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
