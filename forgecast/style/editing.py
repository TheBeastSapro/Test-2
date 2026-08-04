"""An editing style: what a creator's cutting, grading and typography actually do.

## What a style is, and why it is not one measurement

`vision.analyse_file` measures one video. One video is an anecdote — it might be the
episode where they tried something, or the one with an unusual subject, or the one cut
short. A *style* is what survives across several, so `learn` takes a list of profiles
and reduces each field by median.

Median rather than mean, for the same reason the outlier scorer uses it: one atypical
reference should not drag the whole style toward itself. And the spread across
references is kept, not discarded — a field the references disagree about is a field
this creator does not actually have a rule for, and the operator should be able to see
that rather than inheriting a confident-looking number computed from noise.

## Why this is separate from MotionPreset

A `MotionPreset` is how type and cards behave. An `EditingStyle` is the whole edit:
cut rhythm, transitions, camera movement, grade, caption discipline, audio levels —
and, as one of its fields, which motion preset to use. Folding them together would
mean you could not learn a new grade without also re-learning the typography.

## What every field is for

Everything here is either directly applicable by the renderer or directly readable by
the operator. Nothing is stored because it was measured; a number that no stage
consumes and no human reads is a number that goes stale silently.
"""

from __future__ import annotations

import json
import re
import statistics
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = "editing-style/1"

DEFAULT_DIRECTORY = "./storage/styles"

# What a script is written to when nothing has been learned: 2.6 words a second of
# runtime, about 156 a minute.
#
# It lives here because this is where the measurement that overrides it lives. It was two
# literals — `graph.pipelines` priced the ledger hold off one and `nodes.content` wrote
# the script against the other — which is one number in two files and no way to find out
# they have stopped agreeing except by reading a script that came out ninety seconds long.
WORDS_PER_SECOND = 2.6

# The shipped hook window: how much of the opening the Hook Gate cuts, watches and judges.
# Fifteen seconds is where a viewer decides, and it is the right answer for a channel
# nobody has measured — see `nodes.hook`. A channel whose references stop their opening
# beat at three seconds is judged on three, because judging that one on fifteen is judging
# it on its setup.
HOOK_SECONDS = 15.0

# Bounds on a measured read rate, in words per second of runtime. Under the floor the
# reference is a music-led piece with occasional narration and the "rate" is measuring its
# silence; over the ceiling nobody is talking that fast for eight minutes and the reading
# is a full transcript divided by a runtime that came back short. Either is inherited as a
# script hundreds of words wrong — `sourcing.MIN_SHARE`/`MAX_SHARE`'s reason, applied to a
# rate rather than to a share.
MIN_RATE, MAX_RATE = 1.2, 4.5

# Bounds on a measured hook window. The floor is `semantic.MIN_SECTION_SECONDS`, restated
# rather than imported so this module does not pull the vision stack in to read one
# number: no beat shorter than that was ever allowed to be a section, so a window under it
# did not come from a boundary and is a stored block that has been corrupted or hand-
# edited. The ceiling is where the gate stops being cheap — an opening beat running past
# half a minute is the first act, and this gate exists to cost a fiftieth of what it
# guards.
MIN_HOOK_SECONDS, MAX_HOOK_SECONDS = 1.5, 30.0

# The fewest words a rate may be measured off. At the shipped rate this is about
# twenty-three seconds of narration: under it, a "channel read rate" is one sentence's
# delivery generalised to every script the channel will ever write, and the arithmetic is
# dominated by wherever the transcriber decided the first and last word were.
MIN_WORDS = 60

# How much faster or slower than the body the opening has to be read before the difference
# is worth putting in front of a writer. A narrator varies by a few percent between beats
# without meaning anything by it — `semantic.ESCALATION_RISE`'s reason, at the one
# boundary this app can act on.
NOTABLE_RATE_CHANGE = 0.15

# What a narrative measurement will not claim, whatever the reference does, reported on
# every profile. Silence here reads as "this channel has no hook pattern" rather than
# "this pass cannot find one" — `semantic.UNCLAIMABLE`'s reason, one level up.
UNCLAIMABLE_HOOK: dict[str, str] = {
    "hook_type": (
        "what kind of opening this is — a question, a cold detail, a flat contradiction — "
        "is a fact about meaning, and the only pass that reaches a reference's narration "
        "reads timings. How long the opening beat runs and how fast it is read are "
        "measured; what it did with them is not, and a type guessed from a duration would "
        "be a rotation-bank entry chosen by a stopwatch"
    ),
}

# Fields reduced by median across references, with the bounds a sane value falls in.
# The bounds are guard rails against a broken measurement, not taste: a target shot
# length of zero or a saturation of 40 is a bug upstream, and inheriting it would
# produce an unrenderable style.
_NUMERIC_BOUNDS: dict[str, tuple[float, float]] = {
    "target_shot_seconds": (0.2, 30.0),
    "shot_seconds_min": (0.1, 30.0),
    "shot_seconds_max": (0.3, 120.0),
    "cuts_per_minute": (0.5, 240.0),
    "jitter": (0.0, 1.0),
    "dissolve_share": (0.0, 1.0),
    "zoom_rate": (0.0, 0.25),
    "motion_intensity": (0.0, 1.0),
    "brightness": (-0.5, 0.5),
    "contrast": (0.4, 2.2),
    "saturation": (0.0, 3.0),
}


