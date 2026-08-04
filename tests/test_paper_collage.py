"""The paper-collage style: stepped motion, a locked camera, and one screen.

The three properties that make this style read as handmade are mechanical rather than
artistic, so they are testable. That is the whole reason to encode the style as code
instead of as guidance in a skill document — "hold for two or three frames" is either
true of the output or it is not.

Rendering tests shell out to ffmpeg, which is a hard dependency of this app rather than
an optional one, so they are not skipped.
"""

from __future__ import annotations

import subprocess
from itertools import pairwise

import pytest

from forgecast.motion import paper

# ------------------------------------------------------------------- stepped motion


def test_motion_arrives_in_steps_rather_than_continuously():
    """The defining property. Fifteen frames should land on five positions, not fifteen."""
    values = [round(value) for value in paper.stepped(0, 100, frames=15, hold=3)]
    assert len(set(values)) == 5
    # And each position is held for exactly the hold, which is what the eye reads as
    # stop-motion rather than as dropped frames.
    assert values[0] == values[1] == values[2]
    assert values[3] == values[4] == values[5]
    assert values[0] != values[3]


def test_a_hold_of_one_is_ordinary_smooth_animation():
    """Stated so the difference is visible in the test file, not only in the docstring."""
    smooth = paper.stepped(0, 100, frames=15, hold=1)
    assert len(set(round(value) for value in smooth)) == 15


def test_the_move_starts_and_ends_where_it_was_told_to():
    values = paper.stepped(20, 80, frames=12, hold=3)
    assert values[0] == pytest.approx(20)
    assert values[-1] == pytest.approx(80)


def test_every_step_lasts_the_same_number_of_frames():
    """Easing is applied to the stepped progress, not to the frame number.

    The other way round produces steps of uneven duration — a longer hesitation at the
    start than at the end — which reads as a stutter rather than as an ease.
    """
    values = paper.stepped(0, 100, frames=18, hold=3, ease="out")
    runs = []
    current = 1
    for previous, value in pairwise(values):
        if value == previous:
            current += 1
        else:
            runs.append(current)
            current = 1
    runs.append(current)
    assert set(runs) == {3}

    # The distance covered per step shrinks, which is the ease.
    positions = sorted(set(values))
    gaps = [b - a for a, b in pairwise(positions)]
    assert gaps == sorted(gaps, reverse=True)


def test_curves_that_survive_being_stepped_are_the_only_ones_offered():
    """A bounce quantised to three-frame holds is a stutter, not a bounce."""
    for kind in ("linear", "in", "out", "in_out"):
        values = paper.stepped(0, 100, frames=12, hold=3, ease=kind)
        assert values[0] == pytest.approx(0)
        assert values[-1] == pytest.approx(100)
        # Monotonic: nothing overshoots and comes back, because an overshoot lands on one
        # step and is gone before it registers as intentional.
        assert values == sorted(values)


def test_a_single_frame_is_the_destination_rather_than_the_start():
    assert paper.stepped(0, 100, frames=1) == [100.0]


# ------------------------------------------------------------------- the build


def test_the_build_leaves_the_hold_it_was_asked_for():
    """0-7s staggered, 7-10s held. The hold is when the viewer reads the frame."""
    schedule = paper.build_on(4, 10.0, settle=0.30)
    ends = [start + duration for start, duration in schedule]
    assert max(ends) == pytest.approx(7.0, abs=0.01)


def test_every_layer_moves_for_the_same_length_of_time():
    """Only the starts stagger.

    Durations that varied too made the build look like it was slowing down as it went,
    which fights the settle that follows it.
    """
    durations = {duration for _, duration in paper.build_on(5, 12.0)}
    assert len(durations) == 1


def test_one_layer_does_not_divide_by_zero():
    schedule = paper.build_on(1, 6.0)
    assert len(schedule) == 1
    assert schedule[0][0] == 0.0


# ------------------------------------------------------------------- the stack


def test_layers_composite_back_to_front_whatever_order_they_were_named_in():
    shot = paper.PaperShot(seconds=10.0,
                           layers=["string", "subject", "base", "strips", "scraps"])
    rows = shot.timeline()
    assert [row["depth"] for row in rows] == sorted(row["depth"] for row in rows)
    assert rows[0]["key"] == "base"
    assert rows[-1]["key"] == "string"


