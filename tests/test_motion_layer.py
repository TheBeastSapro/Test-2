"""Motion in the render pipeline: what gets animated, and how text is shaped.

The text-shaping tests carry more weight than they look like they should. On-screen
type is read in a glance, so it has to break where the language breaks — and a naive
character or word split produces exactly the lines that make a viewer re-read:
"Why deep-sea cables keep breaking: What" and "breaking. The mechanism is".
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

from forgecast.motion.presets import LIBRARY, MotionPreset
from forgecast.render.ffmpeg import Scene as RenderScene
from forgecast.render.motion_layer import (
    MAX_LINE_CHARS,
    MotionPlan,
    _first_phrase,
    _phrases,
    _stage,
    _trim,
    apply,
    plan,
    resolve_preset,
)

FAST = LIBRARY["text_pop"]        # intensity 0.75 — stages kinetic type
CALM = LIBRARY["lower_third"]     # intensity 0.30 — titles only


def _scenes(count: int, *, seconds: float = 5.0,
            narration: str = "Two facts. One cable. Nobody noticed the break.") -> list:
    return [RenderScene(index=index, seconds=seconds, narration=narration)
            for index in range(count)]


# ------------------------------------------------------------------ preset choice


def test_named_preset_wins(tmp_path):
    assert resolve_preset("kinetic_type", directory=tmp_path).name == "kinetic_type"


def test_a_missing_name_falls_back_to_intensity_rather_than_failing(tmp_path, caplog):
    """A run that already paid for a script must not die over a renamed preset."""
    chosen = resolve_preset("was_renamed", intensity=0.9, directory=tmp_path)
    assert chosen.name == "kinetic_type"
    assert any("was_renamed" in record.message for record in caplog.records)


def test_learned_preset_is_preferred_over_the_builtin(tmp_path):
    MotionPreset(name="text_pop", intensity=0.4,
                 provenance={"origin": "reference"}).save(tmp_path)
    assert resolve_preset("text_pop", directory=tmp_path).intensity == 0.4


# -------------------------------------------------------------------- planning


def test_opening_scene_gets_the_title():
    plans = plan(_scenes(3), preset=CALM, headline="Why cables break")
    assert plans[0].kind == "title"
    assert plans[0].lines == ["Why cables break"]


def test_second_scene_names_the_subject():
    plans = plan(_scenes(3), preset=CALM, headline="Why cables break")
    assert plans[1].kind == "lower_third"
    assert len(plans[1].lines) == 2


def test_a_calm_preset_does_not_stage_kinetic_type():
    plans = plan(_scenes(5), preset=CALM, headline="Title")
    assert [item.kind for item in plans[2:]] == ["none", "none", "none"]


def test_a_fast_preset_stages_kinetic_type():
    plans = plan(_scenes(5), preset=FAST, headline="Title")
    assert all(item.kind == "kinetic" for item in plans[2:])
    assert all(len(item.lines) > 1 for item in plans[2:])


def test_short_scenes_are_left_alone():
    """A move that cannot finish inside the scene reads worse than no move."""
    plans = plan(_scenes(3, seconds=0.8), preset=FAST, headline="Title")
    assert all(item.kind == "none" for item in plans)
    assert "0.8s" in plans[0].reason


def test_the_planner_can_request_motion_explicitly():
    scenes = _scenes(2)
    scenes[1].meta = {"motion": {"kind": "lower_third", "lines": ["A", "B"]}}
    plans = plan(scenes, preset=CALM, headline="Title")
    assert plans[1].lines == ["A", "B"]
    assert plans[1].reason == "requested by the planner"


def test_every_scene_gets_a_plan_entry_with_a_reason():
    plans = plan(_scenes(4), preset=CALM, headline="Title")
    assert len(plans) == 4
    assert all(item.reason for item in plans)


# --------------------------------------------------------------- text shaping


def test_a_long_headline_breaks_at_its_clause():
    assert _trim("Why deep-sea cables keep breaking: What actually goes wrong") == (
        "Why deep-sea cables keep breaking"
    )


def test_a_headline_with_no_clause_break_ends_on_a_whole_word():
    result = _trim("An extremely long headline with no punctuation whatsoever here")
    assert result == "An extremely long headline with no"
    assert not result.endswith(("-", ",", ";"))


def test_a_short_headline_is_untouched():
    assert _trim("Short one") == "Short one"


def test_phrases_keep_their_terminal_punctuation():
    assert _phrases("Two facts. One cable.") == ["Two facts.", "One cable."]


def test_staged_lines_never_span_a_sentence_boundary():
    lines = _stage(
        "That brings us to the practical side of why cables break. "
        "The mechanism is simple.", 6.0, FAST,
    )
    assert lines
    for line in lines:
        stripped = line.rstrip(".!?")
        assert "." not in stripped, f"line spans a sentence: {line!r}"


def test_short_sentences_are_staged_one_per_line():
    assert _stage("Two facts. One cable. Nobody noticed.", 6.0, FAST) == [
        "Two facts.", "One cable.", "Nobody noticed.",
    ]


def test_staged_lines_respect_the_width_budget():
    lines = _stage("A single continuous clause with no punctuation at all "
                   "running on and on and on", 8.0, FAST)
    assert lines
    assert max(len(line) for line in lines) <= MAX_LINE_CHARS


def test_staging_declines_when_there_is_no_time():
    assert _stage("Two facts. One cable. Nobody noticed.", 0.9, FAST) == []


def test_first_phrase_prefers_a_clause_to_a_character_count():
    assert _first_phrase("Cables snap, and nobody notices for hours") == "Cables snap"


# ----------------------------------------------------------------- application


@pytest.fixture(scope="module")
def base_clip(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("motion_layer") / "base.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "color=c=0x203040:s=320x180:r=25:d=4",
         "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )
    return path


def _lit(path: Path, width: int = 320, height: int = 180) -> np.ndarray:
    """Per-frame count of pixels brighter than the flat 0x203040 background.

    The threshold is 100, not "near-white": a preset's accent colour can be dark in
    luma terms — text_pop's #ff5d5d reads as 142 — and a brightness probe tuned to
    white silently misses accented lines entirely.
    """
    raw = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, height, width)
    return (frames > 100).sum(axis=(1, 2))


def test_applying_a_plan_puts_type_on_the_clip(tmp_path, base_clip):
    item = MotionPlan(0, "title", ["Deep-sea cables"])
    out = apply(base_clip, tmp_path / "titled.mp4", item, preset=CALM,
                seconds=4.0, width=320, height=180, fps=25)
    assert out != base_clip

    before, after = _lit(base_clip), _lit(out)
    assert before.max() == 0, "the base clip should be flat"
    assert after.max() > 100, "no type was drawn"
    # And it must not be on screen for the whole clip — that is a burned-in caption,
    # not a title animation.
    assert after.min() == 0


def test_an_inactive_plan_returns_the_clip_untouched(tmp_path, base_clip):
    item = MotionPlan(0, "none", [])
    assert apply(base_clip, tmp_path / "x.mp4", item, preset=CALM,
                 seconds=4.0) == base_clip


def test_kinetic_application_stages_more_than_one_appearance(tmp_path, base_clip):
    item = MotionPlan(0, "kinetic", ["Two facts.", "One cable.", "Nobody noticed."])
    out = apply(base_clip, tmp_path / "kinetic.mp4", item, preset=FAST,
                seconds=4.0, width=320, height=180, fps=25)
    present = _lit(out) > 40
    appearances = int((present[1:] & ~present[:-1]).sum()) + int(present[0])
    assert appearances >= 3, f"only {appearances} appearance(s)"
