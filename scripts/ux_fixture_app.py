"""The app, serving the UX fixture database instead of the real one.

    uv run python -m uvicorn scripts.ux_fixture_app:app --port 8107

`SESSIONS_DB_PATH` is a module constant rather than configuration, deliberately:
there is exactly one database in production and an environment variable that
could point the app somewhere else is a foot-gun the app has no use for. This
overrides it for a UI pass, in a file that is obviously not the app.

Pairs with `scripts/seed_ux_fixture.py`, which writes the database.
"""

from __future__ import annotations

import os
from pathlib import Path

import backend.api as api
from backend.api import app  # noqa: F401 — re-exported for uvicorn

_DB = Path(os.environ.get("CODEONBOARD_UX_DB", "data/ux-fixture.db")).resolve()
if not _DB.exists():
    raise SystemExit(
        f"{_DB} does not exist — run scripts/seed_ux_fixture.py first"
    )

api.SESSIONS_DB_PATH = _DB
