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

import logging
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
from backend.agents.grader.verification import grade_verification
from backend.agents.mentor.mutator import Diagnosis, mutate as mutate_graph
from backend.agents.teaching import run as run_teaching
from backend.agents.teaching import respond as teaching_respond
from backend.agents.teaching import verify as teaching_verify
from backend.learning import adaptation
from backend.learning import history
from backend.learning import progress
from backend.learning import scope
from backend.learning import store as learning_store
from backend.learning import understanding
from backend.learning.graph import understanding_of
from backend.pipeline.runner import run_pipeline
from backend.repo import dossier_store
from backend.pipeline.state import OnboardState
from backend.repo.cloner import check_repo_reachable, clone_repo, get_commit_sha

load_dotenv(override=True)
logger = logging.getLogger(__name__)
app = FastAPI(title="CodeOnboard API")

# The dev frontend's origins. `localhost` and `127.0.0.1` are the same machine
# but different *origins* to a browser, so both have to be listed: opening the
# app on the one that isn't allowed makes every call fail CORS, which the
# browser reports only as "Failed to fetch".
#
# Overridable so a second instance can be run beside an existing one — an
# isolated copy on another port, for instance — without broadening what a
# normal run accepts.
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CODEONBOARD_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
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
    # "assessment" (the lesson's own question) or "verification" (a fresh question
    # about one gap, from POST /verify). Defaulted, so every existing client keeps
    # working without knowing verification exists (§18.10).
    kind: str = history.ASSESSMENT


class WaiveRequest(BaseModel):
    # Omit to waive every open blocking gap on the node; supply one to waive it
    # alone. Two shapes rather than two endpoints, because "stop asking me about
    # this" is one intent at two scopes (§18.16.2).
    gap_id: str | None = None
    node_id: str | None = None


def _gaps_payload(node) -> list[dict]:
    """The node's OPEN gaps, for the learner to see.

    §18.10 calls this "the product's most honest surface: it tells the learner
    what they still do not know, by name". Open only — a `verified` gap is closed
    and a `waived` one is what they asked to stop hearing about.

    `blocking` is included even though it is derivable from `kind`, because the
    frontend needs to distinguish "this is holding the node back" from "this is
    worth knowing" without shipping a copy of the policy.
    """
    return [
        {
            "id": gap.id,
            "kind": gap.kind,
            "claim": gap.claim,
            "objective_part": gap.objective_part,
            "status": gap.status,
            "blocking": gap.is_blocking,
            "verification_attempts": gap.verification_attempts,
            "exhausted": gap.is_exhausted,
        }
        for gap in node.gaps
        if gap.is_open
    ]


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


def _node_source(graph, node) -> str:
    """The unit's anchored source, for a re-teach that must stay grounded.

    A corrected lesson is still a lesson: it may not be written from the
    objective alone (learning-engine.md §4.1.2), so this raises exactly as
    rendering does when nothing can be read.
    """
    from backend.agents.teaching.agent import _read_node_source

    return _read_node_source(clone_repo(graph.repo_url), node)


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
        logger.warning(
            "teaching fallback: node=%s errors=%s", graph.current_node_id, state.errors
        )
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
    # Leaving unfinished remediation behind is an EXPLICIT DECISION, so it is
    # recorded as one (§18.16.3). `continue_past` fires only where the node
    # actually has open blocking gaps, so an ordinary advance stamps nothing.
    #
    # This is what makes journey completion reachable at all: walking to the end
    # settles every stop by construction. A refresh does not advance, so a refresh
    # never settles anything — which is the property that keeps "the learner dealt
    # with this" from being inferred from mere presence.
    graph.continue_past(current)
    # A prerequisite edge points at the node it unlocks, so next_in_path already
    # walks a warm-up back to the objective the user failed. That return is the
    # point of the remediation: they get another attempt at the thing they got
    # wrong, now that the missing piece has been taught. Nothing here special-
    # cases prerequisites — jumping *past* the original node would leave the
    # failed objective permanently unlearned.
    nxt = graph.next_in_path(current)

    # Step over `optional` units. They sit on the same spine by design (§6.3) so
    # that nothing is lost and depth stays one click away in the rail — but they
    # are not part of the journey the learner was promised, and the stop counter
    # and `readiness()` have always excluded them. Walking into one contradicted
    # both: a sixteen-unit graph that says "stop 3 of 15" would still make the
    # learner pass through all sixteen.
    #
    # This is what makes "make it shorter" mean anything, and what makes
    # prune-ahead actually shorten a journey rather than only relabel it.
    # Reaching an optional unit deliberately, from the rail, still works — `jump`
    # sets it as current and nothing here interferes.
    seen: set[str] = {current}
    while nxt is not None and graph.is_optional(graph.nodes[nxt]) and nxt not in seen:
        seen.add(nxt)
        nxt = graph.next_in_path(nxt)

    if nxt is None:
        learning_store.save_graph(graph, SESSIONS_DB_PATH)
        return {"done": True}

    graph.set_current(nxt)
    client = _new_client()
    lesson = _render_current_lesson(graph, client)  # also persists
    return {"done": False, "node_id": nxt, "lesson": lesson}


