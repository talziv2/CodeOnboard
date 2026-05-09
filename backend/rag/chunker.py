from pathlib import Path

from tree_sitter import Language, Parser
from tree_sitter_python import language as python_language

PY_LANGUAGE = Language(python_language())

CHUNK_NODE_TYPES = {"function_definition", "class_definition"}
IMPORT_NODE_TYPES = {"import_statement", "import_from_statement"}


def _get_node_name(node, source: bytes) -> str:
    for child in node.children:
        if child.type == "identifier":
            return source[child.start_byte:child.end_byte].decode("utf-8")
    return "unknown"


def _chunk_file(file_path: Path, repo_path: str) -> list[dict]:
    parser = Parser(PY_LANGUAGE)
    source = file_path.read_bytes()
    tree = parser.parse(source)

    relative_file = str(file_path.relative_to(repo_path))
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
                "content": content,
            })
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
                "content": content,
            })
            return

        for child in node.children:
            traverse(child)

    traverse(tree.root_node)
    return chunks


def chunk_repo(repo_path: str) -> list[dict]:
    all_chunks = []
    for py_file in Path(repo_path).rglob("*.py"):
        try:
            all_chunks.extend(_chunk_file(py_file, repo_path))
        except Exception:
            continue
    return all_chunks
