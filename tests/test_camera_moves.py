"""The camera vocabulary, and the pipeline actually using it.

`nodes/media.py` asked the planner for a `motion` string and appended it to the shot
prompt verbatim — so "dramatic sweeping movement" reached the generator exactly like
that. Meanwhile `skills/data/i2v-prompt-cookbook.md` carried 229 lines of real craft
about camera phrasing that had never touched the pipeline. This is the executable half.
"""

from __future__ import annotations

from pathlib import Path

from forgecast.prompts import moves


def test_every_move_says_what_it_is_for_and_carries_a_fragment():
    """A move with no fragment is a label, which is what the pipeline already had."""
    for move in moves.CATALOGUE:
        assert move.fragment.strip(), f"{move.key} has no prompt fragment"
        assert move.when_to_use.strip(), f"{move.key} does not say when to use it"
        assert 0.0 <= move.intensity <= 1.0


def test_free_text_is_matched_rather_than_rejected():
    """Every stored shot list already holds free text, and the planner is a language
    model that will write "slowly pushing in" the day after something teaches it to
    write "push_in"."""
    assert moves.resolve("slow push in").key == "push_in"
    assert moves.resolve("slowly pushing in toward her").key == "push_in"
    assert moves.resolve("FPV drone rush through").key == "fpv"
    assert moves.resolve("locked off on a tripod").key == "static"


def test_an_unrecognised_move_becomes_the_one_that_is_wrong_least_often():
    """Not an error several minutes into a paid render, and not nothing."""
    assert moves.resolve("dramatic sweeping cinematic energy").key == "push_in"
    assert moves.resolve("").key == "push_in"
    assert moves.resolve("!!!").key == "push_in"


def test_a_longer_alias_wins_over_a_shorter_one():
    """Otherwise a phrase belonging to one move is captured by a fragment of another,
    and the shot gets a camera nobody asked for."""
    assert moves.resolve("crash zoom").key == "crash_zoom"
    assert moves.resolve("zoom in slowly").key == "push_in"


def test_intensity_selects_on_the_same_scale_transitions_use():
    """A channel whose cutting is calm and whose camera is a crash zoom is two style
    decisions disagreeing inside one video."""
    from forgecast.render import transitions

    assert moves.for_intensity(0.0).key == "static"
    assert moves.for_intensity(1.0).intensity >= 0.85
    assert transitions.for_intensity(0.0).key == "cut"


def test_a_move_the_shot_cannot_contain_is_downgraded():
    """An orbit given two seconds does not render as a slower orbit — it renders as a
    wobble. A locked-off camera is the honest outcome."""
    move, fragment = moves.fragment_for("orbit around it", seconds=2.0)
    assert move.key == "static"
    assert "locked off" in fragment

    move, _ = moves.fragment_for("orbit around it", seconds=6.0)
    assert move.key == "orbit"


def test_a_move_with_no_minimum_survives_a_short_shot():
    """A crash zoom is punctuation. It is supposed to happen in half a second."""
    move, _ = moves.fragment_for("crash zoom", seconds=0.6)
    assert move.key == "crash_zoom"


def _media_source() -> str:
    return (Path(moves.__file__).resolve().parents[1] / "nodes" / "media.py").read_text()


def test_the_shot_node_sends_the_fragment_and_not_the_planners_words():
    """The whole point. `motion` was concatenated raw into the prompt."""
    body = _media_source()
    assert "camera_moves.fragment_for(" in body
    assert "Camera: {shot.get('motion'" not in body, (
        "the raw planner string is still being appended")


def test_the_planner_is_given_the_vocabulary_to_pick_from():
    """Appended at the call site rather than written into the constant, so a move added
    to the catalogue reaches the planner without a second copy of the list."""
    assert "camera_moves.planner_vocabulary()" in _media_source()

    listed = moves.planner_vocabulary()
    for move in moves.CATALOGUE:
        assert move.key in listed, f"{move.key} is not offered to the planner"
    assert len(listed) < 2000, f"the vocabulary is {len(listed)} characters"


def test_the_artifact_records_the_camera_that_actually_ran():
    """Not the one asked for. A shot too short to contain its move is downgraded, and
    without this the artifact claims a camera the video does not have."""
    assert "camera=move.key" in _media_source()
