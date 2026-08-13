# Persistence for the Investigation Dossier (Stage 4).
#
# The dossier is produced once at onboarding and consumed for the whole life of
# the learning session — by Teaching on every lesson and by the Mutator on every
# confusion signal. Without persistence it dies with the request that made it,
# which is why this lands before those consumers migrate.
#
# KEYED TO THE SESSION, NOT THE REPOSITORY. A survey is goal-agnostic and shared
# per (repo, commit); a dossier is goal-SPECIFIC and must never leak across
# goals. It is stored against the learning graph's session_id, with the commit
# recorded alongside so a checkout that moved underneath invalidates it rather
# than pointing at drifted code.
#
# D12 IS THE GOVERNING RULE. A missing, corrupt or version-mismatched dossier
# reads as *unavailable* — never migrated, never regenerated behind the user's
# back. Every consumer has a defined behaviour for absent, so an old session, a
# schema bump or a moved commit degrades lesson richness and nothing more.

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path("data/sessions.db")

# Bump when the dossier payload shape changes incompatibly. Old rows then read
# as unavailable and sessions fall back to their no-dossier behaviour.
DOSSIER_SCHEMA_VERSION = 1

_TABLE = """
CREATE TABLE IF NOT EXISTS investigation (
    session_id      TEXT PRIMARY KEY,
    commit_sha      TEXT NOT NULL,
    schema_version  INTEGER NOT NULL,
    payload_json    TEXT NOT NULL,
    accepted        INTEGER NOT NULL DEFAULT 0,
    used_survey     INTEGER NOT NULL DEFAULT 0,
    stop_reason     TEXT,
    cost_usd        REAL NOT NULL DEFAULT 0,
    seconds         REAL NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
)
"""


def _connect(db_path: Path | None) -> sqlite3.Connection:
    db_path = Path(db_path) if db_path is not None else DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute(_TABLE)
    return connection


def save_investigation(
    session_id: str,
    commit_sha: str,
    investigation: dict,
    db_path: Path | None = None,
) -> None:
    """Persist the investigation for one session. Silent no-op without a dossier."""
    dossier = (investigation or {}).get("dossier")
    if not dossier:
        return
    with _connect(db_path) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO investigation "
            "(session_id, commit_sha, schema_version, payload_json, accepted, "
            " used_survey, stop_reason, cost_usd, seconds, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id, commit_sha, DOSSIER_SCHEMA_VERSION,
                json.dumps(investigation),
                int(bool(investigation.get("accepted"))),
                int(bool(investigation.get("used_survey"))),
                str(investigation.get("stop_reason") or ""),
                float(investigation.get("cost_usd") or 0.0),
                float(investigation.get("seconds") or 0.0),
                time.strftime("%Y-%m-%dT%H:%M:%S"),
            ),
        )
        connection.commit()


def load_investigation(
    session_id: str,
    commit_sha: str | None = None,
    db_path: Path | None = None,
) -> dict | None:
    """The stored investigation, or None when it is unavailable for any reason.

    Unavailable means: absent, a schema version this build does not understand,
    unreadable JSON, structurally not a dossier, or recorded against a different
    commit than the one now checked out. Every one of those is the same answer
    to the caller — D12 makes "absent" a supported state, so there is nothing to
    gain from distinguishing them at the call site.
    """
    try:
        with _connect(db_path) as connection:
            row = connection.execute(
                "SELECT payload_json, schema_version, commit_sha FROM investigation "
                "WHERE session_id = ?",
                (session_id,),
            ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    if row["schema_version"] != DOSSIER_SCHEMA_VERSION:
        return None
    if commit_sha is not None and row["commit_sha"] != commit_sha:
        # The checkout moved: anchors recorded against the old commit may point
        # at drifted code. Treated as unavailable rather than silently trusted.
        return None
    try:
        payload = json.loads(row["payload_json"])
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("dossier"), dict):
        return None
    return payload


def delete_investigation(session_id: str, db_path: Path | None = None) -> None:
    with _connect(db_path) as connection:
        connection.execute(
            "DELETE FROM investigation WHERE session_id = ?", (session_id,)
        )
        connection.commit()
