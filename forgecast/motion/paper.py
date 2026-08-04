"""Paper-collage animation: the cut-out, stepped, locked-camera style.

## What this style is

A base of aged paper. Torn scraps and maps laid over it. Subjects as high-contrast
halftone cut-outs with ragged edges. Typewritten strips, stamps, and red string running
pin to pin. Nothing moves smoothly and the camera never moves at all.

It is the look of a physical desk being assembled under a locked-off camera, and the
reason it reads as made rather than generated is almost entirely mechanical — three
properties, none of them artistic:

* **Stepped motion.** Every element moves, holds for two or three frames, moves again.
  Smooth interpolation is what makes motion graphics look computed; removing it is what
  makes them look handled. See `stepped`.
* **A locked camera.** No push-in, no drift, no parallax. Only the paper moves.
* **One screen.** Every cut-out in the video carries the identical halftone dot pitch,
  because they were all screened by the same function. That is what makes a collage read
  as one artifact instead of a pile of separate images.

## Why none of this is generated video

This is the one style in the app where image-to-video is the wrong tool rather than an
expensive one. Veo, Kling and the rest produce smooth motion, drifting cameras and
photoreal texture, and this style deliberately removes all three — so the money buys
output that then has to be fought. A paper-collage video costs nothing to generate: the
source art can come from any still image provider including a free one, and everything
below is ffmpeg arithmetic.

## Why the textures are built rather than shipped or prompted

Neither of the obvious answers survives contact.

*Prompting for them* fails on determinism, which is the whole style. Ask an image model
for "aged newsprint" eighty times and you get eighty different papers, and the collage
stops looking like one desk. It also fails in practice — asked for a flat paper texture,
a current model returns a photograph of paper in a wooden picture frame, because "texture"
in its training data is mostly product photography.

*Shipping them* means binary assets in the repository and in every package, a licence
question for each one, and a fixed number of papers that viewers eventually recognise.

Building them from ffmpeg primitives costs no bytes, is reproducible from a seed, and
gives an unlimited number of papers that are all the same paper. The recipe is two
octaves of noise generated small and scaled up — low-frequency variation has to be
*generated* at low frequency, because blurring high-frequency noise removes variation
rather than enlarging it, which is what the first attempt at this did.
"""

from __future__ import annotations

import logging
import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("forgecast.motion.paper")

# Frames an element rests on before it moves again. Two is the sharpest and reads as
# stop-motion; three is calmer and is what most of this style uses. One is smooth
# animation with extra steps, which is the thing being avoided.
DEFAULT_HOLD_FRAMES = 3

# Halftone cell size in pixels at 1080p, and the screen angle. 45 degrees is what print
# uses for a single-colour screen because it is the angle at which the human eye is least
# able to resolve the grid — the dots read as tone rather than as a pattern.
DEFAULT_CELL = 8
SCREEN_ANGLE_DEGREES = 45.0

# How far a dot may grow within its cell. Above about 0.72 the dots of neighbouring cells
# merge in the shadows and the screen fills to solid black; below about 0.5 the darkest
# areas never close up and the cut-out looks washed out.
DOT_GAIN = 0.62

_FFMPEG_TIMEOUT = 180.0


# --------------------------------------------------------------------------- easing