def _respond_to_verification(
    graph, state: OnboardState, current: str, body: RespondRequest, client
) -> dict:
    """Grade an answer to a verification question (gap-model M6, §18.10).

    A separate act with a separate shape, and the differences are the design:

      - No `classification`. A verification answer is evidence about specific
        false beliefs, not a re-assessment of the objective, so it does not
        re-grade the node. `understanding_state` still moves, but only because
        gaps closing changes what `understanding_of` derives.
      - No adaptation. `decide_all` is not consulted and no hint, re-teach or
        warm-up is produced — the outcome of a verification is a gap closing or
        not closing.
      - The attempt is recorded with `kind="verification"`, which keeps it out of
        `history.assessments()` and therefore out of every assessment-only
        consumer.

    The existing response keys are still present, so an un-updated client that
    somehow posts here reads something coherent rather than a `KeyError`.
    """
    node = graph.nodes[current]
    if not node.gap_state.pending_verification:
        raise HTTPException(status_code=409, detail="no_pending_verification")

    result = grade_verification(state, node, body.response, client=client)
    if result.get("failed"):
        # Nothing resolved, no attempt charged, the question still pending. The
        # learner may answer again without having spent anything.
        raise HTTPException(status_code=503, detail="verification_grading_failed")

    graph.record_attempt(
        current,
        body.response,
        # Deliberately not a verdict about the objective: `understanding_of` is
        # what answers that, from the latest ASSESSMENT plus the gap list.
        classification="",
        rationale=result.get("rationale") or "",
        kind=history.VERIFICATION,
    )
    learning_store.save_graph(graph, SESSIONS_DB_PATH)

    return {
        "kind": history.VERIFICATION,
        "resolved": result.get("resolved", []),
        "unresolved": result.get("unresolved", []),
        "rationale": result.get("rationale"),
        "gaps": _gaps_payload(node),
        "understanding_state": understanding_of(node),
        "current_node_id": graph.current_node_id,
        # Present so the shape overlaps the assessment reply rather than being a
        # disjoint union the client has to switch on before it can read anything.
        "classification": None,
        "gap_kind": None,
        "mutation": {"kind": "none"},
        "adaptation": {"kind": "none"},
        "errors": state.errors,
    }


@app.post("/session/{session_id}/verify")
def session_verify(session_id: str, body: dict | None = None) -> dict:
    """Generate a FRESH question testing whether a gap has actually closed.

    Replaces "Try again", which re-showed the answered question after `reveal`
    had already given away the reasoning — a memory check (§18.7).

    Aimed at ONE gap: the highest-precedence open blocking gap that still has
    verification budget. Asking about three at once would let an answer address
    one and appear to have addressed all three, which is the partial answer that
    looks like completion.
    """
    node_id = (body or {}).get("node_id")
    graph = _load_session_or_404(session_id)
    current = node_id or graph.current_node_id
    if current is None or current not in graph.nodes:
        raise HTTPException(status_code=404, detail="node_not_found")
    node = graph.nodes[current]

    plan = adaptation.decide_all(
        "partial", list(node.gaps),
        remediation_rounds=node.gap_state.remediation_rounds,
    )
    # The active set is already precedence-ordered and cap-filtered, so an
    # exhausted gap is not offered — the system has stopped proposing for it.
    target = plan.active_set[0] if plan.active_set else None
    if target is None:
        raise HTTPException(status_code=409, detail="nothing_to_verify")

    client = _new_client()
    state = OnboardState(repo_url=graph.repo_url, goal=graph.goal, client=client)
    state.graph = graph
    try:
        source = _node_source(graph, node)
    except Exception as exc:
        # §4.1.2 applied here: with no source the model would invent the scenario,
        # and failing an imaginary question would record real evidence about it.
        raise HTTPException(status_code=409, detail="source_unavailable") from exc

    prompt = teaching_verify.verify(state, node, [target], source, client=client)
    if prompt is None:
        raise HTTPException(status_code=503, detail="verification_unavailable")

    stored = teaching_verify.store(node, prompt)
    learning_store.save_graph(graph, SESSIONS_DB_PATH)
    return {
        "node_id": current,
        # No `reveal` and no expected answer — excluded by design, not omitted for
        # brevity. Shipping the answer beside the question is what made re-asking
        # meaningless in the first place.
        "question": stored["question"],
        "targets": stored["targets"],
        "gaps": _gaps_payload(node),
        "errors": state.errors,
    }


