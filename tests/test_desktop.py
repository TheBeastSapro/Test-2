"""The desktop application: first-run preparation and the loopback sign-in handoff.

The handoff tests are the important half. It is the only path in the system that turns
something other than a password into a session, so every condition that gates it gets
its own test — and each one is written as the attack it prevents, not as the branch it
covers.
"""

from __future__ import annotations

import base64
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from forgecast.api import local as local_routes
from forgecast.api.main import app
from forgecast.auth import hash_password
from forgecast.config import get_settings
from forgecast.desktop import bootstrap, supervisor
from forgecast.models import User

TOKEN = "test-handoff-token-0123456789"


@pytest.fixture
def client() -> TestClient:
    """A client whose peer address is a real loopback address.

    TestClient reports "testclient" as the peer by default, which `_is_loopback`
    correctly rejects — so without this every handoff test would pass for the wrong
    reason, and the one test that checks a non-loopback request would prove nothing.
    """
    with TestClient(app, client=("127.0.0.1", 54321)) as test_client:
        yield test_client


@pytest.fixture
def desktop():
    """Turn on desktop mode for one test and put it back afterwards.

    The settings object is mutated rather than the environment for the reason given in
    test_private_instance: `get_settings` is cached and the engine was built from it.
    """
    settings = get_settings()
    previous = (settings.local_mode, settings.local_handoff_token,
                settings.owner_email, settings.local_handoff_ttl_seconds)
    settings.local_mode = True
    settings.local_handoff_token = TOKEN
    settings.owner_email = ""
    settings.local_handoff_ttl_seconds = 300
    # Each test starts its own clock; otherwise the module's import-time start makes
    # the whole suite look expired once it has run for five minutes.
    local_routes._STARTED_AT = time.monotonic()
    yield settings
    (settings.local_mode, settings.local_handoff_token,
     settings.owner_email, settings.local_handoff_ttl_seconds) = previous


@pytest.fixture
def owner(session) -> User:
    user = User(email="owner@localhost", hashed_password=hash_password("x" * 14))
    session.add(user)
    session.commit()
    return user


# ------------------------------------------------------------------ the handoff


