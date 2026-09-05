"""**The patch is the learner's, it never reaches disk, and nothing here runs.**

Run with: uv run pytest tests/test_contribution_boundary.py -v

Three laws, each asserted the strongest way available, because the coding stage
is where this product is one careless commit away from becoming something it
deliberately is not.

  NOTHING IS WRITTEN TO THE CHECKOUT
      `data/repos/<owner>/<name>` is ONE directory shared by every user and every
      session of that repository (`repo/cloner.py` — the layout exists because
      two owners with the same repository name once shared a checkout and one
      learner silently studied the other's code). Applying a learner's patch
      there would corrupt other people's sessions. Asserted structurally: no
      contribution module opens a file for writing or reaches a filesystem
      mutator.

  NOTHING EXECUTES REPOSITORY CODE
      There is no sandbox in this project and there is no test runner. Executing
      a cloned public repository's suite is arbitrary code execution as the
      server user. Asserted structurally: no `subprocess`, no `os.system`, no
      `eval`, no `exec`, no `importlib`. `ast.parse` is the one structural read
      of learner text that is allowed, and it builds a tree rather than running
      one.

  THE SYSTEM NEVER WRITES THE CODE
      The plan is prose, the review is an opinion, the PR summary describes a
      change that already exists. If a prompt started returning code the learner
      would stop being the contributor, which is the whole difference between
      this and a coding agent. Asserted against the prompts themselves.

The behavioural half of the first two is `tests/test_contribution_api.py`, which
drives the routes over HTTP; this file is the half a hurried change trips over.
"""
import ast
import pathlib
import re

import pytest

import backend.api as api
from backend.agents.contribution import agent as contribution_agent
from backend.learning import contribution as contribution_model


BACKEND = pathlib.Path(api.__file__).parent
CONTRIBUTION_MODULES = [
    BACKEND / "learning" / "contribution.py",
    BACKEND / "agents" / "contribution" / "agent.py",
]

# Ways to run something, and ways to change a file. Named rather than
# pattern-matched, so adding one is a deliberate act somebody has to defend.
FORBIDDEN_CALLS = {
    # execution
    "system", "popen", "spawn", "spawnl", "spawnv", "execv", "execve",
    "eval", "exec", "compile", "run", "check_call", "check_output", "call",
    "import_module", "__import__",
    # filesystem mutation
    "open", "write_text", "write_bytes", "mkdir", "makedirs", "remove",
    "unlink", "rmtree", "copy", "copyfile", "touch", "chmod",
}

# `replace` and `rename` are deliberately ABSENT from the set above. `str.replace`
# is idiomatic and used for path normalisation, and an AST walk cannot tell it
# from `os.replace` by name alone. The filesystem versions are unreachable
# anyway: they need `os`, `pathlib` or `shutil`, and all three are forbidden
# below. Catching the module is stronger than guessing at the attribute.
FORBIDDEN_IMPORTS = {
    "os", "pathlib", "subprocess", "shutil", "importlib", "runpy",
    "multiprocessing", "socket", "git", "tempfile",
}


