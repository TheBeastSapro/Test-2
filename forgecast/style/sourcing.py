"""How a reference channel gets its pictures, measured rather than configured.

## Why this exists

Two numbers decided what a run costs and what it looks like, and both were constants:
one beat in three could be animated, one in four could take the premium model. They were
reasonable guesses and they were wrong for most channels — a cinematic storytelling
channel moves nearly every shot, a white-background explainer moves almost none, and a
listicle sits between them. A guess baked into `render/cutting.py` is a guess every
channel pays for.

The reference channel already answers this. `vision.visual.motion_profile` runs on every
shot of a learned reference and reports whether it moved and how; `colour_profile`
reports what the frame is mostly made of. Both were measured, summarised into a
distribution, and then used for nothing but choosing a Ken Burns rate. This reads the
same measurements and turns them into the two budgets and the background treatment.

## What can honestly be measured, and what cannot

**Whether a shot moves** — yes. A still under a Ken Burns push shows low, smooth,
edge-weighted change (`camera_move == "zoom"`); real footage shows higher change that is
not edge-weighted. That distinction is the whole animation budget.

**Whether the frame is a flat background** — yes. A white-background explainer is mostly
one near-neutral colour with cut-out subjects on it, which a palette measurement sees
plainly.

**Whether a shot was licensed, generated, or lifted from somewhere** — *no*, and this
module does not pretend otherwise. Nothing in a decoded frame says where it came from.
What it reports is how long the moving shots run, which is the number that matters for
an operator-directed clip: a channel that cuts sourced footage at three seconds tells you
to cut yours at three seconds, and the app can cap to it rather than to a figure someone
typed.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field

# A shot whose motion is a zoom at this magnitude or below is a still being pushed into,
# not footage. Above it, something in the frame is genuinely moving.
#
# The threshold is `motion_profile`'s own "subtle" boundary rather than a new number. A
# second threshold measuring the same quantity is a second answer to "did this move",
# and the two would drift the first time either was tuned.
STILL_MAGNITUDE = 0.05

# Where "mostly one colour" starts. A white-background explainer runs well above this —
# the subject is a cut-out on a flat field — while a photographic shot rarely passes it
# even when it has a lot of sky.
FLAT_COVERAGE = 0.55

# How near-neutral a flat background has to be to count as the white-card look rather
# than as a strong brand colour. Both are flat; only one wants cut-out treatment.
NEUTRAL_SPREAD = 28.0

# Bounds on what a measurement may conclude. A reference measured as animating every
# single shot is more likely a decode that classified badly than a channel with no
# stills, and inheriting 1.0 would put a whole video on the video endpoint.
MIN_SHARE, MAX_SHARE = 0.0, 0.85


@dataclass
class SourcingProfile:
    """What a reference does about pictures. Every field is JSON-serialisable."""

    # Share of shots that are moving footage rather than stills. Replaces the hard
    # `scenes // 3`, and is the single number that decides what a run costs.
    animation_share: float = 0.33
    # Share of shots worth the premium endpoint. Not directly measurable — nothing in a
    # frame says "this beat mattered" — so it is derived: the dearest quarter of the
    # animated shots, floored so a channel that animates little still gets one upgrade.
    hero_share: float = 0.25
    # Median length of the moving shots, in seconds — a *preference*, never a cap.
    #
    # The distinction matters and it is the operator's own: script and visual have to
    # stay in sync, so what is on screen is decided by the narration under it. A scene
    # of twenty seconds does not become one twenty-second clip because the reference
    # holds them that long, and it does not become a three-second clip and seventeen
    # seconds of nothing because the reference cuts fast. `render.cutting.plan_cuts`
    # already guarantees shots sum exactly to the narration; this says how many pieces
    # that scene should be cut into, which is the part the reference can answer.
    clip_seconds: float = 0.0
    # The white-card explainer look: subjects composited on a flat field.
    flat_background: bool = False
    background_colour: str = ""
    # How much of the measurement is worth trusting. `low` means the reference was too
    # short, too few shots, or classified with no confidence — and a low-confidence
    # profile is reported rather than applied.
    confidence: str = "low"
    shots_measured: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> SourcingProfile:
        known = {key: value for key, value in (payload or {}).items()
                 if key in cls.__dataclass_fields__}
        return cls(**known)

    @property
    def usable(self) -> bool:
        """Whether this should drive a run, as opposed to merely being shown.

        A profile measured off four shots is an anecdote. Applying it silently is how a
        channel ends up animating everything because one reference happened to open on a
        montage — so `learn` keeps it either way and the budget functions ask this first.
        """
        return self.confidence in {"medium", "high"} and self.shots_measured >= 8


def _moving(shot: dict) -> bool:
    """Did something in this shot actually move, or is it a still being pushed into?

    Reads `motion_profile`'s own output rather than re-deriving it. A `zoom` under the
    subtle threshold is Ken Burns on a plate — which is exactly what this app does to a
    still — so counting it as animation would have every channel inherit an animation
    share of one and every run priced as all-video.
    """
    motion = shot.get("motion") or {}
    magnitude = motion.get("magnitude")
    magnitude = float(magnitude) if isinstance(magnitude, (int, float)) else 0.0
    classification = str(motion.get("classification") or "")
    move = str(motion.get("camera_move") or "")

    if classification == "static":
        return False
    if move == "zoom" and magnitude <= STILL_MAGNITUDE:
        return False
    return magnitude > STILL_MAGNITUDE


def _rgb(row: dict) -> tuple[float, float, float] | None:
    """A palette row's colour. `visual._palette` writes `hex` and nothing else."""
    value = str(row.get("hex") or "").lstrip("#")
    if len(value) != 6:
        return None
    try:
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except ValueError:
        return None


