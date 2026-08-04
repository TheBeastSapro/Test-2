"""What a learned reference SAYS, cut into the beats it says it in.

## Why this exists

`profile.build` has taken a `semantic` argument since the day it was written, and
nothing has ever passed one. `engine.analyse_file` forwards whatever it was handed,
every caller handed it `None`, and so every reference this app has ever learned came
back carrying the profile's own apology: "no semantic pass: shot subjects, graphic
style and text contents are not described". A socket wired to nothing is worse than no
socket at all, because the field it would fill reads as optional rather than missing.

The hole underneath the argument was larger than the argument. `ingest/transcript.py`
has produced word-level timings from the start — but only for a file the *operator*
supplied, on the edit-somebody-else's-video path. A learned reference went through the
entire vision engine without anybody once asking what it said. Forgecast could tell you
a creator cuts every 2.1 seconds, grades warm and locks their cuts to the beat, and
could not tell you they spend four seconds making a promise and the last six asking for
a follow. The edit was measured; the argument the edit exists to carry was not.

This reads the words and where they land, and cuts them into the story's beats. It
transcribes through `ingest.transcript` rather than opening its own model, because two
transcribers in one tree is two answers to what a video said, and the two would diverge
the first time either changed model.

## Why the beats are cut at pauses and not at cuts

The obvious boundary was already in memory: `shots.detect` knows every cut in the
video, timed to the frame. It was rejected. A cut is a *visual* boundary, and a creator
cuts inside a sentence constantly — sectioning a reference that cuts thirty times a
minute on its cuts produces thirty "beats" of four words each, which is a shot list
with a story's vocabulary written over it. What ends a beat of narrative is the
narrator stopping, and where the narrator stopped is in the transcript.

What counts as stopping is measured against this narration rather than fixed, for the
reason `shots.ABSOLUTE_FLOOR` is adaptive: a fixed cutoff fails in both directions. A
breathless short-form read leaves 0.15s between sentences and half a second between
beats; a documentary leaves half a second inside one sentence. So a beat break is a gap
markedly longer than *this* read's own typical gap, with an absolute floor so a
wall-to-wall read does not turn every breath into a section.

## Why a section can come back called `body`

The vocabulary is closed — `hook`, `setup`, `escalation`, `turn`, `payoff`, `close` —
so that ten learned references are countable rather than ten essays. But a closed
vocabulary invites the failure this module is most likely to commit: six names and five
sections, so something gets called a `turn` because it was fourth. Every name here is
issued by a rule with a measurable trigger, and a section no rule reaches is called
`body` and carries the sentence saying why. An invented section is worse than a missing
one, because a missing one is visible.

## What can honestly be measured, and what cannot

**When words are said and how fast** — yes, and this is the whole floor the rest
stands on. `faster-whisper` returns word timings, so section durations, word counts and
words-per-second are counted rather than estimated.

**Where the beats break** — yes, as pauses. A scripted read breathes between beats and
does not breathe inside one, and that gap is the only boundary evidence the audio
carries. It is honest evidence of *a* break; it is not evidence of what the break was
for.

**Where the hook ends** — yes, in the sense that can be acted on: the opening beat runs
until the narrator first stops for longer than they stop inside a beat, and that instant
is a number an editor can cut to. What cannot be read is whether the promise had been
*made* by then — a hook that ends before it has said anything is still a first beat.

**Whether the delivery escalates** — yes. Words-per-second per section is arithmetic,
and a run of sections each read faster than the last is a measured acceleration. What
that acceleration means is not measured: a middle that speeds up may be a story
tightening or may be the dense part of an explainer, and this reports the rise.

**Which beat is the `payoff`** — *no*, and this module does not pretend otherwise. A
payoff is a promise being kept, and whether a promise was kept is a fact about meaning
that no timing carries. The one marker that would locate it — a marked break followed
by a change of pace — is the evidence already spent naming `turn`, and a second name
for one measurement is a second answer that drifts apart the first time either is
tuned. So `payoff` is reported as not claimed, with that reason attached, on every
reference.

**Whether the transcript is right** — partly, and it is reported rather than assumed.
`faster-whisper` returns a per-word probability; a read taken over music, in an accent
the model is weak on, or at 210 words a minute comes back with low ones. Sections
measured off words the model was unsure of are marked low confidence rather than
presented at the same weight as a clean read.

**What is on screen while it is said** — *no*. This module reads audio. On-screen text
is frequently a second, denser script running in parallel with the narration, and
`profile._confidence` already says plainly that text is located by edge density and not
read. A `semantic` block filled by a vision provider is still the thing that would
answer that, and supplying one explicitly to `analyse_file` still overrides this.

**Anything at all, when there is no transcription model** — no, and that is a first-
class outcome rather than a crash. `faster-whisper` is the optional `edit` extra, and a
machine without it gets a narrative block that says which tool is missing and grades
itself `none`. A learn that dies because a reference could not be transcribed is a learn
that produced nothing; a learn that says "I could not hear this one" is a learn.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from ..ingest import transcript
from ..ingest.transcript import Line
from .probe import VideoMeta

log = logging.getLogger("forgecast.vision.semantic")

# The closed vocabulary. Fixed so that a shelf of learned references is countable —
# "four of six open on a hook that ends inside three seconds" only means something if
# every reference reached for the same word.
VOCABULARY = ("hook", "setup", "escalation", "turn", "payoff", "close")

# What a section is called when no rule reached it. Named rather than left blank: a
# blank name reads as a bug, and this is a finding — the beats either side of it are
# indistinguishable from it on every axis this module can measure.
UNNAMED = "body"

# Names that will not be issued whatever the reference does, and the reason, reported
# on every measurement. Silence here would look like "this reference had no payoff"
# rather than "this pass cannot find one" — see the honesty section above.
UNCLAIMABLE: dict[str, str] = {
    "payoff": (
        "a payoff is a promise being kept, which is a fact about meaning and not about "
        "timing. The only marker that would locate one — a marked break followed by a "
        "change of pace — is the evidence already spent naming `turn`, and two names "
        "for one measurement are two answers"
    ),
}

# The shortest gap between two spoken lines that can be a beat change rather than a
# breath. Below this a "section boundary" is punctuation: measured across scripted
# narration, the gap either side of a comma or a full stop sits in the low hundreds of
# milliseconds, and a threshold under that sections a paragraph into its sentences.
PAUSE_FLOOR = 0.45

# How much longer than this read's own typical gap a pause has to be before it is a
# beat change. The multiple, not a second absolute figure, is what stops a slow
# narrator being sectioned on every full stop while a fast one is never sectioned at
# all — the same failure `shots.NOISE_MULTIPLE` exists to prevent one level down.
PAUSE_MULTIPLE = 1.8

# The most sections a reference may be cut into. The vocabulary has six names, and a
# seventh section would be a `body` sitting between two beats that the naming rules
# cannot tell apart anyway — so the weakest breaks are dropped rather than reported as
# structure nobody can use.
MAX_SECTIONS = 6

# Shorter than this and a span is a beat inside a section, not a section. A dramatic
# stop mid-argument leaves a two-word span either side of it, and reporting that as a
# narrative section puts a `turn` on a pause for effect.
MIN_SECTION_SECONDS = 1.5

# Below this many spoken lines there is nothing to section. Four lines is three gaps,
# and three is the fewest a median can be taken over without "typical" being one of the
# two extremes — a threshold derived from two numbers is one of those two numbers.
MIN_LINES = 4

# How far the sharpest break has to stand out from the other beat breaks before it is
# a `turn`. Every section boundary is already a long pause by construction; without
# this the longest of six near-identical pauses would be named a turn on a difference
# of forty milliseconds.
TURN_MULTIPLE = 1.6

# How much faster the delivery has to get across a run of sections before that run is
# an escalation rather than noise in the read. A narrator varies by a few percent
# between beats without meaning anything by it.
ESCALATION_RISE = 0.15

# What counts as the read speeding up or slowing down over the whole runtime.
# Deliberately the same figure as `shots.pacing_trend` uses for the edit, so "the edit
# accelerates" and "the read accelerates" describe the same size of change and can be
# put side by side without converting anything.
TREND_CHANGE = 0.25

# Mean per-word probability below which the words themselves are in doubt. Sections cut
# out of a transcript the model was unsure of are still cut in the right places — the
# timings are solid even when the words are wrong — but the quoted text is not evidence
# of anything, so the whole block drops to low rather than only the text.
SHAKY_WORDS = 0.55


@dataclass
class Section:
    """One beat of the story, and the measurement that earned it its name."""

    name: str
    index: int
    start: float
    end: float
    words: int
    text: str
    # How long the narrator stopped before this section began. 0.0 for the opening
    # beat, which begins because the video does. This is the whole boundary evidence,
    # so it is carried rather than thrown away after the split — a `turn` named on a
    # 1.9s break can be argued with, a `turn` named on nothing cannot.
    opened_on_pause: float = 0.0
    share: float = 0.0
    evidence: str = ""

    @property
    def seconds(self) -> float:
        return round(max(0.0, self.end - self.start), 3)

    @property
    def words_per_second(self) -> float:
        """Speech rate across this beat.

        Over the beat's *spoken* span rather than over wall-clock, which is the same
        span `ingest.transcript.Line` divides by. A section that ends on three seconds
        of silence has not slowed down; it has stopped, and the pause is reported
        separately as the next section's `opened_on_pause`.
        """
        return round(self.words / self.seconds, 2) if self.seconds > 0 else 0.0

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "index": self.index,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "seconds": self.seconds,
            "words": self.words,
            "words_per_second": self.words_per_second,
            "share": round(self.share, 3),
            "opened_on_pause": round(self.opened_on_pause, 3),
            "text": self.text,
            "evidence": self.evidence,
        }


@dataclass
class Narrative:
    """What a reference said and how it was structured. Every field is JSON-safe."""

    # Whether there were words to read at all. False is a finding, not a failure: a
    # music-led reference with no narration is a format, and `notes` says which it was.
    transcribed: bool = False
    # Whether the read could be cut into beats. False with `transcribed` true is the
    # short reference: something was said, and there is not enough of it to have a
    # structure. Reported rather than filled in.
    sectioned: bool = False
    sections: list[Section] = field(default_factory=list)
    # Where the opening beat stops, in seconds. The single number this whole module
    # exists to produce — it is what an editor cuts to and what a script is written
    # against. `None` when the reference could not be sectioned.
    hook_ends_at: float | None = None
    runtime_seconds: float = 0.0
    spoken_seconds: float = 0.0
    # How much of the runtime has words over it. Separates a narrated explainer from a
    # visual-led piece that speaks for a fifth of its length, which are different
    # formats with the same word count.
    speech_share: float = 0.0
    words: int = 0
    words_per_second: float = 0.0
    words_per_minute: float = 0.0
    # accelerating | steady | decelerating | not_measured — the read, over the whole
    # runtime, in `shots.pacing_trend`'s own words.
    delivery_trend: str = "not_measured"
    # Vocabulary names not issued, and why. The honest half of a closed vocabulary.
    not_claimed: dict[str, str] = field(default_factory=dict)
    confidence: str = "none"
    lines_read: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "transcribed": self.transcribed,
            "sectioned": self.sectioned,
            "sections": [section.as_dict() for section in self.sections],
            "hook_ends_at": (round(self.hook_ends_at, 3)
                             if self.hook_ends_at is not None else None),
            "runtime_seconds": round(self.runtime_seconds, 3),
            "spoken_seconds": round(self.spoken_seconds, 3),
            "speech_share": round(self.speech_share, 3),
            "words": self.words,
            "words_per_second": round(self.words_per_second, 2),
            "words_per_minute": round(self.words_per_minute, 1),
            "delivery_trend": self.delivery_trend,
            "not_claimed": dict(self.not_claimed),
            "confidence": self.confidence,
            "lines_read": self.lines_read,
            "notes": list(self.notes),
        }


# ------------------------------------------------------------------- the transcript


def _transcribe(meta: VideoMeta, *, model: str, language: str) -> tuple[list[Line], str]:
    """`(lines, why there are none)`. Never raises, for the reason `read` does not.

    A reference that cannot be transcribed has to cost one reference, not the whole
    learn. `ingest.read` already made that choice for the supplied-video path and put
    the reason in `missing`; this is the same choice with the reason in `notes`.

    The bare `except` is deliberate and is the failure it prevents: the first
    transcription on a machine downloads model weights, and everything from a closed
    socket to an unreadable audio stream to an ONNX runtime that will not load on this
    CPU surfaces here as some exception nobody has enumerated. A learn that dies on the
    third of five references leaves the operator with nothing and no reason.
    """
    if not meta.has_audio:
        return [], "the reference has no audio track — nothing was said over it"

    ok, why = transcript.available()
    if not ok:
        return [], why

    try:
        lines = transcript.read(meta.path, model_name=model, language=language or None)
    except Exception as exc:                                          # pragma: no cover
        log.warning("transcription of %s failed: %s", meta.path.name, exc)
        return [], f"transcription failed ({type(exc).__name__}: {exc})"

    if not lines:
        return [], ("no speech was found in the audio — the reference is scored or "
                    "silent rather than narrated")
    return lines, ""


# ----------------------------------------------------------------------- sectioning


def _gaps(lines: list[Line]) -> list[float]:
    """The silence between consecutive spoken lines. `gaps[i]` closes `lines[i]`.

    Floored at zero because whisper's VAD occasionally hands back segments that
    overlap by a few milliseconds, and a negative gap would drag the median that every
    threshold below is measured against.
    """
    return [max(0.0, after.start - before.end) for before, after in zip(lines, lines[1:])]


def _break_threshold(gaps: list[float]) -> float:
    """How long a pause has to be, in this read, to be a beat change."""
    if not gaps:
        return PAUSE_FLOOR
    return max(PAUSE_FLOOR, statistics.median(gaps) * PAUSE_MULTIPLE)


def _spans(bounds: list[int], count: int) -> list[tuple[int, int]]:
    """`bounds` (indices of the lines a section ends on) as `(first, last)` line pairs."""
    edges = [-1, *bounds, count - 1]
    return [(edges[i] + 1, edges[i + 1]) for i in range(len(edges) - 1)]


def _prune(bounds: list[int], lines: list[Line]) -> list[int]:
    """Drop boundaries until no section is shorter than `MIN_SECTION_SECONDS`.

    One at a time and shortest first, rather than filtering in a single pass. Two
    adjacent short spans merge into one long enough section, and a single pass would
    drop both boundaries and swallow a real beat with them.
    """
    bounds = sorted(bounds)
    while bounds:
        spans = _spans(bounds, len(lines))
        lengths = [lines[last].end - lines[first].start for first, last in spans]
        shortest = min(range(len(lengths)), key=lambda i: lengths[i])
        if lengths[shortest] >= MIN_SECTION_SECONDS:
            break
        # Merge backwards into the previous section, except for the opening one, which
        # has nothing behind it and so absorbs forwards instead.
        bounds.pop(shortest - 1 if shortest > 0 else 0)
    return bounds


def _boundaries(lines: list[Line]) -> tuple[list[int], int]:
    """`(lines a section ends on, breaks found before pruning)`.

    The second number is not diagnostics. A reference comes back unsectioned for two
    completely different reasons — the narrator never stopped, or they stopped so often
    that every span was too short to be a beat — and a note that names the wrong one
    sends the operator looking at the wrong reference.
    """
    gaps = _gaps(lines)
    threshold = _break_threshold(gaps)
    candidates = [index for index, gap in enumerate(gaps) if gap >= threshold]
    if len(candidates) > MAX_SECTIONS - 1:
        # Keep the longest pauses rather than the first ones. Truncating in time order
        # would section the opening minute of a ten-minute reference in detail and
        # report the remaining nine as one beat.
        strongest = sorted(candidates, key=lambda index: gaps[index], reverse=True)
        candidates = sorted(strongest[: MAX_SECTIONS - 1])
    return _prune(list(candidates), lines), len(candidates)


def _build(lines: list[Line], bounds: list[int], runtime: float) -> list[Section]:
    gaps = _gaps(lines)
    sections: list[Section] = []
    for index, (first, last) in enumerate(_spans(bounds, len(lines))):
        span = lines[first : last + 1]
        text = " ".join(line.text.strip() for line in span).strip()
        start, end = span[0].start, span[-1].end
        sections.append(Section(
            name=UNNAMED,
            index=index,
            start=start,
            end=end,
            words=sum(len(line.text.split()) for line in span),
            text=text,
            opened_on_pause=round(gaps[first - 1], 3) if first > 0 else 0.0,
            share=round((end - start) / runtime, 3) if runtime > 0 else 0.0,
        ))
    return sections


# --------------------------------------------------------------------- naming rules


def _name_turn(sections: list[Section], claimable: list[int]) -> int | None:
    """The section opening on a break that stands out from the other breaks.

    Every section here already opens on a long pause — that is what made it a section —
    so "the longest one" is not evidence on its own. It has to be `TURN_MULTIPLE` clear
    of the typical break, or six evenly spaced beats would get a `turn` on whichever
    pause happened to run forty milliseconds long.
    """
    breaks = [section.opened_on_pause for section in sections[1:]]
    if not breaks or not claimable:
        return None
    typical = statistics.median(breaks)
    best = max(claimable, key=lambda index: sections[index].opened_on_pause)
    longest = sections[best].opened_on_pause
    if typical <= 0 or longest < typical * TURN_MULTIPLE:
        return None
    sections[best].name = "turn"
    sections[best].evidence = (
        f"opens on the longest break in the read ({longest:.2f}s), "
        f"{longest / typical:.1f}x this reference's typical {typical:.2f}s beat break — "
        f"something changed here, and a pause cannot say what")
    return best


def _name_escalation(sections: list[Section], claimable: list[int]) -> list[int]:
    """The longest run of consecutive sections each read faster than the last.

    Runs, not the single fastest section: one quick beat is a beat, and what escalation
    sounds like is the read getting faster and staying faster. The run also has to gain
    `ESCALATION_RISE` overall, so three sections drifting up by two percent each do not
    earn the name.
    """
    best: list[int] = []
    current: list[int] = []
    for index in claimable:
        rate = sections[index].words_per_second
        if (current and index == current[-1] + 1
                and rate > sections[current[-1]].words_per_second):
            current.append(index)
        else:
            current = [index]
        if len(current) > len(best):
            best = list(current)

    if len(best) < 2:
        return []
    opening = sections[best[0]].words_per_second
    closing = sections[best[-1]].words_per_second
    if opening <= 0 or (closing - opening) / opening < ESCALATION_RISE:
        return []

    for index in best:
        sections[index].name = "escalation"
        sections[index].evidence = (
            f"delivery rises across these {len(best)} beats, "
            f"{opening:.2f} to {closing:.2f} words/s")
    return best


def _name(sections: list[Section]) -> dict[str, str]:
    """Assign what the measurements support and report every name they do not.

    Order matters and it runs sharpest evidence first: the ends of the reference are
    positional facts, the `turn` is a single measured discontinuity, and `escalation`
    is a trend over several sections. Naming loosely first would let a trend claim a
    section a discontinuity had better evidence for.
    """
    not_claimed = dict(UNCLAIMABLE)

    sections[0].name = "hook"
    sections[0].evidence = (
        "the opening beat — it runs until the narrator first stops for longer than "
        "they stop inside a beat")

    if len(sections) >= 3:
        sections[-1].name = "close"
        sections[-1].evidence = (
            f"the final beat, after the last break of "
            f"{sections[-1].opened_on_pause:.2f}s")
    else:
        # Two sections is a hook and the rest of the video. Calling the second one a
        # close would claim this reference had a middle, which is exactly the invented
        # structure a closed vocabulary makes tempting.
        not_claimed["close"] = (
            "only two beats could be separated, so a `close` here would be the body of "
            "the reference under a second name")

    claimable = [index for index, section in enumerate(sections)
                 if section.name == UNNAMED]
    turn = _name_turn(sections, claimable)
    if turn is None:
        not_claimed["turn"] = (
            "no break stands out — every beat boundary in this read is about as long "
            "as the others, so nothing marks one of them as the moment it changed")

    claimable = [index for index in claimable if index != turn]
    escalation = _name_escalation(sections, claimable)
    if not escalation:
        not_claimed["escalation"] = (
            f"the read never gets {ESCALATION_RISE:.0%} faster across two consecutive "
            f"beats, so nothing measurable is building")

    # `setup` is the beats between the opening and the point the read starts rising.
    # Claimed only when an escalation was found, because the escalation is what gives
    # the slot a measured far edge — without one, "after the hook" is the whole middle
    # of the video and naming it setup is naming it by position.
    if escalation:
        for index in claimable:
            if index < escalation[0] and sections[index].name == UNNAMED:
                sections[index].name = "setup"
                sections[index].evidence = (
                    f"sits between the hook and the point the delivery starts rising "
                    f"at {sections[escalation[0]].start:.2f}s")
    if not any(section.name == "setup" for section in sections):
        not_claimed["setup"] = (
            "nothing marks where a setup would end — that edge is the point the read "
            "starts rising, and this reference has no measured rise"
            if not escalation else
            "the read starts rising immediately after the hook, leaving no beat "
            "between the two")

    for section in sections:
        if section.name == UNNAMED:
            section.evidence = (
                "no measured marker separates this beat from the ones either side of "
                "it — same kind of break, no change in delivery")
    return not_claimed


# ------------------------------------------------------------------------- assembly


def _delivery_trend(lines: list[Line]) -> str:
    """Does the read accelerate, decelerate or hold over the runtime?

    Mean rate across the first third of the lines against the last third, which is
    `shots.pacing_trend`'s own comparison so the two answers are commensurable. The
    sign is inverted relative to that function and this is the trap: it compares shot
    *durations*, where accelerating means the number went down, and this compares
    *rates*, where accelerating means the number went up.
    """
    rates = [line.words_per_second for line in lines if line.seconds > 0]
    if len(rates) < 6:
        return "not_measured"
    third = max(len(rates) // 3, 1)
    head = statistics.fmean(rates[:third])
    tail = statistics.fmean(rates[-third:])
    if head <= 0:
        return "not_measured"
    change = (tail - head) / head
    if change > TREND_CHANGE:
        return "accelerating"
    if change < -TREND_CHANGE:
        return "decelerating"
    return "steady"


def _word_confidence(lines: list[Line]) -> float | None:
    """Mean per-word probability, or `None` when no word carried one."""
    scores = [word.probability for line in lines for word in line.words
              if isinstance(word.probability, (int, float))]
    return statistics.fmean(scores) if scores else None


def section(lines: list[Line], *, runtime: float = 0.0) -> Narrative:
    """Cut a transcript into narrative beats. Pure arithmetic over what was heard.

    Separate from `measure` for the reason `style.sourcing.measure` is separate from
    the decode that feeds it: the sectioning is the part with judgement in it, and it
    can be argued with at a desk against a transcript typed by hand. Fusing it into the
    function that owns the model would mean the only way to test a boundary rule is to
    transcribe a video.
    """
    lines = [line for line in (lines or []) if line.text.strip()]
    spoken = round(sum(line.seconds for line in lines), 3)
    words = sum(len(line.text.split()) for line in lines)
    # A runtime nobody supplied falls back to where the speech ends. Shares are then
    # shares of the narrated span rather than of the video, which is worth saying
    # rather than dividing by zero.
    runtime = float(runtime) if runtime and runtime > 0 else (lines[-1].end if lines else 0.0)

    found = Narrative(
        transcribed=bool(lines),
        runtime_seconds=round(runtime, 3),
        spoken_seconds=spoken,
        speech_share=round(spoken / runtime, 3) if runtime > 0 else 0.0,
        words=words,
        words_per_second=round(words / spoken, 2) if spoken > 0 else 0.0,
        words_per_minute=round(words / spoken * 60, 1) if spoken > 0 else 0.0,
        delivery_trend=_delivery_trend(lines),
        not_claimed=dict(UNCLAIMABLE),
        lines_read=len(lines),
    )
    if not lines:
        found.notes.append("nothing was transcribed, so there is no narrative to read")
        return found

    if len(lines) < MIN_LINES:
        found.confidence = "low"
        found.notes.append(
            f"{len(lines)} line(s) of speech — too short to section. Beat boundaries "
            f"are pauses measured against this read's own typical pause, and under "
            f"{MIN_LINES} lines there are not enough gaps for 'typical' to mean "
            f"anything")
        return found

    bounds, breaks = _boundaries(lines)
    if not bounds:
        found.confidence = "low"
        found.notes.append(
            f"every span between the {breaks} break(s) in this read is under "
            f"{MIN_SECTION_SECONDS}s — beats that short are pauses for effect, not "
            f"sections"
            if breaks else
            "the narrator never stops for longer than they stop inside a sentence, so "
            "there is one continuous beat and no boundary to cut on")
        return found

    found.sections = _build(lines, bounds, runtime)
    found.sectioned = True
    found.hook_ends_at = found.sections[0].end
    found.not_claimed = _name(found.sections)

    # Enough sections to have a shape, and enough lines that each one was read off more
    # than a sentence. Below either, the structure is right where it is and thin
    # everywhere else.
    found.confidence = ("high" if len(found.sections) >= 4 and len(lines) >= 8
                        else "medium")

    hook = found.sections[0]
    if hook.share > 0.4:
        # A slow open, and a finding rather than a fault in the measurement: the first
        # beat really does run past two fifths of the video. Said out loud because the
        # number underneath it — `hook_ends_at` — looks like a bug otherwise.
        found.notes.append(
            f"the opening beat runs {hook.share:.0%} of the runtime — a slow open, or "
            f"a reference that simply does not pause until it is nearly over")

    heard = _word_confidence(lines)
    if heard is not None and heard < SHAKY_WORDS:
        found.confidence = "low"
        found.notes.append(
            f"the transcription model averaged {heard:.2f} confidence per word — the "
            f"timings are still where the speech is, but the quoted text is not "
            f"evidence of what was said")
    return found


def measure(meta: VideoMeta, *, model: str = transcript.DEFAULT_MODEL,
            language: str = "") -> Narrative:
    """Transcribe a learned reference and read its structure. Never raises.

    Slow, because it decodes audio and runs a speech model over it — which is why
    `engine.analyse_file` takes it as an opt-in rather than doing it on every analyse.
    A `compare` or a `restyle --verify` re-measures a file to check an edit landed and
    has no use at all for what the file said.
    """
    lines, why = _transcribe(meta, model=model, language=language)
    if not lines:
        found = Narrative(runtime_seconds=round(meta.duration, 3),
                          not_claimed=dict(UNCLAIMABLE))
        found.notes.append(why)
        return found

    found = section(lines, runtime=meta.duration)
    log.info("narrative: %d sections, hook ends at %s, confidence %s",
             len(found.sections), found.hook_ends_at, found.confidence)
    return found
