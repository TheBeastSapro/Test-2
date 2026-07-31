"""Shot boundary detection and edit rhythm.

The shot list is the spine of every other measurement: colour, motion and
cut-to-beat all describe shots or boundaries. Getting it right matters more than
any single downstream metric.

We take the full per-frame scene-change score from ffmpeg's `scdet` rather than
letting ffmpeg threshold for us. Having the whole curve is what lets us separate a
hard cut (one isolated spike) from a dissolve (a run of moderate scores across
several frames) — a distinction that is invisible if you only get the timestamps
back, and one that materially changes how you'd replicate the edit.

**Known blind spot.** `scdet` scores mean absolute *luma* difference, so a cut is
faint whenever brightness barely changes across it, however different the colours
are. Measured on flat colour fields: an 8-level luma step scores ~2.7 and is missed,
21 levels scores ~7 and is caught, and a navy-to-dark-red cut scores ~10 despite
being a total hue change. The floor stays at 4.0 rather than chasing the 2.7 case,
because on real footage a threshold that low cannot tell compression noise from an
edit. In practice this costs you cuts between two similarly-lit shots — worth
knowing when a shot count looks lower than expected, which is why the chosen
threshold is reported in the output.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from .probe import FFMPEG, ProbeError, VideoMeta, run

# Thresholding is adaptive, and it has to be. A fixed cutoff fails in both
# directions: a navy-to-red cut scores only ~10 because those colours have similar
# luma, while a single handheld shot can push 5-8 every frame without any edit at
# all. So an edit is defined relative to *this video's own* inter-frame noise, with
# an absolute floor so a static screencast (noise ~0) does not turn every
# compression artefact into a cut.
#
# threshold = max(ABSOLUTE_FLOOR, p75(scores) * NOISE_MULTIPLE)
#
# The percentile is 75, not 95, and that is a bug fix rather than a preference. A
# noise floor taken at p95 assumes cut frames are rarer than 5% of all frames — true
# for a 12 cuts/min documentary, false for exactly the fast-cut content this tool
# exists to analyse. Measured on a 12-cut, 8-second clip at 25fps: cut frames are
# 5.4% of the total, so p95 landed *on a cut score* (7.3), the threshold became 43.8,
# and 9 of 11 cuts were silently dropped. p75 tolerates a cut rate up to 25% — about
# 6 cuts per second — which no real edit reaches.
ABSOLUTE_FLOOR = 4.0
NOISE_MULTIPLE = 6.0
NOISE_PERCENTILE = 75
# A boundary spanning more than this many frames is a dissolve, not a cut.
MAX_CUT_FRAMES = 2
# Two boundaries closer than this are one event seen twice (common on dissolves).
MIN_SHOT_SECONDS = 0.30

_SCORE_RE = re.compile(r"lavfi\.scd\.score=([0-9.]+)")
_TIME_RE = re.compile(r"pts_time:([0-9.]+)")


@dataclass
class Boundary:
    time: float
    score: float
    kind: str  # "cut" | "dissolve"


@dataclass
class Shot:
    index: int
    start: float
    end: float
    entry: str = "cut"   # how this shot was entered
    exit: str = "cut"    # how it was left

    @property
    def duration(self) -> float:
        return max(self.end - self.start, 0.0)

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration, 3),
            "entry": self.entry,
            "exit": self.exit,
        }


@dataclass
class ShotAnalysis:
    shots: list[Shot]
    boundaries: list[Boundary]
    threshold: float = 0.0
    noise_floor: float = 0.0
    score_curve: list[tuple[float, float]] = field(default_factory=list, repr=False)

    # -- rhythm ---------------------------------------------------------------

    @property
    def durations(self) -> list[float]:
        return [shot.duration for shot in self.shots]

    def cuts_per_minute(self, duration: float) -> float:
        if duration <= 0:
            return 0.0
        return len(self.boundaries) / (duration / 60)

    def regularity(self) -> float | None:
        """Coefficient of variation of shot length, inverted into 0-1 regularity.

        1.0 is metronomic, 0 is wildly varied. This separates a rhythm-locked
        montage from a documentary that holds some shots and races through others —
        the two feel completely different and have the same cuts-per-minute.
        """
        durations = [d for d in self.durations if d > 0]
        if len(durations) < 3:
            return None
        mean = statistics.fmean(durations)
        if mean <= 0:
            return None
        cv = statistics.stdev(durations) / mean
        return round(max(0.0, 1.0 - min(cv, 1.0)), 3)

    def pacing_trend(self) -> str:
        """Does the edit accelerate, decelerate, or hold?

        Compare mean shot length in the first third against the last third. An
        accelerating edit is a deliberate retention technique; a decelerating one
        usually means the payoff is at the end.
        """
        durations = self.durations
        if len(durations) < 6:
            return "insufficient_shots"
        third = max(len(durations) // 3, 1)
        head = statistics.fmean(durations[:third])
        tail = statistics.fmean(durations[-third:])
        if head <= 0:
            return "unknown"
        change = (tail - head) / head
        if change < -0.25:
            return "accelerating"
        if change > 0.25:
            return "decelerating"
        return "steady"

    def as_dict(self, duration: float) -> dict:
        durations = [d for d in self.durations if d > 0]
        return {
            "shot_count": len(self.shots),
            "boundary_count": len(self.boundaries),
            # Reported so a surprising shot count can be audited rather than trusted.
            "detection": {
                "threshold": round(self.threshold, 3),
                "noise_floor_p95": round(self.noise_floor, 3),
            },
            "cuts_per_minute": round(self.cuts_per_minute(duration), 2),
            "shot_length": {
                "mean": round(statistics.fmean(durations), 3) if durations else None,
                "median": round(statistics.median(durations), 3) if durations else None,
                "min": round(min(durations), 3) if durations else None,
                "max": round(max(durations), 3) if durations else None,
                "stdev": (
                    round(statistics.stdev(durations), 3) if len(durations) > 1 else None
                ),
            },
            "regularity": self.regularity(),
            "pacing_trend": self.pacing_trend(),
            "transition_mix": self.transition_mix(),
            "shots": [shot.as_dict() for shot in self.shots],
        }

    def transition_mix(self) -> dict:
        counts = {"cut": 0, "dissolve": 0}
        for boundary in self.boundaries:
            counts[boundary.kind] = counts.get(boundary.kind, 0) + 1
        total = sum(counts.values()) or 1
        return {kind: round(count / total, 3) for kind, count in counts.items()}


def score_curve(meta: VideoMeta, *, timeout: float = 900.0) -> list[tuple[float, float]]:
    """Per-frame (time, scene_change_score) for the whole video."""
    proc = run(
        [
            FFMPEG, "-hide_banner", "-nostats", "-i", str(meta.path),
            # threshold=0 so every frame is reported and we threshold ourselves.
            "-vf", "scdet=threshold=0,metadata=print:file=-",
            "-f", "null", "-",
        ],
        label="scdet",
        timeout=timeout,
    )
    text = proc.stdout.decode(errors="replace")
    if not text:
        text = proc.stderr.decode(errors="replace")

    curve: list[tuple[float, float]] = []
    pending_time: float | None = None
    for line in text.splitlines():
        time_match = _TIME_RE.search(line)
        if time_match:
            pending_time = float(time_match.group(1))
            continue
        score_match = _SCORE_RE.search(line)
        if score_match and pending_time is not None:
            curve.append((pending_time, float(score_match.group(1))))
            pending_time = None

    if not curve:
        raise ProbeError(
            "scdet produced no scores — the file may have a single frame or an "
            "unreadable video stream"
        )
    return curve


def adaptive_threshold(
    scores: list[float],
    *,
    floor: float = ABSOLUTE_FLOOR,
    multiple: float = NOISE_MULTIPLE,
    percentile: int = NOISE_PERCENTILE,
) -> tuple[float, float]:
    """Return (threshold, noise_floor) for this video's score distribution."""
    if not scores:
        return floor, 0.0
    ordered = sorted(scores)
    index = min(len(ordered) - 1, int(len(ordered) * percentile / 100))
    noise = ordered[index]
    return max(floor, noise * multiple), noise


