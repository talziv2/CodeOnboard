# Source parsing for Layer A — the tree-sitter walk the Skeleton is built from.
#
# This module began life as `backend/rag/chunker.py`, cutting a repository into
# embeddable chunks. Retrieval is gone, but the walk itself was never retrieval
# machinery: it finds every function, class and import statement with exact line
# ranges, which is precisely what the deterministic index needs. It moved here
# because Layer A is now its only consumer, not because the name was tidied.
#
# One unit per definition, plus one per import statement. `content` is carried on
# each unit because callers that want source (the Skeleton drops it; tests use
# it) should not have to re-read the file.
#
# PYTHON-ONLY, structurally: the grammar, the node types and the role rules are
# all Python. Multi-language support means adding sibling adapters behind this
# interface, not generalising this file.

from pathlib import Path

from tree_sitter import Language, Parser
from tree_sitter_python import language as python_language

PY_LANGUAGE = Language(python_language())

CHUNK_NODE_TYPES = {"function_definition", "class_definition"}
IMPORT_NODE_TYPES = {"import_statement", "import_from_statement"}

# Every Python file is indexed and each unit carries a `role`, so a caller can
# tell library source from tests, docs, examples and dev tooling. The Skeleton
# uses it for `list_files(role=…)` and to keep `scripts/` out of a repository's
# source root.
ROLE_DIR_SEGMENTS: dict[str, frozenset[str]] = {
    "test": frozenset({"tests", "test", "__tests__"}),
    "doc": frozenset({"docs", "doc", "docs_src"}),
    "example": frozenset({"examples", "example"}),
    "tooling": frozenset({"scripts"}),
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


def _parse_file(file_path: Path, repo_path: str) -> list[dict]:
    parser = Parser(PY_LANGUAGE)
    source = file_path.read_bytes()
    tree = parser.parse(source)

    relative_path = file_path.relative_to(repo_path)
    relative_file = str(relative_path)
    role = classify_role(relative_path)
    units: list[dict] = []

    def traverse(node):
        if node.type in CHUNK_NODE_TYPES:
            name = _get_node_name(node, source)
            content = source[node.start_byte:node.end_byte].decode("utf-8")
            units.append({
                "file": relative_file,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "type": "function" if node.type == "function_definition" else "class",
                "name": name,
                "language": "python",
                "role": role,
                "content": content,
            })
            # Keep recursing into classes so methods become their own units.
            # The class unit is kept too: the Skeleton needs both to derive
            # qualified names ("Session.send") by containment.
            if node.type == "class_definition":
                for child in node.children:
                    traverse(child)
            return

        if node.type in IMPORT_NODE_TYPES:
            content = source[node.start_byte:node.end_byte].decode("utf-8")
            units.append({
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
    return units


def parse_repo(repo_path: str) -> list[dict]:
    """Every function, class and import in the checkout, with exact ranges.

    A file that will not parse is skipped rather than failing the index: one
    unreadable module must not cost the repository its whole skeleton.
    """
    repo = Path(repo_path)
    units: list[dict] = []
    for py_file in repo.rglob("*.py"):
        try:
            units.extend(_parse_file(py_file, repo_path))
        except Exception:
            continue
    return units
