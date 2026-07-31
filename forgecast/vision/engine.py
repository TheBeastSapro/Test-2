"""Orchestrator: reference in, StyleProfile out.

One decode pass for frames, one for scene scores, one for audio. Everything else is
numpy over what is already in memory, which is why a whole-video analysis costs
roughly the time of three sequential reads rather than one per metric.
"""

from __future__ import annotations

import logging
from pathlib import Path

from . import audio as audio_mod
from . import shots as shots_mod
from . import visual as visual_mod
from .acquire import Acquired, acquire
from .probe import VideoMeta, probe
from .profile import StyleProfile, build

log = logging.getLogger("forgecast.vision")


def analyse_file(
    path: str | Path,
    *,
    sample_fps: float = visual_mod.SAMPLE_FPS,
    max_frames: int = visual_mod.MAX_FRAMES,
    semantic: dict | None = None,
    source_meta: dict | None = None,
) -> StyleProfile:
    meta: VideoMeta = probe(path)
    log.info("analysing %s (%.1fs, %dx%d)", meta.path.name, meta.duration,
             meta.width, meta.height)

    shot_analysis = shots_mod.detect(meta)
    log.info("detected %d shots (threshold %.1f)", len(shot_analysis.shots),
             shot_analysis.threshold)

    frames = visual_mod.sample(meta, fps=sample_fps, max_frames=max_frames)
    log.info("sampled %d frames at %.2f fps", len(frames), frames.fps)

    whole_colour = visual_mod.colour_profile(frames.frames)
    overlay = visual_mod.overlay_profile(frames.frames)

    per_shot: list[dict] = []
    for shot in shot_analysis.shots:
        window = frames.between(shot.start, shot.end)
        if len(window) == 0:
            # Shot shorter than the sampling interval: take the nearest frame so the
            # shot still contributes a colour reading rather than vanishing.
            nearest = int(min(max(shot.start * frames.fps, 0), len(frames) - 1))
            window = frames.frames[nearest: nearest + 1]
        entry = shot.as_dict()
        entry["colour"] = visual_mod.colour_profile(window, palette_size=3).as_dict()
        entry["motion"] = visual_mod.motion_profile(window).as_dict()
        per_shot.append(entry)

    audio_analysis = audio_mod.analyse(meta)
    alignment = audio_mod.beat_alignment(
        [boundary.time for boundary in shot_analysis.boundaries], audio_analysis
    )

    profile = build(
        meta, shot_analysis, whole_colour, per_shot, overlay,
        audio_analysis, alignment, semantic=semantic,
    )
    if source_meta:
        profile.source.update(source_meta)
    return profile


def analyse_reference(
    reference: str,
    workdir: str | Path,
    *,
    max_seconds: float | None = None,
    **kwargs,
) -> tuple[StyleProfile, Acquired]:
    """Acquire (local path, direct URL, or platform URL) then analyse."""
    workdir = Path(workdir)
    acquired = acquire(reference, workdir, max_seconds=max_seconds)
    profile = analyse_file(acquired.path, source_meta=acquired.as_dict(), **kwargs)
    return profile, acquired
