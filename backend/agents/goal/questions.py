# Question flow for the Goal Agent dialogue.
#
# Everyone gets the 4 CORE_QUESTIONS in order:
#   1. familiarity  (options)   — where the user is starting from
#   2. goal_type_raw (options)  — why they're here; drives follow-up routing
#   3. primary_goal (free text) — what they want to walk away able to do
#   4. background   (free text) — languages/frameworks they already know
#
# After Q4, FOLLOWUP_QUESTIONS adds 1–2 goal-specific questions:
#   understand_system / understand_component  →  focus_area
#   understand_architecture                   →  focus_area
#   contribute_code                           →  contribution_context
#   improve_existing_system                   →  change_target
#                                                risk_tolerance
#   debug_issue                               →  error_description
#                                                tried_so_far
#
# GOAL_TYPE_MAP translates the human-readable Q2 option into the internal
# goal_type string used for routing and stored in GoalOutput.

from dataclasses import dataclass


@dataclass
class Question:
    key: str
    text: str
    options: list[str] | None = None


FAMILIARITY_OPTIONS = [
    "Starting fresh — never looked at it",
    "Skimmed the README or docs",
    "Looked at some code but still confused",
    "Used it before, now diving into the source",
]

GOAL_TYPE_OPTIONS = [
    "Use it in my own project",
    "Understand the architecture (layers, boundaries, design)",
    "Improve or extend the codebase safely",
    "Contribute code / open a PR",
    "Debug an issue I'm hitting",
    "Understand how it works (reading/learning)",
]

GOAL_TYPE_MAP: dict[str, str] = {
    "Use it in my own project": "understand_component",
    "Understand the architecture (layers, boundaries, design)": "understand_architecture",
    "Improve or extend the codebase safely": "improve_existing_system",
    "Contribute code / open a PR": "contribute_code",
    "Debug an issue I'm hitting": "debug_issue",
    "Understand how it works (reading/learning)": "understand_system",
}

CORE_QUESTIONS: list[Question] = [
    Question(
        key="familiarity",
        text="How familiar are you with this codebase?",
        options=FAMILIARITY_OPTIONS,
    ),
    Question(
        key="goal_type_raw",
        text="What brings you to this repo?",
        options=GOAL_TYPE_OPTIONS,
    ),
    Question(
        key="primary_goal",
        text="What specifically do you want to be able to do after this session?",
    ),
    Question(
        key="background",
        text="What languages, frameworks, or similar tools do you already know?",
    ),
]

_UNDERSTAND_FOLLOWUP = Question(
    key="focus_area",
    text="Is there a part of the system you're most curious about, or do you want the full picture?",
)

_ARCHITECTURE_FOLLOWUP = Question(
    key="focus_area",
    text="Any specific architectural concern (e.g. request lifecycle, extension surface, plugin system), or a full architectural tour?",
)

FOLLOWUP_QUESTIONS: dict[str, list[Question]] = {
    "understand_system": [_UNDERSTAND_FOLLOWUP],
    "understand_component": [_UNDERSTAND_FOLLOWUP],
    "understand_architecture": [_ARCHITECTURE_FOLLOWUP],
    "contribute_code": [
        Question(
            key="contribution_context",
            text="Is there a specific issue or feature you're working on? (paste a GitHub issue link or describe it)",
        )
    ],
    "improve_existing_system": [
        Question(
            key="change_target",
            text="What change do you want to make? (e.g. \"add a new auth scheme\", \"refactor the session lifecycle\", \"extend the adapter interface\")",
        ),
        Question(
            key="risk_tolerance",
            text="How safety-critical is this change? (e.g. \"prototype, can break\", \"production use, must not regress\")",
        ),
    ],
    "debug_issue": [
        Question(key="error_description", text="What error or unexpected behavior are you seeing?"),
        Question(key="tried_so_far", text="What have you already tried?"),
    ],
}
