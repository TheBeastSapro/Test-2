"""What makes an instance safe to expose: closed registration and signed media.

Both of these guard the same failure — an instance that becomes reachable and hands
things to strangers. They are tested together because they are the checklist you run
before pointing a tunnel at this thing.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_api import auth, register

from forgecast.api.main import app
from forgecast.api.media import relative_path, sign_url
from forgecast.config import Settings, get_settings


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def closed_signup():
    """Close registration for one test, then restore whatever it was.

    Mutating the cached settings object rather than the environment, because
    `get_settings` is lru_cached and `db.engine` was built from it at import time —
    clearing the cache mid-suite would hand out a settings object pointing at a
    different database than the one the session factory is bound to.
    """
    settings = get_settings()
    original = settings.allow_signup
    settings.allow_signup = False
    yield settings
    settings.allow_signup = original


# ------------------------------------------------------------------ registration


def test_registration_is_closed_by_default():
    """The shipped default must be the restrictive one.

    A private instance that becomes reachable must not accept strangers because
    nobody remembered to turn signup off.

    Asserted against the field default rather than an instance: this suite sets
    FORGECAST_ALLOW_SIGNUP in the environment, and an environment variable would
    override the default being tested.
    """
    assert Settings.model_fields["allow_signup"].default is False


def test_api_signup_is_refused_when_closed(client, closed_signup):
    response = client.post(
        "/api/auth/signup",
        json={"email": "stranger@example.com", "password": "supersecret"},
    )
    assert response.status_code == 403
    assert "bootstrap" in response.json()["detail"]


def test_web_signup_is_refused_when_closed(client, closed_signup):
    response = client.post(
        "/login",
        data={"email": "stranger@example.com", "password": "supersecret",
              "action": "signup"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)
    assert "Registration+is+closed" in response.headers["location"]


def test_the_signup_button_is_hidden_when_closed(client, closed_signup):
    body = client.get("/login").text
    assert 'value="signup"' not in body
    assert "private instance" in body


def test_existing_accounts_can_still_sign_in_when_closed(client, closed_signup):
    # Created while open, in a fixture that runs before signup is closed.
    settings = get_settings()
    settings.allow_signup = True
    register(client, "owner@example.com")
    settings.allow_signup = False

    response = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "supersecret"},
    )
    assert response.status_code == 200, response.text


# -------------------------------------------------------------------- media URLs


def test_the_storage_directory_is_not_mounted_statically(client):
    """Regression: /files served every run's media with no authorisation at all."""
    storage = get_settings().storage_dir
    storage.mkdir(parents=True, exist_ok=True)
    (storage / "leak.txt").write_text("secret", encoding="utf-8")

    assert client.get("/files/leak.txt").status_code == 404


def test_a_signed_url_serves_the_file(client):
    storage = get_settings().storage_dir
    (storage / "clip.txt").write_text("payload", encoding="utf-8")

    url = sign_url(storage / "clip.txt", user_id=1)
    assert url is not None
    response = client.get(url)
    assert response.status_code == 200
    assert response.text == "payload"
    # A signed URL must never be cached by a shared proxy.
    assert "private" in response.headers["cache-control"]


def test_an_unsigned_request_is_refused(client):
    storage = get_settings().storage_dir
    (storage / "clip.txt").write_text("payload", encoding="utf-8")

    assert client.get("/media/clip.txt").status_code == 422        # no params
    assert client.get(
        "/media/clip.txt?uid=1&exp=99999999999&sig=deadbeef"
    ).status_code == 403


def test_a_tampered_path_is_refused(client):
    """The signature covers the path, so pointing a valid one elsewhere fails."""
    storage = get_settings().storage_dir
    (storage / "clip.txt").write_text("payload", encoding="utf-8")
    (storage / "other.txt").write_text("not yours", encoding="utf-8")

    url = sign_url(storage / "clip.txt", user_id=1)
    assert url is not None
    moved = url.replace("clip.txt", "other.txt")
    assert client.get(moved).status_code == 403


def test_a_signature_from_another_user_does_not_transfer(client):
    storage = get_settings().storage_dir
    (storage / "clip.txt").write_text("payload", encoding="utf-8")

    url = sign_url(storage / "clip.txt", user_id=1)
    assert url is not None
    assert client.get(url.replace("uid=1", "uid=2")).status_code == 403


def test_an_expired_url_is_refused(client):
    storage = get_settings().storage_dir
    (storage / "clip.txt").write_text("payload", encoding="utf-8")

    url = sign_url(storage / "clip.txt", user_id=1, ttl=-10)
    assert url is not None
    response = client.get(url)
    assert response.status_code == 403
    assert response.json()["detail"] == "link expired"


def test_traversal_cannot_be_signed(tmp_path):
    outside = tmp_path / "passwd"
    outside.write_text("root:x:0:0", encoding="utf-8")
    assert relative_path(outside) is None
    assert sign_url(outside, user_id=1) is None


def test_a_traversal_url_is_refused_even_if_signed(client):
    """Belt and braces: the route re-checks containment after verifying the HMAC."""
    from forgecast.api.media import _signature

    relative = "../../etc/passwd"
    expires = int(time.time()) + 600
    signature = _signature(relative, 1, expires)
    response = client.get(
        f"/media/{relative}?uid=1&exp={expires}&sig={signature}"
    )
    assert response.status_code in (403, 404)


def test_video_requests_can_seek(client):
    """A Range request has to return 206, or scrubbing a render is broken."""
    storage = get_settings().storage_dir
    (storage / "seek.bin").write_bytes(b"0123456789")

    url = sign_url(storage / "seek.bin", user_id=1)
    assert url is not None
    response = client.get(url, headers={"Range": "bytes=2-5"})
    assert response.status_code == 206, response.headers
    assert response.content == b"2345"


# ------------------------------------------------------- URLs the app hands out


def test_run_artifact_urls_are_signed(client):
    token = register(client, "signed@example.com")
    channel = client.post(
        "/api/channels", headers=auth(token),
        json={"name": "C", "niche": "n", "target_duration_seconds": 20,
              "voice_id": "v"},
    ).json()["id"]
    run = client.post(
        "/api/runs", headers=auth(token),
        json={"channel_id": channel, "topic": "Signed URL check",
              "pipeline": "faceless_shorts"},
    )
    assert run.status_code == 201, run.text

    detail = client.get(f"/api/runs/{run.json()['id']}", headers=auth(token)).json()
    for artifact in detail["artifacts"]:
        if artifact["url"]:
            assert artifact["url"].startswith("/media/")
            assert "sig=" in artifact["url"] and "exp=" in artifact["url"]


def test_signing_declines_a_path_outside_storage():
    assert sign_url(Path("/etc/hostname"), user_id=1) is None
