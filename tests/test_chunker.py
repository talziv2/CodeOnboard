"""
Pytest tests for chunker exclusion + happy-path chunking.
Run with: uv run pytest tests/test_chunker.py -v
"""
from pathlib import Path

from backend.rag.chunker import _is_excluded, chunk_repo


def _write(path: Path, content: str = "def x():\n    pass\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# ── _is_excluded unit tests ───────────────────────────────────────────────────

def test_is_excluded_top_level_tests_dir():
    assert _is_excluded(Path("tests/foo.py"))
    assert _is_excluded(Path("tests/sub/foo.py"))


def test_is_excluded_singular_test_dir():
    assert _is_excluded(Path("test/foo.py"))


def test_is_excluded_dunder_tests_dir():
    assert _is_excluded(Path("__tests__/foo.py"))


def test_is_excluded_nested_tests_dir():
    assert _is_excluded(Path("src/tests/foo.py"))
    assert _is_excluded(Path("src/pkg/tests/bar.py"))


def test_is_excluded_docs_and_examples():
    assert _is_excluded(Path("docs/conf.py"))
    assert _is_excluded(Path("examples/demo.py"))
    assert _is_excluded(Path("example/demo.py"))


def test_is_excluded_conftest_anywhere():
    assert _is_excluded(Path("conftest.py"))
    assert _is_excluded(Path("src/pkg/conftest.py"))


def test_is_not_excluded_library_files():
    assert not _is_excluded(Path("src/foo.py"))
    assert not _is_excluded(Path("src/pkg/util.py"))
    assert not _is_excluded(Path("foo.py"))


def test_is_not_excluded_filename_containing_test_substring():
    # filename contains "test" but isn't an excluded dir or conftest.py
    assert not _is_excluded(Path("src/testing.py"))
    assert not _is_excluded(Path("src/contest.py"))


# ── chunk_repo integration with exclusion ─────────────────────────────────────

def test_chunk_repo_excludes_tests_directory(tmp_path):
    _write(tmp_path / "src" / "lib.py", "def foo():\n    pass\n")
    _write(tmp_path / "tests" / "test_lib.py", "def test_foo():\n    pass\n")

    chunks = chunk_repo(str(tmp_path))
    files = {c["file"] for c in chunks}

    assert any("lib.py" in f for f in files)
    assert not any("test_lib" in f for f in files)


def test_chunk_repo_excludes_nested_tests_directory(tmp_path):
    _write(tmp_path / "src" / "core.py", "def main():\n    pass\n")
    _write(tmp_path / "src" / "tests" / "test_inner.py", "def test():\n    pass\n")

    chunks = chunk_repo(str(tmp_path))
    files = {c["file"] for c in chunks}

    assert any("core" in f for f in files)
    assert not any("test_inner" in f for f in files)


def test_chunk_repo_excludes_conftest(tmp_path):
    _write(tmp_path / "conftest.py", "import pytest\n")
    _write(tmp_path / "module.py", "def m():\n    pass\n")

    chunks = chunk_repo(str(tmp_path))
    files = {c["file"] for c in chunks}

    assert not any("conftest" in f for f in files)
    assert any("module" in f for f in files)


def test_chunk_repo_excludes_docs_and_examples(tmp_path):
    _write(tmp_path / "docs" / "conf.py", "project = 'x'\n")
    _write(tmp_path / "examples" / "demo.py", "def demo():\n    pass\n")
    _write(tmp_path / "src" / "real.py", "def real():\n    pass\n")

    chunks = chunk_repo(str(tmp_path))
    files = {c["file"] for c in chunks}

    assert any("real" in f for f in files)
    assert not any("conf.py" in f and "docs" in f for f in files)
    assert not any("demo" in f for f in files)


def test_chunk_repo_still_chunks_library_files(tmp_path):
    _write(
        tmp_path / "src" / "core.py",
        "class A:\n"
        "    def method(self):\n"
        "        pass\n\n"
        "def standalone():\n"
        "    return 1\n",
    )

    chunks = chunk_repo(str(tmp_path))
    names = {c["name"] for c in chunks if c["type"] != "import"}

    assert "A" in names
    assert "standalone" in names
