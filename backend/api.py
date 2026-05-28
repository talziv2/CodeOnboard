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
from backend.agents.teaching import run as run_teaching
from backend.learning import store as learning_store
from backend.pipeline.runner import run_pipeline
from backend.pipeline.state import OnboardState
from backend.rag.cloner import clone_repo

load_dotenv()
app = FastAPI(title="CodeOnboard API")

# In-memory session store: session_id → GoalSession (goal dialogue only).
# Learning-graph sessions live in SQLite (learning_store) — different lifecycle:
# the goal dialogue is ephemeral, the learning graph persists across requests.
sessions: dict[str, GoalSession] = {}

# Indirection so tests can point persistence at a temp DB.
SESSIONS_DB_PATH = learning_store.DEFAULT_DB_PATH


def _new_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


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


# ── /onboard ──────────────────────────────────────────────────────────────────

class OnboardRequest(BaseModel):
    repo_url: str
    goal: dict


class OnboardResponse(BaseModel):
    learning_path: list | None
    module_map: dict | None
    confidence: str
    errors: list


@app.post("/onboard", response_model=OnboardResponse)
def onboard(body: OnboardRequest) -> OnboardResponse:
    client = _new_client()
    state = run_pipeline(body.repo_url, body.goal, client=client)
    return OnboardResponse(
        learning_path=state.learning_path,
        module_map=state.module_map,
        confidence=state.confidence,
        errors=state.errors,
    )


# ── Interactive learning session (Phase 3 Part 4) ───────────────────────────────
#
# Lifecycle, all backed by SQLite (learning_store):
#   POST /session/start            → run pipeline, persist graph, return it
#   GET  /session/{id}             → fetch the serialized graph (state inspection)
#   GET  /session/{id}/lesson      → render the current node's lesson
#   POST /session/{id}/advance     → mark visited, move to next node, render it
#
# A "lesson" is produced by the Teaching Agent on demand and cached on the node,
# so re-fetching the same node is free.


class SessionStartRequest(BaseModel):
    repo_url: str
    goal: dict


class AdvanceRequest(BaseModel):
    signal: str = "next"


def _load_session_or_404(session_id: str):
    graph = learning_store.load_graph(session_id, SESSIONS_DB_PATH)
    if graph is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    return graph


def _render_current_lesson(graph, client) -> dict:
    """Run the Teaching Agent on the graph's current node, persist, return the lesson.

    repo_path is re-derived via clone_repo (no-op when already cloned) since the
    persisted graph doesn't carry it — Teaching needs it to read source.
    """
    repo_path = clone_repo(graph.repo_url)
    state = OnboardState(repo_url=graph.repo_url, goal=graph.goal, client=client)
    state.repo_path = repo_path
    state.graph = graph
    run_teaching(state, client=client)
    # Persist whatever changed (cached_lesson on the node, etc.).
    learning_store.save_graph(graph, SESSIONS_DB_PATH)
    if state.current_lesson is None:
        raise HTTPException(
            status_code=500,
            detail={"error": "lesson_generation_failed", "errors": state.errors},
        )
    return state.current_lesson


@app.post("/session/start")
def session_start(body: SessionStartRequest) -> dict:
    client = _new_client()
    state = run_pipeline(body.repo_url, body.goal, client=client)
    if state.graph is None:
        raise HTTPException(
            status_code=500,
            detail={"error": "no_graph", "errors": state.errors},
        )
    learning_store.save_graph(state.graph, SESSIONS_DB_PATH)
    return {
        "session_id": state.graph.session_id,
        "graph": state.graph.to_dict(),
        "errors": state.errors,
    }


@app.get("/session/{session_id}")
def session_get(session_id: str) -> dict:
    graph = _load_session_or_404(session_id)
    return graph.to_dict()


@app.get("/session/{session_id}/lesson")
def session_lesson(session_id: str) -> dict:
    graph = _load_session_or_404(session_id)
    if graph.current_node_id is None:
        raise HTTPException(status_code=409, detail="session_has_no_current_node")
    client = _new_client()
    lesson = _render_current_lesson(graph, client)
    return {"node_id": graph.current_node_id, "lesson": lesson}


@app.post("/session/{session_id}/advance")
def session_advance(session_id: str, body: AdvanceRequest) -> dict:
    # Part 4 supports only "next". Richer signals (deeper / simpler / skip /
    # confused) arrive with the Part 6 mutator.
    if body.signal != "next":
        raise HTTPException(
            status_code=400,
            detail=f"unsupported signal {body.signal!r}; only 'next' is supported in Part 4",
        )

    graph = _load_session_or_404(session_id)
    current = graph.current_node_id
    if current is None:
        raise HTTPException(status_code=409, detail="session_has_no_current_node")

    graph.mark_visited(current)
    nxt = graph.next_in_sequence(current)
    if nxt is None:
        # End of the sequence. Leave current_node_id pointing at the last node
        # (non-destructive) so /session/{id} still shows where the user ended.
        learning_store.save_graph(graph, SESSIONS_DB_PATH)
        return {"done": True}

    graph.set_current(nxt)
    client = _new_client()
    lesson = _render_current_lesson(graph, client)  # also persists
    return {"done": False, "node_id": nxt, "lesson": lesson}
