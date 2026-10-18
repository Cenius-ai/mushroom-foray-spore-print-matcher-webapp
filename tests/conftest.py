"""Test fixtures: every test runs against a throwaway SQLite file seeded on boot."""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Configure the app before it is imported anywhere: a temp database, a stable
# test secret and a private upload directory.
_TMP = Path(tempfile.mkdtemp(prefix="foray-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["UPLOAD_DIR"] = str(_TMP / "uploads")
os.environ["SESSION_SECRET"] = "test-secret-4f1c9a2e7b-donotuseinprod"
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"

DEMO_IDENTIFIER = "cenius@cenius.ai"
DEMO_PASSWORD = "cenius"


@pytest.fixture(scope="session")
def app_module():
    import app as app_module

    return app_module


@pytest.fixture()
def anon_client(app_module):
    """A client with no session cookie (fresh cookie jar per test)."""
    from fastapi.testclient import TestClient

    with TestClient(app_module.app) as fresh:
        yield fresh


@pytest.fixture(scope="session")
def demo_client(app_module):
    """The seeded demo account, signed in through the JSON API."""
    from fastapi.testclient import TestClient

    with TestClient(app_module.app) as signed_in:
        response = signed_in.post(
            "/api/auth/login", json={"username": DEMO_IDENTIFIER, "password": DEMO_PASSWORD}
        )
        assert response.status_code == 200, response.text
        yield signed_in


@pytest.fixture(scope="session")
def second_user(app_module):
    """A second account with its own session, used for ownership checks."""
    from fastapi.testclient import TestClient

    with TestClient(app_module.app) as other:
        response = other.post(
            "/api/auth/register",
            json={"username": "rowan", "password": "rowanpassword"},
        )
        assert response.status_code == 201, response.text
        yield other


def csrf_token_from(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "sign-in form should carry a CSRF token"
    return match.group(1)


def form_login(client, identifier: str, password: str, mode: str = "signin"):
    """Drive the server-rendered sign-in card exactly like a browser would."""
    page = client.get("/login")
    token = csrf_token_from(page.text)
    return client.post(
        "/login",
        data={"username": identifier, "password": password, "mode": mode, "csrf_token": token},
        follow_redirects=False,
    )
