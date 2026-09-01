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
#                if done:     returns { done: true, goal: { ... } } and KEEPS the
#                             session, so the client's review step can still call
#                             /goal/back to reopen an answer before starting
#
#   2b. Client calls POST /goal/back { session_id } to correct an earlier answer
#      api.py  → calls agent.step_back(session), which un-answers the last
#                question and hands it back with what was answered
#              ← returns { question: {...}, answer: "<what they said>" }
#
# The api.py layer only handles HTTP concerns (routing, status codes, request
# parsing). All dialogue logic lives in agent.py.

import logging
import os
import threading
import uuid
from contextlib import asynccontextmanager

import anthropic
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.routing import Match
from pydantic import BaseModel

from backend.agents.goal import (
    CORE_QUESTIONS,
    GoalSession,
    process_answer,
    question_progress,
    start_session,
    step_back,
)
from backend.agents.briefing import build_briefing
from backend.agents.grader import run as run_grader
from backend.agents.grader.verification import grade_verification
from backend.agents.mentor.mutator import Diagnosis, mutate as mutate_graph
from backend.agents.teaching import run as run_teaching
from backend.agents.teaching import respond as teaching_respond
from backend.agents.teaching import reassess as teaching_reassess
from backend.agents.teaching import verify as teaching_verify
from backend.agents.tutor import context as tutor_context
from backend.agents.tutor import explain as tutor_explain
from backend.agents.tutor import mode as tutor_mode
from backend.agents.tutor import scaffold as tutor_scaffold
from backend.agents.tutor import suggest as tutor_suggest
from backend.learning import adaptation
from backend.learning import history
from backend.learning import progress
from backend.learning import retry as retry_model
from backend.learning import scope
from backend.learning import store as learning_store
from backend.learning import tutor as tutor_model
from backend.learning.flags import tutor_enabled
from backend.learning import understanding
from backend.auth import config as auth_config
from backend.auth import drafts
from backend.auth.deps import CurrentUser, current_user, owned_session
from backend.auth import tokens
from backend.auth.google_routes import identities_router
from backend.auth.google_routes import router as google_router
from backend.auth.routes import router as auth_router
from backend.auth.startup import run_startup_checks
from backend.learning.graph import is_settled, understanding_of
from backend.learning.reset import reset_to_plan
from backend.pipeline import progress as pipeline_progress
from backend.pipeline.runner import run_pipeline
from backend.repo import dossier_store, survey_store
from backend.pipeline.state import OnboardState
from backend.repo.cloner import (
    check_repo_reachable,
    clone_repo,
    get_commit_sha,
    parse_repo_url,
    resolve_within,
)

# `.env` FILLS GAPS; IT DOES NOT WIN.
#
# This was `override=True`, which inverted the precedence every other tool in the
# stack uses: the file beat the environment, so a variable set where the process was
# launched was silently discarded. `CODEONBOARD_GAPS=0 uv run uvicorn …` ran with
# gaps ON if `.env` said `1` — the opposite of what the person typing it asked for,
# with nothing to indicate it.
#
# It also cost fourteen test failures. `.env` carries `CODEONBOARD_CURRICULUM=1` for
# manual E2E runs, and this line runs at IMPORT time, so any test file that imported
# the API switched the Mentor's planner for every test after it (see
# `tests/conftest.py`). The suite is isolated from that now, but the isolation was
# treating a symptom of this line.
#
# Default precedence — real environment first, file second — is what makes both the
# command line and the file usable for what each is for: the file for the values
# that never change on this machine, the environment for the ones being varied right
# now.
load_dotenv()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Checked once, before the process serves anything (multi-user M1).

    The ownership check is a REFUSAL rather than a warning. Once M3's filter is
    in place a session with no `user_id` is unreachable by every user forever,
    and the person who notices is a learner whose work has vanished from their
    dashboard — a log line would not be read, a process that will not start is.

    The Dossier sweep is the opposite: it repairs quietly, because an orphaned
    dossier is unreachable derived data and D12 already makes "absent" a
    supported state for every consumer.

    A lifespan handler rather than `@app.on_event("startup")`, which FastAPI
    deprecates.
    """
    # Configuration BEFORE the database: a deployment with an insecure setting
    # should not get as far as touching data.
    auth_config.enforce()
    result = run_startup_checks(SESSIONS_DB_PATH)
    reported = {k: v for k, v in result.items() if v}
    if reported:
        logger.info("startup housekeeping: %s", reported)
    yield


app = FastAPI(title="CodeOnboard API", lifespan=_lifespan)

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

# `allow_credentials` is what lets the browser send the auth cookie on a
# cross-origin call. It is needed only for DIRECT access to :8000 — the Next.js
# `/api/*` rewrite (D-2) makes the app's own requests first-party, so CORS is not
# load-bearing for it any more.
#
# Kept configured anyway, because `tests/test_cors.py` pins it and because curl,
# Swagger and the smoke scripts all talk to :8000 directly. Never `*` alongside
# credentials — browsers reject that combination, and the explicit list is what
# makes it safe.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(google_router)
app.include_router(identities_router)


# ── the third layer (multi-user.md §7.2) ─────────────────────────────────────
#
# `store.load_graph` makes an unowned read impossible, and `Depends(current_user)`
# makes the routes ergonomic about it. This catches the case both miss: a route
# added later that declares NEITHER, whose author did not run the coverage test.
#
# It checks what a route DECLARES, not whether a cookie is present. A second
# cookie check would duplicate the dependency and disagree with it — the
# dependency resolves the session properly, this one could only guess — so
# instead it asks a different question: "does this path have an auth dependency
# at all?" A path that does is left entirely alone. A path that does not, and is
# not deliberately public, is refused before it runs.
#
# An ALLOW-LIST, not a deny-list. A deny-list of protected paths fails open —
# forget an entry and it is public. This fails closed: a new path is refused
# until somebody names it here, in a diff a reviewer sees.
PUBLIC_PATHS: frozenset[str] = frozenset({
    "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc", "/health",
})

_AUTH_DEPENDENCIES = frozenset({"current_user", "optional_user", "owned_session", "owner_id"})


def _declares_auth(dependant) -> bool:
    """Does this route pull in one of the auth dependencies, at any depth?"""
    if getattr(dependant.call, "__name__", "") in _AUTH_DEPENDENCIES:
        return True
    return any(_declares_auth(sub) for sub in dependant.dependencies)


def _route_for(scope) -> object | None:
    """The route this request will actually be dispatched to, or None.

    Uses Starlette's own matcher rather than comparing `request.url.path` to
    `route.path`. THE BUG THAT MADE THIS NECESSARY: route paths are TEMPLATES —
    `/session/{session_id}` — so a string comparison against `/session/abc123`
    never matched, and every templated route was treated as undeclared and
    refused. The symptom was every session route returning 401 with a correct
    cookie and a correct dependency.
    """
    for route in app.routes:
        match, _ = route.matches(scope)
        if match is not Match.NONE:
            return route
    return None


@app.middleware("http")
async def _security_headers(request, call_next):
    """Headers that cost nothing and remove whole categories of mistake.

    `nosniff` stops a browser second-guessing a content type — the trick that
    turns a JSON endpoint into a script include. `DENY` on framing removes
    clickjacking outright; nothing here is meant to be embedded. `no-referrer`
    keeps session ids out of the Referer header on any outbound link, which is
    the quiet way URLs leak to third parties.

    A Content-Security-Policy is deliberately NOT set here: this app serves an
    API, and its pages come from Next, which owns their policy. A CSP declared
    in two places is one that disagrees with itself.
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


@app.middleware("http")
async def _refuse_undeclared_routes(request, call_next):
    """Refuse any route that neither declares auth nor is deliberately public.

    OPTIONS is exempt: a CORS preflight carries no credential by definition, and
    401-ing it makes the browser report the real request as an opaque CORS
    failure — the least informative error in web development.

    An unmatched path falls through to the router, which answers 404. Refusing it
    here would turn "no such endpoint" into "not authenticated", which is both
    wrong and confusing.
    """
    if request.method == "OPTIONS" or request.url.path.startswith("/auth/"):
        return await call_next(request)

    route = _route_for(request.scope)
    if route is None or getattr(route, "path", None) in PUBLIC_PATHS:
        return await call_next(request)

    dependant = getattr(route, "dependant", None)
    if dependant is not None and _declares_auth(dependant):
        return await call_next(request)

    return JSONResponse(status_code=401, content={"detail": "not_authenticated"})


# THE GOAL INTERVIEW LIVES IN A TABLE NOW (M7, `backend/auth/drafts.py`).
#
# It used to be a module-level dict capped at 64 and shared by everybody, and
# all three of those were wrong: it died with the process, the cap was global so
# concurrent learners evicted each other, and it was unowned so anybody holding
# an id could drive somebody else's interview.
#
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