def stepped(start: float, end: float, frames: int, *,
            hold: int = DEFAULT_HOLD_FRAMES, ease: str = "out") -> list[float]:
    """One value per frame, moving in visible steps rather than continuously.

    The defining property of the style, and the reason `motion/presets.py` could not
    produce it: every preset there interpolates smoothly, which is correct for broadcast
    motion graphics and is exactly the quality this style exists to remove.

    Easing is applied to the *stepped* progress rather than to the frame number. Applying
    it the other way round produces steps of uneven duration — the element hesitates
    longer at the start than at the end — which reads as dropped frames rather than as a
    choice. This way every step lasts the same number of frames and the distance covered
    per step shrinks, which is what a hand-animated ease-out actually looks like.
    """
    count = max(1, int(frames))
    rest = max(1, int(hold))
    if count == 1:
        return [float(end)]

    steps = max(1, math.ceil(count / rest))
    values: list[float] = []
    for index in range(count):
        # Which step this frame belongs to, and where that step sits in the move.
        position = min(index // rest, steps - 1)
        progress = position / (steps - 1) if steps > 1 else 1.0
        values.append(float(start) + (float(end) - float(start)) * _ease(progress, ease))
    return values


def _ease(progress: float, kind: str) -> float:
    """Named curves, deliberately few.

    Only shapes that survive being stepped. A bounce or an elastic curve quantised to
    three-frame holds reads as a stutter, not as a bounce — the overshoot lands on one
    step and is gone before the eye registers it as intentional.
    """
    t = min(1.0, max(0.0, float(progress)))
    if kind == "linear":
        return t
    if kind == "in":
        return t * t
    if kind == "in_out":
        return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2
    return 1 - (1 - t) ** 2  # "out", the default


def build_on(count: int, seconds: float, *, fps: int = 30,
             settle: float = 0.30) -> list[tuple[float, float]]:
    """When each layer arrives, back to front, with time left over to hold.

    The assembly rhythm this style uses: elements stagger in over the first stretch,
    then everything stops and only micro-animation continues. The hold is not dead time —
    it is when the viewer reads the frame, and a build that runs to the last frame gives
    them nowhere to do that.

    `settle` is the share of the shot reserved for that hold. Returned as (start, duration)
    per layer in seconds, in the order they should be composited: background first.
    """
    total = max(0.1, float(seconds))
    layers = max(1, int(count))
    building = total * (1.0 - min(0.8, max(0.0, settle)))
    # Every layer gets the same move duration; only their starts stagger. Layers whose
    # durations also varied made the build look like it was slowing down as it went,
    # which fights the settle that follows it.
    move = max(1.0 / fps, building / (layers + 1))
    # Divided by the gaps between layers, not by the layers. Dividing by the count leaves
    # one gap's worth of slack at the end, so the last element lands early and the settle
    # runs longer than it was asked to — which on a ten-second shot was four seconds of
    # hold where three were wanted.
    gap = (building - move) / (layers - 1) if layers > 1 else 0.0
    return [(round(index * gap, 4), round(move, 4)) for index in range(layers)]


# --------------------------------------------------------------------------- filters
#
# Returned as filter strings rather than run here, so a caller can chain them into one
# encode instead of paying for a file round-trip per effect. `render_*` below is the
# convenience path for when one effect is all that is wanted.


def halftone_filter(*, cell: int = DEFAULT_CELL,
                    angle_degrees: float = SCREEN_ANGLE_DEGREES,
                    gain: float = DOT_GAIN) -> str:
    """A real amplitude-modulated print screen: dot radius grows with local darkness.

    Not a dither and not a threshold. Both of those produce a pattern whose *density*
    varies, which is frequency modulation and looks like a laser printer. Print halftone
    varies the dot's *size* on a fixed grid, and the difference is visible immediately —
    it is the difference between a newspaper photograph and a fax.

    The grid is rotated before the cell arithmetic rather than after, because rotating
    the finished screen resamples it and softens exactly the hard dot edges that make it
    read as ink.
    """
    size = max(2, int(cell))
    radians = math.radians(float(angle_degrees))
    cos, sin = round(math.cos(radians), 6), round(math.sin(radians), 6)
    reach = max(0.1, min(0.9, float(gain))) * size

    return (
        "format=gray,"
        "geq=lum='"
        # Rotate the sampling grid, not the image.
        f"st(0, X*{cos} + Y*{sin});"
        f"st(1, Y*{cos} - X*{sin});"
        # Offset from this cell's centre, on the rotated grid.
        f"st(2, ld(0) - {size}*floor(ld(0)/{size}) - {size}/2);"
        f"st(3, ld(1) - {size}*floor(ld(1)/{size}) - {size}/2);"
        "st(4, hypot(ld(2), ld(3)));"
        # Darkness here decides how far the dot reaches.
        "st(5, (255 - p(X,Y))/255);"
        f"if(lt(ld(4), ld(5)*{reach}), 0, 255)"
        "'"
    )


@dataclass(frozen=True)
class PaperTone:
    """The colour of one kind of paper, as channel multipliers on white.

    Multipliers rather than a hex colour because the texture is built in greyscale and
    tinted last. Generating it in colour desaturates it — `noise` operates per channel and
    pushes everything toward grey — which is why an early version of this came out olive
    however warm the base colour was.
    """

    key: str
    label: str
    red: float
    green: float
    blue: float
    #: Where the mid-tones sit. Lower is a darker, more handled sheet.
    floor: float = 0.58


TONES: dict[str, PaperTone] = {
    "newsprint": PaperTone("newsprint", "Aged newsprint", 0.870, 0.800, 0.625),
    "manila": PaperTone("manila", "Manila folder", 0.855, 0.735, 0.520, floor=0.52),
    "ledger": PaperTone("ledger", "Ledger paper", 0.900, 0.880, 0.790, floor=0.66),
    "kraft": PaperTone("kraft", "Kraft board", 0.680, 0.540, 0.380, floor=0.46),
    "bone": PaperTone("bone", "Bone white", 0.945, 0.930, 0.890, floor=0.72),
}

DEFAULT_TONE = "newsprint"


def paper_inputs(width: int, height: int, seed: int) -> list[str]:
    """The lavfi sources a paper texture needs, as ffmpeg arguments.

    Two noise octaves generated *small* and scaled up. This is the part that has to be
    done this way: low-frequency variation must be generated at low frequency. Blurring
    high-frequency noise does not enlarge its features, it removes them, and the result
    is a flat sheet with a slight haze — which is what the first attempt produced.
    """
    return [
        "-f", "lavfi", "-i", f"color=c=white:s={int(width)}x{int(height)}",
        # ~7x4: the blotching that reads as damp and age.
        "-f", "lavfi", "-i", "color=c=gray:s=7x4",
        # ~26x15: the middle scale, so the sheet is not two tones.
        "-f", "lavfi", "-i", "color=c=gray:s=26x15",
    ]


def paper_filtergraph(width: int, height: int, *, seed: int = 7,
                      tone: str = DEFAULT_TONE, grain: float = 11.0,
                      vignette: bool = True) -> str:
    """The filter_complex that turns those three sources into a sheet of paper."""
    swatch = TONES.get(tone) or TONES[DEFAULT_TONE]
    big_seed = int(seed) % 10000
    mid_seed = (int(seed) * 7 + 41) % 10000

    # Darkening at the edges, not brightening. `mode=backward` lightens the corners,
    # which is what a backlit screen does and the opposite of what handling does to
    # paper — the edges are where a sheet is held, folded and foxed. A wide angle keeps
    # it subtle; a sheet with an obvious vignette reads as a photograph of paper.
    vignette_step = "vignette=angle=PI/9," if vignette else ""
    return (
        f"[1:v]noise=alls=80:allf=t+u:all_seed={big_seed},format=gray,"
        f"scale={int(width)}:{int(height)}:flags=bicubic,"
        "format=yuva420p,colorchannelmixer=aa=0.30[big];"
        f"[2:v]noise=alls=60:allf=t+u:all_seed={mid_seed},format=gray,"
        f"scale={int(width)}:{int(height)}:flags=bicubic,"
        "format=yuva420p,colorchannelmixer=aa=0.13[mid];"
        "[0:v][big]overlay[a];[a][mid]overlay,"
        "format=gray,"
        f"curves=all='0/{swatch.floor:.2f} 0.5/{(swatch.floor + 1.0) / 2:.2f} 1/1.0',"
        "format=rgb24,"
        f"colorchannelmixer=rr={swatch.red}:gg={swatch.green}:bb={swatch.blue},"
        f"{vignette_step}"
        # Grain last. Applied before the curve above, its amplitude is halved by the
        # range compression and the sheet comes out with no fibre at all.
        f"noise=alls={max(0, int(grain))}:allf=t+u:all_seed={(big_seed + 13) % 10000}"
    )


def torn_edge_filter(*, seed: int = 5, bite: int = 7) -> str:
    """Ragged an already-extracted alpha channel, so a cut-out looks torn rather than cut.

    The single cheapest thing that separates this style from a clean composite. A matte
    from background removal has a smooth, slightly soft edge — correct for a photographic
    composite and wrong here, where every element is supposed to have been pulled apart by
    hand.

    Takes and returns a greyscale alpha rather than an RGBA image, because the colour
    channels must not go through this: displacing them as well fringes the edge with
    whatever was behind the subject in the source.
    """
    amount = max(1, int(bite))
    return (
        # Displace the edge by a noise field, then re-threshold. Blurring alone rounds
        # the edge; blurring and re-thresholding makes it wander, which is what torn is.
        f"noise=alls={amount * 9}:allf=t+u:all_seed={int(seed) % 10000},"
        f"boxblur=luma_radius={amount}:luma_power=1,"
        "curves=all='0/0 0.46/0 0.54/1 1/1'"
    )


def cutout_filtergraph(*, cell: int = DEFAULT_CELL, tear: int = 7,
                       seed: int = 5, gain: float = DOT_GAIN) -> str:
    """Screen a cut-out's colour and tear its alpha, in one pass.

    The two halves have to be separated and put back together, because the halftone
    starts with `format=gray` and greyscale has no alpha — screening an RGBA image
    directly returns a rectangle, which is exactly what the first render of this style
    produced: a portrait with a border, sitting on the paper like a photograph rather than
    like something torn out of a newspaper.
    """
    return (
        "[0:v]format=yuva420p,split=2[colour][matte];"
        f"[matte]alphaextract,{torn_edge_filter(seed=seed, bite=tear)}[torn];"
        f"[colour]{halftone_filter(cell=cell, gain=gain)},format=gray,format=yuva420p"
        "[screened];"
        "[screened][torn]alphamerge[out]"
    )


def render_cutout(src: Path, out_path: Path, *, cell: int = DEFAULT_CELL,
                  tear: int = 7, seed: int = 5) -> Path:
    """One subject, screened and torn, with its background already removed.

    Expects an RGBA source — `layers.matte.cut` is what produces one. Passing a JPEG
    here screens it and tears an alpha channel that is fully opaque, which produces a
    torn-edged rectangle rather than a cut-out and is worth knowing rather than guessing
    at from the output.
    """
    out_path = Path(out_path).with_suffix(".png")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
         "-filter_complex", cutout_filtergraph(cell=cell, tear=tear, seed=seed),
         "-map", "[out]", "-frames:v", "1", str(out_path)],
        "cutting out and screening a subject",
    )
    return out_path


