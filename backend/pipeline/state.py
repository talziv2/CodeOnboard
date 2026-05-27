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
    # operator.add reducer: when a node returns errors, the list is *extended*
    # rather than replaced. Required for safe concurrent writes once parallel
    # nodes exist (e.g. Documentation Agent in Phase 2). Harmless today.
    errors: Annotated[list, operator.add] = field(default_factory=list)
    # Carried through the graph so nodes can reach the Anthropic client.
    # LangGraph nodes receive only the state, so extra args like `client=`
    # can't be passed positionally — they ride along here instead.
    client: anthropic.Anthropic | None = field(default=None, repr=False, compare=False)
