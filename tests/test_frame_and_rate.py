"""What the app actually exports at, and whether either number is a choice.

Two settings that were constants, and one of them was a constant nobody chose.

`dimensions` resolved 9:16 to 1080x1920 and 1:1 to 1080x1080 but 16:9 to 1280x720 — so
vertical and square already rendered at 1080p and the main long-form format was the single
one shipping at 720p. That was not a decision; it was a fallback that outlived the two
cases written above it.

Frame rate was pinned at 30 in `VCODEC` and in four filter strings, reachable from
nowhere. The default is still 30, which is right for this footage, but the reason it has
to be threaded rather than left as a constant is `concat_clips`: it stream-copies, so
pieces at mixed rates give a file whose timestamps drift against its audio.
"""

from __future__ import annotations

import pytest

from forgecast.nodes._common import (
    DEFAULT_HEIGHT,
    SUPPORTED_HEIGHTS,
    frame_for,
    resolve_height,
)
from forgecast.render.ffmpeg import (
    DEFAULT_FPS,
    SUPPORTED_FPS,
    resolve_fps,
    vcodec,
)

# ------------------------------------------------------------------ the frame


def test_long_form_renders_at_1080p():
    """The bug this file exists for."""
    assert frame_for("16:9") == (1920, 1080)
    assert DEFAULT_HEIGHT == 1080


def test_vertical_and_square_are_unchanged():
    """They were already at 1080. A fix to one format must not move the other two."""
    assert frame_for("9:16") == (1080, 1920)
    assert frame_for("1:1") == (1080, 1080)


def test_the_named_resolution_is_the_short_edge_whichever_edge_that_is():
    """1080p is 1920x1080 landscape and 1080x1920 portrait — the number is 1080 in both.

    Treating it as the height always gave 9:16 a 608x1080 frame: correctly 9:16, and a
    third of the pixels anybody asking for 1080p expected.
    """
    assert min(frame_for("16:9", 1080)) == 1080
    assert min(frame_for("9:16", 1080)) == 1080
    assert min(frame_for("21:9", 1080)) == 1080


def test_an_aspect_the_old_table_did_not_have_gets_its_own_frame():
    """21:9 and 4:3 used to fall through to 16:9 silently."""
    assert frame_for("21:9", 1080) == (2520, 1080)
    assert frame_for("4:3", 1080) == (1440, 1080)
    # And an aspect nobody has heard of still renders, at the common one.
    assert frame_for("wobble", 1080) == (1920, 1080)


@pytest.mark.parametrize("aspect", ["16:9", "9:16", "1:1", "4:3", "21:9"])
@pytest.mark.parametrize("height", SUPPORTED_HEIGHTS)
def test_every_frame_is_even_on_both_edges(aspect, height):
    """libx264 will not take an odd dimension, and the failure lands at encode time —
    minutes into a run that has already paid for a script, a voiceover and eighty clips."""
    wide, tall = frame_for(aspect, height)
    assert wide % 2 == 0 and tall % 2 == 0


def test_an_unsupported_height_is_snapped_rather_than_trusted():
    assert resolve_height(1081) == 1080
    assert resolve_height(2160) == 1440
    assert resolve_height(0) == DEFAULT_HEIGHT
    assert resolve_height(None) == DEFAULT_HEIGHT


def test_720_is_still_available():
    """It is in stored runs, and it halves the encode time on a slow machine."""
    assert 720 in SUPPORTED_HEIGHTS
    assert frame_for("16:9", 720) == (1280, 720)


# ------------------------------------------------------------------ the rate


def test_the_default_rate_is_30():
    """Right for this footage: the i2v vendors return 24 or 30 natively and WAN returns
    16, so encoding those at 60 duplicates frames and adds no information."""
    assert DEFAULT_FPS == 30
    assert resolve_fps(None) == 30
    assert "-r" in vcodec() and "30" in vcodec()


def test_60_is_available_because_it_was_asked_for():
    assert 60 in SUPPORTED_FPS
    assert vcodec(60)[-1] == "60"


def test_24_is_available_for_the_film_rate():
    assert vcodec(24)[-1] == "24"


