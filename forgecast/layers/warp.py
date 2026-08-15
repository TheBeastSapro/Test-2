"""Bending a limb without moving the rest of the creature.

`parts.find` says which pixels are an arm and where it attaches. This turns that into
pixels: each limb rotates about its own anchor by a small angle, scaled per pixel by the
limb's weight, so the flesh at the tip swings and the flesh at the shoulder does not
move at all.

## Why a weighted rotation rather than a mesh

A mesh warp with pins is the general tool and it is more than this needs. The weight
field out of `parts` is already a per-pixel "how much of this limb is this", which is
exactly the skinning weight a rigged mesh would compute — so the deformation is one
rotation per limb, evaluated per pixel, and there is no mesh to build, tessellate or
keep from folding.

## Why the map is inverse and why that is allowed to be approximate

Resampling reads: for each destination pixel, where did it come from. Inverting a
spatially varying rotation exactly is a root-find per pixel. Evaluating the weight at
the destination instead is the standard approximation, and its error goes as the
gradient of the weight times the angle — at half a degree, across a weight that is
smoothed over a fiftieth of the frame, it is far under a pixel. The angles here are
small by design, because a creature whose arm swings visibly far stops reading as the
canonical artwork and starts reading as a puppet.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

#: How far a limb swings at its tip, in radians, at full weight. About four degrees:
#: enough that the arm is visibly alive next to a still body, small enough that the
#: silhouette the audience knows is still the silhouette on screen.
LIMB_SWING = 0.07

#: Seconds for one full swing. Slow, and prime-ish against the drift and sway periods in
#: `layers.shot` so the three motions never come back into phase inside a shot.
LIMB_PERIOD = 5.0


def _grid(shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    rows, columns = shape
    ys, xs = np.mgrid[0:rows, 0:columns]
    return xs.astype(np.float32), ys.astype(np.float32)


def bend(image: Image.Image, limbs, angles) -> Image.Image:
    """One frame: every limb rotated about its anchor by its own angle.

    `angles` is one angle in radians per limb, so a caller can drive them out of phase.
    Returns the image unchanged when there is nothing to bend, which is the common case.
    """
    if not limbs or not len(angles):
        return image

    frame = image.convert("RGBA")
    source = np.array(frame)
    height, width = source.shape[:2]
    xs, ys = _grid((height, width))

    # Where each destination pixel is read from. Displacements are summed rather than
    # composed: the weight fields are all but disjoint, so at any pixel one term is the
    # rotation and the others are zero.
    map_x, map_y = xs.copy(), ys.copy()
    for limb, angle in zip(limbs, angles, strict=False):
        if not angle:
            continue
        weight = limb.weight
        if weight.shape != (height, width):
            weight = np.array(
                Image.fromarray((np.clip(weight, 0, 1) * 255).astype(np.uint8))
                .resize((width, height), Image.BILINEAR)).astype(np.float32) / 255.0
        # Inverse rotation, so this reads from where the pixel came from.
        theta = (-float(angle)) * weight
        cos, sin = np.cos(theta), np.sin(theta)
        ax, ay = float(limb.anchor[0]), float(limb.anchor[1])
        dx, dy = xs - ax, ys - ay
        map_x += (ax + cos * dx - sin * dy) - xs
        map_y += (ay + sin * dx + cos * dy) - ys

    import cv2

    bent = cv2.remap(source, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    return Image.fromarray(bent, mode="RGBA")


def swing(limbs, moment: float, *, phase: float = 0.0,
          amplitude: float = LIMB_SWING, period: float = LIMB_PERIOD) -> list[float]:
    """The angle each limb is at, at one moment.

    Every limb gets its own phase offset so they do not swing together — two arms moving
    in lockstep is a semaphore, not a creature. The offset is derived from the limb's
    index rather than randomised, so the same shot re-renders identically.
    """
    step = 2.0 * np.pi / max(0.1, period)
    return [amplitude * float(np.sin(step * moment + phase + index * 1.9))
            for index in range(len(limbs))]
