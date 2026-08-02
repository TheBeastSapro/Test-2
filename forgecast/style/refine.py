"""Improving a learned style instead of copying it.

## The problem with a faithful copy

`learn` is deliberately descriptive: it reports what a reference actually does. That
includes what the reference does badly. Real channels ship videos with crushed blacks,
captions held for eight seconds, a cut every 2.0 seconds exactly for eleven minutes,
and audio six decibels under the platform target. Reproducing those faithfully
produces something that reads as an imitation of that channel *including its
weaknesses* — the "made by someone cheaper" result.

## What separates an upgrade from an opinion

The temptation is to "improve" by taste, which is how you get a style that is neither
the reference's nor good. So every correction here has to clear a bar: it fixes
something that is **measurably** wrong, against a threshold that can be stated, for a
reason that is about how the video is perceived rather than how it looks to me.

Each one is a `Refinement` with the field, the old value, the new value, and the
reason. Nothing is changed silently, and `refine` hands back the list, so the operator
can always see the difference between "this is how they cut" and "this is how we cut,
and here is why we departed".

## What is deliberately *not* corrected here

Anything that is a genuine stylistic choice. A slow channel stays slow. A desaturated
channel stays desaturated. A channel that never uses dissolves never gets one. The
corrections below only fire when a value crosses into territory where it stops being a
choice and starts being a defect.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .editing import EditingStyle

# Below this a shot is gone before the eye has resolved what is in it. The figure is
# the conservative end of the range usually cited for recognising a novel image;
# faster cutting works only when the viewer already knows the subject.
MIN_READABLE_SHOT = 0.5

# A cut rhythm this even has no accent in it — every shot the same length reads as a
# slideshow on a timer, and the viewer stops expecting anything to happen.
MIN_JITTER = 0.15
JITTER_FLOOR = 0.22

# `eq` contrast beyond this crushes shadow detail and blows highlights on the same
# frame; saturation beyond it pushes skin tones orange and skies to a flat cyan.
MAX_CONTRAST = 1.45
MAX_SATURATION = 1.55
MIN_SATURATION = 0.35

# A caption held longer than this has been read several times over, and the viewer's
# eye has already left it. Matches the render stage's own cue ceiling.
MAX_CAPTION_SECONDS = 4.0

# A faceless video with no motion graphics at all is a slideshow with a voice over it.
MIN_MOTION_FOR_FACELESS = 0.16

# How much shorter the opening shots run than the body. Front-loading the pace is the
# one broadly-supported retention move: the decision to keep watching is made early,
# and a faster open buys the room to slow down later.
OPENING_PACE = 0.82


@dataclass
class Refinement:
    """One departure from the reference, with the reason it was made."""

    field: str
    was: object
    now: object
    why: str

    def as_dict(self) -> dict:
        return {"field": self.field, "was": self.was, "now": self.now, "why": self.why}

    def __str__(self) -> str:
        return f"{self.field}: {self.was} -> {self.now} ({self.why})"


def _shot_floor(style: EditingStyle) -> list[Refinement]:
    changes = []
    if style.target_shot_seconds < MIN_READABLE_SHOT:
        changes.append(Refinement(
            "target_shot_seconds", round(style.target_shot_seconds, 2), MIN_READABLE_SHOT,
            f"below {MIN_READABLE_SHOT}s a shot is gone before the eye resolves it",
        ))
        style.target_shot_seconds = MIN_READABLE_SHOT
        # `cuts_per_minute` is the same fact stated the other way round. Leaving it
        # alone would ship a style claiming 158 cuts a minute out of half-second
        # shots, and the two numbers disagreeing is worse than either being wrong.
        corrected = round(60.0 / MIN_READABLE_SHOT, 2)
        if abs(style.cuts_per_minute - corrected) > 0.5:
            changes.append(Refinement(
                "cuts_per_minute", round(style.cuts_per_minute, 1), corrected,
                "kept consistent with the corrected shot length",
            ))
            style.cuts_per_minute = corrected
    if style.shot_seconds_min < MIN_READABLE_SHOT:
        changes.append(Refinement(
            "shot_seconds_min", round(style.shot_seconds_min, 2), MIN_READABLE_SHOT,
            "the shortest shot must still be readable",
        ))
        style.shot_seconds_min = MIN_READABLE_SHOT
    if style.shot_seconds_max < style.shot_seconds_min:
        changes.append(Refinement(
            "shot_seconds_max", round(style.shot_seconds_max, 2),
            round(style.shot_seconds_min * 2, 2),
            "the range was inverted by the floor correction",
        ))
        style.shot_seconds_max = style.shot_seconds_min * 2
    return changes


def _rhythm_variation(style: EditingStyle) -> list[Refinement]:
    if style.jitter >= MIN_JITTER:
        return []
    was = round(style.jitter, 3)
    style.jitter = JITTER_FLOOR
    return [Refinement(
        "jitter", was, JITTER_FLOOR,
        "every shot the same length reads as a slideshow on a timer; varying the "
        "length is what makes a cut land",
    )]


def _grade_limits(style: EditingStyle) -> list[Refinement]:
    changes = []
    if style.contrast > MAX_CONTRAST:
        changes.append(Refinement(
            "contrast", round(style.contrast, 3), MAX_CONTRAST,
            "beyond this the shadows crush and the highlights blow on the same frame",
        ))
        style.contrast = MAX_CONTRAST
    if style.saturation > MAX_SATURATION:
        changes.append(Refinement(
            "saturation", round(style.saturation, 3), MAX_SATURATION,
            "beyond this skin goes orange and sky goes flat cyan",
        ))
        style.saturation = MAX_SATURATION
    elif 0.0 < style.saturation < MIN_SATURATION:
        changes.append(Refinement(
            "saturation", round(style.saturation, 3), MIN_SATURATION,
            "near-monochrome by accident rather than by design; a deliberate "
            "black-and-white look sets saturation to zero",
        ))
        style.saturation = MIN_SATURATION
    return changes


def _caption_discipline(style: EditingStyle) -> list[Refinement]:
    changes = []
    if style.caption_max_seconds > MAX_CAPTION_SECONDS:
        changes.append(Refinement(
            "caption_max_seconds", style.caption_max_seconds, MAX_CAPTION_SECONDS,
            "a card held longer than this has been read twice and the eye has left it",
        ))
        style.caption_max_seconds = MAX_CAPTION_SECONDS
    if style.caption_max_chars > 46:
        changes.append(Refinement(
            "caption_max_chars", style.caption_max_chars, 46,
            "lines longer than this wrap unpredictably at mobile width",
        ))
        style.caption_max_chars = 46
    if style.caption_max_lines > 2:
        changes.append(Refinement(
            "caption_max_lines", style.caption_max_lines, 2,
            "a third line covers the lower third of the picture",
        ))
        style.caption_max_lines = 2
    return changes


def _motion_floor(style: EditingStyle) -> list[Refinement]:
    if style.motion_intensity >= MIN_MOTION_FOR_FACELESS:
        return []
    was = round(style.motion_intensity, 3)
    style.motion_intensity = MIN_MOTION_FOR_FACELESS
    return [Refinement(
        "motion_intensity", was, MIN_MOTION_FOR_FACELESS,
        "with no graphics at all a faceless video is a slideshow with a voice on it; "
        "this is the minimum that still reads as restrained",
    )]


def _front_load(style: EditingStyle) -> list[Refinement]:
    if style.pacing == "accelerating":
        return []
    was = style.pacing
    style.pacing = "decelerating"
    return [Refinement(
        "pacing", was, "decelerating",
        "the decision to keep watching is made in the first fifteen seconds, so the "
        "open cuts faster and the body earns the room to slow down",
    )]


def _loudness(style: EditingStyle) -> list[Refinement]:
    if style.loudness_target:
        return []
    style.loudness_target = "youtube"
    return [Refinement(
        "loudness_target", "", "youtube",
        "an unmastered mix plays quiet next to everything else in the feed",
    )]


# In application order. Shot floor runs before rhythm so the variation correction sees
# corrected lengths, and grade limits run before nothing in particular — they are
# independent, and the order is only fixed so the report reads the same way twice.
REFINEMENTS = (
    ("shot floor", _shot_floor),
    ("rhythm variation", _rhythm_variation),
    ("grade limits", _grade_limits),
    ("caption discipline", _caption_discipline),
    ("motion floor", _motion_floor),
    ("opening pace", _front_load),
    ("loudness", _loudness),
)


def refine(
    style: EditingStyle, *, name: str = "", skip: tuple[str, ...] = (),
) -> tuple[EditingStyle, list[Refinement]]:
    """Return an improved copy of `style` and the list of departures made.

    Never mutates the input. A learned style is evidence about a reference, and
    evidence that changes when you look at it is not evidence — so the original stays
    on disk exactly as measured, and the refined version is a separate, named thing
    whose provenance points back at its parent.

    `skip` names refinements to leave out, for the case where the operator has decided
    the reference was right and the rule is wrong. Which is allowed: these are strong
    defaults, not laws.
    """
    working = replace(style, name=name or f"{style.name} (refined)")
    working.palette = list(style.palette)
    working.notes = list(style.notes)

    applied: list[Refinement] = []
    for label, rule in REFINEMENTS:
        if label in skip:
            continue
        applied.extend(rule(working))

    working.provenance = {
        "origin": "refined",
        "parent": style.key,
        "refinements": [item.as_dict() for item in applied],
        "skipped": list(skip),
    }
    if applied:
        working.notes = [*working.notes, *(str(item) for item in applied)]
    return working, applied
