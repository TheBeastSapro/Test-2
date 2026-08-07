"""The transition a reference was measured to use, actually applied.

`render/transitions.py` shipped complete — a catalogue, a planner that refuses an
overlap the shots cannot afford, an `available()` guard for an ffmpeg without `xfade`,
and a `hold_timeline` that keeps the bed the length the narration was recorded against.
It had no caller. Every video went through `concat_clips`, which is a hard cut.

The reason it was never wired is the interesting part: two vocabularies that never met.
`vision/profile.py` classifies a reference's joins as `cut` or `dissolve`, because that
is what decodes reliably off frames. The catalogue is named for editorial intent —
`soften`, `time_passes`, `revelation`. `get()` never raises and falls back to a hard
cut, so a style asking for "dissolve" was silently hard-cut and looked like the feature
working. It looked like it worked when this wiring was first written, too.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forgecast.render import transitions as tr
from forgecast.render.ffmpeg import Scene, _join_scenes, ffprobe_duration, run_ffmpeg


def test_the_style_vocabulary_maps_onto_the_catalogue():
    """`dissolve` has to become a real catalogue key. It maps to `soften` rather than
    anything louder: a measured cross-dissolve is the join being hidden, and fadeblack
    or zoomin would invent an intent the measurement cannot support."""
    assert tr.from_style("dissolve") == "soften"
    assert tr.BY_KEY["soften"].xfade == "fade"


def test_a_measured_cut_stays_a_cut():
    assert tr.from_style("cut") == tr.DEFAULT_KEY
    assert tr.from_style("") == tr.DEFAULT_KEY


def test_an_unknown_name_falls_back_rather_than_raising():
    """A style from a newer build, or a typo, must give the quietest edit rather than
    stopping a render that has already been paid for."""
    assert tr.from_style("holographic_swirl") == tr.DEFAULT_KEY


def test_a_catalogue_key_passes_straight_through():
    """So an operator or the agent can still ask for one by name."""
    assert tr.from_style("time_passes") == "time_passes"


@pytest.fixture(scope="module")
def clips(tmp_path_factory) -> tuple[list[Path], list[Scene]]:
    workdir = tmp_path_factory.mktemp("joins")
    made, scenes = [], []
    for index, colour in enumerate(("red", "green", "blue", "orange")):
        path = workdir / f"c{index}.mp4"
        run_ffmpeg(["-f", "lavfi", "-i", f"color=c={colour}:s=320x180:d=3:r=30",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], label="fixture")
        made.append(path)
        scenes.append(Scene(index=index, seconds=3.0))
    return made, scenes


def _rgb_at(path: Path, seconds: float) -> tuple[int, int, int]:
    import subprocess

    from forgecast.render.ffmpeg import FFMPEG

    raw = subprocess.run(
        [FFMPEG, "-v", "error", "-ss", str(seconds), "-i", str(path),
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True).stdout
    return tuple(raw[:3])


def test_a_dissolving_reference_gets_a_real_blend(clips, tmp_path):
    """The assertion this file exists for. The first version of this wiring produced a
    file of exactly the right duration whose frames were identical to a hard cut — the
    numbers all looked right and nothing had dissolved."""
    made, scenes = clips
    out = _join_scenes(made, scenes, tmp_path / "x.mp4",
                       transition="dissolve", dissolve_share=1.0)

    blended = _rgb_at(out, 2.85)
    assert blended != (253, 0, 0), "still the outgoing shot — nothing dissolved"
    assert blended != (0, 127, 0), "already the incoming shot — nothing dissolved"
    assert blended[0] > 20 and blended[1] > 20, f"expected a mix, got {blended}"


def test_the_bed_keeps_the_length_the_narration_was_recorded_against(clips, tmp_path):
    """Every overlap makes the bed shorter, and the voiceover did not move. A video
    with eight transitions ending four seconds before its own narration is the failure
    `hold_timeline` exists for, and it accumulates towards the payoff."""
    made, scenes = clips
    intended = sum(scene.seconds for scene in scenes)

    for kwargs in ({}, {"transition": "dissolve", "dissolve_share": 1.0},
                   {"transition": "dissolve", "dissolve_share": 0.5}):
        out = _join_scenes(made, scenes, tmp_path / f"d{len(kwargs)}{kwargs}.mp4"[:60],
                           **kwargs)
        assert abs(ffprobe_duration(out) - intended) < 0.15, kwargs


def test_a_hard_cutting_reference_is_untouched(clips, tmp_path):
    """The reference this work was measured against hard-cuts exclusively. It must go
    through the same concat every render used before this existed."""
    made, scenes = clips
    out = _join_scenes(made, scenes, tmp_path / "c.mp4",
                       transition="cut", dissolve_share=1.0)

    assert _rgb_at(out, 2.85) == (253, 0, 0)


def test_zero_share_means_no_transitions_even_when_one_is_named(clips, tmp_path):
    made, scenes = clips
    out = _join_scenes(made, scenes, tmp_path / "z.mp4",
                       transition="dissolve", dissolve_share=0.0)

    assert _rgb_at(out, 2.85) == (253, 0, 0)


def test_a_partial_share_dissolves_some_boundaries_and_cuts_others(clips, tmp_path):
    """Spread evenly rather than taken from the front — a video that dissolves its
    first third and cuts the rest reads as two edits stitched together."""
    made, scenes = clips
    keys = ["cut"] * 3
    boundaries, wanted = 3, round(3 * 0.34)
    step = boundaries / wanted
    for index in range(wanted):
        keys[min(boundaries - 1, int(index * step))] = "soften"

    assert keys.count("soften") == 1
    assert sum(1 for join in tr.plan([3.0] * 4, keys) if not join.is_cut) == 1
