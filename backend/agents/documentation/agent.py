# Documentation Agent — extracts README, module docstrings, class/function
# docstrings, and docs/ directory files from the cloned repo.
#
# No LLM call. This is pure file reading — fast, deterministic, zero cost.
# The Teaching Agent uses the output to include real documentation quotes in
# its lessons rather than relying on LLM-generated descriptions.
#
# Entry point:
#   run(state, client=None) → reads all documentation from state.repo_path,
#                             writes state.doc_context, returns state.
#
# Output shape:
#   state.doc_context = {
#       "readme":      str,       # first 2 000 chars of the repo README
#       "file_docs":   {          # relative path → module-level docstring
#           "requests/auth.py":       "Urllib3 authentication classes...",
#       },
#       "symbol_docs": {          # relative path → {symbol_name: docstring}
#           "requests/sessions.py": {
#               "Session":       "A Requests session...",
#               "HTTPAdapter":   "...",
#               "request":       "...",
#           }
#       },
#       "extra_docs":  {          # docs/ directory files (RST / MD)
#           "docs/quickstart.rst": "...",
#       }
#   }
#
# Mirrors the other agents: client signature accepted but ignored, errors
# appended to state.errors, never raises.

import ast
from pathlib import Path

from backend.pipeline.state import OnboardState


_README_CHARS = 2000    # cap README to keep Teaching Agent prompts lean
_MAX_PY_FILES = 120     # large repos can have 500+ Python files
_MAX_DOC_FILES = 10     # docs/ directory files to read
_DOC_FILE_CHARS = 1000  # chars per docs/ file

_README_NAMES = (
    "README.md", "readme.md",
    "README.rst", "readme.rst",
    "README.txt", "readme.txt",
    "README",
)

_SYMBOL_TYPES = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _read_readme(repo_path: str) -> str:
    for name in _README_NAMES:
        p = Path(repo_path) / name
        if p.exists():
            try:
                return p.read_text(encoding="utf-8", errors="ignore")[:_README_CHARS]
            except Exception:
                continue
    return ""


def _extract_file_docs(file_path: Path) -> tuple[str, dict[str, str]]:
    """Return (module_docstring, {symbol_name: docstring}) for a Python file.

    Walks the top-level AST nodes only (no nested functions/methods) to keep
    the output focused on the public surface of each file.
    """
    module_doc = ""
    symbols: dict[str, str] = {}
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source)
        module_doc = ast.get_docstring(tree) or ""
        # Top-level classes and functions only — methods inside classes are
        # included by iterating class body.
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                doc = ast.get_docstring(node)
                if doc:
                    symbols[node.name] = doc
                # One level deeper: public methods of this class.
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not child.name.startswith("_"):
                            mdoc = ast.get_docstring(child)
                            if mdoc:
                                symbols[f"{node.name}.{child.name}"] = mdoc
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node)
                if doc:
                    symbols[node.name] = doc
    except Exception:
        pass
    return module_doc, symbols


def _read_docs_dir(repo_path: str) -> dict[str, str]:
    """Read .md and .rst files from the repo's docs/ directory (if present)."""
    extra: dict[str, str] = {}
    docs_dir = Path(repo_path) / "docs"
    if not docs_dir.exists():
        return extra
    count = 0
    for pattern in ("*.md", "*.rst"):
        for f in sorted(docs_dir.rglob(pattern)):
            if count >= _MAX_DOC_FILES:
                return extra
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")[:_DOC_FILE_CHARS]
                relative = str(f.relative_to(repo_path))
                extra[relative] = content
                count += 1
            except Exception:
                continue
    return extra


def run(state: OnboardState, client=None) -> OnboardState:
    if not state.repo_path:
        state.errors.append("documentation_agent: repo_path missing, skipping")
        return state

    repo = Path(state.repo_path)
    if not repo.exists():
        # Graceful no-op — repo not cloned yet (e.g. in unit tests with fake paths).
        state.doc_context = {"readme": "", "file_docs": {}, "symbol_docs": {}, "extra_docs": {}}
        return state

    readme = _read_readme(state.repo_path)

    file_docs: dict[str, str] = {}
    symbol_docs: dict[str, dict[str, str]] = {}

    try:
        py_files = sorted(repo.rglob("*.py"))[:_MAX_PY_FILES]
    except Exception:
        py_files = []

    for py_file in py_files:
        module_doc, symbols = _extract_file_docs(py_file)
        try:
            relative = str(py_file.relative_to(state.repo_path))
        except ValueError:
            continue
        if module_doc:
            file_docs[relative] = module_doc
        if symbols:
            symbol_docs[relative] = symbols

    extra_docs = _read_docs_dir(state.repo_path)

    state.doc_context = {
        "readme": readme,
        "file_docs": file_docs,
        "symbol_docs": symbol_docs,
        "extra_docs": extra_docs,
    }
    return state
