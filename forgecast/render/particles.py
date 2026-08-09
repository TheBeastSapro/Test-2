"""Snow and fog over a finished shot.

## Why these two and why sparingly

The reference uses atmosphere twice in nine minutes — falling snow at 0:59, fog at 2:18
— and that ratio is the point. A creature standing in weather reads as being *somewhere*;
weather on every shot reads as a filter, and the eye stops seeing the creature.

## Why the operator chooses, and not this module

I looked for a signal in the source material and there is not one. Across nine real
creature pages on three wikis, only three contained any weather word at all and each
appeared exactly once — one "fog" in the 13,471 characters of the Doors wiki's Seek
page, one "smoke" in Rush's, one "winter" in Amber's. A passing noun in a wall of prose
is not a page saying its creature lives in the snow, and an atmosphere picked off it
would be this app inventing a fact about somebody else's canon.

So this is applied where it is asked for. The measurement is recorded rather than
retried, because the next person to have the idea should be able to see it was checked.

## Why a tiled texture rather than a particle system

ffmpeg has no particles, and a per-frame Python compositor is tens of seconds a shot. A
texture that repeats with the frame's own height can be scrolled forever with one
`overlay` and an expression: generate at twice the height with the top half copied
exactly to the bottom, scroll through one height, and the wrap is seamless because the
pixel arriving is the pixel that left.
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from . import ffmpeg as ff

#: Flakes per megapixel of frame. Sparse: the reference's snow is legible as individual
#: flakes, and past this it becomes static.
SNOW_DENSITY = 90

#: Flake radius as a fraction of frame height, near and far. Two sizes at two speeds is
#: what gives depth — one size at one speed is a texture sliding down the glass.
SNOW_NEAR = 0.0042
SNOW_FAR = 0.0022

#: Seconds for a flake to cross the frame, near and far. The near layer falls faster,
#: which is the parallax that makes the two read as distance rather than as two textures.
SNOW_FALL_NEAR = 7.0
SNOW_FALL_FAR = 13.0

#: Peak opacity of each layer. Low, because snow is meant to be noticed at the edge of
#: attention — snow you look at is snow that has taken the shot off the creature.
SNOW_ALPHA_NEAR = 0.55
SNOW_ALPHA_FAR = 0.30

#: An even haze under the unevenness. Without it the blobs leave dry patches, and a
#: sheet that covers three quarters of the frame and stops reads as a gradient wipe
#: rather than as weather — which is what the first render of this looked like: hazed
#: to the left, a hard vertical edge, clear dark wall to the right. Fog has a floor.
FOG_BASE = 0.38

#: Fog: blobs per megapixel, their radius as a fraction of frame height, and how hard
#: the whole sheet is blurred afterwards. Few and large, then blurred past recognition —
#: what is wanted is unevenness, not clouds.
FOG_BLOBS = 22
FOG_RADIUS = 0.30
FOG_BLUR = 0.055

#: Peak opacity, and seconds to cross the frame sideways. Slow enough that a four-second
#: shot shows drift rather than travel.
FOG_ALPHA = 0.30
FOG_DRIFT = 26.0


def _seamless(width: int, height: int, draw_one) -> Image.Image:
    """A texture twice `height` tall whose bottom half repeats its top exactly.

    That periodicity is what makes an endless scroll possible with one overlay: after
    scrolling a full `height` the image beneath the frame is identical to the one that
    started there, so there is no wrap and no seam to hide.
    """
    tile = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw_one(tile)
    sheet = Image.new("RGBA", (width, height * 2), (0, 0, 0, 0))
    sheet.paste(tile, (0, 0))
    sheet.paste(tile, (0, height))
    return sheet


def snow_sheet(width: int, height: int, *, radius: float, alpha: float,
               seed: int) -> Image.Image:
    """One layer of flakes, seamless vertically."""
    rng = random.Random(seed)
    count = max(12, round(SNOW_DENSITY * (width * height) / 1_000_000))
    size = max(1.0, radius * height)
    value = int(255 * alpha)

    def scatter(tile: Image.Image) -> None:
        pen = ImageDraw.Draw(tile)
        for _ in range(count):
            x = rng.uniform(0, width)
            y = rng.uniform(0, height)
            # Flakes vary in size within a layer as well as between layers; identical
            # discs read as a pattern however they are scattered.
            r = size * rng.uniform(0.6, 1.25)
            pen.ellipse([(x - r, y - r), (x + r, y + r)],
                        fill=(255, 255, 255, int(value * rng.uniform(0.6, 1.0))))

    return _seamless(width, height, scatter)


def fog_sheet(width: int, height: int, *, seed: int) -> Image.Image:
    """A soft uneven sheet, seamless horizontally.

    Built the same way as the snow and then rotated in use: the drift is sideways, so
    the repeat has to be along the width.
    """
    rng = random.Random(seed)
    radius = FOG_RADIUS * height
    value = int(255 * FOG_ALPHA)

    def blobs(tile: Image.Image) -> None:
        pen = ImageDraw.Draw(tile)
        # The floor first, then the variation on top of it.
        pen.rectangle([(0, 0), tile.size], fill=(216, 216, 222, int(value * FOG_BASE)))
        for _ in range(FOG_BLOBS):
            x, y = rng.uniform(0, height), rng.uniform(0, width)
            r = radius * rng.uniform(0.7, 1.4)
            pen.ellipse([(x - r, y - r), (x + r, y + r)],
                        fill=(216, 216, 222, int(value * rng.uniform(0.5, 1.0))))

    # Generated tall and transposed, so the seam runs along the axis it scrolls on.
    sheet = _seamless(height, width, blobs).transpose(Image.TRANSPOSE)
    return sheet.filter(ImageFilter.GaussianBlur(max(4, int(FOG_BLUR * height))))


def apply(clip_path: Path | str, out_path: Path | str, kind: str, *,
          seconds: float, width: int, height: int, fps: int = 30,
          seed: int = 0, encoder: str = "") -> Path:
    """Lay snow or fog over a finished shot. Returns the clip unchanged for anything else.

    Unknown kinds pass through rather than raising: this sits in the middle of a render
    that has already been paid for, and an atmosphere nobody recognises is a reason to
    ship the shot without it, not a reason to lose the run.
    """
    clip, out = Path(clip_path), Path(out_path)
    wanted = str(kind or "").strip().lower()
    if wanted not in ("snow", "fog"):
        return clip

    work = out.parent / f"{out.stem}_atmos"
    work.mkdir(parents=True, exist_ok=True)
    # A still needs looping to have a duration; a clip already has one and looping it
    # would make the shot repeat under the weather. Most canon shots are stills, so
    # getting this the wrong way round would be the common case rather than the corner.
    still = clip.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
    inputs: list[str] = (["-loop", "1", "-i", str(clip)] if still
                         else ["-i", str(clip)])
    # Fitted to the frame before anything is laid over it, for two reasons that both
    # bite. The sheets below are built at the frame's size, so a base of any other size
    # would be weathered over part of itself. And a canon shot that needed no plate
    # arrives as the wiki's own file at the wiki's own dimensions — 1962x1425 on the
    # first one this hit — which libx264 refuses outright for having an odd height.
    # Cover-and-crop rather than stretch, the same fit the rest of the renderer uses.
    steps: list[str] = [f"[0:v]scale={width}:{height}:force_original_aspect_ratio="
                        f"increase,crop={width}:{height}[base]"]
    stream = "[base]"

    if wanted == "snow":
        layers = (
            ("far", SNOW_FAR, SNOW_ALPHA_FAR, SNOW_FALL_FAR, seed * 2 + 1),
            ("near", SNOW_NEAR, SNOW_ALPHA_NEAR, SNOW_FALL_NEAR, seed * 2 + 2),
        )
        for index, (name, radius, alpha, fall, layer_seed) in enumerate(layers, start=1):
            path = work / f"snow_{name}.png"
            snow_sheet(width, height, radius=radius, alpha=alpha,
                       seed=layer_seed).save(path)
            inputs += ["-loop", "1", "-i", str(path)]
            # `mod` keeps the offset inside one height, so the expression never grows
            # large enough to lose precision on a long shot.
            speed = height / max(0.5, fall)
            steps.append(
                f"{stream}[{index}:v]overlay=x=0:"
                f"y='-mod({speed:.3f}*t\\,{height})':format=auto[a{index}]")
            stream = f"[a{index}]"
    else:
        path = work / "fog.png"
        fog_sheet(width, height, seed=seed + 1).save(path)
        inputs += ["-loop", "1", "-i", str(path)]
        speed = width / max(0.5, FOG_DRIFT)
        steps.append(
            f"{stream}[1:v]overlay=y=0:"
            f"x='-mod({speed:.3f}*t\\,{width})':format=auto[a1]")
        stream = "[a1]"

    ff.run_ffmpeg(
        [*inputs, "-filter_complex", ";".join(steps),
         "-map", stream, "-t", f"{max(0.1, float(seconds)):.3f}",
         *ff.vcodec(fps, encoder), "-r", str(fps), "-an", str(out)],
        label=f"{wanted} overlay",
    )
    return out
