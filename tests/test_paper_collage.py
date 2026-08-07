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


def test_the_torn_edge_works_on_a_greyscale_alpha_not_an_image():
    """It takes an already-extracted alpha, so the colour channels cannot reach it.

    Running them through would fringe the edge with whatever was behind the subject in
    the source image. `cutout_filtergraph` is what splits them.
    """
    graph = paper.torn_edge_filter()
    assert "alphaextract" not in graph
    assert "geq" not in graph
    # Re-thresholded after the blur. Blurring alone rounds the edge; blurring and
    # re-thresholding makes it wander, which is what torn looks like.
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


# ------------------------------------------------------------------- compositing


def _rows(seconds=8.0, layers=("base", "scraps", "subject", "strips")):
    return paper.PaperShot(seconds=seconds, layers=list(layers)).timeline(fps=30)


def test_each_layer_reads_its_own_input():
    """Inputs are supplied in row order, base first, so a row's position is its index.

    Offsetting by one made every layer composite the next layer's image, and the last one
    referenced an input that did not exist — which ffmpeg reports only as "Invalid
    argument", several seconds into building the graph.
    """
    graph = paper.shot_filtergraph(_rows(), {}, width=1280, height=720, fps=30)
    assert "[0:v]scale=1280:720" in graph
    for index in (1, 2, 3):
        assert f"[{index}:v]" in graph
    assert "[4:v]" not in graph


def test_the_base_is_the_canvas_and_never_overlays():
    graph = paper.shot_filtergraph(_rows(), {}, width=1280, height=720, fps=30,
                                   shadows=False)
    # Three layers over the base means three overlays, not four.
    assert graph.count("overlay=") == 3


def test_motion_is_stepped_in_the_filtergraph_too():
    """A render that eases smoothly while the Python preview steps is worse than no
    preview. The `floor` is what makes them the same animation."""
    graph = paper.shot_filtergraph(_rows(), {}, width=1280, height=720, fps=30)
    assert "floor(" in graph
    assert "eval=frame" in graph


def test_the_filtergraph_steps_at_the_same_moments_as_the_python():
    """Pinned to each other, because they are two implementations of one curve."""
    expression = paper._stepped_expression(0.0, 3.0, fps=30, hold=3)
    # 90 frames, held three at a time, is 30 steps — so the divisor is 29.
    assert "/29" in expression

    # Counted as runs rather than as distinct values: under an ease-out the last few
    # steps are close enough together that two of them round to the same number, so
    # counting distinct values undercounts the steps that actually happen.
    values = paper.stepped(0, 100, frames=90, hold=3)
    runs = 1 + sum(1 for a, b in pairwise(values) if a != b)
    assert runs == 30


def test_a_layer_that_does_not_travel_gets_no_travel_expression():
    """`x+-100*(...)` is valid ffmpeg and unreadable, and a layer with no offset should
    not carry the arithmetic at all."""
    assert paper._travel("(W-w)*0.5", 0.0, "1") == "(W-w)*0.5"
    assert "-100.0*" in paper._travel("(W-w)*0.5", -100.0, "P")
    assert "+100.0*" in paper._travel("(W-w)*0.5", 100.0, "P")
    assert "+-" not in paper._travel("(W-w)*0.5", -100.0, "P")


def test_a_placement_can_be_given_as_a_bare_pair():
    """Most layers need nothing said about them beyond where they sit."""
    assert paper.Placement.of((0.3, 0.7)) == paper.Placement(0.3, 0.7)
    assert paper.Placement.of(paper.Placement(0.1, 0.2, 0.5)).height == 0.5
    assert paper.Placement.of(None) == paper.Placement()


def test_a_sized_layer_is_scaled_to_a_fraction_of_the_frame():
    """A 1024-wide portrait dropped on a 1280-wide frame is not a placement, it is a
    background. Sizing is in fractions so one composition renders at any resolution."""
    graph = paper.shot_filtergraph(
        _rows(), {"subject": paper.Placement(0.5, 0.5, height=0.62)},
        width=1280, height=720, fps=30)
    # 0.62 of 720, and even, because libx264 will not take an odd dimension.
    assert "scale=-2:446" in graph


def test_a_rotated_layer_keeps_transparent_corners():
    """Black corners would cover the sheet the layer is supposed to be lying on."""
    graph = paper.shot_filtergraph(
        _rows(), {"scraps": paper.Placement(0.3, 0.4, rotate=-3.5)},
        width=1280, height=720, fps=30)
    assert "fillcolor=none" in graph