class BackRequest(BaseModel):
    session_id: str


# The question being returned to, plus the answer already given for it, so the
# client can put the user back exactly where they were rather than in front of
# an empty field.
class BackResponse(BaseModel):
    question: QuestionOut
    answer: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

class RepoCheckRequest(BaseModel):
    repo_url: str


@app.get("/health")
def health() -> dict:
    """Liveness. Deliberately public, and deliberately says nothing.

    No version, no database status, no session count — a health endpoint that
    reports internals is a reconnaissance endpoint. "I am up" is the entire
    contract, and it is the only thing a load balancer or a restart script needs.
    """
    return {"status": "ok"}


@app.post("/repo/check")
def repo_check(
    body: RepoCheckRequest, user: CurrentUser = Depends(current_user)
) -> dict:
    # Catches an unclonable URL before the user answers five questions, rather
    # than surfacing it as a pipeline failure minutes later.
    #
    # `check_repo_reachable` now validates the URL against the scheme/host
    # allow-list BEFORE it reaches git, so a URL pointing anywhere but GitHub is
    # refused without an outbound request being made. That matters here more than
    # anywhere else in the API: this endpoint's entire job is to make the server
    # fetch a URL a caller supplied, which is a server-side request forgery
    # primitive unless something bounds where it may point.
    reason = check_repo_reachable(body.repo_url)
    return {"ok": reason is None, "reason": reason}


@app.post("/goal/start", response_model=StartResponse)
def goal_start(
    body: StartRequest, user: CurrentUser = Depends(current_user)
) -> StartResponse:
    session = drafts.create(user.user_id, body.repo_url, SESSIONS_DB_PATH)
    first_q = CORE_QUESTIONS[0]
    index, total = question_progress(session)
    return StartResponse(
        session_id=session.session_id,
        question=QuestionOut(
            text=first_q.text, options=first_q.options, index=index, total=total
        ),
    )


@app.post("/goal/answer", response_model=AnswerResponse)
def goal_answer(
    body: AnswerRequest, user: CurrentUser = Depends(current_user)
) -> AnswerResponse:
    session = drafts.load(body.session_id, user.user_id, SESSIONS_DB_PATH)
    if session is None:
        # 404 for "not yours" as well as "not there" — a draft id must not be
        # usable to discover that somebody else is mid-interview.
        raise HTTPException(status_code=404, detail="session_not_found")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    try:
        next_q, goal_output = process_answer(session, body.answer, client=client)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    drafts.save(session, user.user_id, SESSIONS_DB_PATH)

    if goal_output is not None:
        # The session stays: the client shows these answers back for confirmation,
        # and /goal/back has to keep working from that review step.
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