# --------------------------------------------------------------------------- rendering


@dataclass
class Sheet:
    """One rendered paper background."""

    path: Path
    width: int
    height: int
    tone: str
    seed: int

    def as_dict(self) -> dict:
        return {"path": str(self.path), "width": self.width, "height": self.height,
                "tone": self.tone, "seed": self.seed}


def _run(args: list[str], what: str) -> None:
    try:
        done = subprocess.run(args, capture_output=True, text=True,
                              timeout=_FFMPEG_TIMEOUT, check=False)
    except FileNotFoundError as exc:  # pragma: no cover - ffmpeg is a hard dependency
        raise RuntimeError("ffmpeg is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{what} timed out") from exc
    if done.returncode != 0:
        # The last line, not the whole log: ffmpeg's stderr is mostly a banner and the
        # useful sentence is at the end.
        tail = (done.stderr or "").strip().splitlines()
        raise RuntimeError(f"{what} failed: {tail[-1] if tail else 'no output'}")


def render_paper(out_path: Path, *, width: int = 1920, height: int = 1080,
                 seed: int = 7, tone: str = DEFAULT_TONE, grain: float = 11.0,
                 vignette: bool = True) -> Sheet:
    """Build a sheet of paper. Same seed, same paper, on any machine."""
    out_path = Path(out_path).with_suffix(".png")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         *paper_inputs(width, height, seed),
         "-filter_complex", paper_filtergraph(width, height, seed=seed, tone=tone,
                                              grain=grain, vignette=vignette),
         "-frames:v", "1", str(out_path)],
        "building a paper texture",
    )
    return Sheet(path=out_path, width=int(width), height=int(height),
                 tone=tone, seed=int(seed))


