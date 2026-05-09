# FastAPI application — HTTP surface for the CodeOnboard backend.
#
# Full flow between api.py and agent.py:
#
#   1. Client calls POST /goal/start { repo_url }
#      api.py  → calls agent.start_session(repo_url)
#                creates a GoalSession (session_id, repo_url, empty answers)
#                stores it in the sessions dict
#              ← returns session_id + first Question (with options)
#
#   2. Client calls POST /goal/answer { session_id, answer } (once per question)
#      api.py  → looks up GoalSession by session_id
#                calls agent.process_answer(session, answer)
#                  agent stores the answer, checks if more questions remain
#                  if yes  → returns (next_question, None)
#                  if no   → calls Haiku, returns (None, GoalOutput)
#              ← if not done: returns { done: false, question: { text, options } }
#                if done:     deletes session, returns { done: true, goal: { ... } }
#
# The api.py layer only handles HTTP concerns (routing, status codes, request
# parsing). All dialogue logic lives in agent.py.

import os

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from backend.agents.goal import (
    CORE_QUESTIONS,
    GoalSession,
    process_answer,
    start_session,
)

load_dotenv()
app = FastAPI(title="CodeOnboard API")

# In-memory session store: session_id → GoalSession
sessions: dict[str, GoalSession] = {}


# ── Request / response models ─────────────────────────────────────────────────

class StartRequest(BaseModel):
    repo_url: str


# A single question sent to the client. options=None means free-text input.
class QuestionOut(BaseModel):
    text: str
    options: list[str] | None = None


class StartResponse(BaseModel):
    session_id: str
    question: QuestionOut


class AnswerRequest(BaseModel):
    session_id: str
    answer: str


# done=False  →  question contains the next prompt
# done=True   →  goal contains the final GoalOutput dict
class AnswerResponse(BaseModel):
    question: QuestionOut | None = None
    goal: dict | None = None
    done: bool


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/goal/start", response_model=StartResponse)
def goal_start(body: StartRequest) -> StartResponse:
    session = start_session(body.repo_url)
    sessions[session.session_id] = session
    first_q = CORE_QUESTIONS[0]
    return StartResponse(
        session_id=session.session_id,
        question=QuestionOut(text=first_q.text, options=first_q.options),
    )


@app.post("/goal/answer", response_model=AnswerResponse)
def goal_answer(body: AnswerRequest) -> AnswerResponse:
    session = sessions.get(body.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session_not_found")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    try:
        next_q, goal_output = process_answer(session, body.answer, client=client)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if goal_output is not None:
        del sessions[body.session_id]
        return AnswerResponse(done=True, goal=goal_output.model_dump())

    return AnswerResponse(
        done=False,
        question=QuestionOut(text=next_q.text, options=next_q.options),
    )
