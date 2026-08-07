"""A subject standing on a plate — the shot this genre is actually made of.

`compose.py` puts things *behind* a subject that was cut out of its own photograph. This
module is the other half: a subject that arrives already separate, placed onto a
background it was never photographed in.

That is the measured shot model of the canon-explainer format. The creature is the
franchise's own artwork, fetched rather than generated because the audience knows what
it looks like; the environment is a plate; and the shot is the first laid over the
second. Nothing in this app assembled that. It generated whole frames, which cannot
produce a named entity an audience already recognises.

## Why the subject is scaled to the frame's height and not its width

These assets are square more often than not — a 1284×1284 PNG with a creature standing
in the middle of it. Fitting such an image to width makes the creature small and the
transparent margin enormous. Fitting the *opaque* region to a fraction of frame height
puts the subject at a believable size regardless of how much empty canvas its author
left around it, which is why `place` measures the alpha before it measures the file.

## Why the horizon matters

A creature composited with its feet in the middle of the frame is floating. The anchor
is the bottom of the subject's opaque region, placed on a horizon line low in the frame,
so the subject stands on the plate rather than hovering over it. That single decision is
most of the difference between a composite that reads as a shot and one that reads as a
sticker.

## Why there is a contact shadow

Same reasoning as `compose.SHADOW_*`, applied downwards instead of behind: a soft dark
ellipse where the subject meets the ground. Without it the eye reads two flat layers.
With it — and only if it stays subtle — the eye reads depth. A shadow you notice is too
strong.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageFilter

#: Where the subject's feet land, as a fraction of frame height. Low, but not on the
#: edge: a plate usually has some foreground, and a subject standing at 1.0 is standing
#: on the frame border rather than in the scene.
HORIZON = 0.93

#: How tall the subject's opaque region is drawn, as a fraction of frame height. Big
#: enough to be the subject of the shot, short enough to leave the plate readable — the
#: reference's creatures fill most of the frame's height and none of them are cropped.
SUBJECT_HEIGHT = 0.78

#: Contact shadow, all as fractions of frame height so they hold at any resolution.
SHADOW_HEIGHT = 0.022
SHADOW_BLUR = 0.014
SHADOW_OPACITY = 0.42
SHADOW_WIDTH = 0.62      # of the subject's own width


@dataclass
class Placed:
    """One composite, and enough about it to animate the subject separately later."""

    path: str
    width: int
    height: int
    #: The subject's box in the finished frame, in pixels. The motion layer needs this
    #: to push the subject on its own track — parallax is the subject and the plate
    #: moving at different rates, and that cannot be planned without knowing where the
    #: subject ended up.
    subject_box: tuple[int, int, int, int]
    layers: list[str]

    def as_dict(self) -> dict:
        return {"path": self.path, "width": self.width, "height": self.height,
                "subject_box": list(self.subject_box), "layers": list(self.layers)}


#: Alpha below this does not count as the subject. A matte is not a clean binary mask —
#: it leaves a haze of 1-to-20 alpha across the region it rejected, and `getbbox()`
#: counts any non-zero pixel. That haze put the measured box at nearly the full canvas
#: on a real asset, which scaled the creature to a fraction of its intended size and
#: anchored the shadow in empty space several hundred pixels below its feet. Found by
#: rendering a shot and looking at it; the numbers alone looked right.
ALPHA_FLOOR = 40


def opaque_box(image: Image.Image, floor: int = ALPHA_FLOOR) -> tuple[int, int, int, int]:
    """The subject's actual bounds inside its canvas.

    Measured rather than assumed. These assets carry wildly different amounts of empty
    margin — the same creature at the same file size can occupy half its canvas or all
    of it — so scaling by file dimensions puts two subjects at two different apparent
    sizes in the same video, which reads as a mistake even to somebody who cannot say
    why.

    Thresholded rather than taken raw, for the reason on `ALPHA_FLOOR`. A subject whose
    every pixel is faint is a subject that is not there, so a threshold that finds
    nothing falls back to the raw box rather than returning an empty one.
    """
    if image.mode != "RGBA":
        return (0, 0, image.width, image.height)
    alpha = image.getchannel("A")
    box = alpha.point(lambda value: 255 if value >= floor else 0).getbbox()
    return box or alpha.getbbox() or (0, 0, image.width, image.height)


def _contact_shadow(size: tuple[int, int], box: tuple[int, int, int, int],
                    frame_height: int) -> Image.Image:
    """A soft ellipse under the subject's feet."""
    shadow = Image.new("RGBA", size, (0, 0, 0, 0))
    subject_w = box[2] - box[0]
    width = max(8, int(subject_w * SHADOW_WIDTH))
    height = max(4, int(frame_height * SHADOW_HEIGHT))
    left = box[0] + (subject_w - width) // 2
    top = box[3] - height // 2

    from PIL import ImageDraw

    ImageDraw.Draw(shadow).ellipse(
        [(left, top), (left + width, top + height)],
        fill=(0, 0, 0, int(255 * SHADOW_OPACITY)),
    )
    return shadow.filter(ImageFilter.GaussianBlur(max(2, int(frame_height * SHADOW_BLUR))))


