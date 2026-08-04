"""The paper edit: what to do with the footage, written down before anything is done.

## Why this exists as its own thing

A professional editor does not open a timeline and start cutting. They watch the
footage, log it, and write a paper edit — which takes to use, where the spine of the
piece is, what gets thrown away, where music comes in. Only then do they assemble.

Forgecast had the two ends of that and not the middle. `ingest` measures a supplied
video; `render` executes a timeline. There was nothing that *decided*, so a decision was
either implicit in whichever function happened to run next, or absent.

So: `ingest` measures, `edit` decides, `render` executes. Three verbs, three packages,
and the middle one produces an artifact you can read.

## Why the plan is an object rather than a function call

Because it is the cheapest possible place to disagree with the machine.

The app's own architecture makes the argument: a gate belongs on the stage that
*determines* the spend, not the stage that *incurs* it. A plan costs nothing to produce,
nothing to change, and nothing to throw away — and it fixes every expensive decision
that comes after it. An operator who can read "cut 47 seconds of silence, drop takes 3
and 7, tighten the gap before the reveal" can correct it in ten seconds. The same
operator watching a finished render has to describe what is wrong with something that
has already been paid for.

It also means the plan can be produced by measurement, by a model, or by hand, and
everything downstream is indifferent to which.

## Every decision carries its reason

`Decision.why` is not documentation. It is the difference between a tool an editor
argues with and one they abandon: "removed 2.4s" invites no response, "removed 2.4s of
silence before the answer" can be answered with "no, that pause was the joke". A plan
you cannot argue with is a plan you have to accept or discard whole.

## What this does not do

It does not cut anything, open a file, or spend anything. It reads measurements and
returns decisions. The temptation to have it also perform the edit is exactly the
temptation `ingest` resists for the same reason — a module that measures and decides
produces numbers nobody can check.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Speech either side of a gap needs a little air, or the cut lands on the breath and
# the words run together. Kept either side of every removed silence.
BREATH_SECONDS = 0.12

# A gap shorter than this is the natural space between sentences. Removing it produces
# the gapless, breathless rhythm that is the single most recognisable sound of an
# automatically edited video — which is the thing this whole direction exists to avoid.
KEEP_GAP_UNDER = 0.45

# And one longer than this is dead air by any standard, whatever it contains.
ALWAYS_CUT_OVER = 1.20

# A kept span shorter than this is not a shot, it is a flash. Trimming either side of a
# silence leaves slivers at the edges of the footage — a real plan produced a 0.06s keep
# at the end of a clip, which is 1.4 frames and reads as a glitch in the finished video.
# Absorbed into the cut beside it rather than kept.
MIN_KEEP_SECONDS = 0.25


@dataclass
class Decision:
    """One thing to do to the footage, and why."""

    action: str          # "keep" | "drop" | "tighten"
    start: float
    end: float
    why: str
    # What the decision was made from, so a plan can be audited back to a measurement
    # rather than taken on trust: "silence", "filler", "speech", "operator".
    source: str = ""

    @property
    def seconds(self) -> float:
        return round(max(0.0, self.end - self.start), 3)

    def as_dict(self) -> dict:
        return {**asdict(self), "seconds": self.seconds}

    @classmethod
    def from_dict(cls, row: dict) -> Decision:
        return cls(action=str(row.get("action") or ""),
                   start=float(row.get("start") or 0.0),
                   end=float(row.get("end") or 0.0),
                   why=str(row.get("why") or ""),
                   source=str(row.get("source") or ""))


@dataclass
class EditPlan:
    """The paper edit. Readable, arguable, and cheap to throw away."""

    source: str
    original_seconds: float
    decisions: list[Decision] = field(default_factory=list)
    # Anything the plan could not decide, named. A plan built without a transcript is a
    # different plan, and the operator has to see that it was built that way.
    unknown: list[str] = field(default_factory=list)

    @property
    def kept(self) -> list[Decision]:
        return [item for item in self.decisions if item.action == "keep"]

    @property
    def removed_seconds(self) -> float:
        return round(sum(item.seconds for item in self.decisions
                         if item.action in ("drop", "tighten")), 2)

    @property
    def final_seconds(self) -> float:
        return round(max(0.0, self.original_seconds - self.removed_seconds), 2)

    @property
    def tightened_by(self) -> float:
        """How much shorter, as a fraction. The number an editor actually quotes."""
        if self.original_seconds <= 0:
            return 0.0
        return round(self.removed_seconds / self.original_seconds, 3)

    @classmethod
    def from_dict(cls, row: dict) -> EditPlan:
        """A plan read back off disk.

        The plan is written down precisely so somebody can go away and read it, which
        means the thing that eventually executes it is loading JSON rather than holding
        the object that produced it. Rebuilt from the decisions alone — every derived
        number on this class is a property, so a stored `final_seconds` that disagreed
        with the decisions it was computed from could not survive the round trip.
        """
        return cls(
            source=str(row.get("source") or ""),
            original_seconds=float(row.get("original_seconds") or 0.0),
            decisions=[Decision.from_dict(item)
                       for item in (row.get("decisions") or [])],
            unknown=[str(item) for item in (row.get("unknown") or [])],
        )

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "original_seconds": self.original_seconds,
            "final_seconds": self.final_seconds,
            "removed_seconds": self.removed_seconds,
            "tightened_by": self.tightened_by,
            "decisions": [item.as_dict() for item in self.decisions],
            "unknown": list(self.unknown),
        }

    def as_markdown(self) -> str:
        """The plan as an editor would read it before agreeing to it.

        Grouped by reason rather than listed in timeline order. Sixty individual
        "removed 0.8s of silence" lines is a log; "47.2s of silence across 38 gaps" is
        a decision somebody can accept or reject in one read.
        """
        lines = [f"# Edit plan — {self.source}", ""]
        lines.append(f"_{self.original_seconds:.0f}s → {self.final_seconds:.0f}s "
                     f"({self.tightened_by:.0%} tighter)_")
        lines.append("")

        by_reason: dict[str, list[Decision]] = {}
        for item in self.decisions:
            if item.action == "keep":
                continue
            by_reason.setdefault(item.why, []).append(item)

        if by_reason:
            lines += ["## What comes out", ""]
            for why, items in sorted(
                    by_reason.items(),
                    key=lambda pair: sum(d.seconds for d in pair[1]), reverse=True):
                total = sum(item.seconds for item in items)
                lines.append(f"- **{total:.1f}s** across {len(items)} "
                             f"place{'s' if len(items) != 1 else ''} — {why}")
            lines.append("")

        if self.unknown:
            lines += ["## What this plan could not see", ""]
            lines += [f"- {item}" for item in self.unknown]
            lines.append("")
        return "\n".join(lines)


def _merge(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Overlapping removals collapsed into one.

    A filler word inside a silence is one cut, not two — and two abutting cuts applied
    separately remove the breath between them twice, which is how a tightened edit ends
    up clipping the start of the next word.
    """
    if not spans:
        return []
    ordered = sorted(spans)
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(round(a, 3), round(b, 3)) for a, b in merged]