@app.post("/goal/back", response_model=BackResponse)
def goal_back(
    body: BackRequest, user: CurrentUser = Depends(current_user)
) -> BackResponse:
    session = drafts.load(body.session_id, user.user_id, SESSIONS_DB_PATH)
    if session is None:
        raise HTTPException(status_code=404, detail="session_not_found")

    stepped = step_back(session)
    if stepped is None:
        # The client disables its own Back control on question one; this is the
        # race, not the normal path.
        raise HTTPException(status_code=400, detail="at_first_question")

    drafts.save(session, user.user_id, SESSIONS_DB_PATH)
    question, previous = stepped
    index, total = question_progress(session)
    return BackResponse(
        question=QuestionOut(
            text=question.text,
            options=question.options,
            index=index,
            total=total,
        ),
        answer=previous,
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
def onboard(
    body: OnboardRequest, user: CurrentUser = Depends(current_user)
) -> OnboardResponse:
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
    # `force_new` is GONE (M3). It existed to override `_try_resume`, which
    # scanned every session in the database for a matching (repo_url, goal) and
    # returned someone else's. With that deleted, creation always creates and
    # there is nothing to force past. Accepted-and-ignored rather than rejected,
    # so an un-updated client keeps working instead of 422-ing on a field that
    # no longer means anything.
    force_new: bool = False
    # A client-invented id it can poll GET /session/progress/{id} with while this
    # request is still in flight. Optional: without one the run reports nothing
    # and behaves exactly as before.
    progress_id: str | None = None


class AdvanceRequest(BaseModel):
    signal: str = "next"
    node_id: str | None = None  # if provided, advance from this node instead of current


class RespondRequest(BaseModel):
    response: str
    node_id: str | None = None  # if provided, grade this node instead of current
    # WHICH QUESTION this answers:
    #   "assessment"   the lesson's own prompt
    #   "verification" a fresh question about one gap, from POST /verify
    #   "reassessment" a fresh question about the OBJECTIVE, from POST /reassess
    #
    # The third is graded as an ORDINARY ASSESSMENT — it is an answer to the
    # objective, so it moves `understanding_state` exactly as the first attempt
    # did. It is a distinct request kind only so the endpoint knows which pending
    # question is being answered and can record the right `question_source`; it is
    # NOT a third `history` attempt kind, and pooling it with assessments is
    # correct rather than a shortcut.
    #
    # Defaulted, so every existing client keeps working (§18.10).
    kind: str = history.ASSESSMENT


class WaiveRequest(BaseModel):
    # Omit to waive every open blocking gap on the node; supply one to waive it
    # alone. Two shapes rather than two endpoints, because "stop asking me about
    # this" is one intent at two scopes (§18.16.2).
    gap_id: str | None = None
    node_id: str | None = None


def _gaps_payload(node) -> list[dict]:
    """The node's gaps, for the learner to see — SETTLED ONES INCLUDED.

    §18.10 calls this "the product's most honest surface: it tells the learner
    what they still do not know, by name". It used to send open gaps only, and
    that made the surface honest about the debt and silent about the repayment:
    a gap the learner CLOSED vanished from the wire the moment it closed, so the
    one trace of the work was an ephemeral feedback card. A ledger that deletes
    the settled rows cannot show progress, only debt.

    So `status` decides how a gap renders, not whether it exists. Every consumer
    filters for itself — `is_open` here would take the choice away from all of
    them, and the two that want open-only (the stop counter, the check-available
    test) say so in one expression.

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
            "opened_at": gap.opened_at,
            "closed_at": gap.closed_at,
        }
        for gap in node.gaps
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


def _load_session_or_404(session_id: str, user_id: str):
    """A session the caller owns, or 404.

    Retained for the handful of places that need a graph part-way through a
    handler rather than as a dependency. It takes the owner explicitly for the
    same reason `store.load_graph` does: there is no way to ask for a session
    without saying whose it is.
    """
    graph = learning_store.load_graph(session_id, user_id, SESSIONS_DB_PATH)
    if graph is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    return graph


def _render_current_lesson(graph, client, owner: str) -> dict:
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
    learning_store.save_graph(graph, SESSIONS_DB_PATH, user_id=owner)
    if state.current_lesson is not None:
        # THE ORIGINAL LESSON, recorded once (session-reset.md §4.3).
        #
        # Here rather than inside Teaching, and only on the success path, for two
        # reasons that are the same reason: this is where "the render worked" is
        # known. The fallback below must NOT be recorded — a Teaching outage would
        # otherwise seal "this lesson could not be generated" into the plan
        # permanently, and every later `Start over` would restore it.
        #
        # A no-op for every subsequent render of the same stop, and for a remedial
        # node, which has no plan row to update. See `record_plan_lesson`.
        learning_store.record_plan_lesson(
            graph.session_id,
            graph.current_node_id,
            state.current_lesson,
            SESSIONS_DB_PATH,
        )
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
            learning_store.save_graph(graph, SESSIONS_DB_PATH, user_id=owner)
        return fallback
    return state.current_lesson


# ── one generation at a time, per learner ────────────────────────────────────
#
# Planning holds a threadpool worker for two to four minutes and spends real
# money. Without a cap, a learner who double-clicks Start pays twice and gets two
# sessions; with several learners, a handful of clicks exhausts the pool and the
# app stops answering anything at all.
#
# Per-user rather than global, because one person's impatience must not block
# somebody else's first session. The global semaphore below is the second bound.
_generating: set[str] = set()
_generating_lock = threading.Lock()

# How many pipelines may run at once across everybody. Chosen against what the
# resource actually is — Starlette's threadpool, and the Anthropic bill — rather
# than against CPU.
_GLOBAL_GENERATION_LIMIT = threading.Semaphore(3)


@app.post("/session/start", status_code=202)
def session_start(
    body: SessionStartRequest,
    background: BackgroundTasks,
    user: CurrentUser = Depends(current_user),
) -> dict:
    """Start planning a session. Returns 202 with the id, immediately.

    ## Why this returns before the work is done (multi-user.md §10.3)

    Planning takes two to four minutes. This used to block for all of it and
    return the id at the END — so closing the tab meant the pipeline still
    finished, the graph was still written, and the learner had no way to find
    it. The session existed and was unreachable.

    Now the row is reserved first, `status = 'generating'`, and the id comes
    back at once. The dashboard shows it working; closing the tab loses nothing;
    a restart mid-plan leaves a row that the startup sweep marks `failed` rather
    than one that spins forever.

    It also stops being the shape that breaks behind the Next rewrite (D-2),
    where a four-minute proxied POST is exactly what a dev server times out.

    `_try_resume` is not coming back: creation always creates (M3).
    """
    with _generating_lock:
        if user.user_id in _generating:
            # Not an error worth dressing up: they clicked twice, or left a tab
            # open. The one in flight is the answer.
            raise HTTPException(status_code=409, detail="generation_already_running")
        _generating.add(user.user_id)

    session_id = uuid.uuid4().hex
    title = _title_from_goal(body.goal, body.repo_url)
    try:
        learning_store.create_pending_session(
            session_id, user.user_id, body.repo_url, body.goal, title,
            SESSIONS_DB_PATH,
        )
    except Exception:
        with _generating_lock:
            _generating.discard(user.user_id)
        raise

    pid = body.progress_id or session_id
    pipeline_progress.begin(pid)
    background.add_task(
        _generate_session, session_id, user.user_id, body, pid
    )
    return {
        "session_id": session_id,
        "status": "generating",
        "progress_id": pid,
        "resumed": False,
        "errors": [],
    }


def _title_from_goal(goal: dict, repo_url: str) -> str:
    """A name for the card before there is anything else to name it after."""
    for key in ("focus_area", "primary_goal"):
        value = (goal.get(key) or "").strip()
        if value:
            title = value[0].upper() + value[1:]
            return title if len(title) <= 60 else title[:57].rstrip() + "…"
    try:
        return "/".join(parse_repo_url(repo_url))
    except ValueError:
        return "Learning session"


def _generate_session(
    session_id: str, owner: str, body: SessionStartRequest, pid: str
) -> None:
    """Plan the session, in the background. Never raises into the caller.

    The one thing this must always do is LEAVE THE ROW IN A TERMINAL STATE.
    A pipeline that fails and leaves `generating` behind is a card that spins
    forever, and the learner cannot tell whether to wait or retry.
    """
    acquired = _GLOBAL_GENERATION_LIMIT.acquire(timeout=900)
    try:
        if not acquired:
            learning_store.set_session_status(session_id, "failed", SESSIONS_DB_PATH)
            logger.warning("generation queue full: session=%s", session_id)
            return
        client = _new_client()
        state = run_pipeline(body.repo_url, body.goal, client=client, progress_id=pid)
        if state.graph is None:
            learning_store.set_session_status(session_id, "failed", SESSIONS_DB_PATH)
            logger.warning("planning produced no graph: session=%s errors=%s",
                           session_id, state.errors)
            return

        # The planner minted its own id; the row already exists under the one the
        # client was handed. Reconciling here rather than teaching the planner
        # about reserved ids keeps the engine ignorant of the account layer (I9).
        state.graph.session_id = session_id
        learning_store.create_session(state.graph, SESSIONS_DB_PATH, user_id=owner)
        learning_store.set_session_status(session_id, "active", SESSIONS_DB_PATH)

        if state.investigation:
            try:
                dossier_store.save_investigation(
                    session_id, get_commit_sha(state.repo_path),
                    state.investigation, SESSIONS_DB_PATH,
                )
            except Exception as e:
                logger.warning("dossier persistence failed (non-fatal): %s", e)
    except Exception as exc:                       # noqa: BLE001
        logger.exception("generation failed: session=%s", session_id)
        try:
            learning_store.set_session_status(session_id, "failed", SESSIONS_DB_PATH)
        except Exception:
            logger.error("could not mark session %s failed: %s", session_id, exc)
    finally:
        if acquired:
            _GLOBAL_GENERATION_LIMIT.release()
        pipeline_progress.finish(pid)
        with _generating_lock:
            _generating.discard(owner)


@app.get("/session/progress/{progress_id}")
def session_progress(
    progress_id: str, user: CurrentUser = Depends(current_user)
) -> dict:
    """What the /session/start call using this id is doing right now.

    Polled on its own request while that POST blocks — FastAPI serves sync
    endpoints from a threadpool, so this is answered while the pipeline works.
    404 means the id was never registered (or has been evicted): the client
    treats that as "no news", never as a failure, because the POST's own
    response is the only authority on whether the run worked.
    """
    snapshot = pipeline_progress.snapshot(progress_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="progress_not_found")
    return snapshot


@app.get("/sessions")
def list_sessions(
    user: CurrentUser = Depends(current_user),
    repo_url: str | None = None,
    include_archived: bool = False,
) -> dict:
    """The CALLER'S sessions, newest activity first.

    This took a required `repo_url` and returned every session on that
    repository belonging to ANYONE (multi-user.md §2 P2) — with 91 sessions in
    the live database, one request returned the whole corpus with full goal
    objects. It is now scoped by owner in SQL, and `repo_url` is an optional
    filter rather than the key.

    Loads no graphs: the dashboard lists everything at once, and reading 900+
    node rows to show three numbers per card is what the cached progress columns
    exist to avoid. Those are NULL until M4 fills them, and a caller must read
    that as "not computed" rather than as zero.
    """
    summaries = learning_store.list_sessions_for_user(
        user.user_id, SESSIONS_DB_PATH, include_archived=include_archived
    )
    if repo_url:
        summaries = [s for s in summaries if s["repo_url"] == repo_url]
    return {"sessions": summaries}


class SessionPatch(BaseModel):
    """What a learner may change about a session from the dashboard.

    Not the goal, not the repository, not the graph. Renaming and archiving are
    the two things that are about the CARD rather than about the learning, and
    everything else on a session is either the learner's own work or the
    planner's output.
    """
    title: str | None = None
    archived: bool | None = None


@app.get("/sessions/{session_id}")
def session_summary(
    session_id: str, user: CurrentUser = Depends(current_user)
) -> dict:
    """One dashboard row, without loading the graph.

    `GET /session/{id}` returns the whole graph — every node, every attempt —
    which is what the workspace needs and far more than a card does. This is the
    cheap read for "did that session finish generating yet".
    """
    summary = learning_store.get_session_summary(
        session_id, user.user_id, SESSIONS_DB_PATH
    )
    if summary is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    return summary


@app.patch("/sessions/{session_id}")
def session_patch(
    session_id: str, body: SessionPatch, user: CurrentUser = Depends(current_user)
) -> dict:
    """Rename or archive. Owner-scoped in the UPDATE, not by loading first."""
    changed = learning_store.update_session(
        session_id, user.user_id, SESSIONS_DB_PATH,
        title=body.title, archived=body.archived,
    )
    if not changed:
        raise HTTPException(status_code=404, detail="session_not_found")
    return learning_store.get_session_summary(
        session_id, user.user_id, SESSIONS_DB_PATH
    ) or {}


@app.delete("/sessions/{session_id}", status_code=204)
def session_delete(
    session_id: str, user: CurrentUser = Depends(current_user)
) -> Response:
    """Delete a session and everything scoped to it. Irreversible.

    `nodes`, `edges`, `plan_nodes` and `plan_edges` cascade on the foreign key.
    `investigation` does NOT — it has no FK to `sessions` (`dossier_store.py`) —
    so `delete_session` removes it explicitly. Without that, every deleted
    session left a full exploration payload behind, keyed to an id nothing would
    ever ask for again.

    Archiving is the reversible option and is what the dashboard offers first;
    this is for a learner who means it.
    """
    if not learning_store.delete_session(session_id, user.user_id, SESSIONS_DB_PATH):
        raise HTTPException(status_code=404, detail="session_not_found")
    logger.info("session deleted: session=%s by user=%s", session_id, user.user_id)
    return Response(status_code=204)


@app.get("/session/{session_id}")
def session_get(session_id: str, user: CurrentUser = Depends(current_user)) -> dict:
    graph = _load_session_or_404(session_id, user.user_id)
    return graph.to_dict()


@app.post("/session/{session_id}/reset")
def session_reset(session_id: str, user: CurrentUser = Depends(current_user)) -> dict:
    """Start over: the same learning path, restored, with none of the learner's work.

    What this endpoint deliberately does NOT do — each one was what `Start over`
    did before, and each is why it took two to four minutes and came back with a
    different curriculum:

      - no pipeline run, no clone, no model call of any kind;
      - no new session id, so the URL, the Dossier and the briefing all survive;
      - nothing derived from the learner's own history.

    It is a restore from the snapshot M1 persisted, so it is deterministic: the
    same session reset twice yields the same graph.

    409 rather than 404 when the plan is missing: the session exists and was
    found, and the reason this cannot proceed is a property of that session
    (written before schema v3 — session-reset.md D8), not a bad URL. No
    reconstruction is attempted, by design.

    Returns the same graph shape as `GET /session/{id}` so the client can swap it
    in without a second fetch, plus what was discarded — which is the honest thing
    to show after an irreversible action.
    """
    graph = _load_session_or_404(session_id, user.user_id)
    plan = learning_store.load_plan(session_id, user.user_id, SESSIONS_DB_PATH)
    if plan is None:
        raise HTTPException(status_code=409, detail="no_plan_snapshot")

    summary = reset_to_plan(graph, plan)
    learning_store.save_graph(graph, SESSIONS_DB_PATH, user_id=user.user_id)
    logger.info(
        "session reset: session=%s discarded=%s", session_id, summary.to_dict()
    )
    return {
        "session_id": session_id,
        "graph": graph.to_dict(),
        "discarded": summary.to_dict(),
    }


@app.get("/session/{session_id}/welcome")
def session_welcome(session_id: str, user: CurrentUser = Depends(current_user)) -> dict:
    """The welcome page's briefing: what this repository is, for this learner.

    Written once and cached on the session. The profile half of that page needs
    no endpoint — it is `graph.goal`, which the session payload already carries.

    The survey is READ, never produced here: it is keyed by (repo, commit) in
    `survey_store`, so a session whose commit has since been re-cloned at another
    revision simply finds nothing and gets a README-only briefing rather than
    prose about code that is no longer there.
    """
    graph = _load_session_or_404(session_id, user.user_id)
    if graph.briefing is not None:
        return {"briefing": graph.briefing}

    survey = None
    repo_path = None
    try:
        repo_path = clone_repo(graph.repo_url)
        owner, repo = parse_repo_url(graph.repo_url)
        survey = survey_store.load_survey(
            f"{owner}/{repo}",
            get_commit_sha(repo_path),
            db_path=SESSIONS_DB_PATH,
        )
    except Exception as e:
        # A missing survey costs the architecture account, not the page: the
        # README and the profile are still there to write from.
        logger.warning("welcome: survey unavailable for %s: %s", session_id, e)

    briefing = build_briefing(
        repo_url=graph.repo_url,
        goal=graph.goal,
        survey=survey,
        doc_context=graph.doc_context,
        repo_path=repo_path,
        client=_new_client(),
    )
    graph.briefing = briefing
    learning_store.save_graph(graph, SESSIONS_DB_PATH, user_id=user.user_id)
    return {"briefing": briefing}


@app.get("/session/{session_id}/lesson")
def session_lesson(session_id: str, user: CurrentUser = Depends(current_user)) -> dict:
    graph = _load_session_or_404(session_id, user.user_id)
    if graph.current_node_id is None:
        raise HTTPException(status_code=409, detail="session_has_no_current_node")

    _render_current_lesson(graph, _new_client(), user.user_id)
    node = graph.nodes[graph.current_node_id]

    return {
        "node_id": graph.current_node_id,
        "lesson": node.cached_lesson,
        # WHAT TO DO HERE, on the one call every arrival and every reload makes.
        # Without it the offer existed only in a grading reply, so a refresh lost
        # it — and "the learner refreshed" is not a decision about their
        # understanding, so it must not change what is on offer.
        "retry": retry_model.to_wire(node),
        # An outstanding question, so a reload puts the learner back in front of
        # it rather than in front of the composer for a prompt that is spent.
        # Both are `{question, ...}` and shipped without any answer.
        "pending": _pending_question(node),
    }


def _pending_question(node) -> dict | None:
    """The question this stop is waiting on, if any, with which kind it is.

    ONE key rather than two, because the client's job is the same either way —
    show this question, post the answer back with this `kind` — and a client that
    had to check two fields to find one question would eventually check only one.
    """
    state = node.gap_state
    if state.pending_verification:
        return {
            "kind": history.VERIFICATION,
            "question": state.pending_verification.get("question", ""),
        }
    if state.pending_reassessment:
        return {
            "kind": history.SOURCE_REASSESSMENT,
            "question": state.pending_reassessment.get("question", ""),
        }
    return None


@app.post("/session/{session_id}/advance")
def session_advance(session_id: str, body: AdvanceRequest, user: CurrentUser = Depends(current_user)) -> dict:
    # "next" moves along the path; "skip" marks the node skipped then advances.
    # Other signals (deeper / simpler) are deferred (phase3.md Part 6).
    if body.signal not in ("next", "skip"):
        raise HTTPException(
            status_code=400,
            detail=f"unsupported signal {body.signal!r}; supported: 'next', 'skip'",
        )

    graph = _load_session_or_404(session_id, user.user_id)
    current = body.node_id or graph.current_node_id
    if current is None:
        raise HTTPException(status_code=409, detail="session_has_no_current_node")
    if current not in graph.nodes:
        raise HTTPException(status_code=404, detail="node_not_found")
    graph.set_current(current)
    # Walking on IS rejoining the route, so whatever brought the learner to this
    # stop stops being news. Cleared for BOTH signals and before either branch:
    # skipping forward is still moving along the path, and a notice that survived
    # an advance would keep claiming they are off-route from a stop they left.
    graph.clear_arrival()

    if body.signal == "skip":
        client = _new_client()
        state = OnboardState(repo_url=graph.repo_url, goal=graph.goal, client=client)
        state.graph = graph
        mutate_graph(state, "skip")
        learning_store.save_graph(graph, SESSIONS_DB_PATH, user_id=user.user_id)
        nxt = graph.current_node_id if graph.current_node_id != current else None
        if nxt is None or nxt == current:
            return {"done": True}
        lesson = _render_current_lesson(graph, client, user.user_id)
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
        learning_store.save_graph(graph, SESSIONS_DB_PATH, user_id=user.user_id)
        return {"done": True}

    graph.set_current(nxt)
    client = _new_client()
    lesson = _render_current_lesson(graph, client, user.user_id)  # also persists
    return {"done": False, "node_id": nxt, "lesson": lesson}


def _respond_to_verification(
    graph, state: OnboardState, current: str, body: RespondRequest, client,
    owner: str,
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

    # Snapshot before grading: `grade_verification` clears the pending question.
    asked_verification = str(
        (node.gap_state.pending_verification or {}).get("question") or ""
    )
    before_gaps = {g.id for g in node.gaps}
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
        # THE QUESTION, kept (M1). `grade_verification` clears
        # `pending_verification` whatever the outcome — the question is spent once
        # asked, and re-showing it would be the "Try again" defect §18.7 removed —
        # so before this it existed NOWHERE afterwards. Read from the snapshot
        # taken above rather than from the node, which has already been cleared.
        question=asked_verification,
        question_source=history.SOURCE_VERIFICATION,
    )
    # The verification's own envelope, on the verification attempt. `action` is
    # `none` because verification produces no adaptation — the outcome is a gap
    # closing or not closing, and saying "none" is how M2 distinguishes "the
    # system deliberately did nothing" from "we have no record".
    #
    # `record_response` files against the latest ASSESSMENT, so it is not used
    # here: this record belongs to the verification attempt itself.
    opened = [g.id for g in node.gaps if g.id not in before_gaps]
    node.attempts[-1][history.RESPONSE] = history.new_response(
        "none",
        **({"gaps_resolved": result["resolved"]} if result.get("resolved") else {}),
        **({"gaps_opened": opened} if opened else {}),
    )
    learning_store.save_graph(graph, SESSIONS_DB_PATH, user_id=owner)

    return {
        "kind": history.VERIFICATION,
        "resolved": result.get("resolved", []),
        "unresolved": result.get("unresolved", []),
        # Same key, same meaning, on both replies — a check can open a gap too.
        "gaps_opened": opened,
        "rationale": result.get("rationale"),
        "gaps": _gaps_payload(node),
        "understanding_state": understanding_of(node),
        "retry": retry_model.to_wire(node),
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
def session_verify(session_id: str, body: dict | None = None, user: CurrentUser = Depends(current_user)) -> dict:
    """Generate a FRESH question testing whether a gap has actually closed.

    Replaces "Try again", which re-showed the answered question after `reveal`
    had already given away the reasoning — a memory check (§18.7).

    Aimed at ONE gap. Asking about three at once would let an answer address one
    and appear to have addressed all three, which is the partial answer that
    looks like completion.

    WHICH one depends on who asked. Omit `gap_id` and the system chooses: the
    highest-precedence open blocking gap that still has verification budget.
    Supply `gap_id` and the learner chose, from the gap list, by name.

    That distinction is also what decides the attempt cap. `VERIFICATION_ATTEMPT_CAP`
    exists so the SYSTEM stops proposing for a gap it has already asked about
    twice (gaps.py, §18.16.1) — it was never a limit on the learner's own
    appetite. A learner who reads "you still believe X" and asks to be tested on
    it again is performing a different act than the system nagging, so an
    exhausted gap is still reachable by name. It remains absent from the active
    set, so nothing about the system's own offering changes.
    """
    body = body or {}
    node_id = body.get("node_id")
    gap_id = body.get("gap_id")
    graph = _load_session_or_404(session_id, user.user_id)
    current = node_id or graph.current_node_id
    if current is None or current not in graph.nodes:
        raise HTTPException(status_code=404, detail="node_not_found")
    node = graph.nodes[current]

    if gap_id:
        # By name, so precedence and the cap are both bypassed — but not
        # `is_open`. A verified gap has nothing left to demonstrate and a waived
        # one is what they asked to stop hearing about; re-asking either would
        # spend a call to re-close something already closed.
        target = next((g for g in node.gaps if g.id == gap_id and g.is_open), None)
        if target is None:
            raise HTTPException(status_code=404, detail="gap_not_found")
    else:
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
    learning_store.save_graph(graph, SESSIONS_DB_PATH, user_id=user.user_id)
    return {
        "node_id": current,
        # No `reveal` and no expected answer — excluded by design, not omitted for
        # brevity. Shipping the answer beside the question is what made re-asking
        # meaningless in the first place.
        "question": stored["question"],
        "targets": stored["targets"],
        "gaps": _gaps_payload(node),
        "retry": retry_model.to_wire(node),
        "errors": state.errors,
    }


@app.post("/session/{session_id}/reassess")
def session_reassess(session_id: str, body: dict | None = None, user: CurrentUser = Depends(current_user)) -> dict:
    """Generate a FRESH question about the OBJECTIVE, after a shortfall.

    The sibling of `/verify`, one level up, and the route for the shortfall that
    named no gap — which is most of them: 27 of the 34 real unmet stops in the
    stored sessions have no open blocking gap, so `/verify` has nothing to aim at
    and there was no way back to `understood` at all.

    Aimed at the objective, generated against the questions already asked and the
    recorded shortfall, and shipping **no answer** — see `teaching/reassess.py`
    for why re-asking anything from `cached_lesson` cannot work.

    Charged on ISSUE, like `pending_verification`: an unanswered question has
    still been asked, and a learner who could refresh their way to fresh
    questions would turn the measure from mastery into persistence.
    """
    body = body or {}
    graph = _load_session_or_404(session_id, user.user_id)
    current = body.get("node_id") or graph.current_node_id
    if current is None or current not in graph.nodes:
        raise HTTPException(status_code=404, detail="node_not_found")
    node = graph.nodes[current]

    # The dispatch decides; this endpoint does not re-derive it. Called by name it
    # still has to obey the budget — unlike `/verify`, where naming a gap
    # deliberately bypasses the cap because asking about a named misconception is
    # a different act from being nagged. There is no equivalent here: the target
    # is always the same objective, so a second door onto it would just be the cap
    # with extra steps.
    if retry_model.reassessments_left(node) <= 0:
        raise HTTPException(status_code=409, detail="reassessment_budget_spent")
    if node.gap_state.pending_reassessment or node.gap_state.pending_verification:
        raise HTTPException(status_code=409, detail="question_already_pending")
    if understanding_of(node) == "understood":
        raise HTTPException(status_code=409, detail="objective_already_met")

    client = _new_client()
    state = OnboardState(repo_url=graph.repo_url, goal=graph.goal, client=client)
    state.graph = graph
    try:
        source = _node_source(graph, node)
    except Exception as exc:
        # §4.1.2. With no source the model invents the scenario, and this answer
        # is an ORDINARY ASSESSMENT — so failing an imaginary question would move
        # `understanding_state` on the strength of imaginary code.
        raise HTTPException(status_code=409, detail="source_unavailable") from exc

    prompt = teaching_reassess.reassess(state, node, source, client=client)
    if prompt is None:
        # Nothing is charged: a question we could not generate is not one the
        # learner spent.
        raise HTTPException(status_code=503, detail="reassessment_unavailable")

    stored = teaching_reassess.store(node, prompt)
    learning_store.save_graph(graph, SESSIONS_DB_PATH, user_id=user.user_id)
    return {
        "node_id": current,
        # No reveal and no expected answer — the whole point.
        "question": stored["question"],
        "retry": retry_model.to_wire(node),
        "errors": state.errors,
    }


@app.post("/session/{session_id}/waive")
def session_waive(session_id: str, body: WaiveRequest, user: CurrentUser = Depends(current_user)) -> dict:
    """Stop remediating — one gap, or every open blocking gap on the node.

    **Never evidence** (§18.16.2): waiving does not produce `verified`, so the
    node stays short of `understood` and `readiness()` stays honest. What it buys
    is that the system stops asking, and that the journey can still complete.

    Reversible by construction: the gaps are still on the node, and
    `POST /verify` will offer them again once they are re-opened, which is what
    "an offer to verify it now" on the completion screen rests on.
    """
    graph = _load_session_or_404(session_id, user.user_id)
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

    learning_store.save_graph(graph, SESSIONS_DB_PATH, user_id=user.user_id)
    return {
        "node_id": current,
        # NAMED, never a bare count: "what you chose not to check" is the most
        # useful thing the artifact can say (§18.16.3).
        "waived": waived,
        "gaps": _gaps_payload(node),
        "understanding_state": understanding_of(node),
        "retry": retry_model.to_wire(node),
        "readiness": graph.readiness(),
        "complete": graph.is_complete(),
    }


@app.post("/session/{session_id}/respond")
def session_respond(session_id: str, body: RespondRequest, user: CurrentUser = Depends(current_user)) -> dict:
    graph = _load_session_or_404(session_id, user.user_id)
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
        return _respond_to_verification(graph, state, current, body, client, user.user_id)

    # A RE-ASSESSMENT ANSWER IS AN ORDINARY ASSESSMENT, and everything below it
    # runs unchanged — the Grader marks it against the same objective, the verdict
    # moves `understanding_state`, and `decide_all` responds to it exactly as it
    # would to a first answer. That is the whole design: a second question about
    # the objective is not a special kind of evidence, it is more of the same kind.
    #
    # The only thing that differs is WHICH question it answered, and the pending
    # question is cleared here because it is now spent.
    reassessment = None
    # `SOURCE_REASSESSMENT`, deliberately — the client is naming WHICH QUESTION it
    # is answering, not claiming a third attempt kind. The attempt this produces is
    # an `ASSESSMENT`, because that is what it is evidence about.
    if body.kind == history.SOURCE_REASSESSMENT:
        reassessment = graph.nodes[current].gap_state.pending_reassessment
        if not reassessment:
            raise HTTPException(status_code=409, detail="no_pending_reassessment")
        graph.nodes[current].gap_state.pending_reassessment = None

    # THE QUESTION THEY ANSWERED, captured before anything can replace it (M1).
    #
    # Read here rather than after grading for a reason that only bites on one
    # path: a `reteach` later in THIS request assigns `node.cached_lesson`
    # wholesale, so by the time the attempt is recorded the prompt the learner
    # actually saw is gone. Reading it late would file every re-taught answer
    # against the question that replaced the one it answered — the exact
    # misattribution this milestone exists to make impossible.
    #
    # `question_source` distinguishes the unit's ORIGINAL prompt from one a
    # previous re-teach installed. Both are assessments of the same objective and
    # they are not the same question: a re-taught prompt is built so it cannot be
    # answered while still holding the diagnosed misconception.
    if reassessment is not None:
        asked = str(reassessment.get("question") or "")
        asked_source = history.SOURCE_REASSESSMENT
    else:
        asked = (graph.nodes[current].cached_lesson or {}).get("prompt") or ""
        asked_source = (
            history.SOURCE_RETEACH
            if history.lesson_was_retaught(graph.nodes[current].attempts)
            else history.SOURCE_LESSON
        )

    # Which gaps this ANSWER opened, as a fact rather than a count. Taken as a
    # before/after delta because the Grader mints ids internally; asking it to
    # report them too would be a second source of the same truth.
    before_gaps = {g.id for g in graph.nodes[current].gaps}
    run_grader(state, body.response, client=client)
    opened = [g.id for g in graph.nodes[current].gaps if g.id not in before_gaps]
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
        question=asked,
        question_source=asked_source,
        # THE CONDITIONS THIS ANSWER WAS GIVEN UNDER (tutor.md §6.4).
        #
        # Read here, at the same point `question` and `question_source` are, and
        # for the same reason: a `reteach` later in this request calls
        # `new_question()`, which clears the counters — so reading them late would
        # file every re-taught answer as unassisted.
        #
        # It does NOT change the grade. Everything below this line runs exactly as
        # it did: the Grader has already marked the answer, `decide_all` responds
        # to the verdict, and nothing consults this. What reads it is `retry.py`,
        # afterwards, to decide what to OFFER.
        #
        # `None` when the Tutor is off, so no attempt is recorded as unassisted on
        # the strength of a feature that was not running.
        assistance=(
            history.new_assistance(
                graph.nodes[current].tutor_state.hints_used,
                graph.nodes[current].tutor_state.revealed,
            )
            if tutor_enabled()
            else None
        ),
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
    # `remediation_rounds` is passed HERE, on the path that spends it. `/verify`
    # always passed it; this call site never did, so the node-level cap was
    # unreachable from the only place that could reach it — the second half of
    # F100, and the half that incrementing the counter alone does not fix.
    plan = adaptation.decide_all(
        classification, list(node.gaps), gap_kind,
        remediation_rounds=node.gap_state.remediation_rounds,
    )
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

    # ── the node-level remediation counter (F100) ─────────────────────────────
    #
    # `remediation_rounds` was declared, persisted, deserialized and read by
    # `decide_all`'s cap — and written by nothing, so `REMEDIATION_ROUND_CAP`
    # was dead and the per-node remediation loop was unbounded.
    #
    # A ROUND IS AN APPLIED REMEDIATION, whichever kind it was. Counting only
    # the structural ones would leave the loop unbounded in exactly the case
    # the cap exists for: `decide_all` picks the action from gap precedence, so
    # a node whose leading gap keeps earning `hint` could be hinted at forever
    # and never reach a cap that only counted warm-ups. What bounds the loop is
    # the number of times the system has responded to this node with help.
    #
    # Applied, not merely chosen: a `prerequisite` the Mutator declined and a
    # re-teach that raised both leave the learner with nothing new, and charging
    # a round for them would spend the budget on the system's own failures.
    #
    # Verifications are NOT counted here. That is the per-GAP budget, and
    # `Gap.record_failed_verification` already keeps it (§18.16.1, LQ10).
    remediated = (
        mutation.get("kind") == "prerequisite"
        or adapted.get("retaught") is True
        or bool(adapted.get("text"))
    )
    if remediated:
        node.gap_state.remediation_rounds += 1

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
        # The gap slots M2 reserved (§18.9). Carried in the SAME envelope rather
        # than in a parallel verification history, so "what this answer revealed"
        # and "what the system did about it" stay one record. Omitted when empty,
        # like every other detail key — absent means "none", not "unknown".
        **({"gaps_opened": opened} if opened else {}),
        **({"gaps_addressed": [g.id for g in plan.targets]} if plan.targets else {}),
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

    learning_store.save_graph(graph, SESSIONS_DB_PATH, user_id=user.user_id)

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
        # WHICH OF THEM THIS ANSWER OPENED. Already recorded on the attempt's
        # response envelope; it simply was not on the reply, so the one surface
        # that needs it — the ledger, deciding whether to open itself — had to
        # diff two payloads it happened to be holding. A client diff is a second
        # implementation of a fact the server already computed, and it is wrong
        # the first time a refresh lands between the two halves.
        #
        # ALWAYS PRESENT on this path, unlike the response envelope's key, which
        # is omitted when empty because absent-means-none is that record's
        # convention. Here an empty list is the answer, and a client that had to
        # tell "no gaps opened" from "this backend does not say" would end up
        # guessing on the commonest case.
        "gaps_opened": opened,
        # WHAT "ASK ME AGAIN" WOULD DO HERE, computed from the learning state
        # rather than reconstructed by the client from four partial flags. The
        # frontend renders this; it no longer decides it.
        "retry": retry_model.to_wire(graph.nodes[current]),
        "complete": graph.is_complete(),
    }


@app.post("/session/{session_id}/retry")
def session_retry(session_id: str, body: dict, user: CurrentUser = Depends(current_user)) -> dict:
    """Insert a prerequisite for the current node and load its lesson.
    Called when the user clicks 'Try again' after a wrong answer.
    """
    node_id = body.get("node_id")
    graph = _load_session_or_404(session_id, user.user_id)
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
        # A learner-requested warm-up is a remediation round too (F100). The
        # origin differs — they asked rather than being sent — but the budget is
        # the node's, not the policy's, so both paths spend from it. Charged
        # only when one was actually spliced: a decline costs nothing.
        graph.nodes[current].gap_state.remediation_rounds += 1
    learning_store.save_graph(graph, SESSIONS_DB_PATH, user_id=user.user_id)
    if graph.current_node_id == current:
        # No prerequisite was inserted (guard triggered) — just return current
        return {"current_node_id": current, "inserted": False}
    lesson = _render_current_lesson(graph, client, user.user_id)
    return {"current_node_id": graph.current_node_id, "inserted": True, "lesson": lesson}


class JumpRequest(BaseModel):
    node_id: str
    # WHY the learner moved. `study` is the ordinary case — they picked a stop off
    # the map or the rail and went to it. `resume` is the return offered by the
    # arrival notice, and it is separate because it is the opposite act: it
    # rejoins the route, so it clears the notice rather than raising another one.
    #
    # Defaulted rather than required: every existing caller sends only `node_id`,
    # and an ordinary jump is what they all mean.
    intent: str = history.JUMP_STUDY


@app.post("/session/{session_id}/jump")
def session_jump(session_id: str, body: JumpRequest, user: CurrentUser = Depends(current_user)) -> dict:
    """Move to a stop that is not the next one — and leave a record that it happened.

    Jumping stays UNCONDITIONAL. Dependencies are not enforced here and no stop is
    ever locked: the learner may study the codebase in whatever order they like,
    and `goal_readiness` already prices disorder in honestly (it is demonstrated
    coverage of the required set, so walking past every question reads 0%).

    What was missing was not a gate but a TRACE. This was the only navigation act
    in the system that left none — `/advance`'s skip stamps `user_override` and
    every scope change writes a journey event — so a session spent jumping around
    was, afterwards, indistinguishable from one spent walking the path. Two things
    are recorded, for two different readers:

      `journey_events`  the permanent record, read by the session log.
      `arrival`         the one live fact, read by the notice on the stop landed
                        on. Cleared by `/advance`, because walking on IS rejoining
                        the route.
    """
    if body.intent not in history.JUMP_INTENTS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported intent {body.intent!r}; supported: "
                   f"{', '.join(sorted(history.JUMP_INTENTS))}",
        )

    graph = _load_session_or_404(session_id, user.user_id)
    if body.node_id not in graph.nodes:
        raise HTTPException(status_code=404, detail="node_not_found")

    # Read BEFORE the move: this is the stop the learner is leaving, and it is
    # what makes "return to where you were" answerable.
    left = graph.current_node_id
    graph.set_current(body.node_id)

    # Recorded for both intents. A return is as much a navigation decision as a
    # departure, and a log that showed only departures would imply the learner
    # never came back.
    graph.record_journey_event(
        history.JUMPED,
        nodes=[body.node_id],
        from_node_id=left,
        intent=body.intent,
    )
    if body.intent == history.JUMP_RESUME:
        graph.clear_arrival()
    else:
        graph.record_arrival(
            body.node_id, kind=history.JUMPED, from_node_id=left
        )

    learning_store.save_graph(graph, SESSIONS_DB_PATH, user_id=user.user_id)
    return {"current_node_id": body.node_id, "arrival": graph.arrival}


class ScopeRequest(BaseModel):
    direction: str  # "shorter" | "deeper"


@app.post("/session/{session_id}/scope")
def session_scope(session_id: str, body: ScopeRequest, user: CurrentUser = Depends(current_user)) -> dict:
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

    graph = _load_session_or_404(session_id, user.user_id)
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
    learning_store.save_graph(graph, SESSIONS_DB_PATH, user_id=user.user_id)

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
def session_override(session_id: str, body: OverrideRequest, user: CurrentUser = Depends(current_user)) -> dict:
    # User-driven edits to their own understanding graph. Pure Python, no LLM.
    if body.action not in ("mark_understood", "mark_weak", "skip"):
        raise HTTPException(
            status_code=400, detail=f"unsupported action {body.action!r}"
        )
    graph = _load_session_or_404(session_id, user.user_id)
    node_id = body.node_id or graph.current_node_id
    if node_id is None or node_id not in graph.nodes:
        raise HTTPException(status_code=404, detail="node_not_found")

    graph.override(node_id, body.action)
    learning_store.save_graph(graph, SESSIONS_DB_PATH, user_id=user.user_id)
    node = graph.nodes[node_id]
    return {
        "node_id": node_id,
        "understanding_state": understanding_of(node),
        "visited": node.visited,
        "weak_spot": node.weak_spot,
    }


@app.get("/session/{session_id}/evidence/{node_id}")
def session_evidence(session_id: str, node_id: str, user: CurrentUser = Depends(current_user)) -> dict:
    """The evidence chain behind one node's understanding state (M3a.1).

    Its own endpoint rather than a slice of the session payload: the timeline
    carries full answer text and superseded lesson bodies, which would multiply
    the size of every `/session/{id}` poll for something read on demand when the
    learner opens one node.
    """
    graph = _load_session_or_404(session_id, user.user_id)
    if node_id not in graph.nodes:
        raise HTTPException(status_code=404, detail="node_not_found")
    return understanding.evidence(graph, node_id)


@app.get("/session/{session_id}/file")
def session_file(session_id: str, path: str, user: CurrentUser = Depends(current_user)) -> dict:
    graph = _load_session_or_404(session_id, user.user_id)
    repo_path = clone_repo(graph.repo_url)
    # Containment is decided by `resolve_within`, which resolves both sides and
    # compares path ANCESTRY. The check here used to be a string prefix, which
    # let a sibling directory whose name merely started the same way through —
    # see the note on `cloner.resolve_within`. The resolved path is then the one
    # that gets opened, so there is no window between checking one path and
    # reading another.
    full_path = resolve_within(repo_path, path)
    if full_path is None:
        raise HTTPException(status_code=400, detail="invalid_path")
    if not full_path.is_file():
        raise HTTPException(status_code=404, detail="file_not_found")
    with open(full_path, encoding="utf-8", errors="replace") as f:
        content = f.read()
    return {"path": path, "content": content}


# ── the Tutor (docs/planning/phases/tutor.md) ────────────────────────────────
#
# Five routes, one law:
#
#     A conversation turn is not evidence about the learner.
#
# The only writes any of them make are the transcript append and the per-node
# counters. No attempt, no gap, no grade, no understanding state, no readiness, no
# journey event, no graph mutation — and `tests/test_tutor_boundary.py` asserts
# both halves of that: the import boundary structurally, and the graph payload by
# comparing `to_dict()` before and after.
#
# Ownership follows the same four layers as every other session route:
# `Depends(current_user)` in the signature, `_load_session_or_404` naming the
# owner, 404 rather than 403, and the coverage test failing the build if either is
# forgotten.


class TutorAskRequest(BaseModel):
    question: str
    node_id: str | None = None


class TutorNodeRequest(BaseModel):
    node_id: str | None = None


class TutorPinRequest(BaseModel):
    turn_id: str
    pinned: bool = True


def _tutor_available() -> None:
    """404 while the flag is off — the route does not exist, rather than refusing.

    A 403 or a 501 would tell a caller the feature is there and withheld, which is
    a fact about our deployment that nobody outside it needs.
    """
    if not tutor_enabled():
        raise HTTPException(status_code=404, detail="not_found")


def _tutor_node(graph, node_id: str | None):
    """The stop a Tutor call is about. `None` only when the session has none."""
    target = node_id or graph.current_node_id
    if target is None:
        return None
    if target not in graph.nodes:
        raise HTTPException(status_code=404, detail="node_not_found")
    return graph.nodes[target]


def _tutor_citable(node) -> tuple:
    """The locations an answer may cite — every anchor the unit is grounded on.

    Built from `lesson_brief["anchors"]` when the unit has them (a flow crossing
    three files is citable in all three) and from the display anchor otherwise.
    The RANGES ARE OURS: the model names a file and a symbol, and these are what
    it is resolved against, so a line number it invented has nowhere to land.
    """
    stored = (node.lesson_brief or {}).get("anchors") or []
    citable = []
    for anchor in stored:
        try:
            citable.append(tutor_context.Citable(
                file=str(anchor["file"]),
                symbol=anchor.get("symbol"),
                line_start=int(anchor["line_start"]),
                line_end=int(anchor["line_end"]),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    if not citable:
        citable.append(tutor_context.Citable(
            file=node.code_anchor.file,
            symbol=node.code_anchor.symbol,
            line_start=node.code_anchor.line_start,
            line_end=node.code_anchor.line_end,
        ))
    return tuple(citable)


def _tutor_repo_inputs(graph, node) -> tutor_context.RepoInputs:
    """Everything that has to be read off a disk, read once.

    The fallback order is the project's — **Dossier, then Skeleton, then
    nothing** — and every step of it is non-fatal, exactly as it is in
    `teaching/agent.py::run`. The one thing that is NOT degraded silently is the
    source: when no anchor can be read, `source` stays None and the context says
    so, because a Tutor answering fluently about code it could not open is the
    failure the grounding rules exist to prevent.
    """
    from backend.agents.teaching.agent import _read_node_source
    from backend.repo import dossier_context, dossier_store, structure, survey_store
    from backend.repo.skeleton import build_skeleton

    if node is None:
        return tutor_context.RepoInputs()

    try:
        repo_path = clone_repo(graph.repo_url)
    except Exception as e:
        logger.warning("tutor: checkout unavailable for %s: %s", graph.session_id, e)
        return tutor_context.RepoInputs()

    source = None
    try:
        source = _read_node_source(repo_path, node)
    except Exception as e:
        # A unit whose every anchor is gone. Reported, then declared to the model
        # as "could not be read" rather than quietly omitted.
        logger.warning("tutor: no readable source for node %s: %s", node.id, e)

    skeleton = None
    try:
        skeleton = build_skeleton(repo_path)
    except Exception as e:
        logger.warning("tutor: skeleton unavailable (non-fatal): %s", e)

    system_context = ""
    if skeleton is not None:
        anchor = node.code_anchor
        try:
            stored = dossier_store.load_investigation(
                graph.session_id, get_commit_sha(repo_path), db_path=SESSIONS_DB_PATH
            )
            dossier = (stored or {}).get("dossier")
            if dossier:
                system_context = dossier_context.context_for_node(
                    skeleton, dossier, anchor.file, symbol=anchor.symbol,
                    line_start=anchor.line_start, line_end=anchor.line_end,
                ).as_prompt_section()
        except Exception as e:
            logger.warning("tutor: dossier context failed (non-fatal): %s", e)
        if not system_context:
            try:
                system_context = structure.neighbour_context(
                    skeleton, anchor.file, symbol=anchor.symbol,
                    line_start=anchor.line_start, line_end=anchor.line_end,
                )
            except Exception as e:
                logger.warning("tutor: structural context failed (non-fatal): %s", e)

    survey = None
    try:
        owner, repo = parse_repo_url(graph.repo_url)
        survey = survey_store.load_survey(
            f"{owner}/{repo}", get_commit_sha(repo_path), db_path=SESSIONS_DB_PATH
        )
    except Exception as e:
        logger.warning("tutor: survey unavailable (non-fatal): %s", e)

    return tutor_context.RepoInputs(
        source=source,
        system_context=system_context or "",
        survey=survey,
        citable=_tutor_citable(node),
    )


def _tutor_offers(graph, node) -> list[dict]:
    """Deterministic offers the SYSTEM makes, from the tier-2 signals (§5.2).

    Distinct from a model's `suggestion`, and deliberately computed rather than
    proposed: "they have asked four questions here" is a fact, where "they seem
    confused" is a judgement. Both end at the same place — a validated control the
    learner may press — but only one of them is allowed to be wrong about the
    learner.

    Never offered while a question is outstanding. Putting an exit in front of
    somebody who is mid-thought is the system telling them to give up.
    """
    if node is None or tutor_mode.mode_for(node).is_scaffold:
        return []
    signal = None
    if tutor_model.returning(node, is_settled(node)):
        signal = "returning"
    elif tutor_model.dwelling(node):
        signal = "dwelling"
    if signal is None:
        return []
    offer = tutor_suggest.validate(graph, node, {"kind": tutor_model.SUGGEST_REASSESS})
    return [{**offer.to_dict(), "signal": signal}] if offer else []


def _tutor_payload(graph, node, turn: dict | None = None) -> dict:
    """One shape for every Tutor response, so a client never has to branch.

    `mode` is recomputed from the graph on EVERY call rather than carried from the
    request. A client that told us which mode it was in would be a client that
    could ask for the answer key.
    """
    mode = tutor_mode.mode_for(node)
    payload = {
        "mode": mode.to_wire(),
        "remaining": tutor_model.remaining(graph.tutor),
        "cap": tutor_model.TUTOR_QUESTION_CAP,
        "node_id": node.id if node is not None else None,
        "offers": _tutor_offers(graph, node),
    }
    if turn is not None:
        payload["turn"] = turn
    return payload


def _tutor_spend_or_409(graph) -> None:
    if tutor_model.remaining(graph.tutor) <= 0:
        raise HTTPException(status_code=409, detail="tutor_limit_reached")


@app.get("/session/{session_id}/tutor")
def tutor_transcript(
    session_id: str, user: CurrentUser = Depends(current_user)
) -> dict:
    """The conversation, the mode, and the counters.

    Called on mount and after `/advance`, so a refresh restores the panel exactly
    — the same reason `/lesson` returns `retry` and `pending`. Reloading is not a
    decision about the learner's understanding, so it must not change what is on
    offer.

    The whole transcript, not a page of it: the cap is twenty turns, so the
    largest possible payload is small, and a panel that had to paginate to show a
    learner their own questions would be paginating for nobody.
    """
    _tutor_available()
    graph = _load_session_or_404(session_id, user.user_id)
    node = _tutor_node(graph, None)
    return {**_tutor_payload(graph, node), "turns": graph.tutor}


@app.post("/session/{session_id}/tutor/ask")
def tutor_ask(
    session_id: str, body: TutorAskRequest,
    user: CurrentUser = Depends(current_user),
) -> dict:
    """A question. Which agent answers it is decided here, never by the caller."""
    _tutor_available()
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question_empty")
    if len(question) > tutor_model.MAX_QUESTION_CHARS:
        raise HTTPException(status_code=400, detail="question_too_long")

    graph = _load_session_or_404(session_id, user.user_id)
    _tutor_spend_or_409(graph)
    node = _tutor_node(graph, body.node_id)
    mode = tutor_mode.mode_for(node)

    client = _new_client()
    errors: list[str] = []
    repo = _tutor_repo_inputs(graph, node)

    if mode.is_scaffold:
        built = tutor_context.build_scaffold_context(
            graph, node, mode.question, repo, graph.tutor,
            hint_level=node.tutor_state.hints_used,
        )
        result = tutor_scaffold.reply(question, built, client=client, errors=errors)
    else:
        built = tutor_context.build_explain_context(graph, node, repo, graph.tutor)
        result = tutor_explain.answer(question, built, client=client, errors=errors)

    # A FAILED CALL IS NOT A TURN.
    #
    # It is not stored, it does not count against the cap, and it does not appear
    # in the transcript — charging a learner's allowance for our own outage would
    # spend their budget on our mistakes, which is the rule `remediation_rounds`
    # already follows. The apology is returned so the panel can say something.
    if errors:
        logger.warning("tutor: call failed session=%s errors=%s", session_id, errors)
        return {**_tutor_payload(graph, node), "turn": None, "failed": True,
                "text": result["text"]}

    suggestion = tutor_suggest.validate(graph, node, result.get("suggestion"))
    turn = tutor_model.new_turn(
        node_id=node.id if node is not None else None,
        mode=mode.mode,
        question=question,
        answer=result["text"],
        scope=result["scope"],
        hint_level=node.tutor_state.hints_used if node is not None else 0,
        citations=result["citations"],
        suggestion=suggestion.to_dict() if suggestion else None,
        grounded=result["grounded"],
        usage=result["usage"],
    )
    graph.tutor.append(turn)
    if node is not None:
        node.tutor_state.turns += 1
    learning_store.save_graph(graph, SESSIONS_DB_PATH, user_id=user.user_id)
    return _tutor_payload(graph, node, turn)


@app.post("/session/{session_id}/tutor/hint")
def tutor_hint(
    session_id: str, body: TutorNodeRequest | None = None,
    user: CurrentUser = Depends(current_user),
) -> dict:
    """One rung of the Socratic ladder.

    409 `not_asking` in EXPLAIN: a hint for a question that is not outstanding is
    a client bug, not a learner action, and inventing one would mean scaffolding
    toward nothing.
    """
    _tutor_available()
    graph = _load_session_or_404(session_id, user.user_id)
    _tutor_spend_or_409(graph)
    node = _tutor_node(graph, (body.node_id if body else None))
    mode = tutor_mode.mode_for(node)
    if not mode.is_scaffold:
        raise HTTPException(status_code=409, detail="not_asking")
    if not mode.can_hint:
        raise HTTPException(status_code=409, detail="hint_ladder_spent")

    rung = node.tutor_state.hints_used + 1
    errors: list[str] = []
    built = tutor_context.build_scaffold_context(
        graph, node, mode.question, _tutor_repo_inputs(graph, node), graph.tutor,
        hint_level=rung,
    )
    result = tutor_scaffold.hint(built, rung, client=_new_client(), errors=errors)

    if errors:
        # THE RUNG IS SPENT ON SUCCESS ONLY. A hint that failed to generate leaves
        # the learner with nothing new, and charging them a rung for it would be
        # the budget paying for our outage.
        logger.warning("tutor hint failed: session=%s errors=%s", session_id, errors)
        return {**_tutor_payload(graph, node), "turn": None, "failed": True,
                "text": result["text"]}

    turn = tutor_model.new_turn(
        node_id=node.id,
        mode=mode.mode,
        question="",
        answer=result["text"],
        scope=result["scope"],
        hint_level=rung,
        citations=result["citations"],
        grounded=result["grounded"],
        usage=result["usage"],
    )
    graph.tutor.append(turn)
    node.tutor_state.hints_used = rung
    node.tutor_state.turns += 1
    learning_store.save_graph(graph, SESSIONS_DB_PATH, user_id=user.user_id)
    return _tutor_payload(graph, node, turn)


@app.post("/session/{session_id}/tutor/reveal")
def tutor_reveal(
    session_id: str, body: TutorNodeRequest | None = None,
    user: CurrentUser = Depends(current_user),
) -> dict:
    """Show the explanation, and spend the question (tutor.md §6.3).

    THE ONLY ENDPOINT THAT RETURNS A REVEAL EARLY, and deliberately a separate,
    explicit, logged act rather than a field on another response. The learner is
    choosing to step out of assessment and back into learning; that is legitimate,
    and it is theirs to make — the UI states the consequence on the control itself
    before this is ever called.

    What happens after is entirely the existing machinery: `prompt_is_unanswered`
    reads `revealed` and returns False, so `retry.offer` falls through to the gap
    branch or the objective branch and hands back a `verify` or a `reassess` — a
    fresh question that ships no answer, bounded by the caps that already exist.
    No parallel assessment flow, and nothing about the objective changes.

    Makes no model call, so it costs nothing and never touches the cap.
    """
    _tutor_available()
    graph = _load_session_or_404(session_id, user.user_id)
    node = _tutor_node(graph, (body.node_id if body else None))
    mode = tutor_mode.mode_for(node)
    # ALREADY REVEALED IS CHECKED FIRST, and the order is the whole point.
    #
    # Revealing spends the prompt, which makes `mode_for` report EXPLAIN — so a
    # second reveal would otherwise be refused as `not_asking`. That is literally
    # true and useless: the learner is not being told that nothing is outstanding,
    # they are being told they already did this. The specific reason has to
    # outrank the general one, or this branch is unreachable and the slug is a lie.
    if node is not None and node.tutor_state.revealed:
        raise HTTPException(status_code=409, detail="already_revealed")
    if not mode.is_scaffold:
        raise HTTPException(status_code=409, detail="not_asking")

    # The unit's own reveal. A verification or re-assessment question ships NO
    # answer by design (`teaching/verify.py`), so there is nothing to show for
    # one — and refusing is the honest response rather than showing the lesson's
    # reveal, which answers a different question.
    if mode.question_source in (history.SOURCE_VERIFICATION, history.SOURCE_REASSESSMENT):
        raise HTTPException(status_code=409, detail="no_explanation_for_this_question")

    reveal = str((node.cached_lesson or {}).get("reveal") or "")
    if not reveal.strip():
        raise HTTPException(status_code=409, detail="no_explanation_available")

    node.tutor_state.revealed = True
    learning_store.save_graph(graph, SESSIONS_DB_PATH, user_id=user.user_id)
    logger.info(
        "tutor reveal: session=%s node=%s hints=%s",
        session_id, node.id, node.tutor_state.hints_used,
    )
    return {
        **_tutor_payload(graph, node),
        "reveal": reveal,
        # The consequence, computed rather than described: this is what the
        # learner gets instead of the question they just spent.
        "retry": retry_model.to_wire(node),
    }


@app.post("/session/{session_id}/tutor/pin")
def tutor_pin(
    session_id: str, body: TutorPinRequest,
    user: CurrentUser = Depends(current_user),
) -> dict:
    """Keep an explanation with the lesson (tutor.md §11.2).

    Sets a flag on a turn ALREADY IN the transcript. Nothing is copied into
    `cached_lesson` and nothing reaches `plan_nodes.lesson_json` — the canonical
    lesson stays canonical, and a pinned note renders beside it as what it is: an
    answer the Tutor wrote for this learner, attributed.
    """
    _tutor_available()
    graph = _load_session_or_404(session_id, user.user_id)
    for turn in graph.tutor:
        if turn.get("id") == body.turn_id:
            turn["pinned"] = bool(body.pinned)
            learning_store.save_graph(graph, SESSIONS_DB_PATH, user_id=user.user_id)
            return {"turn": turn}
    raise HTTPException(status_code=404, detail="turn_not_found")