def render_halftone(src: Path, out_path: Path, *, cell: int = DEFAULT_CELL,
                    angle_degrees: float = SCREEN_ANGLE_DEGREES,
                    gain: float = DOT_GAIN) -> Path:
    """Screen one image. Every cut-out in a video should go through this once."""
    out_path = Path(out_path).with_suffix(".png")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
         "-vf", halftone_filter(cell=cell, angle_degrees=angle_degrees, gain=gain) +
                ",format=yuv420p",
         "-frames:v", "1", str(out_path)],
        "screening an image",
    )
    return out_path


# --------------------------------------------------------------------------- the style


@dataclass(frozen=True)
class Layer:
    """One thing on the desk, and how it arrives."""

    key: str
    label: str
    #: Compositing order. Lower is further back.
    depth: int
    #: How it enters. Only moves a hand could make — nothing rotates in 3D.
    entry: str
    when_to_use: str
    #: Whether it keeps moving during the settle. Most things do not.
    micro: bool = False


STACK: tuple[Layer, ...] = (
    Layer("base", "Paper base", depth=0, entry="hold",
          when_to_use="The sheet everything else sits on. It never animates — a moving "
                      "background under stepped foreground elements reads as a video "
                      "playing behind paper, which breaks the illusion in one shot."),
    Layer("scraps", "Torn scraps and maps", depth=10, entry="drop",
          when_to_use="The second layer of paper, laid at slight angles. Carries the "
                      "subject matter without having to be legible — a map of the right "
                      "region does more than a caption naming it."),
    Layer("subject", "Halftone cut-out", depth=20, entry="drop",
          when_to_use="The thing the beat is about, screened and torn. One per beat. Two "
                      "cut-outs competing for the same frame is the most common way this "
                      "style stops reading."),
    Layer("strips", "Typewritten strips", depth=30, entry="slide",
          when_to_use="The words. Short — a strip is a phrase, not a sentence — and set "
                      "as though typed and cut out, which is why they arrive sliding "
                      "rather than fading."),
    Layer("stamp", "Stamp or annotation", depth=40, entry="stamp", micro=True,
          when_to_use="Emphasis, once or twice in a video. It lands hard and settles, "
                      "and it is the one element that may keep breathing during the hold."),
    Layer("string", "Red string", depth=50, entry="draw", micro=True,
          when_to_use="Connection between two things already on screen. It draws pin to "
                      "pin rather than appearing, because the drawing is the argument — "
                      "and it cannot be the first thing in a shot, since there is nothing "
                      "yet for it to connect."),
)

