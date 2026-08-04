"""Reading a video somebody hands you, which this app could not do at all.

## What was missing

Forgecast generates. You give it a topic and it writes a brief, a script, a shot list
and a render. Every path in it runs in that direction, and there was no way in from the
other end: no probe, no transcript, no shot boundaries, no silence map. "Here is a video,
edit it" had nothing to attach to.

This package is that way in. It turns a file into measurements, and nothing else — it
makes no decisions, cuts nothing and writes no video. That separation is deliberate and
it is the same one `research` keeps: measuring is one job and deciding is another, and a
module that does both produces numbers you cannot argue with because you cannot see them.

## Everything here is measured, and says when it is not

Each reader returns its own confidence and its own failure. A machine with no
`scenedetect` still gets a probe and a silence map; a machine with no transcription model
still gets shots. What it must never do is guess — a shot list inferred from "probably
about every four seconds" looks exactly like a measured one and is worth nothing.

`read()` therefore returns partial results with `missing` naming what could not be read
and why, rather than raising. An edit built from three of the four available readings is
a worse edit; an edit that could not start at all is no edit.

## Why the heavy dependencies are optional

`faster-whisper` pulls a runtime and downloads a model; `scenedetect` pulls OpenCV, which
is 60 MB. Neither belongs in the base install of an app whose first run has to work on a
slow connection, and neither is needed by the generate direction at all. They are the
`edit` extra, and `available()` reports what is present so the UI can offer the install
rather than failing at the moment somebody drops a file in.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import probe, shots, silence, transcript
from .probe import Media
from .shots import Shot
from .silence import Quiet
from .transcript import Line, Word

log = logging.getLogger("forgecast.ingest")

__all__ = ["Ingest", "Line", "Media", "Quiet", "Shot", "Word", "available", "read"]


@dataclass
class Ingest:
    """One supplied video, measured. No decisions in here."""

    path: str
    media: Media
    shots: list[Shot] = field(default_factory=list)
    quiet: list[Quiet] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    # What could not be read, and why. Named rather than silently absent: an edit built
    # without a transcript is a different edit, and the operator has to be able to see
    # that it was built that way.
    missing: list[str] = field(default_factory=list)

    @property
    def speech_seconds(self) -> float:
        return round(sum(line.seconds for line in self.lines), 2)

    @property
    def quiet_seconds(self) -> float:
        return round(sum(item.seconds for item in self.quiet), 2)

    @property
    def shots_per_minute(self) -> float:
        """How fast the supplied video already cuts.

        The single most useful number about somebody else's edit, and the one
        `style.editing` already speaks in — so a reference read here is comparable with a
        style learned there without converting anything.
        """
        if not self.shots or self.media.duration <= 0:
            return 0.0
        return round(len(self.shots) / (self.media.duration / 60.0), 2)

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "media": asdict(self.media),
            "shots": [asdict(shot) for shot in self.shots],
            "quiet": [asdict(item) for item in self.quiet],
            "lines": [line.as_dict() for line in self.lines],
            "missing": list(self.missing),
            "speech_seconds": self.speech_seconds,
            "quiet_seconds": self.quiet_seconds,
            "shots_per_minute": self.shots_per_minute,
        }

    def summary(self) -> str:
        """One line an operator or the agent can read without opening the numbers."""
        parts = [f"{self.media.duration:.0f}s",
                 f"{self.media.width}x{self.media.height}",
                 f"{self.media.fps:.0f}fps"]
        if self.shots:
            parts.append(f"{len(self.shots)} shots ({self.shots_per_minute:.1f}/min)")
        if self.lines:
            parts.append(f"{len(self.lines)} lines of speech")
        if self.quiet:
            parts.append(f"{self.quiet_seconds:.0f}s quiet")
        if self.missing:
            parts.append("not read: " + "; ".join(self.missing))
        return " · ".join(parts)


def available() -> dict:
    """What this machine can currently measure, and the fix for what it cannot.

    Asked before a file is accepted rather than after. Dropping a video in and being
    told twenty seconds later that the transcription model is missing is the shape of
    failure this app keeps removing.
    """
    return {
        "probe": probe.available(),
        "shots": shots.available(),
        "silence": silence.available(),
        "transcript": transcript.available(),
    }


def read(path: Path | str, *, want_transcript: bool = True,
         want_shots: bool = True) -> Ingest:
    """Measure a supplied video. Never raises for a reading that cannot be taken.

    The probe is the exception — a file that cannot be probed is not a video, and there
    is nothing to degrade to. Everything after it is best-effort and named in `missing`.
    """
    target = Path(path)
    media = probe.read(target)          # raises: no probe means no video
    found = Ingest(path=str(target), media=media)

    if want_shots:
        ok, why = shots.available()
        if ok:
            try:
                found.shots = shots.read(target)
            except Exception as exc:                                  # pragma: no cover
                log.exception("shot detection failed")
                found.missing.append(f"shots ({type(exc).__name__}: {exc})")
        else:
            found.missing.append(f"shots ({why})")

    ok, why = silence.available()
    if ok:
        try:
            found.quiet = silence.read(target)
        except Exception as exc:                                      # pragma: no cover
            log.exception("silence detection failed")
            found.missing.append(f"silence ({type(exc).__name__}: {exc})")
    else:
        found.missing.append(f"silence ({why})")

    if want_transcript:
        ok, why = transcript.available()
        if ok:
            try:
                found.lines = transcript.read(target)
            except Exception as exc:                                  # pragma: no cover
                log.exception("transcription failed")
                found.missing.append(f"transcript ({type(exc).__name__}: {exc})")
        else:
            found.missing.append(f"transcript ({why})")

    return found
