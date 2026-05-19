from pathlib import Path

from tree_sitter import Language, Parser
from tree_sitter_python import language as python_language

PY_LANGUAGE = Language(python_language())

CHUNK_NODE_TYPES = {"function_definition", "class_definition"}
IMPORT_NODE_TYPES = {"import_statement", "import_from_statement"}

# Every Python file is indexed; each chunk carries a `role` so retrieval can
# filter by it. Tour-style goals (understand_system) stay source-only, while
# debug_issue / contribute_code also retrieve test chunks as evidence.
ROLE_DIR_SEGMENTS: dict[str, frozenset[str]] = {
    "test": frozenset({"tests", "test", "__tests__"}),
    "doc": frozenset({"docs", "doc", "docs_src"}),
    "example": frozenset({"examples", "example"}),
}
TEST_FILE_NAMES = frozenset({"conftest.py"})


def _get_node_name(node, source: bytes) -> str:
    for child in node.children:
        if child.type == "identifier":
            return source[child.start_byte:child.end_byte].decode("utf-8")
    return "unknown"


def _is_test_filename(name: str) -> bool:
    if not name.endswith(".py"):
        return False
    return name.startswith("test_") or name.endswith("_test.py")


def classify_role(relative_path: Path) -> str:
    """Tag a file by what kind of code it holds: source | test | doc | example.

    A test filename anywhere wins over its directory, so a ``test_*.py`` file
    sitting in a source package is still tagged ``test``.
    """
    name = relative_path.name
    if name in TEST_FILE_NAMES or _is_test_filename(name):
        return "test"
    parts = set(relative_path.parts)
    for role, segments in ROLE_DIR_SEGMENTS.items():
        if parts & segments:
            return role
    return "source"


def _chunk_file(file_path: Path, repo_path: str) -> list[dict]:
    parser = Parser(PY_LANGUAGE)
    source = file_path.read_bytes()
    tree = parser.parse(source)

    relative_path = file_path.relative_to(repo_path)
    relative_file = str(relative_path)
    role = classify_role(relative_path)
    chunks = []

    def traverse(node):
        if node.type in CHUNK_NODE_TYPES:
            name = _get_node_name(node, source)
            content = source[node.start_byte:node.end_byte].decode("utf-8")
            chunks.append({
                "file": relative_file,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "type": "function" if node.type == "function_definition" else "class",
                "name": name,
                "language": "python",
                "role": role,
                "content": content,
            })
            # For classes, keep recursing so methods become their own chunks.
            # The class chunk is kept too (whole-class context), and the
            # retrieval layer drops it when narrower method chunks land in
            # the same result set.
            if node.type == "class_definition":
                for child in node.children:
                    traverse(child)
            return

        if node.type in IMPORT_NODE_TYPES:
            content = source[node.start_byte:node.end_byte].decode("utf-8")
            chunks.append({
                "file": relative_file,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "type": "import",
                "name": content.split("\n")[0][:80],
                "language": "python",
                "role": role,
                "content": content,
            })
            return

        for child in node.children:
            traverse(child)

    traverse(tree.root_node)
    return chunks


def chunk_repo(repo_path: str) -> list[dict]:
    repo = Path(repo_path)
    all_chunks = []
    for py_file in repo.rglob("*.py"):
        try:
            all_chunks.extend(_chunk_file(py_file, repo_path))
        except Exception:
            continue
    return all_chunks