def slug(name: str) -> str:
    """A filesystem-safe key. The filename, the lookup key and the CLI flag are one."""
    cleaned = re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")
    return cleaned or "style"


@dataclass
class EditingStyle:
    """A complete, applicable editing look. Every field is JSON-serialisable."""

    name: str

    # -- rhythm ----------------------------------------------------------------
    target_shot_seconds: float = 4.0
    shot_seconds_min: float = 2.0
    shot_seconds_max: float = 8.0
    cuts_per_minute: float = 15.0
    jitter: float = 0.35                 # 0 = metronomic, 1 = wildly varied
    pacing: str = "steady"               # accelerating | steady | decelerating
    snap_cuts_to_beat: bool = False

    # -- transitions -----------------------------------------------------------
    transition: str = "cut"              # cut | dissolve
    dissolve_share: float = 0.0

    # -- movement --------------------------------------------------------------
    ken_burns: bool = True
    zoom_rate: float = 0.02              # zoom factor per second on a still
    motion_intensity: float = 0.5        # drives which motion preset is chosen
    motion_preset: str = ""              # empty = pick by intensity

    # -- typography ------------------------------------------------------------
    captions: bool = True
    caption_position: str = "bottom_third"
    caption_max_chars: int = 40
    caption_max_lines: int = 2
    caption_max_seconds: float = 4.0

    # -- grade -----------------------------------------------------------------
    brightness: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0
    palette: list[dict] = field(default_factory=list)

    # -- audio -----------------------------------------------------------------
    loudness_target: str = "youtube"
    music_bed: bool = False
    music_gain_db: float = -8.0
    duck_depth_db: float = 10.0

    # -- map ---------------------------------------------------------------------
    map_style: str = "documentary_dark"

    # -- sourcing ------------------------------------------------------------------
    # How this creator gets their pictures: what share of beats move, what a moving
    # beat runs for, whether the frame is a flat card. Measured by `style.sourcing`
    # from the same per-shot analysis every other field here comes from.
    #
    # It is on the style rather than on the channel because it is a property of the
    # look, not of the account: learn a creator once, apply that style to three
    # channels, and all three source pictures the way that creator does. Two channels
    # modelled on one reference cannot drift apart, because there is one measurement.
    #
    # This is what replaced two constants — one beat in three may animate, one in four
    # may take the premium endpoint. Both were reasonable guesses and both were wrong
    # for most channels: a white-card explainer moves almost nothing, a cinematic
    # channel moves nearly everything, and the guess was priced into every run.
    sourcing: dict = field(default_factory=dict)

    # -- narrative -----------------------------------------------------------------
    # What this creator's narration does: how fast they talk over their runtime, and where
    # their opening beat stops. Measured by `vision.semantic` off the reference's own
    # audio, pooled here by `_narrative_of` from the same profiles every other field
    # comes from.
    #
    # It is on the style rather than on the channel for `sourcing`'s reason, which applies
    # here without a word changed: it is a property of the look, not of the account. Learn
    # a creator once, apply that style to three channels, and all three write to that
    # creator's pace and open on that creator's beat. Two channels modelled on one
    # reference cannot drift apart, because there is one measurement.
    #
    # This is what replaced two more constants — 2.6 words a second, and a fifteen-second
    # hook window. Both were reasonable guesses, both were the same guess for every
    # channel, and both decided something a reference can answer exactly: a breathless
    # shorts channel says four words a second and stops its opening beat at three, and was
    # getting a script written at the pace of a documentary and an opening judged on five
    # times the video it actually opens with.
    narrative: dict = field(default_factory=dict)

    # -- bookkeeping -------------------------------------------------------------
    # How much the references disagreed, per field, 0..1. A high number means this
    # creator has no consistent rule here and the median is not worth much.
    spread: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=lambda: {"origin": "built_in"})
    notes: list[str] = field(default_factory=list)

    # ------------------------------------------------------------ serialisation

    @property
    def key(self) -> str:
        return slug(self.name)

    def as_dict(self) -> dict:
        return {"schema_version": SCHEMA_VERSION, **asdict(self)}

    @classmethod
    def from_dict(cls, payload: dict) -> EditingStyle:
        known = {
            key: value for key, value in payload.items()
            if key in cls.__dataclass_fields__
        }
        if "name" not in known:
            raise ValueError("an editing style needs a name")
        return cls(**known)

    def save(self, directory: Path | str = DEFAULT_DIRECTORY) -> Path:
        path = Path(directory) / f"{self.key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.as_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path | str) -> EditingStyle:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def variant(self, name: str, **changes) -> EditingStyle:
        return replace(self, name=name, **changes)

    # ------------------------------------------------------------- application

    def to_render_spec(self) -> dict:
        """The subset the render node reads, in the shape it already expects.

        Emitting a plain dict in `RenderSpec`'s own shape rather than a new type: the
        renderer already consumes `channel.style_profile["render_spec"]`, and adding a
        second path into it would mean two places that decide how a video is cut.
        """
        return {
            "target_shot_seconds": round(self.target_shot_seconds, 3),
            "shot_seconds_range": [round(self.shot_seconds_min, 3),
                                   round(self.shot_seconds_max, 3)],
            "cuts_per_minute": round(self.cuts_per_minute, 2),
            "jitter": round(self.jitter, 3),
            "transition": self.transition,
            "dissolve_share": round(self.dissolve_share, 3),
            "ken_burns": self.ken_burns,
            "zoom_rate": round(self.zoom_rate, 4),
            "captions": self.captions,
            "caption_position": self.caption_position,
            "snap_cuts_to_beat": self.snap_cuts_to_beat,
            "pacing": self.pacing,
            "motion_intensity": round(self.motion_intensity, 3),
            "grade_filter": self.grade_filter(),
            "target_brightness": round(self.brightness, 3),
            "target_contrast": round(self.contrast, 3),
            "target_saturation": round(self.saturation, 4),
            "palette": self.palette,
        }

    def grade_filter(self) -> str:
        """The `eq` filter this grade compiles to, or empty when it is a no-op."""
        parts = []
        if abs(self.brightness) > 0.005:
            parts.append(f"brightness={self.brightness:.3f}")
        if abs(self.contrast - 1.0) > 0.005:
            parts.append(f"contrast={self.contrast:.3f}")
        if abs(self.saturation - 1.0) > 0.005:
            parts.append(f"saturation={self.saturation:.3f}")
        return f"eq={':'.join(parts)}" if parts else ""

    def to_channel_profile(self, existing: dict | None = None) -> dict:
        """Merge this style into a channel's `style_profile`, keeping what it does not own.

        A channel's profile also carries things a style has no opinion about — its
        tone, its learned decisions. Replacing the whole dict would silently discard
        them, so this merges the keys the style is authoritative for and leaves the
        rest untouched.
        """
        profile = dict(existing or {})
        profile["render_spec"] = self.to_render_spec()
        profile["editing_style"] = self.key
        profile["map_style"] = self.map_style
        profile["loudness_target"] = self.loudness_target
        if self.motion_preset:
            profile["motion_preset"] = self.motion_preset
        if self.sourcing:
            # How this look sources pictures, carried onto the channel so the planner and
            # the ledger read the same measurement. Only written when there is one —
            # a style learned before this existed, or from a reference too thin to
            # measure, must not overwrite a channel's working numbers with an empty dict.
            profile["sourcing"] = dict(self.sourcing)
        if self.narrative:
            # How this look narrates, carried onto the channel for exactly the reason
            # above: the stage that writes the script, the gate that watches the opening
            # and the ledger that reserves against both have to be reading one
            # measurement. Guarded the same way and for the same failure — a style learned
            # before this field existed carries an empty dict, and writing that would
            # silently return a working channel to the shipped constants.
            profile["narrative"] = dict(self.narrative)
        return profile

    def summary(self) -> str:
        """One line an operator can read at a glance."""
        cuts = f"{self.cuts_per_minute:.0f} cuts/min"
        rhythm = "metronomic" if self.jitter < 0.15 else (
            "varied" if self.jitter < 0.5 else "highly varied")
        return (f"{cuts}, {self.target_shot_seconds:.1f}s shots, {rhythm}, "
                f"{self.pacing}, {self.transition}, "
                f"motion {self.motion_intensity:.2f}")


