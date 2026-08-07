"""What shape a reference is, read from the marks its own creator wrote.

## The question this answers, which nothing else here asks

`reverse-engineer-format.md` makes one demand before any other: decide whether the
reference is a single throughline, an anthology, or a countdown, because nothing later
is answerable until it is. Nothing in this tree decided it. `vision.semantic` cuts a
reference into `hook`, `setup`, `escalation`, `turn`, `payoff`, `close` — the beats of a
video with one argument — and it is the only structural model the app has, so every
reference got that shape whether or not it had it.

The skill file records what that costs, because it has already happened: a horror
explainer was read as a documentary with one throughline and a teased reveal. It is an
anthology of eight or nine self-contained segments with no cold open at all. A hook
framework was applied to a video that has no hook. The correction was written down and
then had nowhere to live, because measuring it needed a structure the code could not
produce.

## Why chapter marks, and not the frames

A creator who publishes timestamps has *declared* where their segments begin. That is
not a cheaper route to the same answer than inferring boundaries from cuts or pauses —
it is a better one. Inference can be wrong; a declaration is the author's own account of
their format. `shots.detect` finds visual cuts and a creator cuts inside a sentence
constantly; `semantic` finds narration pauses and an anthology's segments are separated
by the same pause length that separates its sentences. Neither can see that eight of
those boundaries are different in kind from the rest. The description says so outright.

It is also the only structural measurement that survives a refused download. Everything
in `vision.visual` needs decoded frames, so a platform that blocks the media fetch
removes the analysis entirely — while the description is a metadata field that arrives
with the listing.

## What this module deliberately does not do

It does not fetch. It takes marks or the text that holds them, from whichever caller
already has them — yt-dlp's parsed `chapters`, yt-dlp's `description`, a connector's
metadata — and measures. A module that fetched would be another way to get a video's
metadata, and there are enough.

It does not name segments, rank them, or read their content. A chapter title is a label
the creator chose; treating it as evidence about the segment's role is the guess this
exists to replace.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

# A mark, in any of the forms creators actually write:
#   0:00 Amber          00:00 - Amber        1:02:33 — The Iris
#   (0:00) Amber        an en dash or em dash after the time also works
_MARK = re.compile(
    r"""^[\s\-–—*•(\[]*
        (?P<h>\d{1,2}:)?(?P<m>\d{1,2}):(?P<s>\d{2})
        [\s\)\]\-–—.:|]*
        (?P<label>.+?)\s*$""",
    re.VERBOSE,
)

# Below this many marks there is no shape to report. Two marks describe one boundary,
# and one boundary is as true of a two-act film as of a list.
MIN_MARKS = 3

# A first mark this close to the start means the video opens on its first unit. Not
# zero: creators write `0:01` and `0:00` interchangeably, and a second of black is not
# a cold open.
COLD_OPEN_FLOOR = 3.0

# How much segment lengths may vary and still be called regular, as a fraction of the
# median. An anthology's units are suspiciously similar in length — that is the tell the
# skill file names. A throughline's chapters are not.
#
# 0.35 rather than something tighter because the last unit routinely runs long: it
# carries the outro. The measurement below excludes the final segment from the spread
# for exactly that reason, so this bounds genuine variation rather than a known artefact.
REGULAR_SPREAD = 0.35


@dataclass
class Chapter:
    start: float
    end: float
    label: str

    @property
    def seconds(self) -> float:
        return round(max(0.0, self.end - self.start), 3)

    def as_dict(self) -> dict:
        return {"start": round(self.start, 3), "end": round(self.end, 3),
                "seconds": self.seconds, "label": self.label}


@dataclass
class Structure:
    """The shape of a reference, and how much of it was actually established."""

    # anthology | countdown | throughline | unknown
    kind: str = "unknown"
    chapters: list[Chapter] = field(default_factory=list)
    unit_count: int = 0
    # The median segment length — the number a script is written against when the
    # format repeats. `None` when there is no repeating unit to have one.
    unit_seconds: float | None = None
    unit_spread: float | None = None
    # True when the video opens directly on its first unit. `None`, not False, when
    # there are no marks to tell — the difference between "it has no cold open" and
    # "nobody said" is the difference this whole module is about.
    cold_open: bool | None = None
    opening_seconds: float = 0.0
    runtime_seconds: float = 0.0
    confidence: str = "none"
    notes: list[str] = field(default_factory=list)

    @property
    def repeating(self) -> bool:
        return self.kind in ("anthology", "countdown")

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "chapters": [c.as_dict() for c in self.chapters],
            "unit_count": self.unit_count,
            "unit_seconds": (round(self.unit_seconds, 2)
                             if self.unit_seconds is not None else None),
            "unit_spread": (round(self.unit_spread, 3)
                            if self.unit_spread is not None else None),
            "cold_open": self.cold_open,
            "opening_seconds": round(self.opening_seconds, 3),
            "runtime_seconds": round(self.runtime_seconds, 3),
            "confidence": self.confidence,
            "notes": list(self.notes),
        }

    def summary(self) -> str:
        if self.kind == "unknown":
            return "structure not established from chapter marks"
        if not self.repeating:
            return (f"one throughline across {self.unit_count} chapters, "
                    f"{self.runtime_seconds:.0f}s")
        opening = ("opens on its first unit" if self.cold_open is False
                   else f"{self.opening_seconds:.0f}s before the first unit")
        return (f"{self.kind}: {self.unit_count} units of ~{self.unit_seconds:.0f}s, "
                f"{opening}")


def _spread(lengths: list[float]) -> float:
    """Population standard deviation over the median — variation at whatever scale.

    Relative rather than absolute so a 9-minute anthology of 60s units and a 60-second
    one of 6s units are held to the same standard, which is the point: regularity is a
    property of a format, not of a runtime.
    """
    usable = [x for x in lengths if x > 0]
    if len(usable) < 2:
        return 1.0
    median = statistics.median(usable)
    return (statistics.pstdev(usable) / median) if median > 0 else 1.0


def _seconds(match: re.Match) -> float:
    hours = int((match.group("h") or "0").rstrip(":"))
    return hours * 3600 + int(match.group("m")) * 60 + int(match.group("s"))


def parse(description: str) -> list[tuple[float, str]]:
    """Timestamped marks from a description, in the order written.

    Only lines that *begin* with a timestamp count. A timestamp cited mid-sentence is a
    reference to a moment, not a declaration of a boundary, and treating the two alike
    is how a "see 4:20 for the full list" in an outro becomes a segment.
    """
    found: list[tuple[float, str]] = []
    for line in (description or "").splitlines():
        match = _MARK.match(line.strip())
        if not match:
            continue
        label = match.group("label").strip()
        if not label:
            continue
        found.append((_seconds(match), label))
    return found


def read(
    *,
    description: str = "",
    chapters: list[dict] | None = None,
    runtime_seconds: float = 0.0,
) -> Structure:
    """Measure a reference's shape from its marks.

    `chapters` is yt-dlp's parsed field and wins when present — it has already resolved
    the end of each mark against the runtime, and it is the extractor's reading of the
    same description rather than a second one. `description` is the fallback, and the
    only thing a connector that returns metadata without parsing it can offer.
    """
    out = Structure(runtime_seconds=float(runtime_seconds or 0.0))

    marks: list[tuple[float, str]] = []
    if chapters:
        for entry in chapters:
            try:
                marks.append((float(entry["start_time"]), str(entry.get("title") or "")))
            except (KeyError, TypeError, ValueError):
                continue
        if marks and not out.runtime_seconds:
            ends = [float(e.get("end_time") or 0.0) for e in chapters]
            out.runtime_seconds = max(ends) if ends else 0.0
    if not marks:
        marks = parse(description)

    if len(marks) < MIN_MARKS:
        out.notes.append(
            f"{len(marks)} chapter mark(s) — fewer than {MIN_MARKS}, so no shape is "
            "claimed. A reference with no marks is not a reference with no structure; "
            "it is one that did not declare its structure here."
        )
        return out

    # Written order is not guaranteed to be time order, and a mark that goes backwards
    # is a typo rather than a boundary.
    marks.sort(key=lambda m: m[0])
    deduped: list[tuple[float, str]] = []
    for start, label in marks:
        if deduped and start <= deduped[-1][0]:
            continue
        deduped.append((start, label))
    marks = deduped

    last_end = out.runtime_seconds or (marks[-1][0] + 0.0)
    if last_end <= marks[-1][0]:
        # No runtime to close the final chapter against. Everything below except the
        # last segment's length is still measurable, so report rather than refuse.
        last_end = marks[-1][0]
        out.notes.append("runtime unknown, so the final unit's length is not measured")

    built: list[Chapter] = []
    for index, (start, label) in enumerate(marks):
        end = marks[index + 1][0] if index + 1 < len(marks) else last_end
        built.append(Chapter(start=start, end=end, label=label))
    out.chapters = built
    out.unit_count = len(built)

    # An opening can be marked or unmarked, and both have to be caught.
    #
    # Unmarked is the easy one: the first mark sits some way into the video and the
    # seconds before it belong to nothing. Marked is the trap, and a decoy caught it —
    # a creator who gives their cold open its own chapter produces a first mark at
    # 0:00, which the naive test reads as "opens on its first unit" while that chapter
    # is also counted as a unit and drags the median with it.
    #
    # It is settled by measurement rather than by reading the label. `interior` is the
    # chapters with neither end's artefacts: not the last, which carries the outro on
    # nearly every anthology, and not the first, which is the thing under test. If the
    # first chapter does not fit what the interior does, it is an opening rather than a
    # unit — the same reasoning that excludes the last one, applied at the other end.
    # A title saying "cold open" would be easier and is exactly the guess this module
    # exists to replace: the creator chose that word for an audience, not for us.
    out.opening_seconds = built[0].start

    # Tested by what the first chapter does to the regularity of the others, not by how
    # long it is on its own. A band around the median was tried first and is too blunt:
    # a 90s opening against 63s units sits inside any band wide enough to keep genuine
    # long units, so it survived the test and dragged the median with it.
    #
    # Asking instead whether the set gets markedly tidier without it separates the two
    # cases cleanly, because that is what an opening actually is — the one entry that
    # does not belong to the series. On that decoy the spread falls from 0.178 to 0.015.
    interior = [c.seconds for c in built[1:-1] if c.seconds > 0]
    first_is_unit = True
    if len(interior) >= 2:
        first = built[0].seconds
        with_first = _spread([first, *interior])
        without = _spread(interior)
        # Both terms matter. The improvement has to be large, and what remains has to be
        # genuinely regular — otherwise a merely uneven set improves by dropping any
        # member, and the first would be blamed for variation spread across all of them.
        if (first > 0 and without <= REGULAR_SPREAD / 2
                and with_first > max(without * 3.0, 0.05)):
            first_is_unit = False
            out.notes.append(
                f"the first chapter runs {first:.0f}s and the rest hold a "
                f"{statistics.median(interior):.0f}s rhythm ({without:.3f} spread, "
                f"{with_first:.3f} with it) — counted as an opening, not as a unit"
            )
            # Say that the other reading exists, because the timings cannot rule it out.
            # An opening and a first unit that simply runs long are the same shape in
            # this data; only the label separates them, and reading labels for role is
            # the guess this module replaces. Demoting is the safer of the two errors —
            # it protects the unit length, which is the number every script written from
            # this reference is measured against, where keeping it inflates that number
            # on every script. But it invents an opening where there may be none, which
            # is close enough to the failure the skill file records that it must not be
            # asserted quietly.
            out.notes.append(
                "a first unit that simply runs long would look identical here — this "
                "reading is from the timings alone"
            )

    if first_is_unit:
        units = built
        out.cold_open = built[0].start > COLD_OPEN_FLOOR
    else:
        units = built[1:]
        # There is an opening either way now; it just happens to be marked.
        out.cold_open = True
        out.opening_seconds = built[0].end
    out.unit_count = len(units)

    # The last unit carries the outro on nearly every anthology, so it is excluded from
    # the regularity test. It is still counted and still reported — it is a unit, it
    # just is not evidence about how long a unit runs.
    body = [c.seconds for c in units[:-1] if c.seconds > 0]
    if len(body) < 2:
        out.notes.append("too few complete units to measure regularity")
        out.confidence = "low"
        out.kind = "unknown"
        return out

    median = statistics.median(body)
    spread = _spread(body)
    out.unit_seconds = median
    out.unit_spread = spread

    if spread <= REGULAR_SPREAD:
        out.kind = "countdown" if _ordered(units) else "anthology"
        out.notes.append(
            f"units run {min(body):.0f}–{max(body):.0f}s around a {median:.0f}s median "
            f"(spread {spread:.2f}) — regular enough to be a repeating unit"
        )
        if out.cold_open is False:
            out.notes.append(
                "the first mark is at the start, so there is no cold open: the video "
                "opens directly on its first unit. A hook written for this format has "
                "nowhere to go."
            )
        else:
            out.notes.append(
                f"{out.opening_seconds:.0f}s runs before the first unit — an opening "
                "the units do not account for"
            )
    else:
        out.kind = "throughline"
        out.notes.append(
            f"chapters run {min(body):.0f}–{max(body):.0f}s around a {median:.0f}s "
            f"median (spread {spread:.2f}) — too uneven to be a repeating unit, so "
            "these read as the parts of one argument rather than a list"
        )

    # Confidence is about how much was measured, never about how neat the answer is.
    if out.unit_count >= 6 and out.runtime_seconds > 0:
        out.confidence = "high"
    elif out.unit_count >= 4:
        out.confidence = "medium"
    else:
        out.confidence = "low"
    # A demoted first chapter is a judgement the timings cannot settle, so a profile
    # carrying one never reads as fully established however many units it has.
    if not first_is_unit and out.confidence == "high":
        out.confidence = "medium"
    return out


_ORDINAL = re.compile(r"^\s*(?:#\s*)?(\d{1,2})\s*[.)\-:–]")


def _ordered(chapters: list[Chapter]) -> bool:
    """Whether the creator numbered their units.

    Deliberately narrow: a leading number on most labels, and nothing else. A countdown
    and an anthology are edited the same way and scripted the same way — the only thing
    that differs is whether position carries meaning, and the honest evidence for that
    is the creator writing the positions down. Inferring it from superlatives in the
    title would be reading the marketing.
    """
    numbered = sum(1 for c in chapters if _ORDINAL.match(c.label))
    return numbered >= max(2, int(len(chapters) * 0.6))


# ------------------------------------------------------------------------- writing
#
# The other direction, and it lives here because this module already owns the format.
# A parser and a writer that disagree about what a mark looks like is a defect nobody
# finds until a published description silently fails to become chapters — the video
# just does not have them, with no error anywhere.
#
# The audience of the format this app targets writes these indexes by hand in the
# comments. That is a request, made repeatedly, for something publishing costs nothing.

#: YouTube's own floor for a chapter's length. A shorter one does not make the list
#: shorter — it makes the whole description fail to parse as chapters, so the video ends
#: up with none at all. That is why this is enforced by dropping the run rather than by
#: dropping the offending mark: a partial list whose remaining gaps are still short
#: fails the same way, and silently.
MIN_CHAPTER_SECONDS = 10.0

#: The first mark has to be exactly this, or there are no chapters. Not "close to zero"
#: — the parser above accepts `0:01` because creators write it, and YouTube does not.
FIRST_MARK = 0.0


def stamp(seconds: float) -> str:
    """A timestamp in the shape YouTube requires: `m:ss`, or `h:mm:ss` past an hour."""
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def write(marks, *, runtime_seconds: float = 0.0) -> tuple[list[str], str]:
    """Chapter lines for a description, and the reason when there are none.

    `marks` is `(start_seconds, label)` pairs in any order. Returns `([], reason)`
    rather than a best effort, because a list that breaks one of YouTube's rules is not
    a shorter list — it is no chapters at all, with nothing anywhere saying so. An
    operator who is told "too short a gap between two segments" can fix it; an operator
    looking at a published video with no chapter bar cannot tell it was ever attempted.
    """
    cleaned = []
    for start, label in marks or ():
        try:
            at = float(start)
        except (TypeError, ValueError):
            continue
        text = " ".join(str(label or "").split())
        if not text or at < 0:
            continue
        cleaned.append((at, text))
    cleaned.sort(key=lambda mark: mark[0])

    # Two marks at the same second are one boundary written twice, and the second of
    # them is what makes the gap zero. Dropped here so the length check below reports
    # a real problem rather than this one.
    deduped: list[tuple[float, str]] = []
    for at, text in cleaned:
        if deduped and at - deduped[-1][0] < 1.0:
            continue
        deduped.append((at, text))

    if len(deduped) < MIN_MARKS:
        return [], (f"{len(deduped)} segment(s) to mark and YouTube needs "
                    f"{MIN_MARKS} — no chapters written")
    if deduped[0][0] != FIRST_MARK:
        return [], (f"the first segment starts at {stamp(deduped[0][0])} and YouTube "
                    f"requires 0:00 — no chapters written")

    edges = [at for at, _ in deduped[1:]]
    if runtime_seconds:
        edges.append(float(runtime_seconds))
    for index, end in enumerate(edges):
        gap = end - deduped[index][0]
        if gap < MIN_CHAPTER_SECONDS:
            return [], (f"{deduped[index][1]!r} runs {gap:.0f}s and YouTube's minimum "
                        f"is {MIN_CHAPTER_SECONDS:.0f}s — no chapters written")

    return [f"{stamp(at)} {text}" for at, text in deduped], ""
