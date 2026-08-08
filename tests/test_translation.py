# Reading an existing session in another language.
#
# The contract under test: switching language must translate persisted prose
# rather than regenerate it, cache the result, and never lose or corrupt the
# session underneath — the graded answers on a node were given against the
# lesson as originally written.

import json
from unittest.mock import MagicMock, patch

import pytest

import backend.api as api
from backend.agents.translator import translate
from backend.learning import store as learning_store
from backend.learning.graph import CodeAnchor, LearningGraph, LearningNode


REPO_URL = "https://github.com/psf/requests"
HEBREW_GOAL = {
    "primary_goal": "להבין את מחזור החיים של בקשה",
    "focus_area": "ניתוב",
    "goal_type": "understand_system",
    "depth": "moderate",
    "language": "he",
}


def _stub_client(payload: dict) -> MagicMock:
    client = MagicMock()
    message = MagicMock()
    message.content = [MagicMock(text=json.dumps(payload, ensure_ascii=False))]
    client.messages.create.return_value = message
    return client


def _graph() -> LearningGraph:
    graph = LearningGraph(repo_url=REPO_URL, goal=dict(HEBREW_GOAL))
    node = graph.add_node(
        LearningNode(
            title="הבן את אובייקט ה-Session",
            code_anchor=CodeAnchor(file="requests/sessions.py", line_start=1, line_end=80),
            concept_tags=["architecture"],
        )
    )
    graph.set_current(node.id)
    return graph


# --- the translator itself ----------------------------------------------------


def test_translate_returns_the_keys_it_was_given():
    client = _stub_client({"a": "Hello", "b": "World"})
    out = translate({"a": "שלום", "b": "עולם"}, "en", client=client)
    assert out == {"a": "Hello", "b": "World"}


def test_translate_drops_keys_the_model_mangled():
    # A missing or blank value must not overwrite the original with nothing.
    client = _stub_client({"a": "Hello", "b": "", "c": "unasked for"})
    out = translate({"a": "שלום", "b": "עולם"}, "en", client=client)
    assert out == {"a": "Hello"}


def test_translate_skips_the_call_entirely_when_there_is_nothing_to_do():
    client = MagicMock()
    assert translate({}, "en", client=client) == {}
    client.messages.create.assert_not_called()


def test_translate_rejects_an_unsupported_language():
    with pytest.raises(ValueError):
        translate({"a": "x"}, "klingon", client=MagicMock())


# --- the graph's translation cache --------------------------------------------


def test_node_falls_back_to_the_original_when_untranslated():
    graph = _graph()
    node = next(iter(graph.nodes.values()))
    assert node.title_in("en", graph.language) == "הבן את אובייקט ה-Session"


def test_node_returns_the_translation_once_cached():
    graph = _graph()
    node = next(iter(graph.nodes.values()))
    node.cache_translation("en", title="Understand the Session object")
    assert node.title_in("en", graph.language) == "Understand the Session object"
    # The original is untouched — translations are derived, never authoritative.
    assert node.title == "הבן את אובייקט ה-Session"
    assert node.title_in("he", graph.language) == "הבן את אובייקט ה-Session"


def test_goal_overlay_only_replaces_translated_keys():
    graph = _graph()
    graph.goal_translations["en"] = {"primary_goal": "understand the request lifecycle"}
    overlaid = graph.goal_in("en")
    assert overlaid["primary_goal"] == "understand the request lifecycle"
    # Machine-read fields survive the overlay untouched.
    assert overlaid["goal_type"] == "understand_system"
    assert overlaid["depth"] == "moderate"
    # focus_area had no translation, so the original shows through.
    assert overlaid["focus_area"] == "ניתוב"


def test_to_dict_renders_the_requested_language():
    graph = _graph()
    node = next(iter(graph.nodes.values()))
    node.cache_translation("en", title="Understand the Session object")

    assert graph.to_dict("en")["nodes"][0]["title"] == "Understand the Session object"
    assert graph.to_dict("he")["nodes"][0]["title"] == "הבן את אובייקט ה-Session"
    # Default is the language the graph was written in.
    assert graph.to_dict()["nodes"][0]["title"] == "הבן את אובייקט ה-Session"


# --- persistence --------------------------------------------------------------


