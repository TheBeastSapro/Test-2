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


# ------------------------------------------------------- selection in a run


class _FakeChannel:
    def __init__(self, style: dict) -> None:
        self.style_profile = style


class _FakeContext:
    """Only the fields `_motion_for` reads. A real NodeContext needs a whole run."""

    def __init__(self, *, options: dict | None = None, params: dict | None = None,
                 style: dict | None = None) -> None:
        self.options = options or {}
        self.params = params or {}
        self.channel = _FakeChannel(style or {})
        self.topic = "Why cables break"


def _resolve(**kwargs):
    from forgecast.nodes.finalize import _motion_for

    return _motion_for(_FakeContext(**kwargs), _scenes(3), {"title": "A title"})


def test_a_run_option_selects_the_preset():
    preset, plans = _resolve(options={"motion_preset": "kinetic_type"})
    assert preset.name == "kinetic_type"
    assert any(item.active for item in plans)


def test_the_run_option_beats_the_channel_default():
    preset, _ = _resolve(options={"motion_preset": "kinetic_type"},
                         style={"motion_preset": "lower_third"})
    assert preset.name == "kinetic_type"


def test_the_channel_default_applies_when_the_run_says_nothing():
    preset, _ = _resolve(style={"motion_preset": "push_in"})
    assert preset.name == "push_in"


def test_measured_intensity_chooses_the_preset_when_no_name_is_given():
    preset, _ = _resolve(style={"render_spec": {"motion_intensity": 0.88}})
    assert preset.intensity >= 0.75


def test_motion_can_be_switched_off_at_any_level():
    for kwargs in ({"options": {"motion": False}},
                   {"params": {"motion": False}},
                   {"style": {"motion": False}}):
        preset, plans = _resolve(**kwargs)
        assert preset is None and plans == []


def test_a_run_with_no_settings_at_all_still_gets_motion():
    """Motion is opt-out: the default path must animate something."""
    preset, plans = _resolve()
    assert preset is not None
    assert any(item.active for item in plans)


# ----------------------------------------------------------------- the CLI


def test_learn_motion_saves_a_preset_from_an_analysed_profile(tmp_path, capsys):
    from forgecast.motion.presets import MotionPreset
    from forgecast.vision.cli import main

    profile = tmp_path / "profile.json"
    profile.write_text(
        '{"schema_version": "1.0", "source": {"path": "ref.mp4"},'
        ' "shot_rhythm": {"cuts_per_minute": 74.0, "shot_length": {"median": 0.8}},'
        ' "motion": {"mean_magnitude": 0.1},'
        ' "overlay": {"caption_zone": "bottom_third", "caption_persistence": 0.82,'
        ' "graphic_density": 0.02},'
        ' "colour": {"brightness": 120, "palette": [{"hex": "#d94f2b", "share": 0.3}]},'
        ' "audio": {}, "beat_alignment": {"measured": false}}',
        encoding="utf-8",
    )

    code = main(["learn-motion", str(profile), "--name", "Ref Look",
                 "--directory", str(tmp_path / "presets"), "--list"])
    assert code == 0

    saved = tmp_path / "presets" / "ref_look.json"
    assert saved.exists()
    preset = MotionPreset.load(saved)
    assert preset.provenance["origin"] == "reference"
    assert preset.intensity > 0.5, "a 74 cuts/min reference is not a calm look"

    # The name is the identifier, so it matches the filename and the CLI flag.
    assert preset.name == "ref_look"
    assert preset.provenance["label"] == "Ref Look"

    out = capsys.readouterr()
    # The printed hint has to be a flag that actually exists, spelled the way the
    # resolver will look it up.
    assert "--motion-preset ref_look" in out.out
    assert "(reference)" in out.out


def test_the_printed_motion_flag_exists_on_the_run_command():
    from forgecast.cli import build_parser

    args = build_parser().parse_args(
        ["run", "start", "--channel", "1", "--topic", "t",
         "--motion-preset", "ref_look"]
    )
    assert args.motion_preset == "ref_look"


def test_learn_motion_reports_an_unreadable_profile_rather_than_raising(tmp_path):
    from forgecast.vision.cli import main

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert main(["learn-motion", str(broken), "--directory", str(tmp_path)]) == 1


# ── keeping motion out of the burned narration track ────────────────────────────
#
# Captions are burned in by a separate pass after motion graphics, so nothing in the
# motion module can see them. That is how the opening scene of every long-form render
# came to draw the video's own title and its first line of narration on top of each
# other: `title` asked the preset for a caption, the preset's `caption_zone` is where
# *narration* goes, and the title landed exactly there. Measured off a real render —
# the motion band spanned 0.75–0.90 of frame height and the caption cue sat inside it.

