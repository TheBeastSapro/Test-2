"""Which of the script's hard claims the research actually stands behind.

`research` verifies claims against fetched sources and hands the writer a list. Nothing
checked whether the script used it. `research_node` already logs the case it fears —
"no verifiable claims found, the script will be written without factual assertions
rather than with invented ones" — and that log was a hope, because nothing read the
script back. A model asked for a documentary supplies numbers, since the genre expects
them, and a fabricated figure looks exactly like a sourced one.
"""

from __future__ import annotations

from forgecast.scripting import grounding, tells

CLAIMS = [
    {"text": "Around 200 submarine cable faults occur each year.",
     "quote": "roughly 200 faults are recorded annually"},
    {"text": "The Atlantic crossing is about 6,600 km.",
     "quote": "6600 km between Europe and North America"},
]


def test_a_figure_in_the_research_is_supported():
    report = grounding.check("There are about 200 faults a year.", CLAIMS)

    assert report.checked == 1
    assert report.supported == 1
    assert report.clean


def test_a_figure_from_nowhere_is_flagged():
    """The failure worth catching: a number the research never produced."""
    report = grounding.check("Repairs cost $2.4 million per incident.", CLAIMS)
    figures = [item for item in report.findings if item.kind == "figure"]

    assert len(figures) == 1
    assert "2.4" in figures[0].token


def test_a_decimal_does_not_split_the_sentence_and_hide_the_figure():
    """The bug this file was written by. The naive splitter broke "$2.4 million" into
    "$2" and ".4 million" — "$2" is a trivial number and ".4" no longer parsed as one,
    so the figure vanished from the check entirely while everything still ran. It also
    made every decimal two sentences, which wrecked the rhythm statistic next door."""
    assert tells.sentences("Repairs cost $2.4 million per incident. It broke.") == [
        "Repairs cost $2.4 million per incident.", "It broke."]


def test_formatting_differences_still_count_as_support():
    """6,600 in the script against 6600 in the source is the same number, and a check
    that failed on a comma would flag every sourced figure in the script."""
    report = grounding.check("The run is 6,600 km.", CLAIMS)

    assert report.supported == 1
    assert report.clean


def test_a_year_is_reported_as_a_date_rather_than_a_figure():
    report = grounding.check("The first cable was laid in 1858.", CLAIMS)
    kinds = {item.kind for item in report.findings}

    assert "year" in kinds or "figure" in kinds
    assert any(item.token == "1858" for item in report.findings)


def test_an_unsourced_superlative_is_flagged():
    """A claim about a maximum is what a documentary is judged on, and what a model
    reaches for to sound authoritative."""
    report = grounding.check("This is the deepest cable ever laid.", CLAIMS)

    assert any(item.kind == "superlative" and item.token == "deepest"
               for item in report.findings)


def test_one_superlative_per_sentence_not_four():
    """A stack of them is one claim, not four findings nobody reads."""
    report = grounding.check("It is the largest, longest and deepest ever built.",
                             CLAIMS)
    supers = [item for item in report.findings if item.kind == "superlative"]

    assert len(supers) == 1


def test_trivial_numbers_are_not_claims():
    """"one of the", "two things", "3am". Flagging these produces a wall nobody reads,
    and a check nobody reads does not exist."""
    report = grounding.check("There are 2 ends and 1 cable between them.", CLAIMS)

    assert report.checked == 0


def test_unverifiable_prose_is_not_checked():
    """"The sea is dark down there" cannot be checked, and pretending to would bury the
    findings that matter."""
    report = grounding.check("The sea is dark down there and very cold.", CLAIMS)

    assert report.checked == 0
    assert "No checkable" in report.as_text()


def test_a_script_with_no_research_flags_everything_checkable():
    """The state research_node warns about. With nothing verified, every figure in the
    script came from the model."""
    report = grounding.check("There are 200 faults and 6,600 km of cable.", [])

    assert report.checked == 2
    assert report.supported == 0
    assert report.claims_available == 0


def test_the_share_is_one_when_there_is_nothing_to_check():
    """So a script of pure narrative does not report 0% grounded and read as a failure."""
    assert grounding.check("It was dark.", CLAIMS).share == 1.0


def test_findings_carry_the_sentence_they_are_in():
    """A finding a person cannot go and look at is a finding they will not act on."""
    report = grounding.check("Repairs cost $2.4 million per incident.", CLAIMS)

    assert report.findings[0].sentence.startswith("Repairs cost")
    assert report.findings[0].where >= 0


def test_it_reports_and_never_edits():
    import inspect

    source = inspect.getsource(grounding)
    assert "def rewrite" not in source and "def fix" not in source


def test_claims_may_arrive_as_objects_or_dicts():
    """So this runs against a stored run as easily as a live one."""
    class Row:
        text = "Around 200 faults occur each year."
        quote = ""
        note = ""

    assert grounding.check("About 200 faults.", [Row()]).supported == 1