BY_KEY: dict[str, Layer] = {layer.key: layer for layer in STACK}


@dataclass
class PaperShot:
    """One beat, planned as a stack rather than as a clip."""

    seconds: float
    layers: list[str] = field(default_factory=list)
    tone: str = DEFAULT_TONE
    seed: int = 7
    hold_frames: int = DEFAULT_HOLD_FRAMES

    def timeline(self, *, fps: int = 30) -> list[dict]:
        """Every layer with its arrival, in compositing order.

        The camera is absent from this on purpose. There is nowhere to put one, which is
        the point — `prompts/moves.py` has twelve camera moves and this style uses none
        of them, so a shot planned here cannot accidentally acquire a push-in.
        """
        ordered = [BY_KEY[key] for key in self.layers if key in BY_KEY]
        ordered.sort(key=lambda layer: layer.depth)

        # Anything that holds is present from the first frame and is not part of the
        # build. The paper base is the case that matters: staggering it in means the shot
        # opens on nothing, and giving it a share of the build shortens every other
        # layer's move for an element that never moves.
        arriving = [layer for layer in ordered if layer.entry != "hold"]
        schedule = dict(zip((layer.key for layer in arriving),
                            build_on(len(arriving), self.seconds, fps=fps), strict=False))

        rows: list[dict] = []
        for layer in ordered:
            start, duration = schedule.get(layer.key, (0.0, float(self.seconds)))
            rows.append({
                "key": layer.key, "label": layer.label, "depth": layer.depth,
                "entry": layer.entry, "micro": layer.micro,
                "start": start, "duration": duration,
                "frames": max(1, round(duration * fps)),
                "hold_frames": self.hold_frames,
            })
        return rows


