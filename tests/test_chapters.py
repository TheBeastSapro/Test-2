"""Reading a reference's shape from the marks its creator published.

The decoys carry the weight here. Every case that matters is one where a wrong answer
looks exactly like a right one — a documentary that is not a list, an opening that is
not a unit, a timestamp in a sentence that is not a boundary. The two real fixtures are
descriptions from the channel `reverse-engineer-format.md` records being read wrongly.
"""

from __future__ import annotations

from forgecast.vision import chapters

# Real, from the channel the skill file's worked example is about. Eight segments, no
# cold open, ~60s each — which is what the module has to say without being told.
M_SIMPLIFIED = """Doctor Nowhere's BIGGEST Monsters Explained in 9 Minutes
Like, subscribe and activate the bell!

— TIMESTAMPS —
00:00 Amber
01:05 Housewalker
02:11 Driving Down the Highway
03:18 Unknown Spider Creature
04:22 Watch Tower
05:25 Sunman
06:29 Unnamed Mushroom Creature
07:26 Neph
"""

DOCUMENTARY = """0:00 Introduction
2:40 The discovery
11:05 What went wrong
12:00 Aftermath
25:30 What it means now
"""


def test_an_anthology_is_read_as_one_and_its_unit_measured():
    found = chapters.read(description=M_SIMPLIFIED, runtime_seconds=531)
    assert found.kind == "anthology"
    assert found.repeating
    assert found.unit_count == 8
    assert 60 <= found.unit_seconds <= 70
    assert found.confidence == "high"


def test_no_cold_open_is_reported_as_a_finding():
    """The single fact the skill file's worked example got wrong."""
    found = chapters.read(description=M_SIMPLIFIED, runtime_seconds=531)
    assert found.cold_open is False
    assert found.opening_seconds == 0.0
    assert any("no cold open" in note for note in found.notes)


def test_a_documentary_is_not_called_a_list():
    """Five chapters of wildly different lengths are one argument, not a repeating unit."""
    found = chapters.read(description=DOCUMENTARY, runtime_seconds=1900)
    assert found.kind == "throughline"
    assert not found.repeating
    assert found.unit_seconds is None or found.unit_spread > chapters.REGULAR_SPREAD


def test_an_unmarked_opening_is_counted_as_one():
    found = chapters.read(
        description="1:30 One\n2:35 Two\n3:38 Three\n4:41 Four", runtime_seconds=340)
    assert found.kind == "anthology"
    assert found.cold_open is True
    assert found.opening_seconds == 90.0
    assert found.unit_count == 4


def test_a_marked_opening_is_not_counted_as_a_unit():
    """The decoy that caught the first implementation.

    A creator who gives their cold open its own chapter produces a first mark at 0:00,
    which a naive test reads as "opens on its first unit" while also counting that
    chapter as a unit and dragging the median with it.
    """
    found = chapters.read(
        description="0:00 Cold open\n1:30 One\n2:35 Two\n3:38 Three\n4:41 Four",
        runtime_seconds=340)
    assert found.unit_count == 4, "the opening is not one of the units"
    assert found.cold_open is True
    assert 60 <= found.unit_seconds <= 66, "the opening must not drag the unit length"


def test_a_demoted_first_chapter_says_the_other_reading_exists():
    """An opening and a long first unit are the same shape in timings. Say so."""
    found = chapters.read(
        description="0:00 Cold open\n1:30 One\n2:35 Two\n3:38 Three\n4:41 Four",
        runtime_seconds=340)
    assert any("runs long" in note for note in found.notes)
    assert found.confidence != "high"


def test_a_regular_first_chapter_is_left_alone():
    """Demotion must not fire on a set that is already regular."""
    found = chapters.read(
        description="0:00 One\n1:03 Two\n2:05 Three\n3:08 Four\n4:10 Five",
        runtime_seconds=310)
    assert found.unit_count == 5
    assert found.cold_open is False


def test_numbered_units_are_a_countdown_and_unnumbered_ones_are_not():
    ordered = chapters.read(
        description="0:00 1. First\n1:02 2. Second\n2:05 3. Third\n3:07 4. Fourth",
        runtime_seconds=250)
    plain = chapters.read(
        description="0:00 First\n1:02 Second\n2:05 Third\n3:07 Fourth",
        runtime_seconds=250)
    assert ordered.kind == "countdown"
    assert plain.kind == "anthology"


def test_a_timestamp_inside_a_sentence_is_not_a_boundary():
    found = chapters.read(
        description="Great bit at 4:20 in this one, and 6:12 is worth a look too.",
        runtime_seconds=600)
    assert found.kind == "unknown"
    assert found.unit_count == 0


def test_too_few_marks_claims_nothing_rather_than_guessing():
    found = chapters.read(description="0:00 Start\n5:00 End", runtime_seconds=600)
    assert found.kind == "unknown"
    assert found.cold_open is None, "no marks to tell is not the same as no cold open"


def test_ytdlp_parsed_chapters_are_preferred_over_the_description():
    """The extractor has already resolved each mark's end; a second parse would differ."""
    found = chapters.read(
        description="0:00 Ignore me\n9:99 nonsense",
        chapters=[{"start_time": 0.0, "end_time": 60.0, "title": "One"},
                  {"start_time": 60.0, "end_time": 121.0, "title": "Two"},
                  {"start_time": 121.0, "end_time": 180.0, "title": "Three"},
                  {"start_time": 180.0, "end_time": 240.0, "title": "Four"}],
    )
    assert found.unit_count == 4
    assert [c.label for c in found.chapters] == ["One", "Two", "Three", "Four"]
    assert found.runtime_seconds == 240.0


def test_marks_written_out_of_order_do_not_produce_negative_units():
    found = chapters.read(
        description="0:00 One\n3:08 Four\n1:03 Two\n2:05 Three", runtime_seconds=310)
    assert [c.start for c in found.chapters] == sorted(c.start for c in found.chapters)
    assert all(c.seconds >= 0 for c in found.chapters)


def test_hours_are_read():
    found = chapters.read(
        description="0:00 One\n1:00:00 Two\n2:00:00 Three\n3:00:00 Four",
        runtime_seconds=14400)
    assert found.chapters[1].start == 3600.0
    assert found.chapters[3].start == 10800.0
