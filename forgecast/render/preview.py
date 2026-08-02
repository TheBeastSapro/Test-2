"""A playable timeline assembled from a run's parts, without rendering anything.

## The problem this solves

Rendering is the slowest and most expensive stage in the pipeline, and it is the only
stage that shows you what the video looks like. So the loop is: wait several minutes,
watch, notice the title is too long, change one word, wait several minutes again. The
feedback that decides the video's quality arrives after every decision that shapes it
has already been made.

Everything needed to *see* the video exists well before the render node runs. The
script has the narration, the shots node has the stills on disk, the voice node has
the audio, and the motion layer decides the graphics from those three. A browser can
composite that in real time. So it does.

## What this is not

It is not a render. It is the same `ScenePlan` the renderer consumes, handed to a
player instead of a compositor — the same contract that already keeps the ffmpeg and
Remotion backends honest, used a third way. Where the player and the renderer can
disagree they are listed in `divergences()` rather than hidden, because a preview that
quietly differs from the output is worse than no preview: it moves the surprise later
instead of removing it.

## Why not embed Remotion Studio

Remotion Studio would be a stronger preview — it is the real compositor, so there is
nothing to diverge. It also needs Node, an npm install, a bundler warm-up measured in
tens of seconds, and a licence that is not free for teams above three people. This
player needs a browser. Both are worth having, and `studio.py` runs the Remotion one
when a machine has Node; this is the one that always works.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..motion.presets import MotionPreset
from .scene_plan import ScenePlan, plan_from

log = logging.getLogger("forgecast.render.preview")

SCHEMA_VERSION = "preview-timeline/1"

# What the player does differently from the renderer. Stated rather than papered over.
DIVERGENCES = [
    "Type is laid out by the browser, so a long line wraps here and is drawn on one "
    "line by ffmpeg. The Remotion backend wraps the same way the preview does.",
    "The Ken Burns push on a still is applied by the renderer, not previewed — a "
    "still holds still here.",
    "Loudness mastering and music ducking happen at render time; the preview plays "
    "the raw voice track.",
    "Burned-in captions are added by the renderer. The preview shows the motion "
    "graphics only.",
]


@dataclass
class PreviewScene:
    """One scene, positioned on the run's timeline."""

    index: int
    start: float
    seconds: float
    narration: str
    plan: dict
    audio_url: str | None = None
    background_url: str | None = None
    background_kind: str = "colour"
    motion_kind: str = "none"
    note: str = ""


@dataclass
class PreviewTimeline:
    duration: float
    width: int
    height: int
    fps: int
    scenes: list[PreviewScene] = field(default_factory=list)
    narration_url: str | None = None
    preset_name: str = ""
    ready: bool = False
    missing: list[str] = field(default_factory=list)
    divergences: list[str] = field(default_factory=lambda: list(DIVERGENCES))

    def as_dict(self) -> dict:
        payload = asdict(self)
        payload["schema_version"] = SCHEMA_VERSION
        return payload


def _url_or_none(path_value, url_for: Callable[[Path], str | None]) -> tuple[str | None, Path | None]:
    """Resolve a recorded path to a servable URL, tolerating every way it can be absent.

    Node outputs carry paths as strings, and a path can be missing, empty, or point at
    a file that has since been deleted. All three mean the same thing to a preview —
    show the colour bed — so they collapse here rather than at four call sites.
    """
    if not path_value:
        return None, None
    path = Path(str(path_value))
    if not path.exists():
        return None, None
    return url_for(path), path


def build(
    *,
    script: dict,
    shots: dict | None,
    voice: dict | None,
    width: int,
    height: int,
    preset: MotionPreset | None,
    motion_plans: list | None,
    url_for: Callable[[Path], str | None],
    fps: int = 30,
) -> PreviewTimeline:
    """Assemble a playable timeline from whatever stages have finished.

    Deliberately tolerant. A run that has a script but no voice yet is still worth
    previewing — the timing comes from the script's own estimates and the player runs
    silently. Each absent stage is named in `missing` so the UI can say what the
    preview is not yet showing, rather than presenting a partial video as the whole
    thing.
    """
    timeline = PreviewTimeline(
        duration=0.0, width=width, height=height, fps=fps,
        preset_name=preset.name if preset else "",
    )

    entries = list(script.get("scenes") or [])
    if not entries:
        timeline.missing.append("script")
        return timeline

    shot_by_index = {
        int(item["scene_index"]): item
        for item in ((shots or {}).get("shots") or [])
        if item.get("scene_index") is not None
    }
    segment_by_index = {
        int(item["scene_index"]): item
        for item in ((voice or {}).get("segments") or [])
        if item.get("scene_index") is not None
    }
    plan_by_index = {
        int(item.scene_index): item for item in (motion_plans or [])
    }

    if not shot_by_index:
        timeline.missing.append("visuals")
    if not segment_by_index:
        timeline.missing.append("voice")

    narration_url, _ = _url_or_none((voice or {}).get("narration_path"), url_for)
    timeline.narration_url = narration_url

    cursor = 0.0
    for entry in entries:
        index = int(entry["index"])
        segment = segment_by_index.get(index) or {}
        # The narration decides the cut, exactly as it does at render time; falling
        # back to the script's estimate keeps a pre-voice preview correctly paced.
        seconds = float(segment.get("seconds") or entry.get("seconds") or 4.0)

        shot = shot_by_index.get(index) or {}
        background_url, background_path = _url_or_none(shot.get("path"), url_for)
        audio_url, _ = _url_or_none(segment.get("path"), url_for)

        item = plan_by_index.get(index)
        if preset is not None and item is not None and item.active and item.lines:
            plan = plan_from(
                preset, item.kind, list(item.lines), seconds=seconds,
                width=width, height=height, fps=fps, background=background_path,
            )
        else:
            plan = ScenePlan(duration=seconds, width=width, height=height, fps=fps)

        # `plan_from` records only a filename, because Remotion resolves assets against
        # a public directory. A browser needs a URL it can actually fetch.
        plan.background.src = background_url
        if background_url:
            suffix = (background_path.suffix.lower() if background_path else "")
            plan.background.kind = (
                "image" if suffix in {".png", ".jpg", ".jpeg", ".webp"} else "video"
            )
        else:
            plan.background.kind = "colour"

        timeline.scenes.append(PreviewScene(
            index=index,
            start=round(cursor, 3),
            seconds=round(seconds, 3),
            narration=entry.get("narration", ""),
            plan=plan.as_dict(),
            audio_url=audio_url,
            background_url=background_url,
            background_kind=plan.background.kind,
            motion_kind=item.kind if item is not None else "none",
            note=item.reason if item is not None else "",
        ))
        cursor += seconds

    timeline.duration = round(cursor, 3)
    timeline.ready = not timeline.missing
    return timeline
