"""Loudness measurement, normalisation, and ducking.

## The defect this fixes

Until now `mux()` took whatever level the voice provider happened to return and
shipped it. ElevenLabs, a mock tone and a Kokoro render do not agree on level to
within 10 dB, so one video played quiet, the next played hot, and a music bed would
have buried the narration entirely. Nothing measured it, so nothing caught it.

## Why measurement rather than a gain slider

Loudness is not peak amplitude. A compressed voice track and a sparse piano bed can
share a peak and differ by 12 LU in perceived level, which is why every platform
normalises on EBU R128 integrated loudness and not on peaks. ffmpeg implements R128
in `loudnorm`, and — importantly — it will *report* the measurement as JSON. So the
target is checkable: normalise, measure the output, assert it landed. That is the same
discipline as the rest of this codebase, applied to the one stage that had none.

## Two passes, not one

Single-pass `loudnorm` works from a running estimate and typically lands 1-3 LU off
target, which is audible. Two-pass measures the whole file first and feeds the real
numbers back in, landing inside ~0.5 LU. The cost is one extra decode of an audio
stream — cheap next to a video encode, and the difference between "about right" and
"correct".

## On the target number

Platforms normalise loud uploads *down* on playback. Mixing hotter than the platform
target does not make a video louder for the viewer; it makes it quieter after
normalisation, with the dynamics already squashed. -14 LUFS is the widely used
streaming target and the default here. Verify against current platform documentation
before treating any specific number as authoritative — these move.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from .ffmpeg import FFMPEG, RenderError, run_ffmpeg

log = logging.getLogger("forgecast.render.audio")

# Integrated loudness targets in LUFS, and true-peak ceilings in dBFS.
PLATFORM_TARGETS: dict[str, tuple[float, float]] = {
    "youtube": (-14.0, -1.0),
    "shorts": (-14.0, -1.0),
    "tiktok": (-14.0, -1.0),
    "broadcast": (-23.0, -1.0),      # EBU R128 proper, for anything going to air
    "archive": (0.0, 0.0),           # sentinel: no normalisation at all
}

# How far the music sits under the narration while it is speaking. Deep enough that
# consonants survive, shallow enough that the bed does not audibly disappear.
DEFAULT_DUCK_DB = 10.0


@dataclass
class Loudness:
    """An EBU R128 measurement of one file."""

    integrated_lufs: float
    true_peak_dbfs: float
    range_lu: float
    threshold_lufs: float

    @property
    def silent(self) -> bool:
        # loudnorm reports -inf (serialised as a very negative number) for silence.
        return self.integrated_lufs < -70.0

    def as_dict(self) -> dict:
        return {
            "integrated_lufs": round(self.integrated_lufs, 2),
            "true_peak_dbfs": round(self.true_peak_dbfs, 2),
            "range_lu": round(self.range_lu, 2),
            "silent": self.silent,
        }


def _to_float(value: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return -99.0
    # loudnorm emits "-inf" for a silent input; json.loads gives back -Infinity,
    # which then poisons every arithmetic comparison downstream.
    return -99.0 if number != number or number == float("-inf") else number


def _probe(cmd: list[str], *, label: str, timeout: float = 900.0):
    """Run ffmpeg and hand back stderr, which is where loudnorm writes its JSON."""
    import subprocess

    proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if proc.returncode != 0 and b"input_i" not in (proc.stderr or b""):
        detail = (proc.stderr or b"").decode(errors="replace")[-500:]
        raise RenderError(f"{label} failed: {detail}")
    return proc


def measure(path: Path, *, timeout: float = 600.0) -> Loudness:
    """Measure a file's integrated loudness without modifying it."""
    proc = _probe(
        [FFMPEG, "-hide_banner", "-nostats", "-i", str(path),
         "-af", "loudnorm=print_format=json", "-f", "null", "-"],
        label="loudness measure", timeout=timeout,
    )
    text = (proc.stderr or b"").decode(errors="replace")

    # The JSON block is the last thing loudnorm writes to stderr, after the log.
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", text, re.DOTALL)
    if not match:
        raise RenderError(f"could not measure loudness of {path.name}")
    payload = json.loads(match.group(0))

    return Loudness(
        integrated_lufs=_to_float(payload.get("input_i")),
        true_peak_dbfs=_to_float(payload.get("input_tp")),
        range_lu=_to_float(payload.get("input_lra")),
        threshold_lufs=_to_float(payload.get("input_thresh")),
    )


