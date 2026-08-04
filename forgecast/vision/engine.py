"""Orchestrator: reference in, StyleProfile out.

One decode pass for frames, one for scene scores, one for audio. Everything else is
numpy over what is already in memory, which is why a whole-video analysis costs
roughly the time of three sequential reads rather than one per metric.
"""

from __future__ import annotations

import logging
from pathlib import Path

from . import audio as audio_mod
from . import semantic as semantic_mod
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
    narrative: bool = False,
    source_meta: dict | None = None,
) -> StyleProfile:
    """Measure one video.

    `semantic` and `narrative` fill the same field and are not the same offer.
    `semantic` is the socket `profile.build` has always had: a block a vision provider
    describing shot subjects and on-screen text would supply, passed in from outside.
    Nothing in this tree has ever supplied one, which is how the profile came to print
    "no semantic pass" on every reference ever learned.

    `narrative=True` fills it from the reference's own audio instead — see
    `vision.semantic`, which needs no provider and no key. An explicitly supplied
    `semantic` still wins, because a caller that has a richer description of the video
    should not have it overwritten by the poorer one this can derive.

    Opt-in rather than always-on because it transcribes, which costs roughly the length
    of the reference and downloads a speech model on a machine's first use. The paths
    that re-measure a file to check an edit landed — `compare`, `restyle --verify` —
    have no use at all for what the file said, and making them pay for it would turn a
    verification into a wait.
    """
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

    if narrative and semantic is None:
        # Last, and after the audio pass on purpose: this is the only step that can
        # take minutes, and a caller that kills the run for being slow should still
        # have had every cheap measurement done before it got here.
        #
        # `measure` never raises. A reference that cannot be transcribed returns a
        # block saying which tool was missing — a learn that dies on the third of five
        # references leaves the operator with nothing.
        story = semantic_mod.measure(meta)
        semantic = story.as_dict()
        log.info("narrative: %s, %d sections, confidence %s",
                 "sectioned" if story.sectioned else "not sectioned",
                 len(story.sections), story.confidence)

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
