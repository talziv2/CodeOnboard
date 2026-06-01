# Goal Agent — session state, dialogue logic, and goal synthesis.
#
# Entry points:
#   start_session(repo_url)          → creates a new GoalSession
#   process_answer(session, answer)  → advances the dialogue; returns the next
#                                      Question or a completed GoalOutput
#
# When all questions are answered, process_answer calls _synthesize_goal which
# sends the full Q&A to claude-haiku-4-5 and validates the response as GoalOutput.
# That GoalOutput becomes OnboardState.goal — the input to all downstream agents.

import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Literal

import anthropic
from pydantic import BaseModel

from backend.agents.goal.questions import (
    CORE_QUESTIONS,
    FOLLOWUP_QUESTIONS,
    GOAL_TYPE_MAP,
    Question,
)


# Validated output of the goal dialogue. Will feed into OnboardState.goal
# once the pipeline runner (backend/pipeline/runner.py) is wired up.
class GoalOutput(BaseModel):
    primary_goal: str
    goal_type: Literal[
        "understand_system",
        "understand_component",
        "understand_architecture",
        "contribute_code",
        "improve_existing_system",
        "debug_issue",
    ]
    focus_area: str
    experience_level: str
    depth: str
    target_repo: str
    familiarity: str
    background: str
    # Populated only for the relevant goal_type
    contribution_context: str | None = None
    change_target: str | None = None
    risk_tolerance: str | None = None
    error_description: str | None = None
    tried_so_far: str | None = None


# Holds the state of one user's dialogue: which repo, what goal_type was chosen,
# and all answers collected so far (keyed by question key).
@dataclass
class GoalSession:
    session_id: str
    repo_url: str
    goal_type: str | None = None  # set after Q2 is answered
    answers: dict[str, str] = field(default_factory=dict)


def _get_question_sequence(session: GoalSession) -> list[Question]:
    # Before Q2 is answered goal_type is None, so only core questions are returned.
    # After Q2, the relevant follow-ups are appended.
    if session.goal_type is None:
        return CORE_QUESTIONS
    return CORE_QUESTIONS + FOLLOWUP_QUESTIONS[session.goal_type]


def start_session(repo_url: str) -> GoalSession:
    return GoalSession(session_id=str(uuid.uuid4()), repo_url=repo_url)


def process_answer(
    session: GoalSession,
    answer: str,
    client: anthropic.Anthropic | None = None,
) -> tuple[Question | None, GoalOutput | None]:
    sequence = _get_question_sequence(session)
    current_q = sequence[len(session.answers)]

    session.answers[current_q.key] = answer

    if current_q.key == "goal_type_raw":
        if answer not in GOAL_TYPE_MAP:
            raise ValueError(f"invalid_goal_type_option: {answer!r}")
        session.goal_type = GOAL_TYPE_MAP[answer]

    updated_sequence = _get_question_sequence(session)
    next_index = len(session.answers)

    if next_index < len(updated_sequence):
        return updated_sequence[next_index], None

    # All questions answered — synthesize the goal.
    if client is None:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    qa_pairs = [(q.text, session.answers[q.key]) for q in updated_sequence]
    goal = _synthesize_goal(session.repo_url, qa_pairs, client=client)
    return None, goal


_SYSTEM_PROMPT = """\
You are a developer assistant helping onboard engineers to unfamiliar codebases.

Given a user's answers about their learning goal and the target repository URL,
produce a JSON object with exactly these keys:
  primary_goal, goal_type, focus_area, experience_level, depth,
  target_repo, familiarity, background

And these optional keys (include only when the user provided relevant data):
  contribution_context, change_target, risk_tolerance,
  error_description, tried_so_far

Rules:
- goal_type must be one of:
    understand_system            — broad "read this library" tour
    understand_component         — focused dive into one feature
    understand_architecture      — layers, boundaries, extension surface, design
    contribute_code              — specific issue or feature PR
    improve_existing_system      — safely change/extend an existing system; the
                                   user cares about risks, extension points, and
                                   what tests guard the area they will touch
    debug_issue                  — trace a specific error
- depth must be one of: overview, moderate, deep
- experience_level: short phrase, e.g. "beginner", "intermediate", "senior engineer"
- familiarity: short phrase summarising the user's familiarity level
- focus_area: the specific part of the codebase to focus on
- For improve_existing_system, copy the user's `change_target` answer into
  change_target verbatim (or paraphrase if very long), and the user's
  `risk_tolerance` answer into risk_tolerance verbatim.
- Return ONLY the JSON object — no markdown fences, no explanation.
"""


def _synthesize_goal(
    repo_url: str,
    qa_pairs: list[tuple[str, str]],
    client: anthropic.Anthropic,
) -> GoalOutput:
    # Build the user message from all Q&A pairs and call Haiku once.
    user_content = f"Target repository: {repo_url}\n\n"
    for question, answer in qa_pairs:
        user_content += f"Q: {question}\nA: {answer}\n\n"

    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=512,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content.strip()}],
    )

    raw = message.content[0].text
    try:
        # Strip markdown code fences if the model wrapped the JSON
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text.strip())
    except json.JSONDecodeError as exc:
        print(f"[goal/synthesize] raw response was:\n{raw}")
        raise ValueError("synthesis_failed") from exc

    return GoalOutput(**data)
