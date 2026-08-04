"""Putting things behind the subject, which is the whole point of having cut it out.

## The one effect worth building first

Text behind the subject. A title sits in the frame, the subject's head and shoulder pass
in front of it, and the viewer reads it as a physical object in the scene rather than as
a caption laid on top. It is the most recognisable mark of a skilled editor on the
platforms this app publishes to, and it is mechanically trivial once a matte exists:

    background → text → subject-with-alpha

Three layers in that order. The difficulty was never the compositing; it was having the
subject on its own layer, which is what `matte` is for.

## Why the text is placed against the subject rather than centred

A title centred in the frame and then occluded is a title you cannot read. The subject's
opaque region is known from the matte, so the text is positioned to overlap it by a
*controlled* amount — enough that the occlusion is unmistakably deliberate, not so much
that the word is lost. `OVERLAP_TARGET` is that amount, and it is the difference between
the effect reading as designed and reading as a mistake.

## Why there is a shadow under the subject and not a stroke around it

A stroke says "this was cut out". A shadow says "this is in front of something". They
are the same operation from the compositor's point of view and opposite in what they
communicate — a hard outline is exactly the tell that the matte was automatic, which is
the impression this whole layer exists to avoid.

The shadow is deliberately soft and low-contrast. A drop shadow you can see is a drop
shadow that is too strong; its job is to separate the subject from the background by
about the amount a real light would, and no more.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# How much of the text's height the subject should cover. A quarter is enough for the
# occlusion to be unmistakable while leaving the word readable — the effect fails in
# both directions, and it fails more often by hiding too much than too little.
OVERLAP_TARGET = 0.26

# The shadow. Offset and blur as a fraction of frame height so it holds at any
# resolution, and an opacity low enough that it separates without being seen.
SHADOW_OFFSET = 0.012
SHADOW_BLUR = 0.018
SHADOW_OPACITY = 0.38


@dataclass
class Layered:
    """One finished composite, and what went into it."""

    path: str
    width: int
    height: int
    layers: list[str]

    def as_dict(self) -> dict:
        return {"path": self.path, "width": self.width, "height": self.height,
                "layers": list(self.layers)}


def _font(size: int):
    """The heaviest face available, because this text is a graphic element.

    A title behind a subject is competing with a photograph for attention and losing at
    any weight below bold. Pillow's default bitmap font is the last resort and looks it,
    so it is worth walking a list first — and on a machine with none of these the
    composite is still produced rather than refused.
    """
    from PIL import ImageFont

    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    )
    for name in candidates:
        if Path(name).is_file():
            try:
                return ImageFont.truetype(name, size)
            except OSError:                                           # pragma: no cover
                continue
    return ImageFont.load_default()


def _subject_box(alpha) -> tuple[int, int, int, int]:
    """The bounding box of everything opaque, so the text can be placed against it."""
    import numpy as np

    rows = np.where(alpha.max(axis=1) > 200)[0]
    cols = np.where(alpha.max(axis=0) > 200)[0]
    if not len(rows) or not len(cols):                                # pragma: no cover
        return 0, 0, alpha.shape[1], alpha.shape[0]
    return int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1])


def _shadow(subject, height: int):
    """A soft shadow cast by the subject's own alpha.

    From the matte rather than from a shape: a shadow that does not match the silhouette
    is worse than none, because it tells the viewer the subject was pasted.
    """
    from PIL import Image, ImageFilter

    alpha = subject.getchannel("A").point(lambda v: int(v * SHADOW_OPACITY))
    blurred = alpha.filter(ImageFilter.GaussianBlur(max(1, int(height * SHADOW_BLUR))))
    layer = Image.new("RGBA", subject.size, (0, 0, 0, 0))
    layer.putalpha(blurred)
    return layer


def text_behind(matte_path: Path | str, out_path: Path | str, text: str, *,
                background: Path | str | None = None,
                colour: tuple[int, int, int] = (255, 255, 255),
                shadow: bool = True) -> Layered:
    """Composite `text` behind the cut-out subject.

    `background` is the plate the subject came from, or any other image. Omitted, the
    subject sits on transparency — which is what a caller compositing over generated
    video wants.
    """
    import numpy as np
    from PIL import Image, ImageDraw

    subject = Image.open(Path(matte_path)).convert("RGBA")
    width, height = subject.size
    layers = ["background", "text", "subject"]

    if background is not None:
        with Image.open(Path(background)) as plate:
            base = plate.convert("RGBA").resize((width, height))
    else:
        base = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        layers[0] = "transparent"

    # Sized to the frame, not to the string. A title that shrinks because the words are
    # long stops being the same design from one video to the next.
    size = max(24, int(height * 0.17))
    font = _font(size)
    drawn = ImageDraw.Draw(base)
    left, top, right, bottom = drawn.textbbox((0, 0), text, font=font)
    text_width, text_height = right - left, bottom - top

    # Placed against the subject rather than in the middle of the frame: centred text
    # that is then occluded is text nobody can read.
    box_left, box_top, box_right, _box_bottom = _subject_box(
        np.array(subject)[:, :, 3])
    x = max(0, (box_left + box_right) // 2 - text_width // 2 - left)
    y = max(0, int(box_top - text_height * (1.0 - OVERLAP_TARGET)) - top)

    drawn.text((x, y), text, font=font, fill=(*colour, 255))

    if shadow:
        base = Image.alpha_composite(base, _shadow(subject, height))
        layers.insert(2, "shadow")

    composite = Image.alpha_composite(base, subject)
    target = Path(out_path).with_suffix(".png")
    target.parent.mkdir(parents=True, exist_ok=True)
    composite.save(target)

    return Layered(path=str(target), width=width, height=height, layers=layers)
