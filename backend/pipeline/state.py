from dataclasses import dataclass, field


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
    errors: list = field(default_factory=list)
