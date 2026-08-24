"""
Pytest tests for the Documentation Agent and its integration with the store
and Teaching Agent prompt.

Run with: uv run pytest tests/test_documentation_agent.py -v

No LLM calls, no network. The agent reads files only, so we test it against
real temporary directories.
"""
from pathlib import Path

import pytest

from tests.conftest import TEST_USER_ID

from backend.agents.documentation.agent import (
    _extract_file_docs,
    _read_docs_dir,
    _read_readme,
    run,
)
from backend.pipeline.state import OnboardState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def repo(tmp_path) -> Path:
    """A minimal fake repo with README, Python files, and a docs/ directory."""
    # README
    (tmp_path / "README.md").write_text(
        "# FakeLib\n\nA library for doing things.\n" * 40,  # longer than 2000 chars
        encoding="utf-8",
    )
    # Python source with a module docstring + class + function
    (tmp_path / "fakelib").mkdir()
    (tmp_path / "fakelib" / "__init__.py").write_text(
        '"""FakeLib top-level package."""\n', encoding="utf-8"
    )
    (tmp_path / "fakelib" / "auth.py").write_text(
        '"""Authentication helpers for FakeLib."""\n\n'
        'class BasicAuth:\n'
        '    """HTTP Basic Authentication handler."""\n\n'
        '    def login(self):\n'
        '        """Perform login."""\n'
        '        pass\n\n'
        'def token_auth(token):\n'
        '    """Authenticate using a bearer token."""\n'
        '    pass\n',
        encoding="utf-8",
    )
    # Python file with NO module docstring but has a class docstring
    (tmp_path / "fakelib" / "utils.py").write_text(
        'class Helper:\n'
        '    """A generic helper class."""\n'
        '    pass\n',
        encoding="utf-8",
    )
    # Python file with nothing at all
    (tmp_path / "fakelib" / "empty.py").write_text(
        "x = 1\n", encoding="utf-8"
    )
    # Nested file to test rglob
    (tmp_path / "fakelib" / "sub").mkdir()
    (tmp_path / "fakelib" / "sub" / "deep.py").write_text(
        '"""Deep nested module."""\n', encoding="utf-8"
    )
    # docs/ directory
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "auth.rst").write_text(
        "Authentication\n==============\nDetails about auth.\n", encoding="utf-8"
    )
    (tmp_path / "docs" / "quickstart.md").write_text(
        "# Quickstart\nGet started quickly.\n", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def state(repo) -> OnboardState:
    return OnboardState(
        repo_url="https://github.com/fake/fakelib",
        goal={"primary_goal": "understand auth"},
        repo_path=str(repo),
    )


# ---------------------------------------------------------------------------
# _read_readme
# ---------------------------------------------------------------------------

def test_read_readme_finds_md(repo):
    assert _read_readme(str(repo)).startswith("# FakeLib")


def test_read_readme_caps_at_2000_chars(repo):
    assert len(_read_readme(str(repo))) <= 2000


def test_read_readme_returns_empty_when_no_readme(tmp_path):
    assert _read_readme(str(tmp_path)) == ""


def test_read_readme_falls_back_to_rst(tmp_path):
    (tmp_path / "README.rst").write_text("RST readme content", encoding="utf-8")
    assert _read_readme(str(tmp_path)) == "RST readme content"


def test_read_readme_prefers_md_over_rst(tmp_path):
    (tmp_path / "README.md").write_text("MD readme", encoding="utf-8")
    (tmp_path / "README.rst").write_text("RST readme", encoding="utf-8")
    assert _read_readme(str(tmp_path)) == "MD readme"


# ---------------------------------------------------------------------------
# _extract_file_docs
# ---------------------------------------------------------------------------

def test_extract_file_docs_module_docstring(repo):
    module_doc, _ = _extract_file_docs(repo / "fakelib" / "auth.py")
    assert module_doc == "Authentication helpers for FakeLib."


def test_extract_file_docs_no_module_docstring(repo):
    module_doc, _ = _extract_file_docs(repo / "fakelib" / "utils.py")
    assert module_doc == ""


def test_extract_file_docs_class_docstring(repo):
    _, symbols = _extract_file_docs(repo / "fakelib" / "auth.py")
    assert "BasicAuth" in symbols
    assert symbols["BasicAuth"] == "HTTP Basic Authentication handler."


def test_extract_file_docs_public_method_docstring(repo):
    _, symbols = _extract_file_docs(repo / "fakelib" / "auth.py")
    assert "BasicAuth.login" in symbols
    assert symbols["BasicAuth.login"] == "Perform login."


def test_extract_file_docs_function_docstring(repo):
    _, symbols = _extract_file_docs(repo / "fakelib" / "auth.py")
    assert "token_auth" in symbols
    assert symbols["token_auth"] == "Authenticate using a bearer token."


def test_extract_file_docs_class_in_file_without_module_doc(repo):
    module_doc, symbols = _extract_file_docs(repo / "fakelib" / "utils.py")
    assert module_doc == ""
    assert "Helper" in symbols


def test_extract_file_docs_empty_file(repo):
    module_doc, symbols = _extract_file_docs(repo / "fakelib" / "empty.py")
    assert module_doc == ""
    assert symbols == {}


def test_extract_file_docs_syntax_error(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("def (((broken:", encoding="utf-8")
    module_doc, symbols = _extract_file_docs(bad)
    assert module_doc == ""
    assert symbols == {}


def test_extract_file_docs_missing_file(tmp_path):
    module_doc, symbols = _extract_file_docs(tmp_path / "nonexistent.py")
    assert module_doc == ""
    assert symbols == {}


# ---------------------------------------------------------------------------
# _read_docs_dir
# ---------------------------------------------------------------------------

def test_read_docs_dir_finds_files(repo):
    extra = _read_docs_dir(str(repo))
    assert any("auth.rst" in k for k in extra)
    assert any("quickstart.md" in k for k in extra)


def test_read_docs_dir_uses_relative_paths(repo):
    extra = _read_docs_dir(str(repo))
    for key in extra:
        assert not key.startswith("/"), f"expected relative path, got: {key}"


def test_read_docs_dir_returns_empty_when_no_docs_dir(tmp_path):
    assert _read_docs_dir(str(tmp_path)) == {}


def test_read_docs_dir_content_is_correct(repo):
    extra = _read_docs_dir(str(repo))
    auth_key = next(k for k in extra if "auth.rst" in k)
    assert "Authentication" in extra[auth_key]


# ---------------------------------------------------------------------------
# run() — happy path (all four keys present)
# ---------------------------------------------------------------------------

def test_run_sets_all_four_keys(state):
    run(state)
    assert set(state.doc_context.keys()) == {"readme", "file_docs", "symbol_docs", "extra_docs"}


def test_run_readme_content(state):
    run(state)
    assert state.doc_context["readme"].startswith("# FakeLib")
    assert len(state.doc_context["readme"]) <= 2000


def test_run_file_docs_captures_module_docstrings(state):
    run(state)
    file_docs = state.doc_context["file_docs"]
    assert any("auth.py" in k for k in file_docs)
    assert any("__init__.py" in k for k in file_docs)
    assert any("deep.py" in k for k in file_docs)


def test_run_file_docs_skips_files_without_module_docstring(state):
    run(state)
    # utils.py has no module docstring
    assert not any("utils.py" in k for k in state.doc_context["file_docs"])


def test_run_symbol_docs_captures_classes_and_functions(state):
    run(state)
    symbol_docs = state.doc_context["symbol_docs"]
    auth_key = next(k for k in symbol_docs if "auth.py" in k)
    assert "BasicAuth" in symbol_docs[auth_key]
    assert "token_auth" in symbol_docs[auth_key]


def test_run_symbol_docs_includes_public_methods(state):
    run(state)
    symbol_docs = state.doc_context["symbol_docs"]
    auth_key = next(k for k in symbol_docs if "auth.py" in k)
    assert "BasicAuth.login" in symbol_docs[auth_key]


def test_run_symbol_docs_captures_classes_even_without_module_docstring(state):
    run(state)
    symbol_docs = state.doc_context["symbol_docs"]
    utils_key = next(k for k in symbol_docs if "utils.py" in k)
    assert "Helper" in symbol_docs[utils_key]


def test_run_extra_docs_finds_docs_dir(state):
    run(state)
    extra = state.doc_context["extra_docs"]
    assert any("auth.rst" in k for k in extra)
    assert any("quickstart.md" in k for k in extra)


def test_run_uses_relative_paths_as_keys(state):
    run(state)
    for key in state.doc_context["file_docs"]:
        assert not key.startswith("/"), f"expected relative path, got: {key}"
    for key in state.doc_context["symbol_docs"]:
        assert not key.startswith("/"), f"expected relative path, got: {key}"


def test_run_does_not_raise_errors(state):
    run(state)
    assert state.errors == []


# ---------------------------------------------------------------------------
# run() — edge / error cases
# ---------------------------------------------------------------------------

def test_run_missing_repo_path_appends_error():
    state = OnboardState(repo_url="https://github.com/fake/fakelib", goal={}, repo_path="")
    run(state)
    assert any("repo_path missing" in e for e in state.errors)
    assert state.doc_context is None


def test_run_nonexistent_repo_path_returns_empty_context():
    state = OnboardState(
        repo_url="https://github.com/fake/fakelib",
        goal={},
        repo_path="/tmp/this_path_does_not_exist_at_all",
    )
    run(state)
    assert state.doc_context == {"readme": "", "file_docs": {}, "symbol_docs": {}, "extra_docs": {}}
    assert state.errors == []


def test_run_repo_with_no_readme(tmp_path):
    (tmp_path / "main.py").write_text('"""A module."""\n', encoding="utf-8")
    state = OnboardState(repo_url="https://github.com/fake/fakelib", goal={}, repo_path=str(tmp_path))
    run(state)
    assert state.doc_context["readme"] == ""
    assert any("main.py" in k for k in state.doc_context["file_docs"])


def test_run_repo_with_no_python_files(tmp_path):
    (tmp_path / "README.md").write_text("# JS Repo", encoding="utf-8")
    state = OnboardState(repo_url="https://github.com/fake/jsrepo", goal={}, repo_path=str(tmp_path))
    run(state)
    assert state.doc_context["readme"] == "# JS Repo"
    assert state.doc_context["file_docs"] == {}
    assert state.doc_context["symbol_docs"] == {}


# ---------------------------------------------------------------------------
# Store round-trip: doc_context (with all four keys) persists and loads
# ---------------------------------------------------------------------------

def test_store_persists_and_loads_doc_context(tmp_path):
    from backend.learning.graph import LearningGraph
    from backend.learning.store import load_graph, save_graph

    db = tmp_path / "sessions.db"
    graph = LearningGraph(repo_url="https://github.com/fake/fakelib", goal={"primary_goal": "test"})
    graph.doc_context = {
        "readme": "# FakeLib",
        "file_docs": {"fakelib/auth.py": "Authentication helpers."},
        "symbol_docs": {"fakelib/auth.py": {"BasicAuth": "HTTP Basic Authentication handler."}},
        "extra_docs": {"docs/auth.rst": "Authentication details."},
    }
    save_graph(graph, db_path=db, user_id=TEST_USER_ID)

    loaded = load_graph(graph.session_id, TEST_USER_ID, db_path=db)
    assert loaded is not None
    assert loaded.doc_context == graph.doc_context


def test_store_loads_none_doc_context_when_not_set(tmp_path):
    from backend.learning.graph import LearningGraph
    from backend.learning.store import load_graph, save_graph

    db = tmp_path / "sessions.db"
    graph = LearningGraph(repo_url="https://github.com/fake/fakelib", goal={"primary_goal": "test"})
    save_graph(graph, db_path=db, user_id=TEST_USER_ID)

    loaded = load_graph(graph.session_id, TEST_USER_ID, db_path=db)
    assert loaded is not None
    assert loaded.doc_context is None
