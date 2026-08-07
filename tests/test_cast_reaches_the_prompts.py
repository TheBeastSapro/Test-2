"""The locked cast has to reach the shot planner and the shot prompts.

`prompts/cast.py` computed the recurring characters, `nodes/content.py` logged "cast
locked: N recurring faces" and wrote them to `script.cast` — and nothing downstream ever
read them. Every shot prompt was planned and generated without the likenesses, which is
the paraphrase the module's own docstring calls "the thing this module exists to
prevent". These tests are about the connection, not about the cast logic.
"""

from __future__ import annotations

from forgecast.prompts import cast

SCENES = [
    {"index": 0, "narration": "The keeper walks the stair."},
    {"index": 1, "narration": "The keeper looks out to sea."},
    {"index": 2, "narration": "A gull lands on the rail."},
]
RAW = [{"name": "The keeper",
        "description": "a weathered man of seventy in a navy wool coat, white beard",
        "scenes": [0, 1]}]


def _restored():
    """Exactly what `broll_plan_node` does to get a Cast back out of the script."""
    stored = cast.build(RAW, SCENES).as_dict()
    inner = stored.get("characters") if isinstance(stored, dict) else stored
    return cast.build(inner, SCENES)


def test_the_stored_cast_survives_the_round_trip():
    """`script["cast"]` holds the BUILT cast, not the planner's raw answer.

    `nodes/content.py` overwrites its own key with `company.as_dict()`, so handing that
    dict straight back to `build` yields two characters called "characters" and
    "walk_ons". The first version of the wiring did exactly that.
    """
    original = cast.build(RAW, SCENES)
    company = _restored()
    assert [c.name for c in company.characters] == [c.name for c in original.characters]
    assert [c.scenes for c in company.characters] == [c.scenes for c in original.characters]
    assert [c.description for c in company.characters] == [
        c.description for c in original.characters]


def test_the_whole_stored_dict_is_not_mistaken_for_a_character_list():
    """The bug the round trip exists to prevent, asserted directly."""
    stored = cast.build(RAW, SCENES).as_dict()
    wrong = cast.build(stored, SCENES)
    assert "characters" not in [c.name for c in wrong.characters], (
        "passing the wrapper to build invents a character named after the key"
    )


def test_the_planner_is_told_the_locked_descriptions_verbatim():
    block = cast.planner_block(_restored())
    assert "The keeper" in block
    assert "navy wool coat" in block, "the description must go through unparaphrased"
    assert "0, 1" in block, "the planner is told which scenes they appear in"


def test_a_shot_prompt_carries_the_likeness_of_whoever_is_in_it():
    company = _restored()
    base = "Wide shot of a spiral staircase, cold morning light"
    stamped = cast.stamp(base, company.in_scene(0))
    assert base.rstrip(".") in stamped, "the planner's own prose is kept"
    assert "navy wool coat" in stamped


def test_a_shot_without_a_locked_character_is_left_alone():
    """Every locked face costs words in every prompt carrying it."""
    company = _restored()
    base = "Wide shot of a spiral staircase, cold morning light"
    assert cast.stamp(base, company.in_scene(2)) == base


def test_no_cast_changes_nothing():
    """A script with no recurring characters must plan exactly as it did before."""
    company = cast.build(None, SCENES)
    assert cast.planner_block(company) == ""
    base = "A gull on a rail"
    assert cast.stamp(base, company.in_scene(0)) == base