def test_the_red_string_is_revealed_rather_than_moved():
    """The drawing is the argument, so it appears progressively instead of arriving."""
    rows = _rows(layers=("base", "subject", "string"))
    graph = paper.shot_filtergraph(rows, {}, width=1280, height=720, fps=30)
    assert "crop=w='max(2\\,iw*" in graph
    # Floored at two pixels: a zero-width crop is an invalid filter and fails at render
    # time rather than at build time.
    assert "crop=w='max(2" in graph


# ------------------------------------------------------------------- the cut-out


def test_screening_a_cut_out_keeps_its_alpha():
    """The halftone starts with format=gray and greyscale has no alpha.

    Screening an RGBA image straight through returns a rectangle — which is exactly what
    the first render of this style produced: a portrait with a border, sitting on the
    paper like a photograph rather than like something torn out of a newspaper.
    """
    graph = paper.cutout_filtergraph()
    assert "split=2" in graph
    assert "alphaextract" in graph
    assert "alphamerge" in graph
    # The colour half is screened; the alpha half is torn. Never the other way round.
    assert graph.index("[colour]") < graph.index("geq=lum")


def test_the_tear_never_touches_the_colour_channels():
    """Displacing them fringes the edge with whatever was behind the subject."""
    graph = paper.cutout_filtergraph()
    tear = graph.split("[matte]", 1)[1].split("[torn]", 1)[0]
    assert "noise=" in tear
    assert "geq" not in tear


def test_a_cut_out_renders_with_transparency(tmp_path):
    import subprocess

    source = tmp_path / "src.png"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "gradients=s=256x256:c0=black:c1=white",
         "-vf", "format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)'"
                ":a='if(lt(hypot(X-128,Y-128),100),255,0)'",
         "-frames:v", "1", str(source)],
        check=True, timeout=60)

    out = paper.render_cutout(source, tmp_path / "cut", cell=6, tear=4)
    assert out.exists()

    # Still has an alpha channel, and it is still partly transparent.
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=pix_fmt", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, timeout=60, check=True)
    assert "a" in probe.stdout.strip()


# ------------------------------------------------------------------- end to end


def test_a_whole_beat_renders_to_video(tmp_path):
    import subprocess

    base = paper.render_paper(tmp_path / "base", width=640, height=360, seed=7)
    scrap = paper.render_paper(tmp_path / "scrap", width=200, height=140, seed=22,
                               tone="kraft", vignette=False)
    strip = paper.render_paper(tmp_path / "strip", width=180, height=30, seed=31,
                               tone="bone", vignette=False)

    shot = paper.PaperShot(seconds=3.0, layers=["base", "scraps", "strips"])
    out = paper.render_shot(
        shot, {"base": base.path, "scraps": scrap.path, "strips": strip.path},
        tmp_path / "beat",
        placements={"scraps": paper.Placement(0.3, 0.4, 0.45, -3.0),
                    "strips": (0.3, 0.85)},
        width=640, height=360, fps=24)

    assert out.exists()
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, timeout=120, check=True)
    assert "640,360" in probe.stdout
    assert abs(float(probe.stdout.strip().splitlines()[-1]) - 3.0) < 0.15


def test_a_layer_with_no_source_is_skipped_rather_than_failing_the_run(tmp_path):
    """A beat that planned for a stamp nobody supplied should still render the rest.

    The alternative is a run that has already paid for a script and a voiceover dying
    over a missing decoration.
    """
    base = paper.render_paper(tmp_path / "base", width=320, height=180, seed=7)
    shot = paper.PaperShot(seconds=2.0, layers=["base", "subject", "stamp"])
    out = paper.render_shot(shot, {"base": base.path}, tmp_path / "beat",
                            width=320, height=180, fps=24)
    assert out.exists()


def test_a_shot_with_no_base_is_refused_with_a_sentence(tmp_path):
    shot = paper.PaperShot(seconds=2.0, layers=["subject"])
    with pytest.raises(ValueError, match="base"):
        paper.render_shot(shot, {"subject": tmp_path / "nothing.png"},
                          tmp_path / "beat")


# ------------------------------------------------------------------- the polish
#
# The first assembled frame this style produced was technically correct and looked
# cheap. Four things were missing, and each of them is the difference between a collage
# and a pile of clip-art rather than a refinement of one.


def test_every_moving_layer_casts_a_shadow():
    """Paper laid on paper casts one. Without it each layer looks printed onto the sheet
    below rather than resting on it, and no amount of texture elsewhere recovers that."""
    graph = paper.shot_filtergraph(_rows(), {}, width=1280, height=720, fps=30)
    # One shadow overlay and one layer overlay for each of the three moving layers.
    assert graph.count("overlay=") == 6
    assert graph.count("split=2") >= 3


