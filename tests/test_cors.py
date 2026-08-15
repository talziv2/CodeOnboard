"""
Pytest tests for the CORS allow-list in backend/api.py.
Run with: uv run pytest tests/test_cors.py -v

A browser reports a blocked cross-origin call as an opaque "Failed to fetch",
indistinguishable from the backend being down — so the allow-list is worth
pinning down in a test rather than discovering by hand in the UI.

No API key, no database and no network: only the preflight handshake is
exercised, which the middleware answers before any route runs.
"""
import importlib

import pytest
from fastapi.testclient import TestClient

import backend.api as api


def preflight(client: TestClient, origin: str):
    return client.options(
        "/repo/check",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )


@pytest.mark.parametrize(
    "origin", ["http://localhost:3000", "http://127.0.0.1:3000"]
)
def test_both_dev_host_spellings_are_allowed(origin):
    # localhost and 127.0.0.1 are one machine but two origins to a browser.
    # Whichever one the dev happens to open, the frontend has to work.
    response = preflight(TestClient(api.app), origin)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_unknown_origin_is_rejected():
    response = preflight(TestClient(api.app), "https://evil.example.com")

    assert "access-control-allow-origin" not in response.headers


def test_env_override_replaces_the_default_list(monkeypatch):
    monkeypatch.setenv(
        "CODEONBOARD_ALLOWED_ORIGINS", "http://localhost:3010, http://localhost:3011"
    )
    reloaded = importlib.reload(api)
    try:
        assert reloaded.ALLOWED_ORIGINS == [
            "http://localhost:3010",
            "http://localhost:3011",
        ]

        client = TestClient(reloaded.app)
        assert (
            preflight(client, "http://localhost:3010").headers[
                "access-control-allow-origin"
            ]
            == "http://localhost:3010"
        )
        # The defaults are replaced, not extended.
        assert (
            "access-control-allow-origin"
            not in preflight(client, "http://localhost:3000").headers
        )
    finally:
        # Other test modules import this module object; leave it as they expect.
        monkeypatch.delenv("CODEONBOARD_ALLOWED_ORIGINS")
        importlib.reload(api)
