"""A shot where the subject moves and the plate does not.

`layers/shot.py` has carried a `subject_box` since it was written, documented as being
there so "the motion layer needs this to push the subject on its own track" — and
nothing used it. The planner has marked shots `animate` for as long, and nothing read
that either, so the ration it computes decided nothing and every canon shot was a still
whatever the plan said.

The distinction these tests exist to hold is the one that is easy to lose. A Ken Burns
push moves every pixel together, which is a camera move — correct for a photograph,
wrong for a cut-out standing on a background it was never photographed in. Two layers at
two rates is parallax, and no whole-frame transform imitates it. So the test that
matters measures the plate corners as well as the subject.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw

from forgecast.layers import shot as layers

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                  reason="ffmpeg is not installed")


@pytest.fixture
def assets(tmp_path: Path) -> tuple[Path, Path]:
    """A transparent subject with a wide empty margin, and a textured plate.

    The margin is the case that matters: these assets arrive as 2250x2250 PNGs with the
    creature somewhere in the middle, and the whole reason `opaque_box` exists is that
    scaling by file size puts two subjects at two apparent sizes in one video.
    """
    subject = Image.new("RGBA", (1000, 1000), (0, 0, 0, 0))
    ImageDraw.Draw(subject).ellipse([(400, 300), (600, 800)], fill=(220, 40, 40, 255))
    subject_path = tmp_path / "subject.png"
    subject.save(subject_path)

    plate = Image.new("RGB", (2400, 1350), (20, 20, 24))
    draw = ImageDraw.Draw(plate)
    for index in range(0, 2400, 40):
        draw.line([(index, 0), (index, 1350)], fill=(60, 55, 50), width=6)
    plate_path = tmp_path / "plate.png"
    plate.save(plate_path)
    return subject_path, plate_path


def test_the_split_layers_land_where_the_flat_composite_puts_them(assets, tmp_path):
    """`prepared` and `place` must agree to the pixel.

    A second copy of the scale-and-anchor arithmetic is how a still and its animated
    version come to put the same creature at two different sizes in one video — the
    kind of defect that renders fine and is visible only when the two cut together.
    """
    subject_path, plate_path = assets

    split = layers.prepared(subject_path, plate_path, tmp_path / "split")
    flat = layers.place(subject_path, plate_path, tmp_path / "flat")

    assert split["subject_box"] == list(flat.subject_box)
    assert Path(split["plate"]).exists()
    assert Image.open(split["subject"]).mode == "RGBA"


def test_the_prepared_plate_already_carries_the_contact_shadow(assets, tmp_path):
    """Baked in at the rest position rather than tracked. The drift is under 2% of frame
    width and the shadow is a soft ellipse, so a third moving input would cost a filter
    input for no visible difference — but a plate with *no* shadow reads as two flat
    layers, which is the whole thing the shadow exists to stop."""
    subject_path, plate_path = assets

    split = layers.prepared(subject_path, plate_path, tmp_path / "with")
    bare = layers.prepared(subject_path, plate_path, tmp_path / "without", shadow=False)

    difference = ImageChops.difference(
        Image.open(split["plate"]).convert("RGB"),
        Image.open(bare["plate"]).convert("RGB"))
    assert difference.getbbox() is not None


@needs_ffmpeg
def test_the_subject_moves_and_the_plate_does_not(assets, tmp_path):
    """The measurement that separates this from a Ken Burns push.

    Sampled at three points in the clip: the region around the subject must change, and
    the far corners of the plate must be byte-identical. A push would move both.
    """
    from forgecast.render.layered import drift_clip

    subject_path, plate_path = assets
    clip = drift_clip(subject_path, plate_path, tmp_path / "drift.mp4",
                      seconds=3.5, width=960, height=540, fps=24)
    assert clip.exists() and clip.stat().st_size > 0

    frames = tmp_path / "frames"
    frames.mkdir()
    from forgecast.render.ffmpeg import run_ffmpeg
    run_ffmpeg(["-i", str(clip), "-vf", r"select='eq(n\,0)+eq(n\,40)+eq(n\,79)'",
                "-vsync", "0", str(frames / "f%02d.png")], label="sample")

    shots = [Image.open(path).convert("RGB") for path in sorted(frames.glob("*.png"))]
    assert len(shots) >= 2, "the clip was too short to sample"

    first, last = shots[0], shots[-1]
    # The subject moved: somewhere in the frame, something changed a lot.
    peak = max(band[1] for band in ImageChops.difference(first, last).getextrema())
    assert peak > 100, f"nothing moved (peak difference {peak})"

    # The plate did not: the corners are the same pixel in every frame. Sampled inside
    # the border rather than on it, because h264 treats the outermost pixels specially.
    for frame in shots:
        assert frame.getpixel((4, 4)) == first.getpixel((4, 4))
        assert frame.getpixel((955, 535)) == first.getpixel((955, 535))


@needs_ffmpeg
def test_two_shots_of_one_creature_do_not_start_the_same_move(assets, tmp_path):
    """A visible loop is what reads as cheap, and two cuts of one creature is the place it
    would show. The phase is per shot for exactly that."""
    from forgecast.render.layered import drift_clip

    subject_path, plate_path = assets
    one = drift_clip(subject_path, plate_path, tmp_path / "a.mp4", seconds=1.0,
                     width=480, height=270, fps=12, phase=0.0)
    two = drift_clip(subject_path, plate_path, tmp_path / "b.mp4", seconds=1.0,
                     width=480, height=270, fps=12, phase=1.7)

    assert one.read_bytes() != two.read_bytes()


# ------------------------------------------------------------------------- the lean
#
# The drift moves the whole cut-out. This is the second half: the subject also leans,
# pivoting on its feet, so the crown travels and the contact point does not.
#
# It is a sway, and the module says so. The reference's Amber moves an *arm*
# independently of its torso, and nothing here knows where an arm is — that needs the
# subject segmented into parts, which is a different piece of work and is still open.
# What this does is shift the creature's weight, which is the thing a rigid translation
# cannot do and the reason a composite otherwise reads as a sticker sliding.


def _subject_columns(image, y0, y1):
    """Mean x of the subject's pixels in a horizontal band, or None.

    Found by channel dominance rather than by alpha: this reads the *rendered* frame,
    which is opaque RGB, so the only thing separating subject from plate is that the
    subject is red and the plate is grey.
    """
    pixels = image.load()
    columns = [x for y in range(y0, y1) for x in range(image.width)
               if pixels[x, y][0] > 120 and pixels[x, y][0] > pixels[x, y][1] + 60]
    return sum(columns) / len(columns) if columns else None


def _crown_and_feet(clip: Path, tmp_path: Path, frames_at: str) -> tuple[list, list]:
    from forgecast.render.ffmpeg import run_ffmpeg

    frames = tmp_path / f"{clip.stem}_frames"
    frames.mkdir(exist_ok=True)
    run_ffmpeg(["-i", str(clip), "-vf", frames_at, "-vsync", "0",
                str(frames / "f%02d.png")], label="sample")

    crowns, feet = [], []
    for path in sorted(frames.glob("*.png")):
        image = Image.open(path).convert("RGB")
        rows = [y for y in range(image.height)
                if _subject_columns(image, y, y + 1) is not None]
        assert rows, "the subject was not visible in a sampled frame"
        crowns.append(_subject_columns(image, rows[0], rows[0] + 12))
        feet.append(_subject_columns(image, rows[-1] - 12, rows[-1]))
    return crowns, feet


@needs_ffmpeg
def test_the_lean_pivots_on_the_feet_and_not_on_the_middle_of_the_picture(
        assets, tmp_path, monkeypatch):
    """`rotate` turns an image about its own centre. The correction that moves that
    pivot down to the contact point is what makes the lean *exist*, not merely what
    makes it correct — which is the opposite of what I assumed before measuring.

    Turning about the centre swings the crown one way and the feet the other, by
    similar small amounts, so the creature pivots around its own waist and almost
    nothing reads. Measured on the fixture below: crown travel 3.09px against a 2.07px
    floor, i.e. nothing. With the pivot moved to the feet the crown travels 8.22px and
    the feet stay put, which is a creature shifting its weight.

    The drift is zeroed here because it moves crown and feet together and would bury
    the thing being measured. Its amplitude has a one-pixel floor, so "off" is a ~2px
    band and that band is the baseline every figure below is read against.
    """
    from forgecast.render import layered

    monkeypatch.setattr(layers, "DRIFT_X", 0.0)
    monkeypatch.setattr(layers, "DRIFT_Y", 0.0)
    subject_path, plate_path = assets
    sample = r"select='eq(n\,0)+eq(n\,56)+eq(n\,112)+eq(n\,168)'"

    def spread(values):
        return max(values) - min(values)

    leaning = layered.drift_clip(subject_path, plate_path, tmp_path / "lean.mp4",
                                 seconds=9.0, width=960, height=540, fps=25, sway=True)
    flat = layered.drift_clip(subject_path, plate_path, tmp_path / "flat.mp4",
                              seconds=9.0, width=960, height=540, fps=25, sway=False)

    lean_crown, lean_feet = _crown_and_feet(leaning, tmp_path, sample)
    floor_crown, _floor_feet = _crown_and_feet(flat, tmp_path, sample)

    # The crown moves, and by a lot more than the integer-rounding floor.
    assert spread(lean_crown) > 2 * spread(floor_crown), (
        f"crown travelled {spread(lean_crown):.2f}px against a floor of "
        f"{spread(floor_crown):.2f}px")

    # And it moves far more than the feet do. This is the assertion that fails if the
    # pivot correction is dropped: without it the two are within a pixel of each other.
    assert spread(lean_crown) > 2 * spread(lean_feet), (
        f"crown {spread(lean_crown):.2f}px vs feet {spread(lean_feet):.2f}px — "
        f"the pivot is in the middle of the picture, not on the ground")


def test_the_contact_point_is_reported_relative_to_the_image_centre(assets, tmp_path):
    """Because that is the point `rotate` turns about. Reported in the subject's own
    coordinates, not the frame's — the rotation happens before the overlay."""
    subject_path, plate_path = assets

    made = layers.prepared(subject_path, plate_path, tmp_path / "p")

    width, height = made["subject_size"]
    dx, dy = made["contact"]
    # The test subject is an ellipse centred horizontally with its base below middle.
    assert abs(dx) < width * 0.05, "the contact point should sit near the centre line"
    assert dy > 0, "the feet are below the image centre"
    assert Image.open(made["subject"]).size == (width, height)


