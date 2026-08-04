"""Applying a StyleProfile — the other half of "adapt this editing style".

## The tension this module resolves

The render pipeline cuts on **narration**: a scene lasts as long as its voiceover
line. A style profile says something different — "median shot 1.0s". Those two
numbers disagree, and naively obeying the profile would truncate the voiceover.

The resolution is the distinction a working editor already makes: a **scene** is a
narration beat, a **shot** is a visual. One 8-second scene can hold eight 1-second
shots. The voiceover is fixed; the visual cutting rate is a style choice made on top
of it. So applying a style means *subdividing* scenes into shots at the reference's
rhythm, never rewriting scene lengths.

That is also why a punch-in counts. When a scene has one plate and the style wants
four cuts, cutting between progressively tighter crops of that plate is a real
technique, not a workaround — it is how a single camera angle becomes four shots.

Everything here is pure and deterministic: same profile and same duration produce
the same plan, so a render is reproducible and a diff is meaningful.

There was also a `render_kwargs(spec)` here that packed grade, captions, Ken Burns,
zoom rate and transition into a dict "the renderer takes directly". It never had a
caller and it could not have had one: no function in `render.ffmpeg` accepts those
names together, so it could not be splatted into anything. The settings reach the
renderer through the profile instead — `style.editing.to_render_spec` writes them into
`channel.style_profile["render_spec"]` and `render.cutting.spec_for` reads them back —
which that method's own docstring names as the single path, on the grounds that a second
one would mean two places deciding how a video is cut. This was that second place.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field

from .profile import RenderSpec

MIN_SHOT = 0.35          # below this a cut reads as a glitch rather than an edit
SNAP_WINDOW = 0.45       # fraction of target length a cut may move to reach a beat

# Punch-in levels for successive shots inside a scene. They ALTERNATE between two
# clearly separated levels rather than creeping upward, because a reframe has to
# clear a size threshold before it registers as a cut at all. Measured on continuous
# footage cut into 1s segments: a 6% crop difference between adjacent shots was
# detected 1 time in 5 (and that one was the source's own cut), while 15% was
# detected 5 times in 5. An earlier version drifted +6% per shot and produced twenty
# planned cuts of which none were visible — the output measured as the unedited
# source. These two levels stay ~24% apart, comfortably clear of the floor.
PUNCH_LEVELS = (1.0, 1.24)
PUNCH_DRIFT = 0.02       # gentle accumulation so a long scene does not look mechanical
PUNCH_DRIFT_CAP = 0.18


@dataclass
class ShotPlan:
    """A planned visual segment inside a scene."""

    start: float
    duration: float
    scene_index: int
    punch_in: float = 1.0     # crop zoom factor; >1 tightens the framing
    snapped_to_beat: bool = False

    @property
    def end(self) -> float:
        return self.start + self.duration

    def as_dict(self) -> dict:
        return {
            "start": round(self.start, 3),
            "duration": round(self.duration, 3),
            "scene_index": self.scene_index,
            "punch_in": round(self.punch_in, 4),
            "snapped_to_beat": self.snapped_to_beat,
        }


@dataclass
class StylePlan:
    shots: list[ShotPlan] = field(default_factory=list)
    grade_filter: str = ""
    transition: str = "cut"
    dissolve_seconds: float = 0.0
    captions: bool = False
    caption_position: str = "none"
    ken_burns: bool = False
    zoom_rate: float = 0.0
    beats_used: int = 0

    def as_dict(self) -> dict:
        return {
            "shot_count": len(self.shots),
            "grade_filter": self.grade_filter,
            "transition": self.transition,
            "dissolve_seconds": round(self.dissolve_seconds, 3),
            "captions": self.captions,
            "caption_position": self.caption_position,
            "ken_burns": self.ken_burns,
            "zoom_rate": round(self.zoom_rate, 4),
            "beats_used": self.beats_used,
            "shots": [shot.as_dict() for shot in self.shots],
        }


def _seed(spec: RenderSpec, salt: str) -> random.Random:
    """Deterministic RNG. Jitter must be reproducible or two renders of the same
    brief drift apart for no reason and a diff tells you nothing."""
    digest = hashlib.sha256(
        f"{spec.target_shot_seconds}:{spec.jitter}:{spec.cuts_per_minute}:{salt}".encode()
    ).hexdigest()
    return random.Random(int(digest[:16], 16))


def plan_shot_lengths(
    total: float,
    spec: RenderSpec,
    *,
    beats: list[float] | None = None,
    offset: float = 0.0,
    salt: str = "",
) -> list[tuple[float, bool]]:
    """Cut `total` seconds into shots at the reference rhythm.

    Returns (duration, snapped_to_beat) pairs summing to `total`. `offset` is the
    absolute start time, needed so beat snapping compares against real timestamps.
    """
    if total <= MIN_SHOT * 2 or spec.target_shot_seconds <= 0:
        return [(total, False)]

    target = max(spec.target_shot_seconds, MIN_SHOT)
    if target >= total:
        return [(total, False)]

    rng = _seed(spec, salt)
    jitter = max(0.0, min(1.0, spec.jitter))

    # Lay down cut points at the target interval, varied by the source's own
    # irregularity. A metronomic reference (jitter 0) yields even shots; an uneven
    # one yields uneven shots, which is the thing that actually distinguishes them.
    points: list[float] = []
    cursor = 0.0
    while True:
        length = target * (1.0 + rng.uniform(-jitter, jitter) * 0.6)
        length = max(MIN_SHOT, length)
        cursor += length
        if cursor >= total - MIN_SHOT:
            break
        points.append(cursor)

    snapped: set[int] = set()
    if spec.snap_cuts_to_beat and beats:
        window = target * SNAP_WINDOW
        for index, point in enumerate(points):
            absolute = point + offset
            nearest = min(beats, key=lambda beat: abs(beat - absolute))
            if abs(nearest - absolute) <= window:
                candidate = nearest - offset
                # Never let snapping collapse a shot below the minimum or reorder cuts.
                previous = points[index - 1] if index else 0.0
                if candidate - previous >= MIN_SHOT and total - candidate >= MIN_SHOT:
                    points[index] = candidate
                    snapped.add(index)

    points = sorted(set(points))
    durations: list[tuple[float, bool]] = []
    previous = 0.0
    for index, point in enumerate(points):
        durations.append((point - previous, index in snapped))
        previous = point
    durations.append((total - previous, False))
    return [(round(d, 4), s) for d, s in durations if d >= MIN_SHOT * 0.5]


def build_plan(
    scene_durations: list[float],
    spec: RenderSpec,
    *,
    beats: list[float] | None = None,
) -> StylePlan:
    """Subdivide narration scenes into shots at the reference's cutting rhythm."""
    shots: list[ShotPlan] = []
    cursor = 0.0
    beats_used = 0

    for scene_index, scene_duration in enumerate(scene_durations):
        if scene_duration <= 0:
            continue
        lengths = plan_shot_lengths(
            scene_duration, spec, beats=beats, offset=cursor, salt=f"scene{scene_index}"
        )
        # With one plate per scene, alternating the crop is what makes each cut
        # legible. See PUNCH_LEVELS for why it alternates instead of creeping.
        for position, (length, snapped) in enumerate(lengths):
            punch = 1.0
            if len(lengths) > 1:
                drift = min(PUNCH_DRIFT * (position // 2), PUNCH_DRIFT_CAP)
                punch = PUNCH_LEVELS[position % len(PUNCH_LEVELS)] + drift
            shots.append(
                ShotPlan(
                    start=cursor,
                    duration=length,
                    scene_index=scene_index,
                    punch_in=punch,
                    snapped_to_beat=snapped,
                )
            )
            beats_used += 1 if snapped else 0
            cursor += length

    dissolve = 0.0
    if spec.transition == "dissolve":
        # Keep the dissolve short relative to the shot or consecutive fades overlap.
        dissolve = min(0.5, max(0.12, spec.target_shot_seconds * 0.15))

    return StylePlan(
        shots=shots,
        grade_filter=spec.grade_filter,
        transition=spec.transition,
        dissolve_seconds=dissolve,
        captions=spec.captions,
        caption_position=spec.caption_position,
        ken_burns=spec.ken_burns,
        zoom_rate=spec.zoom_rate,
        beats_used=beats_used,
    )


def grade_transfer(
    source_brightness: float,
    source_contrast: float,
    source_saturation: float,
    spec: RenderSpec,
    *,
    strength: float = 0.85,
) -> str:
    """An ffmpeg `eq` string moving *this source* toward the reference's look.

    Distinct from `spec.grade_filter`, and the difference matters. The profile's
    filter answers "how do I get from neutral footage to this look", which is right
    when you are grading generated plates. Conforming an already-graded source is a
    different question — "how do I get from *here* to there" — and using the
    neutral-referenced filter for it fails visibly: applying a +0.009 brightness lift
    to footage that is already dark leaves it dark, nowhere near a bright reference.

    Still approximate, and deliberately so. Contrast and brightness interact, so an
    exact match needs iteration, and `strength` below 1.0 leaves the result slightly
    short of the target rather than overshooting into a caricature.
    """
    brightness = 0.0
    if source_brightness > 0:
        delta = (spec.target_brightness - source_brightness) / 255.0
        brightness = max(-0.6, min(0.6, delta * strength))

    contrast = 1.0
    target_contrast = getattr(spec, "target_contrast", 0.0) or 0.0
    if source_contrast > 1.0 and target_contrast > 1.0:
        ratio = target_contrast / source_contrast
        contrast = max(0.5, min(2.0, 1.0 + (ratio - 1.0) * strength))

    saturation = 1.0
    if source_saturation > 0.01 and spec.target_saturation > 0.01:
        ratio = spec.target_saturation / source_saturation
        saturation = max(0.3, min(3.0, 1.0 + (ratio - 1.0) * strength))

    return (
        f"eq=brightness={brightness:.3f}:contrast={contrast:.3f}"
        f":saturation={saturation:.3f}"
    )


def refine_grade(
    filter_string: str,
    measured_brightness: float,
    measured_contrast: float,
    measured_saturation: float,
    spec: RenderSpec,
) -> str:
    """One corrective pass over a grade, using what the filter actually produced.

    Needed because the three controls interact: lifting brightness adds a constant to
    every channel, which shrinks `(max-min)/max` and therefore *desaturates*. A
    single analytic pass lands brightness and then misses saturation for that exact
    reason. Measuring the result and correcting the residual is both simpler and more
    accurate than modelling the interaction.
    """
    params = dict(
        part.split("=", 1) for part in filter_string.removeprefix("eq=").split(":")
        if "=" in part
    )
    brightness = float(params.get("brightness", 0.0))
    contrast = float(params.get("contrast", 1.0))
    saturation = float(params.get("saturation", 1.0))

    if measured_brightness > 0:
        residual = (spec.target_brightness - measured_brightness) / 255.0
        brightness = max(-0.8, min(0.8, brightness + residual))

    target_contrast = getattr(spec, "target_contrast", 0.0) or 0.0
    if measured_contrast > 1.0 and target_contrast > 1.0:
        contrast = max(0.4, min(2.5, contrast * (target_contrast / measured_contrast)))

    if measured_saturation > 0.01 and spec.target_saturation > 0.01:
        saturation = max(
            0.2, min(4.0, saturation * (spec.target_saturation / measured_saturation))
        )

    return (
        f"eq=brightness={brightness:.3f}:contrast={contrast:.3f}"
        f":saturation={saturation:.3f}"
    )


def caption_margin(position: str, height: int) -> int:
    """ffmpeg subtitle MarginV for a caption zone, in pixels from the bottom."""
    return {
        "bottom_third": max(int(height * 0.12), 20),
        "centre": max(int(height * 0.45), 40),
        "top_third": max(int(height * 0.78), 60),
    }.get(position, max(int(height * 0.12), 20))


def spec_from_dict(payload: dict) -> RenderSpec:
    """Rebuild a RenderSpec from a saved profile's `render_spec` block."""
    data = payload.get("render_spec", payload)
    low, high = (data.get("shot_seconds_range") or [1.0, 1.0])[:2]
    return RenderSpec(
        target_shot_seconds=float(data.get("target_shot_seconds") or 2.0),
        shot_seconds_range=(float(low), float(high)),
        cuts_per_minute=float(data.get("cuts_per_minute") or 0.0),
        jitter=float(data.get("jitter") or 0.0),
        transition=str(data.get("transition") or "cut"),
        dissolve_share=float(data.get("dissolve_share") or 0.0),
        ken_burns=bool(data.get("ken_burns")),
        zoom_rate=float(data.get("zoom_rate") or 0.0),
        captions=bool(data.get("captions")),
        caption_position=str(data.get("caption_position") or "none"),
        snap_cuts_to_beat=bool(data.get("snap_cuts_to_beat")),
        pacing=str(data.get("pacing") or "steady"),
        grade_filter=str(data.get("grade_filter") or ""),
        target_brightness=float(data.get("target_brightness") or 128.0),
        target_contrast=float(data.get("target_contrast") or 55.0),
        target_saturation=float(data.get("target_saturation") or 0.3),
        palette=list(data.get("palette") or []),
    )
