"""Cloud backup, reachable from the application.

The package under `forgecast/cloud/` was complete and tested from the day it was
written and had no HTTP end and no page, so from inside the app it was
indistinguishable from a feature that did not exist. It was reported as missing.
These tests are about the door, not the room behind it — `tests/test_cloud.py`
already exercises the snapshot, the transport and the restore round trip.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from forgecast.api.main import create_app


@pytest.fixture(autouse=True)
def forget_cloud_config():
    """Each test starts with no cloud config.

    `storage/cloud.json` is a file, not a table, so the `fresh_database` fixture does
    not touch it — one test saving a token left the next one authorised, and a test
    asserting "you cannot do this before connecting" passed only when it ran first.
    """
    from forgecast.cloud import config as cloud_config

    path = cloud_config.default_path()
    path.unlink(missing_ok=True)
    yield
    path.unlink(missing_ok=True)


@pytest.fixture
def client(user):
    with TestClient(create_app()) as test_client:
        token = test_client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "supersecret"},
        ).json()["access_token"]
        test_client.headers["Authorization"] = f"Bearer {token}"
        yield test_client


def test_the_endpoints_exist_and_need_an_account():
    """Every one of them, not just the read. A write endpoint left open here would let
    anyone who can reach the port push this install's scripts to their own GitHub."""
    with TestClient(create_app()) as anon:
        for method, path in (("get", "/api/cloud"), ("get", "/api/cloud/plan"),
                             ("post", "/api/cloud/enable"), ("post", "/api/cloud/device"),
                             ("post", "/api/cloud/device/poll"),
                             ("post", "/api/cloud/repository"),
                             ("post", "/api/cloud/backup"), ("post", "/api/cloud/restore")):
            answered = getattr(anon, method)(path)
            assert answered.status_code == 401, f"{method.upper()} {path} is open"


def test_status_is_readable_on_a_fresh_install_and_says_it_is_off(client):
    body = client.get("/api/cloud").json()
    assert body["enabled"] is False
    assert body["active"] is False
    assert body["authorised"] is False
    # No credential in the response, in any shape. Not even the ciphertext: it is one
    # leaked .env away from being the token, and API bodies get pasted into support
    # threads.
    flat = str(body).lower()
    assert "token" not in flat and "ciphertext" not in flat


def test_what_would_be_sent_is_answerable_while_the_feature_is_off(client):
    """The question an operator should ask first, and the one they cannot ask anywhere
    else. Requiring the feature to be on before it can be answered means enabling the
    thing you are trying to evaluate."""
    body = client.get("/api/cloud/plan").json()
    assert body["ok"] is True
    assert "files" in body and "excluded_count" in body


def test_turning_it_off_keeps_the_credential(client):
    """Off means "do not talk to GitHub", not "forget who I am". Clearing the token on
    a toggle turns a week's pause into a full re-authorisation."""
    from forgecast.cloud import config as cloud_config

    stored = cloud_config.load()
    stored.set_token("gho_pretend")
    stored.enabled = True
    stored.save()

    client.post("/api/cloud/enable", json={"enabled": False})
    after = cloud_config.load()
    assert after.enabled is False
    assert after.token == "gho_pretend"


def test_polling_before_a_sign_in_started_is_refused_not_guessed(client):
    answered = client.post("/api/cloud/device/poll")
    assert answered.status_code == 409


def test_a_repository_cannot_be_set_before_there_is_an_account_to_make_it_on(client):
    answered = client.post("/api/cloud/repository", json={"repository": "backup"})
    assert answered.status_code == 409
    assert "connect to GitHub first" in answered.json()["detail"]


def test_the_settings_page_offers_it(client):
    """The whole point. A working feature with no way in is a missing feature."""
    body = client.get("/settings").text
    assert 'data-panel="cloud"' in body
    assert "Cloud backup" in body
    # And it states the thing that is easy to assume and expensive to discover.
    assert "Renders do not" in body