# ------------------------------------------------------------------- learning


def _median(values: list[float], fallback: float, bounds: tuple[float, float]) -> float:
    usable = [
        float(value) for value in values
        if isinstance(value, (int, float)) and bounds[0] <= float(value) <= bounds[1]
    ]
    return statistics.median(usable) if usable else fallback


def _spread(values: list[float]) -> float:
    """How much the references disagree, normalised to 0..1.

    Half the interquartile-ish range over the median. Expressed relative to the value
    because a 2-second disagreement means something very different for 3-second shots
    than for 30-second ones.
    """
    usable = [float(v) for v in values if isinstance(v, (int, float))]
    if len(usable) < 2:
        return 0.0
    middle = statistics.median(usable)
    if abs(middle) < 1e-9:
        return 0.0 if max(usable) - min(usable) < 1e-9 else 1.0
    return min(1.0, (max(usable) - min(usable)) / (2 * abs(middle)))


def _mode(values: list[str], fallback: str, allowed: tuple[str, ...] = ()) -> str:
    """The most common value, ignoring ones outside the allowed set.

    The filter is what stops a measurement's *diagnostic* from becoming a style. When
    `vision` cannot judge pacing it reports `insufficient_shots`, which is a statement
    about the evidence rather than about the edit — adopting it would give a style a
    pacing nothing downstream knows how to apply.
    """
    usable = [str(value) for value in values if value]
    if allowed:
        usable = [value for value in usable if value in allowed]
    if not usable:
        return fallback
    # `mode` raises on a tie in older Pythons; counting keeps a stable winner, which
    # is good enough for a categorical with three options.
    return max(set(usable), key=usable.count)


def _majority(values: list[bool], fallback: bool) -> bool:
    usable = [bool(value) for value in values if value is not None]
    if not usable:
        return fallback
    return sum(usable) * 2 > len(usable)


