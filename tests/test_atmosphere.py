"""Snow and fog over a shot, and the signal that does not exist for choosing them.

The reference uses atmosphere twice in nine minutes — falling snow at 0:59, fog at 2:18.
That ratio is the point: a creature standing in weather reads as being somewhere, and
weather on every shot reads as a filter.

The part worth recording is the negative result. I went looking for a signal in the
source material so the app could pick this itself, and there is not one: across nine
real creature pages on three wikis, only three contained any weather word at all and
each appeared exactly once — one "fog" in the 13,471 characters of the Doors wiki's Seek
page, one "smoke" in Rush's, one "winter" in Amber's. A passing noun in a wall of prose
is not a page saying its creature lives in the fog, so this is applied where it is asked
for and nowhere else.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw

from forgecast.graph.engine import ChannelSnapshot, NodeContext
from forgecast.nodes import media as media_node
from forgecast.providers import ProviderRegistry
from forgecast.render import particles

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                  reason="ffmpeg is not installed")


@pytest.fixture
def shot(tmp_path: Path) -> Path:
    """A finished shot at an awkward size, which is the size these actually arrive at.

    Odd height on purpose: a canon shot that needed no plate is the wiki's own file at
    the wiki's own dimensions, and the first real one this hit was 1962x1425. libx264
    refuses an odd height outright.
    """
    frame = Image.new("RGB", (1962, 1425), (26, 22, 20))
    draw = ImageDraw.Draw(frame)
    for index in range(0, 1962, 60):
        draw.line([(index, 0), (index, 1425)], fill=(64, 58, 52), width=8)
    path = tmp_path / "shot.png"
    frame.save(path)
    return path


# ------------------------------------------------------------------- the sheets


def test_a_sheet_repeats_exactly_so_the_scroll_never_seams():
    """The bottom half is the top half, pixel for pixel.

    That periodicity is the whole scrolling trick: after travelling one frame height the
    image beneath is identical to the one that started there, so there is nothing to
    wrap and no seam to hide. Break it and a video gets a line crossing it every few
    seconds — which is exactly the sort of thing nobody sees until it ships.
    """
    sheet = particles.snow_sheet(400, 300, radius=0.01, alpha=0.6, seed=7)

    assert sheet.size == (400, 600)
    top = sheet.crop((0, 0, 400, 300))
    bottom = sheet.crop((0, 300, 400, 600))
    assert ImageChops.difference(top.convert("RGB"), bottom.convert("RGB")).getbbox() \
        is None


def test_the_fog_sheet_repeats_along_the_axis_it_travels_on():
    """It drifts sideways, so the repeat has to be across the width, not down."""
    sheet = particles.fog_sheet(400, 300, seed=7)

    assert sheet.size == (800, 300)
    left = sheet.crop((0, 0, 400, 300)).convert("RGB")
    right = sheet.crop((400, 0, 800, 300)).convert("RGB")
    # Blurred after tiling, so the halves match closely rather than exactly; a seam
    # would show as a large difference, not a small one.
    extrema = ImageChops.difference(left, right).getextrema()
    assert max(band[1] for band in extrema) < 24


def test_fog_covers_the_whole_sheet_rather_than_patches_of_it():
    """Random blobs alone left dry ground, and a sheet that covers three quarters of the
    frame and stops reads as a gradient wipe rather than as weather — which is what the
    first render of this looked like. Fog has a floor."""
    sheet = particles.fog_sheet(600, 400, seed=3)

    alpha = sheet.getchannel("A")
    assert alpha.getextrema()[0] > 0, "part of the frame has no fog on it at all"


# --------------------------------------------------------------------- over a shot


@needs_ffmpeg
def test_weather_lands_on_a_still_of_any_size(shot, tmp_path):
    """Two failures in one: the sheets are built at the frame's size so the base has to
    be fitted to it, and the wiki's own file is not the frame's size and frequently not
    even an even number of pixels."""
    out = particles.apply(shot, tmp_path / "snowed.mp4", "snow",
                          seconds=1.5, width=960, height=540, fps=12, seed=2)

    assert out.suffix == ".mp4"
    assert out.exists() and out.stat().st_size > 0


@needs_ffmpeg
def test_an_atmosphere_nobody_recognises_returns_the_shot_untouched(shot, tmp_path):
    """This sits in the middle of a render that has already been paid for. An
    unrecognised name is a reason to ship the shot bare, not to lose the run."""
    assert particles.apply(shot, tmp_path / "x.mp4", "sleet",
                           seconds=1.0, width=320, height=180) == shot


# ---------------------------------------------------------------- who decides it


def _context(tmp_path, params) -> NodeContext:
    return NodeContext(
        run_id=1, topic="Doors", options={}, node_key="broll_plan",
        node_type="broll_plan", params=params, attempts=0,
        channel=ChannelSnapshot(
            id=1, name="Doors", niche="horror", language="en", voice_id="",
            avatar_id="", aspect_ratio="16:9", target_duration_seconds=60,
            style_profile={}, video_model="", video_model_hero=""),
        registry=ProviderRegistry(mode="mock"), workdir=tmp_path / "w",
        upstream_outputs={})


def test_weather_is_named_per_entity_because_that_is_how_it_is_used(tmp_path):
    """One creature in snow, one in fog, the rest in neither — which a channel-wide
    setting cannot express and would turn into a filter over the whole video."""
    context = _context(tmp_path, {"atmosphere": {"Amber": "snow", "Seek": "fog"}})

    assert media_node._atmosphere_for(context, "Amber") == "snow"
    assert media_node._atmosphere_for(context, "Seek") == "fog"
    assert media_node._atmosphere_for(context, "Figure") == ""


def test_a_plain_string_covers_every_entity_in_the_run(tmp_path):
    context = _context(tmp_path, {"atmosphere": "snow"})

    assert media_node._atmosphere_for(context, "anything") == "snow"


def test_a_misspelt_atmosphere_is_refused_where_the_operator_can_still_see_it(tmp_path):
    """`particles` would ignore it and ship the shot bare, which is right there and
    useless here: they typed something, and planning is the last stage that can tell
    them it did nothing."""
    context = _context(tmp_path, {"atmosphere": "sleet"})

    assert media_node._atmosphere_for(context, "Seek") == ""


def test_nothing_asked_for_means_no_weather(tmp_path):
    """Off is the default and stays the default. There is no signal in the source
    material to turn it on with — see this module's docstring for the measurement."""
    assert media_node._atmosphere_for(_context(tmp_path, {}), "Seek") == ""
