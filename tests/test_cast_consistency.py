"""Keeping the same person the same person from shot four to shot sixty.

The shot planner writes every visual prompt independently, so a script that says "a
70-year-old grandmother" in scene two, "the grandmother" in scene seven and "she" in
scene eleven produced three different women. It is the most obvious tell that a machine
made a narrative video, and obvious in a way the others are not: somebody who cannot say
why a grade looks wrong will say instantly that the woman at the window is not the woman
in the kitchen.

The tests worth reading here are the ones about *which* subjects get locked and what a
locked description has to contain, because both were wrong in the first implementation
and both were wrong in the direction that silently drops the character who most needed
locking.
"""

from __future__ import annotations

from forgecast.prompts import cast

GRANDMOTHER = ("a 70-year-old woman with short white hair, wire-rimmed glasses on a "
               "chain, and a beige cable-knit cardigan")
REYES = "a woman in her forties, dark hair pulled back, navy scrubs under a grey coat"


def _scenes(*narrations: str) -> list[dict]:
    return [{"index": index, "narration": text, "visual_prompt": ""}
            for index, text in enumerate(narrations)]


# ------------------------------------------------------------------ who gets locked


def test_someone_in_two_scenes_is_locked():
    company = cast.build(
        [{"name": "the grandmother", "description": GRANDMOTHER}],
        _scenes("the grandmother waits", "nothing", "the grandmother reads"))
    assert [one.name for one in company.characters] == ["the grandmother"]
    assert company.by_key("grandmother").scenes == (0, 2)


def test_someone_in_one_scene_is_not_locked_and_is_said_so():
    """They cannot be inconsistent with themselves, and every locked face costs words in
    every prompt carrying it. The name is still reported, so an operator asking why the
    courier drifted finds "he appears once" rather than nothing."""
    company = cast.build(
        [{"name": "the courier", "description": "a man in a red uniform"}],
        _scenes("a courier knocks", "she opens the letter"))
    assert company.characters == []
    assert company.walk_ons == ["the courier"]


def test_a_character_introduced_in_full_and_then_shortened_is_still_found():
    """The bug the first implementation had, on exactly the case the fallback exists for.

    A script introduces "Dr Elena Reyes" and thereafter writes "Reyes". Matching on the
    name's longest word picked "elena", found her once, and dropped her as a walk-on —
    the character most worth locking, discarded by the code meant to catch her.
    """
    company = cast.build(
        [{"name": "Dr Elena Reyes", "description": REYES}],
        _scenes("Dr Reyes knocked twice", "the door stayed shut",
                "Reyes found the letter"))
    assert [one.name for one in company.characters] == ["Dr Elena Reyes"]
    assert company.characters[0].scenes == (0, 2)


def test_an_honorific_does_not_make_every_doctor_the_same_doctor():
    """"Dr" left in the match would be this module's own failure, inverted."""
    company = cast.build(
        [{"name": "Dr Patel", "description": REYES}],
        _scenes("Dr Osei examined the notes", "Dr Lindqvist disagreed"))
    assert company.characters == []


def test_stated_scene_numbers_win_over_reading_the_narration():
    """The model knows who is in a shot better than a word match does. Reading the
    narration is the fallback for when it did not say."""
    company = cast.build(
        [{"name": "the pilot", "description": REYES, "scenes": [4, 9]}],
        _scenes("nothing here", "nor here"))
    assert company.by_key("pilot").scenes == (4, 9)


def test_the_same_character_listed_twice_is_one_character():
    """A model that lists someone twice usually describes them well once, so the fuller
    description wins and the scene lists merge."""
    company = cast.build([
        {"name": "The Grandmother", "description": "an old woman", "scenes": [0]},
        {"name": "the grandmother", "description": GRANDMOTHER, "scenes": [3]},
    ], [])
    assert len(company.characters) == 1
    assert company.characters[0].description == GRANDMOTHER
    assert company.characters[0].scenes == (0, 3)


