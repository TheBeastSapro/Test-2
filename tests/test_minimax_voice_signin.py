"""The MiniMax subscription route, and whether Settings can reach it.

`MiniMaxCliVoiceProvider` narrates through `mmx speech synthesize` signed in with the
operator's plan, so characters come out of an allowance already paid for rather than off
an API balance. `minimax_auth` finds the CLI, reads its sign-in state, distinguishes a
plan sign-in from a key one, and starts the browser flow. The registry routes to it.

Settings offered one thing for that vendor: a box to paste an API key — the route the CLI
adapter exists to avoid. So these are reachability tests.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from forgecast.agent import minimax_auth
from forgecast.api.main import create_app
from forgecast.auth import create_access_token
from forgecast.models import User


@pytest.fixture
def client(user: User):
    with TestClient(create_app()) as test_client:
        test_client.headers["Authorization"] = f"Bearer {create_access_token(user)}"
        yield test_client


def test_the_status_endpoint_answers(client):
    answer = client.get("/api/voice/minimax")
    assert answer.status_code == 200
    body = answer.json()
    # The same field names the two agent backends use, so one front-end reader serves
    # all three — a fourth shape would mean a fourth branch, and the branch nobody tests
    # is the one that shows a blank box.
    for field in ("ok", "headline", "detail", "cli_found", "signed_in", "can_login",
                  "with_api_key", "fixes"):
        assert field in body, field
    assert body["install_hint"] == minimax_auth.INSTALL_HINT


def test_signed_in_with_a_key_is_reported_separately_from_signed_in(client):
    """They are different bills. A CLI authenticated with a key charges per character
    exactly like the HTTP route, so folding it into `signed_in` would tell the operator
    their narration is on the plan while it draws down a balance."""
    body = client.get("/api/voice/minimax").json()
    assert body["with_api_key"] is not None
    assert "with_api_key" in body and "signed_in" in body


def test_the_endpoints_require_a_user():
    with TestClient(create_app()) as anonymous:
        assert anonymous.get("/api/voice/minimax").status_code == 401
        assert anonymous.post("/api/voice/minimax/login").status_code == 401
        assert anonymous.post("/api/voice/minimax/install").status_code == 401


def test_login_reports_rather_than_raising_when_the_cli_is_absent(client):
    """The CLI is not installed in this environment, so this is the real path."""
    answer = client.post("/api/voice/minimax/login")
    assert answer.status_code == 200
    body = answer.json()
    assert body["ok"] is False
    assert minimax_auth.INSTALL_HINT in body["message"]


def test_the_settings_page_offers_the_subscription_and_not_only_a_key(client):
    """The whole defect: the page had one control for this vendor and it was the
    expensive one."""
    page = client.get("/settings").text
    assert 'id="minimax-voice"' in page
    assert "mmxCheck" in page
    # It names the channel setting that actually uses this route, because a sign-in
    # nobody points a channel at changes nothing.
    assert "minimax-voice-cli" in page


def test_the_page_says_what_the_key_box_below_it_does_instead(client):
    page = client.get("/settings").text
    assert "bills per character" in page


def test_signing_in_goes_through_the_shared_terminal_launcher():
    """It used to build its own, interpolating the command into an AppleScript string —
    where quoting each argument is not protection, because AppleScript is not a shell."""
    import inspect

    source = inspect.getsource(minimax_auth.start_login)
    assert "open_terminal" in source
    assert "osascript" not in source
    assert "do script" not in source
