"""Which encoder renders, and how the app finds out whether it can.

Every other stage in this pipeline costs time *and* a vendor's bill. The render costs
only time, on the operator's own machine — which makes the encoder the one place where
somebody's hardware pays for itself. A small NVIDIA card cannot generate a single frame
of video and encodes one perfectly well, because encoding is a fixed-function block
rather than the tensor cores.

The load-bearing test in this file is `test_a_listed_encoder_is_not_a_usable_one`. Asking
`ffmpeg -encoders` is the obvious way to detect hardware encoding and it is wrong: a great
many builds carry `h264_nvenc` on machines with no NVIDIA driver, so the encoder is
listed, is selected, and then fails at the first clip. Losing a render that way costs a
script, a voiceover and eighty generated shots.
"""

from __future__ import annotations

import subprocess

import pytest
from fastapi.testclient import TestClient

from forgecast.api.main import create_app
from forgecast.auth import create_access_token
from forgecast.models import User
from forgecast.render import ffmpeg as ff


@pytest.fixture
def client(user: User):
    with TestClient(create_app()) as test_client:
        test_client.headers["Authorization"] = f"Bearer {create_access_token(user)}"
        yield test_client


@pytest.fixture(autouse=True)
def _forget_the_probe():
    """The availability answer is cached for the process. Tests that pretend a machine
    has different hardware have to clear it, or the second one reads the first's."""
    ff._ENCODER_CACHE = None
    yield
    ff._ENCODER_CACHE = None


# ------------------------------------------------------------------ detection


def test_a_listed_encoder_is_not_a_usable_one():
    """The whole reason detection is a trial encode.

    This machine's ffmpeg lists h264_nvenc — it was built with it — and cannot run it,
    because there is no NVIDIA driver here. Grepping the listing would select it and
    fail every render.
    """
    listing = subprocess.run([ff.FFMPEG, "-hide_banner", "-encoders"],
                             capture_output=True, text=True, timeout=30).stdout
    if "h264_nvenc" not in listing:
        pytest.skip("this ffmpeg was built without NVENC, so the trap is not present")

    # Listed...
    assert "h264_nvenc" in listing
    # ...and the honest answer is whatever encoding a frame says. On a build machine with
    # no GPU that is False, which is the case this test exists for; on a workstation with
    # one it is True and the assertion below still holds because it is about agreement
    # with a real encode, not about a fixed answer.
    probed = ff.available_encoders()["nvidia"]
    real = subprocess.run(
        [ff.FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", "color=c=black:s=32x32:d=0.04", "-c:v", "h264_nvenc",
         "-frames:v", "1", "-f", "null", "-"],
        capture_output=True, text=True, timeout=60)
    really_works = real.returncode == 0 and "rror" not in (real.stderr or "")
    assert probed == really_works


def test_the_cpu_encoder_is_always_available():
    """Probing it would mean a machine with no working hardware encoder reported nothing
    usable rather than the one thing that always is."""
    assert ff.available_encoders()["cpu"] is True


def test_the_probe_is_cached_because_a_render_asks_per_clip():
    ff.available_encoders()
    assert ff._ENCODER_CACHE is not None
    # Second call must not shell out again.
    ff._ENCODER_CACHE = {"cpu": True, "nvidia": True, "intel": False}
    assert ff.available_encoders()["nvidia"] is True


# ------------------------------------------------------------------ the downgrade


def test_an_unavailable_encoder_downgrades_rather_than_failing():
    """A run that has already spent money must finish. A missing encoder is a slower
    render, not a lost one — the same argument `render/backends.py` makes about the
    motion renderer."""
    ff._ENCODER_CACHE = {"cpu": True, "nvidia": False, "intel": False}
    assert ff.resolve_encoder("nvidia") == "cpu"
    assert ff.resolve_encoder("intel") == "cpu"