def test_the_handoff_signs_the_window_in(client, desktop, owner):
    response = client.get(f"/local/session?t={TOKEN}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert "forgecast_session" in response.cookies

    # And the cookie is a real session, not a decoration.
    assert client.get("/", follow_redirects=False).status_code == 200


def test_a_normal_deployment_has_no_handoff_route(client, owner):
    """`local_mode` is off unless the launcher turned it on, and off means gone."""
    assert get_settings().local_mode is False
    assert client.get(f"/local/session?t={TOKEN}").status_code == 404


def test_a_wrong_token_does_not_sign_anyone_in(client, desktop, owner):
    response = client.get("/local/session?t=not-the-token", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert "forgecast_session" not in response.cookies


def test_an_empty_token_is_not_a_free_pass(client, desktop, owner):
    """Regression guard: a comparison against "" must not succeed when the setting is
    also empty at some future point."""
    response = client.get("/local/session", follow_redirects=False)
    assert "forgecast_session" not in response.cookies


def test_the_handoff_expires(client, desktop, owner):
    """The window opens within a second of launch. Anything later is not the window."""
    local_routes._STARTED_AT = time.monotonic() - 10_000
    response = client.get(f"/local/session?t={TOKEN}", follow_redirects=False)
    assert response.status_code == 303
    assert "expired" in response.headers["location"].lower()
    assert "forgecast_session" not in response.cookies


def test_a_forwarded_port_is_not_the_local_operator(client, desktop, owner, monkeypatch):
    """The whole reason this is a token and not a localhost check.

    A tunnel, a forwarded port, or any other process on the machine arrives on
    127.0.0.1. Peer address alone must never authorise anything.
    """
    monkeypatch.setattr(local_routes, "_is_loopback", lambda _request: False)
    assert client.get(f"/local/session?t={TOKEN}").status_code == 404


def test_loopback_detection(monkeypatch):
    class Fake:
        def __init__(self, host):
            self.client = type("C", (), {"host": host})()

    assert local_routes._is_loopback(Fake("127.0.0.1"))
    assert local_routes._is_loopback(Fake("::1"))
    assert local_routes._is_loopback(Fake("localhost"))
    assert not local_routes._is_loopback(Fake("10.0.0.4"))
    assert not local_routes._is_loopback(Fake("example.com"))
    # No reported peer must fail closed, not open.
    assert not local_routes._is_loopback(type("R", (), {"client": None})())


# ------------------------------------------------------------- owner resolution


def test_a_single_account_is_the_owner(session, desktop, owner):
    assert local_routes._owner(session).id == owner.id


def test_two_accounts_and_no_configured_owner_is_ambiguous(session, desktop, owner):
    """Signing in as "whoever is first" would be a lottery, so it declines instead."""
    session.add(User(email="second@localhost", hashed_password=hash_password("y" * 14)))
    session.commit()
    assert local_routes._owner(session) is None


def test_a_configured_owner_wins_over_the_first_row(session, desktop, owner):
    second = User(email="second@localhost", hashed_password=hash_password("y" * 14))
    session.add(second)
    session.commit()
    desktop.owner_email = "second@localhost"
    assert local_routes._owner(session).id == second.id


def test_a_configured_owner_that_does_not_exist_resolves_to_nobody(session, desktop, owner):
    desktop.owner_email = "ghost@localhost"
    assert local_routes._owner(session) is None


# -------------------------------------------------------------------- quitting


def test_quit_is_refused_on_a_normal_deployment(client, owner):
    client.cookies.clear()
    assert client.post("/local/quit").status_code in (401, 404)


def test_quit_stops_the_app(client, desktop, owner):
    local_routes.SHUTDOWN.clear()
    client.get(f"/local/session?t={TOKEN}", follow_redirects=False)
    assert client.post("/local/quit").status_code == 200
    assert local_routes.SHUTDOWN.is_set()
    local_routes.SHUTDOWN.clear()


def test_status_reports_what_the_app_can_do(client, desktop):
    payload = client.get("/local/status").json()
    assert payload["local_mode"] is True
    assert isinstance(payload["ffmpeg"], bool)


# ------------------------------------------------------------------- bootstrap


def test_first_run_generates_secrets(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    values = bootstrap.ensure_env_file(tmp_path)

    assert len(values["FORGECAST_SECRET_KEY"]) >= 40
    assert values["FORGECAST_ALLOW_SIGNUP"] == "false"
    # A password is generated rather than fixed, because a predictable local password
    # becomes a real hole the moment the port is forwarded.
    assert len(values["FORGECAST_OWNER_PASSWORD"]) >= 12


def test_the_generated_encryption_key_is_a_valid_fernet_key(tmp_path: Path):
    """It is generated with the standard library, so its format has to be asserted.

    A key that Fernet rejects would not surface until the first provider credential is
    saved, which is a long way from the code that made it.
    """
    from cryptography.fernet import Fernet

    values = bootstrap.ensure_env_file(tmp_path)
    key = values["FORGECAST_ENCRYPTION_KEY"]
    assert len(base64.urlsafe_b64decode(key)) == 32
    box = Fernet(key.encode())
    assert box.decrypt(box.encrypt(b"secret")) == b"secret"


def test_existing_secrets_are_never_rewritten(tmp_path: Path):
    """Regenerating the encryption key would orphan every stored provider credential."""
    first = bootstrap.ensure_env_file(tmp_path)
    second = bootstrap.ensure_env_file(tmp_path)
    assert first["FORGECAST_ENCRYPTION_KEY"] == second["FORGECAST_ENCRYPTION_KEY"]
    assert first["FORGECAST_SECRET_KEY"] == second["FORGECAST_SECRET_KEY"]


def test_a_hand_written_setting_survives_and_gaps_are_filled(tmp_path: Path):
    (tmp_path / ".env").write_text("FORGECAST_PROVIDER_MODE=live\n")
    values = bootstrap.ensure_env_file(tmp_path)
    assert values["FORGECAST_PROVIDER_MODE"] == "live"
    assert "FORGECAST_SECRET_KEY" in values

    body = (tmp_path / ".env").read_text()
    assert body.count("FORGECAST_PROVIDER_MODE") == 1


def test_the_install_fingerprint_changes_with_the_dependencies(tmp_path: Path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[project]\nname='x'\n")
    before = bootstrap._fingerprint(tmp_path)
    pyproject.write_text("[project]\nname='x'\ndependencies=['httpx']\n")
    assert bootstrap._fingerprint(tmp_path) != before


def test_the_install_fingerprint_changes_when_the_folder_moves(tmp_path: Path):
    """Regression: a moved install must reinstall, or it can run the wrong code.

    `pip install -e .` writes a finder into the virtualenv recording the project's
    absolute path. Move the folder and that path is stale. It is usually harmless —
    the launcher puts the real project directory first on `sys.path` — but if the old
    path still exists, which is exactly what copying the folder produces, anything
    importing `forgecast` without the launcher loads the *original* folder's code while
    writing to the copy's database.

    Measured before this was fixed: with a copy left at the old location, a bare
    `python -c "import forgecast"` inside the moved venv resolved to the old folder.
    """
    first = tmp_path / "drive-d" / "Forgecast"
    second = tmp_path / "drive-e" / "Forgecast"
    for path in (first, second):
        path.mkdir(parents=True)
        (path / "pyproject.toml").write_text("[project]\nname='forgecast'\n")

    assert bootstrap._fingerprint(first) != bootstrap._fingerprint(second)


def test_an_unmoved_install_is_not_reinstalled_on_every_launch(tmp_path: Path):
    """The other half of the same rule: a normal launch must stay fast.

    The fingerprint is what makes the expensive step skippable, so it has to be stable
    across launches that changed nothing.
    """
    (tmp_path / "pyproject.toml").write_text("[project]\nname='forgecast'\n")
    assert bootstrap._fingerprint(tmp_path) == bootstrap._fingerprint(tmp_path)


def test_python_version_is_checked():
    bootstrap.check_python()  # this interpreter runs the suite, so it must pass


def test_ffmpeg_check_explains_the_fix_when_it_is_missing(monkeypatch):
    monkeypatch.setattr(bootstrap.shutil, "which", lambda _name: None)
    ok, message = bootstrap.check_ffmpeg()
    assert ok is False
    assert "ffmpeg" in message and "install" in message.lower()


# ------------------------------------------------------------------ supervisor


def test_a_port_is_found_even_when_the_preferred_one_is_taken():
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen(1)
        blocked = taken.getsockname()[1]

        port = supervisor.free_port(blocked)
        assert port != blocked

    # And the port handed back is actually bindable.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", port))


def test_the_environment_is_configured_before_anything_reads_it(tmp_path, monkeypatch):
    monkeypatch.delenv("FORGECAST_LOCAL_HANDOFF_TOKEN", raising=False)
    token = supervisor.configure_environment(tmp_path, 8123)

    import os

    assert os.environ["FORGECAST_LOCAL_MODE"] == "true"
    assert os.environ["FORGECAST_BASE_URL"] == "http://127.0.0.1:8123"
    assert os.environ["FORGECAST_LOCAL_HANDOFF_TOKEN"] == token
    assert len(token) >= 32


def test_health_wait_gives_up_rather_than_hanging():
    # Nothing is listening on this port, so the only correct outcome is a timely None.
    started = time.monotonic()
    assert supervisor.wait_for_health("http://127.0.0.1:9", timeout=1.0) is None
    assert time.monotonic() - started < 6.0
