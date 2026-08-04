"""Cutting a narration scene into visual shots — the wiring `vision.apply` was missing.

`vision/apply.py` has known how to subdivide a scene into shots at a measured rhythm
since it was written, and nothing imported it. Read its module docstring for the
design; this module is the part that connects it to ffmpeg and to the money.

Three things have to be true at once, and each one is a decision recorded here rather
than a preference:

**The narration is fixed.** A scene lasts exactly as long as its voiceover line. So
subdivision is arithmetic on integer milliseconds, not on floats: shot lengths that sum
to 7.998 instead of 8.000 push every later scene earlier by 2ms, and over a 480-second
render that accumulates into audio that visibly leads the picture. `plan_cuts` raises
rather than returning a plan whose shots do not sum to their scene.

**A cut has to be visible to count.** `apply.PUNCH_LEVELS` alternates between two
framings 24% apart because a reframe below ~15% was detected 1 time in 5. That number
is why `ken_burns` is switched off on a subdivided scene: the push closes on 1.12 by the
end of a shot, so a following shot at 1.24 is only 11% tighter than the frame the viewer
just left — under the floor. The zoom exists to keep a single 60-second still from
looking dead, and once the still is cut every 3.5 seconds the cut does that job better.

**Plates cost money and shots do not.** One generated image can carry several shots at
different crops. `plates_for` decides how many plates a scene actually buys, and
`estimate_plates` gives the ledger the same number in advance so the reserve and the
spend are computed by one rule instead of two that drift.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..vision.profile import RenderSpec

# The cutting rate for a channel that has never been given a reference to learn from.
#
# 3.5s is ~17 visual cuts per minute, the middle of the 12-20 band narrated faceless
# explainers sit in. It is chosen against two failures rather than for a feel:
#   - The old behaviour was one visual per narration beat, i.e. ~8 visuals in 480s, one
#     of them on screen for a minute. Anything in the band fixes that.
#   - Going faster costs plates. At SHOTS_PER_PLATE below, 3.5s means one plate per 14s
#     of runtime; a 1.5s default would mean one per 6s and a 480s video would spend the
#     whole ledger reserve on stills with nothing left for a scene that needs an extra.
DEFAULT_SHOT_SECONDS = 3.5

# Metronomic cuts read as a slideshow on a timer, which is the failure being fixed here
# wearing a different hat. 0.25 spreads shots across roughly 2.5-4.5s. `apply` seeds its
# RNG from the spec, so this stays reproducible.
DEFAULT_JITTER = 0.25

# A learned profile is honoured, but not below this. Every shot is a separate ffmpeg
# encode plus a concat entry: at 0.5s a 480s video is a thousand encodes, and the render
# outruns the vendor calls it is supposed to be cheap next to. A sub-second punch-in on a
# still also reads as a flicker rather than an edit.
MIN_TARGET_SHOT_SECONDS = 1.0

# How many shots one plate should carry before the viewer stops seeing cuts and starts
# seeing the same picture. `apply.PUNCH_LEVELS` offers two clearly separated framings, so
# four shots is A B A' B' — each framing twice. A fifth return to the same still is where
# recognition beats the reframe.
SHOTS_PER_PLATE = 4

# One plate per this much *scene*, which is the whole cost model in one number.
#
# Note what it is not a function of: the style's cutting rate. A channel that cuts twice
# as fast gets twice as many shots out of each plate, not twice the bill — the cutting
# rate is a style choice and the plate budget is a cost decision, and letting the first
# drive the second is how an analysed reference with a 1.0s median would quietly turn a
# $14 video into a $100 one. At 14s a 480-second video buys ~35 plates against the
# ledger's existing 80-unit reserve, so the fix fits inside money already held.
SECONDS_PER_PLATE = DEFAULT_SHOT_SECONDS * SHOTS_PER_PLATE

# The most scenes a run of this length produces, which is what the reserve has to assume:
# every scene buys at least one plate however short it is, and one in three of them may
# be animated, which is where the money is.
#
# It used to be the literal 12, on the grounds that "the brief prompt asks for 4-12
# beats". That stopped being true when the beat count moved into `scripting.method`'s
# cadence — which asks for 19 beats at eight minutes, 36 at fifteen and 72 at half an
# hour. A reserve enumerating twelve splits of an eight-minute video was pricing four
# animated beats against the six a real script produces.
#
# The margin is because a language model asked for nineteen beats returns about
# nineteen. Holding for a script that came back a quarter denser costs a user the wait
# for a release; not holding for it is a run that spends past its own hold.
_SCENE_MARGIN = 1.25


def max_scenes(target_seconds: float) -> int:
    """How many scenes a script of this length can be expected to contain, generously.

    From `scripting.method.cadence`, which is the thing that actually tells the model how
    many beats to write, so the two cannot drift the way a literal did.
    """
    from ..scripting.method import cadence

    return max(4, math.ceil(cadence(int(max(0.0, float(target_seconds or 0.0)))).beats
                            * _SCENE_MARGIN))

# What share of a script's beats the app will grant the hero tier, however many the
# planner asks for.
#
# A cap rather than an allocation, and it exists because of how a language model satisfies
# "mark the important shots": the cheapest way to be safe is to mark most of them, and a
# plan with half its scenes hero has not routed anything — it has chosen the expensive
# model for the whole video, at a settings page that promised a fifth of the cost. The
# roles that earn an upgrade are a fixed, short list — hook, reveal, payoff, close — so a
# quarter is generous at the twelve-scene ceiling above.
HERO_SHARE = 0.25


def video_budget(scenes: int) -> int:
    """How many of a script's beats may be animated. At most one in three.

    Here rather than beside the planner that enforces it, because the ledger has to
    reserve against the same number. Animation is the whole cost of a run — a still is
    five credits and a premium clip is two hundred — so a budget the money model cannot
    read is a budget that under-reserves every run it constrains. That is exactly what
    happened: the reserve priced a blended per-plate figure invented by hand while this
    cap decided the real bill, and the two disagreed by a factor of three.
    """
    return max(1, max(0, int(scenes)) // 3)


def hero_budget(scenes: int) -> int:
    """How many animated beats may take the premium model. See `HERO_SHARE`."""
    return max(1, round(max(0, int(scenes)) * HERO_SHARE))


class CutPlanError(RuntimeError):
    """A shot plan that does not add up to its narration. Never recoverable."""


@dataclass(frozen=True)
class SceneBeat:
    """A narration beat handed to the planner: how long it runs and what it may use."""

    index: int
    seconds: float
    plates: int = 1
    # A visual that animates itself — the world map is the one that exists — must not be
    # cut into. Its framing *is* the content, and reframing mid-route reads as an error.
    hold: bool = False


@dataclass(frozen=True)
class ShotCut:
    """One visual segment: which plate, which crop, how long, where in the plate."""

    scene_index: int
    shot_index: int
    plate_index: int
    seconds: float
    punch_in: float = 1.0
    # Where in the plate this shot starts, for a plate that is itself a moving clip.
    # Successive segments of one clip played in order are not a cut, so the punch-in is
    # what makes the edit visible and this is what keeps the content advancing.
    source_offset: float = 0.0
    snapped_to_beat: bool = False

    def as_dict(self) -> dict:
        return {
            "scene_index": self.scene_index,
            "shot_index": self.shot_index,
            "plate_index": self.plate_index,
            "seconds": round(self.seconds, 3),
            "punch_in": round(self.punch_in, 4),
            "source_offset": round(self.source_offset, 3),
            "snapped_to_beat": self.snapped_to_beat,
        }


# ------------------------------------------------------------------------------ spec


def default_spec() -> RenderSpec:
    """The cutting rhythm for a channel with no analysed reference."""
    from ..vision.apply import spec_from_dict

    return spec_from_dict(
        {
            "render_spec": {
                "target_shot_seconds": DEFAULT_SHOT_SECONDS,
                "shot_seconds_range": [
                    DEFAULT_SHOT_SECONDS * 0.6,
                    DEFAULT_SHOT_SECONDS * 1.5,
                ],
                "jitter": DEFAULT_JITTER,
            }
        }
    )


def spec_for(style_profile: dict | None) -> RenderSpec:
    """The run's cutting rhythm: the channel's measured style, else the default.

    A profile that reports a median shot below `MIN_TARGET_SHOT_SECONDS` is honoured up
    to that floor and no further — see the constant for why the limit is about render
    cost rather than taste.
    """
    from ..vision.apply import spec_from_dict

    measured = (style_profile or {}).get("render_spec") or {}
    if not measured.get("target_shot_seconds"):
        return default_spec()

    spec = spec_from_dict({"render_spec": measured})
    if spec.target_shot_seconds < MIN_TARGET_SHOT_SECONDS:
        spec.target_shot_seconds = MIN_TARGET_SHOT_SECONDS
    return spec


# ----------------------------------------------------------------------- plate budget


def shot_estimate(seconds: float, spec: RenderSpec) -> int:
    """How many shots a scene of this length holds, to the nearest whole shot.

    Deliberately arithmetic rather than a call to the planner: this decides a *budget*,
    and it runs against the script's estimated scene lengths while the plan itself runs
    against the measured voiceover. Matching the planner's jitter here would be false
    precision on a number that is already an estimate of a different quantity.
    """
    target = max(MIN_TARGET_SHOT_SECONDS, float(spec.target_shot_seconds or 0.0))
    return max(1, round(max(0.0, seconds) / target))


def plates_for(seconds: float, spec: RenderSpec | None = None, *, reusable: bool = True) -> int:
    """How many generated plates a scene buys.

    `spec` is accepted and ignored: see `SECONDS_PER_PLATE` for why the budget must not
    move with the cutting rate. It stays in the signature because every caller already
    has one and a reader who assumed otherwise should find the answer at the call site.

    `reusable` is false for a visual whose own motion is the point — one clip, sliced.
    Buying a second animated clip for one scene is the most expensive thing this pipeline
    can do, and the punch-in already gives that scene its cuts.
    """
    if not reusable:
        return 1
    return max(1, math.ceil(max(0.0, seconds) / SECONDS_PER_PLATE))


def estimate_plates(target_seconds: float, *, scenes: int = 0) -> int:
    """The ledger's reserve for the shots node, in plates.

    The reserve has to cover whatever shape of script arrives, and the shape matters
    because `plates_for` rounds up per scene: the same runtime split into more beats buys
    more plates. So this takes the worst legal split rather than an average, which is the
    difference between a reserve and a guess.

    The old reserve was `target_seconds / 6` — about 80 units for an 8-minute video
    against the 8 the node then spent, wrong by an order of magnitude in the safe
    direction. It is derived from the same constant now, so the two move together.

    `scenes` is the ceiling to enumerate up to, and defaults to `max_scenes` for this
    runtime. It was a flat 12 until the beat count moved into the scripting cadence.
    """
    total = max(0.0, float(target_seconds))
    ceiling = max(1, int(scenes) if scenes else max_scenes(total))
    return max(
        1,
        max(count * plates_for(total / count) for count in range(1, ceiling + 1)),
    )


# ------------------------------------------------------------------------------ plan


def plan_cuts(
    beats: Sequence[SceneBeat],
    spec: RenderSpec,
    *,
    audio_beats: list[float] | None = None,
) -> list[ShotCut]:
    """Subdivide each narration beat into shots that sum to it exactly.

    Deterministic: `apply` seeds its jitter from the spec, and everything after that is
    integer arithmetic, so the same profile and the same scene lengths produce the same
    plan. A render is therefore reproducible and a diff of the plan means something.
    """
    from ..vision.apply import MIN_SHOT, build_plan

    durations = [max(0.0, float(beat.seconds)) for beat in beats]
    plan = build_plan(durations, spec, beats=audio_beats)

    by_position: dict[int, list] = {}
    for shot in plan.shots:
        by_position.setdefault(shot.scene_index, []).append(shot)

    min_ms = max(1, round(MIN_SHOT * 1000))
    cuts: list[ShotCut] = []

    for position, beat in enumerate(beats):
        # Milliseconds, because that is the resolution ffmpeg is actually given: every
        # duration reaches it as `-t %.3f`. Planning in floats and formatting to three
        # places loses up to half a millisecond per shot with nothing to absorb it.
        total_ms = round(max(0.0, float(beat.seconds)) * 1000)
        if total_ms <= 0:
            continue

        planned = [] if beat.hold else by_position.get(position, [])
        spans = _quantise([shot.duration for shot in planned], total_ms, min_ms)
        if sum(spans) != total_ms:  # pragma: no cover - guarded by construction
            raise CutPlanError(
                f"scene {beat.index}: shots sum to {sum(spans)}ms, narration is "
                f"{total_ms}ms"
            )

        plates = max(1, min(int(beat.plates or 1), len(spans)))
        offset_ms = 0
        for shot_index, span in enumerate(spans):
            source = planned[shot_index] if shot_index < len(planned) else None
            cuts.append(
                ShotCut(
                    scene_index=beat.index,
                    shot_index=shot_index,
                    plate_index=(shot_index * plates) // len(spans),
                    seconds=span / 1000,
                    punch_in=(
                        source.punch_in if source is not None and len(spans) > 1 else 1.0
                    ),
                    source_offset=offset_ms / 1000,
                    snapped_to_beat=bool(
                        source is not None
                        and source.snapped_to_beat
                        and shot_index < len(spans) - 1
                    ),
                )
            )
            offset_ms += span

    verify(beats, cuts)
    return cuts


def _quantise(lengths: list[float], total_ms: int, min_ms: int) -> list[int]:
    """Whole-millisecond spans summing to exactly `total_ms`.

    Every span but the last is the planner's length rounded to a millisecond; the last
    absorbs the whole residual, so rounding error stops at the scene boundary instead of
    walking down the timeline. A cut is dropped rather than shortened below `min_ms`,
    because a 40ms shot is a glitch and a slightly long final shot is not.
    """
    spans: list[int] = []
    cursor = 0
    for wanted in lengths[:-1]:
        span = max(min_ms, round(wanted * 1000))
        if total_ms - (cursor + span) < min_ms:
            break
        spans.append(span)
        cursor += span
    spans.append(total_ms - cursor)
    return spans


def verify(beats: Sequence[SceneBeat], cuts: Sequence[ShotCut]) -> None:
    """Every scene's shots must sum to its narration, to the millisecond.

    A raise, not an `assert`: this runs in production under whatever flags the host
    chose, and the failure it catches does not look like a timing bug when it lands. It
    looks like the voiceover being wrong, and someone spends a day in the TTS provider.
    """
    wanted = {beat.index: round(max(0.0, float(beat.seconds)) * 1000) for beat in beats}
    got: dict[int, int] = {}
    for cut in cuts:
        got[cut.scene_index] = got.get(cut.scene_index, 0) + round(cut.seconds * 1000)

    for index, target_ms in wanted.items():
        if target_ms <= 0:
            continue
        actual_ms = got.get(index, 0)
        if actual_ms != target_ms:
            raise CutPlanError(
                f"scene {index}: shots total {actual_ms / 1000:.3f}s but the narration "
                f"is {target_ms / 1000:.3f}s — the render would drift by "
                f"{(actual_ms - target_ms) / 1000:+.3f}s from here on"
            )


def shots_per_minute(cuts: Sequence[ShotCut]) -> float:
    """The planned cutting rate, for the log line that makes this change auditable."""
    total = sum(cut.seconds for cut in cuts)
    if total <= 0:
        return 0.0
    return len(cuts) / (total / 60)