def learn(
    profiles: list[dict],
    *,
    name: str,
    reference: str = "",
    notes: list[str] | None = None,
) -> EditingStyle:
    """Reduce one or more measured `StyleProfile` dicts into a style.

    Descriptive only. If the references cut metronomically, so does the result; if
    their grade clips, so does the result. Making it *better* is `refine`'s job, and
    keeping the two apart is what lets an operator see the difference between what the
    reference does and what we chose to do differently.
    """
    if not profiles:
        raise ValueError("learning a style needs at least one measured profile")

    specs = [dict(profile.get("render_spec") or {}) for profile in profiles]
    rhythms = [dict(profile.get("shot_rhythm") or {}) for profile in profiles]
    overlays = [dict(profile.get("overlay") or {}) for profile in profiles]
    audios = [dict(profile.get("audio") or {}) for profile in profiles]

    def numbers(key: str, source: list[dict], default: float) -> list[float]:
        return [item.get(key, default) for item in source]

    ranges = [spec.get("shot_seconds_range") or [2.0, 8.0] for spec in specs]
    lows = [float(item[0]) for item in ranges if len(item) == 2]
    highs = [float(item[1]) for item in ranges if len(item) == 2]

    style = EditingStyle(
        name=name,
        target_shot_seconds=_median(numbers("target_shot_seconds", specs, 4.0), 4.0,
                                    _NUMERIC_BOUNDS["target_shot_seconds"]),
        shot_seconds_min=_median(lows, 2.0, _NUMERIC_BOUNDS["shot_seconds_min"]),
        shot_seconds_max=_median(highs, 8.0, _NUMERIC_BOUNDS["shot_seconds_max"]),
        cuts_per_minute=_median(numbers("cuts_per_minute", specs, 15.0), 15.0,
                                _NUMERIC_BOUNDS["cuts_per_minute"]),
        jitter=_median(numbers("jitter", specs, 0.35), 0.35, _NUMERIC_BOUNDS["jitter"]),
        pacing=_mode([str(spec.get("pacing", "")) for spec in specs], "steady",
                     allowed=("accelerating", "steady", "decelerating")),
        snap_cuts_to_beat=_majority(
            [bool(spec.get("snap_cuts_to_beat")) for spec in specs], False),
        transition=_mode([str(spec.get("transition", "")) for spec in specs], "cut",
                         allowed=("cut", "dissolve")),
        dissolve_share=_median(numbers("dissolve_share", specs, 0.0), 0.0,
                               _NUMERIC_BOUNDS["dissolve_share"]),
        ken_burns=_majority([bool(spec.get("ken_burns")) for spec in specs], True),
        zoom_rate=_median(numbers("zoom_rate", specs, 0.02), 0.02,
                          _NUMERIC_BOUNDS["zoom_rate"]),
        motion_intensity=_median(numbers("motion_intensity", specs, 0.5), 0.5,
                                 _NUMERIC_BOUNDS["motion_intensity"]),
        captions=_majority([bool(spec.get("captions")) for spec in specs], True),
        caption_position=_mode(
            [str(spec.get("caption_position", "")) for spec in specs], "bottom_third",
            allowed=("bottom_third", "centre", "top_third", "none")),
        brightness=_median(numbers("target_brightness", specs, 0.0), 0.0,
                           _NUMERIC_BOUNDS["brightness"]),
        contrast=_median(numbers("target_contrast", specs, 1.0), 1.0,
                         _NUMERIC_BOUNDS["contrast"]),
        saturation=_median(numbers("target_saturation", specs, 1.0), 1.0,
                           _NUMERIC_BOUNDS["saturation"]),
        palette=_palette_of(profiles),
        music_bed=_majority(
            [bool(item.get("has_music") or item.get("music")) for item in audios], False),
        sourcing=_sourcing_of(profiles),
        narrative=_narrative_of(profiles),
        notes=list(notes or []),
    )

    style.spread = {
        "target_shot_seconds": round(_spread(numbers("target_shot_seconds", specs, 4.0)), 3),
        "cuts_per_minute": round(_spread(numbers("cuts_per_minute", specs, 15.0)), 3),
        "jitter": round(_spread(numbers("jitter", specs, 0.35)), 3),
        "motion_intensity": round(_spread(numbers("motion_intensity", specs, 0.5)), 3),
        "saturation": round(_spread(numbers("target_saturation", specs, 1.0)), 3),
        "contrast": round(_spread(numbers("target_contrast", specs, 1.0)), 3),
    }
    style.provenance = {
        "origin": "learned",
        "references": [
            str((profile.get("source") or {}).get("path") or reference or "?")
            for profile in profiles
        ],
        "sample_size": len(profiles),
        "learned_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "shot_count": sum(int(item.get("shot_count") or 0) for item in rhythms),
        "captions_seen": sum(1 for item in overlays if item.get("has_captions")),
    }
    return style


# `vision` reports confidence as a label, not a number. Ranked here rather than
# compared as strings, because "high" sorts below "low" alphabetically and that would
# pick the *least* confident palette every time.
_CONFIDENCE_RANK = {"high": 3.0, "medium": 2.0, "low": 1.0, "none": 0.0}


def _confidence_score(value) -> float:
    """Read a confidence that may be a label, a number, or missing."""
    if isinstance(value, (int, float)):
        return float(value)
    return _CONFIDENCE_RANK.get(str(value).strip().lower(), 1.5)


