# Persistence for the Layer B repository survey.
#
# Follows the discipline established in backend/learning/store.py: SQLite in the
# same data/sessions.db, an explicit schema version, and a version mismatch
# treated as MISSING rather than migrated. That rule is safe here because a
# survey is derived data — an absent survey degrades the next investigation's
# starting map, never a session (D12); the next onboarding simply recomputes it.
#
# Cache key: (owner_repo, commit_sha, schema_version) — shared across all users
# and all goals per §6. `clone_repo` never updates a checkout in place, so the
# commit is effectively pinned per repository name; if repository updating ever
# lands, the key already accounts for it.

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path("data/sessions.db")

# Bump when the survey payload shape changes incompatibly. Old rows then read
# as missing and the next onboarding writes a fresh survey.
# 2 — `entry_points` gained `perspective` (runtime | public_api). A v1 survey
# cannot answer the public-surface question at all, so it must not be reused
# under the v2 contract: the key includes the version, and an old row simply
# never matches.
SURVEY_SCHEMA_VERSION = 2

_TABLE = """
CREATE TABLE IF NOT EXISTS repo_survey (
    owner_repo      TEXT NOT NULL,
    commit_sha      TEXT NOT NULL,
    schema_version  INTEGER NOT NULL,
    payload_json    TEXT NOT NULL,
    accepted        INTEGER NOT NULL,
    cost_usd        REAL NOT NULL DEFAULT 0,
    seconds         REAL NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    PRIMARY KEY (owner_repo, commit_sha, schema_version)
)
"""


def _connect(db_path: Path | None) -> sqlite3.Connection:
    db_path = Path(db_path) if db_path is not None else DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute(_TABLE)
    return connection


def load_survey(
    owner_repo: str, commit_sha: str, db_path: Path | None = None
) -> dict | None:
    """The stored survey payload, or None when absent or version-mismatched."""
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT payload_json, schema_version FROM repo_survey "
            "WHERE owner_repo = ? AND commit_sha = ? AND schema_version = ?",
            (owner_repo, commit_sha, SURVEY_SCHEMA_VERSION),
        ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row["payload_json"])
    except (json.JSONDecodeError, TypeError):
        return None   # a corrupt row is a missing row, never a crash


def save_survey(
    owner_repo: str,
    commit_sha: str,
    payload: dict,
    *,
    accepted: bool,
    cost_usd: float = 0.0,
    seconds: float = 0.0,
    db_path: Path | None = None,
) -> None:
    with _connect(db_path) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO repo_survey "
            "(owner_repo, commit_sha, schema_version, payload_json, accepted, "
            " cost_usd, seconds, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                owner_repo, commit_sha, SURVEY_SCHEMA_VERSION,
                json.dumps(payload), int(accepted), float(cost_usd),
                float(seconds), time.strftime("%Y-%m-%dT%H:%M:%S"),
            ),
        )
        connection.commit()


def get_or_create_survey(
    *,
    client,
    repo_path: str,
    owner_repo: str,
    commit_sha: str,
    db_path: Path | None = None,
) -> tuple[dict | None, dict]:
    """The survey for this checkout — loaded when stored, produced once otherwise.

    Returns (payload, meta). ``payload`` is None only when a fresh survey could
    not be produced at all; the caller decides what a survey-less onboarding
    does (the investigation runs from the skeleton alone). ``meta`` reports
    where the survey came from and what it cost, for telemetry.
    """
    stored = load_survey(owner_repo, commit_sha, db_path=db_path)
    if stored is not None:
        return stored, {"source": "cache", "cost_usd": 0.0, "seconds": 0.0}

    from backend.repo import survey as survey_module

    run = survey_module.run_survey(client=client, repo_path=repo_path)
    payload = run.survey
    meta = {
        "source": "fresh",
        "accepted": run.accepted,
        "stop_reason": run.exploration.stop_reason,
        "cost_usd": run.exploration.usage.cost_usd(),
        "seconds": run.exploration.seconds,
    }
    if payload is not None:
        save_survey(
            owner_repo, commit_sha, payload,
            accepted=run.accepted,
            cost_usd=meta["cost_usd"], seconds=meta["seconds"],
            db_path=db_path,
        )
    return payload, meta
