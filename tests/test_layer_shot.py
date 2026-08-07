"""A subject standing on a plate — the shot this genre is made of.

`layers/compose.py` puts things behind a subject cut from its own photograph. This is
the other half: a subject that arrives separately, placed onto a background it was never
photographed in. That is the measured shot model of the canon-explainer format — the
creature is the franchise's artwork, the environment is a plate, and the shot is the
first over the second. Nothing in this app assembled that; it generated whole frames,
which cannot produce a named entity an audience already recognises.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from forgecast.layers.shot import (
    ALPHA_FLOOR,
    HORIZON,
    SUBJECT_HEIGHT,
    opaque_box,
    place,
)


def _subject(tmp_path, *, margin: int = 300, size: int = 1000):
    """A blob on a large transparent canvas — the shape these assets arrive in."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse(
        [(margin, margin), (size - margin, size - margin)], fill=(200, 40, 40, 255))
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "subject.png"
    image.save(path)
    return path


def _plate(tmp_path, *, size=(800, 600)):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "plate.png"
    Image.new("RGB", size, (30, 34, 48)).save(path)
    return path


def test_the_subject_stands_on_the_horizon_rather_than_floating(tmp_path):
    placed = place(_subject(tmp_path), _plate(tmp_path), tmp_path / "out.png",
                   width=1600, height=900)

    assert abs(placed.subject_box[3] - 900 * HORIZON) <= 2


def test_the_subject_is_scaled_by_its_opaque_region_not_its_canvas(tmp_path):
    """These assets carry wildly different margins. Scaling by file dimensions puts two
    subjects at two apparent sizes in one video, which reads as a mistake to somebody
    who cannot say why."""
    wide = place(_subject(tmp_path / "a", margin=100), _plate(tmp_path / "a"),
                 tmp_path / "a" / "o.png", width=1600, height=900)
    tight = place(_subject(tmp_path / "b", margin=420), _plate(tmp_path / "b"),
                  tmp_path / "b" / "o.png", width=1600, height=900)

    def height(box):
        return box[3] - box[1]

    assert abs(height(wide.subject_box) - height(tight.subject_box)) <= 3
    assert abs(height(wide.subject_box) - 900 * SUBJECT_HEIGHT) <= 3


def test_faint_matte_haze_does_not_blow_out_the_measured_box():
    """The bug this was found with. A matte is not a clean binary mask — it leaves a
    haze of very low alpha across the region it rejected, and `getbbox()` counts any
    non-zero pixel. On a real asset that put the box at nearly the full canvas, which
    scaled the creature to a fraction of its size and anchored its shadow several
    hundred pixels below its feet. The numbers alone looked plausible; rendering the
    shot and looking at it is what showed it."""
    image = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    # A real subject in the middle...
    ImageDraw.Draw(image).rectangle([(150, 150), (250, 250)], fill=(255, 0, 0, 255))
    # ...and one nearly-invisible stray pixel in the corner.
    image.putpixel((5, 5), (255, 0, 0, ALPHA_FLOOR - 20))

    assert image.getchannel("A").getbbox() == (5, 5, 251, 251)     # what raw would say
    assert opaque_box(image) == (150, 150, 251, 251)               # what we use


def test_a_subject_that_is_entirely_faint_still_reports_a_box():
    """A threshold that finds nothing must fall back rather than return an empty box —
    an empty box divides by zero on the way to a scale factor."""
    image = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle([(10, 10), (60, 60)], fill=(255, 0, 0, 5))

    assert opaque_box(image) == (10, 10, 61, 61)


def test_an_image_with_no_alpha_is_placed_rather_than_refused(tmp_path):
    """Not every asset worth using arrives pre-cut. A caller that wanted a matte should
    have asked `layers.matte` for one; failing silently here would be a different kind
    of wrong."""
    flat = tmp_path / "flat.png"
    Image.new("RGB", (500, 500), (10, 200, 10)).save(flat)

    placed = place(flat, _plate(tmp_path), tmp_path / "o.png", width=1600, height=900)

    assert Image.open(placed.path).size == (1600, 900)


def test_the_plate_is_covered_not_stretched(tmp_path):
    """An aspect-distorted background is the most obvious tell in a composite."""
    tall = tmp_path / "tall.png"
    Image.new("RGB", (400, 1600), (12, 12, 12)).save(tall)

    placed = place(_subject(tmp_path), tall, tmp_path / "o.png", width=1600, height=900)
    out = Image.open(placed.path)

    assert out.size == (1600, 900)
    # Every edge is plate: a contain-fit would leave letterbox bars.
    for xy in ((2, 2), (1597, 2), (2, 897), (1597, 897)):
        assert out.getpixel(xy) != (0, 0, 0)


def test_the_offset_makes_room_on_one_side_for_a_bubble(tmp_path):
    """The reference does exactly this on its gag shots — the subject moves off centre
    so the speech bubble has somewhere to be."""
    centred = place(_subject(tmp_path / "c"), _plate(tmp_path / "c"),
                    tmp_path / "c" / "o.png", width=1600, height=900)
    shifted = place(_subject(tmp_path / "s"), _plate(tmp_path / "s"),
                    tmp_path / "s" / "o.png", width=1600, height=900, offset_x=-0.2)

    assert shifted.subject_box[0] < centred.subject_box[0]
    assert abs((centred.subject_box[0] - shifted.subject_box[0]) - 0.2 * 1600) <= 2


def test_the_composite_records_what_went_into_it(tmp_path):
    """A shot nobody can trace back to its sources is a shot nobody can re-cut or
    attribute."""
    subject, plate = _subject(tmp_path), _plate(tmp_path)
    placed = place(subject, plate, tmp_path / "o.png", width=800, height=450)

    assert placed.as_dict()["layers"] == [str(plate), str(subject)]
    assert placed.as_dict()["subject_box"] == list(placed.subject_box)