def _palette_of(profiles: list[dict]) -> list[dict]:
    """The palette of the reference whose colour reading is most confident.

    Averaging palettes across references produces mud — mixing two distinct three-
    colour looks gives six desaturated near-greys that belong to neither. Picking one
    intact palette keeps a usable set of colours.
    """
    best: list[dict] = []
    best_score = -1.0
    for profile in profiles:
        colour = profile.get("colour") or {}
        palette = colour.get("palette") or []
        if not palette:
            continue
        score = _confidence_score((profile.get("confidence") or {}).get("colour"))
        if score > best_score:
            best, best_score = list(palette), score
    return best


def _sourcing_of(profiles: list[dict]) -> dict:
    """How this creator gets their pictures, pooled across the references.

    Pooled at the *shot* level rather than averaged per reference, which is the same
    reasoning `_palette_of` uses inverted. A palette is a set and averaging two sets
    gives mud; an animation share is a proportion, and the honest proportion across
    three references is the shots that moved over the shots that ran — not the mean of
    three proportions, which weights a two-minute video the same as a twenty-minute one.

    The colour reading comes from whichever reference was most confident about colour,
    for the reason `_palette_of` gives: a flat white card and a graded photographic look
    averaged together describe neither.
    """
    from .sourcing import measure

    per_shot: list[dict] = []
    colour: dict = {}
    best_score = -1.0
    for profile in profiles:
        rows = profile.get("per_shot") or []
        per_shot.extend(row for row in rows if isinstance(row, dict))
        score = _confidence_score((profile.get("confidence") or {}).get("colour"))
        if score > best_score and (profile.get("colour") or {}).get("palette"):
            colour, best_score = dict(profile.get("colour") or {}), score
    if not per_shot:
        return {}
    return measure(per_shot, colour=colour).as_dict()


def _narrative_of(profiles: list[dict]) -> dict:
    """What this creator's narration does, pooled across the references.

    Reads the `semantic` block each reference already carries. A block that came from a
    vision provider rather than from `vision.semantic` has none of these fields and
    contributes nothing — which is the right outcome and not a check worth adding, since
    `measure_narrative` counts words and seconds and a description of the shots has
    neither.

    `{}` when no reference carries a narrative block at all, so a style learned before
    this existed does not arrive at `to_channel_profile` claiming to have measured
    something. A block that is present and thin is kept, notes and all, for `_sourcing_of`'s
    reason: the consumers gate on `usable`, so a thin measurement costs the channel the
    shipped defaults and hands the operator the sentence saying why.
    """
    blocks = [profile.get("semantic") for profile in profiles]
    narratives = [block for block in blocks
                  if isinstance(block, dict) and "transcribed" in block]
    if not narratives:
        return {}
    return measure_narrative(narratives).as_dict()


# ---------------------------------------------- the narration, as a writing budget


@dataclass
class NarrativeProfile:
    """What a reference channel's narration does. Every field is JSON-serialisable."""

    # Words over runtime — the rate every script's length is built out of. Defaults to the
    # shipped figure rather than to zero, so a profile that measured nothing is a profile
    # that agrees with the app instead of a hole every reader has to check for.
    words_per_second: float = WORDS_PER_SECOND
    # Where the opening beat stops, in seconds. 0.0 means no reference could be sectioned
    # — which is a different outcome from a short hook and must not round to one.
    hook_seconds: float = 0.0
    hook_words: int = 0
    # How fast the opening is read, which is not the same number as the rate above and is
    # the more useful of the two: a creator who opens a third faster than they run is
    # doing something a writer can copy, and `Section.words_per_second` measures it.
    hook_words_per_second: float = 0.0
    hook_share: float = 0.0
    # accelerating | steady | decelerating | not_measured — the read over the whole
    # runtime, in `vision.semantic`'s own words so the two can be put side by side.
    delivery_trend: str = "not_measured"
    confidence: str = "none"
    words_measured: int = 0
    runtime_measured: float = 0.0
    references: int = 0
    hooks_measured: int = 0
    not_claimed: dict = field(default_factory=lambda: dict(UNCLAIMABLE_HOOK))
    notes: list[str] = field(default_factory=list)

    @property
    def words_per_minute(self) -> float:
        """The same rate an operator can read. Derived, never stored: two fields holding
        one measurement is two answers the first time either is rounded."""
        return round(self.words_per_second * 60, 1)

    def as_dict(self) -> dict:
        return {**asdict(self), "words_per_minute": self.words_per_minute}

    @classmethod
    def from_dict(cls, payload: dict) -> NarrativeProfile:
        known = {key: value for key, value in (payload or {}).items()
                 if key in cls.__dataclass_fields__}
        return cls(**known)

    @property
    def usable(self) -> bool:
        """Whether this should decide what gets written, as opposed to merely being shown.

        Deliberately the same gate `SourcingProfile.usable` uses: a confidence the
        measurement graded itself, and enough evidence under it to generalise from. A rate
        read off twenty words is an anecdote, and an anecdote applied here is every script
        this channel ever writes coming out the wrong length — so `learn` keeps it either
        way and `writing_budget` asks this first.
        """
        return self.confidence in {"medium", "high"} and self.words_measured >= MIN_WORDS


