import operator
from dataclasses import dataclass, field
from typing import Annotated

import anthropic

from backend.learning.graph import LearningGraph


@dataclass
class OnboardState:
    repo_url: str
    goal: dict | None = None
    repo_path: str = ""
    # Subsystem account derived from the Layer B survey (or, without one, from
    # the skeleton). Not an index status: it describes the repository, and
    # nothing waits on it.
    module_map: dict | None = None
    # Set by Documentation Agent: README excerpt + per-file module docstrings.
    # Passed to Teaching Agent so it can quote real documentation in lessons.
    doc_context: dict | None = None
    learning_path: list | None = None
    confidence: str = "low"
    # The objective-first planner's account of the cut it made: how many
    # objectives were proposed, how many survived grounding, how large the
    # required set plus its dependency closure was BEFORE any band, where the
    # journey landed, and whether the band bound.
    #
    # This exists because the band is a guard around a number nobody had ever
    # measured (learning-engine.md §6.3): "the curriculum genuinely needs N" and
    # "the band allowed N" are different facts, and only the first can tell you
    # whether a band is set correctly. Sits next to `confidence` because it is
    # the same kind of thing — the planner's self-report, not its output.
    # None for the pre-B3 planner, which does not make a cut.
    plan_report: dict | None = None
    # Phase 3: the interactive learning graph. Set by the Planner Agent,
    # mutated by the mutator on each user signal, persisted by the store.
    # The Phase 1 `learning_path` field stays around for compatibility while
    # the Mentor Agent is still wired in; Phase 3's Planner replaces it.
    graph: LearningGraph | None = None
    # The rendered lesson for `graph.current_node_id`. Set by the Teaching
    # Agent, cleared by /advance. Not persisted on its own — the node's
    # cached_lesson is the source of truth for revisits.
    current_lesson: dict | None = None
    # The Grader's classification of the user's last free-text response
    # ({classification, rationale}). Transient like current_lesson — the
    # durable effect is the node's understanding_state / weak_spot, which
    # the Grader updates directly on the graph.
    last_grade: dict | None = None
    # What the mutator did on the last signal ({kind, new_node_id?,
    # anchor_node_id?}). Transient — the durable effect is the mutated graph.
    # kind: "none" | "prerequisite" | "skip".
    last_mutation: dict | None = None
    # The Layer B repository survey (explorer path). A plain payload dict,
    # loaded from the survey store or produced once and persisted. Context for
    # the investigation — never evidence for a code claim.
    survey: dict | None = None
    # The Goal Investigation result (explorer path, D11): produced once by the
    # goal_investigation node and read by Reviewer and Mentor, which must not
    # explore on their own. Shape:
    #   {"dossier": {...}, "accepted": bool, "stop_reason": str,
    #    "turns": int, "cost_usd": float}
    # `accepted` False means the dossier was salvaged at budget exhaustion with
    # a recorded gap — downstream confidence must reflect that (§5.4).
    investigation: dict | None = None
    # Structured review produced by the Reviewer Agent for goal types that need
    # architectural reasoning (improve_existing_system, understand_architecture).
    # Consumed by the Mentor Agent to emit risk/extension_point nodes. None for
    # all other goal types — the Mentor falls back to its normal behaviour.
    system_review: dict | None = None
    # operator.add reducer: when a node returns errors, the list is *extended*
    # rather than replaced. Required for safe concurrent writes once parallel
    # nodes exist (e.g. Documentation Agent in Phase 2). Harmless today.
    errors: Annotated[list, operator.add] = field(default_factory=list)
    # Client-supplied id for live progress reporting (backend/pipeline/progress).
    # Empty string means "nobody is watching" — every reporting call short-circuits
    # on it, so a run without one behaves exactly as before.
    progress_id: str = ""
    # Carried through the graph so nodes can reach the Anthropic client.
    # LangGraph nodes receive only the state, so extra args like `client=`
    # can't be passed positionally — they ride along here instead.
    client: anthropic.Anthropic | None = field(default=None, repr=False, compare=False)