def test_the_paper_base_is_there_from_the_first_frame_and_never_animates():
    """Staggering it in means the shot opens on nothing."""
    shot = paper.PaperShot(seconds=10.0, layers=["base", "subject", "strips"])
    base = next(row for row in shot.timeline() if row["key"] == "base")
    assert base["start"] == 0.0
    assert base["duration"] == pytest.approx(10.0)
    assert base["entry"] == "hold"


def test_a_held_layer_takes_no_share_of_the_build():
    """Otherwise every moving layer's move is shortened by an element that never moves."""
    with_base = paper.PaperShot(seconds=10.0, layers=["base", "subject", "strips"])
    without = paper.PaperShot(seconds=10.0, layers=["subject", "strips"])
    moving = [row["duration"] for row in with_base.timeline() if row["entry"] != "hold"]
    assert moving == [row["duration"] for row in without.timeline()]


def test_the_shot_has_nowhere_to_put_a_camera():
    """The camera is absent by construction, not by convention.

    `prompts/moves.py` carries twelve camera moves and this style uses none of them, so a
    shot planned here cannot accidentally acquire a push-in.
    """
    rows = paper.PaperShot(seconds=8.0, layers=["base", "subject"]).timeline()
    assert not any("camera" in row or "motion" in row for row in rows)
    assert paper.catalogue()["camera"] == "locked"


def test_the_style_generates_no_video_and_says_so():
    """The reason to reach for it: Veo and Kling produce the three things it removes."""
    assert paper.catalogue()["generated_video"] is False


def test_an_unknown_layer_is_dropped_rather_than_crashing_a_paid_run():
    rows = paper.PaperShot(seconds=8.0, layers=["base", "hologram"]).timeline()
    assert [row["key"] for row in rows] == ["base"]


# ------------------------------------------------------------------- the filters


def test_the_halftone_screen_is_rotated_before_the_cell_arithmetic():
    """Rotating the finished screen resamples it and softens the dot edges.

    Those hard edges are the whole difference between ink and a blur, so the rotation has
    to happen on the sampling grid.
    """
    graph = paper.halftone_filter(cell=8, angle_degrees=45)
    # The rotation appears in the coordinate setup, before any cell modulo.
    rotate = graph.index("0.707107")
    modulo = graph.index("floor(")
    assert rotate < modulo


def test_dot_reach_is_bounded_so_the_screen_neither_fills_nor_washes_out():
    """Above ~0.72 neighbouring dots merge to solid black; below ~0.5 shadows never close."""
    # In range, the reach is just gain x cell.
    assert "6.4" in paper.halftone_filter(cell=8, gain=0.8)
    # Out of range, it is clamped to [0.1, 0.9] rather than trusted.
    assert "9.0" in paper.halftone_filter(cell=10, gain=5.0)
    assert "1.0" in paper.halftone_filter(cell=10, gain=-1.0)


def test_the_paper_is_built_from_low_frequency_noise_rather_than_blurred_noise():
    """Blurring high-frequency noise removes variation. It does not enlarge it.

    The first version of this filtergraph blurred a full-resolution noise field and
    produced a flat sheet with a slight haze.
    """
    inputs = paper.paper_inputs(1920, 1080, seed=7)
    assert "color=c=gray:s=7x4" in inputs
    assert "color=c=gray:s=26x15" in inputs
    graph = paper.paper_filtergraph(1920, 1080)
    assert "scale=1920:1080:flags=bicubic" in graph
    assert "boxblur" not in graph


def test_grain_is_applied_after_the_tone_curve():
    """Applied before it, the curve's range compression halves the grain's amplitude and
    the sheet comes out with no fibre at all."""
    graph = paper.paper_filtergraph(1920, 1080, grain=11)
    assert graph.index("curves=all") < graph.rindex("noise=alls=11")


def test_the_same_seed_is_the_same_paper():
    """Determinism is the style. Eighty different papers is eighty different desks."""
    assert (paper.paper_filtergraph(1920, 1080, seed=7)
            == paper.paper_filtergraph(1920, 1080, seed=7))
    assert (paper.paper_filtergraph(1920, 1080, seed=7)
            != paper.paper_filtergraph(1920, 1080, seed=8))


