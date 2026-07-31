"""Self-calibrating colour grade.

Builds a candidate `eq` filter, actually runs it over a handful of frames, measures
what came out, and corrects the residual. Two passes over ~40 downscaled frames costs
a fraction of a second and replaces "approximately the right direction" with a
measured match — which matters because the three eq controls interact and a
single-shot analytic grade reliably misses saturation.
"""

from __future__ import annotations

import logging
import subprocess

import numpy as np

from .apply import grade_transfer, refine_grade
from .probe import FFMPEG, VideoMeta
from .profile import RenderSpec
from .visual import ColourProfile, colour_profile

log = logging.getLogger("forgecast.vision.grade")

CALIBRATION_FRAMES = 40
CALIBRATION_WIDTH = 128


def _sample_with_filter(
    meta: VideoMeta, filter_string: str | None, *, frames: int = CALIBRATION_FRAMES
) -> np.ndarray:
    """Decode a thin, evenly spread sample, optionally through a filter."""
    fps = max(frames / max(meta.duration, 0.1), 0.1)
    height = max(2, round(CALIBRATION_WIDTH * meta.height / max(meta.width, 1)))
    height += height % 2

    chain = f"fps={fps:.6f},scale={CALIBRATION_WIDTH}:{height}"
    if filter_string:
        chain = f"{chain},{filter_string}"

    proc = subprocess.run(
        [FFMPEG, "-v", "error", "-i", str(meta.path), "-vf", chain,
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True,
        timeout=300,
    )
    frame_bytes = CALIBRATION_WIDTH * height * 3
    count = len(proc.stdout) // frame_bytes
    if count == 0:
        return np.zeros((0, height, CALIBRATION_WIDTH, 3), dtype=np.uint8)
    return np.frombuffer(
        proc.stdout[: count * frame_bytes], dtype=np.uint8
    ).reshape(count, height, CALIBRATION_WIDTH, 3)


def calibrate(
    meta: VideoMeta, spec: RenderSpec, *, passes: int = 2
) -> tuple[str, ColourProfile, ColourProfile]:
    """Return (filter, source colour, predicted result colour).

    `passes` is the number of *corrections*, not attempts. One is usually enough for
    brightness; the second is what pulls saturation back after the brightness lift.
    """
    source_frames = _sample_with_filter(meta, None)
    if source_frames.size == 0:
        return "", ColourProfile(0, 0, 0, 0, []), ColourProfile(0, 0, 0, 0, [])

    source = colour_profile(source_frames)
    filter_string = grade_transfer(
        source.brightness, source.contrast, source.saturation, spec
    )
    result = source

    for index in range(max(1, passes)):
        graded = _sample_with_filter(meta, filter_string)
        if graded.size == 0:
            break
        result = colour_profile(graded)
        log.info(
            "grade pass %d: %s -> brightness %.1f (target %.1f), saturation %.3f "
            "(target %.3f)",
            index + 1, filter_string, result.brightness, spec.target_brightness,
            result.saturation, spec.target_saturation,
        )
        close_enough = (
            abs(result.brightness - spec.target_brightness) < 4
            and abs(result.saturation - spec.target_saturation) < 0.03
        )
        if close_enough or index == passes - 1:
            break
        filter_string = refine_grade(
            filter_string, result.brightness, result.contrast, result.saturation, spec
        )

    return filter_string, source, result


__all__ = ["calibrate"]