def _calls(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


def _imports(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize(
    "path", CONTRIBUTION_MODULES, ids=lambda p: p.name,
)
class TestStructural:
    def test_nothing_writes_to_the_filesystem_or_executes(self, path):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offending = _calls(tree) & FORBIDDEN_CALLS
        assert not offending, (
            f"{path.name} calls {sorted(offending)} — the contribution stage "
            f"never writes to the shared repository checkout and never runs "
            f"repository code"
        )

    def test_nothing_imports_a_process_or_a_filesystem_mutator(self, path):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offending = _imports(tree) & FORBIDDEN_IMPORTS
        assert not offending, f"{path.name} imports {sorted(offending)}"


class TestTheOneAllowedStructuralRead:
    def test_ast_parse_is_how_learner_code_is_inspected(self):
        """`ast.parse` builds a syntax tree; it does not import, execute or
        evaluate. It is the whole reason the deterministic checks can exist."""
        source = pathlib.Path(contribution_model.__file__).read_text(encoding="utf-8")
        assert "ast.parse" in source

    def test_a_hostile_patch_is_not_run(self, tmp_path):
        marker = tmp_path / "ran.txt"
        source = (
            "import os\n"
            f"os.makedirs({str(tmp_path / 'x')!r}, exist_ok=True)\n"
            f"open({str(marker)!r}, 'w').write('pwned')\n"
        )
        check = contribution_model.check_scope(
            [contribution_model.PatchFile(path="a.py", contents=source)],
            {"target": [{"file": "a.py", "symbol": "f"}]},
        )
        assert not marker.exists()
        # It was read structurally, which is the point: refusing to run it does
        # not mean refusing to look at it.
        assert check.unparseable == []

    def test_parse_failures_are_findings_rather_than_exceptions(self):
        """A patch that does not parse is something to show the learner, not a
        500. The bounds in `patch_faults` keep `ast.parse` inside the envelope it
        is safe in; this covers what gets through them."""
        check = contribution_model.check_scope(
            [contribution_model.PatchFile(path="a.py", contents="def (:\n")], {},
        )
        assert check.unparseable == ["a.py"]


class TestTheSystemNeverWritesTheCode:
    @pytest.mark.parametrize("prompt,forbids", [
        (contribution_agent._PLAN_SYSTEM, "Do NOT write the code"),
        (contribution_agent._REVIEW_SYSTEM, "DO NOT REWRITE IT"),
    ])
    def test_the_prompts_forbid_producing_code(self, prompt, forbids):
        assert forbids in prompt

    def test_no_endpoint_generates_a_patch(self):
        """The `patch` field is only ever written from the request body. If any
        other route assigned it, the learner would stop being the contributor."""
        source = pathlib.Path(api.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        writers = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if (isinstance(target, ast.Attribute) and target.attr == "patch"
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "state"):
                    writers.append(node.lineno)
        assert len(writers) == 1, (
            f"`state.patch` is assigned at lines {writers}; exactly one writer is "
            f"allowed, and it is the one that stores the request body"
        )

    def test_the_review_prompt_refuses_the_claims_it_cannot_support(self):
        """Correctness, safety and test results are three claims this stage does
        not get to make, and the prompt is the last place they could collapse."""
        prompt = contribution_agent._REVIEW_SYSTEM
        assert "You are NOT being asked whether it is correct" in prompt
        assert "Nothing has been run" in prompt

    def test_the_pr_prompt_does_not_claim_a_passing_suite(self):
        assert "Do not claim the tests pass" in contribution_agent._PR_SYSTEM


class TestScopeIsNotCorrectness:
    def test_passed_means_only_that_nothing_left_the_boundary(self):
        """`ScopeCheck.passed` is the one claim a path comparison supports. A
        syntax error is a real finding and is deliberately not folded in — one
        word meaning two things is how "scope check passed" starts being read as
        "the change is fine"."""
        check = contribution_model.check_scope(
            [contribution_model.PatchFile(path="a.py", contents="def (:\n")],
            {"target": [{"file": "a.py", "symbol": "f"}]},
        )
        assert check.unparseable == ["a.py"]
        assert check.passed is True

    @pytest.mark.parametrize("claim", [
        r"\bcorrect\b", r"\bcorrectly\b", r"\bvalid\b", r"\bverified\b",
        r"\bis safe\b", r"\btests pass\b", r"\bit works\b",
    ])
    def test_the_wording_never_claims_correctness(self, claim):
        """The copy is where the three claims would collapse on screen.

        WHOLE WORDS, not substrings. "You need 4 concepts before implementing
        this safely" is a claim about the LEARNER'S READINESS and is exactly
        right — but a substring match reads `is safe` out of `this safely` and
        fails on copy that says nothing about the patch at all.
        """
        strings = (pathlib.Path(api.__file__).parent.parent / "frontend" / "lib"
                   / "strings.ts").read_text(encoding="utf-8")
        block = strings[strings.index("  contribution: {"):]
        block = block[:block.index("\n  },")].lower()
        assert not re.search(claim, block), (
            f"the contribution copy makes the claim {claim!r} about a change "
            f"that nothing has run"
        )

    def test_the_tests_row_says_what_did_not_happen(self):
        strings = (pathlib.Path(api.__file__).parent.parent / "frontend" / "lib"
                   / "strings.ts").read_text(encoding="utf-8")
        assert "Not executed by CodeOnboard" in strings
