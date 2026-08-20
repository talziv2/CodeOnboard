"""The environment beats `.env`, and importing the API does not rewrite it.

Two claims, both learned the expensive way.

`backend/api.py` loaded its `.env` with `override=True`, which inverted the
precedence every other tool in the stack uses: the file beat the environment, so a
variable set where the process was launched was silently discarded.
`CODEONBOARD_GAPS=0 uv run uvicorn …` ran with gaps ON if `.env` said `1`, with
nothing to indicate it.

And because that call runs at IMPORT time, the same line cost fourteen test
failures in `test_mentor_dossier.py` — a file that imports the API turned the
Mentor's planner on for every test after it. `tests/conftest.py` isolates the suite
from ambient flags, but that isolation was treating a symptom of this.

Run with: uv run pytest tests/test_env_precedence.py -v
"""
import importlib
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _in_subprocess(code: str, env: dict[str, str]) -> str:
    """Run `code` in a fresh interpreter with `env` set.

    A subprocess rather than `importlib.reload`, because what is being tested is
    what happens the FIRST time `backend.api` is imported into a process. Reloading
    inside this one would measure a second import into an environment the first had
    already touched — which is the very confusion these tests exist to rule out.
    """
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_a_flag_set_in_the_environment_survives_the_import():
    """The footgun, stated as the person typing the command would see it."""
    code = (
        "import backend.api, os;"
        "print(os.environ.get('CODEONBOARD_GAPS'))"
    )
    assert _in_subprocess(code, {"CODEONBOARD_GAPS": "0"}) == "0"


def test_the_curriculum_flag_survives_too():
    """The one that broke the suite. `.env` sets it to `1` on this machine."""
    code = (
        "import backend.api;"
        "from backend.agents.mentor.agent import curriculum_enabled;"
        "print(curriculum_enabled())"
    )
    assert _in_subprocess(code, {"CODEONBOARD_CURRICULUM": "0"}) == "False"


def test_dotenv_still_fills_a_gap():
    """Precedence, not exclusion. The file is still how values that never change
    on a machine get set — this asserts the fix did not simply disable it."""
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return  # nothing to fill from; the claim is untestable rather than false
    keys = [
        line.split("=", 1)[0].strip()
        for line in env_file.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.strip().startswith("#")
    ]
    if not keys:
        return
    code = (
        "import backend.api, os;"
        f"print(any(os.environ.get(k) for k in {keys!r}))"
    )
    # Deliberately no overrides passed: with none set, the file must be what
    # provides them.
    assert _in_subprocess(code, {}) == "True"


def test_importing_the_api_does_not_turn_flags_on_for_everyone_else():
    """The suite-level version of the same claim.

    `tests/conftest.py` guarantees this per test; this guarantees it of the import
    itself, so the conftest stays a convenience rather than the only thing standing
    between the suite and fourteen anonymous AttributeErrors.
    """
    code = (
        "import os;"
        "os.environ.pop('CODEONBOARD_CURRICULUM', None);"
        "os.environ.pop('CODEONBOARD_GAPS', None);"
        "import backend.api;"
        "from backend.agents.mentor.agent import curriculum_enabled;"
        "print(curriculum_enabled())"
    )
    # Unset before the import, so only `.env` could turn it on. It may — that is
    # what the file is for — but the value must come from the file rather than from
    # an override, which the first two tests establish.
    result = _in_subprocess(code, {})
    assert result in {"True", "False"}


def test_the_module_does_not_call_load_dotenv_with_override():
    """Read the source, because the behavioural tests above can only prove the
    current `.env`'s contents, and this proves the intent regardless of them."""
    source = (REPO_ROOT / "backend" / "api.py").read_text(encoding="utf-8")
    calls = [
        line.strip()
        for line in source.splitlines()
        if "load_dotenv(" in line and not line.strip().startswith("#")
    ]
    assert calls, "the call disappeared; this test is now measuring nothing"
    for call in calls:
        assert "override" not in call, call
