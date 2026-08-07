"""The shot list for one segment, written before anything is rendered.

`plan.py` decides what to cut out of footage somebody handed the app. This decides what
a segment is *made of* before any of it exists — which asset carries which beat, how
long each shot holds, where the name and the stats land, and which shot is worth
animating.

## Why there is a plan at all

An editor does not open the software and start cutting. They write the shot list first,
because deciding "the wide establishes, the push lands on the reveal, the stats come up
under the second line" is cheap on paper and expensive in a timeline. This module is
that piece of paper. It is also what makes the edit reviewable: a plan can be read and
argued with in seconds, and a render cannot.

Everything here is data. Nothing renders, nothing fetches, nothing spends.

## The shape it plans to

Measured from a reference whose segments run about a minute each and go: the name, an
encounter told as a story, a switch into specification, then survival instructions. Its
shots hold two to four seconds and hard-cut. Its screen carries the name, the numbers
and the jokes, and its voice carries the prose.

So a segment is three beats with different jobs, and the shot list gives each the
treatment its job needs rather than cutting the whole thing at one rate:

  behaviour    the story, and it goes first. Most shots, and the one place motion
               earns its cost.
  appearance   the switch into specification. Fewest shots, longest holds, and where
               the numbers belong.
  survival     instructions. Short and plain — a held shot under an imperative reads
               as padding.

The order is the measured one and it is not the order the wiki lists them in. The
reference opens on the encounter and only then tells you what the thing is; a segment
that specifies before it tells the story has explained the answer before asking the
question.

## Why assets are assigned rather than cycled

Round-robin over a gallery puts the establishing wide on the punchline. The subject's
best asset goes to the beat that introduces it, wide images go to the beat that needs a
place, and repeats are pushed as far apart as the segment allows — a shot reused two
cuts later reads as a mistake, and the same shot four cuts later does not.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: How long a shot holds, in seconds, before and after the rhythm is applied. The
#: measured reference sits at 2–4s and does not change rate between its hook and its
#: body; these are the floor and ceiling a plan will not cross whatever it is told.
MIN_HOLD = 1.6
MAX_HOLD = 5.0

#: Share of a segment's running time each beat gets. Measured off the reference: roughly
#: half the segment is the story, a third is the specification, and the rest is the
#: instructions. They sum to 1.0 and are renormalised if a beat is missing.
BEAT_SHARE = {"behaviour": 0.50, "appearance": 0.32, "survival": 0.18}

#: Longest a single shot holds inside each beat. The story can breathe; instructions
#: cannot, because a held shot under an imperative reads as padding.
BEAT_MAX_HOLD = {"behaviour": 4.2, "appearance": 5.0, "survival": 3.0}

#: How many shots into the segment the stat card appears — measured as a fraction of
#: the way through the appearance beat, which is where the reference puts its numbers.
STAT_AT = 0.45

#: How many shots one picture may carry before the plan says so. Above this the segment
#: is a slideshow with cuts in it, and the fix is more assets rather than more editing.
MAX_SHOTS_PER_ASSET = 5


@dataclass
class Shot:
    """One shot on the list. Nothing here has been rendered."""

    index: int
    beat: str
    seconds: float
    #: The asset this shot draws from, by name. Empty means the plan wants a picture
    #: nothing supplied — which is a hole to fill, not a shot to render.
    asset: str = ""
    #: Whether the asset is a subject to composite onto a plate or already a shot.
    composite: bool = False
    #: What is on screen besides the picture.
    overlays: list[str] = field(default_factory=list)
    #: Whether this shot is worth animating. Expensive, so it is rationed by the plan
    #: rather than decided per shot at render time.
    animate: bool = False
    note: str = ""

    def as_dict(self) -> dict:
        return {"index": self.index, "beat": self.beat, "seconds": round(self.seconds, 2),
                "asset": self.asset, "composite": self.composite,
                "overlays": list(self.overlays), "animate": self.animate,
                "note": self.note}


@dataclass
class Segment:
    """A shot list, and the arithmetic that produced it."""

    title: str
    seconds: float
    shots: list[Shot]
    assets_used: int = 0
    assets_available: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def shot_count(self) -> int:
        return len(self.shots)

    @property
    def mean_hold(self) -> float:
        return round(self.seconds / max(1, len(self.shots)), 2)

    def as_dict(self) -> dict:
        return {"title": self.title, "seconds": round(self.seconds, 2),
                "shots": [shot.as_dict() for shot in self.shots],
                "shot_count": self.shot_count, "mean_hold": self.mean_hold,
                "assets_used": self.assets_used,
                "assets_available": self.assets_available,
                "warnings": list(self.warnings)}

    def as_text(self) -> str:
        """The shot list as an editor would read it.

        Rendered as text because that is the form a plan gets argued with. A dict is for
        the renderer; this is for the person deciding whether the plan is any good.
        """
        lines = [f"{self.title} — {self.seconds:.0f}s, {self.shot_count} shots, "
                 f"{self.mean_hold:.1f}s average"]
        clock = 0.0
        for shot in self.shots:
            marks = list(shot.overlays)
            if shot.animate:
                marks.append("motion")
            suffix = f"  [{', '.join(marks)}]" if marks else ""
            asset = shot.asset or "NO ASSET"
            lines.append(f"  {clock:5.1f}  {shot.seconds:>4.1f}s  {shot.beat:<10} "
                         f"{asset[:40]:<40}{suffix}")
            clock += shot.seconds
        for warning in self.warnings:
            lines.append(f"  ! {warning}")
        return "\n".join(lines)


def _beat_seconds(beats: dict, total: float) -> dict:
    """Split the segment's running time across the beats that exist.

    Renormalised rather than left short. A page with no survival section should not
    produce a segment that runs 82% of its length and then stops.
    """
    present = {name: BEAT_SHARE[name] for name in BEAT_SHARE if beats.get(name)}
    if not present:
        return {}
    scale = sum(present.values())
    return {name: total * share / scale for name, share in present.items()}


def _hold_for(beat: str, target: float) -> float:
    return max(MIN_HOLD, min(BEAT_MAX_HOLD.get(beat, MAX_HOLD), MAX_HOLD, target))


def _spread(assets: list, count: int, *, offset: int = 0) -> list:
    """Pick `count` assets, reusing as sparsely as the gallery allows.

    Round-robin rather than random, and never twice in a row while an unused asset
    exists: a shot repeated two cuts later reads as a mistake, and the same shot four
    cuts later does not.
    """
    if not assets:
        return [None] * count
    return [assets[(offset + index) % len(assets)] for index in range(count)]


def plan(entity: dict, *, seconds: float = 62.0, target_hold: float = 3.0,
         gags: list[str] | None = None) -> Segment:
    """A shot list for one entity's segment.

    `entity` is what `research.fandom` returns — beats, stats and a gallery. Taken as a
    plain dict rather than the dataclass so a plan can be written from a saved run, from
    the agent, or from a hand-typed sketch without importing the reader.
    """
    beats = dict(entity.get("beats") or {})
    stats = dict(entity.get("stats") or {})
    gallery = list(entity.get("gallery") or [])
    title = str(entity.get("title") or "Untitled")
    warnings: list[str] = []

    if not beats:
        return Segment(title=title, seconds=0.0, shots=[],
                       assets_available=len(gallery),
                       warnings=["no readable sections — this entity cannot carry a "
                                 "segment"])

    # Subjects first: a portrait crop composited onto a plate is the shot this format is
    # built from, and a wide image is a background or an establisher.
    subjects = [item for item in gallery if item.get("portrait")]
    wides = [item for item in gallery if not item.get("portrait")]
    if not gallery:
        warnings.append("no artwork on the page — every shot here is a hole to fill")

    split = _beat_seconds(beats, seconds)
    shots: list[Shot] = []
    used: set[str] = set()
    index = 0

    # Story first. The wiki lists Appearance above Behaviour and the narration does the
    # opposite, because a segment that specifies before it tells the story has given the
    # answer before asking the question.
    cursor = 0
    for beat in ("behaviour", "appearance", "survival"):
        span = split.get(beat)
        if not span:
            continue
        count = max(1, round(span / _hold_for(beat, target_hold)))
        hold = span / count

        # The story beat gets the wides where there are any — it is the beat that needs
        # a place for the encounter to happen in. Everything else leads on the subject.
        pool = (wides + subjects) if beat == "behaviour" and wides else (subjects or wides)
        # The cycle carries across beats rather than restarting. Per-beat round-robin
        # put the same picture on shots 0, 7 and 17 of a 21-shot segment — three
        # separate moments that all opened on the identical frame.
        chosen = _spread(pool, count, offset=cursor)
        # `+ 1`, not `+ count`. Advancing by the beat's own length realigns the cycle
        # whenever that length is a multiple of the gallery size — with five images and
        # a ten-shot beat, the next beat opened on the identical frame the segment
        # opened on. The extra step keeps consecutive beats out of phase.
        cursor += count + 1

        for position in range(count):
            asset = chosen[position] or {}
            overlays: list[str] = []
            if index == 0:
                overlays.append("name card")
            if beat == "appearance" and stats and position == max(
                    0, min(count - 1, round(count * STAT_AT))):
                overlays.append("stat card")

            shots.append(Shot(
                index=index, beat=beat, seconds=hold,
                asset=str(asset.get("name") or ""),
                composite=bool(asset.get("portrait")),
                overlays=overlays,
                # Motion is rationed, not sprinkled. The reference animates about twice
                # a minute and lands it on the beat the narration is describing, which
                # is the story — an animated establisher is spend with nothing to show
                # for it.
                animate=beat == "behaviour" and position in (0, count // 2),
                note="",
            ))
            if asset.get("name"):
                used.add(str(asset["name"]))
            index += 1

    # Gags go on the story beat, where the reference puts them, and never on the shot
    # carrying the name card — two things asking to be read at once is neither read.
    for offset, line in enumerate(gags or []):
        candidates = [shot for shot in shots
                      if shot.beat == "behaviour" and "name card" not in shot.overlays]
        if not candidates:
            warnings.append(f"nowhere to put the gag {line!r}")
            break
        candidates[(offset * 2 + 1) % len(candidates)].overlays.append(f"bubble: {line}")

    # Flagged on load per picture rather than on the count of pictures. A gallery of one
    # is not a problem in a six-shot segment and is a serious one in twenty-one, and the
    # earlier form — comparing used against min(3, available) — could never fire for a
    # single-image page, which is exactly the case worth warning about.
    per_asset = len(shots) / max(1, len(used))
    if used and per_asset > MAX_SHOTS_PER_ASSET:
        warnings.append(
            f"{len(used)} image(s) carrying {len(shots)} shots — {per_asset:.0f} each. "
            "The segment is leaning on too few pictures; find more before rendering.")

    return Segment(title=title, seconds=sum(shot.seconds for shot in shots), shots=shots,
                   assets_used=len(used), assets_available=len(gallery),
                   warnings=warnings)
