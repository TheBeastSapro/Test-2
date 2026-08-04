"""Where nobody is talking, which is where most of an edit's time is won.

Raw footage is mostly gaps. A talking head takes a breath, loses the thread, restarts
the sentence; a screen capture waits for a page to load. Cutting those out is the single
largest improvement available to a supplied video and it is entirely mechanical — no
taste is involved in removing two seconds of nothing.

## Measured by ffmpeg, not by a model

`silencedetect` is a filter that already ships, reads the actual waveform, and costs one
pass. A transcript-derived gap map would be a second-hand version of the same thing:
words have timings, but the space between two words is not the same as the absence of
sound, and it is the absence of sound the viewer hears.

## Why the thresholds are what they are

`-32 dB` rather than a lower floor because room tone in a real recording sits well above
silence, and a threshold tuned to a synthetic file removes nothing from a real one.
`0.35s` because shorter than that is the natural space between sentences — cutting it
produces the breathless, gapless rhythm that is the most recognisable sound of an
automatically edited video.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_NOISE_DB = -32.0
DEFAULT_MIN_SECONDS = 0.35
DETECT_TIMEOUT = 900

_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_END = re.compile(r"silence_end:\s*(-?[\d.]+)")


@dataclass
class Quiet:
    """One stretch with no speech in it."""

    start: float
    end: float

    @property
    def seconds(self) -> float:
        return round(max(0.0, self.end - self.start), 3)


def available() -> tuple[bool, str]:
    if not shutil.which("ffmpeg"):
        return False, "ffmpeg is not installed"
    return True, ""


def read(path: Path, *, noise_db: float = DEFAULT_NOISE_DB,
         min_seconds: float = DEFAULT_MIN_SECONDS) -> list[Quiet]:
    """Every silent stretch, in order.

    Returns an empty list for a file with no audio rather than raising — a silent
    screen capture has no silences to cut, which is a fact about it and not a failure.
    """
    ok, why = available()
    if not ok:                                                        # pragma: no cover
        raise RuntimeError(why)

    try:
        done = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
             "-af", f"silencedetect=noise={noise_db}dB:d={min_seconds}",
             "-f", "null", "-"],
            capture_output=True, text=True, errors="replace", timeout=DETECT_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:              # pragma: no cover
        raise RuntimeError(f"silence detection failed: {exc}") from exc

    # ffmpeg writes the filter's findings to stderr and exits 0. A non-zero exit here
    # means the file could not be decoded at all, which the probe would already have
    # caught — so it is reported rather than guessed at.
    text = done.stderr or ""
    if done.returncode != 0 and "silence_start" not in text:
        raise RuntimeError(f"ffmpeg could not read the audio: {text.strip()[-200:]}")

    found: list[Quiet] = []
    pending: float | None = None
    for line in text.splitlines():
        start = _START.search(line)
        if start:
            pending = float(start.group(1))
            continue
        end = _END.search(line)
        if end and pending is not None:
            found.append(Quiet(start=round(max(0.0, pending), 3),
                               end=round(float(end.group(1)), 3)))
            pending = None

    # A silence that runs to the end of the file has a start and no end, because the
    # filter never sees it stop. Dropped rather than invented: the caller knows the
    # duration and can decide what a trailing gap is worth, and a fabricated end
    # timestamp would be indistinguishable from a measured one.
    return [item for item in found if item.seconds > 0]