# --------------------------------------------------------------------------- compositing
#
# The stack is rendered with ffmpeg rather than with Remotion. Remotion is the better tool
# for this style and is where it should end up — real path trimming, real masks, real
# typography — but it is an optional install, and a style that only renders when an
# optional 350MB toolchain is present is a style most installs cannot use. So the layers
# composite here, in the dependency the app already requires, and the Remotion backend
# becomes the upgrade rather than the entry fee.
#
# Stepped motion survives the translation because ffmpeg's overlay expressions can read
# `t`. Quantising it is the whole trick: `floor` the elapsed frames into holds, and the
# element moves in the same visible steps `stepped()` produces in Python.


def _stepped_expression(start: float, duration: float, *, fps: int, hold: int,
                        ease: str = "out") -> str:
    """Progress from 0 to 1 in visible steps, as an ffmpeg expression in `t`.

    The same arithmetic as `stepped`, written for a filtergraph. It is duplicated rather
    than shared because there is nothing to share — one produces a list of numbers and the
    other produces a string of ffmpeg syntax — but the two are pinned to each other by
    test, because a Python preview that steps differently from the render is worse than
    no preview.
    """
    frames = max(1, round(max(0.001, duration) * fps))
    rest = max(1, int(hold))
    steps = max(1, math.ceil(frames / rest))
    begin = round(float(start), 4)

    if steps == 1:
        return "1"

    # Elapsed frames since this layer started, floored into holds, as a fraction of the
    # total number of steps. Clipped at both ends so the expression is safe before the
    # layer starts and after it lands.
    progress = (f"clip(floor(max(0\\,(t-{begin}))*{fps}/{rest})/{steps - 1}\\,0\\,1)")

    if ease == "linear":
        return progress
    if ease == "in":
        return f"pow({progress}\\,2)"
    return f"(1-pow(1-{progress}\\,2))"  # "out", the default


#: Where each entry comes from, as a fraction of the frame. The moves are short on
#: purpose — a long travel reads as a slide transition, and this is meant to read as
#: something being *placed*, which is a movement of a few centimetres.
_ENTRY_OFFSETS: dict[str, tuple[float, float]] = {
    "drop": (0.0, -0.14),     # from above, the way a hand lays paper down
    "slide": (-0.16, 0.0),    # in from the left, the way a cut strip is pushed in
    "stamp": (0.0, -0.05),    # a short hard fall
    "draw": (0.0, 0.0),       # does not travel; it is revealed. See `_draw_chain`
    "hold": (0.0, 0.0),
}

#: The stamp lands harder than anything else, which is what "stamp" means. Two frames
#: rather than three, so it arrives in fewer, larger jumps.
_STAMP_HOLD = 2