# ------------------------------------------------------- subject or already a shot
#
# Found while starting the limb warp: half the assets I had been treating as cut-outs
# are not cut-outs. `Asset.is_portrait_crop` decides from the dimensions, and both
# shapes are square — Amber's artwork on doctor-nowhere-creatures is a 2265x2265
# *photograph* of the creature on a road at night, fully opaque. The compositor scaled
# that whole picture and pasted it onto a generated plate, which rendered a photo stuck
# on wallpaper, and had done since the lane was built.


def test_transparency_and_not_shape_decides_what_is_a_cut_out(tmp_path):
    """Measured across seven real assets off three wikis: the three scene shots are
    0.000 transparent and the three cut-outs are 0.565, 0.693 and 0.767. Nothing is
    tuned — the threshold only has to sit in an enormous gap."""
    square_photo = Image.new("RGB", (600, 600), (40, 40, 50))
    cutout = Image.new("RGBA", (600, 600), (0, 0, 0, 0))
    ImageDraw.Draw(cutout).ellipse([(200, 100), (400, 500)], fill=(200, 40, 40, 255))

    photo_path = tmp_path / "photo.png"
    cut_path = tmp_path / "cut.png"
    square_photo.save(photo_path)
    cutout.save(cut_path)

    assert layers.is_cutout(cut_path)
    assert not layers.is_cutout(photo_path)
    # Both are square, so the shape test cannot tell them apart — which is the bug.
    assert square_photo.size == cutout.size


def test_an_image_saved_with_alpha_but_fully_opaque_is_still_a_shot(tmp_path):
    """RGBA is not the test either. A scene exported as a PNG with an alpha channel it
    never uses is a whole shot with four channels."""
    opaque = Image.new("RGBA", (400, 400), (30, 30, 30, 255))
    path = tmp_path / "opaque_rgba.png"
    opaque.save(path)

    assert not layers.is_cutout(path)
