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

    vignette_step = "vignette=angle=PI/8:mode=backward," if vignette else ""
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
    """Ragged the alpha channel, so a cut-out looks torn rather than cut.

    The single cheapest thing that separates this style from a clean composite. A matte
    from background removal has a smooth, slightly soft edge — correct for a photographic
    composite and wrong here, where every element is supposed to have been pulled apart by
    hand.

    Works on alpha only. Displacing the colour channels as well would fringe the edge with
    whatever was behind the subject in the source image.
    """
    amount = max(1, int(bite))
    return (
        "format=yuva420p,"
        "alphaextract,"
        # Displace the edge by a noise field, then re-threshold. Blurring alone rounds
        # the edge; blurring and re-thresholding makes it wander.
        f"noise=alls={amount * 9}:allf=t+u:all_seed={int(seed) % 10000},"
        f"boxblur=luma_radius={amount}:luma_power=1,"
        "curves=all='0/0 0.46/0 0.54/1 1/1'"
    )


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