def detect(
    meta: VideoMeta,
    *,
    floor: float = ABSOLUTE_FLOOR,
    multiple: float = NOISE_MULTIPLE,
    min_shot: float = MIN_SHOT_SECONDS,
    curve: list[tuple[float, float]] | None = None,
) -> ShotAnalysis:
    curve = curve if curve is not None else score_curve(meta)
    threshold, noise = adaptive_threshold(
        [score for _, score in curve], floor=floor, multiple=multiple
    )

    # Group consecutive above-threshold frames into one event, then let run length
    # separate a cut from a dissolve: a cut is over in a frame or two, a dissolve
    # smears the change across many.
    events: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for time, score in curve:
        if score >= threshold:
            current.append((time, score))
        elif current:
            events.append(current)
            current = []
    if current:
        events.append(current)

    boundaries: list[Boundary] = []
    for run_frames in events:
        peak_time, peak_score = max(run_frames, key=lambda item: item[1])
        kind = "cut" if len(run_frames) <= MAX_CUT_FRAMES else "dissolve"
        if peak_time < min_shot:
            # scdet scores the first frame against no predecessor, so any clip that
            # opens on busy or bright content reports a cut at frame 1 — measured at
            # t=0.04 on grain, high-motion and strobing fixtures alike. The start of
            # a video is already a shot start; counting it again inflates the shot
            # count and leaves a zero-length shot at the head.
            continue
        if boundaries and peak_time - boundaries[-1].time < min_shot:
            # Same event detected twice; keep the stronger reading.
            if peak_score > boundaries[-1].score:
                boundaries[-1] = Boundary(peak_time, peak_score, kind)
            continue
        boundaries.append(Boundary(peak_time, peak_score, kind))

    shots: list[Shot] = []
    edges = [0.0] + [b.time for b in boundaries] + [meta.duration]
    for index in range(len(edges) - 1):
        start, end = edges[index], edges[index + 1]
        if end - start < min_shot and index not in (0, len(edges) - 2):
            continue
        entry = boundaries[index - 1].kind if index > 0 and index - 1 < len(boundaries) else "start"
        exit_kind = boundaries[index].kind if index < len(boundaries) else "end"
        shots.append(Shot(index=len(shots), start=start, end=end, entry=entry, exit=exit_kind))

    return ShotAnalysis(
        shots=shots,
        boundaries=boundaries,
        threshold=threshold,
        noise_floor=noise,
        score_curve=curve,
    )
