"""Moving a creature's arm without moving the creature.

This is the gap `render/layered` named and could not close: the reference's Amber
stretches an arm while its torso holds still, and translating or turning the whole
cut-out cannot imitate that however carefully it is tuned.

Two questions, and the first is the harder one — *which pixels are an arm*. A
part-segmentation model is the obvious reach and the wrong tool: those are trained on
people and animals, and a black slime with two claws is neither. The question is
simpler than semantics anyway. A limb is a thin thing sticking out of a thick thing,
and the alpha channel already carries that.

The route to the working method is worth keeping, because two plausible versions of it
are wrong on real assets and both looked right in code:

* walking each skeleton endpoint back to its first junction returns terminal *twigs* —
  on Seek's Sludgey2 that found one claw finger and missed both arms, because an arm
  ending in a three-fingered claw has the fingers as branches and the arm as an
  internal segment;
* thresholding the *mask* by thickness fails differently: every silhouette has a thin
  shell around it, so the body's rim joins both arms into one region.

Thresholding the skeleton works, and is stable — Sludgey2 reports its two arms at 0.35,
0.45 and 0.55.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from forgecast.layers import parts, warp

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                  reason="ffmpeg is not installed")


@pytest.fixture
def creature(tmp_path: Path) -> Path:
    """A fat body with two thin arms — the shape the detector is about.

    Deliberately not a photograph of anything: the method is a shape method, and a
    fixture that needed to look like a monster would be testing the artwork.
    """
    image = Image.new("RGBA", (600, 600), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)
    pen.ellipse([(180, 260), (420, 560)], fill=(210, 60, 60, 255))   # body
    pen.line([(230, 300), (90, 90)], fill=(210, 60, 60, 255), width=26)   # left arm
    pen.line([(370, 300), (510, 90)], fill=(210, 60, 60, 255), width=26)  # right arm
    path = tmp_path / "creature.png"
    image.save(path)
    return path


# ------------------------------------------------------------------- finding them


def test_both_arms_are_found_and_the_body_is_not(creature):
    limbs = parts.find(Image.open(creature))

    assert len(limbs) == 2, f"expected two arms, got {len(limbs)}"
    # Anchors at the shoulders, tips out at the hands: every anchor is lower on the
    # image than every tip, which is what "sticking out of the body" means here.
    for limb in limbs:
        assert limb.anchor[1] > limb.tip[1]
        assert limb.reach >= parts.MIN_REACH


def test_a_creature_that_is_one_mass_reports_no_limbs(tmp_path):
    """The common case, and not a failure. Most cut-outs are a body; the caller holds
    them still rather than inventing a joint."""
    blob = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    ImageDraw.Draw(blob).ellipse([(80, 80), (320, 320)], fill=(200, 50, 50, 255))
    path = tmp_path / "blob.png"
    blob.save(path)

    assert parts.find(path) == []


def test_a_hole_in_the_matte_is_not_an_arm(tmp_path):
    """An eye punched through a cut-out is a hole in the mask, and the skeleton of a
    shape with holes runs *around* them — so the loop's ends read as limbs."""
    holed = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    pen = ImageDraw.Draw(holed)
    pen.ellipse([(60, 60), (340, 340)], fill=(200, 50, 50, 255))
    pen.ellipse([(150, 150), (250, 250)], fill=(0, 0, 0, 0))     # the eye

    path = tmp_path / "holed.png"
    holed.save(path)

    assert parts.find(path) == []


def test_a_limb_owns_its_own_flesh_and_fades_at_the_shoulder(creature):
    """The weight is what makes this a warp rather than a cut and paste. At the tip it
    is full, at the anchor it is nothing, and the limbs do not claim each other."""
    limbs = parts.find(Image.open(creature))
    left, right = sorted(limbs, key=lambda limb: limb.tip[0])

    assert left.weight[left.tip[1], left.tip[0]] > 0.5
    assert left.weight[left.anchor[1], left.anchor[0]] < 0.4
    # The other arm's tip is not in this arm's weight.
    assert left.weight[right.tip[1], right.tip[0]] < 0.05


# -------------------------------------------------------------------- moving them


def _bounds(image: Image.Image, box) -> tuple[int, int, int, int] | None:
    region = np.array(image.convert("RGBA").crop(box).getchannel("A")) >= 40
    if not region.any():
        return None
    rows, columns = np.where(region)
    return int(columns.min()), int(rows.min()), int(columns.max()), int(rows.max())


def test_bending_moves_the_arms_and_leaves_the_body_where_it_was(creature):
    """The whole claim, measured on the silhouette rather than on the colours."""
    image = Image.open(creature).convert("RGBA")
    limbs = parts.find(image)

    bent = warp.bend(image, limbs, [0.30, -0.30])

    arms = (0, 0, 600, 240)
    body = (150, 400, 450, 600)
    assert _bounds(bent, arms) != _bounds(image, arms), "the arms did not move"
    assert _bounds(bent, body) == _bounds(image, body), "the body moved"