def test_an_available_encoder_is_used():
    ff._ENCODER_CACHE = {"cpu": True, "nvidia": True, "intel": False}
    assert ff.resolve_encoder("nvidia") == "nvidia"


def test_an_unknown_name_is_the_cpu_rather_than_an_error():
    assert ff.resolve_encoder("wobble") == "cpu"
    assert ff.resolve_encoder("") == "cpu"


def test_the_codec_actually_changes_with_the_choice():
    ff._ENCODER_CACHE = {"cpu": True, "nvidia": True, "intel": True}
    assert "libx264" in ff.vcodec(30, "cpu")
    assert "h264_nvenc" in ff.vcodec(30, "nvidia")
    assert "h264_qsv" in ff.vcodec(30, "intel")


def test_every_encoder_is_quality_targeted_rather_than_bitrate_targeted():
    """A still scene should cost few bits and a busy one more, which is what makes a long
    video look even. A fixed bitrate spends the same on both."""
    ff._ENCODER_CACHE = {"cpu": True, "nvidia": True, "intel": True}
    assert "-crf" in ff.vcodec(30, "cpu")
    assert "-cq" in ff.vcodec(30, "nvidia")
    assert "-global_quality" in ff.vcodec(30, "intel")


def test_the_frame_rate_survives_the_encoder_choice():
    """Both are settled in the same call, because `concat_clips` stream-copies: pieces
    from two different encoders, or two different rates, join into a file that stutters
    or drifts against its audio."""
    ff._ENCODER_CACHE = {"cpu": True, "nvidia": True, "intel": False}
    for name in ("cpu", "nvidia"):
        assert ff.vcodec(60, name)[-2:] == ["-r", "60"]


# ------------------------------------------------------------------ end to end


def test_a_render_asking_for_hardware_it_does_not_have_still_finishes(tmp_path):
    """The failure this guards against is not theoretical: it is a render dying at the
    first clip on a machine whose ffmpeg advertises an encoder its driver cannot open."""
    ff._ENCODER_CACHE = None
    scenes = [ff.Scene(index=0, seconds=1.0, narration="One."),
              ff.Scene(index=1, seconds=1.0, narration="Two.")]
    out = ff.assemble_video(
        scenes, tmp_path / "out.mp4", workdir=tmp_path / "work",
        width=320, height=180, fps=30, encoder="nvidia", subtitles=False)
    assert out.exists()
    assert abs(ff.ffprobe_duration(out) - 2.0) < 0.25


# ------------------------------------------------------------------ the door


def test_the_endpoint_reports_what_will_actually_run(client):
    """Resolved, not echoed. Somebody who set `nvidia` on a machine that cannot run it
    should read that the render is on the CPU, not that it is on the GPU."""
    answer = client.get("/api/encoders")
    assert answer.status_code == 200
    body = answer.json()
    assert body["will_use"] in ff.ENCODERS
    keys = {row["key"] for row in body["encoders"]}
    assert keys == set(ff.ENCODERS)
    # Each row says what it costs and what it buys, because the trade is real: hardware
    # encoding makes a slightly larger file for the same picture.
    assert all(row["note"] for row in body["encoders"])


def test_it_is_a_machine_setting_and_not_a_channel_one():
    """A GPU belongs to the computer. `Channel` is what the cloud backup copies, so a
    channel restored onto a second machine must not arrive asking for hardware that
    machine does not have."""
    from forgecast.api.routes_settings import ENV_FIELDS
    from forgecast.models import Channel

    assert any(field["key"] == "FORGECAST_VIDEO_ENCODER" for field in ENV_FIELDS)
    assert not hasattr(Channel, "video_encoder")


def test_the_setting_is_not_masked_because_it_is_not_a_secret():
    """An operator who cannot read the value back cannot tell a saved setting from a
    typo'd one."""
    from forgecast.api.routes_settings import ENV_FIELDS

    field = next(f for f in ENV_FIELDS if f["key"] == "FORGECAST_VIDEO_ENCODER")
    assert field["secret"] is False
