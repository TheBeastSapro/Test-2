"""Motion presets: a look, stored as data, that can be learned from a reference.

A preset is not code. It is a small bag of numbers — how fast things enter, how far a
card grows, where captions sit, which accent colour — that `build_*` turns into the
`Text`/`ImageCard`/`Band` elements of `compose.py`. That distinction is the whole point
of this module: because a preset is data, it can be **measured off a reference video and
saved**, and the next run can ask for "the look from that channel" by name.

So there are two ways to get one:

  LIBRARY["card_reveal"]                     a hand-tuned starting point
  derive_from_profile(style_profile_dict)    measured from a reference you supplied

Both produce the same type, and `save()`/`load()` round-trip either to JSON. A derived
preset keeps a `provenance` block holding the numbers it was derived from, so months
later you can see *why* a preset moves the way it does instead of guessing.

## What "intensity" means

One scalar, 0..1, drives the aggression of every move. It is derived — not chosen —
from three measurements that all correlate with how busy an edit feels:

  cuts per minute        pacing; a 40 cuts/min edit cannot afford a 0.9s entry
  mean motion magnitude  how much the frame itself moves
  graphic density        how much non-photographic content is on screen

Each is normalised against a ceiling drawn from the reference set measured while
building the vision engine, then averaged with pacing weighted double, because pacing
is what a viewer reads as "energy" first.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from .compose import Band, ImageCard, Text
from .keyframe import Track, fade_in_out

SCHEMA_VERSION = "motion-preset/1"

# Ceilings for normalising measurements into 0..1. These are not arbitrary: they are
# the top of the range observed across the reference clips used to build the vision
# engine, so a value at the ceiling means "as busy as the busiest thing measured".
CUTS_PER_MINUTE_CEILING = 45.0
MOTION_MAGNITUDE_CEILING = 0.18
GRAPHIC_DENSITY_CEILING = 0.25

ENTRY_FAMILIES = ("pop", "slide", "rise", "wipe")


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _lerp(low: float, high: float, amount: float) -> float:
    return low + (high - low) * _clamp(amount)


@dataclass
class MotionPreset:
    """A reusable motion look. Every field is JSON-serialisable on purpose."""

    name: str
    intensity: float = 0.5

    # -- entries ---------------------------------------------------------------
    entry: str = "rise"              # pop | slide | rise | wipe
    entry_duration: float = 0.45
    easing: str = "ease_out"
    stagger: float = 0.35            # gap between successive elements
    hold: float = 2.6                # seconds an element stays before leaving
    exit_duration: float = 0.3

    # -- type ------------------------------------------------------------------
    caption_zone: str = "bottom_third"
    caption_style: str = "band"      # band | box | outline | plain
    text_height_ratio: float = 0.055  # cap height as a fraction of frame height
    text_colour: str = "white"
    accent_colour: str = "#ffcc33"
    band_opacity: float = 0.62

    # -- cards -----------------------------------------------------------------
    card_scale: float = 0.5          # fraction of frame width at rest
    card_zoom: float = 1.12          # end scale / start scale over the card's life
    card_tilt: float = 0.0           # radians it settles through
    card_shadow: bool = True

    # -- rhythm ----------------------------------------------------------------
    beat_sync: bool = False
    bpm: float | None = None

    provenance: dict = field(default_factory=lambda: {"origin": "built_in"})

    # -- serialisation ---------------------------------------------------------

    def as_dict(self) -> dict:
        return {"schema_version": SCHEMA_VERSION, **asdict(self)}

    @classmethod
    def from_dict(cls, payload: dict) -> MotionPreset:
        fields = {key for key in cls.__dataclass_fields__}
        known = {key: value for key, value in payload.items() if key in fields}
        if "name" not in known:
            raise ValueError("a motion preset needs a name")
        return cls(**known)

    def save(self, directory: Path | str = "./storage/motion_presets") -> Path:
        path = Path(directory) / f"{slug(self.name)}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.as_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path | str) -> MotionPreset:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def variant(self, name: str, **changes) -> MotionPreset:
        """A copy with fields overridden — how a user tweaks a learned preset."""
        return replace(self, name=name, **changes)

    # -- element construction --------------------------------------------------

    def caption(self, text: str, *, start: float, width: int, height: int,
                duration: float | None = None, accent: bool = False) -> list:
        """A caption with the preset's entry move, plus its backing if any."""
        span = duration if duration is not None else self.hold
        size = max(14, int(self.text_height_ratio * height))
        y = _ZONES.get(self.caption_zone, 0.82)
        # A fade that does not fit its window would still be rising when `enable`
        # switches off, so the line would vanish mid-move instead of leaving.
        rise = min(self.entry_duration, span * 0.45)
        fall = min(self.exit_duration, span * 0.35)

        elements: list = []
        if self.caption_style == "band":
            elements.append(Band(
                start=start, duration=span,
                colour=f"black@{self.band_opacity:.2f}",
                y=y - 0.07, height_fraction=0.15,
            ))

        move = self._entry_track(axis="x", width=width, height=height)
        item = Text(
            start=start, duration=span, text=text, size=size,
            colour=self.accent_colour if accent else self.text_colour,
            x=move if self.entry in {"slide", "wipe"} else 0.5,
            y=self._entry_y(y) if self.entry == "rise" else y,
            alpha=fade_in_out(span, rise=rise, fall=fall),
            box=self.caption_style == "box",
            box_colour=f"black@{self.band_opacity:.2f}",
            border=2 if self.caption_style == "outline" else 0,
        )
        elements.append(item)
        return elements

    def card(self, path: Path, *, start: float, width: int,
             duration: float | None = None) -> ImageCard:
        """An image card that grows and settles according to the preset."""
        span = duration if duration is not None else self.hold + self.entry_duration
        rest = self.card_scale

        scale: Track | float
        if abs(self.card_zoom - 1.0) < 0.005:
            scale = rest
        else:
            # Grow *through* the resting scale rather than up to it, so the card is
            # never smaller than intended at the moment it becomes readable.
            scale = (Track("scale")
                     .at(0.0, rest / self.card_zoom, "linear")
                     .at(span, rest * self.card_zoom, "ease_out"))

        rotation: Track | float = 0.0
        if abs(self.card_tilt) > 0.001:
            rotation = (Track("rotation")
                        .at(0.0, self.card_tilt, "linear")
                        .at(min(span, self.entry_duration * 2.2), 0.0, "ease_out"))

        return ImageCard(
            start=start, duration=span, path=path,
            scale=scale, x=0.5, y=0.44, rotation=rotation,
            fade_in=self.entry_duration * 0.7,
            fade_out=self.exit_duration,
            shadow=self.card_shadow,
        )

    def lower_third(self, headline: str, subhead: str, *, start: float,
                    width: int, height: int, duration: float = 4.0) -> list:
        """Two stacked lines over a band, the second staggered behind the first."""
        size = max(16, int(self.text_height_ratio * height))
        y = _ZONES.get(self.caption_zone, 0.82)
        elements: list = [Band(
            start=start, duration=duration,
            colour=f"black@{max(self.band_opacity, 0.55):.2f}",
            y=y - 0.06, height_fraction=0.19,
        )]
        slide = self._entry_track(axis="x", width=width, height=height)
        elements.append(Text(
            start=start, duration=duration, text=headline, size=size,
            colour=self.accent_colour, x=slide if self.entry != "pop" else 0.3,
            y=y - 0.02,
            alpha=fade_in_out(duration, rise=self.entry_duration,
                              fall=self.exit_duration),
        ))
        elements.append(Text(
            start=start + self.stagger, duration=max(0.4, duration - self.stagger),
            text=subhead, size=max(12, int(size * 0.62)),
            colour=self.text_colour, x=0.3, y=y + 0.06,
            alpha=fade_in_out(max(0.4, duration - self.stagger),
                              rise=self.entry_duration, fall=self.exit_duration),
        ))
        return elements

    def kinetic(self, lines: list[str], *, start: float, width: int,
                height: int, per_line: float | None = None) -> list:
        """One line at a time, each replacing the last.

        The step is the preset's stagger, so a fast-cut reference produces rapid-fire
        type and a slow one produces something readable.

        Windows are butt-joined, not overlapped. Overlapping them would put two lines
        at the same position for the length of the crossfade, and two sets of letters
        at 50% over each other is illegible — it reads as a smear, not a transition.
        Each line's own fade in and out happens inside its own window, which gives a
        clean swap at the joint.
        """
        step = per_line if per_line is not None else max(0.5, self.stagger * 2.4)
        elements: list = []
        for index, line in enumerate(lines):
            elements.extend(self.caption(
                line, start=start + index * step, width=width, height=height,
                duration=step,
                accent=(index == len(lines) - 1 and len(lines) > 1),
            ))
        return elements

    # -- entry moves -----------------------------------------------------------

    def _entry_track(self, *, axis: str, width: int, height: int) -> Track:
        """Horizontal entry: slide in from the side, or wipe across from further out."""
        travel = 0.16 if self.entry == "slide" else 0.30
        return (Track(f"{axis}_entry")
                .at(0.0, 0.5 - travel, "linear")
                .at(self.entry_duration, 0.5, self.easing))

    def _entry_y(self, rest: float) -> Track:
        """Vertical entry: rise into place from below the resting line."""
        return (Track("y_entry")
                .at(0.0, rest + 0.06, "linear")
                .at(self.entry_duration, rest, self.easing))