def _travel(target: str, offset_pixels: float, progress: str) -> str:
    """Resting position, plus however much of the entry offset is still to be covered.

    The sign is folded into the operator rather than left on the number. `x+-100*(...)`
    is valid ffmpeg and unreadable, and this expression is the first thing anybody
    debugging a misplaced layer will look at.
    """
    if not round(offset_pixels, 2):
        return target
    sign = "-" if offset_pixels < 0 else "+"
    return f"{target}{sign}{abs(offset_pixels):.1f}*(1-{progress})"


def _draw_chain(label: str, start: float, duration: float, *, fps: int,
                hold: int) -> str:
    """Reveal a layer left to right instead of moving it.

    Red string is the case this exists for: it connects two things already on screen, and
    the drawing *is* the argument, so it has to appear progressively rather than arrive.
    `crop` with `eval=frame` re-evaluates its width every frame, which is the only way to
    animate a reveal without a mask.

    The width floors at two pixels rather than zero — a zero-width crop is an invalid
    filter, and it fails at render time rather than at build time.
    """
    progress = _stepped_expression(start, duration, fps=fps, hold=hold)
    return (f"[{label}]crop=w='max(2\\,iw*{progress})':h=ih:x=0:y=0:eval=frame,"
            f"format=yuva420p[{label}d]")


@dataclass(frozen=True)
class Placement:
    """Where a layer rests and how big it is, both as fractions of the frame.

    Fractions rather than pixels throughout, so one composition renders at 720p for a
    preview and 1080p for delivery without being laid out twice. `height` is the
    load-bearing one: a cut-out arrives at whatever size its source image happened to be,
    and a 1024-pixel-wide portrait dropped onto a 1280-wide frame covers almost all of it
    — which is not a placement, it is a background.
    """

    x: float = 0.5
    y: float = 0.5
    #: Fraction of the frame's height this layer should occupy. 0 leaves it as supplied.
    height: float = 0.0
    #: Degrees. Paper is laid down by hand and almost never lands square.
    rotate: float = 0.0

    @classmethod
    def of(cls, value) -> Placement:
        """Accept a bare (x, y) too — most layers need nothing else said about them."""
        if isinstance(value, Placement):
            return value
        if isinstance(value, (tuple, list)) and len(value) >= 2:
            return cls(float(value[0]), float(value[1]),
                       float(value[2]) if len(value) > 2 else 0.0,
                       float(value[3]) if len(value) > 3 else 0.0)
        return cls()


def shot_filtergraph(rows: list[dict], placements: dict, *,
                     width: int, height: int, fps: int) -> str:
    """The filter_complex that assembles one beat.

    `rows` is a `PaperShot.timeline()`. `placements` maps a layer key to a `Placement`,
    or to a bare (x, y) pair, so a composition is described once and renders at any size.
    """
    chains: list[str] = []
    # Input 0 is the base sheet, scaled to fill. Everything else overlays onto it in the
    # order the timeline already sorted them into.
    chains.append(f"[0:v]scale={width}:{height},setsar=1,format=yuva420p[canvas0]")

    canvas = "canvas0"
    overlay_index = 0
    for index, row in enumerate(rows):
        if row["key"] == "base":
            continue
        overlay_index += 1
        # Inputs are supplied in `rows` order, base first, so a row's own position *is*
        # its input index. Offsetting by one made every layer read the next layer's
        # image, and the last one read an input that did not exist.
        source = f"{index}:v"
        label = f"L{overlay_index}"
        spot = Placement.of(placements.get(row["key"], Placement()))
        rest_x, rest_y = spot.x, spot.y
        entry = str(row["entry"])
        hold = _STAMP_HOLD if entry == "stamp" else int(row["hold_frames"])
        offset_x, offset_y = _ENTRY_OFFSETS.get(entry, (0.0, 0.0))

        # Sized before anything else, so the entry offsets and the reveal crop all work
        # against the size it will actually be composited at.
        prepare = ["setsar=1"]
        if spot.height > 0:
            # Height-driven with the width following, so the layer keeps its proportions.
            # -2 rather than -1 because libx264 needs even dimensions and an odd
            # intermediate fails at encode time rather than here.
            prepare.append(f"scale=-2:{max(2, round(height * spot.height))}")
        if round(spot.rotate, 2):
            # Transparent corners, not black ones: the whole point is that the sheet
            # underneath shows through where this one does not cover it.
            prepare.append(f"rotate={math.radians(spot.rotate):.5f}"
                           ":fillcolor=none:ow=rotw(iw):oh=roth(ih)")
        prepare.append("format=yuva420p")
        chains.append(f"[{source}]{','.join(prepare)}[{label}]")

        if entry == "draw":
            chains.append(_draw_chain(label, row["start"], row["duration"],
                                      fps=fps, hold=hold))
            moving = f"{label}d"
            progress = "1"
        else:
            moving = label
            progress = _stepped_expression(row["start"], row["duration"],
                                           fps=fps, hold=hold)

        # Resting position in pixels, minus the entry offset scaled by how far the move
        # still has to go. At progress 0 the element sits at rest+offset; at 1, at rest.
        target_x = f"(W-w)*{rest_x:.4f}"
        target_y = f"(H-h)*{rest_y:.4f}"
        x_expr = _travel(target_x, offset_x * width, progress)
        y_expr = _travel(target_y, offset_y * height, progress)

        # `enable` rather than trusting the position: an element parked off-frame is
        # still composited every frame, and eighty of those is real encode time.
        out = f"canvas{overlay_index}"
        chains.append(
            f"[{canvas}][{moving}]overlay=x='{x_expr}':y='{y_expr}'"
            f":enable='gte(t,{round(float(row['start']), 4)})'"
            f":eval=frame:format=auto[{out}]"
        )
        canvas = out

    chains.append(f"[{canvas}]format=yuv420p[out]")
    return ";".join(chains)