def test_translations_survive_a_save_load_round_trip(tmp_path):
    db = tmp_path / "sessions.db"
    graph = _graph()
    node = next(iter(graph.nodes.values()))
    node.cache_translation("en", title="Understand the Session object")
    node.cache_translation("en", lesson={"walkthrough": "…", "prompt": "…"})
    graph.goal_translations["en"] = {"primary_goal": "understand the lifecycle"}

    learning_store.save_graph(graph, db)
    loaded = learning_store.load_graph(graph.session_id, db)

    reloaded = loaded.nodes[node.id]
    assert reloaded.title_in("en", loaded.language) == "Understand the Session object"
    assert reloaded.lesson_in("en", loaded.language)["walkthrough"] == "…"
    assert loaded.goal_in("en")["primary_goal"] == "understand the lifecycle"


# --- the HTTP surface ---------------------------------------------------------


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(api, "SESSIONS_DB_PATH", tmp_path / "sessions.db")
    monkeypatch.setattr(api, "_new_client", lambda: MagicMock())
    return TestClient(api.app)


def _persist(graph):
    learning_store.save_graph(graph, api.SESSIONS_DB_PATH)


def test_session_without_language_reads_as_written(client):
    graph = _graph()
    _persist(graph)
    with patch.object(api, "translate") as translate_mock:
        body = client.get(f"/session/{graph.session_id}").json()
    # Nothing to translate, so nothing was spent.
    translate_mock.assert_not_called()
    assert body["nodes"][0]["title"] == "הבן את אובייקט ה-Session"
    assert body["language"] == "he"


def test_session_in_another_language_translates_and_caches(client):
    graph = _graph()
    node_id = graph.current_node_id
    _persist(graph)

    with patch.object(
        api,
        "translate",
        return_value={
            f"node:{node_id}": "Understand the Session object",
            "goal:primary_goal": "understand the request lifecycle",
        },
    ) as first:
        body = client.get(f"/session/{graph.session_id}?language=en").json()

    assert first.call_count == 1
    assert body["language"] == "en"
    assert body["source_language"] == "he"
    assert body["nodes"][0]["title"] == "Understand the Session object"
    assert body["goal"]["primary_goal"] == "understand the request lifecycle"

    # Second read is served from the cache — switching back and forth is free.
    with patch.object(api, "translate") as second:
        again = client.get(f"/session/{graph.session_id}?language=en").json()
    second.assert_not_called()
    assert again["nodes"][0]["title"] == "Understand the Session object"


def test_a_failed_translation_degrades_to_the_original(client):
    graph = _graph()
    _persist(graph)
    with patch.object(api, "translate", side_effect=RuntimeError("api down")):
        res = client.get(f"/session/{graph.session_id}?language=en")
    # A translation outage must not take the session down with it.
    assert res.status_code == 200
    assert res.json()["nodes"][0]["title"] == "הבן את אובייקט ה-Session"


def test_unknown_language_reads_as_english_rather_than_failing(client):
    graph = _graph()
    _persist(graph)
    with patch.object(api, "translate", return_value={}):
        res = client.get(f"/session/{graph.session_id}?language=klingon")
    assert res.status_code == 200
    assert res.json()["language"] == "en"


def test_switching_language_does_not_touch_the_persisted_goal(client):
    # /session/start matches on exact goal equality to decide whether to resume.
    # If reading in another language rewrote the goal, every switch would orphan
    # the session.
    graph = _graph()
    _persist(graph)
    with patch.object(api, "translate", return_value={"goal:primary_goal": "x"}):
        client.get(f"/session/{graph.session_id}?language=en")

    reloaded = learning_store.load_graph(graph.session_id, api.SESSIONS_DB_PATH)
    assert reloaded.goal == HEBREW_GOAL


def test_lesson_is_translated_but_the_graded_original_is_kept(client):
    graph = _graph()
    node = graph.nodes[graph.current_node_id]
    node.cached_lesson = {
        "walkthrough": "הסבר בעברית",
        "prompt": "שאלה בעברית",
        "expected_answer": "תשובה",
        "prompt_kind": "predict-then-reveal",
    }
    _persist(graph)

    with patch.object(api, "_render_current_lesson", return_value=node.cached_lesson), \
         patch.object(
             api,
             "translate",
             return_value={"walkthrough": "English walkthrough", "prompt": "English prompt"},
         ):
        body = client.get(f"/session/{graph.session_id}/lesson?language=en").json()

    assert body["lesson"]["walkthrough"] == "English walkthrough"
    assert body["lesson"]["prompt"] == "English prompt"

    # The Grader marks against the original, so it must survive untranslated.
    reloaded = learning_store.load_graph(graph.session_id, api.SESSIONS_DB_PATH)
    assert reloaded.nodes[node.id].cached_lesson["walkthrough"] == "הסבר בעברית"
    assert reloaded.nodes[node.id].cached_lesson["expected_answer"] == "תשובה"
