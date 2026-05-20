import operator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated, Any

if TYPE_CHECKING:
    import anthropic


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
    # operator.add reducer: when a node returns errors, the list is *extended*
    # rather than replaced. Required for safe concurrent writes once parallel
    # nodes exist (e.g. Documentation Agent in Phase 2). Harmless today.
    errors: Annotated[list, operator.add] = field(default_factory=list)
    # Carried through the graph so nodes can reach the Anthropic client.
    # LangGraph nodes receive only the state, so extra args like `client=`
    # can't be passed positionally — they ride along here instead.
    client: "anthropic.Anthropic | None" = field(default=None, repr=False, compare=False)
