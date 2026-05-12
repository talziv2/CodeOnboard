"""
Pytest tests for chunker exclusion + happy-path chunking.
Run with: uv run pytest tests/test_chunker.py -v
"""
from pathlib import Path

from backend.rag.chunker import _is_excluded, _is_test_filename, chunk_repo


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
    # filename contains "test" but isn't an excluded dir, conftest, or test_*/x_test pattern
    assert not _is_excluded(Path("src/testing.py"))
    assert not _is_excluded(Path("src/contest.py"))


# ── test_*.py / *_test.py filename exclusion ──────────────────────────────────

def test_is_test_filename_pytest_prefix():
    assert _is_test_filename("test_submarine.py")
    assert _is_test_filename("test_foo.py")


def test_is_test_filename_underscore_suffix():
    assert _is_test_filename("submarine_test.py")
    assert _is_test_filename("foo_test.py")


def test_is_test_filename_rejects_non_python():
    assert not _is_test_filename("test_data.txt")
    assert not _is_test_filename("submarine_test.json")


def test_is_test_filename_rejects_lookalikes():
    assert not _is_test_filename("testing.py")
    assert not _is_test_filename("contest.py")
    assert not _is_test_filename("attest.py")


def test_is_excluded_test_prefix_at_top_level():
    assert _is_excluded(Path("test_submarine.py"))


def test_is_excluded_test_prefix_nested():
    assert _is_excluded(Path("src/test_lib.py"))


def test_is_excluded_underscore_test_suffix():
    assert _is_excluded(Path("submarine_test.py"))
    assert _is_excluded(Path("src/foo_test.py"))


def test_chunk_repo_excludes_top_level_test_file(tmp_path):
    _write(tmp_path / "submarine.py", "class Sub:\n    pass\n")
    _write(tmp_path / "test_submarine.py", "def test_sub():\n    pass\n")
    _write(tmp_path / "main_test.py", "def test_main():\n    pass\n")

    chunks = chunk_repo(str(tmp_path))
    files = {c["file"] for c in chunks}

    assert any("submarine.py" == f for f in files)
    assert not any("test_submarine" in f for f in files)
    assert not any("main_test" in f for f in files)


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


# ── method-level chunking inside classes ──────────────────────────────────────

def test_chunk_repo_emits_method_chunks_inside_classes(tmp_path):
    _write(
        tmp_path / "src" / "core.py",
        "class Submarine:\n"
        "    def __init__(self, x):\n"
        "        self.x = x\n\n"
        "    def dive(self):\n"
        "        return self.x\n\n"
        "    def surface(self):\n"
        "        return 0\n",
    )

    chunks = chunk_repo(str(tmp_path))
    by_type = {c["type"]: [c["name"] for c in chunks if c["type"] == c["type"]] for c in chunks}
    class_names = [c["name"] for c in chunks if c["type"] == "class"]
    func_names = [c["name"] for c in chunks if c["type"] == "function"]

    assert "Submarine" in class_names
    assert "__init__" in func_names
    assert "dive" in func_names
    assert "surface" in func_names


def test_chunk_repo_method_chunks_have_inner_line_ranges(tmp_path):
    _write(
        tmp_path / "src" / "core.py",
        "class Submarine:\n"
        "    def dive(self):\n"
        "        return 1\n",
    )

    chunks = chunk_repo(str(tmp_path))
    cls = next(c for c in chunks if c["type"] == "class")
    fn = next(c for c in chunks if c["type"] == "function" and c["name"] == "dive")

    # method's range must be strictly inside the class's range
    assert cls["start_line"] <= fn["start_line"]
    assert fn["end_line"] <= cls["end_line"]


def test_chunk_repo_handles_nested_classes(tmp_path):
    _write(
        tmp_path / "src" / "core.py",
        "class Outer:\n"
        "    class Inner:\n"
        "        def method(self):\n"
        "            return 1\n",
    )

    chunks = chunk_repo(str(tmp_path))
    class_names = [c["name"] for c in chunks if c["type"] == "class"]
    func_names = [c["name"] for c in chunks if c["type"] == "function"]

    assert "Outer" in class_names
    assert "Inner" in class_names
    assert "method" in func_names