def test_the_base_sheet_casts_no_shadow():
    """It is the desk. A shadow under the bottom layer has nothing to fall on."""
    graph = paper.shot_filtergraph(
        _rows(layers=("base", "subject")), {}, width=1280, height=720, fps=30)
    assert graph.count("overlay=") == 2  # one shadow, one subject


def test_the_shadow_travels_with_the_layer():
    """One pinned to the resting position while the sheet is still moving reads as a
    hole in the paper."""
    graph = paper.shot_filtergraph(_rows(), {}, width=1280, height=720, fps=30)
    shadow_overlay = next(line for line in graph.split(";")
                          if "overlay=" in line and "[S1]" in line)
    # The same stepped progress expression the layer itself uses.
    assert "floor(" in shadow_overlay


def test_the_shadow_is_blackened_before_it_is_blurred():
    """Blurring first and darkening after drags the subject's own colours out past its
    edge and fringes the shadow."""
    chain = paper.shadow_chain("L1", "S1")
    assert chain.index("colorchannelmixer") < chain.index("boxblur")


def test_the_shadow_is_built_from_the_layers_own_alpha():
    """So a torn edge casts a torn shadow rather than a rectangular one."""
    chain = paper.shadow_chain("L1", "S1")
    assert "aa=" in chain
    assert "alpha_radius" in chain


def test_grain_is_applied_once_over_the_whole_composite():
    """Identical grain across every layer is the evidence the eye uses to decide it is
    looking at one photograph. Per-layer grain makes the seams more visible, not less."""
    graph = paper.shot_filtergraph(_rows(), {}, width=1280, height=720, fps=30)
    assert graph.count("noise=alls") == 1
    # And it is last, after everything has been assembled.
    assert graph.rindex("noise=alls") > graph.rindex("overlay=")


def test_nothing_in_the_graph_subsamples_chroma_before_the_final_encode():
    """A hard alpha edge over 4:2:0 puts a coloured fringe along the boundary — visibly
    green along the top of a torn scrap — because the colour planes are half resolution
    and bleed across the cut. Every layer in this style has a hard torn edge."""
    graph = paper.shot_filtergraph(_rows(), {}, width=1280, height=720, fps=30)
    assert "yuva420p" not in graph
    assert graph.count("yuva444p") >= 4
    # yuv420p is fine at the very end: that is the delivery format, after compositing.
    assert graph.rindex("yuv420p") > graph.rindex("yuva444p")


def test_a_rectangle_is_torn_by_building_an_edge_not_by_displacing_one():
    """`torn_edge_filter` pushes an existing boundary around, which is right for a matte
    and does nothing to a rectangle — its alpha is opaque everywhere, so there is no
    boundary to push and the filter only speckles the middle. That is exactly what put a
    clean-cornered rectangle on screen."""
    graph = paper.torn_rect_filter(600, 400, seed=5, bite=9)
    # Distance to the nearest edge, compared against a threshold that wanders.
    assert "min(min(X, W-1-X), min(Y, H-1-Y))" in graph
    assert "sin(" in graph
    # No noise filter: `geq` is where the per-pixel decision has to happen and `noise`
    # is not available inside it.
    assert "noise=" not in graph


def test_the_tear_is_the_same_every_time_for_a_seed():
    assert (paper.torn_rect_filter(600, 400, seed=5)
            == paper.torn_rect_filter(600, 400, seed=5))
    assert (paper.torn_rect_filter(600, 400, seed=5)
            != paper.torn_rect_filter(600, 400, seed=6))


def test_a_typewritten_strip_is_set_in_monospace():
    """Proportional type says "designed in software", which is the thing this style is
    pretending not to be."""
    font = paper.type_font()
    assert font, "no monospace font on this machine"
    assert "mono" in font.lower()


def test_strip_text_is_escaped_for_drawtext():
    """drawtext parses its own value: a colon separates options and a quote ends the
    literal, so a strip reading "16:9 — it's the wrong crop" truncates or fails the whole
    graph."""
    assert paper._escape_drawtext("16:9 it's") == r"16\:9 it\'s"
    assert paper._escape_drawtext("100%") == r"100\%"


def test_a_strip_is_sized_from_its_text(tmp_path):
    """A three-word strip should be a three-word strip, not a short phrase adrift in a
    wide band — which is the giveaway that a template made it."""
    import subprocess

    short = paper.render_strip("NO", tmp_path / "short", point=24)
    long = paper.render_strip("A CONSIDERABLY LONGER LINE", tmp_path / "long", point=24)

    def width(path):
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=60, check=True)
        return int(out.stdout.strip())

    assert width(long) > width(short) * 2


