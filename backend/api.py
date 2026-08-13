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
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.agents.goal import (
    CORE_QUESTIONS,
    GoalSession,
    process_answer,
    question_progress,
    start_session,
)
from backend.agents.grader import run as run_grader
from backend.agents.mentor.mutator import mutate as mutate_graph
from backend.agents.teaching import run as run_teaching
from backend.learning import store as learning_store
from backend.pipeline.runner import run_pipeline
from backend.repo import dossier_store
from backend.pipeline.state import OnboardState
from backend.repo.cloner import check_repo_reachable, clone_repo, get_commit_sha

load_dotenv(override=True)
app = FastAPI(title="CodeOnboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
# index/total let the UI show interview progress. total is a lower bound until
# Q2 fixes the goal_type, since goal_type decides how many follow-ups follow.
class QuestionOut(BaseModel):
    text: str
    options: list[str] | None = None
    index: int = 1
    total: int = len(CORE_QUESTIONS) + 1


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

class RepoCheckRequest(BaseModel):
    repo_url: str


@app.post("/repo/check")
def repo_check(body: RepoCheckRequest) -> dict:
    # Catches an unclonable URL before the user answers five questions, rather
    # than surfacing it as a pipeline failure minutes later.
    reason = check_repo_reachable(body.repo_url)
    return {"ok": reason is None, "reason": reason}


@app.post("/goal/start", response_model=StartResponse)
def goal_start(body: StartRequest) -> StartResponse:
    session = start_session(body.repo_url)
    sessions[session.session_id] = session
    first_q = CORE_QUESTIONS[0]
    index, total = question_progress(session)
    return StartResponse(
        session_id=session.session_id,
        question=QuestionOut(
            text=first_q.text, options=first_q.options, index=index, total=total
        ),
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

    index, total = question_progress(session)
    return AnswerResponse(
        done=False,
        question=QuestionOut(
            text=next_q.text,
            options=next_q.options,
            index=index,
            total=total,
        ),
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
    # When an identical (repo_url, goal) session already exists, /session/start
    # resumes it instead of re-running the pipeline. Set force_new to start a
    # fresh session regardless.
    force_new: bool = False


class AdvanceRequest(BaseModel):
    signal: str = "next"
    node_id: str | None = None  # if provided, advance from this node instead of current


class RespondRequest(BaseModel):
    response: str
    node_id: str | None = None  # if provided, grade this node instead of current


class OverrideRequest(BaseModel):
    action: str  # "mark_understood" | "mark_weak" | "skip"
    node_id: str | None = None  # defaults to the current node


# Shown when the Teaching Agent fails outright, so the session isn't blocked.
_FALLBACK_READ_SOURCE = (
    "The lesson for this node could not be generated automatically.\n\n"
    "Please read the source file `{file}` lines {start}–{end} directly."
)
_FALLBACK_SKIP_NODE = "Lesson generation failed. Please skip this node."
_FALLBACK_PROMPT = "What is the main purpose of this code?"


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
    # Make doc_context available to Teaching Agent. It lives on the graph
    # (persisted in SQLite) because state is reconstructed fresh here.
    state.doc_context = graph.doc_context
    run_teaching(state, client=client)
    # Persist whatever changed (cached_lesson on the node, etc.).
    learning_store.save_graph(graph, SESSIONS_DB_PATH)
    if state.current_lesson is None:
        # Surface why teaching failed — state.errors is otherwise discarded.
        print(f"[teaching fallback] node={graph.current_node_id} errors={state.errors}", flush=True)
        # Fallback: return a minimal lesson so the session isn't blocked.
        node = graph.nodes.get(graph.current_node_id)
        fallback = {
            "walkthrough": (
                _FALLBACK_READ_SOURCE.format(
                    file=node.code_anchor.file,
                    start=node.code_anchor.line_start,
                    end=node.code_anchor.line_end,
                )
                if node else _FALLBACK_SKIP_NODE
            ),
            "prompt": _FALLBACK_PROMPT,
            "expected_answer": "",
            "prompt_kind": "predict-then-reveal",
        }
        # Save fallback as cached_lesson so the grader can run against it.
        if node:
            node.cached_lesson = fallback
            learning_store.save_graph(graph, SESSIONS_DB_PATH)
        return fallback
    return state.current_lesson


@app.post("/session/start")
def session_start(body: SessionStartRequest) -> dict:
    # Resume: if an identical (repo_url, goal) session exists, continue it
    # rather than paying for the pipeline again. Match on exact goal equality.
    if not body.force_new:
        resumed = _try_resume(body.repo_url, body.goal)
        if resumed is not None:
            return resumed

    client = _new_client()
    state = run_pipeline(body.repo_url, body.goal, client=client)
    if state.graph is None:
        raise HTTPException(
            status_code=500,
            detail={"error": "no_graph", "errors": state.errors},
        )
    learning_store.save_graph(state.graph, SESSIONS_DB_PATH)
    # The dossier outlives the request that produced it: Teaching and the
    # Mutator run later in the session and need the same understanding. Keyed to
    # this session and this commit, so goal-specific understanding is never
    # reused across goals or against code that has since drifted.
    if state.investigation:
        try:
            dossier_store.save_investigation(
                state.graph.session_id,
                get_commit_sha(state.repo_path),
                state.investigation,
                SESSIONS_DB_PATH,
            )
        except Exception as e:
            # Persistence is enrichment (D12) — failing here must not lose a
            # graph the user has already paid for.
            state.errors.append(f"dossier persistence failed (non-fatal): {e}")
    return {
        "session_id": state.graph.session_id,
        "graph": state.graph.to_dict(),
        "resumed": False,
        "errors": state.errors,
    }


def _try_resume(repo_url: str, goal: dict) -> dict | None:
    for summary in learning_store.list_sessions_for_repo(repo_url, SESSIONS_DB_PATH):
        if summary["goal"] != goal:
            continue
        graph = learning_store.load_graph(summary["session_id"], SESSIONS_DB_PATH)
        if graph is None:
            continue
        # Move the pointer to a sensible re-entry point and persist it.
        resume_node = graph.resume_point()
        if resume_node is not None:
            graph.set_current(resume_node)
            learning_store.save_graph(graph, SESSIONS_DB_PATH)
        return {
            "session_id": graph.session_id,
            "graph": graph.to_dict(),
            "resumed": True,
            "errors": [],
        }
    return None


@app.get("/sessions")
def list_sessions(repo_url: str) -> dict:
    # Past sessions for a repo, so a returning client can find and resume one.
    summaries = learning_store.list_sessions_for_repo(repo_url, SESSIONS_DB_PATH)
    return {"sessions": summaries}


@app.get("/session/{session_id}")
def session_get(session_id: str) -> dict:
    graph = _load_session_or_404(session_id)
    return graph.to_dict()


@app.get("/session/{session_id}/lesson")
def session_lesson(session_id: str) -> dict:
    graph = _load_session_or_404(session_id)
    if graph.current_node_id is None:
        raise HTTPException(status_code=409, detail="session_has_no_current_node")

    _render_current_lesson(graph, _new_client())
    node = graph.nodes[graph.current_node_id]

    return {"node_id": graph.current_node_id, "lesson": node.cached_lesson}


@app.post("/session/{session_id}/advance")
def session_advance(session_id: str, body: AdvanceRequest) -> dict:
    # "next" moves along the path; "skip" marks the node skipped then advances.
    # Other signals (deeper / simpler) are deferred (phase3.md Part 6).
    if body.signal not in ("next", "skip"):
        raise HTTPException(
            status_code=400,
            detail=f"unsupported signal {body.signal!r}; supported: 'next', 'skip'",
        )

    graph = _load_session_or_404(session_id)
    current = body.node_id or graph.current_node_id
    if current is None:
        raise HTTPException(status_code=409, detail="session_has_no_current_node")
    if current not in graph.nodes:
        raise HTTPException(status_code=404, detail="node_not_found")
    graph.set_current(current)

    if body.signal == "skip":
        client = _new_client()
        state = OnboardState(repo_url=graph.repo_url, goal=graph.goal, client=client)
        state.graph = graph
        mutate_graph(state, "skip")
        learning_store.save_graph(graph, SESSIONS_DB_PATH)
        nxt = graph.current_node_id if graph.current_node_id != current else None
        if nxt is None or nxt == current:
            return {"done": True}
        lesson = _render_current_lesson(graph, client)
        return {"done": False, "node_id": graph.current_node_id, "lesson": lesson}

    # signal == "next"
    graph.mark_visited(current)
    nxt = graph.next_in_path(current)

    # If the current node is a prerequisite, skip the node it unlocks —
    # the user already tried it (got it wrong) and chose "Try again" which
    # inserted this prerequisite. After learning the prereq, move forward
    # past the original node rather than retrying it.
    # A prerequisite node has an outgoing prerequisite edge to the node it unlocks
    current_is_prereq = any(
        e.kind == "prerequisite" and e.from_node_id == current
        for e in graph.edges
    )
    if current_is_prereq and nxt is not None:
        graph.mark_visited(nxt)
        nxt = graph.next_in_path(nxt)

    if nxt is None:
        learning_store.save_graph(graph, SESSIONS_DB_PATH)
        return {"done": True}

    graph.set_current(nxt)
    client = _new_client()
    lesson = _render_current_lesson(graph, client)  # also persists
    return {"done": False, "node_id": nxt, "lesson": lesson}


@app.post("/session/{session_id}/respond")
def session_respond(session_id: str, body: RespondRequest) -> dict:
    graph = _load_session_or_404(session_id)
    current = body.node_id or graph.current_node_id
    if current is None:
        raise HTTPException(status_code=409, detail="session_has_no_current_node")
    if current not in graph.nodes:
        raise HTTPException(status_code=404, detail="node_not_found")
    # Set current so grader and mutator operate on the right node
    graph.set_current(current)
    if not graph.nodes[current].cached_lesson:
        raise HTTPException(status_code=409, detail="no_lesson_rendered_yet")

    client = _new_client()
    state = OnboardState(repo_url=graph.repo_url, goal=graph.goal, client=client)
    state.graph = graph
    run_grader(state, body.response, client=client)
    # The Grader updated the node's understanding_state / weak_spot in place.

    grade = state.last_grade or {}
    classification = grade.get("classification") or "partial"
    graph.record_attempt(
        current, body.response, classification, grade.get("rationale") or ""
    )

    # A WRONG answer gets a warm-up automatically — being stuck is exactly when
    # a user is least able to judge that they need one. Three classifications do
    # not qualify:
    #   partial    the user is mostly there, so the warm-up stays an offer they
    #              can decline (the /retry endpoint);
    #   off-topic  the answer says nothing about their understanding, so it is
    #              not grounds to reshape their path — they typed something
    #              unrelated, which is not the same as being stuck;
    #   understood nothing to remediate.
    # The Mutator's one-prerequisite-per-node cap still applies, so repeated
    # failures cannot stack warm-ups.
    mutation = {"kind": "none"}
    if classification == "confused":
        try:
            mutation_state = OnboardState(
                repo_url=graph.repo_url, goal=graph.goal, client=client
            )
            mutation_state.graph = graph
            mutation_state.repo_path = clone_repo(graph.repo_url)
            mutate_graph(mutation_state, "prerequisite", client=client)
            mutation = mutation_state.last_mutation or {"kind": "none"}
            state.errors.extend(mutation_state.errors)
        except Exception as exc:  # a failed warm-up must not lose the grade
            state.errors.append(f"auto prerequisite failed: {exc}")

    learning_store.save_graph(graph, SESSIONS_DB_PATH)

    return {
        "classification": classification,
        "rationale": grade.get("rationale"),
        "understanding_state": graph.nodes[current].understanding_state,
        "mutation": mutation,
        "current_node_id": graph.current_node_id,  # may now point at a new prerequisite
    }


@app.post("/session/{session_id}/retry")
def session_retry(session_id: str, body: dict) -> dict:
    """Insert a prerequisite for the current node and load its lesson.
    Called when the user clicks 'Try again' after a wrong answer.
    """
    node_id = body.get("node_id")
    graph = _load_session_or_404(session_id)
    current = node_id or graph.current_node_id
    if not current or current not in graph.nodes:
        raise HTTPException(status_code=404, detail="node_not_found")
    graph.set_current(current)
    client = _new_client()
    state = OnboardState(repo_url=graph.repo_url, goal=graph.goal, client=client)
    state.graph = graph
    state.repo_path = clone_repo(graph.repo_url)
    mutate_graph(state, "prerequisite", client=client)
    learning_store.save_graph(graph, SESSIONS_DB_PATH)
    if graph.current_node_id == current:
        # No prerequisite was inserted (guard triggered) — just return current
        return {"current_node_id": current, "inserted": False}
    lesson = _render_current_lesson(graph, client)
    return {"current_node_id": graph.current_node_id, "inserted": True, "lesson": lesson}


@app.post("/session/{session_id}/jump")
def session_jump(session_id: str, body: dict) -> dict:
    node_id = body.get("node_id")
    graph = _load_session_or_404(session_id)
    if not node_id or node_id not in graph.nodes:
        raise HTTPException(status_code=404, detail="node_not_found")
    graph.set_current(node_id)
    learning_store.save_graph(graph, SESSIONS_DB_PATH)
    return {"current_node_id": node_id}


@app.post("/session/{session_id}/override")
def session_override(session_id: str, body: OverrideRequest) -> dict:
    # User-driven edits to their own understanding graph. Pure Python, no LLM.
    if body.action not in ("mark_understood", "mark_weak", "skip"):
        raise HTTPException(
            status_code=400, detail=f"unsupported action {body.action!r}"
        )
    graph = _load_session_or_404(session_id)
    node_id = body.node_id or graph.current_node_id
    if node_id is None or node_id not in graph.nodes:
        raise HTTPException(status_code=404, detail="node_not_found")

    graph.override(node_id, body.action)
    learning_store.save_graph(graph, SESSIONS_DB_PATH)
    node = graph.nodes[node_id]
    return {
        "node_id": node_id,
        "understanding_state": node.understanding_state,
        "visited": node.visited,
        "weak_spot": node.weak_spot,
    }


@app.get("/session/{session_id}/file")
def session_file(session_id: str, path: str) -> dict:
    graph = _load_session_or_404(session_id)
    repo_path = clone_repo(graph.repo_url)
    full_path = os.path.join(repo_path, path)
    # Prevent path traversal outside the repo
    if not os.path.abspath(full_path).startswith(os.path.abspath(repo_path)):
        raise HTTPException(status_code=400, detail="invalid_path")
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="file_not_found")
    with open(full_path, encoding="utf-8", errors="replace") as f:
        content = f.read()
    return {"path": path, "content": content}
