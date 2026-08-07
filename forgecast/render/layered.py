"""A shot where the subject moves and the plate does not.

## Why this is not a Ken Burns push

A push moves every pixel of the frame together, which is a camera move — correct for a
photograph, wrong for a cut-out standing on a background it was never photographed in.
Move the subject alone against a still plate and the eye reads the *creature* moving,
because that is what is happening: two layers at two rates is parallax, and no
whole-frame transform can imitate it.

That is the reference's own construction. `REFERENCE-MSIMPLIFIED` records it plainly —
"Amber's arm at 0:13 moves independently of its torso — a separate layer, not an
image-to-video clip" — and `layers/shot.py` has carried a `subject_box` since it was
written, documented as being for exactly this and used by nothing.

## What this deliberately does not do

It moves the whole cut-out. It does not warp it, rig it, or animate parts of it against
each other, so the reference's stretching arm is still out of reach. Stated rather than
elided, because "motion: done" is how a gap stops being visible.

## Why ffmpeg rather than PIL

Ninety frames of a 2250px subject composited onto 1080p in Python is tens of seconds a
shot, and a run has twenty of them. `overlay` takes expressions in `t`, so the whole
move is one filtergraph and one pass.
"""

from __future__ import annotations

import math
from pathlib import Path

from ..layers import shot as layers
from . import ffmpeg as ff


def drift_clip(subject_path: Path | str, plate_path: Path | str, out_path: Path | str, *,
               seconds: float, width: int = 1920, height: int = 1080, fps: int = 30,
               phase: float = 0.0, offset_x: float = 0.0,
               encoder: str = "") -> Path:
    """Render `seconds` of the subject drifting across a still plate.

    `phase` shifts where in the cycle this shot starts, in radians. Two shots of one
    creature cut together would otherwise begin the identical move at the identical
    speed, which is a loop — and a visible loop is the thing that reads as cheap. Pass
    the shot's index times something irrational-ish and they never line up.
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    work = out.parent / f"{out.stem}_layers"

    made = layers.prepared(subject_path, plate_path, work,
                           width=width, height=height, offset_x=offset_x)

    # Amplitudes in whole pixels, because overlay's x/y are integers and a sub-pixel
    # amplitude rounds to a subject that jumps between two positions rather than moving.
    amp_x = max(1, round(width * layers.DRIFT_X))
    amp_y = max(1, round(height * layers.DRIFT_Y))
    rate = 2 * math.pi / layers.DRIFT_PERIOD
    # Cosine on x and sine on y, so the subject traces an ellipse rather than a diagonal
    # line it retraces — a straight there-and-back is legible as a slider.
    x = f"{made['x']}+{amp_x}*cos({rate:.6f}*t+{phase:.4f})"
    y = f"{made['y']}+{amp_y}*sin({rate:.6f}*t+{phase:.4f})"

    ff.run_ffmpeg(
        ["-loop", "1", "-i", made["plate"],
         "-loop", "1", "-i", made["subject"],
         "-filter_complex", f"[0:v][1:v]overlay=x='{x}':y='{y}':format=auto[v]",
         "-map", "[v]", "-t", f"{max(0.1, float(seconds)):.3f}",
         *ff.vcodec(fps, encoder), "-r", str(fps), "-an", str(out)],
        label="layer drift",
    )
    return out