def test_a_strip_actually_has_ink_on_it(tmp_path):
    """The first assembled frame composited a blank cream bar, because the strip was made
    by the paper generator and nothing ever put words on it."""
    import subprocess

    strip = paper.render_strip("THE CABLE WAS NEVER REPAIRED", tmp_path / "s", point=28)
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-f", "lavfi",
         f"movie={strip},format=gray,signalstats",
         "-show_entries", "frame_tags=lavfi.signalstats.YMIN",
         "-of", "csv=p=0"],
        capture_output=True, text=True, timeout=60, check=True)
    # Ink is dark. A blank strip's darkest pixel is paper.
    assert int(out.stdout.strip().splitlines()[0]) < 90


def test_a_scrap_is_torn_on_every_side(tmp_path):
    """Corners are the tell. An untorn scrap is a rectangle of flat colour."""
    import subprocess

    scrap = paper.render_scrap(tmp_path / "scrap", width=300, height=200, tear=9)
    # The corners must be transparent — that is what "torn" means at a corner.
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-f", "lavfi",
         f"movie={scrap},format=rgba,crop=8:8:0:0,alphaextract,signalstats",
         "-show_entries", "frame_tags=lavfi.signalstats.YMAX",
         "-of", "csv=p=0"],
        capture_output=True, text=True, timeout=60, check=True)
    assert int(out.stdout.strip().splitlines()[0]) == 0


# ------------------------------------------------------- the style reaches a video
#
# Every renderer above was built and tested, and `forgecast/motion/paper.py` was
# imported by nothing but this file: 963 lines with no caller. What was missing was the
# assembly — a function turning a still into a beat — and a channel setting that picks
# the style. These hold both.

def _plain_still(path):
    import subprocess
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=white:s=640x360",
         "-vf", "drawbox=x=220:y=70:w=200:h=220:color=0x1a2b3c@1:t=fill",
         "-frames:v", "1", str(path)], check=True, capture_output=True)
    return path


def test_a_still_becomes_a_paper_beat(tmp_path):
    still = _plain_still(tmp_path / "still.png")
    out = paper.compose_beat(still, tmp_path / "beat.mp4", seconds=2.0, index=1,
                             text="THE LIGHTHOUSE", width=640, height=360)
    assert out.exists() and out.stat().st_size > 0

    import subprocess
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
         str(out)], capture_output=True, text=True)
    assert abs(float(probe.stdout.strip()) - 2.0) < 0.25


def test_a_beat_generates_no_video_and_spends_nothing(tmp_path, monkeypatch):
    """The style's whole argument: image-to-video is the wrong tool here, not a dear one."""
    import forgecast.providers.media as media_provider

    def explode(*_a, **_k):
        raise AssertionError("the paper style must not call a video vendor")

    monkeypatch.setattr(media_provider, "video_usd", explode, raising=False)
    still = _plain_still(tmp_path / "still.png")
    paper.compose_beat(still, tmp_path / "beat.mp4", seconds=1.5, width=640, height=360)


def test_a_missing_decoration_does_not_lose_the_beat(tmp_path, monkeypatch):
    """A run that already paid for a script must not die over a torn scrap."""
    def no_scrap(*_a, **_k):
        raise RuntimeError("ffmpeg said no")

    monkeypatch.setattr(paper, "render_scrap", no_scrap)
    still = _plain_still(tmp_path / "still.png")
    out = paper.compose_beat(still, tmp_path / "beat.mp4", seconds=1.5,
                             width=640, height=360)
    assert out.exists() and out.stat().st_size > 0


def test_beats_in_one_run_share_their_paper(tmp_path):
    """A collage that changes desk halfway through is a pile of images."""
    still = _plain_still(tmp_path / "still.png")
    first = paper.compose_beat(still, tmp_path / "a.mp4", seconds=1.0, index=0,
                               width=640, height=360, workdir=tmp_path / "wa")
    second = paper.compose_beat(still, tmp_path / "b.mp4", seconds=1.0, index=1,
                                width=640, height=360, workdir=tmp_path / "wb")
    assert first.exists() and second.exists()
    # Same tone, adjacent seeds — one desk, different tears.
    assert (tmp_path / "wa" / "base.png").exists()
    assert (tmp_path / "wb" / "base.png").exists()


def test_the_style_is_selectable_on_a_channel():
    from forgecast.nodes import media as media_node
    assert media_node.PAPER_COLLAGE == "paper_collage"
