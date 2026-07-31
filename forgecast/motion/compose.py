"""Animated elements, and the filtergraph they compile to.

## Two constraints that shape everything here

**1. Text alpha is keyframable; image alpha is not.** `drawtext` accepts an expression
for `alpha`, so text can follow any opacity curve for free. Overlaid images have no
equivalent — the only way to drive an image's alpha from an expression is `geq`, which
evaluates per pixel per channel and is roughly two orders of magnitude slower than
everything else in the graph. So image opacity uses `fade=alpha=1`, which covers what
is actually needed (appear, disappear) at normal speed. That is why `ImageCard` takes
`fade_in`/`fade_out` durations while `Text` takes an alpha `Track`.

**2. An animated `scale` changes the frame size every frame, and most filters cannot
survive that.** This is the constraint that dictates the *order* of the card chain, and
it is worth spelling out because it fails silently — the render succeeds and the card
simply never moves. Measured on ffmpeg 6.1, with a card scaled 40 → 520 px:

    format=rgba AFTER  the animated scale   frozen at 40 px for the whole clip
    format=rgba BEFORE the animated scale   animates correctly
    pad         after  the animated scale   frozen
    drawbox     after  the animated scale   box geometry frozen (iw is config-time)
    split       after  the animated scale   frozen in BOTH branches
    rotate with ow='hypot(iw,ih)'           canvas frozen, so the growing card clips
    rotate with a literal ow/oh             animates and stays centred

So: everything that fixes or reads a frame size runs *before* the scale, and the one
filter that must follow it (`rotate`) gets a literal canvas computed here in Python
from the largest scale the track ever reaches. A border is `pad`ded on ahead of the
scale, which also means its thickness grows with the card — which is what scaling a
bordered card looks like in a real compositor anyway. And a card's shadow is a second
decode of the same file rather than a `split`, because splitting froze it.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass, field
from math import ceil, hypot
from pathlib import Path

from .keyframe import Track, _fmt

# Escaping for text that lands inside a filtergraph. Colons separate filter options
# and single quotes delimit expressions, so both have to go, and a stray one produces
# an ffmpeg parse error rather than a wrong picture.
_TEXT_UNSAFE = str.maketrans({
    ":": "\\:", "'": "’", "\\": "", "%": "", "\n": " ",
    "[": "(", "]": ")", ",": "\\,", ";": " ",
})

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def font_file() -> str | None:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def escape_text(value: str) -> str:
    return str(value).translate(_TEXT_UNSAFE)


def image_size(path: Path) -> tuple[int, int]:
    """Intrinsic pixel size of an image, for sizing a rotation canvas.

    Falls back to 16:9 rather than raising: a wrong canvas produces a slightly
    over-sized transparent border, while an exception would kill the render.
    """
    from ..vision.probe import FFPROBE

    try:
        proc = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x",
             str(path)],
            capture_output=True, timeout=20,
        )
        width, height = proc.stdout.decode().strip().split(",")[0].split("x")[:2]
        return (int(width), int(height))
    except Exception:
        return (1920, 1080)


def _even(value: float) -> int:
    """libx264 needs even dimensions, and rotate canvases feed it directly."""
    number = ceil(value)
    return number + (number % 2)


def _pixels(value: float, extent: int) -> float:
    """A fraction of the frame when <= 1, otherwise an absolute pixel count."""
    return value * extent if 0 <= value <= 1 else value


@dataclass
class Element:
    """Common timing. `start` shifts every track of this element."""

    start: float = 0.0
    duration: float = 3.0

    @property
    def end(self) -> float:
        return self.start + self.duration

    def _window(self) -> str:
        return f"between(t,{_fmt(self.start)},{_fmt(self.end)})"


@dataclass
class Text(Element):
    """Animated type. Alpha, position and size can all be keyframed."""

    text: str = ""
    size: int = 48
    colour: str = "white"
    x: Track | float = 0.5           # fraction of width when <= 1, else pixels
    y: Track | float = 0.8
    alpha: Track | None = None
    box: bool = False
    box_colour: str = "black@0.55"
    border: int = 0
    border_colour: str = "black"
    shadow: tuple[int, int] | None = None

    def compile(self, width: int, height: int) -> str:
        font = font_file()
        options = [f"text='{escape_text(self.text)}'"]
        if font:
            options.append(f"fontfile='{font}'")
        options += [
            f"fontsize={self.size}",
            f"fontcolor={self.colour}",
            f"x={self._axis(self.x, width, 'text_w')}",
            f"y={self._axis(self.y, height, 'text_h')}",
        ]
        if self.alpha is not None:
            # drawtext clamps alpha itself, but a negative value from an easing
            # overshoot makes it error rather than clamp.
            options.append(
                f"alpha='max(0,min(1,{self.alpha.expression(offset=self.start)}))'"
            )
        if self.box:
            options += ["box=1", f"boxcolor={self.box_colour}", "boxborderw=18"]
        if self.border:
            options += [f"borderw={self.border}", f"bordercolor={self.border_colour}"]
        if self.shadow:
            options += [f"shadowx={self.shadow[0]}", f"shadowy={self.shadow[1]}"]
        options.append(f"enable='{self._window()}'")
        return "drawtext=" + ":".join(options)

    def _axis(self, value: Track | float, extent: int, measure: str) -> str:
        """Centre-relative placement, so a fraction means "this far across".

        The track is offset by `start` like every other track on this element, so a
        move written from t=0 plays when the element appears rather than before it.
        """
        if isinstance(value, Track):
            expression = value.expression(offset=self.start, scale=extent)
            return f"'({expression})-({measure}/2)'"
        return f"'({_fmt(_pixels(value, extent))})-({measure}/2)'"


@dataclass
class ImageCard(Element):
    """An image overlaid with animated scale, position and rotation.

    `scale` is a fraction of the frame width. Opacity uses fades — see the module
    docstring for why it cannot be a Track.
    """

    path: Path | None = None
    scale: Track | float = 0.55
    x: Track | float = 0.5
    y: Track | float = 0.45
    rotation: Track | float = 0.0        # radians
    fade_in: float = 0.35
    fade_out: float = 0.0
    shadow: bool = True
    shadow_offset: int = 14
    shadow_opacity: float = 0.45
    border: int = 0
    border_colour: str = "white"

    def max_width(self, frame_width: int) -> float:
        """The widest this card ever gets, in pixels. Sizes the rotation canvas."""
        if isinstance(self.scale, Track):
            values = [key.value for key in self.scale.keys] or [0.0]
            return _pixels(max(values), frame_width)
        return _pixels(self.scale, frame_width)

    @property
    def input_count(self) -> int:
        """How many decoder inputs this card claims.

        Two when it casts a shadow, because the shadow is a second copy of the same
        image rather than a `split` of the first — see `compile`.
        """
        return 2 if self.shadow else 1

    def _steps(self, width: int) -> list[str]:
        """The per-copy filter chain, in the one order that survives animation."""
        scale_expression = (
            self.scale.expression(offset=self.start, scale=width)
            if isinstance(self.scale, Track)
            else _fmt(_pixels(self.scale, width))
        )

        # Order matters — see the module docstring. format and the border pad both
        # come first, while the frame size is still static.
        steps = ["format=rgba"]
        if self.border:
            steps.append(
                f"pad=iw+{self.border * 2}:ih+{self.border * 2}:{self.border}:"
                f"{self.border}:color={self.border_colour}"
            )
        # eval=frame is what makes the scale animate rather than being fixed at t=0.
        steps.append(f"scale=w='{scale_expression}':h=-1:eval=frame")

        rotation_expression = (
            self.rotation.expression(offset=self.start)
            if isinstance(self.rotation, Track) else _fmt(self.rotation)
        )
        if rotation_expression not in {"0", "0.0"}:
            # A literal canvas, big enough for the largest scale turned to its worst
            # angle. hypot(iw,ih) would be evaluated once against the *first* frame,
            # which is the smallest one, and the card would clip as it grew.
            source_w, source_h = image_size(self.path) if self.path else (1920, 1080)
            widest = self.max_width(width) + self.border * 2
            tallest = widest * (source_h / max(1, source_w))
            canvas = _even(hypot(widest, tallest))
            steps.append(
                f"rotate='{rotation_expression}':c=none:ow={canvas}:oh={canvas}"
            )

        if self.fade_in > 0:
            steps.append(
                f"fade=t=in:st={_fmt(self.start)}:d={_fmt(self.fade_in)}:alpha=1"
            )
        if self.fade_out > 0:
            steps.append(
                f"fade=t=out:st={_fmt(self.end - self.fade_out)}:"
                f"d={_fmt(self.fade_out)}:alpha=1"
            )
        return steps

    def compile(self, inputs: list[int], width: int, height: int, label: str,
                out_label: str) -> tuple[list[str], str]:
        """Return (filter chain fragments, the label now carrying this card).

        `inputs` are the decoder indices this card owns — one, or two when it casts a
        shadow. The shadow is a *second decode of the same file* rather than a `split`
        of the first, and that is not a stylistic choice: measured on ffmpeg 6.1,
        `split` freezes a stream whose frame size changes, so splitting an animated
        card silently pins it at its first-frame size. Decoding a still image twice
        costs microseconds and removes the failure mode entirely.
        """
        index = inputs[0]
        target = f"card{index}"
        chain: list[str] = [f"[{index}:v]{','.join(self._steps(width))}[{target}]"]

        x_expression = _overlay_axis(self.x, width, "w", self.start)
        y_expression = _overlay_axis(self.y, height, "h", self.start)

        if self.shadow and len(inputs) > 1:
            # A displaced dark copy under the card. Cheaper and more predictable than
            # blurring an alpha matte, and at video scale it reads the same.
            # colorchannelmixer zeroes the colour channels and scales alpha in one
            # linear pass; geq would do the same thing per pixel per channel through
            # an expression evaluator — same picture, ~100x the cost.
            shadow_label = f"{target}_shadow"
            chain.append(
                f"[{inputs[1]}:v]{','.join(self._steps(width))},"
                f"colorchannelmixer=rr=0:rg=0:rb=0:gr=0:gg=0:gb=0:"
                f"br=0:bg=0:bb=0:aa={_fmt(self.shadow_opacity)}[{shadow_label}]"
            )
            chain.append(
                f"[{label}][{shadow_label}]overlay="
                f"x='{x_expression}+{self.shadow_offset}':"
                f"y='{y_expression}+{self.shadow_offset}':"
                f"eval=frame:enable='{self._window()}'[{out_label}_s]"
            )
            chain.append(
                f"[{out_label}_s][{target}]overlay=x='{x_expression}':"
                f"y='{y_expression}':eval=frame:enable='{self._window()}'[{out_label}]"
            )
        else:
            chain.append(
                f"[{label}][{target}]overlay=x='{x_expression}':y='{y_expression}':"
                f"eval=frame:enable='{self._window()}'[{out_label}]"
            )
        return chain, out_label


@dataclass
class Band(Element):
    """A solid or translucent rectangle — lower thirds, title backing, wipes."""

    colour: str = "black@0.6"
    x: Track | float = 0.0
    y: Track | float = 0.78
    width_fraction: float = 1.0
    height_fraction: float = 0.14

    def compile(self, width: int, height: int) -> str:
        box_width = int(self.width_fraction * width)
        box_height = int(self.height_fraction * height)
        x_expression = (
            self.x.expression(offset=self.start, scale=width)
            if isinstance(self.x, Track) else _fmt(_pixels(self.x, width))
        )
        y_expression = (
            self.y.expression(offset=self.start, scale=height)
            if isinstance(self.y, Track) else _fmt(_pixels(self.y, height))
        )
        return (
            f"drawbox=x='{x_expression}':y='{y_expression}':w={box_width}:"
            f"h={box_height}:color={self.colour}:t=fill:enable='{self._window()}'"
        )


def _overlay_axis(value: Track | float, extent: int, measure: str,
                  offset: float = 0.0) -> str:
    """Overlay position, centring the element on the given point."""
    if isinstance(value, Track):
        return f"({value.expression(offset=offset, scale=extent)})-({measure}/2)"
    return f"({_fmt(_pixels(value, extent))})-({measure}/2)"


# ----------------------------------------------------------------------- scene


@dataclass
class Scene:
    """A base layer plus animated elements, compiled into one ffmpeg invocation."""

    duration: float
    width: int = 1280
    height: int = 720
    fps: int = 30
    background: Path | None = None       # image or video; a colour card if absent
    background_colour: str = "0x101418"
    elements: list[Element] = field(default_factory=list)

    def add(self, *elements: Element) -> Scene:
        self.elements.extend(elements)
        return self

    def command(self, out_path: Path) -> list[str]:
        cards = [item for item in self.elements if isinstance(item, ImageCard) and item.path]
        overlays = [item for item in self.elements if not isinstance(item, ImageCard)]

        args: list[str] = ["-y"]
        if self.background and self.background.exists():
            suffix = self.background.suffix.lower()
            if suffix in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
                args += ["-loop", "1", "-t", _fmt(self.duration), "-i", str(self.background)]
            else:
                args += ["-i", str(self.background)]
        else:
            args += [
                "-f", "lavfi", "-i",
                f"color=c={self.background_colour}:s={self.width}x{self.height}"
                f":r={self.fps}:d={_fmt(self.duration)}",
            ]

        # Input 0 is the background, so cards start at 1. A shadowed card claims two
        # consecutive indices for the same file, which is why this allocates rather
        # than just enumerating.
        allocated: list[list[int]] = []
        next_index = 1
        for card in cards:
            indices = list(range(next_index, next_index + card.input_count))
            next_index += card.input_count
            allocated.append(indices)
            for _ in indices:
                args += ["-loop", "1", "-t", _fmt(self.duration), "-i", str(card.path)]

        chain: list[str] = [
            f"[0:v]scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
            f"crop={self.width}:{self.height},setsar=1,fps={self.fps}[bg]"
        ]
        label = "bg"
        for position, (card, indices) in enumerate(zip(cards, allocated, strict=True), 1):
            fragments, label = card.compile(
                indices, self.width, self.height, label, f"v{position}"
            )
            chain.extend(fragments)

        drawn = [
            element.compile(self.width, self.height)
            for element in overlays
            if hasattr(element, "compile")
        ]
        if drawn:
            chain.append(f"[{label}]{','.join(drawn)}[out]")
            label = "out"

        args += [
            "-filter_complex", ";".join(chain),
            "-map", f"[{label}]",
            "-t", _fmt(self.duration),
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-r", str(self.fps),
            str(out_path),
        ]
        return args

    def render(self, out_path: Path, *, timeout: float = 600.0) -> Path:
        from ..vision.probe import FFMPEG, ProbeError, run

        out_path.parent.mkdir(parents=True, exist_ok=True)
        args = self.command(out_path)
        proc = run([FFMPEG, "-hide_banner", "-loglevel", "error", *args],
                   label="motion scene", timeout=timeout)
        if proc.returncode != 0 or not out_path.exists():
            detail = proc.stderr.decode(errors="replace")[-600:]
            raise ProbeError(
                f"motion scene render failed: {detail}\n"
                f"filtergraph: {shlex.join(args)[:900]}"
            )
        return out_path
