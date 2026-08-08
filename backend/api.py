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
    localize,
    process_answer,
    question_progress,
    start_session,
)
from backend.agents.grader import run as run_grader
from backend.agents.language import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, language_of
from backend.agents.translator import translate
from backend.agents.mentor.mutator import mutate as mutate_graph
from backend.agents.teaching import run as run_teaching
from backend.learning import store as learning_store
from backend.pipeline.runner import run_pipeline
from backend.pipeline.state import OnboardState
from backend.rag.cloner import check_repo_reachable, clone_repo

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
    # Interview language. Rides along on the synthesized goal from here on, so
    # every downstream agent writes prose the user can read. Unknown codes fall
    # back to English rather than 400 — a bad locale shouldn't block a session.
    language: str = DEFAULT_LANGUAGE


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


@app.get("/languages")
def languages() -> dict:
    # Lets the UI build its switcher from the backend's actual capability rather
    # than a duplicated hardcoded list.
    return {"languages": SUPPORTED_LANGUAGES, "default": DEFAULT_LANGUAGE}


@app.post("/goal/start", response_model=StartResponse)
def goal_start(body: StartRequest) -> StartResponse:
    language = language_of({"language": body.language})
    session = start_session(body.repo_url, language=language)
    sessions[session.session_id] = session
    first_q = localize(CORE_QUESTIONS[0], language)
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
    localized = localize(next_q, session.language)
    return AnswerResponse(
        done=False,
        question=QuestionOut(
            text=localized.text,
            options=localized.options,
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
    # The language the user is currently reading in. Feedback is a direct reply
    # to someone reading right now, so it follows the display language rather
    # than the language the session was created in.
    language: str | None = None


class OverrideRequest(BaseModel):
    action: str  # "mark_understood" | "mark_weak" | "skip"
    node_id: str | None = None  # defaults to the current node


# Shown when the Teaching Agent fails outright, so it never reaches the model
# that would otherwise have translated it.
_FALLBACK_LESSON: dict[str, dict[str, str]] = {
    "en": {
        "read_source": (
            "The lesson for this node could not be generated automatically.\n\n"
            "Please read the source file `{file}` lines {start}–{end} directly."
        ),
        "skip_node": "Lesson generation failed. Please skip this node.",
        "prompt": "What is the main purpose of this code?",
    },
    "he": {
        "read_source": (
            "לא ניתן היה לייצר את השיעור עבור הצומת הזה באופן אוטומטי.\n\n"
            "אנא קרא ישירות את קובץ המקור `{file}`, שורות {start}–{end}."
        ),
        "skip_node": "ייצור השיעור נכשל. אנא דלג על הצומת הזה.",
        "prompt": "מהי המטרה העיקרית של הקוד הזה?",
    },
}


def _load_session_or_404(session_id: str):
    graph = learning_store.load_graph(session_id, SESSIONS_DB_PATH)
    if graph is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    return graph


# ── Reading a session in another language ─────────────────────────────────────
#
# A graph's prose is written once, in the language of the session, and then
# persisted alongside the answers the user gave against it. Switching language
# therefore translates rather than regenerates: regenerating would produce
# *different* lessons and invalidate that history.
#
# Both helpers below are no-ops when the requested language is the one the graph
# was written in, so the single-language path costs nothing.


def _fill_title_translations(graph, language: str, client) -> bool:
    """Translate any node titles (and the goal blurb) missing for `language`.

    One batched call for the whole graph. Returns True if anything was cached,
    so the caller knows whether a save is warranted.
    """
    if language == graph.language:
        return False

    pending: dict[str, str] = {}
    for node in graph.nodes.values():
        if not graph.nodes[node.id].translations.get(language, {}).get("title"):
            pending[f"node:{node.id}"] = node.title

    goal_keys = ("primary_goal", "focus_area")
    cached_goal = graph.goal_translations.get(language, {})
    for key in goal_keys:
        if graph.goal.get(key) and not cached_goal.get(key):
            pending[f"goal:{key}"] = graph.goal[key]

    if not pending:
        return False

    try:
        translated = translate(pending, language, client=client)
    except Exception as exc:
        # Falling back to the original language is a worse read, but a readable
        # one. Never fail a page load over a translation. Nothing is cached, so
        # a transient outage is retried on the next read.
        print(f"[translate titles] {language}: {exc}", flush=True)
        return False

    # A key the model declined to return is cached as its original text. The
    # call happened; repeating it on every page load would spend money to be
    # told the same thing again.
    resolved = {key: translated.get(key, source) for key, source in pending.items()}

    slot = graph.goal_translations.setdefault(language, {})
    for key, value in resolved.items():
        kind, _, ident = key.partition(":")
        if kind == "node" and ident in graph.nodes:
            graph.nodes[ident].cache_translation(language, title=value)
        elif kind == "goal":
            slot[ident] = value
    return True


def _fill_lesson_translation(graph, node, language: str, client) -> bool:
    """Translate one node's cached lesson into `language` if not already done."""
    if language == graph.language or not node.cached_lesson:
        return False
    if node.translations.get(language, {}).get("lesson"):
        return False

    lesson = node.cached_lesson
    pending = {
        field: lesson[field]
        for field in ("walkthrough", "prompt")
        if isinstance(lesson.get(field), str) and lesson[field].strip()
    }
    if not pending:
        return False

    try:
        translated = translate(pending, language, client=client)
    except Exception as exc:
        print(f"[translate lesson] {node.id} {language}: {exc}", flush=True)
        return False

    # expected_answer is never shown; it only ever feeds the Grader, which is
    # told to grade the idea rather than the wording, so it stays as written.
    resolved = {key: translated.get(key, source) for key, source in pending.items()}
    node.cache_translation(language, lesson={**lesson, **resolved})
    return True


def _requested_language(graph, language: str | None) -> str:
    """The language to render in — the request's, or the graph's own."""
    if language is None:
        return graph.language
    return language_of({"language": language})


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
        strings = _FALLBACK_LESSON.get(language_of(graph.goal), _FALLBACK_LESSON["en"])
        fallback = {
            "walkthrough": (
                strings["read_source"].format(
                    file=node.code_anchor.file,
                    start=node.code_anchor.line_start,
                    end=node.code_anchor.line_end,
                )
                if node else strings["skip_node"]
            ),
            "prompt": strings["prompt"],
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
def session_get(session_id: str, language: str | None = None) -> dict:
    graph = _load_session_or_404(session_id)
    lang = _requested_language(graph, language)
    if _fill_title_translations(graph, lang, _new_client()):
        learning_store.save_graph(graph, SESSIONS_DB_PATH)
    return graph.to_dict(lang)


@app.get("/session/{session_id}/lesson")
def session_lesson(session_id: str, language: str | None = None) -> dict:
    graph = _load_session_or_404(session_id)
    if graph.current_node_id is None:
        raise HTTPException(status_code=409, detail="session_has_no_current_node")
    client = _new_client()
    lang = _requested_language(graph, language)

    # The lesson is always generated in the session's own language so that
    # cached_lesson stays the single version the Grader marks against; reading
    # it in another language is a translation layered on top.
    _render_current_lesson(graph, client)
    node = graph.nodes[graph.current_node_id]
    if _fill_lesson_translation(graph, node, lang, client):
        learning_store.save_graph(graph, SESSIONS_DB_PATH)

    return {
        "node_id": graph.current_node_id,
        "lesson": node.lesson_in(lang, graph.language),
        "language": lang,
    }


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
    print(f"[advance] current={current[:8]} is_prereq={current_is_prereq} nxt={nxt[:8] if nxt else None} edges={[(e.from_node_id[:8], e.to_node_id[:8], e.kind) for e in graph.edges]}")
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
    lang = _requested_language(graph, body.language)
    # Overriding only the state's copy — graph.goal stays the persisted original,
    # which /session/start matches on when deciding whether to resume.
    state = OnboardState(
        repo_url=graph.repo_url,
        goal={**graph.goal, "language": lang},
        client=client,
    )
    state.graph = graph
    run_grader(state, body.response, client=client)
    # The Grader updated the node's understanding_state / weak_spot in place.

    grade = state.last_grade or {}
    classification = grade.get("classification") or "partial"
    graph.record_attempt(
        current, body.response, classification, grade.get("rationale") or ""
    )

    # A wrong answer gets a warm-up automatically — being stuck is exactly when
    # a user is least able to judge that they need one. "partial" does not: the
    # user is mostly there, so the warm-up stays an offer they can decline
    # (the /retry endpoint). The Mutator's one-prerequisite-per-node cap still
    # applies, so repeated failures can't stack warm-ups.
    mutation = {"kind": "none"}
    if classification in ("confused", "off-topic"):
        try:
            # A warm-up adds a real node to the graph, so its title is written
            # in the session's own language and translated for display like
            # every other node — unlike the grading feedback above, which is
            # transient and follows the reader.
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
