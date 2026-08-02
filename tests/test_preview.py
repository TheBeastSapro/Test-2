"""The preview timeline: what the studio plays before anything renders.

The point of a preview is that it agrees with the render. So most of these tests are
agreement tests — the preview's frame size, its scene lengths, and its motion decisions
must come from the same places the render node reads them from, and each test names the
specific way a preview goes wrong when it does not.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forgecast.motion.presets import LIBRARY
from forgecast.render import preview
from forgecast.render.motion_layer import MotionPlan


def script(count: int = 3, seconds: float = 5.0) -> dict:
    return {
        "title": "Why deep-sea cables keep breaking",
        "scenes": [
            {"index": i, "seconds": seconds, "narration": f"Sentence {i}. And more."}
            for i in range(count)
        ],
    }


def url_for(path: Path) -> str:
    return f"/media/{path.name}?signed=1"


@pytest.fixture
def assets(tmp_path: Path):
    """Real files on disk, because the builder skips paths that do not exist."""
    made = {}
    for name in ("shot0.png", "shot1.mp4", "voice0.m4a", "voice1.m4a", "narration.m4a"):
        path = tmp_path / name
        path.write_bytes(b"\x00")
        made[name] = path
    return made


# ------------------------------------------------------------------- the basics


def test_a_script_alone_is_enough_to_preview():
    """A run that has only reached the script stage is still worth watching.

    This is the case the preview exists for — seeing the shape of the video before
    spending anything on visuals or voice.
    """
    timeline = preview.build(
        script=script(), shots=None, voice=None, width=1280, height=720,
        preset=None, motion_plans=[], url_for=url_for,
    )
    assert len(timeline.scenes) == 3
    assert timeline.duration == 15.0
    assert timeline.ready is False
    assert set(timeline.missing) == {"visuals", "voice"}


def test_an_empty_script_reports_what_is_missing_rather_than_crashing():
    timeline = preview.build(
        script={}, shots=None, voice=None, width=1280, height=720,
        preset=None, motion_plans=[], url_for=url_for,
    )
    assert timeline.scenes == []
    assert timeline.missing == ["script"]


def test_scenes_are_laid_end_to_end_with_no_gaps():
    timeline = preview.build(
        script=script(4, seconds=3.0), shots=None, voice=None, width=1280, height=720,
        preset=None, motion_plans=[], url_for=url_for,
    )
    cursor = 0.0
    for scene in timeline.scenes:
        assert scene.start == pytest.approx(cursor)
        cursor += scene.seconds
    assert timeline.duration == pytest.approx(cursor)


# -------------------------------------------------------------------- agreement


def test_the_narration_decides_the_cut_exactly_as_it_does_at_render_time(assets):
    """Regression: using the script's estimate once voice exists mistimes everything.

    The render node takes the length from the synthesised audio. A preview that used
    the script's guess would drift further from the truth with every scene, and would
    be most wrong at the end — where a Short's timing matters most.
    """
    voice = {
        "narration_path": str(assets["narration.m4a"]),
        "segments": [
            {"scene_index": 0, "path": str(assets["voice0.m4a"]), "seconds": 7.4},
            {"scene_index": 1, "path": str(assets["voice1.m4a"]), "seconds": 2.1},
        ],
    }
    timeline = preview.build(
        script=script(2, seconds=5.0), shots=None, voice=voice,
        width=1280, height=720, preset=None, motion_plans=[], url_for=url_for,
    )
    assert [s.seconds for s in timeline.scenes] == [7.4, 2.1]
    assert timeline.scenes[1].start == pytest.approx(7.4)


def test_a_deleted_asset_falls_back_to_the_colour_bed(tmp_path):
    """Node output records a path; the file can be gone. Three ways of "absent" all
    have to mean the same thing to a player."""
    shots = {"shots": [
        {"scene_index": 0, "path": str(tmp_path / "never-written.png")},
        {"scene_index": 1, "path": ""},
        {"scene_index": 2},
    ]}
    timeline = preview.build(
        script=script(3), shots=shots, voice=None, width=1280, height=720,
        preset=None, motion_plans=[], url_for=url_for,
    )
    for scene in timeline.scenes:
        assert scene.background_url is None
        assert scene.background_kind == "colour"
        assert scene.plan["background"]["colour"]


def test_a_still_and_a_clip_are_distinguished(assets):
    shots = {"shots": [
        {"scene_index": 0, "path": str(assets["shot0.png"])},
        {"scene_index": 1, "path": str(assets["shot1.mp4"])},
    ]}
    timeline = preview.build(
        script=script(2), shots=shots, voice=None, width=1280, height=720,
        preset=None, motion_plans=[], url_for=url_for,
    )
    assert timeline.scenes[0].background_kind == "image"
    assert timeline.scenes[1].background_kind == "video"


def test_the_plan_carries_a_fetchable_url_not_a_bare_filename(assets):
    """`plan_from` records a filename because Remotion resolves against a public
    directory. A browser needs something it can actually request."""
    shots = {"shots": [{"scene_index": 0, "path": str(assets["shot0.png"])}]}
    timeline = preview.build(
        script=script(1), shots=shots, voice=None, width=1280, height=720,
        preset=LIBRARY["card_reveal"],
        motion_plans=[MotionPlan(0, "title", ["Headline"])],
        url_for=url_for,
    )
    src = timeline.scenes[0].plan["background"]["src"]
    assert src.startswith("/media/") and "signed=1" in src


# ----------------------------------------------------------------------- motion


def test_motion_elements_come_from_the_same_preset_the_renderer_uses():
    timeline = preview.build(
        script=script(1, seconds=8.0), shots=None, voice=None,
        width=1280, height=720, preset=LIBRARY["card_reveal"],
        motion_plans=[MotionPlan(0, "title", ["Deep-sea cables"])],
        url_for=url_for,
    )
    elements = timeline.scenes[0].plan["elements"]
    kinds = [element["kind"] for element in elements]
    assert "text" in kinds
    text = next(element for element in elements if element["kind"] == "text")
    assert text["text"] == "Deep-sea cables"
    # Times in seconds and positions as fractions — the plan contract, unchanged.
    assert 0 <= text["x"] <= 1 and 0 <= text["y"] <= 1
    assert text["duration"] <= 8.0


def test_a_scene_with_no_motion_plan_still_plays():
    timeline = preview.build(
        script=script(2), shots=None, voice=None, width=1280, height=720,
        preset=LIBRARY["card_reveal"],
        motion_plans=[MotionPlan(0, "title", ["Headline"]),
                      MotionPlan(1, "none", [], "captions carry it")],
        url_for=url_for,
    )
    assert timeline.scenes[1].plan["elements"] == []
    assert timeline.scenes[1].motion_kind == "none"


def test_motion_off_produces_bare_scenes():
    timeline = preview.build(
        script=script(2), shots=None, voice=None, width=1280, height=720,
        preset=None, motion_plans=None, url_for=url_for,
    )
    assert all(scene.plan["elements"] == [] for scene in timeline.scenes)
    assert timeline.preset_name == ""


def test_the_plan_is_sized_for_a_vertical_frame_when_asked():
    timeline = preview.build(
        script=script(1), shots=None, voice=None, width=1080, height=1920,
        preset=LIBRARY["card_reveal"],
        motion_plans=[MotionPlan(0, "title", ["Headline"])],
        url_for=url_for,
    )
    assert (timeline.width, timeline.height) == (1080, 1920)
    assert timeline.scenes[0].plan["width"] == 1080


# ------------------------------------------------------------------- honesty


def test_the_preview_states_where_it_differs_from_the_render():
    """A preview that quietly differs from the output moves the surprise later rather
    than removing it, so the differences ship with the data."""
    timeline = preview.build(
        script=script(1), shots=None, voice=None, width=1280, height=720,
        preset=None, motion_plans=[], url_for=url_for,
    )
    assert timeline.divergences
    joined = " ".join(timeline.divergences).lower()
    for subject in ("caption", "loudness", "ken burns"):
        assert subject in joined


def test_the_payload_is_json_serialisable():
    import json

    timeline = preview.build(
        script=script(2), shots=None, voice=None, width=1280, height=720,
        preset=LIBRARY["card_reveal"],
        motion_plans=[MotionPlan(0, "title", ["Headline"]), MotionPlan(1, "none", [])],
        url_for=url_for,
    )
    payload = json.loads(json.dumps(timeline.as_dict()))
    assert payload["schema_version"] == preview.SCHEMA_VERSION
    assert len(payload["scenes"]) == 2
