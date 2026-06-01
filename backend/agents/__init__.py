# Lazy-load each agent so that merely importing a sub-package (e.g.
# backend.agents.documentation) does not drag in the entire heavy chain
# (code_structure → embedder → sentence_transformers → torch/numpy).
# PEP 562 module __getattr__ is called only when the name is not already in
# the module's namespace — i.e. on first access, not at import time.

__all__ = [
    "run_code_structure",
    "run_documentation",
    "run_mentor",
    "run_prioritization",
    "run_reviewer",
    "start_session",
    "process_answer",
]


def __getattr__(name: str):
    if name == "run_code_structure":
        from backend.agents.code_structure import run
        return run
    if name == "run_documentation":
        from backend.agents.documentation import run
        return run
    if name == "run_mentor":
        from backend.agents.mentor import run
        return run
    if name == "run_prioritization":
        from backend.agents.prioritization import run
        return run
    if name == "start_session":
        from backend.agents.goal import start_session
        return start_session
    if name == "process_answer":
        from backend.agents.goal import process_answer
        return process_answer
    raise AttributeError(f"module 'backend.agents' has no attribute {name!r}")
