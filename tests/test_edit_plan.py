"""The paper edit — decided and written down before anything is cut.

A professional editor watches the footage, logs it, and writes a paper edit before
opening a timeline. Forgecast had `ingest` (measures) and `render` (executes) and
nothing in between, so a decision was either implicit in whichever function ran next or
absent. This is the middle, and it is an object rather than a function call because it
is the cheapest possible place to disagree with the machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise

import pytest

from forgecast.edit import plan as edit_plan
from forgecast.edit import tighten


# A stand-in for `ingest.Ingest`, so these tests do not need ffmpeg or a model. The plan
# reads measurements and nothing else, which is exactly what makes that possible — and
# is the reason the two packages are separate.
@dataclass
class _Media:
    duration: float
    width: int = 1920
    height: int = 1080
    fps: float = 30.0
    has_audio: bool = True


@dataclass
class _Quiet:
    start: float
    end: float

    @property
    def seconds(self) -> float:
        return round(self.end - self.start, 3)


@dataclass
class _Word:
    text: str
    start: float
    end: float

    @property
    def is_filler(self) -> bool:
        return self.text.strip().lower() in {"um", "uh", "erm"}


@dataclass
class _Line:
    words: list = field(default_factory=list)


@dataclass
class _Found:
    path: str
    media: _Media
    quiet: list = field(default_factory=list)
    lines: list = field(default_factory=list)
    shots: list = field(default_factory=list)
    missing: list = field(default_factory=list)


def test_dead_air_comes_out_and_the_rhythm_of_speech_stays():
    """The line between them is the whole craft.

    Removing the natural space between sentences produces the gapless, breathless
    rhythm that is the single most recognisable sound of an automatically edited video.
    """
    found = _Found("clip.mp4", _Media(30.0), quiet=[
        _Quiet(5.0, 9.0),      # dead air — out
        _Quiet(12.0, 12.3),    # the space between two sentences — stays
        _Quiet(20.0, 21.5),    # dead air — out
    ])
    result = tighten(found)

    dropped = [item for item in result.decisions if item.action == "drop"]
    assert len(dropped) == 2, "the 0.3s gap between sentences was cut"
    assert result.removed_seconds > 5.0
    assert result.final_seconds < 30.0


def test_a_cut_leaves_a_breath_either_side():
    """Cutting a silence to nothing lands the join on the breath and runs the words
    together. It is the difference between tightened and clipped."""
    found = _Found("clip.mp4", _Media(20.0), quiet=[_Quiet(5.0, 9.0)])
    cut = next(item for item in tighten(found).decisions if item.action == "drop")
    assert cut.start > 5.0
    assert cut.end < 9.0
    assert cut.seconds == pytest.approx(4.0 - 2 * edit_plan.BREATH_SECONDS, abs=0.01)


def test_a_filler_inside_a_silence_is_one_cut_not_two():
    """Two abutting cuts applied separately remove the breath between them twice, which
    is how a tightened edit clips the start of the next word."""
    found = _Found(
        "clip.mp4", _Media(20.0),
        quiet=[_Quiet(5.0, 9.0)],
        lines=[_Line(words=[_Word("um", 6.0, 6.4)])])
    dropped = [item for item in tighten(found).decisions if item.action == "drop"]
    assert len(dropped) == 1, f"expected one merged cut, got {len(dropped)}"


def test_a_kept_sliver_is_absorbed_rather_than_flashed():
    """Trimming a breath either side of every silence leaves fragments at the edges. A
    real plan produced a 0.06s keep — 1.4 frames, which reads as a glitch."""
    found = _Found("clip.mp4", _Media(10.0), quiet=[_Quiet(0.5, 5.0), _Quiet(5.1, 9.95)])
    result = tighten(found)
    for keep in result.kept:
        assert keep.seconds >= edit_plan.MIN_KEEP_SECONDS, (
            f"a {keep.seconds}s keep survived — that is a flash, not a shot")


def test_the_keeps_and_the_drops_together_account_for_the_whole_file():
    """A plan that only lists removals cannot be executed without re-deriving the
    inverse, and the two derivations disagreeing is a frame lost at every join."""
    found = _Found("clip.mp4", _Media(30.0),
                   quiet=[_Quiet(4.0, 8.0), _Quiet(15.0, 18.0)])
    result = tighten(found)
    covered = sum(item.seconds for item in result.decisions)
    assert covered == pytest.approx(30.0, abs=0.05)
    # And nothing overlaps, or the executed timeline repeats footage.
    spans = sorted((item.start, item.end) for item in result.decisions)
    for (_, first_end), (second_start, _) in pairwise(spans):
        assert second_start >= first_end - 0.001


def test_every_decision_says_why():
    """"Removed 2.4s" invites no response. "Removed 2.4s of silence before the answer"
    can be answered with "no, that pause was the joke". A plan you cannot argue with is
    one you have to accept or discard whole."""
    found = _Found("clip.mp4", _Media(20.0), quiet=[_Quiet(5.0, 9.0)])
    for item in tighten(found).decisions:
        assert item.why.strip(), f"a {item.action} with no reason"
        assert item.source.strip(), f"a {item.action} that cannot be audited"


def test_what_the_plan_could_not_see_is_carried_into_it():
    """A plan built without a transcript is a different plan, and the operator has to
    see it was built that way."""
    found = _Found("clip.mp4", _Media(20.0), quiet=[_Quiet(5.0, 9.0)],
                   missing=["transcript (the edit extra is not installed)"])
    result = tighten(found)
    assert result.unknown
    assert "could not see" in result.as_markdown()


def test_the_plan_reads_as_a_decision_rather_than_as_a_log():
    """Sixty "removed 0.8s of silence" lines is a log. "47.2s across 38 places" is
    something somebody can accept or reject in one read."""
    found = _Found("clip.mp4", _Media(120.0),
                   quiet=[_Quiet(float(n), n + 2.0) for n in range(5, 100, 10)])
    text = tighten(found).as_markdown()
    assert "What comes out" in text
    assert "tighter" in text
    # Grouped, not enumerated: one line per reason, not one per cut.
    assert text.count("- **") <= 3


def test_nothing_is_cut_from_footage_with_nothing_to_cut():
    found = _Found("clip.mp4", _Media(10.0))
    result = tighten(found)
    assert result.removed_seconds == 0.0
    assert result.final_seconds == 10.0
    assert len(result.kept) == 1