@app.post("/session/{session_id}/waive")
def session_waive(session_id: str, body: WaiveRequest) -> dict:
    """Stop remediating — one gap, or every open blocking gap on the node.

    **Never evidence** (§18.16.2): waiving does not produce `verified`, so the
    node stays short of `understood` and `readiness()` stays honest. What it buys
    is that the system stops asking, and that the journey can still complete.

    Reversible by construction: the gaps are still on the node, and
    `POST /verify` will offer them again once they are re-opened, which is what
    "an offer to verify it now" on the completion screen rests on.
    """
    graph = _load_session_or_404(session_id)
    current = body.node_id or graph.current_node_id
    if current is None or current not in graph.nodes:
        raise HTTPException(status_code=404, detail="node_not_found")
    node = graph.nodes[current]

    if body.gap_id:
        if not graph.waive_gap(current, body.gap_id):
            # Unknown, or already settled. A 404 rather than a silent success, so
            # a stale UI cannot report a waiver that did not happen.
            raise HTTPException(status_code=404, detail="gap_not_open")
        waived = [body.gap_id]
    else:
        waived = graph.waive_remaining(current)

    learning_store.save_graph(graph, SESSIONS_DB_PATH)
    return {
        "node_id": current,
        # NAMED, never a bare count: "what you chose not to check" is the most
        # useful thing the artifact can say (§18.16.3).
        "waived": waived,
        "gaps": _gaps_payload(node),
        "understanding_state": understanding_of(node),
        "readiness": graph.readiness(),
        "complete": graph.is_complete(),
    }


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

    if body.kind == history.VERIFICATION:
        return _respond_to_verification(graph, state, current, body, client)

    run_grader(state, body.response, client=client)
    # The Grader updated the node's understanding_state / weak_spot in place.

    grade = state.last_grade or {}
    classification = grade.get("classification") or "partial"
    gap_kind = grade.get("gap_kind") or "none"
    graph.record_attempt(
        current,
        body.response,
        classification,
        grade.get("rationale") or "",
        gap_kind=gap_kind,
        # Whether the verdict is the Grader's or the fallback. The Grader signals
        # a failure by appending to `state.errors` and returning `partial` with a
        # fixed rationale; recorded here so the two are distinguishable forever
        # after, instead of a system outage counting as half a learner's grasp.
        graded=bool(grade.get("graded", True)),
    )

    # WHAT the answer earns is decided deterministically from why it fell short
    # (learning-engine.md §9.1). Only `missing_prerequisite` changes the graph;
    # the others answer the learner where they are. `off-topic` and `understood`
    # earn nothing — an unrelated answer is evidence of neither understanding nor
    # misunderstanding, and must not reshape a path.
    node = graph.nodes[current]
    # The M4 plan is the SINGLE SOURCE OF TRUTH for both what happens and which
    # gaps it addresses. Nothing below re-derives targets from `gap_kind`: the
    # scalar names a category, and one category can cover several distinct
    # misconceptions that each need correcting by name (§18.5).
    #
    # `gap_kind` is still passed, and is consulted only when there are no gap
    # objects at all — the flag-off world, where the scalar is the whole signal.
    # That is what keeps this call identical to the old `decide` there.
    plan = adaptation.decide_all(classification, list(node.gaps), gap_kind)
    action = plan.action
    rationale = grade.get("rationale") or ""
    mutation = {"kind": "none"}
    adapted: dict = {"kind": action}
    # The lesson a re-teach replaces, captured before it is overwritten.
    superseded: dict | None = None

    if action == "prerequisite":
        try:
            mutation_state = OnboardState(
                repo_url=graph.repo_url, goal=graph.goal, client=client
            )
            mutation_state.graph = graph
            mutation_state.repo_path = clone_repo(graph.repo_url)
            # The Mutator's one-prerequisite-per-node cap still applies, so
            # repeated failures cannot stack warm-ups.
            mutate_graph(
                mutation_state, "prerequisite", client=client,
                # The warm-up is chosen for the diagnosed misconception, not
                # merely for the node (§18.2). We already hold the grade here.
                #
                # `plan.targets[0]` is the ONE gap §18.5 allows a structural
                # mutation to address; the rest stay open and are picked up on a
                # later cycle, after this foundation has landed.
                diagnosis=Diagnosis(
                    answer=body.response, rationale=rationale, gap_kind=gap_kind,
                    gap=plan.targets[0] if plan.targets else None,
                ),
            )
            mutation = mutation_state.last_mutation or {"kind": "none"}
            state.errors.extend(mutation_state.errors)
        except Exception as exc:  # a failed warm-up must not lose the grade
            state.errors.append(f"auto prerequisite failed: {exc}")
    elif action == "hint":
        adapted["text"] = teaching_respond.hint(
            state, node, body.response, rationale, client=client, gaps=plan.targets
        )
    elif action == "followup":
        adapted["text"] = teaching_respond.followup(
            state, node, body.response, rationale, client=client, gaps=plan.targets
        )
    elif action == "reteach":
        try:
            # Snapshot BEFORE the re-teach: `reteach` assigns `cached_lesson`
            # directly, so after the call the previous body no longer exists
            # anywhere.
            previous_lesson = node.cached_lesson
            source = _node_source(graph, node)
            # Every target, not just the leading one: a re-teach is a lesson and
            # can name several misconceptions at once, and one it omits is one
            # nothing else will come back for.
            lesson = teaching_respond.reteach(
                state, node, body.response, rationale, source, client=client,
                gaps=plan.targets,
            )
            adapted["retaught"] = lesson is not None
            if lesson is not None:
                superseded = previous_lesson
        except Exception as exc:
            state.errors.append(f"re-teach failed: {exc}")
            adapted["retaught"] = False

    # Adapting UPWARD, and the only response that shortens the journey: an area
    # the learner has demonstrably got does not need its remaining recommended
    # units at full length. Pure Python, no call, and it runs on every graded
    # answer because the evidence it reads only ever changes here.
    pruned = adaptation.prune_ahead(graph)
    if pruned:
        adapted["pruned"] = len(pruned)

    # ── history (learning-graph.md M2) ────────────────────────────────────────
    #
    # Two records, deliberately in two places, because they have two lifecycles.
    #
    # ATTEMPT-SCOPED: what this answer earned. Caused by one answer, describes
    # one answer. The ids and reasons are kept, not a boolean — "a warm-up was
    # inserted" cannot later answer "and did the learner come back and get it".
    graph.record_response(current, history.new_response(
        action,
        **({"text": adapted["text"]} if adapted.get("text") else {}),
        **({"retaught": adapted["retaught"]} if "retaught" in adapted else {}),
        # The superseded lesson, kept where the supersession happened. A re-teach
        # overwrites `cached_lesson`, so without this the version that misled the
        # learner is gone and "how their understanding moved" loses one side.
        **({"superseded_lesson": superseded} if superseded else {}),
        **({"remediation_node_id": mutation.get("new_node_id")}
           if mutation.get("kind") == "prerequisite" else {}),
        # A refusal is a real answer, not a malfunction: "every candidate was a
        # peer, not a foundation" is the most useful thing the system can say
        # about a confusion it chose not to act on. It was being discarded.
        **({"declined_reason": mutation.get("rationale") or mutation.get("reason")}
           if mutation.get("kind") == "none" and action == "prerequisite" else {}),
    ))

    # PLAN-SCOPED: the journey changed shape. Recorded with the ids it moved, so
    # a later view can explain a shorter journey rather than only report one.
    if pruned:
        graph.record_journey_event(
            history.PRUNE_AHEAD, nodes=pruned,
            cause={"node_id": current,
                   "attempt_index": len(graph.nodes[current].attempts) - 1},
        )
    if mutation.get("kind") == "prerequisite":
        graph.record_journey_event(
            history.REMEDIATION_INSERTED,
            nodes=[mutation.get("new_node_id")],
            cause={"node_id": current,
                   "attempt_index": len(graph.nodes[current].attempts) - 1},
            origin=progress.SYSTEM_REMEDIATION,
            unlocks=current,
        )

    learning_store.save_graph(graph, SESSIONS_DB_PATH)

    return {
        "classification": classification,
        "gap_kind": gap_kind,
        "rationale": grade.get("rationale"),
        "understanding_state": understanding_of(graph.nodes[current]),
        "mutation": mutation,
        "adaptation": adapted,
        "current_node_id": graph.current_node_id,  # may now point at a new prerequisite
        # The outstanding-gaps list (§18.10). Additive: every key above is
        # unchanged, so an un-updated client keeps working and simply does not
        # render it.
        "gaps": _gaps_payload(graph.nodes[current]),
        "complete": graph.is_complete(),
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
    # No grade in scope — the learner asked for this warm-up after answering, so
    # the diagnosis comes off the node's own attempt history. `mutate` does the
    # lookup when we pass nothing, which keeps the fallback in one place.
    #
    # `learner_request` is the one thing this endpoint knows that `/respond`
    # does not: the learner asked to step back rather than the policy sending
    # them (learning-engine.md §18.11).
    mutate_graph(
        state, "prerequisite", client=client, origin=progress.LEARNER_REQUEST
    )
    # Also attempt-less: the learner asked for a warm-up some time after
    # answering, so this is a change to the journey rather than a response to an
    # answer. `origin` is what later separates "I chose to step back" from "the
    # system sent me back" — a distinction no intervention rate should blur.
    inserted = (state.last_mutation or {}).get("new_node_id")
    if inserted:
        graph.record_journey_event(
            history.REMEDIATION_INSERTED, nodes=[inserted],
            origin=progress.LEARNER_REQUEST, unlocks=current,
        )
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


class ScopeRequest(BaseModel):
    direction: str  # "shorter" | "deeper"


@app.post("/session/{session_id}/scope")
def session_scope(session_id: str, body: ScopeRequest) -> dict:
    """Adjust the journey's scope after the learner has seen it (§5.3).

    Pure Python, no LLM, no planning: it moves existing units between the
    `priority` buckets the planner already assigned. `deeper` exposes material
    that is already in the graph and never generates more — a journey with
    nothing optional left has nothing further to offer, and says so rather than
    inventing something to look responsive.
    """
    if body.direction not in ("shorter", "deeper"):
        raise HTTPException(
            status_code=400,
            detail=f"unsupported direction {body.direction!r}; supported: "
                   f"'shorter', 'deeper'",
        )

    graph = _load_session_or_404(session_id)
    before = scope.journey_size(graph)
    changed = (
        scope.shorten(graph) if body.direction == "shorter" else scope.deepen(graph)
    )
    # THE CASE THAT DECIDED THE OWNERSHIP SPLIT: this endpoint takes no answer,
    # so there is no attempt to hang this on. A journey-shape history that lived
    # inside `attempts` could not record half of what changes a journey.
    if changed:
        graph.record_journey_event(
            history.SCOPE_SHORTER if body.direction == "shorter"
            else history.SCOPE_DEEPER,
            nodes=changed,
        )
    learning_store.save_graph(graph, SESSIONS_DB_PATH)

    return {
        "direction": body.direction,
        "changed": len(changed),
        "journey_size_before": before,
        "journey_size": scope.journey_size(graph),
        "readiness": graph.readiness(),
        # False means there was nothing left to move — the caller should say so
        # plainly instead of implying the request did something.
        "applied": bool(changed),
    }


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
        "understanding_state": understanding_of(node),
        "visited": node.visited,
        "weak_spot": node.weak_spot,
    }


@app.get("/session/{session_id}/evidence/{node_id}")
def session_evidence(session_id: str, node_id: str) -> dict:
    """The evidence chain behind one node's understanding state (M3a.1).

    Its own endpoint rather than a slice of the session payload: the timeline
    carries full answer text and superseded lesson bodies, which would multiply
    the size of every `/session/{id}` poll for something read on demand when the
    learner opens one node.
    """
    graph = _load_session_or_404(session_id)
    if node_id not in graph.nodes:
        raise HTTPException(status_code=404, detail="node_not_found")
    return understanding.evidence(graph, node_id)


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
