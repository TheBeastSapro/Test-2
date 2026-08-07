"""What gives a script away as machine-written, checked on the finished text.

method.py bans nine constructions and puts them in the prompt. That is a request, and
this module exists because a request is not a check — this codebase's own notes say
twice that an instruction the model may treat as context is one it drops once the output
gets long, and a script is exactly the output that gets long. Nothing looked at what came
back.
"""

from __future__ import annotations

from forgecast.scripting import tells

# The reference channel's own narration, from its transcript — a human-edited script
# read by TTS. It is the control: if this trips the checker, the checker is wrong.
REFERENCE = (
    "Amber. One night in a quiet town, a young man noticed his neighbor's lights "
    "flicker. He looked outside and saw something tall standing beside the house. At "
    "first, it didn't move. Then suddenly, its arm stretched forward and smashed through "
    "the window. He froze. The creature pulled something out, a child. As it stepped back "
    "into the dim light, he realized it had no head. Its chest slowly opened. An eye "
    "stared forward, and then it split into a mouth. The man couldn't move. He could only "
    "watch as it lifted the child and swallowed it whole. No sound, no struggle."
)


def test_real_narration_passes():
    """The control. A checker that flags the thing it was measured against is a checker
    that will be turned off."""
    report = tells.check(REFERENCE)

    assert report.clean, report.as_text()


def test_the_banned_openers_are_caught_despite_their_placeholder():
    """`method.BANNED` writes its entries the way a person reads them — "In the world of
    X". Matched literally those could only fire on a script containing the letter X, so
    the most common machine opener on the list was unenforceable."""
    for opener in ("In the world of deep-sea cables, things break.",
                   "When it comes to undersea repair, ships are slow.",
                   "In today's world, nobody notices."):
        kinds = [tell.kind for tell in tells.check(opener).tells]
        assert "banned phrase" in kinds, opener


def test_a_banned_phrase_always_carries_its_replacement():
    """A ban with nothing on the other side gets obeyed twice and then dropped, because
    the writer still has to put something in the slot."""
    report = tells.check("In the world of cables, little did they know.")
    named = [tell for tell in report.tells if tell.kind == "banned phrase"]

    assert named
    assert all(tell.instead for tell in named)


def test_the_placeholder_cannot_swallow_a_sentence():
    """A greedy wildcard would match across a full stop and flag prose that merely
    contains the opening words somewhere far apart."""
    text = ("In the room the air was still. Nobody spoke of the world of cables for "
            "another hour.")

    assert not [tell for tell in tells.check(text).tells if tell.kind == "banned phrase"]


def test_the_current_machine_cadence_is_caught_in_its_variants():
    for line in ("It is not just a cable, but a lifeline.",
                 "Not only is it deep, it's also long.",
                 "This was not merely damage, but a warning."):
        kinds = [tell.kind for tell in tells.check(line).tells]
        assert "machine cadence" in kinds, line


def test_hedging_is_counted_per_hundred_words_not_absolutely():
    """One hedge in a long script is fine; four in ninety words is a narrator with no
    position, which is the specific thing an explainer cannot afford."""
    dense = ("Perhaps it broke. Arguably the cause is somewhat unclear. Possibly the "
             "ship was seemingly at fault.")
    sparse = "Perhaps it broke. " + "The cable runs from Lisbon to Recife. " * 30

    assert any(t.kind == "hedging" for t in tells.check(dense).tells)
    assert not any(t.kind == "hedging" for t in tells.check(sparse).tells)


def test_a_tricolon_habit_is_flagged_and_one_list_is_not():
    once = "Ships, anchors and trawlers cause most of it. " + "It runs deep. " * 30
    habit = ("Engineers, operators, and regulators agree. Ships, anchors, and trawlers "
             "cause it. Repair, inspection, and monitoring follow.")

    assert not any(t.kind == "rhythm habit" for t in tells.check(once).tells)
    assert any(t.kind == "rhythm habit" for t in tells.check(habit).tells)


def test_metronomic_prose_is_flagged_and_varied_prose_is_not():
    even = " ".join(["The cable runs beneath the cold Atlantic water."] * 8)
    varied = ("The cable runs beneath the cold Atlantic water for four thousand "
              "kilometres without once touching land. It broke. Nobody noticed for six "
              "hours, because the traffic simply rerouted itself through a second line "
              "that nobody had thought about in years. Then that one broke too.")

    assert any(t.kind == "metronomic" for t in tells.check(even).tells)
    assert not any(t.kind == "metronomic" for t in tells.check(varied).tells)


def test_a_short_script_is_not_judged_on_rhythm():
    """Four sentences is not evidence of a habit, and flagging on noise is how a check
    gets ignored."""
    assert tells.rhythm("One. Two. Three.") == 1.0
    assert not any(t.kind == "metronomic" for t in tells.check("It broke. We fixed it.").tells)


def test_the_checker_reports_and_never_rewrites():
    """A checker that silently fixes its own findings is one nobody can audit, and the
    point is that a person sees the list."""
    import inspect

    source = inspect.getsource(tells)
    assert "def check(" in source
    assert "def rewrite" not in source and "def fix" not in source


def test_findings_carry_a_location_and_a_quote():
    """A finding a person cannot go and look at is a finding they will not act on."""
    report = tells.check("It is not just a cable, but a lifeline. " + "It runs. " * 20)
    cadence = next(t for t in report.tells if t.kind == "machine cadence")

    assert cadence.where >= 0
    assert "not just a cable" in cadence.quote


def test_the_report_reads_as_prose_for_a_person():
    text = tells.check(REFERENCE).as_text()

    assert "nothing flagged" in text
    assert "words" in text
