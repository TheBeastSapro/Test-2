"""Render backend selection and the engine-neutral scene plan.

The Remotion render itself is not exercised here: it needs a Node toolchain and a
headless Chromium, and a suite that fails because `npm install` was not run in an
optional subdirectory is a suite people learn to ignore. What is tested is everything
that decides *whether* it runs, and the plan both engines consume — because a plan
that means different things to the two backends is the failure that matters.
"""

from __future__ import annotations

import json
from itertools import pairwise

import pytest

from forgecast.motion.presets import LIBRARY, MotionPreset
from forgecast.render.backends import (
    FfmpegBackend,
    RemotionBackend,
    backend_for,
)
from forgecast.render.scene_plan import ScenePlan, plan_from

FAST = LIBRARY["text_pop"]
CALM = LIBRARY["lower_third"]


# ------------------------------------------------------------------- selection


def test_ffmpeg_is_the_default():
    assert backend_for().name == "ffmpeg"
    assert backend_for("").name == "ffmpeg"


def test_an_unknown_backend_downgrades_rather_than_raising():
    """A run that already paid for a script must not die over a renderer typo."""
    assert backend_for("blender").name == "ffmpeg"


def test_an_unavailable_backend_downgrades(monkeypatch):
    monkeypatch.setattr(RemotionBackend, "available", lambda self: False)
    assert backend_for("remotion").name == "ffmpeg"


def test_an_available_backend_is_used(monkeypatch):
    monkeypatch.setattr(RemotionBackend, "available", lambda self: True)
    assert backend_for("remotion").name == "remotion"


def test_backend_names_are_case_and_space_insensitive(monkeypatch):
    monkeypatch.setattr(RemotionBackend, "available", lambda self: True)
    assert backend_for("  Remotion ").name == "remotion"


def test_ffmpeg_backend_is_available_wherever_ffmpeg_is():
    assert FfmpegBackend().available() is True


def test_remotion_availability_requires_the_installed_project(tmp_path):
    """node alone is not enough — an uninstalled project fails mid-render."""
    assert RemotionBackend(root=tmp_path).available() is False


# ------------------------------------------------------------------ scene plan


def test_plan_carries_seconds_not_frames():
    """A preset measured at 24fps must drive a 30fps render unchanged."""
    plan = plan_from(FAST, "title", ["Hello"], seconds=4.0, width=1280, height=720)
    assert plan.duration == 4.0
    for element in plan.elements:
        assert element.start < 4.0
        assert element.duration <= 4.0


def test_positions_are_fractions_so_a_plan_survives_a_reframe():
    landscape = plan_from(FAST, "title", ["Hi"], seconds=4, width=1280, height=720)
    portrait = plan_from(FAST, "title", ["Hi"], seconds=4, width=1080, height=1920)
    left = next(e for e in landscape.elements if e.kind == "text")
    right = next(e for e in portrait.elements if e.kind == "text")
    assert left.x == right.x <= 1.0
    assert left.y == right.y <= 1.0
    assert left.sizeRatio == right.sizeRatio <= 1.0


def test_a_title_plan_has_one_caption():
    plan = plan_from(CALM, "title", ["A headline"], seconds=5, width=640, height=360)
    texts = [e for e in plan.elements if e.kind == "text"]
    assert len(texts) == 1
    assert texts[0].text == "A headline"


def test_a_lower_third_stacks_two_lines_behind_a_band():
    plan = plan_from(CALM, "lower_third", ["Name", "Subtitle"],
                     seconds=6, width=640, height=360)
    kinds = [e.kind for e in plan.elements]
    assert kinds.count("band") == 1
    assert kinds.count("text") == 2
    texts = sorted((e for e in plan.elements if e.kind == "text"),
                   key=lambda e: e.start)
    # The subhead is staggered behind the headline, and smaller.
    assert texts[1].start > texts[0].start
    assert texts[1].sizeRatio < texts[0].sizeRatio


def test_kinetic_lines_do_not_overlap():
    plan = plan_from(FAST, "kinetic", ["one", "two", "three"],
                     seconds=6, width=640, height=360)
    texts = sorted((e for e in plan.elements if e.kind == "text"),
                   key=lambda e: e.start)
    assert len(texts) == 3
    for current, following in pairwise(texts):
        assert current.start + current.duration <= following.start + 1e-6


def test_the_last_kinetic_line_uses_the_accent_colour():
    plan = plan_from(FAST, "kinetic", ["one", "two"], seconds=6,
                     width=640, height=360)
    texts = sorted((e for e in plan.elements if e.kind == "text"),
                   key=lambda e: e.start)
    assert texts[-1].colour == FAST.accent_colour
    assert texts[0].colour == FAST.text_colour


def test_a_video_background_travels_by_filename_only(tmp_path):
    """Remotion resolves assets against a public directory, not an absolute path."""
    clip = tmp_path / "deep" / "scene_000.mp4"
    clip.parent.mkdir(parents=True)
    clip.touch()
    plan = plan_from(CALM, "title", ["x"], seconds=3, width=640, height=360,
                     background=clip)
    assert plan.background.src == "scene_000.mp4"
    assert plan.background.kind == "video"


def test_an_image_background_is_labelled_as_one(tmp_path):
    still = tmp_path / "plate.png"
    still.touch()
    plan = plan_from(CALM, "title", ["x"], seconds=3, width=640, height=360,
                     background=still)
    assert plan.background.kind == "image"


def test_no_background_is_a_colour_card():
    plan = plan_from(CALM, "title", ["x"], seconds=3, width=640, height=360)
    assert plan.background.kind == "colour"
    assert plan.background.src is None


def test_the_plan_names_the_preset_it_came_from():
    """Provenance: a render should be traceable to the preset behind it."""
    learned = MotionPreset(name="ref_look", provenance={"origin": "reference"})
    plan = plan_from(learned, "title", ["x"], seconds=3, width=640, height=360)
    assert plan.presetName == "ref_look"


# --------------------------------------------------------------- the JSON bridge


def test_props_are_valid_json_with_the_plan_nested():
    plan = plan_from(FAST, "kinetic", ["a", "b"], seconds=5, width=640, height=360)
    payload = json.loads(plan.to_props())
    assert set(payload) == {"plan"}
    assert payload["plan"]["fps"] == 30
    assert len(payload["plan"]["elements"]) == len(plan.elements)


def test_props_omit_an_absent_background_source():
    """`src: null` would make staticFile() throw rather than fall through."""
    payload = json.loads(ScenePlan(duration=2.0).to_props())
    assert "src" not in payload["plan"]["background"]


def test_every_element_declares_its_kind():
    """The TypeScript side switches on `kind`; an element without one renders blank."""
    plan = plan_from(FAST, "kinetic", ["a", "b", "c"], seconds=6,
                     width=640, height=360)
    payload = json.loads(plan.to_props())
    for element in payload["plan"]["elements"]:
        # `card` is deliberately absent. It was a third element kind that no path ever
        # emitted, and it is gone from the planner, the Remotion renderer and the browser
        # preview alike — leaving it permitted here would let it come back unnoticed.
        assert element["kind"] in {"text", "band"}


@pytest.mark.parametrize("kind", ["title", "lower_third", "kinetic"])
def test_every_plan_kind_produces_something_renderable(kind):
    plan = plan_from(FAST, kind, ["one", "two"], seconds=6, width=640, height=360)
    assert plan.elements, f"{kind} produced an empty plan"


def test_an_unknown_kind_produces_an_empty_plan_rather_than_raising():
    plan = plan_from(FAST, "interpretive_dance", ["x"], seconds=4,
                     width=640, height=360)
    assert plan.elements == []