def place(subject_path: Path | str, plate_path: Path | str, out_path: Path | str, *,
          width: int = 1920, height: int = 1080,
          subject_height: float = SUBJECT_HEIGHT, horizon: float = HORIZON,
          offset_x: float = 0.0, shadow: bool = True) -> Placed:
    """Composite a subject onto a plate and return where it landed.

    `offset_x` moves the subject off centre as a fraction of frame width — negative
    left, positive right — which is what makes room for a speech bubble on the other
    side. The reference does exactly that on its gag shots.

    A subject with no alpha is placed anyway rather than refused. Not every asset that
    is worth using arrives pre-cut, and a caller that wanted a matte should have asked
    `layers.matte` for one; silently failing here would be a different kind of wrong.
    """
    subject = Image.open(subject_path).convert("RGBA")
    plate = Image.open(plate_path).convert("RGB")

    # The plate fills the frame by cover, not by stretch. An aspect-distorted background
    # is the single most obvious tell in a composite.
    scale = max(width / plate.width, height / plate.height)
    plate = plate.resize((max(1, round(plate.width * scale)),
                          max(1, round(plate.height * scale))), Image.LANCZOS)
    left = (plate.width - width) // 2
    top = (plate.height - height) // 2
    frame = plate.crop((left, top, left + width, top + height)).convert("RGBA")

    # Scale so the *opaque* region is the requested share of frame height.
    box = opaque_box(subject)
    opaque_h = max(1, box[3] - box[1])
    factor = (height * subject_height) / opaque_h
    subject = subject.resize((max(1, round(subject.width * factor)),
                              max(1, round(subject.height * factor))), Image.LANCZOS)
    box = tuple(round(value * factor) for value in box)

    # Anchor the bottom of the opaque region on the horizon, then centre it — measured
    # on the subject, not on the canvas, so an asset with a lopsided margin still lands
    # in the middle of the shot.
    opaque_w = box[2] - box[0]
    paste_x = round(width / 2 - box[0] - opaque_w / 2 + offset_x * width)
    paste_y = round(height * horizon - box[3])

    placed_box = (paste_x + box[0], paste_y + box[1],
                  paste_x + box[2], paste_y + box[3])
    if shadow:
        frame = Image.alpha_composite(
            frame, _contact_shadow((width, height), placed_box, height))

    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    layer.paste(subject, (paste_x, paste_y), subject)
    frame = Image.alpha_composite(frame, layer)

    target = Path(out_path).with_suffix(".png")
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.convert("RGB").save(target)
    return Placed(path=str(target), width=width, height=height,
                  subject_box=placed_box,
                  layers=[str(plate_path), str(subject_path)])
