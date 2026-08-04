"""Cutting the subject out of a still, so there is something to put things behind.

## Why this is the highest-leverage visual thing in the app

Not because a cutout is impressive. Because of what it unlocks. A still is one flat
image and nothing can be *behind* anything in it. The moment the subject is on its own
layer with an alpha channel, everything behind it becomes addressable: a title the
subject occludes, a background that moves at a different rate, a shadow that sits
correctly, a glow that wraps.

That is what reads as "edited" rather than "generated". A generated still that slowly
zooms is a photograph with a camera move. The same still with its subject lifted onto a
layer is a composite, and the difference is visible to somebody who could not tell you
why.

The specific move worth having first is **text behind the subject** — a title that the
subject's shoulder passes in front of. It is mechanically trivial once a matte exists
and impossible without one, and it is currently the single most recognisable mark of a
skilled editor on the platforms this app publishes to.

## A bad matte is worse than no matte

This is the load-bearing judgement in this file. Hair, motion blur and semi-transparent
edges are where automatic segmentation fails, and it fails by leaving a fringe — a halo
of background pixels around the subject, or a hard jagged edge where a soft one belongs.
The eye catches a fringe instantly, and it reads as cheap in a way that a plain
uncomposited still never does.

So every matte is measured before it is used and `usable` can be False. A refused matte
falls back to the plain still, which is the same degradation the renderer already does
when an animation fails and it uses the plate. Producing a worse video than the one that
would have been produced without the feature is the only outcome not worth having.

## Why stills and not video

Per-frame matting is slow and, worse, it flickers: each frame is segmented
independently, so the boundary shifts by a pixel or two every frame and the subject
appears to shimmer. Fixing that needs temporal stabilisation, which is a different and
much larger problem. Stills are where this is clean, cheap and correct — and stills are
most of what this app renders anyway, because a Ken Burns move on an image is about ten
times cheaper than a generated clip.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("forgecast.layers.matte")

# `u2net` rather than `isnet-general-use` or a human-specific model. It is the
# general-purpose one: this app's stills are objects, places and machines at least as
# often as they are people, and a human-segmentation model returns an empty mask for a
# photograph of a ship — which is a silent failure that looks like a broken image.
DEFAULT_MODEL = "u2net"

# A subject occupying less than this is a failed segmentation, not a small subject.
# Below about 2% of the frame there is nothing to composite against and the "subject" is
# usually a speck of noise the model latched onto.
MIN_COVERAGE = 0.02

# And above this, the model has selected the background as well as the subject — which
# produces a cutout indistinguishable from the original and a composite with nothing
# visible behind it.
MAX_COVERAGE = 0.92

# The proportion of the matte that is neither fully opaque nor fully transparent. This
# is the number that catches the failure that matters: a real subject boundary is
# anti-aliased and carries a band of partial alpha, and a matte with almost none of it
# has been cut with a hard threshold. That is the jagged fringe the eye catches.
MIN_SOFT_EDGE = 0.0008
# Too much of it means the model was unsure everywhere — a haze rather than a subject.
MAX_SOFT_EDGE = 0.30


@dataclass
class Matte:
    """One subject cut out of a still, and whether it is good enough to use."""

    source: str
    path: str
    width: int
    height: int
    # Fraction of the frame the subject occupies.
    coverage: float
    # Fraction of the frame that is a partial-alpha boundary.
    soft_edge: float
    usable: bool
    # Why it was refused, when it was. Empty on a good matte. Shown to the operator, so
    # it says what happened rather than naming a threshold.
    refused: str = ""

    def as_dict(self) -> dict:
        return {"source": self.source, "path": self.path,
                "width": self.width, "height": self.height,
                "coverage": self.coverage, "soft_edge": self.soft_edge,
                "usable": self.usable, "refused": self.refused}


def available() -> tuple[bool, str]:
    try:
        import rembg  # noqa: F401
    except ImportError:
        return False, "subject cutouts need the video editing tools"
    return True, ""


@lru_cache(maxsize=2)
def _session(model_name: str):
    """One session per model, reused.

    Building it loads a 176 MB network. Doing that per shot would add several seconds to
    every still in a video of up to eighty of them, which is the difference between a
    feature somebody leaves on and one they turn off.
    """
    from rembg import new_session

    return new_session(model_name)


def _measure(alpha) -> tuple[float, float]:
    """Coverage and soft-edge fraction, from the alpha channel."""

    total = alpha.size or 1
    opaque = int((alpha > 250).sum())
    soft = int(((alpha >= 5) & (alpha <= 250)).sum())
    return round(opaque / total, 4), round(soft / total, 4)


def _verdict(coverage: float, soft_edge: float) -> str:
    """Empty when the matte is usable, otherwise the sentence explaining the refusal."""
    if coverage < MIN_COVERAGE:
        return ("almost nothing was selected — there is no clear subject in this "
                "image to cut out")
    if coverage > MAX_COVERAGE:
        return ("nearly the whole frame was selected, so there is no background to "
                "put anything behind")
    if soft_edge < MIN_SOFT_EDGE:
        return ("the edge came out hard rather than anti-aliased, which shows as a "
                "jagged fringe around the subject")
    if soft_edge > MAX_SOFT_EDGE:
        return ("the boundary is soft everywhere — the model could not find a definite "
                "edge, and the cutout would look like a haze")
    return ""


def cut(image_path: Path | str, out_path: Path | str, *,
        model_name: str = DEFAULT_MODEL) -> Matte:
    """Cut the subject out of one still, and say whether the result is good enough.

    Always writes the file, even when the matte is refused. The caller decides what to
    do with `usable`, and having the rejected matte on disk is what makes a refusal
    reviewable instead of a claim.
    """
    ok, why = available()
    if not ok:
        raise RuntimeError(why)

    import numpy as np
    from PIL import Image
    from rembg import remove

    source = Path(image_path)
    target = Path(out_path).with_suffix(".png")     # alpha needs PNG, whatever was asked
    target.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source) as opened:
        original = opened.convert("RGB")
    cutout = remove(original, session=_session(model_name))
    if cutout.mode != "RGBA":                                         # pragma: no cover
        cutout = cutout.convert("RGBA")
    cutout.save(target)

    coverage, soft_edge = _measure(np.array(cutout)[:, :, 3])
    refused = _verdict(coverage, soft_edge)
    if refused:
        log.info("matte refused for %s: %s", source.name, refused)

    return Matte(source=str(source), path=str(target),
                 width=cutout.width, height=cutout.height,
                 coverage=coverage, soft_edge=soft_edge,
                 usable=not refused, refused=refused)
