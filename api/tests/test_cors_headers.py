"""A denied cross-origin request has to carry CORS headers too.

A browser cannot read a cross-origin response that has no Access-Control-Allow-Origin,
whatever its status. When the access guard ran outside CORSMiddleware its 401 reached
the browser bare, the fetch rejected, and the hosted web app reported the API as
unreachable — the status was right and the header was missing. These tests pin the
middleware order that keeps the real status readable.
"""

import importlib
import json
import os

import pytest
from fastapi.testclient import TestClient

ORIGIN = "https://schooltrace.vercel.app"
HOST = "api.example.test"


@pytest.fixture
def hosted_client(monkeypatch, tmp_path):
    from app.security import password_hash

    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SCHOOLTRACE_PUBLIC_HOSTS", HOST)
    monkeypatch.setenv("SCHOOLTRACE_ALLOWED_ORIGINS", ORIGIN)
    monkeypatch.setenv(
        "SCHOOLTRACE_USERS",
        json.dumps({"admin": {"password_hash": password_hash("pw"), "role": "admin", "workspaces": []}}),
    )

    import app.main
    import app.security

    importlib.reload(app.security)
    importlib.reload(app.main)
    try:
        with TestClient(app.main.app, base_url=f"https://{HOST}") as client:
            yield client
    finally:
        # The reloaded modules read the environment at import, so restore them for
        # every other test in the session.
        for name in ("SCHOOLTRACE_PUBLIC_HOSTS", "SCHOOLTRACE_ALLOWED_ORIGINS", "SCHOOLTRACE_USERS"):
            os.environ.pop(name, None)
        importlib.reload(app.security)
        importlib.reload(app.main)


def test_unauthenticated_request_is_401_the_browser_can_read(hosted_client):
    response = hosted_client.get("/api/coverage", headers={"Origin": ORIGIN})
    assert response.status_code == 401
    assert response.headers.get("access-control-allow-origin") == ORIGIN
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_health_answers_the_probe_with_cors(hosted_client):
    response = hosted_client.get("/api/health", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == ORIGIN


def test_signing_in_then_reading_coverage_succeeds(hosted_client):
    login = hosted_client.post(
        "/api/access/login",
        json={"username": "admin", "password": "pw"},
        headers={"Origin": ORIGIN},
    )
    assert login.status_code == 200, login.text
    assert login.headers.get("access-control-allow-origin") == ORIGIN
    # Any authenticated route will do; this one only has to get past the guard.
    after = hosted_client.get("/api/workspaces", headers={"Origin": ORIGIN})
    assert after.status_code == 200, after.text
    assert after.headers.get("access-control-allow-origin") == ORIGIN
