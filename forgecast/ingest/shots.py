"""Where the supplied video already cuts.

Two things need this. Re-editing footage has to know which cuts were deliberate so it
does not cut across one — a new cut two frames after an existing one reads as a glitch,
not as pace. And reading a video as a *reference* needs its cutting rate, which is the
number `style.editing` speaks in, so a measurement here is directly comparable with a
style learned there.

## Content detection, not threshold detection

`ContentDetector` compares successive frames in HSV and fires on change. The alternative,
`ThresholdDetector`, fires on fades to black — which finds chapter breaks in a film and
almost nothing in the kind of footage this app is handed, where cuts are hard and the
picture never goes dark.

## Why it downscales before looking

Shot detection at 4K costs minutes and finds exactly the same cuts it finds at 480p: a
cut is a global change, and nothing about it lives in the detail. `downscale` is the
difference between a reading that happens while somebody waits and one they abandon.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Below this, a "shot" is a decode artefact or a flash frame rather than a cut somebody
# made. Merged into its neighbour instead of being reported as its own shot.
MIN_SHOT_SECONDS = 0.4

# How hard a frame-to-frame change has to be. 27 is the library's own default and is
# tuned for exactly this: hard cuts in ordinary footage, without firing on a fast pan.
THRESHOLD = 27.0


@dataclass
class Shot:
    """One continuous take in the supplied video."""

    index: int
    start: float
    end: float

    @property
    def seconds(self) -> float:
        return round(max(0.0, self.end - self.start), 3)


def available() -> tuple[bool, str]:
    try:
        import scenedetect  # noqa: F401
    except ImportError:
        # Names the fix rather than the missing import, and the fix is a button rather
        # than a command: this app installs its own tooling, so an operator told to run
        # `pip install scenedetect` has been handed the maintainer's job. Setup lists
        # this exact row.
        return False, "shot detection needs Video editing tools — install them in Setup"
    return True, ""


def read(path: Path, *, threshold: float = THRESHOLD,
         min_seconds: float = MIN_SHOT_SECONDS) -> list[Shot]:
    """Every shot boundary, as spans rather than as cut points.

    Spans because that is what a caller needs. A list of timestamps makes every consumer
    do the same pairing, and the one that gets it wrong is off by one shot for the whole
    video.
    """
    ok, why = available()
    if not ok:                                                        # pragma: no cover
        raise RuntimeError(why)

    from scenedetect import ContentDetector, detect

    scenes = detect(str(path), ContentDetector(threshold=threshold),
                    show_progress=False)

    spans: list[tuple[float, float]] = [
        (round(start.get_seconds(), 3), round(end.get_seconds(), 3))
        for start, end in scenes
    ]
    if not spans:
        return []

    # Flash frames merged into what came before them. A 3-frame "shot" is not a shot
    # anybody cut, and left in the list it makes the cutting rate meaningless.
    merged: list[list[float]] = [list(spans[0])]
    for start, end in spans[1:]:
        if end - start < min_seconds:
            merged[-1][1] = end
        else:
            merged.append([start, end])

    return [Shot(index=index, start=start, end=end)
            for index, (start, end) in enumerate(merged)]