def test_a_zero_angle_changes_nothing(creature):
    """A limb at rest has to resample to itself, or every shot acquires a soft frame
    wherever the swing crosses zero."""
    image = Image.open(creature).convert("RGBA")
    limbs = parts.find(image)

    still = warp.bend(image, limbs, [0.0, 0.0])

    assert _bounds(still, (0, 0, 600, 600)) == _bounds(image, (0, 0, 600, 600))


def test_a_subject_with_no_limbs_comes_back_untouched(tmp_path):
    blob = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    ImageDraw.Draw(blob).ellipse([(40, 40), (160, 160)], fill=(200, 50, 50, 255))

    assert warp.bend(blob, [], []) is blob


def test_the_arms_do_not_swing_in_lockstep(creature):
    """Two arms moving together is a semaphore. The offset is derived from the limb's
    index rather than randomised, so a shot re-renders identically."""
    limbs = parts.find(Image.open(creature))

    angles = warp.swing(limbs, 0.4)

    assert len(angles) == len(limbs)
    assert abs(angles[0] - angles[1]) > 1e-3


# --------------------------------------------------------------- through the render


@needs_ffmpeg
def test_the_bend_reaches_the_rendered_clip(creature, tmp_path, monkeypatch):
    """Rendered twice, with and without, and compared at matched frames.

    Matched frames rather than frames of one clip: the drift has a one-pixel amplitude
    floor, and on a textured subject one pixel of travel changes enough of the frame to
    bury the thing being measured. Identical in both clips, it cancels.
    """
    from forgecast.layers import shot as shot_layers
    from forgecast.render import layered
    from forgecast.render.ffmpeg import run_ffmpeg

    monkeypatch.setattr(shot_layers, "DRIFT_X", 0.0)
    monkeypatch.setattr(shot_layers, "DRIFT_Y", 0.0)

    plate = Image.new("RGB", (1200, 700), (20, 20, 26))
    pen = ImageDraw.Draw(plate)
    for index in range(0, 1200, 40):
        pen.line([(index, 0), (index, 700)], fill=(60, 55, 50), width=6)
    plate_path = tmp_path / "plate.png"
    plate.save(plate_path)

    frames: dict[str, list] = {}
    for tag, bend in (("bend", True), ("flat", False)):
        clip = layered.drift_clip(creature, plate_path, tmp_path / f"{tag}.mp4",
                                  seconds=2.0, width=480, height=270, fps=12,
                                  sway=False, bend=bend)
        out = tmp_path / f"fr_{tag}"
        out.mkdir()
        run_ffmpeg(["-i", str(clip), "-vf", r"select='eq(n\,0)+eq(n\,11)'",
                    "-vsync", "0", str(out / "f%02d.png")], label="sample")
        frames[tag] = [np.array(Image.open(path).convert("RGB")).astype(int)
                       for path in sorted(out.glob("*.png"))]

    assert frames["bend"] and len(frames["bend"]) == len(frames["flat"])
    moved = max(
        int((np.abs(a - b).max(axis=2) > 25).sum())
        for a, b in zip(frames["bend"], frames["flat"], strict=True))
    assert moved > 200, f"the bend did not reach the clip (only {moved}px differ)"


# ------------------------------------------------- the plate that is one shot long


@needs_ffmpeg
def test_seeking_past_the_end_of_a_short_plate_still_yields_a_clip(tmp_path):
    """The bug that killed the first canon run that ever reached the renderer.

    A video plate is normally long enough for several shots, so the cutting plan seeks
    into it. An animated canon shot is not: `drift_clip` renders it at the shot's own
    length — 3.03 seconds — and the plan then seeks 6 seconds in for the second shot
    sharing that plate. ffmpeg decodes no frames and writes a 262-byte file with no
    duration *without failing*, so the run died much later at the concat with "could
    not read duration", having already paid for every stage upstream.

    `-vsync cfr` holds the last frame of a source that is merely short. It cannot hold
    a frame that was never decoded.
    """
    from forgecast.render.ffmpeg import (
        RenderError,
        ffprobe_duration,
        normalise_clip,
        still_to_clip,
    )

    frame = Image.new("RGB", (640, 360), (40, 30, 30))
    ImageDraw.Draw(frame).ellipse([(200, 100), (440, 260)], fill=(200, 60, 60))
    still = tmp_path / "still.png"
    frame.save(still)
    source = still_to_clip(still, tmp_path / "short.mp4", 3.0,
                           width=640, height=360, fps=30)
    assert ffprobe_duration(source) < 4.0

    out = normalise_clip(source, tmp_path / "cut.mp4", 3.0,
                         width=640, height=360, seek=6.0, fps=30)

    assert out.stat().st_size > 1000, "a seek past the end produced an empty file"
    try:
        assert ffprobe_duration(out) > 1.0
    except RenderError:  # pragma: no cover - this is the bug, stated plainly
        raise AssertionError("the clip has no readable duration") from None