def test_the_torn_edge_touches_alpha_only():
    """Displacing the colour channels fringes the edge with whatever was behind the
    subject in the source image."""
    graph = paper.torn_edge_filter()
    assert "alphaextract" in graph
    # Re-thresholded after the blur. Blurring alone rounds the edge; blurring and
    # re-thresholding makes it wander, which is what torn looks like.
    assert "curves=" in graph
    assert graph.index("boxblur") < graph.index("curves=")


# ------------------------------------------------------------------- rendering


def _luma_spread(path) -> int:
    """How many distinct grey levels an image actually contains."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-f", "lavfi",
         f"movie={path},format=gray,signalstats",
         "-show_entries", "frame_tags=lavfi.signalstats.YMIN,lavfi.signalstats.YMAX",
         "-of", "csv=p=0"],
        capture_output=True, text=True, timeout=60, check=True)
    low, high = (int(value) for value in out.stdout.strip().splitlines()[0].split(","))
    return high - low


def test_a_sheet_of_paper_renders(tmp_path):
    sheet = paper.render_paper(tmp_path / "sheet", width=320, height=180, seed=7)
    assert sheet.path.exists()
    assert sheet.path.stat().st_size > 1000
    # It has to have texture. A flat fill would pass an "it rendered" assertion and is
    # exactly the failure the first three attempts at this filtergraph produced.
    assert _luma_spread(sheet.path) > 20


def test_the_same_seed_renders_the_same_bytes(tmp_path):
    first = paper.render_paper(tmp_path / "a", width=200, height=120, seed=11)
    second = paper.render_paper(tmp_path / "b", width=200, height=120, seed=11)
    assert first.path.read_bytes() == second.path.read_bytes()


def test_a_different_tone_is_a_different_paper(tmp_path):
    newsprint = paper.render_paper(tmp_path / "n", width=200, height=120, tone="newsprint")
    kraft = paper.render_paper(tmp_path / "k", width=200, height=120, tone="kraft")
    assert newsprint.path.read_bytes() != kraft.path.read_bytes()


def test_an_unknown_tone_falls_back_rather_than_failing_a_paid_run(tmp_path):
    sheet = paper.render_paper(tmp_path / "x", width=200, height=120, tone="chartreuse")
    assert sheet.path.exists()


def test_screening_an_image_produces_ink_rather_than_grey(tmp_path):
    """A halftone is two tones. If the output still has a range of greys it is a
    desaturation, not a screen."""
    source = tmp_path / "src.png"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "gradients=s=256x144:c0=black:c1=white", "-frames:v", "1", str(source)],
        check=True, timeout=60)

    screened = paper.render_halftone(source, tmp_path / "out", cell=6)
    assert screened.exists()

    out = subprocess.run(
        ["ffprobe", "-v", "error", "-f", "lavfi",
         f"movie={screened},format=gray,signalstats",
         "-show_entries", "frame_tags=lavfi.signalstats.YMIN,lavfi.signalstats.YMAX",
         "-of", "csv=p=0"],
        capture_output=True, text=True, timeout=60, check=True)
    low, high = (int(value) for value in out.stdout.strip().splitlines()[0].split(","))
    # Ink and paper, with the full range between them present as dots rather than as tone.
    assert low <= 20
    assert high >= 230


def test_a_finer_cell_puts_more_ink_on_the_page(tmp_path):
    """Sanity on the screen itself: dot pitch has to actually change the output."""
    source = tmp_path / "src.png"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "gradients=s=256x144:c0=black:c1=white", "-frames:v", "1", str(source)],
        check=True, timeout=60)

    coarse = paper.render_halftone(source, tmp_path / "coarse", cell=14)
    fine = paper.render_halftone(source, tmp_path / "fine", cell=4)
    assert coarse.read_bytes() != fine.read_bytes()


def test_a_missing_source_is_a_readable_error_rather_than_a_traceback(tmp_path):
    with pytest.raises(RuntimeError, match="screening"):
        paper.render_halftone(tmp_path / "nothing.png", tmp_path / "out")
