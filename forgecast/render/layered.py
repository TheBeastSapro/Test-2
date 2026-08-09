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

## The two moves, and why the second needs the first's geometry

**Drift** translates the whole cut-out on a slow ellipse. **Sway** leans it, pivoting on
its feet, so the crown travels and the contact point does not.

The pivot is the whole of the second move. `rotate` turns an image about its own centre,
and a creature turned about its waist swings its crown one way and its feet the other by
similar small amounts — which reads as almost nothing. Measured on a test subject: 3.09
pixels of crown travel against a 2.09 pixel rounding floor, i.e. nothing. Moving the
pivot down to the contact point — by cancelling the swing back out in the overlay, using
the offset `layers.prepared` reports — takes the same half-degree to 8.22 pixels at the
crown with the feet still planted. So the correction is not a refinement on the lean; it
is the reason there is a lean to see.

## What this deliberately does not do

Both moves are rigid: the cut-out is translated and turned, never deformed. The
reference's Amber moves an *arm* independently of its torso, and nothing here knows
where an arm is — that needs the subject segmented into parts, and it is still open.
Particle overlays (the falling snow at 0:59, the fog at 2:18) are untouched. Stated
rather than elided, because "motion: done" is how a gap stops being visible.

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
               phase: float = 0.0, offset_x: float = 0.0, sway: bool = True,
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

    chain = "[1:v]"
    if sway:
        # The lean. `rotate` turns the image about its own centre, so on its own it
        # swings the creature's feet through an arc — which is a picture being spun, not
        # a creature shifting its weight. The feet are pinned by cancelling that swing
        # back out in the overlay: for a contact point (dx, dy) from the centre, a
        # clockwise turn of A moves it to (dx·cosA minus dy·sinA, dx·sinA + dy·cosA), and
        # subtracting the difference holds it still.
        #
        # Clockwise-positive was measured rather than read: a +0.20 rad turn moved the
        # test subject's crown from x=200.5 to x=233.5, i.e. to the right.
        dx, dy = made["contact"]
        angle = (f"{layers.SWAY:.5f}*sin({2 * math.pi / layers.SWAY_PERIOD:.6f}*t"
                 f"+{phase:.4f})")
        x += f"-(({dx:.2f})*(cos({angle})-1)-({dy:.2f})*sin({angle}))"
        y += f"-(({dx:.2f})*sin({angle})+({dy:.2f})*(cos({angle})-1))"
        # Output size held at the input's, so the overlay's origin does not move under
        # us. The assets this runs on carry a wide transparent margin — a fraction of a
        # degree cannot push a subject into its own edge.
        chain = f"[1:v]rotate=a='{angle}':c=none:ow=iw:oh=ih[sub];[sub]"

    ff.run_ffmpeg(
        ["-loop", "1", "-i", made["plate"],
         "-loop", "1", "-i", made["subject"],
         "-filter_complex",
         f"{chain}null[s];[0:v][s]overlay=x='{x}':y='{y}':format=auto[v]",
         "-map", "[v]", "-t", f"{max(0.1, float(seconds)):.3f}",
         *ff.vcodec(fps, encoder), "-r", str(fps), "-an", str(out)],
        label="layer drift",
    )
    return out
