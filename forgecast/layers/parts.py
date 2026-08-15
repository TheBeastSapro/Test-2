"""Finding a cut-out's limbs, so one can be moved without the rest.

## What this is for

The reference's Amber stretches an arm while its torso holds still — a limb moving
independently, which no transform of the whole picture can imitate. `render/layered.py`
translates and leans the whole cut-out and says plainly that it cannot do this. This is
the missing half: which pixels are an arm.

## Why morphology and not a segmentation model

The obvious reach is a part-segmentation network. It is the wrong tool here twice over.
Those models are trained on people and animals, and these subjects are neither — a
model that finds shoulders and elbows has nothing to say about a black slime with two
claws. And the question is genuinely simpler than semantics: a limb is *a thin thing
sticking out of a thick thing*, which is a shape property the alpha channel already
carries.

So: distance transform for thickness, skeleton for structure, and a branch of the
skeleton that ends in open space is an appendage. Nothing here knows what an arm is,
and the code does not claim to — `Limb` is named for what it measures.

## What decides a limb from a bump

Two ratios, both against the subject's own size so they hold for any asset:

* the branch has to be long enough to read as a limb rather than a lump, and
* the subject has to be markedly thicker somewhere than the branch is, or the whole
  creature is a worm and every end of it is "a limb".

An asset with no limbs is the common case and is not a failure — most cut-outs are a
body. The caller holds it still.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image
from scipy import ndimage
from skimage.morphology import skeletonize

#: Alpha at or above this is the subject, matching `layers.shot.ALPHA_FLOOR` so the
#: silhouette this measures is the silhouette that gets composited.
ALPHA_FLOOR = 40

#: The mask is measured at this size on its long edge. Morphology on a 2250px asset
#: answers the same shape question several seconds slower, and the skeleton of a
#: high-resolution mask is noisier — every wobble in the matte becomes a twig.
WORK_EDGE = 384

#: A spine reaching less than this share of the subject's long edge is a bump, not a
#: limb.
MIN_REACH = 0.15

#: Skeleton below this share of the body's thickest point is a limb's spine rather than
#: the body's. Chosen for being uncritical rather than for being right: across three
#: real cut-outs the answer is the same at 0.35, 0.45 and 0.55 — Seek's Sludgey2 reports
#: its two arms at every one of them.
THIN_SHARE = 0.45

#: How many limbs to return. The reference moves one at a time; returning a dozen
#: invites a caller to animate all of them, which is a creature having a seizure.
MAX_LIMBS = 4


@dataclass
class Limb:
    """One appendage: where it attaches, where it ends, and which pixels are it."""

    #: Both in the *original* image's pixels, so a caller never has to know this was
    #: measured on a downscaled copy.
    anchor: tuple[int, int]
    tip: tuple[int, int]
    #: How far the tip is from the anchor, as a share of the subject's long edge. What
    #: makes one limb worth moving more than another.
    reach: float
    thickness: float
    #: Per-pixel weight over the whole image, 0 outside this limb and rising to 1 at the
    #: tip. This is the thing that makes the warp a warp rather than a cut and paste:
    #: the limb blends into the body instead of shearing away from it.
    weight: np.ndarray = field(repr=False, default_factory=lambda: np.zeros((1, 1)))

    def as_dict(self) -> dict:
        return {"anchor": list(self.anchor), "tip": list(self.tip),
                "reach": round(self.reach, 4), "thickness": round(self.thickness, 4)}


def _mask(image: Image.Image) -> np.ndarray:
    if "A" not in image.getbands():
        return np.ones((image.height, image.width), dtype=bool)
    return np.array(image.convert("RGBA").getchannel("A")) >= ALPHA_FLOOR


def _neighbours(skeleton: np.ndarray) -> np.ndarray:
    """How many skeleton pixels each skeleton pixel touches, itself included."""
    return ndimage.convolve(skeleton.astype(np.uint8), np.ones((3, 3), np.uint8),
                            mode="constant")


def find(image, *, max_limbs: int = MAX_LIMBS) -> list[Limb]:
    """Every appendage on a cut-out, longest reach first.

    Returns `[]` for a subject that is one mass, which is most of them and is not a
    failure. Takes a path or an opened image.
    """
    opened = image if isinstance(image, Image.Image) else Image.open(image)
    opened = opened.convert("RGBA")
    full = _mask(opened)
    if not full.any():
        return []

    height, width = full.shape
    scale = WORK_EDGE / max(height, width)
    if scale < 1.0:
        small = np.array(
            Image.fromarray(full.astype(np.uint8) * 255).resize(
                (max(1, round(width * scale)), max(1, round(height * scale))),
                Image.NEAREST)) > 127
    else:
        scale, small = 1.0, full
    if small.sum() < 32:
        return []

    # Holes fill first: an eye punched through a matte is a hole in the mask, and the
    # skeleton of a shape with holes runs *around* them and reports the loop's ends as
    # limbs.
    small = ndimage.binary_fill_holes(small)
    thickness = ndimage.distance_transform_edt(small)
    body = float(thickness.max())
    if body <= 1:
        return []

    skeleton = skeletonize(small)
    if not skeleton.any():
        return []

    long_edge = max(small.shape)
    # A limb's spine is skeleton that runs through thin flesh. Thresholding the *mask*
    # this way does not work and the picture says why: every silhouette has a thin shell
    # around it, so the body's rim joins both arms into one region. The skeleton has no
    # shell.
    #
    # The first attempt walked each skeleton endpoint back to its first junction, which
    # returns terminal twigs rather than limbs — on Seek's Sludgey2 that found one claw
    # *finger* and missed both arms. An arm ending in a three-fingered claw has its
    # fingers as branches and the arm itself as an internal segment, so the whole thin
    # run has to be taken together.
    spine = skeleton & (thickness < body * THIN_SHARE)
    labels, count = ndimage.label(spine, structure=np.ones((3, 3)))
    if not count:
        return []

    # Which mask pixel belongs to which skeleton pixel, so a spine can claim its flesh.
    # `distance_transform_edt` returns the nearest feature's coordinates when asked,
    # which is exactly this in one pass.
    _, indices = ndimage.distance_transform_edt(~skeleton, return_indices=True)
    owner = labels[indices[0], indices[1]]

    found: list[Limb] = []
    for index in range(1, count + 1):
        points = np.argwhere(labels == index)
        if len(points) < 4:
            continue
        # The anchor is the end nearest the body — the thickest point on the spine —
        # and the tip is whatever is furthest from it. Taking the two extremes of the
        # bounding box instead would put the anchor in mid-air for a bent limb.
        depths = thickness[points[:, 0], points[:, 1]]
        anchor = points[int(np.argmax(depths))]
        spans = np.hypot(points[:, 0] - anchor[0], points[:, 1] - anchor[1])
        tip = points[int(np.argmax(spans))]
        reach = float(spans.max()) / long_edge
        if reach < MIN_REACH:
            continue

        # Flesh owned by this spine, graded from 0 at the anchor to 1 at the tip, so the
        # limb blends into the body rather than shearing off it.
        mine = (owner == index) & small
        rows, columns = np.nonzero(mine)
        weight_small = np.zeros(small.shape, dtype=np.float32)
        away = np.hypot(rows - anchor[0], columns - anchor[1])
        weight_small[rows, columns] = np.clip(away / max(1.0, spans.max()), 0.0, 1.0)
        # Smoothed only where smoothing *adds*. The blur exists to spill a little
        # weight across the ownership boundary so the limb blends into the body instead
        # of shearing off it — but a blur also costs the tip the most, because the tip
        # is a few pixels of silhouette surrounded by empty space. Measured at the tip:
        # 0.26 where it should be 1, which had the end of the limb swinging less than
        # its middle. Taking the larger of the two keeps the blend and the extremity.
        blurred = ndimage.gaussian_filter(weight_small,
                                          sigma=max(1.0, long_edge * 0.015))
        weight_small = np.maximum(weight_small, blurred) * small

        weight = np.array(
            Image.fromarray((np.clip(weight_small, 0, 1) * 255).astype(np.uint8))
            .resize((width, height), Image.BILINEAR)).astype(np.float32) / 255.0
        weight *= full
        found.append(Limb(
            anchor=(int(anchor[1] / scale), int(anchor[0] / scale)),
            tip=(int(tip[1] / scale), int(tip[0] / scale)),
            reach=reach,
            thickness=float(depths.mean()) / body,
            weight=weight,
        ))

    found.sort(key=lambda limb: limb.reach, reverse=True)
    return found[:max_limbs]