def test_a_crowd_is_capped_at_the_faces_a_viewer_tracks():
    """More than a handful is not a cast, and locking them all would put a hundred words
    of description into every prompt — pushing the shot out of its own attention."""
    raw = [{"name": f"person {index}", "description": REYES,
            "scenes": list(range(index, index + 2 + index))}
           for index in range(12)]
    company = cast.build(raw, [])
    assert len(company.characters) == cast.MAX_CAST
    # The most-seen faces survive the cap, not whoever the model listed first.
    counts = [one.appearances for one in company.characters]
    assert counts == sorted(counts, reverse=True)
    assert len(company.walk_ons) == 12 - cast.MAX_CAST


# ------------------------------------------------------------------ the description


def test_a_label_is_not_a_likeness():
    """"An old woman" produces a different old woman every time, which is the failure."""
    assert cast.thin_description("an old woman")
    assert not cast.thin_description(GRANDMOTHER)


def test_a_description_naming_no_physical_trait_is_flagged():
    """There has to be something in it for the model to hold still. A role and a mood
    both change from shot to shot; a cardigan does not."""
    assert cast.thin_description(
        "a determined and resourceful investigator who never gives up on a case")


def test_a_biography_is_flagged_too():
    """It crowds the shot out of its own prompt."""
    assert cast.thin_description(" ".join(["word"] * 60))


def test_an_empty_description_says_what_will_happen():
    assert "invent" in cast.thin_description("")


def test_a_weak_description_is_warned_about_and_never_rewritten():
    """Padding it would invent a face nobody chose and then lock eighty shots to it."""
    company = cast.build(
        [{"name": "the man", "description": "a man", "scenes": [0, 1]}], [])
    assert company.characters[0].description == "a man"
    assert cast.thin_description(company.characters[0].description)


# ------------------------------------------------------------------ the prompt


def test_the_likeness_is_appended_rather_than_spliced_into_the_sentence():
    """Rewriting the planner's prose to work a description in is a second generation of
    paraphrase — the thing this module exists to prevent — and it breaks the prompt
    skeleton where subject, action, camera and lighting each hold their own clause."""
    company = cast.build([{"name": "the grandmother", "description": GRANDMOTHER,
                           "scenes": [0, 1]}], [])
    original = "She looks up from the letter; static medium close-up, warm window light"
    stamped = cast.stamp(original, company.characters)
    assert stamped.startswith(original.rstrip("."))
    assert GRANDMOTHER in stamped


def test_only_the_characters_in_this_shot_are_stamped():
    """Not an optimisation. A prompt holding six descriptions has pushed its own subject
    out of the model's attention."""
    company = cast.build([
        {"name": "the grandmother", "description": GRANDMOTHER, "scenes": [0, 1]},
        {"name": "Reyes", "description": REYES, "scenes": [2, 3]},
    ], [])
    stamped = cast.stamp("a kitchen at dawn", company.in_scene(0))
    assert GRANDMOTHER in stamped
    assert REYES not in stamped


def test_the_description_is_reused_word_for_word():
    """Verbatim is the operative word. A planner asked to describe someone consistently
    produces eleven consistent-sounding descriptions of eleven different women."""
    company = cast.build([{"name": "x", "description": GRANDMOTHER, "scenes": [0, 1]}], [])
    first = cast.stamp("shot one", company.in_scene(0))
    second = cast.stamp("shot two", company.in_scene(1))
    assert GRANDMOTHER in first
    assert GRANDMOTHER in second


def test_a_character_with_no_description_is_not_stamped_as_a_blank():
    company = cast.build([{"name": "the man", "description": "", "scenes": [0, 1]}], [])
    assert cast.stamp("a doorway", company.characters) == "a doorway"


def test_the_planner_is_told_up_front_as_well_as_stamped_afterwards():
    """Stamping alone leaves the planner free to write "an older woman looks up" for
    someone locked as a seventy-year-old — the prompt then carries two descriptions of one
    person and the model resolves the contradiction however it likes."""
    company = cast.build([{"name": "the grandmother", "description": GRANDMOTHER,
                           "scenes": [0, 1]}], [])
    block = cast.planner_block(company)
    assert GRANDMOTHER in block
    assert "do not paraphrase" in block
    assert cast.planner_block(cast.Cast()) == ""


