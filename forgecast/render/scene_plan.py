"""The renderer-neutral description of an animated scene.

## Why this exists

There are now two ways to draw a motion scene: ffmpeg filtergraphs, and a browser
compositor. The temptation is to let each one grow its own idea of what a scene is,
and the result of that is a look that drifts — the same preset produces different
video depending on which engine ran, and nobody can say which is correct.

So neither engine defines the scene. This module does. A `ScenePlan` is plain data
built from a `MotionPreset` and a `MotionPlan`; `forgecast.motion.compose` compiles it
to a filtergraph, and the Remotion project renders it in React. The plan is the
contract, and `remotion/src/types.ts` mirrors it field for field.

## Two conventions, both deliberate

**Times are seconds, not frames.** A preset measured from a 24fps reference has to
drive a 30fps render without rewriting a single number.

**Positions are fractions of the frame, not pixels.** The same plan renders at
1280x720 and 1080x1920. A preset learned from a landscape reference is still usable on
a Short, which is the whole point of learning it.

## Every element here is type, and the card is why that is worth saying

A plan could describe a `card` — one still, centred and tilted with a shadow — until it
was removed here and in `remotion/src`. Three renderers drew one and no builder anywhere
emitted one, so no run could produce it; the reason was structural rather than a caller
somebody forgot to write. (The third renderer, the branch in `web/preview.html`, is now
unreachable and wants deleting with it.)

A plan describes one scene, and by the time one is built that scene's picture is already
a finished clip: `render.cutting` has subdivided the narration into shots and
`ffmpeg._build_scene_clip` has cut between a plate per shot. A card could therefore only
hold one still for a whole scene — and on the very format it was meant for, the
white-background explainer, that is the wrong number. `style.sourcing` measures that
channel as changing picture on nearly every cut, `plate_carry` consequently buys a plate
per shot, and a card would have hidden the four pictures the run just paid for behind one
of them.

The flat field that format wants is a property of the plate, not of a graphic laid over
one: `flat_background` and `background_colour` want reading where plates are commissioned
and where the colour bed is chosen. Neither is here. This layer draws type over a picture
it does not own, which is what every element below has in common.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..motion.presets import MotionPreset

SCHEMA_VERSION = "scene-plan/1"

# Matches the ffmpeg backend's caption geometry so the two agree.
_ZONES = {"bottom_third": 0.82, "centre": 0.5, "top_third": 0.16, "none": 0.82}


@dataclass
class TextItem:
    text: str
    start: float
    duration: float
    sizeRatio: float
    colour: str
    x: float
    y: float
    entry: str
    entryDuration: float
    exitDuration: float
    easing: str
    style: str
    bandOpacity: float
    kind: str = "text"


@dataclass
class BandItem:
    start: float
    duration: float
    colour: str
    opacity: float
    y: float
    widthFraction: float
    heightFraction: float
    kind: str = "band"


@dataclass
class Background:
    kind: str = "colour"                  # video | image | colour
    colour: str = "#101418"
    src: str | None = None


@dataclass
class ScenePlan:
    duration: float
    width: int = 1280
    height: int = 720
    fps: int = 30
    background: Background = field(default_factory=Background)
    elements: list = field(default_factory=list)
    presetName: str = "none"
    fontFamily: str = (
        'system-ui, -apple-system, "Segoe UI", Roboto, "DejaVu Sans", sans-serif'
    )

    def as_dict(self) -> dict:
        return {"schema_version": SCHEMA_VERSION, **asdict(self)}

    def to_props(self) -> str:
        """The `--props` payload for the Remotion CLI."""
        payload = asdict(self)
        payload["background"] = {
            key: value for key, value in payload["background"].items()
            if value is not None
        }
        return json.dumps({"plan": payload})

    def add(self, *items) -> ScenePlan:
        self.elements.extend(items)
        return self


def caption_items(
    preset: MotionPreset, text: str, *, start: float, duration: float,
    accent: bool = False,
) -> list:
    """A caption plus its backing, in plan form."""
    y = _ZONES.get(preset.caption_zone, 0.82)
    items: list = []
    if preset.caption_style == "band":
        items.append(BandItem(
            start=start, duration=duration, colour="#000000",
            opacity=preset.band_opacity, y=y - 0.07,
            widthFraction=1.0, heightFraction=0.15,
        ))
    items.append(TextItem(
        text=text, start=start, duration=duration,
        sizeRatio=preset.text_height_ratio,
        colour=preset.accent_colour if accent else preset.text_colour,
        x=0.5, y=y,
        entry=preset.entry,
        entryDuration=preset.entry_duration,
        exitDuration=preset.exit_duration,
        easing=preset.easing,
        style=preset.caption_style,
        bandOpacity=preset.band_opacity,
    ))
    return items


def plan_from(
    preset: MotionPreset,
    kind: str,
    lines: list[str],
    *,
    seconds: float,
    width: int,
    height: int,
    fps: int = 30,
    background: Path | None = None,
) -> ScenePlan:
    """Build a plan for one scene, using the same staging rules as the ffmpeg path.

    `background` is a path inside the directory the renderer will be pointed at; only
    its filename travels in the plan, because Remotion resolves assets relative to a
    public directory rather than by absolute path.
    """
    bed = Background(colour="#101418")
    if background is not None:
        suffix = background.suffix.lower()
        bed = Background(
            kind="image" if suffix in {".png", ".jpg", ".jpeg", ".webp"} else "video",
            colour="#000000",
            src=background.name,
        )

    plan = ScenePlan(
        duration=seconds, width=width, height=height, fps=fps,
        background=bed, presetName=preset.name,
    )

    if kind == "title" and lines:
        start = min(0.4, seconds * 0.15)
        plan.add(*caption_items(
            preset, lines[0], start=start,
            duration=min(seconds - start, preset.hold + preset.entry_duration),
            accent=True,
        ))
    elif kind == "lower_third" and lines:
        start = min(0.5, seconds * 0.2)
        span = min(seconds - start, preset.hold + 1.4)
        y = _ZONES.get(preset.caption_zone, 0.82)
        plan.add(BandItem(
            start=start, duration=span, colour="#000000",
            opacity=max(preset.band_opacity, 0.55), y=y - 0.06,
            widthFraction=1.0, heightFraction=0.19,
        ))
        plan.add(TextItem(
            text=lines[0], start=start, duration=span,
            sizeRatio=preset.text_height_ratio, colour=preset.accent_colour,
            x=0.5, y=y - 0.02, entry=preset.entry,
            entryDuration=preset.entry_duration, exitDuration=preset.exit_duration,
            easing=preset.easing, style="plain", bandOpacity=preset.band_opacity,
        ))
        if len(lines) > 1 and lines[1]:
            plan.add(TextItem(
                text=lines[1], start=start + preset.stagger,
                duration=max(0.4, span - preset.stagger),
                sizeRatio=preset.text_height_ratio * 0.62,
                colour=preset.text_colour, x=0.5, y=y + 0.06,
                entry=preset.entry, entryDuration=preset.entry_duration,
                exitDuration=preset.exit_duration, easing=preset.easing,
                style="plain", bandOpacity=preset.band_opacity,
            ))
    elif kind == "kinetic" and lines:
        step = max(0.6, (seconds - 0.3) / max(1, len(lines)))
        for index, line in enumerate(lines):
            plan.add(*caption_items(
                preset, line, start=0.2 + index * step, duration=step,
                accent=(index == len(lines) - 1 and len(lines) > 1),
            ))

    return plan