def tighten(found, *, keep_gap_under: float = KEEP_GAP_UNDER,
            always_cut_over: float = ALWAYS_CUT_OVER,
            min_keep: float = MIN_KEEP_SECONDS,
            drop_fillers: bool = True) -> EditPlan:
    """A first-pass paper edit from what was measured. Decides nothing it cannot see.

    `found` is an `ingest.Ingest`. The plan removes dead air and filler words and keeps
    everything else — which is the assembly cut, not the fine cut. It is deliberately
    the boring pass: it is the one that is right almost always, and the interesting
    decisions are the ones an operator should be making against a plan they can read.
    """
    plan = EditPlan(source=found.path, original_seconds=found.media.duration,
                    unknown=list(found.missing))

    removals: list[tuple[float, float, str, str]] = []

    for quiet in found.quiet:
        if quiet.seconds <= keep_gap_under:
            continue
        if quiet.seconds >= always_cut_over:
            why = "dead air"
        else:
            why = "a pause longer than the rhythm of the speech around it"
        # Trimmed rather than removed whole. Cutting a silence to nothing lands the
        # join on the breath and runs the words together; leaving a little air either
        # side is the difference between tightened and clipped.
        start = quiet.start + BREATH_SECONDS
        end = quiet.end - BREATH_SECONDS
        if end > start:
            removals.append((start, end, why, "silence"))

    if drop_fillers and found.lines:
        for line in found.lines:
            for word in line.words:
                if word.is_filler:
                    removals.append((word.start, word.end,
                                     "a filler word", "filler"))

    # Merged before they become decisions, so the plan reports the cuts it will make
    # rather than the reasons it found — a filler inside a silence is one cut.
    reasons: dict[tuple[float, float], tuple[str, str]] = {}
    for start, end, why, source in removals:
        reasons[(round(start, 3), round(end, 3))] = (why, source)

    for start, end in _merge([(s, e) for s, e, _w, _src in removals]):
        why, source = next(
            (value for span, value in reasons.items()
             if span[0] >= start - 0.001 and span[1] <= end + 0.001),
            ("dead air", "silence"))
        plan.decisions.append(
            Decision(action="drop", start=start, end=end, why=why, source=source))

    # What survives, as explicit keeps. A plan that only lists removals cannot be
    # executed without re-deriving the inverse, and the two derivations disagreeing is
    # a frame lost at every join.
    keeps: list[Decision] = []
    cursor = 0.0
    for cut in sorted(plan.decisions, key=lambda item: item.start):
        if cut.start > cursor:
            keeps.append(Decision(action="keep", start=cursor, end=cut.start,
                                  why="speech", source="speech"))
        cursor = max(cursor, cut.end)
    if cursor < found.media.duration:
        keeps.append(Decision(action="keep", start=cursor, end=found.media.duration,
                              why="speech", source="speech"))

    # Slivers absorbed rather than kept. Trimming a breath either side of every silence
    # leaves fragments at the edges, and a 0.06s keep is 1.4 frames — a flash, which
    # reads as a glitch and is worse than the dead air it was trying to save.
    for keep in keeps:
        if keep.seconds >= min_keep:
            plan.decisions.append(keep)
        else:
            plan.decisions.append(
                Decision(action="drop", start=keep.start, end=keep.end,
                         why="a fragment too short to see", source="sliver"))

    plan.decisions.sort(key=lambda item: (item.start, item.action))
    return plan