# ------------------------------------------------------------------ tolerance


def test_a_model_returning_a_dict_instead_of_a_list_still_works():
    """This reads a language model's output, and the script is already written and
    approved by the time it runs. A shape surprise is not worth failing a paid run over."""
    company = cast.build({"the grandmother": GRANDMOTHER},
                         _scenes("the grandmother waits", "the grandmother reads"))
    assert [one.name for one in company.characters] == ["the grandmother"]


def test_alternative_field_names_are_accepted():
    company = cast.build([{"who": "the grandmother", "appearance": GRANDMOTHER,
                           "appears_in": [0, 2]}], [])
    assert company.characters[0].description == GRANDMOTHER


def test_nothing_at_all_is_an_empty_cast_rather_than_an_error():
    for value in (None, [], {}, "grandmother", 7):
        assert not cast.build(value, [])


# ------------------------------------------------------------------ reachability


def test_the_script_stage_asks_for_a_cast_and_stores_one():
    import inspect

    from forgecast.nodes import content

    source = inspect.getsource(content.script_node)
    assert "cast.SCRIPT_INSTRUCTION" in source
    assert "cast.build" in source
    # Warned about, not silently padded.
    assert "thin_description" in source


def test_the_cast_is_visible_in_the_document_the_gate_shows():
    """A description nobody read is a face that turns up identical in eighty shots and
    wrong in all of them. The script gate is the last point where changing it is free."""
    from forgecast.nodes.content import _as_markdown

    company = cast.build([
        {"name": "the grandmother", "description": GRANDMOTHER, "scenes": [0, 1]},
        {"name": "the courier", "description": "a man in red", "scenes": [2]},
    ], [])
    page = _as_markdown({"title": "t", "word_count": 10, "estimated_seconds": 60,
                         "scenes": [], "cast": company.as_dict()})
    assert "## Cast" in page
    assert GRANDMOTHER in page
    # And the ones deliberately not locked, so the decision is visible rather than absent.
    assert "the courier" in page


def test_a_script_with_no_cast_does_not_grow_an_empty_heading():
    from forgecast.nodes.content import _as_markdown

    page = _as_markdown({"title": "t", "word_count": 10, "estimated_seconds": 60,
                         "scenes": [], "cast": cast.Cast().as_dict()})
    assert "## Cast" not in page


# ------------------------------------------------------------------ every language


def test_a_name_in_a_non_latin_script_is_not_silently_dropped():
    """The worst bug this module had, and it was invisible.

    Keys were built with `[a-z]+`, so a name written in Cyrillic, Arabic, Devanagari or
    Japanese produced no words at all, keyed to empty, and was discarded before it could
    be locked. This app carries a `language` per channel, so an Arabic or Hindi channel
    had no character consistency whatsoever and nothing anywhere said so.
    """
    for name in ("Дмитрий", "الأم", "田中", "मीरा", "Ólafsdóttir"):
        company = cast.build(
            [{"name": name, "description": REYES, "scenes": [0, 1]}], [])
        assert [one.name for one in company.characters] == [name], name
        assert company.characters[0].key, f"{name} keyed to nothing"


def test_a_name_with_digits_is_its_own_character():
    """"Agent 47" and "Agent 12" keyed as "agent" and merged into one person."""
    company = cast.build([
        {"name": "Agent 47", "description": REYES, "scenes": [0, 1]},
        {"name": "Agent 12", "description": GRANDMOTHER, "scenes": [2, 3]},
    ], [])
    assert len(company.characters) == 2


def test_a_short_name_is_found_in_the_narration_rather_than_skipped():
    """Plenty of names are two characters. The rule that drops short words exists to stop
    "the" and "dr" matching everything, and a two-character name is not that problem."""
    company = cast.build(
        [{"name": "田中", "description": REYES}],
        _scenes("田中 opened the door", "nothing here", "田中 read the letter"))
    assert company.characters and company.characters[0].scenes == (0, 2)