def _flat(colour: dict) -> tuple[bool, str]:
    """Is this a flat-background look, and what colour is the field?

    Summed across neighbouring palette entries rather than read off the largest one, and
    that is not tidiness. `visual._palette` quantises to three bits per channel, so a
    white card with any grading across it splits between #f0f0f0 and #d0d0d0 and the
    largest single bucket can sit under a third — which would report the most obviously
    flat frame in the format as not flat.

    So: group the palette by how near-neutral each entry is, and ask whether the neutral
    entries together cover the frame. A photographic shot with a lot of sky does not pass
    this, because sky is blue.
    """
    palette = [row for row in (colour.get("palette") or []) if isinstance(row, dict)]
    if not palette:
        return False, ""

    neutral_share = 0.0
    brightest: tuple[float, str] = (-1.0, "")
    coloured: dict[str, float] = {}
    for row in palette:
        share = float(row.get("share") or 0.0)
        rgb = _rgb(row)
        if rgb is None:
            continue
        if (max(rgb) - min(rgb)) <= NEUTRAL_SPREAD:
            neutral_share += share
            mean = statistics.fmean(rgb)
            if mean > brightest[0]:
                brightest = (mean, str(row.get("hex") or ""))
        else:
            coloured[str(row.get("hex") or "")] = coloured.get(
                str(row.get("hex") or ""), 0.0) + share

    if neutral_share >= FLAT_COVERAGE:
        label = brightest[1] or ""
        if brightest[0] >= 170:
            label = label or "white"
        elif brightest[0] <= 70:
            label = label or "black"
        return True, label

    # A flat *brand* colour rather than a white card — same cut-out treatment, different
    # field, so it is reported rather than rounded down to "not flat".
    if coloured:
        best_hex, best_share = max(coloured.items(), key=lambda item: item[1])
        if best_share >= FLAT_COVERAGE:
            return True, best_hex
    return False, ""


def measure(per_shot: list[dict], *, colour: dict | None = None) -> SourcingProfile:
    """Read a learned reference's per-shot analysis into a sourcing profile.

    `per_shot` is what `vision.profile` already produces — one dict per detected shot
    with `motion`, `seconds` and the rest. Nothing new is decoded; this is arithmetic on
    a measurement the learn pass has been making and discarding.
    """
    shots = [shot for shot in (per_shot or []) if isinstance(shot, dict)]
    if not shots:
        return SourcingProfile(notes=["no shots were measured"])

    moving = [shot for shot in shots if _moving(shot)]
    share = len(moving) / len(shots)

    lengths = [float(shot.get("seconds") or 0.0) for shot in moving]
    lengths = [value for value in lengths if value > 0]
    clip_seconds = round(statistics.median(lengths), 2) if lengths else 0.0

    flat, background = _flat(colour or {})

    notes: list[str] = []
    confidence = "high"
    if len(shots) < 8:
        confidence = "low"
        notes.append(f"only {len(shots)} shots — too few to generalise from")
    elif len(shots) < 25:
        confidence = "medium"

    # Bounded, and the clamp is reported. A share of 1.0 is far more likely to be a
    # decode that classified badly than a channel with no stills in it, and inheriting
    # it silently puts a whole video on the video endpoint at the video endpoint's price.
    bounded = min(MAX_SHARE, max(MIN_SHARE, share))
    if bounded != round(share, 4) and abs(bounded - share) > 0.005:
        notes.append(f"measured {share:.0%} of shots moving, held at {bounded:.0%} — "
                     f"a reference that animates everything is usually a bad decode")

    return SourcingProfile(
        animation_share=round(bounded, 3),
        # A quarter of what moves, because the premium tier is only ever spent on an
        # animated beat — a still marked hero costs exactly what a still costs. Floored
        # at one beat's worth so a channel that animates little still gets its opening
        # upgraded, which is the shot every viewer sees.
        hero_share=round(max(0.05, bounded * 0.25), 3),
        clip_seconds=clip_seconds,
        flat_background=flat,
        background_colour=background,
        confidence=confidence,
        shots_measured=len(shots),
        notes=notes,
    )


def budgets(profile: SourcingProfile | dict | None, scenes: int) -> tuple[int, int]:
    """`(animated beats, premium beats)` for a script of this many scenes.

    The one place a measured profile becomes a number of shots, so the planner that
    enforces the budget and the ledger that reserves against it cannot disagree — which
    is the failure the hard-coded thirds were already an instance of.

    An unusable profile falls back to the shipped defaults rather than to whatever a
    four-shot reference happened to say. See `SourcingProfile.usable`.
    """
    from ..render.cutting import hero_budget, video_budget

    if isinstance(profile, dict):
        profile = SourcingProfile.from_dict(profile)
    if profile is None or not profile.usable:
        return video_budget(scenes), hero_budget(scenes)

    count = max(0, int(scenes))
    animated = max(1, round(count * profile.animation_share))
    heroes = max(1, round(count * profile.hero_share))
    return min(animated, count), min(heroes, animated)
