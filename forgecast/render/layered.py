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

## The third move, which is not rigid

**Bend** animates the limbs. `layers/parts` finds them from the alpha — a limb is a thin
run of skeleton attached to a thick body, which is a shape question the silhouette
already answers — and `layers/warp` rotates each about its own anchor, weighted per
pixel, so the tip swings and the shoulder does not.

Measured against the same clip rendered without it, at matched frames with the drift and
the lean switched off: the arms differ by four to nine thousand pixels and the body by
one. The few hundred that do change on the body sit at the shoulder, which is the blend
doing its job rather than a leak.

It costs a frame sequence instead of a looped still — roughly five seconds for a
five-second clip — so it is a flag, and a subject with no limbs skips it entirely rather
than writing a hundred identical frames.

## What this still does not do

Nothing here knows what an arm *is*. It knows that something thin sticks out of
something thick, which is enough to move it and is not the same claim — a subject whose
limbs are drawn folded against its body has none by this definition. Particle overlays
live in `render/particles` and are asked for rather than found, for the reason recorded
there. Stated rather than elided, because "motion: done" is how a gap stops being
visible.

## Why ffmpeg rather than PIL

Ninety frames of a 2250px subject composited onto 1080p in Python is tens of seconds a
shot, and a run has twenty of them. `overlay` takes expressions in `t`, so the whole
move is one filtergraph and one pass.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image

from ..layers import shot as layers
from . import ffmpeg as ff


def drift_clip(subject_path: Path | str, plate_path: Path | str, out_path: Path | str, *,
               seconds: float, width: int = 1920, height: int = 1080, fps: int = 30,
               phase: float = 0.0, offset_x: float = 0.0, sway: bool = True,
               bend: bool = True, encoder: str = "") -> Path:
    """Render `seconds` of the subject drifting across a still plate.

    `phase` shifts where in the cycle this shot starts, in radians. Two shots of one
    creature cut together would otherwise begin the identical move at the identical
    speed, which is a loop — and a visible loop is the thing that reads as cheap. Pass
    the shot's index times something irrational-ish and they never line up.

    `bend` animates the subject's limbs where it has any. It costs a frame sequence
    instead of one looped still, so it is worth having a way to turn off.
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    work = out.parent / f"{out.stem}_layers"

    made = layers.prepared(subject_path, plate_path, work,
                           width=width, height=height, offset_x=offset_x)

    # The limbs, if this creature has any. Measured on the *prepared* subject, which is
    # already at its final pixel size — finding them on a 2250px source and scaling the
    # weights down would blur the boundary the warp depends on.
    subject_input = ["-loop", "1", "-i", made["subject"]]
    if bend:
        frames = _bent_frames(made["subject"], work / "bend", seconds=seconds, fps=fps,
                              phase=phase)
        if frames:
            # A sequence rather than a looped still. `-framerate` is the input rate and
            # has to be set before `-i`, or ffmpeg reads the images at 25fps whatever
            # the output rate is and the whole motion runs at the wrong speed.
            subject_input = ["-framerate", str(fps), "-i", str(frames)]

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
         *subject_input,
         "-filter_complex",
         f"{chain}null[s];[0:v][s]overlay=x='{x}':y='{y}':format=auto[v]",
         "-map", "[v]", "-t", f"{max(0.1, float(seconds)):.3f}",
         *ff.vcodec(fps, encoder), "-r", str(fps), "-an", str(out)],
        label="layer drift",
    )
    return out


def _bent_frames(subject_path, out_dir, *, seconds: float, fps: int,
                 phase: float) -> Path | None:
    """A PNG sequence of the subject with its limbs animated, or `None`.

    `None` for a subject with no limbs, which is most of them: a body with no
    appendages has nothing to bend, and writing a hundred identical frames to say so
    would cost a second and change no pixel. The caller falls back to the looped still.

    Written as PNGs rather than encoded to an intermediate video because the subject
    carries alpha, and the codecs that keep an alpha channel through an intermediate are
    the ones that either lose it silently or are not built into every ffmpeg.
    """
    from ..layers import parts, warp

    subject = Image.open(subject_path).convert("RGBA")
    limbs = parts.find(subject)
    if not limbs:
        return None

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("*.png"):
        stale.unlink()

    # One past the end, so the last frame of the clip has an image to be rather than
    # ffmpeg holding the second-to-last.
    count = max(2, math.ceil(max(0.1, float(seconds)) * fps) + 1)
    for index in range(count):
        moment = index / float(fps)
        frame = warp.bend(subject, limbs, warp.swing(limbs, moment, phase=phase))
        frame.save(out / f"f{index:05d}.png")
    return out / "f%05d.png"
