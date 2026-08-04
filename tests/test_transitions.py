"""Transitions between shots, and the arithmetic that keeps them honest.

The renderer hard-cut every scene, so "professional transitions" was a real gap. What
fills it is ffmpeg's own `xfade` — 58 of them, already on every machine that can render
at all — rather than a bought pack, because a bought pack is licensed to one buyer and
this app ships as a zip you send to other people.

The tests that matter here are the timing ones. A transition overlaps two clips, so it
makes the video shorter, and the narration was recorded against the length it was before.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from forgecast.render import transitions as tr
from forgecast.render.ffmpeg import ffprobe_duration


def _clip(path: Path, colour: str, seconds: float) -> Path:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", f"color=c={colour}:s=320x180:d={seconds}:r=24",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(path)],
        check=True, capture_output=True)
    return path


# ------------------------------------------------------------------- the catalogue


def test_a_hard_cut_is_the_default_and_is_in_the_catalogue():
    """Not an absence of a transition — a choice, with a reason attached.

    Every transition that is not a cut is the edit announcing itself, so the quiet one
    has to be the one you get without asking.
    """
    assert tr.DEFAULT_KEY == "cut"
    assert tr.get("cut").xfade == ""
    assert tr.get("").key == "cut"
    # Anything unrecognised gives the quietest edit rather than stopping a paid render.
    assert tr.get("no-such-transition").key == "cut"


def test_every_entry_says_when_to_use_it_not_what_it_looks_like():
    """`smoothleft` describes pixels. The style profile and the agent choose on meaning,
    so an entry with no editorial job is an entry nobody can pick correctly."""
    for item in tr.CATALOGUE:
        assert item.use_when.strip(), f"{item.key} does not say when to use it"
        assert 0.0 <= item.intensity <= 1.0
        if item.xfade:
            assert tr.MIN_SECONDS <= item.seconds <= tr.MAX_SECONDS


def test_the_ones_left_out_are_recorded_with_the_reason():
    """Otherwise the next person re-adds `radial` believing nobody considered it."""
    assert tr.RETIRED
    assert all(reason.strip() for reason in tr.RETIRED.values())
    assert not (set(tr.RETIRED) & {item.xfade for item in tr.CATALOGUE})


def test_a_measured_energy_maps_onto_a_transition():
    """This is how `style.editing`'s numbers become a choice rather than a preference."""
    assert tr.for_intensity(0.0).key == "cut"
    assert tr.for_intensity(1.0).intensity >= 0.7


# --------------------------------------------------------------------- the planning


def test_a_shot_too_short_to_afford_a_transition_gets_a_cut():
    """A shot that is mostly overlap is not a shot.

    The viewer never sees it settle, and the transition either side of it reads as one
    long smear rather than as two edits.
    """
    joins = tr.plan([6.0, 0.8, 6.0], ["focus_in", "focus_in"])
    assert joins[0].is_cut, "a 0.8s neighbour cannot afford a 0.6s transition"
    assert joins[1].is_cut


def test_a_transition_is_clamped_rather_than_refused():
    """A style profile asking for three seconds is asking for a slideshow, but a render
    that has already been paid for should not stop over it."""
    joins = tr.plan([20.0, 20.0], ["soften"], seconds=9.0)
    assert joins[0].seconds == tr.MAX_SECONDS
    joins = tr.plan([20.0, 20.0], ["soften"], seconds=0.01)
    assert joins[0].seconds == tr.MIN_SECONDS


def test_the_shortening_is_reported_rather_than_left_to_be_discovered():
    """Every overlap makes the video shorter. A caller that cannot see by how much
    cannot re-time anything against it."""
    joins = tr.plan([9.0, 9.0, 9.0], ["time_passes", "time_passes"])
    assert tr.shortening(joins) == pytest.approx(1.4, abs=0.001)
    assert tr.shortening(tr.plan([9.0, 9.0], ["cut"])) == 0.0


# ------------------------------------------------------------ rendered, not asserted


@pytest.mark.skipif(not tr.available(), reason="this ffmpeg has no xfade")
def test_the_timeline_is_held_so_narration_stays_in_sync(tmp_path):
    """The one that would ship as a bug.

    Eight transitions in an eight-minute video make the bed about four seconds short,
    and the narration was recorded against the length it was before — so the voice runs
    past the end, and the drift lands on the payoff. The last frame is held for exactly
    the total overlap instead.
    """
    clips = [_clip(tmp_path / f"{name}.mp4", name, 3.0)
             for name in ("red", "blue", "green")]
    durations = [3.0, 3.0, 3.0]
    joins = tr.plan(durations, ["focus_in", "time_passes"])
    assert tr.shortening(joins) > 0, "this test needs real transitions to be planned"

    held = tr.join_clips(clips, joins, durations, tmp_path / "held.mp4")
    assert ffprobe_duration(held) == pytest.approx(sum(durations), abs=0.08)

    # And the raw form, for a caller that is re-timing the audio itself.
    loose = tr.join_clips(clips, joins, durations, tmp_path / "loose.mp4",
                          hold_timeline=False)
    assert ffprobe_duration(loose) == pytest.approx(
        sum(durations) - tr.shortening(joins), abs=0.08)


@pytest.mark.skipif(not tr.available(), reason="this ffmpeg has no xfade")
def test_all_cuts_produces_the_video_it_always_produced(tmp_path):
    """The fallback has to be the old behaviour exactly, not an approximation of it —
    a machine that cannot do transitions must still finish a render."""
    clips = [_clip(tmp_path / f"{name}.mp4", name, 2.0) for name in ("red", "blue")]
    joins = tr.plan([2.0, 2.0], ["cut"])
    out = tr.join_clips(clips, joins, [2.0, 2.0], tmp_path / "out.mp4")
    assert ffprobe_duration(out) == pytest.approx(4.0, abs=0.08)


def test_an_ffmpeg_without_xfade_degrades_instead_of_failing(tmp_path, monkeypatch):
    """A distribution build older than 4.3 should produce hard cuts and a finished
    video, not a filter-graph error several minutes into a render."""
    monkeypatch.setattr(tr, "available", lambda: False)
    clips = [_clip(tmp_path / f"{name}.mp4", name, 1.0) for name in ("red", "blue")]
    joins = tr.plan([1.0, 1.0], ["soften"], seconds=0.3)
    out = tr.join_clips(clips, joins, [1.0, 1.0], tmp_path / "out.mp4")
    assert out.exists()
    assert ffprobe_duration(out) == pytest.approx(2.0, abs=0.08)
