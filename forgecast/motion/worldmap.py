"""The animated world map: a dot-grid globe, markers that land, arcs that draw.

## What this produces

A video clip. Not an overlay filter, not a filtergraph fragment — an mp4 the rest of
the system treats exactly like any other scene visual. That choice is what makes the
map work on both render backends and in the preview studio without three
implementations of the same geometry: the map is rendered once by Pillow, and after
that it is footage.

## Why frames rather than ffmpeg drawing

Everything else in `forgecast.motion` compiles to ffmpeg expressions, because ffmpeg
can express a value changing over time and that is all a text or card animation needs.
A map cannot be expressed that way. It is tens of thousands of primitives per frame,
laid out by a projection, with a route that has to be clipped at the antimeridian.
`drawbox` cannot do it and `geq` would take minutes a frame.

Pillow can draw a frame of it in tens of milliseconds. So the map is rasterised frame
by frame and encoded — the one place in this package where leaving ffmpeg's expression
language is the right call, rather than the lazy one.

## The three animations, and why those three

A documentary map does three things, and doing more makes it a dashboard:

* **Reveal** — the land resolves in, either as a wipe across the frame or a fade up.
  It gives the establishing beat somewhere to land.
* **Markers** — a place matters, and it lands with a ring that expands and fades. The
  ring is what makes a dot read as "here", and it is why a static dot looks dead.
* **Arcs** — a relationship between two places, drawn along the actual short path over
  the sphere. The head of the arc leads the drawn tail so the eye follows it.

Underneath all three the window can push in, from the whole world to the region the
markers occupy, which is the move that turns a map into a shot.
"""

from __future__ import annotations

import colorsys
import itertools
import logging
import math
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .geo import (
    Bounds,
    Projection,
    bounds_for,
    great_circle,
    is_land,
    resolve,
    split_at_seam,
)

log = logging.getLogger("forgecast.motion.worldmap")

# Dots are placed on a screen-space grid, not a geographic one, so the spacing stays
# even when the window is zoomed. Below about 5px they merge into a smear at 720p;
# above about 16 they read as a pegboard rather than a map.
MIN_DOT_SPACING = 5
MAX_DOT_SPACING = 16


