"""The layered renderer, selectable from somewhere other than a command line.

`finalize` reads `motion_backend` from the run options and from the channel's style
profile, and the only writer in the whole tree was one `--motion-backend` flag on the
CLI. So the Remotion renderer shipped in every archive, could be installed from inside
the app, and could not be chosen by anybody who was not using the command line — and
when it was chosen and absent, `backends.backend_for` downgraded to ffmpeg with nothing
but a `log.warning` to say so.

These tests are about being able to pick it and being told what actually ran.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from forgecast.agent.studio import Studio
from forgecast.api.main import create_app
from forgecast.models import Channel


@pytest.fixture
def client(user):
    with TestClient(create_app()) as test_client:
        token = test_client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "supersecret"},
        ).json()["access_token"]
        test_client.headers["Authorization"] = f"Bearer {token}"
        yield test_client


@pytest.fixture
def no_remotion(monkeypatch):
    """The ordinary state of a fresh install: the motion toolset is not there."""
    from forgecast.desktop import toolchain
    from forgecast.render import backends

    monkeypatch.setattr(backends.RemotionBackend, "available", lambda self: False)
    monkeypatch.setattr(toolchain, "extra_installed",
                        lambda name, root=None: (False, "the Remotion renderer")
                        if name == "motion" else (True, ""))


# ------------------------------------------------------ the key the renderer reads


def test_the_setting_is_written_where_finalize_reads_it(user, channel, session):
    """The load-bearing link, asserted on the source of the reader as well as on the
    write. A setter that stored this under any other name would pass every test that
    only read it back through the setter, and change nothing about the video."""
    finalize = (Path(__file__).resolve().parent.parent / "forgecast" / "nodes"
                / "finalize.py").read_text(encoding="utf-8")
    assert 'style_profile or {}).get("motion_backend")' in finalize

    result = Studio(user_id=user.id).set_motion_backend(channel.id, "remotion")
    assert result["motion_backend"] == "remotion"

    session.expire_all()
    stored = session.get(Channel, channel.id)
    assert stored.style_profile["motion_backend"] == "remotion"


def test_setting_the_renderer_keeps_everything_else_on_the_profile(user, channel,
                                                                  session):
    """Why this is a targeted setter and not `update_channel(style_profile=...)`.

    The profile also carries the channel's tone, its learned render spec and its map
    style. A caller that only meant to switch renderer and wrote the whole dict would
    take those with it, and nothing would report the loss.
    """
    Studio(user_id=user.id).set_motion_backend(channel.id, "remotion")
    session.expire_all()
    assert session.get(Channel, channel.id).style_profile["tone"] == "calm and precise"


def test_a_renderer_that_does_not_exist_is_refused_rather_than_stored(user, channel):
    answered = Studio(user_id=user.id).set_motion_backend(channel.id, "blender")
    assert "error" in answered
    assert "remotion" in answered["error"]


def test_a_channel_belonging_to_someone_else_is_not_addressable(user, channel, session):
    from forgecast.auth import hash_password
    from forgecast.models import User

    other = User(email="someone@else.test", hashed_password=hash_password("x" * 12))
    session.add(other)
    session.commit()
    assert "error" in Studio(user_id=other.id).set_motion_backend(channel.id, "remotion")


# ----------------------------------------------------------------- the downgrade


def test_the_downgrade_is_reported_where_the_choice_is_made(user, channel, no_remotion):
    """It used to be a log warning, which meant the operator's only evidence that the
    renderer had fallen back was a video that looked exactly like the last one."""
    answered = Studio(user_id=user.id).set_motion_backend(channel.id, "remotion")
    assert answered["motion_backend"] == "remotion"
    assert answered["will_use"] == "ffmpeg"
    assert answered["downgraded"] is True
    assert "not installed" in answered["why"]
    # And the answer ends in something the app can do about it.
    assert "pip install" not in answered["install"]
    assert "/api/setup/extras/motion" in answered["install"]


def test_the_report_says_what_will_run_not_what_was_asked_for(user, channel,
                                                              no_remotion):
    Studio(user_id=user.id).set_motion_backend(channel.id, "remotion")
    report = Studio(user_id=user.id).render_backends()

    mine = next(row for row in report["channels"] if row["id"] == channel.id)
    assert mine["asked_for"] == "remotion"
    assert mine["will_use"] == "ffmpeg"
    assert report["motion_extra"]["installed"] is False


def test_the_channel_page_offers_the_picker_and_names_the_fallback(client, channel,
                                                                   no_remotion):
    """The whole point. A renderer that can be installed and not selected is a renderer
    nobody has."""
    client.post(f"/c/{channel.id}/motion-backend", data={"motion_backend": "remotion"})

    page = client.get(f"/c/{channel.id}").text
    assert f'action="/c/{channel.id}/motion-backend"' in page
    assert 'name="motion_backend"' in page
    assert "Motion renderer" in page
    # And it says which engine is actually going to draw the frames.
    assert "renders fall back to" in page


def test_the_picker_shows_the_engine_that_is_running_when_nothing_is_wrong(client,
                                                                          channel):
    page = client.get(f"/c/{channel.id}").text
    assert "Renders use" in page
    assert "renders fall back to" not in page


def test_saving_the_renderer_needs_an_account_and_a_channel_you_own(channel):
    with TestClient(create_app()) as anon:
        answered = anon.post(f"/c/{channel.id}/motion-backend",
                             data={"motion_backend": "remotion"})
        assert answered.status_code == 401


def test_an_unknown_renderer_from_the_form_is_a_400(client, channel):
    answered = client.post(f"/c/{channel.id}/motion-backend",
                           data={"motion_backend": "blender"})
    assert answered.status_code == 400


# ------------------------------------------------------------------- the chat's end


def test_the_chat_can_read_and_set_it():
    from forgecast.agent import tools

    assert "mcp__forgecast__render_backends" in tools.ALLOWED
    assert "mcp__forgecast__set_motion_backend" in tools.ALLOWED
    assert "render_backends" in tools._READ_ONLY
    assert "set_motion_backend" in tools._WRITES