def _vertical_span(element, height: int = 1080) -> tuple[float, float]:
    """Top and bottom of an element as fractions of frame height.

    Bands carry their own height. Text is measured from its size, which is what the
    overlap is actually made of — a band clear of the captions with its type hanging
    below it would pass a band-only check and still collide.
    """
    from forgecast.motion.compose import Band, Text

    y = float(element.y if not hasattr(element.y, "at") else 0.5)
    if isinstance(element, Band):
        return y, y + element.height_fraction
    if isinstance(element, Text):
        half = (element.size / height) * 0.75      # cap height either side of centre
        return y - half, y + half
    return y, y


@pytest.mark.parametrize("preset_name", sorted(LIBRARY))
@pytest.mark.parametrize("kind,lines", [
    ("title", ["Why deep-sea cables keep breaking"]),
    ("lower_third", ["Why deep-sea cables keep breaking", "the mechanism"]),
])
def test_motion_never_composites_into_the_burned_caption_zone(preset_name, kind, lines):
    from forgecast.motion.presets import CAPTION_SAFE_BOTTOM

    preset = LIBRARY[preset_name]
    width, height = 1920, 1080

    if kind == "title":
        elements = preset.caption(
            lines[0], start=0.4, width=width, height=height, duration=3.0,
            accent=True, zone="centre",
        )
    else:
        elements = preset.lower_third(
            lines[0], lines[1], start=0.5, width=width, height=height,
            duration=4.0, zone="above_captions",
        )

    for element in elements:
        _top, bottom = _vertical_span(element, height)
        assert bottom <= CAPTION_SAFE_BOTTOM + 0.001, (
            f"{preset_name}/{kind}: {type(element).__name__} reaches {bottom:.3f}, "
            f"into the caption track that starts at {CAPTION_SAFE_BOTTOM}"
        )


def test_the_title_card_is_not_placed_by_the_caption_zone():
    """The regression itself, stated as the rule it broke: `caption_zone` decides
    where narration sits, and a title is not narration. A preset that captions in the
    bottom third must still put its title clear of the bottom third."""
    from forgecast.motion.presets import CAPTION_SAFE_BOTTOM

    bottom_captioned = [p for p in LIBRARY.values() if p.caption_zone == "bottom_third"]
    assert bottom_captioned, "no preset captions in the bottom third — rewrite this test"

    for preset in bottom_captioned:
        elements = preset.caption(
            "Why deep-sea cables keep breaking", start=0.4, width=1920, height=1080,
            duration=3.0, accent=True, zone="centre",
        )
        for element in elements:
            _top, bottom = _vertical_span(element)
            assert bottom <= CAPTION_SAFE_BOTTOM, preset.name


def _elements_apply_composites(monkeypatch, item, preset, tmp_path):
    """What `apply` would actually draw, without encoding anything.

    The check has to run against `apply`, not against the preset. The defect was a
    call site: the preset placed exactly where it was asked to, and `apply` asked for
    the caption zone. A test that calls `preset.caption(zone="centre")` itself asserts
    the fix while re-making the mistake it is guarding — it passes with the call site
    reverted.
    """
    from forgecast.motion import Scene as MotionScene
    from forgecast.render import motion_layer

    captured: list = []
    out = tmp_path / "out.mp4"

    def fake_render(self, path, timeout=600.0):
        captured.extend(self.elements)
        return path

    monkeypatch.setattr(MotionScene, "render", fake_render)
    clip = tmp_path / "in.mp4"
    clip.write_bytes(b"")
    motion_layer.apply(clip, out, item, preset=preset, seconds=6.0,
                       width=1920, height=1080, fps=30)
    return captured


@pytest.mark.parametrize("preset_name", sorted(LIBRARY))
def test_apply_keeps_the_title_out_of_the_caption_track(monkeypatch, preset_name, tmp_path):
    from forgecast.motion.presets import CAPTION_SAFE_BOTTOM

    plan = MotionPlan(0, "title", ["Why deep-sea cables keep breaking"], "opening scene")
    for element in _elements_apply_composites(monkeypatch, plan, LIBRARY[preset_name], tmp_path):
        _top, bottom = _vertical_span(element)
        assert bottom <= CAPTION_SAFE_BOTTOM + 0.001, (
            f"{preset_name}: title {type(element).__name__} reaches {bottom:.3f}, "
            f"into the caption track starting at {CAPTION_SAFE_BOTTOM}"
        )


@pytest.mark.parametrize("preset_name", sorted(LIBRARY))
def test_apply_keeps_the_lower_third_above_the_caption_track(
    monkeypatch, preset_name, tmp_path,
):
    from forgecast.motion.presets import CAPTION_SAFE_BOTTOM

    plan = MotionPlan(1, "lower_third",
                      ["Why deep-sea cables keep breaking", "the mechanism"],
                      "names the subject early")
    for element in _elements_apply_composites(monkeypatch, plan, LIBRARY[preset_name], tmp_path):
        _top, bottom = _vertical_span(element)
        assert bottom <= CAPTION_SAFE_BOTTOM + 0.001, (
            f"{preset_name}: lower third {type(element).__name__} reaches {bottom:.3f}"
        )
