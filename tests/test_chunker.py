"""
Pytest tests for chunker role tagging + happy-path chunking.
Run with: uv run pytest tests/test_chunker.py -v
"""
from pathlib import Path

from backend.rag.chunker import _is_test_filename, classify_role, chunk_repo


def _write(path: Path, content: str = "def x():\n    pass\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# ── classify_role ─────────────────────────────────────────────────────────────

def test_classify_role_test_directories():
    assert classify_role(Path("tests/foo.py")) == "test"
    assert classify_role(Path("test/foo.py")) == "test"
    assert classify_role(Path("__tests__/foo.py")) == "test"
    assert classify_role(Path("src/pkg/tests/bar.py")) == "test"


def test_classify_role_test_filenames():
    assert classify_role(Path("test_submarine.py")) == "test"
    assert classify_role(Path("src/test_lib.py")) == "test"
    assert classify_role(Path("src/foo_test.py")) == "test"
    assert classify_role(Path("conftest.py")) == "test"
    assert classify_role(Path("src/pkg/conftest.py")) == "test"


def test_classify_role_docs_and_examples():
    assert classify_role(Path("docs/conf.py")) == "doc"
    assert classify_role(Path("doc/conf.py")) == "doc"
    assert classify_role(Path("examples/demo.py")) == "example"
    assert classify_role(Path("example/demo.py")) == "example"


def test_classify_role_source():
    assert classify_role(Path("src/foo.py")) == "source"
    assert classify_role(Path("src/pkg/util.py")) == "source"
    assert classify_role(Path("foo.py")) == "source"


def test_classify_role_ignores_lookalike_filenames():
    # filename contains "test" but is not a test_*/x_test pattern
    assert classify_role(Path("src/testing.py")) == "source"
    assert classify_role(Path("src/contest.py")) == "source"
    assert classify_role(Path("src/attest.py")) == "source"


def test_is_test_filename_rejects_non_python():
    assert not _is_test_filename("test_data.txt")
    assert not _is_test_filename("submarine_test.json")


# ── chunk_repo includes all files, tagged by role ─────────────────────────────

def test_chunk_repo_includes_test_files_tagged_test(tmp_path):
    _write(tmp_path / "src" / "lib.py", "def foo():\n    pass\n")
    _write(tmp_path / "tests" / "test_lib.py", "def test_foo():\n    pass\n")

    chunks = chunk_repo(str(tmp_path))
    by_file = {c["file"]: c["role"] for c in chunks}

    assert any("lib.py" in f and role == "source" for f, role in by_file.items())
    assert any("test_lib" in f and role == "test" for f, role in by_file.items())


def test_chunk_repo_includes_docs_and_examples(tmp_path):
    _write(tmp_path / "docs" / "conf.py", "project = 'x'\ndef helper():\n    pass\n")
    _write(tmp_path / "examples" / "demo.py", "def demo():\n    pass\n")
    _write(tmp_path / "src" / "real.py", "def real():\n    pass\n")

    chunks = chunk_repo(str(tmp_path))
    roles_by_file = {c["file"]: c["role"] for c in chunks}

    assert any("real" in f and r == "source" for f, r in roles_by_file.items())
    assert any("conf.py" in f and r == "doc" for f, r in roles_by_file.items())
    assert any("demo" in f and r == "example" for f, r in roles_by_file.items())


def test_chunk_repo_every_chunk_has_a_role(tmp_path):
    _write(tmp_path / "src" / "core.py", "class A:\n    def m(self):\n        pass\n")
    _write(tmp_path / "tests" / "test_core.py", "def test_a():\n    pass\n")

    chunks = chunk_repo(str(tmp_path))
    assert chunks
    assert all(c["role"] in {"source", "test", "doc", "example"} for c in chunks)


def test_chunk_repo_nested_test_dir_tagged_test(tmp_path):
    _write(tmp_path / "src" / "core.py", "def main():\n    pass\n")
    _write(tmp_path / "src" / "tests" / "test_inner.py", "def test():\n    pass\n")

    chunks = chunk_repo(str(tmp_path))
    roles_by_file = {c["file"]: c["role"] for c in chunks}

    assert any("core" in f and r == "source" for f, r in roles_by_file.items())
    assert any("test_inner" in f and r == "test" for f, r in roles_by_file.items())


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
