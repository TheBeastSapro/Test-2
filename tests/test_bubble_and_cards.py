"""The three things the reference puts on screen instead of narration captions.

Measured: that channel burns no subtitles at all. Its screen carries the entity's name,
its height and weight, and speech-bubble jokes, while the voice carries the prose. The
bubbles are not decoration — the most-liked comment on a nine-minute video quotes one
that is on screen for about two seconds, and the next two most-liked parody the survival
block and the narrator's flatness. Copy the anecdotes and drop the bubbles and you have
reproduced everything except the reason anybody comments.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from forgecast.motion import bubble
from forgecast.motion.presets import LIBRARY, name_card, stat_card

PRESET = LIBRARY["card_reveal"]
FRAME = {"width": 1920, "height": 1080}


# ── speech bubbles ──────────────────────────────────────────────────────────────

def test_a_bubble_renders_with_transparency_and_a_tail(tmp_path):
    path = bubble.draw("There's a good snack in this house", tmp_path / "b.png", **{
        "frame_width": 1920, "frame_height": 1080})

    image = Image.open(path)
    assert image.mode == "RGBA"
    # The tail hangs below the body, so the canvas is taller than the text block.
    assert image.height > bubble.TAIL_H
    # Corners must be clear: a bubble drawn as an opaque rectangle is a caption.
    assert image.getpixel((0, 0))[3] == 0


def test_nothing_to_say_draws_nothing(tmp_path):
    """An empty gag must not become an empty white box on screen."""
    assert bubble.draw("", tmp_path / "a.png") is None
    assert bubble.draw("   \n  ", tmp_path / "b.png") is None


def test_the_tail_side_changes_the_shape(tmp_path):
    """The tail points at the speaker, and on a composited shot the speaker is on one
    side. Two bubbles that differ only in tail must not be the same picture."""
    left = bubble.draw("Same words", tmp_path / "l.png", tail="left")
    right = bubble.draw("Same words", tmp_path / "r.png", tail="right")

    assert left.read_bytes() != right.read_bytes()


def test_wrapping_breaks_at_words_and_never_hyphenates():
    lines = bubble.wrap("It looks like a mushroom bigger than yours")

    assert len(lines) > 1
    assert all(not line.startswith(" ") for line in lines)
    assert " ".join(lines) == "It looks like a mushroom bigger than yours"


def test_a_long_line_is_capped_rather_than_becoming_a_paragraph():
    """A bubble is a punchline. Past a point it stops reading as somebody speaking."""
    lines = bubble.wrap("word " * 200)

    assert sum(len(line) for line in lines) <= bubble.MAX_CHARS + len(lines)


def test_the_same_joke_lands_on_the_same_file(tmp_path):
    """Hashed rather than counted, so re-rendering a scene does not accumulate
    bubble_1..bubble_40 across retries."""
    first = bubble.path_for("A joke", tmp_path)
    again = bubble.path_for("A joke", tmp_path)
    other = bubble.path_for("A different joke", tmp_path)

    assert first == again
    assert first != other


def test_the_tail_side_is_part_of_the_identity(tmp_path):
    assert bubble.path_for("x", tmp_path, tail="left") != \
        bubble.path_for("x", tmp_path, tail="right")


# ── name and stat cards ─────────────────────────────────────────────────────────

def test_the_name_card_sits_clear_of_the_caption_zone():
    """These have to coexist with burned captions on a channel that does burn them."""
    from forgecast.motion.presets import CAPTION_SAFE_BOTTOM

    for element in name_card(PRESET, "House Walker", start=0.2, **FRAME):
        assert element.y < CAPTION_SAFE_BOTTOM


def test_the_name_card_uses_the_learned_accent_rather_than_a_constant():
    """A name card that ignores the reference's palette is a card from another
    channel."""
    tinted = PRESET.variant("other", accent_colour="#00ff88")

    assert name_card(tinted, "Amber", start=0.0, **FRAME)[0].colour == "#00ff88"


def test_the_stat_card_takes_the_shape_the_wiki_reader_returns():
    """The infobox reaches the screen without a translation step. The one place these
    numbers exist is that page, and re-typing them is how a video ends up disagreeing
    with its own source."""
    stats = {"height": "Around 13 to 33 feet",
             "weight": "Approximately 456 lbs (206 kg)",
             "species": "Unknown"}

    rows = stat_card(PRESET, stats, start=0.0, **FRAME)

    assert len(rows) == 3
    assert "13 to 33 feet" in rows[0].text
    assert rows[0].text.startswith("HEIGHT")


def test_stat_rows_keep_a_fixed_order_across_segments():
    """Two segments of the same video must not put height in different places."""
    first = stat_card(PRESET, {"weight": "1 kg", "height": "2 m"}, start=0.0, **FRAME)
    second = stat_card(PRESET, {"height": "9 m", "weight": "3 kg"}, start=0.0, **FRAME)

    assert [row.text.split()[0] for row in first] == ["HEIGHT", "WEIGHT"]
    assert [row.text.split()[0] for row in second] == ["HEIGHT", "WEIGHT"]


def test_rows_do_not_overlap_each_other():
    stats = {"height": "a", "weight": "b", "species": "c", "status": "d"}
    ys = [row.y for row in stat_card(PRESET, stats, start=0.0, **FRAME)]

    assert ys == sorted(ys)
    assert all(b - a >= 0.04 for a, b in zip(ys, ys[1:]))


def test_an_entity_with_no_stats_draws_no_card():
    """A page whose infobox had nothing must not put an empty label on screen."""
    assert stat_card(PRESET, {}, start=0.0, **FRAME) == []
    assert stat_card(PRESET, {"height": ""}, start=0.0, **FRAME) == []


# ── reachability ────────────────────────────────────────────────────────────────
#
# All three shipped with no production caller — the defect this repository names in its
# own docs, committed three times in one session by the changes that documented it.
# `motion_layer.apply` dispatches on `MotionPlan.kind`, so these are kinds.

def _elements_for(monkeypatch, tmp_path, kind, lines):
    from forgecast.motion import Scene as MotionScene
    from forgecast.render import motion_layer

    captured: list = []
    monkeypatch.setattr(MotionScene, "render",
                        lambda self, path, timeout=600.0: (captured.extend(self.elements),
                                                           path)[1])
    clip = tmp_path / "in.mp4"
    clip.write_bytes(b"")
    motion_layer.apply(clip, tmp_path / "out.mp4",
                       motion_layer.MotionPlan(0, kind, lines, ""),
                       preset=PRESET, seconds=6.0, width=1920, height=1080)
    return captured


def test_the_name_card_is_reachable_from_the_render_path(monkeypatch, tmp_path):
    elements = _elements_for(monkeypatch, tmp_path, "name_card", ["House Walker"])

    assert elements
    assert any(getattr(item, "text", "") == "House Walker" for item in elements)


def test_the_stat_card_accepts_both_shapes_a_caller_produces(monkeypatch, tmp_path):
    """"height: 23 m" is what a person types; "height  23 m" is what the wiki reader's
    rows look like flattened. Understanding one of them would be a card that renders
    empty for half its callers."""
    colon = _elements_for(monkeypatch, tmp_path, "stat_card", ["height: 23 m"])
    spaced = _elements_for(monkeypatch, tmp_path, "stat_card", ["height  23 m"])

    assert [item.text for item in colon] == [item.text for item in spaced]
    assert "23 m" in colon[0].text


def test_a_bubble_becomes_a_card_with_a_real_file(monkeypatch, tmp_path):
    from forgecast.motion.compose import ImageCard

    elements = _elements_for(monkeypatch, tmp_path, "bubble",
                             ["There's a good snack in this house"])

    assert len(elements) == 1
    assert isinstance(elements[0], ImageCard)
    assert Path(elements[0].path).exists()


def test_an_empty_gag_renders_nothing_rather_than_a_blank_card(monkeypatch, tmp_path):
    assert _elements_for(monkeypatch, tmp_path, "bubble", ["   "]) == []


def test_a_stat_card_with_no_usable_rows_draws_nothing(monkeypatch, tmp_path):
    assert _elements_for(monkeypatch, tmp_path, "stat_card", ["height", ""]) == []
