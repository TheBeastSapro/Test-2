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