_ZONES = {"bottom_third": 0.82, "centre": 0.5, "top_third": 0.16, "none": 0.82}


def slug(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return cleaned or "preset"


# ------------------------------------------------------------------- built-ins


LIBRARY: dict[str, MotionPreset] = {
    "card_reveal": MotionPreset(
        name="card_reveal", intensity=0.45, entry="rise", entry_duration=0.5,
        hold=3.4, caption_style="band", card_scale=0.56, card_zoom=1.14,
        card_tilt=0.0, accent_colour="#ffd166",
    ),
    "text_pop": MotionPreset(
        name="text_pop", intensity=0.75, entry="pop", entry_duration=0.18,
        stagger=0.16, hold=1.5, exit_duration=0.16, caption_style="outline",
        text_height_ratio=0.075, accent_colour="#ff5d5d", card_zoom=1.2,
    ),
    "kinetic_type": MotionPreset(
        name="kinetic_type", intensity=0.9, entry="slide", entry_duration=0.14,
        stagger=0.12, hold=0.9, exit_duration=0.12, caption_style="plain",
        text_height_ratio=0.09, caption_zone="centre", accent_colour="#4dd4ff",
        card_zoom=1.24, card_tilt=0.05,
    ),
    "slide_in": MotionPreset(
        name="slide_in", intensity=0.55, entry="slide", entry_duration=0.34,
        stagger=0.28, hold=2.8, caption_style="band", card_zoom=1.1,
    ),
    "lower_third": MotionPreset(
        name="lower_third", intensity=0.3, entry="wipe", entry_duration=0.55,
        stagger=0.4, hold=4.2, caption_style="band", band_opacity=0.7,
        text_height_ratio=0.05, card_zoom=1.06, card_shadow=True,
    ),
    "push_in": MotionPreset(
        name="push_in", intensity=0.35, entry="rise", entry_duration=0.6,
        stagger=0.45, hold=4.0, caption_style="plain", card_scale=0.62,
        card_zoom=1.18, card_tilt=0.0, card_shadow=False,
    ),
}


def by_intensity(intensity: float) -> MotionPreset:
    """The built-in whose intensity is nearest — the fallback when nothing measured."""
    return min(LIBRARY.values(), key=lambda item: abs(item.intensity - intensity))


def get(name: str, *, directory: Path | str = "./storage/motion_presets") -> MotionPreset:
    """Resolve by name: a saved preset first, then a built-in.

    Saved wins because a preset learned from the user's own reference is more
    specific than anything shipped here, and because that is what re-using a name
    is *for* — overriding the default look with one that was measured.
    """
    path = Path(directory) / f"{slug(name)}.json"
    if path.exists():
        return MotionPreset.load(path)
    if name in LIBRARY:
        return LIBRARY[name]
    raise KeyError(
        f"no motion preset named {name!r}: not saved in {directory} and not one of "
        f"{sorted(LIBRARY)}"
    )


def available(directory: Path | str = "./storage/motion_presets") -> list[dict]:
    """Everything selectable, learned presets marked as such — for the UI."""
    out = [
        {"name": preset.name, "intensity": preset.intensity, "origin": "built_in"}
        for preset in sorted(LIBRARY.values(), key=lambda item: item.intensity)
    ]
    folder = Path(directory)
    if folder.exists():
        for path in sorted(folder.glob("*.json")):
            try:
                preset = MotionPreset.load(path)
            except Exception:
                continue        # a hand-edited file must not break the picker
            origin = (preset.provenance or {}).get("origin", "learned")
            out = [item for item in out if item["name"] != preset.name]
            out.append({
                "name": preset.name, "intensity": preset.intensity,
                "origin": origin, "path": str(path),
                "reference": (preset.provenance or {}).get("reference"),
            })
    return out


# ------------------------------------------------------------------- learning


def derive_intensity(profile: dict) -> tuple[float, dict]:
    """Measured intensity, with the numbers behind it returned for the record."""
    rhythm = profile.get("shot_rhythm") or {}
    motion = profile.get("motion") or {}
    overlay = profile.get("overlay") or {}

    cuts = float(rhythm.get("cuts_per_minute") or 0.0)
    magnitude = float(motion.get("mean_magnitude") or 0.0)
    density = float(overlay.get("graphic_density") or 0.0)

    pace = _clamp(cuts / CUTS_PER_MINUTE_CEILING)
    movement = _clamp(magnitude / MOTION_MAGNITUDE_CEILING)
    graphics = _clamp(density / GRAPHIC_DENSITY_CEILING)

    # Pacing weighted double: it is the first thing a viewer reads as energy.
    intensity = _clamp((pace * 2 + movement + graphics) / 4)
    return intensity, {
        "cuts_per_minute": round(cuts, 2), "pace_component": round(pace, 3),
        "mean_motion_magnitude": round(magnitude, 4),
        "motion_component": round(movement, 3),
        "graphic_density": round(density, 4), "graphics_component": round(graphics, 3),
    }


def derive_from_profile(profile: dict, *, name: str = "",
                        reference: str = "") -> MotionPreset:
    """Turn a measured StyleProfile into a preset.

    Everything here is read off the measurement — nothing is asked for and nothing is
    invented. Where a measurement is missing the built-in default stands, which is why
    a profile from a clip with no audio still yields a usable preset (just without
    beat sync).
    """
    intensity, components = derive_intensity(profile)

    rhythm = profile.get("shot_rhythm") or {}
    motion = profile.get("motion") or {}
    overlay = profile.get("overlay") or {}
    colour = profile.get("colour") or {}
    audio = profile.get("audio") or {}
    beats = profile.get("beat_alignment") or {}

    # Entries must fit inside a shot, or the move is still arriving when the cut
    # lands. Half the median shot is the longest that reliably reads as complete.
    median_shot = float((rhythm.get("shot_length") or {}).get("median") or 3.0)
    entry_duration = _clamp(min(median_shot * 0.45, _lerp(0.6, 0.14, intensity)),
                            0.1, 0.9)

    # A busier edit gets a punchier entry family. wipe is deliberately reserved for
    # the calmest end — a 0.55s wipe in a 40-cuts/min edit is never on screen long
    # enough to finish.
    if intensity > 0.72:
        entry = "pop"
    elif intensity > 0.5:
        entry = "slide"
    elif intensity > 0.28:
        entry = "rise"
    else:
        entry = "wipe"

    persistence = float(overlay.get("caption_persistence") or 0.0)
    zone = overlay.get("caption_zone") or "bottom_third"
    if zone == "none":
        zone = "bottom_third"
    # Persistent burned-in captions read as a solid style; occasional ones are
    # usually titles, which want a band behind them to separate from the footage.
    if persistence > 0.6:
        caption_style = "outline"
    elif persistence > 0.25:
        caption_style = "band"
    else:
        caption_style = "box"

    brightness = float(colour.get("brightness") or 110.0)
    palette = colour.get("palette") or []
    accent = _accent_from(palette, brightness)

    magnitude = float(motion.get("mean_magnitude") or 0.0)
    # Cards should move about as much as the footage does, or they read as pasted on.
    card_zoom = round(1.0 + _clamp(magnitude / MOTION_MAGNITUDE_CEILING) * 0.24 +
                      intensity * 0.06, 3)
    tilt = round(_lerp(0.0, 0.06, intensity) if intensity > 0.6 else 0.0, 4)

    bpm = audio.get("tempo_bpm") or audio.get("bpm")
    on_beat = beats.get("cuts_on_beat_ratio")
    beat_sync = bool(beats.get("measured") and on_beat and float(on_beat) >= 0.5)

    preset = MotionPreset(
        name=name or f"ref_{slug(reference)[:32]}" or "learned",
        intensity=round(intensity, 3),
        entry=entry,
        entry_duration=round(entry_duration, 3),
        easing="ease_out" if intensity < 0.8 else "ease_in_out",
        stagger=round(_clamp(_lerp(0.45, 0.12, intensity), 0.08, 0.6), 3),
        hold=round(_clamp(median_shot * 0.9, 0.8, 5.0), 3),
        exit_duration=round(_clamp(entry_duration * 0.7, 0.1, 0.5), 3),
        caption_zone=zone,
        caption_style=caption_style,
        text_height_ratio=round(_lerp(0.05, 0.085, intensity), 4),
        text_colour="white" if brightness < 165 else "#101418",
        accent_colour=accent,
        band_opacity=round(_clamp(0.5 + (1 - brightness / 255) * 0.3, 0.4, 0.8), 3),
        card_scale=round(_lerp(0.62, 0.48, intensity), 3),
        card_zoom=card_zoom,
        card_tilt=tilt,
        card_shadow=brightness > 60,   # a shadow on near-black footage is invisible
        beat_sync=beat_sync,
        bpm=round(float(bpm), 2) if bpm else None,
        provenance={
            "origin": "reference",
            "reference": reference or (profile.get("source") or {}).get("path", ""),
            "schema_version": profile.get("schema_version", ""),
            "edit_signature": profile.get("edit_signature", []),
            "measured": components,
            "caption_persistence": round(persistence, 3),
            "grade_label": colour.get("grade_label", ""),
            "confidence": profile.get("confidence", {}),
        },
    )

    if beat_sync and bpm:
        # Snap the stagger to a musical subdivision so staged text lands with the
        # track instead of drifting against it.
        beat = 60.0 / float(bpm)
        subdivision = beat / 2 if preset.stagger < beat * 0.75 else beat
        preset = replace(preset, stagger=round(subdivision, 3))

    return preset


def _accent_from(palette: list[dict], brightness: float) -> str:
    """The most colourful palette entry, brightened enough to read as an accent.

    The dominant colour is usually the background, which is exactly what an accent
    must *not* be, so entries are ranked by saturation rather than share.
    """
    best, best_score = None, -1.0
    for entry in palette:
        hex_value = str(entry.get("hex") or "")
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", hex_value):
            continue
        red, green, blue = (int(hex_value[index:index + 2], 16)
                            for index in (1, 3, 5))
        high, low = max(red, green, blue), min(red, green, blue)
        saturation = (high - low) / high if high else 0.0
        if saturation > best_score:
            best, best_score = (red, green, blue), saturation

    if best is None or best_score < 0.15:
        # Nothing colourful enough to pull from — fall back on a legible default
        # rather than picking a grey and calling it an accent.
        return "#ffd166" if brightness < 165 else "#c2410c"

    red, green, blue = best
    if max(best) < 160:                     # lift a dark accent into readability
        factor = 160 / max(1, max(best))
        red, green, blue = (min(255, int(channel * factor)) for channel in best)
    return f"#{red:02x}{green:02x}{blue:02x}"


def learn(profile: dict, *, name: str = "", reference: str = "",
          directory: Path | str = "./storage/motion_presets") -> tuple[MotionPreset, Path]:
    """Derive a preset from a measurement and save it under a reusable name."""
    preset = derive_from_profile(profile, name=name, reference=reference)
    return preset, preset.save(directory)
