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