def _median_of(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def _hook_of(block: dict) -> dict | None:
    """The opening beat of one reference, or `None` when it has no measured one.

    `hook_ends_at` and the first section are two spellings of one boundary and both are
    required, because a block carrying one without the other has been edited by hand or
    truncated in storage — and a hook window derived from half a measurement is the kind
    of number that looks measured and is not.
    """
    if not block.get("sectioned"):
        return None
    ends_at = block.get("hook_ends_at")
    sections = [row for row in (block.get("sections") or []) if isinstance(row, dict)]
    if not isinstance(ends_at, (int, float)) or ends_at <= 0 or not sections:
        return None
    return sections[0]


def measure_narrative(blocks: list[dict] | None) -> NarrativeProfile:
    """Read the `semantic` blocks of one or more learned references into a writing profile.

    `blocks` is what `vision.semantic.measure` already produces — one `Narrative.as_dict()`
    per reference. Nothing is transcribed here and no model is loaded; this is arithmetic
    on a measurement the learn pass has been making, grading, storing, displaying and
    handing to nobody.

    The rate is pooled rather than averaged per reference, for `_sourcing_of`'s reason: a
    rate is words over seconds, so the honest figure across three references is every word
    over every second — not the mean of three rates, which gives a forty-second short the
    same vote as a twenty-minute documentary.

    The hook takes the median instead, and the difference is not an inconsistency. A hook
    length is not a quantity to be totalled: it is a decision the creator makes once per
    video, so the question is which length they keep choosing, and one reference that
    opened on a ninety-second cold open must not drag the answer. That is `learn`'s own
    rule for every other field here.
    """
    read = [block for block in (blocks or [])
            if isinstance(block, dict) and block.get("transcribed")]
    notes: list[str] = []
    if not read:
        # The transcriber's own reason, carried up in the same sentence rather than
        # restated or listed underneath. "Video editing tools are not installed" and "the
        # reference has no audio track" are different problems with different fixes, and
        # everything downstream of here reads the first note — a bare "not transcribed"
        # sends the operator to re-learn a reference that was never going to work.
        reasons = [str(line) for block in (blocks or [])
                   for line in (block.get("notes") or [])[:1]]
        notes.append("no reference could be transcribed"
                     + (f": {'; '.join(reasons)}" if reasons else ""))
        return NarrativeProfile(notes=notes)

    words = sum(int(block.get("words") or 0) for block in read)
    runtime = sum(float(block.get("runtime_seconds") or 0.0) for block in read)
    rate = words / runtime if runtime > 0 else 0.0

    # Bounded, and the clamp is reported. Inheriting an unclamped rate is a script written
    # at somebody's transcription error — see `MIN_RATE`/`MAX_RATE`.
    bounded = min(MAX_RATE, max(MIN_RATE, rate)) if rate > 0 else WORDS_PER_SECOND
    if rate > 0 and abs(bounded - rate) > 0.005:
        notes.append(
            f"measured {rate:.2f} words a second across the references, held at "
            f"{bounded:.2f} — a read outside {MIN_RATE}–{MAX_RATE} is a transcript "
            f"divided by the wrong runtime rather than a creator")

    # Graded on the evidence under the rate and nothing else, which is `SourcingProfile`'s
    # own ladder with words in place of shots. A reference the transcriber was unsure of
    # does not appear here, and that is deliberate rather than an omission: `semantic` is
    # explicit that a shaky read keeps its timings and loses only its quoted text — and no
    # quoted text leaves this module, so the doubt has nothing here to undermine. It is
    # still said out loud below, because an operator reading a profile graded `high` off
    # references the model could barely hear deserves to know which it was.
    confidence = "high"
    if words < MIN_WORDS:
        confidence = "low"
        notes.append(
            f"{words} words across {len(read)} reference(s) — under {MIN_WORDS} a read "
            f"rate is one sentence's delivery generalised to every script this channel "
            f"will ever write")
    elif words < MIN_WORDS * 4 or len(read) < 2:
        confidence = "medium"

    shaky = sum(1 for block in read
                if _confidence_score(block.get("confidence")) <= _CONFIDENCE_RANK["low"])
    if shaky:
        notes.append(
            f"{shaky} of {len(read)} reference(s) came back low confidence and are pooled "
            f"in at full weight — what a low grade puts in doubt is the transcribed text, "
            f"and the text is the one thing this measurement does not use")

    hooks = [(block, found) for block, found in
             ((block, _hook_of(block)) for block in read) if found is not None]
    hook_seconds = _median_of([float(block["hook_ends_at"]) for block, _ in hooks])
    hook_words = int(_median_of([float(found.get("words") or 0) for _, found in hooks]))
    hook_share = _median_of([float(found.get("share") or 0.0) for _, found in hooks])
    # The opening's own rate is pooled, not medianed: it is a rate, and the rule above
    # applies to it exactly as it applies to the whole reference's.
    hook_spoken = sum(float(found.get("seconds") or 0.0) for _, found in hooks)
    hook_rate = (sum(float(found.get("words") or 0) for _, found in hooks) / hook_spoken
                 if hook_spoken > 0 else 0.0)

    if hook_seconds > 0:
        held = min(MAX_HOOK_SECONDS, max(MIN_HOOK_SECONDS, hook_seconds))
        if abs(held - hook_seconds) > 0.005:
            notes.append(
                f"the references stop their opening beat at {hook_seconds:.1f}s, held at "
                f"{held:.1f}s — past {MAX_HOOK_SECONDS:.0f}s the opening is the first act "
                f"and the gate would cost what it is guarding")
        hook_seconds = round(held, 2)
    else:
        notes.append(
            f"no reference could be sectioned, so where this channel's opening beat stops "
            f"is not measured and the gate keeps the shipped {HOOK_SECONDS:.0f}s window")

    return NarrativeProfile(
        words_per_second=round(bounded, 3),
        hook_seconds=hook_seconds,
        hook_words=hook_words,
        hook_words_per_second=round(hook_rate, 2),
        hook_share=round(hook_share, 3),
        delivery_trend=_mode([str(block.get("delivery_trend") or "") for block in read],
                             "not_measured",
                             allowed=("accelerating", "steady", "decelerating")),
        confidence=confidence,
        words_measured=words,
        runtime_measured=round(runtime, 2),
        references=len(read),
        hooks_measured=len(hooks),
        notes=notes,
    )


def _hook_pattern(profile: NarrativeProfile) -> dict:
    """What an opening looks like on this channel, as the numbers behind it and one line.

    The sentence is built here rather than at each reader, so the block the writer is
    given and the block the gate judges against cannot describe the same channel
    differently — `skills.gates.Quote.sentence` exists for the same reason.

    No wording from the reference is in here, and that is a decision rather than an
    omission. The transcript is sitting right there and quoting it would be the strongest
    possible instruction — which is the problem: an opening line handed to a model as an
    example comes back rewritten eight words at a time, and the channel it was measured
    off is somebody else's. What is measured is a length and a pace, so a length and a
    pace is what gets passed on.
    """
    rate = profile.hook_words_per_second
    body = profile.words_per_second
    opens = "at the same pace as the rest of the video"
    if rate > 0 and body > 0:
        change = (rate - body) / body
        if change > NOTABLE_RATE_CHANGE:
            opens = f"{change:.0%} faster than the rest of the video"
        elif change < -NOTABLE_RATE_CHANGE:
            opens = f"{abs(change):.0%} slower than the rest of the video"

    sentence = (
        f"The references stop their opening beat at {profile.hook_seconds:.1f}s — about "
        f"{profile.hook_words} words at {rate:.1f} words a second, {opens} "
        f"({body:.1f} words a second, {profile.words_per_minute:.0f} a minute). "
        f"Measured across {profile.hooks_measured} of "
        f"{profile.references} reference(s), confidence {profile.confidence}.")
    return {
        "seconds": profile.hook_seconds,
        "words": profile.hook_words,
        "words_per_second": rate,
        "share": profile.hook_share,
        "body_words_per_second": body,
        "opens": opens,
        "delivery_trend": profile.delivery_trend,
        "references": profile.hooks_measured,
        "confidence": profile.confidence,
        "sentence": sentence,
        "not_claimed": dict(profile.not_claimed),
    }


@dataclass(frozen=True)
class WritingBudget:
    """What a script is written to: the rate, the opening window, and where each came from.

    One object rather than two functions because three callers read both numbers — the
    stage that writes the script, the gate that cuts the opening out of it, and the ledger
    that reserves against both — and a caller taking the rate from a measurement and the
    window from a constant would be holding credits for a hook nobody is going to cut.

    `note` is not decoration. A fallback that does not say it fell back is indistinguishable
    from a measurement, and that is precisely how this app came to have a `semantic` block
    on every learned reference and a script written as though it had never looked.
    """

    words_per_second: float
    hook_seconds: float
    measured: bool
    hook_measured: bool
    hook: dict
    note: str

    def words_for(self, seconds: float) -> int:
        """How many words this channel says over `seconds` of finished video.

        The conversion itself, so the reserve and the prompt cannot round it differently.
        """
        return max(0, int(max(0.0, float(seconds or 0.0)) * self.words_per_second))


def writing_budget(narrative: NarrativeProfile | dict | None) -> WritingBudget:
    """The two numbers a script is written to for this channel.

    The one place a measured narrative becomes a rate and a window, so the stage that
    writes the script, the gate that watches its opening and the ledger that reserves
    against both cannot disagree — which is the failure the two hard-coded literals were
    already an instance of, one file apart.

    An unusable profile falls back to the shipped defaults rather than to whatever one
    thin reference happened to say, and says which in `note`. See `NarrativeProfile.usable`
    — the gate is `SourcingProfile.usable`'s, unchanged.
    """
    if isinstance(narrative, dict):
        narrative = NarrativeProfile.from_dict(narrative)

    if narrative is None or not narrative.usable:
        # The measurement's own first note, not a sentence written here. "Video editing
        # tools are not installed" and "fifteen words is not a channel" send the operator
        # to two different places, and a fallback that says only "not measured" sends them
        # nowhere.
        why = "no reference has been learned for this channel"
        if narrative is not None and narrative.notes:
            why = narrative.notes[0]
        elif narrative is not None and narrative.references:
            why = f"the learned references graded {narrative.confidence} confidence"
        return WritingBudget(
            words_per_second=WORDS_PER_SECOND,
            hook_seconds=HOOK_SECONDS,
            measured=False,
            hook_measured=False,
            hook={},
            note=(f"{why} — writing at the shipped {WORDS_PER_SECOND} words a second and "
                  f"judging the opening on {HOOK_SECONDS:.0f}s"),
        )

    # The rate is usable and the hook is a second measurement on top of it. A reference
    # that never pauses has a perfectly good rate and no boundary in it at all, so the two
    # are gated separately — collapsing them would throw away a measured rate because the
    # narrator did not stop for breath.
    hook_measured = narrative.hook_seconds > 0 and narrative.hooks_measured > 0
    hook_seconds = narrative.hook_seconds if hook_measured else HOOK_SECONDS

    note = (f"writing at the learned {narrative.words_per_second:.2f} words a second "
            f"({narrative.words_per_minute:.0f} a minute) rather than the shipped "
            f"{WORDS_PER_SECOND}")
    if hook_measured:
        note = (f"{note}, and judging the opening on {hook_seconds:.1f}s rather than "
                f"{HOOK_SECONDS:.0f}s")
    else:
        note = (f"{note}. No reference could be sectioned, so the opening keeps the "
                f"shipped {HOOK_SECONDS:.0f}s window")

    return WritingBudget(
        words_per_second=narrative.words_per_second,
        hook_seconds=hook_seconds,
        measured=True,
        hook_measured=hook_measured,
        hook=_hook_pattern(narrative) if hook_measured else {},
        note=note,
    )


# -------------------------------------------------------------------- blending


# Fields where a mix means "take one or the other", because there is no halfway.
_CATEGORICAL = ("pacing", "transition", "caption_position", "loudness_target",
                "map_style", "motion_preset")
_BOOLEAN = ("snap_cuts_to_beat", "ken_burns", "captions", "music_bed")


def blend(first: EditingStyle, second: EditingStyle, weight: float = 0.5, *,
          name: str = "") -> EditingStyle:
    """Mix two styles. `weight` is how much of `second` to take, 0..1.

    Numbers interpolate. Categoricals and booleans do not — there is no style halfway
    between a cut and a dissolve, and averaging "bottom third" with "centre" would put
    the captions somewhere neither creator puts them. Those switch at the halfway
    point, which is the only choice that keeps the result a style someone could
    actually have.
    """
    amount = max(0.0, min(1.0, weight))
    mixed = replace(first, name=name or f"{first.name} x {second.name}")

    for key, bounds in _NUMERIC_BOUNDS.items():
        if not hasattr(mixed, key):
            continue
        low = float(getattr(first, key))
        high = float(getattr(second, key))
        value = low + (high - low) * amount
        setattr(mixed, key, max(bounds[0], min(bounds[1], value)))

    for key in ("caption_max_seconds", "music_gain_db", "duck_depth_db"):
        low, high = float(getattr(first, key)), float(getattr(second, key))
        setattr(mixed, key, low + (high - low) * amount)
    for key in ("caption_max_chars", "caption_max_lines"):
        low, high = int(getattr(first, key)), int(getattr(second, key))
        setattr(mixed, key, round(low + (high - low) * amount))

    winner = second if amount >= 0.5 else first
    for key in _CATEGORICAL + _BOOLEAN:
        setattr(mixed, key, getattr(winner, key))

    # The palette comes whole from the dominant side, for the same reason learn picks
    # one intact palette rather than averaging.
    mixed.palette = list(winner.palette)
    mixed.spread = {}
    mixed.notes = []
    mixed.provenance = {
        "origin": "blend",
        "parents": [first.key, second.key],
        "weight": round(amount, 3),
        "blended_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    return mixed


# ------------------------------------------------------------------- storage


def available(directory: Path | str = DEFAULT_DIRECTORY) -> list[dict]:
    """Every saved style, newest first, as summary rows for a list view."""
    folder = Path(directory)
    rows: list[dict] = []
    if not folder.exists():
        return rows
    for path in sorted(folder.glob("*.json")):
        try:
            style = EditingStyle.load(path)
        except (ValueError, OSError, json.JSONDecodeError):
            continue
        rows.append({
            "key": style.key,
            "name": style.name,
            "summary": style.summary(),
            "origin": style.provenance.get("origin", "?"),
            "sample_size": style.provenance.get("sample_size", 0),
            "learned_at": style.provenance.get("learned_at")
            or style.provenance.get("blended_at", ""),
            "notes": style.notes,
        })
    rows.sort(key=lambda row: row["learned_at"], reverse=True)
    return rows


def get(name: str, directory: Path | str = DEFAULT_DIRECTORY) -> EditingStyle:
    path = Path(directory) / f"{slug(name)}.json"
    if not path.exists():
        known = [row["key"] for row in available(directory)]
        raise KeyError(f"no editing style {name!r}; have {known}")
    return EditingStyle.load(path)


def delete(name: str, directory: Path | str = DEFAULT_DIRECTORY) -> bool:
    path = Path(directory) / f"{slug(name)}.json"
    if path.exists():
        path.unlink()
        return True
    return False