def test_an_unsupported_rate_is_snapped_rather_than_encoded():
    """The rate is not only an encoder flag — it is baked into filter strings and into
    the concat, so an arbitrary value would produce pieces at one rate and a stream copy
    expecting another."""
    assert resolve_fps(50) == 60
    assert resolve_fps(25) == 24
    assert resolve_fps(120) == 60


def test_the_encoder_settings_are_otherwise_identical_across_rates():
    """Only the rate may differ. A preset or pixel format that changed with it would make
    the stream-copied concat lossy in a way nothing reports."""
    at30, at60 = vcodec(30), vcodec(60)
    assert at30[:-1] == at60[:-1]


# ------------------------------------------------------------------ reachability


def test_neither_is_pinned_in_the_pipeline_any_more():
    """Both pipelines hardcoded a frame in their node params, which overrode the channel
    entirely — so a channel setting would have been a setting with no effect."""
    from forgecast.graph import pipelines

    for name in ("faceless_longform", "faceless_shorts"):
        for node in pipelines.get_pipeline(name).nodes:
            assert "width" not in node.params, f"{name}.{node.key}"
            assert "height" not in node.params, f"{name}.{node.key}"


def test_the_channel_carries_both_onto_the_run():
    from forgecast.graph.engine import ChannelSnapshot

    snapshot = ChannelSnapshot(
        id=1, name="c", niche="n", language="en", voice_id="", avatar_id="",
        aspect_ratio="16:9", target_duration_seconds=480, style_profile={},
        video_height=1440, video_fps=60,
    )
    assert snapshot.video_height == 1440
    assert snapshot.video_fps == 60

    # Defaulted, so every older construction keeps working and means "let the app decide".
    plain = ChannelSnapshot(
        id=1, name="c", niche="n", language="en", voice_id="", avatar_id="",
        aspect_ratio="16:9", target_duration_seconds=480, style_profile={})
    assert plain.video_height == 0
    assert plain.video_fps == 0


# ------------------------------------------------------------------ the door


@pytest.fixture
def client(user):
    from fastapi.testclient import TestClient

    from forgecast.api.main import create_app
    from forgecast.auth import create_access_token

    with TestClient(create_app()) as test_client:
        test_client.headers["Authorization"] = f"Bearer {create_access_token(user)}"
        yield test_client


def test_the_channel_page_offers_both_and_saves_them(client, session, channel):
    from forgecast.models import Channel

    page = client.get(f"/c/{channel.id}").text
    assert 'name="video_height"' in page
    assert 'name="video_fps"' in page
    # Priced in frames, not in bare numbers: "1080p" alone does not say what a 9:16
    # channel is going to get.
    assert "1920x1080" in page or "1080x1920" in page

    answer = client.post(f"/c/{channel.id}/delivery",
                         data={"video_height": 1440, "video_fps": 60},
                         follow_redirects=False)
    assert answer.status_code == 303
    session.expire_all()
    saved = session.get(Channel, channel.id)
    assert saved.video_height == 1440
    assert saved.video_fps == 60


def test_a_number_outside_the_set_is_snapped_rather_than_refused(
    client, session, channel
):
    """These are numbers, not slugs. A value outside the supported set has an obvious
    nearest neighbour, and refusing would mean a 400 on a form that only offered valid
    options — which can only reach somebody posting by hand."""
    from forgecast.models import Channel

    answer = client.post(f"/c/{channel.id}/delivery",
                         data={"video_height": 2160, "video_fps": 50},
                         follow_redirects=False)
    assert answer.status_code == 303
    session.expire_all()
    saved = session.get(Channel, channel.id)
    assert saved.video_height == 1440
    assert saved.video_fps == 60


def test_zero_means_the_app_default_rather_than_a_missing_value(
    client, session, channel
):
    from forgecast.models import Channel

    channel.video_height = 720
    session.commit()
    client.post(f"/c/{channel.id}/delivery", data={"video_height": 0, "video_fps": 0},
                follow_redirects=False)
    session.expire_all()
    assert session.get(Channel, channel.id).video_height == 0


def test_the_page_says_what_60fps_does_and_does_not_buy(client, channel):
    """Said where the choice is made, rather than discovered after a render that took
    twice as long."""
    page = client.get(f"/c/{channel.id}").text
    assert "duplicates frames" in page
