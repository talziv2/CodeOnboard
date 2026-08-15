# Question flow for the Goal Agent dialogue.
#
# Everyone gets the 5 CORE_QUESTIONS in order:
#   1. familiarity  (options)   — where the user is starting from
#   2. goal_type_raw (options)  — why they're here; drives follow-up routing
#   3. primary_goal (free text) — what they want to walk away able to do
#   4. code_depth   (options)   — how far into the implementation to go
#   5. background   (free text) — languages/frameworks they already know
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
# These strings are shown to the user verbatim rather than generated, so the
# interview is the same five questions every run — no model call, no drift.
#
# The option a user picks comes back as the display string, and GOAL_TYPE_MAP is
# keyed on those same strings, which is what routes Q2 to a goal_type.

from dataclasses import dataclass


@dataclass
class Question:
    key: str
    text: str
    options: list[str] | None = None


# --- option vocabularies -----------------------------------------------------

FAMILIARITY_OPTIONS: list[str] = [
    "Starting fresh — never looked at it",
    "Skimmed the README or docs",
    "Looked at some code but still confused",
    "Used it before, now diving into the source",
]

# Display string → the goal_type it routes to. The display string is what comes
# back on the wire and what the rest of the backend reasons about.
GOAL_TYPE_MAP: dict[str, str] = {
    "Use it in my own project": "understand_component",
    "Understand the architecture (layers, boundaries, design)": "understand_architecture",
    "Improve or extend the codebase safely": "improve_existing_system",
    "Contribute code / open a PR": "contribute_code",
    "Debug an issue I'm hitting": "debug_issue",
    "Understand how it works (reading/learning)": "understand_system",
}

GOAL_TYPE_OPTIONS: list[str] = list(GOAL_TYPE_MAP)

# Display string → the code_depth key the rest of the system reasons about.
#
# Scope (how much of the system a journey covers) and code depth (how far into
# the implementation it goes) are two dimensions, not one — a broad shallow tour
# and a narrow deep dive are both legitimate (learning-engine.md LP4). Only this
# one genuinely needs the user: scope is derived from the goal and the repository,
# and then adjusted against a plan the user can actually see.
#
# Phrased as outcomes rather than levels, because "how deep do you want to go?"
# invites everyone to answer "deep".
CODE_DEPTH_MAP: dict[str, str] = {
    "Give me the map — architecture, responsibilities, flows, key decisions":
        "map",
    "I'll be working in here — the map, plus what I'd need to change things safely":
        "working",
    "I need to master the internals — algorithms, data structures, critical paths":
        "implementation",
}

CODE_DEPTH_OPTIONS: list[str] = list(CODE_DEPTH_MAP)


# --- questions ---------------------------------------------------------------

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
        key="code_depth",
        text="How deep into the actual implementation do you want to go?",
        options=CODE_DEPTH_OPTIONS,
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
        Question(
            key="error_description",
            text="What error or unexpected behavior are you seeing?",
        ),
        Question(
            key="tried_so_far",
            text="What have you already tried?",
        ),
    ],
}