def normalise(
    src: Path,
    out_path: Path,
    *,
    platform: str = "youtube",
    target_lufs: float | None = None,
    true_peak: float | None = None,
    timeout: float = 900.0,
) -> Loudness:
    """Two-pass loudness normalisation. Returns the measurement of the *output*.

    Returning the output measurement rather than nothing is deliberate: the caller
    can assert the result landed on target, which is the only way to know the stage
    did anything at all.
    """
    default_target, default_peak = PLATFORM_TARGETS.get(
        platform, PLATFORM_TARGETS["youtube"]
    )
    target = default_target if target_lufs is None else target_lufs
    peak = default_peak if true_peak is None else true_peak

    measured = measure(src, timeout=timeout)
    if measured.silent:
        # Normalising silence amplifies the noise floor into a hiss. Copy instead.
        log.warning("%s is silent; copying without normalisation", src.name)
        run_ffmpeg(["-i", str(src), "-c", "copy", str(out_path)], label="copy silent")
        return measured

    # Pass two: hand loudnorm the real measurements so it can compute one exact
    # correction instead of tracking an estimate as it goes.
    settings = (
        f"loudnorm=I={target}:TP={peak}:LRA=11"
        f":measured_I={measured.integrated_lufs}"
        f":measured_TP={measured.true_peak_dbfs}"
        f":measured_LRA={measured.range_lu}"
        f":measured_thresh={measured.threshold_lufs}"
        ":linear=true:print_format=summary"
    )
    run_ffmpeg(
        ["-i", str(src), "-af", settings, "-ar", "48000", "-c:a", "aac",
         "-b:a", "320k", str(out_path)],
        label="loudnorm",
    )
    return measure(out_path, timeout=timeout)


def normalise_video_audio(
    src: Path, out_path: Path, *, platform: str = "youtube",
    timeout: float = 900.0,
) -> Loudness | None:
    """Normalise the audio of a video without re-encoding the video.

    `-c:v copy` is the point: a loudness pass that re-encodes the picture costs
    minutes and loses a generation of quality for no reason.
    """
    if platform == "archive":
        return None

    target, peak = PLATFORM_TARGETS.get(platform, PLATFORM_TARGETS["youtube"])
    measured = measure(src, timeout=timeout)
    if measured.silent:
        log.warning("%s has no measurable audio; leaving it alone", src.name)
        return measured

    settings = (
        f"loudnorm=I={target}:TP={peak}:LRA=11"
        f":measured_I={measured.integrated_lufs}"
        f":measured_TP={measured.true_peak_dbfs}"
        f":measured_LRA={measured.range_lu}"
        f":measured_thresh={measured.threshold_lufs}"
        ":linear=true"
    )
    run_ffmpeg(
        ["-i", str(src), "-af", settings, "-c:v", "copy",
         "-c:a", "aac", "-b:a", "320k", "-ar", "48000", str(out_path)],
        label="loudnorm video",
    )
    return measure(out_path, timeout=timeout)


def duck_under(
    voice: Path,
    music: Path,
    out_path: Path,
    *,
    depth_db: float = DEFAULT_DUCK_DB,
    music_gain_db: float = -8.0,
    timeout: float = 900.0,
) -> Path:
    """Mix music under narration, ducking the bed whenever the voice speaks.

    `sidechaincompress` is real ducking: the voice drives a compressor on the music,
    so the bed drops on speech and rides back up in the gaps. A static gain cut can
    only be wrong in one of two directions — too quiet under the pauses, or too loud
    under the words.

    The release is long (250 ms) on purpose. A fast release pumps audibly between
    words, which is the sound of an amateur mix even when every level is correct.
    """
    ratio = max(1.5, min(20.0, depth_db / 2.0))
    graph = (
        f"[1:a]volume={music_gain_db}dB[bed];"
        f"[0:a]asplit=2[voice][key];"
        f"[bed][key]sidechaincompress="
        f"threshold=0.05:ratio={ratio:.2f}:attack=10:release=250:makeup=1[ducked];"
        f"[voice][ducked]amix=inputs=2:duration=first:dropout_transition=0"
        f":normalize=0[out]"
    )
    run_ffmpeg(
        ["-i", str(voice), "-i", str(music), "-filter_complex", graph,
         "-map", "[out]", "-c:a", "aac", "-b:a", "320k", "-ar", "48000",
         str(out_path)],
        label="duck music under voice",
    )
    return out_path


def loop_to_length(src: Path, out_path: Path, seconds: float) -> Path:
    """Loop a music bed to cover a duration, then cut it exactly.

    `-t` is an *output* option here and `-stream_loop` bounds the input. An unbounded
    loop with no duration cap produces a stream that never ends — ffmpeg encodes
    until something kills it. Every looped input in this codebase carries a cap for
    that reason.
    """
    run_ffmpeg(
        ["-stream_loop", "-1", "-i", str(src), "-t", f"{max(seconds, 0.1):.3f}",
         "-af", "afade=t=out:st=" + f"{max(seconds - 2.0, 0.0):.3f}" + ":d=2",
         "-c:a", "aac", "-b:a", "320k", "-ar", "48000", str(out_path)],
        label="loop music bed",
    )
    return out_path
