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
    module_map: dict | None = None
    relevant_modules: list[str] | None = None  # set by Prioritization Agent
    chunks_embedded: bool = False
    # Reviewer Agent output (set only for goal types that need it:
    # improve_existing_system, understand_architecture). Consumed by the
    # Mentor as additional context. Shape: see backend/agents/reviewer/agent.py
    # ReviewerOutput. None for goal types that skip the Reviewer node.
    system_review: dict | None = None
    learning_path: list | None = None
    confidence: str = "low"
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
    # operator.add reducer: when a node returns errors, the list is *extended*
    # rather than replaced. Required for safe concurrent writes once parallel
    # nodes exist (e.g. Documentation Agent in Phase 2). Harmless today.
    errors: Annotated[list, operator.add] = field(default_factory=list)
    # Carried through the graph so nodes can reach the Anthropic client.
    # LangGraph nodes receive only the state, so extra args like `client=`
    # can't be passed positionally — they ride along here instead.
    client: anthropic.Anthropic | None = field(default=None, repr=False, compare=False)