def _rgb(value: str) -> tuple[int, int, int]:
    text = value.lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _mix(colour: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    """Scale a colour towards black. Used for the un-revealed part of the map."""
    factor = max(0.0, min(1.0, amount))
    return tuple(int(channel * factor) for channel in colour)  # type: ignore[return-value]


def _brighten(colour: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    hue, light, sat = colorsys.rgb_to_hls(*(c / 255 for c in colour))
    r, g, b = colorsys.hls_to_rgb(hue, min(1.0, light + amount), sat)
    return (int(r * 255), int(g * 255), int(b * 255))


def _ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 2


def _ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


@dataclass
class MapStyle:
    """How the map looks. Every field is JSON-serialisable, like `MotionPreset`."""

    name: str = "documentary_dark"
    ocean: str = "#0b1017"
    land: str = "#1e3a4c"
    land_accent: str = "#2f6b86"     # dots inside the focus window
    marker: str = "#ffd166"
    arc: str = "#ffd166"
    graticule: str = "#141d28"       # lat/lon grid; empty string turns it off
    dot_spacing: int = 8
    dot_radius: float = 1.6
    arc_width: int = 2
    marker_radius: int = 5
    label_size_ratio: float = 0.032
    label_colour: str = "#e6e9ef"
    vignette: float = 0.35            # 0 = off, 1 = heavy
    reveal: str = "wipe"              # wipe | fade | none

    def as_dict(self) -> dict:
        from dataclasses import asdict

        return asdict(self)


# Named looks. `documentary_dark` is the default because it is the register the
# documentary_unveil motion preset pairs with — restrained, cool, land barely brighter
# than the ocean until something is happening on it.
MAP_LIBRARY: dict[str, MapStyle] = {
    "documentary_dark": MapStyle(name="documentary_dark"),
    "blueprint": MapStyle(
        name="blueprint", ocean="#06121f", land="#12405f", land_accent="#2b8fc4",
        marker="#7fe3ff", arc="#7fe3ff", graticule="#0d2438", dot_spacing=7,
        dot_radius=1.5, vignette=0.28,
    ),
    "amber_archive": MapStyle(
        name="amber_archive", ocean="#120d08", land="#3d2a16", land_accent="#8a5a22",
        marker="#ffb547", arc="#ff8c3a", graticule="#1d150c", dot_spacing=9,
        dot_radius=1.8, vignette=0.42,
    ),
    "signal_red": MapStyle(
        name="signal_red", ocean="#0d0b0e", land="#2b1c22", land_accent="#7a2f3d",
        marker="#ff5d5d", arc="#ff5d5d", graticule="#1a1216", dot_spacing=8,
        dot_radius=1.6, vignette=0.45,
    ),
    "clean_light": MapStyle(
        name="clean_light", ocean="#eef1f5", land="#c3ced9", land_accent="#8fa6b8",
        marker="#1f6feb", arc="#1f6feb", graticule="#e2e7ee", dot_spacing=8,
        dot_radius=1.7, label_colour="#1b2430", vignette=0.0,
    ),
}


@dataclass
class Marker:
    """A place on the map, with the moment it lands."""

    lat: float
    lon: float
    label: str = ""
    at: float = 0.0                   # seconds into the clip
    pulse: bool = True

    @classmethod
    def of(cls, where, *, label: str = "", at: float = 0.0, pulse: bool = True) -> Marker:
        lat, lon = resolve(where)
        return cls(lat=lat, lon=lon, label=label or (where if isinstance(where, str) else ""),
                   at=at, pulse=pulse)


@dataclass
class Arc:
    """A route between two places, drawn along the short path over the sphere."""

    start: tuple[float, float]
    end: tuple[float, float]
    at: float = 0.0
    duration: float = 1.6
    label: str = ""

    @classmethod
    def between(cls, origin, destination, *, at: float = 0.0,
                duration: float = 1.6, label: str = "") -> Arc:
        return cls(start=resolve(origin), end=resolve(destination),
                   at=at, duration=duration, label=label)


@dataclass
class MapSpec:
    """Everything needed to render one map clip."""

    seconds: float = 6.0
    width: int = 1280
    height: int = 720
    fps: int = 30
    style: MapStyle = field(default_factory=lambda: MAP_LIBRARY["documentary_dark"])
    markers: list[Marker] = field(default_factory=list)
    arcs: list[Arc] = field(default_factory=list)
    # Start and end windows. Leave `focus` unset to derive it from the markers.
    view: Bounds = field(default_factory=Bounds)
    focus: Bounds | None = None
    push_in: bool = True
    push_start: float = 0.6
    push_duration: float = 3.4
    labels: bool = True

    def resolved_focus(self) -> Bounds:
        """Where the push-in ends: the given window, or the markers' own extent."""
        if self.focus is not None:
            return self.focus
        points = [(m.lat, m.lon) for m in self.markers]
        for arc in self.arcs:
            points.extend([arc.start, arc.end])
        if not points:
            return self.view
        return bounds_for(points)

    def opening_view(self) -> Bounds:
        """The window the clip starts on.

        A whole-world view is re-centred on wherever the story is. The centre of a
        360-degree window is free — every choice shows the same map, just with the
        seam somewhere else — so putting it on the subject turns the push-in into a
        pure zoom with no pan.

        That is not a cosmetic preference. Measured on a Los Angeles-to-Tokyo route
        before this: a Greenwich-centred world view panning to a Pacific-centred one
        swept the window across the seam, and Tokyo sat off-screen from 1.6s to 2.9s
        of a 6-second clip — the marker landed and then vanished. Starting on the
        subject's own meridian removes the pan, and with it the problem.
        """
        view = self.view
        if view.lon_span >= 359.0 and (self.markers or self.arcs):
            return view.with_lon_span(360.0, self.resolved_focus().lon_centre)
        return view

    def window_at(self, time: float) -> Bounds:
        aspect = self.width / self.height
        start = self.opening_view().with_aspect(aspect)
        if not self.push_in:
            return start
        target = self.resolved_focus().with_aspect(aspect)
        if self.push_duration <= 0:
            return target
        progress = _ease_in_out((time - self.push_start) / self.push_duration)
        return start.lerp(target, progress)


# ------------------------------------------------------------------- rendering


def _font(size: int):
    from PIL import ImageFont

    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ):
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _draw_graticule(draw, projection: Projection, style: MapStyle) -> None:
    if not style.graticule:
        return
    colour = _rgb(style.graticule)
    bounds = projection.bounds
    # A grid step that yields roughly six to ten lines across the window whatever the
    # zoom. A fixed 30-degree grid vanishes when zoomed in and clutters when zoomed out.
    for span, get, draw_line in (
        (bounds.lon_span, lambda v: projection.to_px(bounds.north, v)[0],
         lambda p: draw.line([(p, 0), (p, projection.height)], fill=colour, width=1)),
        (bounds.lat_span, lambda v: projection.to_px(v, bounds.west)[1],
         lambda p: draw.line([(0, p), (projection.width, p)], fill=colour, width=1)),
    ):
        step = next((s for s in (1, 2, 5, 10, 15, 30, 45, 60) if span / s <= 10), 60)
        start = math.floor((bounds.south if span is bounds.lat_span else bounds.west) / step) * step
        value = start
        limit = start + span + step
        while value <= limit:
            draw_line(get(value))
            value += step


def _draw_dots(draw, projection: Projection, style: MapStyle, *,
               reveal: float, focus: Bounds | None) -> int:
    """Stipple the land. Returns how many dots were drawn, for tests to assert on."""
    spacing = max(MIN_DOT_SPACING, min(MAX_DOT_SPACING, style.dot_spacing))
    radius = style.dot_radius
    base = _rgb(style.land)
    accent = _rgb(style.land_accent)
    bounds = projection.bounds
    lon_per_px = bounds.lon_span / projection.width
    lat_per_px = bounds.lat_span / projection.height

    # `reveal` is a wipe front measured in x. Everything left of it is drawn.
    front = projection.width * reveal if style.reveal == "wipe" else projection.width
    fade = 1.0 if style.reveal != "fade" else max(0.0, min(1.0, reveal))

    drawn = 0
    for py in range(spacing // 2, projection.height, spacing):
        lat = bounds.north - py * lat_per_px
        if not -90 <= lat <= 90:
            continue
        for px in range(spacing // 2, projection.width, spacing):
            if px > front:
                break
            lon = bounds.west + px * lon_per_px
            if lon > 180:
                lon -= 360
            if not is_land(lat, lon):
                continue
            inside = focus is not None and (
                focus.west <= lon <= focus.east and focus.south <= lat <= focus.north
            )
            colour = accent if inside else base
            if fade < 1.0:
                colour = _mix(colour, fade)
            draw.ellipse(
                [px - radius, py - radius, px + radius, py + radius], fill=colour
            )
            drawn += 1
    return drawn


def _draw_arcs(draw, projection: Projection, style: MapStyle,
               arcs: list[Arc], time: float) -> None:
    colour = _rgb(style.arc)
    head = _brighten(colour, 0.25)
    for arc in arcs:
        if time < arc.at:
            continue
        progress = 1.0 if arc.duration <= 0 else _ease_out((time - arc.at) / arc.duration)
        if progress <= 0:
            continue
        path = great_circle(arc.start, arc.end)
        # Trim to the drawn fraction *before* splitting, so a route that crosses the
        # seam still grows smoothly rather than jumping when it reaches the edge.
        keep = max(2, int(len(path) * progress))
        for segment in split_at_seam(path[:keep], projection):
            draw.line(segment, fill=colour, width=style.arc_width, joint="curve")
        if progress < 1.0:
            tip = split_at_seam(path[:keep], projection)
            if tip and tip[-1]:
                x, y = tip[-1][-1]
                r = style.arc_width + 2
                draw.ellipse([x - r, y - r, x + r, y + r], fill=head)


def _draw_markers(draw, projection: Projection, style: MapStyle,
                  markers: list[Marker], time: float, font) -> None:
    colour = _rgb(style.marker)
    label_colour = _rgb(style.label_colour)
    for marker in markers:
        if time < marker.at:
            continue
        if not projection.contains(marker.lat, marker.lon):
            continue
        x, y = projection.to_px(marker.lat, marker.lon)
        age = time - marker.at

        # The dot drops in over a fifth of a second; without the growth it appears
        # between two frames and the eye misses that anything happened.
        grow = _ease_out(age / 0.22)
        r = style.marker_radius * grow
        if r >= 0.5:
            draw.ellipse([x - r, y - r, x + r, y + r], fill=colour)

        if marker.pulse:
            # One ring per 1.6 s, expanding and fading. Rings are what make a marker
            # read as a live location instead of a printed dot.
            phase = (age % 1.6) / 1.6
            ring = style.marker_radius + phase * style.marker_radius * 3.2
            alpha = int(200 * (1 - phase))
            if alpha > 8:
                draw.ellipse(
                    [x - ring, y - ring, x + ring, y + ring],
                    outline=(*colour, alpha), width=2,
                )

        if marker.label and grow > 0.6:
            _draw_label(draw, marker.label, x, y, style, font, label_colour)


def _draw_label(draw, text: str, x: float, y: float, style: MapStyle,
                font, colour) -> None:
    """Place a marker's name beside it, flipping side rather than running off frame.

    Measured, not assumed: the label sits to the right by default, and moves to the
    left when the measured text box would cross the frame edge. Before this, a marker
    near the right edge — which is where the destination of a route usually ends up —
    had its name clipped mid-word.
    """
    gap = style.marker_radius + 6
    width, height = draw.im.size if hasattr(draw, "im") else (0, 0)
    try:
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        text_w, text_h = right - left, bottom - top
    except (AttributeError, TypeError):  # pragma: no cover - very old Pillow
        text_w, text_h = len(text) * 8, 12

    px = x + gap
    if width and px + text_w > width - 8:
        px = x - gap - text_w
    px = max(6.0, px)
    py = min(max(4.0, y - text_h / 2), (height - text_h - 4) if height else y)
    draw.text((px, py), text, font=font, fill=colour)


def _apply_vignette(image, amount: float):
    if amount <= 0:
        return image
    from PIL import Image, ImageDraw, ImageFilter

    width, height = image.size
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).ellipse(
        [-width * 0.18, -height * 0.28, width * 1.18, height * 1.28], fill=255
    )
    mask = mask.filter(ImageFilter.GaussianBlur(min(width, height) * 0.09))
    dark = Image.new("RGB", (width, height), (0, 0, 0))
    return Image.composite(image, Image.blend(image, dark, amount), mask)


def render_frame(spec: MapSpec, time: float):
    """One frame of the map, as a Pillow image. Exposed so tests can measure pixels."""
    from PIL import Image, ImageDraw

    style = spec.style
    image = Image.new("RGB", (spec.width, spec.height), _rgb(style.ocean))
    overlay = Image.new("RGBA", (spec.width, spec.height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw_rgba = ImageDraw.Draw(overlay)

    projection = Projection(spec.window_at(time), spec.width, spec.height)

    reveal = 1.0
    if style.reveal in {"wipe", "fade"}:
        reveal = _ease_in_out(time / max(spec.seconds * 0.28, 0.35))

    _draw_graticule(draw, projection, style)
    focus = spec.resolved_focus() if (spec.markers or spec.arcs) else None
    _draw_dots(draw, projection, style, reveal=reveal, focus=focus)
    _draw_arcs(draw, projection, style, spec.arcs, time)
    # Markers go on the RGBA layer because their pulse rings need real alpha; the
    # base image is RGB so the encoder never sees a stray alpha channel.
    #
    # Label size comes off the *smaller* side of the frame. Scaling by height put
    # 61px type on a 1080x1920 Short — big enough that two names collided and the
    # second ran off the edge.
    label_px = max(11, int(style.label_size_ratio * min(spec.width, spec.height)))
    _draw_markers(draw_rgba, projection, style, spec.markers, time, _font(label_px))

    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    return _apply_vignette(image, style.vignette)


def render_clip(spec: MapSpec, out_path: Path, *, timeout: float = 900.0) -> Path:
    """Render the whole animation to an mp4.

    Frames go to a temporary directory and are encoded in one ffmpeg pass. Piping raw
    frames to ffmpeg's stdin would avoid the disk write, but a PNG sequence is
    inspectable when a map comes out wrong — and a map coming out wrong is a geometry
    bug, which is exactly the kind you want to look at a frame of.
    """
    import tempfile

    out_path.parent.mkdir(parents=True, exist_ok=True)
    total = max(1, round(spec.seconds * spec.fps))

    with tempfile.TemporaryDirectory(prefix="forgecast-map-") as work:
        folder = Path(work)
        for index in range(total):
            frame = render_frame(spec, index / spec.fps)
            frame.save(folder / f"f{index:05d}.png")

        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-framerate", str(spec.fps),
            "-i", str(folder / "f%05d.png"),
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-r", str(spec.fps), str(out_path),
        ]
        proc = subprocess.run(command, capture_output=True, timeout=timeout)
        if proc.returncode != 0 or not out_path.exists():
            detail = (proc.stderr or b"").decode(errors="replace")[-500:]
            raise RuntimeError(f"map encode failed: {detail}")

    log.info("rendered map clip %s (%d frames, %.1fs)", out_path.name, total, spec.seconds)
    return out_path


def spec_from(
    places: list, *, seconds: float = 6.0, width: int = 1280, height: int = 720,
    fps: int = 30, style: str | MapStyle = "documentary_dark",
    connect: bool = True, labels: bool = True,
) -> MapSpec:
    """Build a sensible clip from a list of places.

    The staging is the part worth having: markers land in sequence rather than all at
    once, each arc starts as its destination lands, and the push-in finishes just
    before the last marker so the move and the reveal do not fight for attention.
    """
    resolved = [Marker.of(item, label=str(item) if labels and isinstance(item, str) else "")
                for item in places]
    if not resolved:
        return MapSpec(seconds=seconds, width=width, height=height, fps=fps,
                       style=MAP_LIBRARY[style] if isinstance(style, str) else style,
                       push_in=False)

    # Leave a beat at the front for the reveal, and a beat at the end to rest on.
    first = min(0.9, seconds * 0.18)
    last = max(first, seconds - 1.4)
    gap = 0.0 if len(resolved) == 1 else (last - first) / (len(resolved) - 1)
    for index, marker in enumerate(resolved):
        marker.at = first + index * gap

    arcs: list[Arc] = []
    if connect and len(resolved) > 1:
        for previous, nxt in itertools.pairwise(resolved):
            arcs.append(Arc(
                start=(previous.lat, previous.lon), end=(nxt.lat, nxt.lon),
                at=nxt.at - min(gap * 0.85, 1.4), duration=min(gap * 0.85, 1.4) or 0.8,
            ))

    chosen = MAP_LIBRARY[style] if isinstance(style, str) else style
    return MapSpec(
        seconds=seconds, width=width, height=height, fps=fps, style=chosen,
        markers=resolved, arcs=arcs, labels=labels,
        push_start=0.5, push_duration=max(1.2, last - 0.4),
    )


def available() -> list[dict]:
    """The map styles, for the CLI and the UI to list."""
    return [
        {"name": style.name, "ocean": style.ocean, "land": style.land,
         "marker": style.marker, "reveal": style.reveal}
        for style in MAP_LIBRARY.values()
    ]