def render_shot(shot: PaperShot, sources: dict[str, Path], out_path: Path, *,
                placements: dict | None = None,
                width: int = 1920, height: int = 1080, fps: int = 30) -> Path:
    """Composite and encode one beat.

    `sources` maps layer key to an image already prepared — cut-outs screened, scraps
    torn. This function does not screen or tear anything: doing it here would re-screen
    the same cut-out on every beat it appears in, and the halftone is meant to be applied
    once so that every instance of an element is identical.

    A layer named in the shot with no source is skipped rather than failing. A beat that
    planned for a stamp nobody supplied should still render the other four layers, since
    the alternative is a run that has already paid for a script and a voiceover dying over
    a missing decoration.
    """
    rows = [row for row in shot.timeline(fps=fps)
            if row["key"] == "base" or row["key"] in sources]
    if not any(row["key"] == "base" for row in rows):
        raise ValueError("a paper shot needs a base sheet")
    if "base" not in sources:
        raise ValueError("no base image supplied")

    out_path = Path(out_path).with_suffix(".mp4")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    args = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    for row in rows:
        # Every input is a still looped for the shot's length. `-loop 1` with `-t` is
        # what turns a PNG into a stream the overlay chain can animate against.
        args += ["-loop", "1", "-t", f"{shot.seconds:.3f}", "-i", str(sources[row["key"]])]

    args += [
        "-filter_complex",
        shot_filtergraph(rows, placements or {}, width=width, height=height, fps=fps),
        "-map", "[out]", "-r", str(fps), "-t", f"{shot.seconds:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    _run(args, "compositing a paper shot")
    return out_path


def catalogue() -> dict:
    """Everything selectable in this style, for a settings page and for the agent."""
    return {
        "tones": [{"key": tone.key, "label": tone.label} for tone in TONES.values()],
        "layers": [{"key": layer.key, "label": layer.label, "depth": layer.depth,
                    "entry": layer.entry, "when_to_use": layer.when_to_use}
                   for layer in STACK],
        "hold_frames": DEFAULT_HOLD_FRAMES,
        "camera": "locked",
        "generated_video": False,
        "note": "Built from stills and ffmpeg arithmetic. This style generates no video "
                "and costs nothing per shot beyond the source images.",
    }
