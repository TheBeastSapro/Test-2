"""Publishing a chapter index, which the audience of this format writes by hand.

The gap list called this open for a reason worth restating: on the reference channel,
viewers write the timestamp index into the comments themselves, video after video. It is
a request — repeated, unprompted — for something that costs nothing to publish, and
until now nothing here produced one.

`vision/chapters.py` could already *read* an index off a reference and had no production
caller in either direction. These tests are about the writing half and its two rules:
marks come from joins the run actually made, and a list that breaks YouTube's own
requirements is refused out loud rather than published broken.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forgecast.graph.engine import ChannelSnapshot, NodeContext
from forgecast.nodes import finalize as finalize_node
from forgecast.providers import ProviderRegistry
from forgecast.vision import chapters

SCENES = [{"index": index, "narration": f"scene {index}", "seconds": 30.0}
          for index in range(6)]


def _context(tmp_path: Path, *, segments=None, spoken=None, description="Subscribe.",
             runtime=180.0) -> NodeContext:
    voice_segments = spoken if spoken is not None else [
        {"scene_index": scene["index"], "seconds": 30.0} for scene in SCENES]
    return NodeContext(
        run_id=1, topic="Doors entities", options={}, node_key="final_review",
        node_type="final_review", params={}, attempts=0,
        channel=ChannelSnapshot(
            id=1, name="Test", niche="horror", language="en", voice_id="",
            avatar_id="", aspect_ratio="16:9", target_duration_seconds=300,
            style_profile={}, video_model="", video_model_hero=""),
        registry=ProviderRegistry(mode="mock"), workdir=tmp_path / "work",
        upstream_outputs={
            "script": {"scenes": SCENES, "title": "T", "description": description},
            "voice": {"segments": voice_segments},
            "render": {"duration_seconds": runtime, "video_path": "/tmp/v.mp4",
                       "size_bytes": 1},
            "compliance": {"verdict": "pass", "issues": []},
            "broll_plan": {"canon_segments": segments if segments is not None else [
                {"title": "Seek", "scene_indexes": [0, 1]},
                {"title": "Figure", "scene_indexes": [2, 3]},
                {"title": "Halt", "scene_indexes": [4, 5]},
            ]},
        },
    )


# ------------------------------------------------------------------ the format itself


def test_a_written_mark_is_read_back_by_this_module_s_own_parser():
    """A writer and a parser that disagree is the defect nobody finds.

    A description whose marks do not parse does not produce a shorter chapter list — the
    video silently has no chapters at all, with no error anywhere to notice.
    """
    marks = [(0.0, "Amber"), (62.0, "Sun Man"), (130.0, "The Rake"), (3725.0, "The Iris")]

    lines, refused = chapters.write(marks, runtime_seconds=3900)

    assert not refused
    assert lines[0] == "0:00 Amber"
    assert lines[-1] == "1:02:05 The Iris"      # past an hour it grows a field
    assert chapters.parse("blurb\n\n" + "\n".join(lines) + "\n\nsubscribe") == marks


def test_a_list_that_breaks_youtube_s_rules_is_refused_with_the_reason():
    """Not trimmed to fit. Every one of these makes the whole description fail to parse
    as chapters, so a "best effort" is a video with none and an operator who cannot tell
    it was attempted."""
    short = chapters.write([(0.0, "A"), (5.0, "B"), (130.0, "C")], runtime_seconds=200)
    late = chapters.write([(3.0, "A"), (62.0, "B"), (130.0, "C")], runtime_seconds=200)
    few = chapters.write([(0.0, "A"), (62.0, "B")], runtime_seconds=200)

    assert short == ([], short[1]) and "minimum" in short[1]
    assert late == ([], late[1]) and "0:00" in late[1]
    assert few == ([], few[1]) and "3" in few[1]


def test_the_last_chapter_is_measured_against_the_runtime():
    """Without the runtime the final segment has no end, so a two-second closer would
    pass the length check by never being checked."""
    marks = [(0.0, "A"), (60.0, "B"), (178.0, "C")]

    assert chapters.write(marks, runtime_seconds=180)[0] == []
    assert chapters.write(marks, runtime_seconds=400)[0]


# --------------------------------------------------------------------- in the run


def test_the_index_is_built_from_the_join_that_decided_the_shots(tmp_path):
    """Not inferred from narration. The scene→entity mapping already exists because it
    chose which artwork each scene uses; reconstructing it from prose would be a guess
    on the one artefact this audience checks against the video."""
    description, why = finalize_node._with_chapters(_context(tmp_path), "Subscribe.")

    assert not why
    assert description.startswith("0:00 Seek\n1:00 Figure\n2:00 Halt")
    # Prepended: on this format the index is what the viewer opened the description for.
    assert description.endswith("Subscribe.")


def test_marks_are_placed_on_the_measured_voiceover_not_the_script_estimate(tmp_path):
    """`render` cuts to the measured lengths. A mark placed on an estimate points at the
    wrong second — which is exactly the failure a viewer notices, because clicking it is
    the only reason the index is there."""
    measured = [{"scene_index": 0, "seconds": 41.0}, {"scene_index": 1, "seconds": 12.0},
                {"scene_index": 2, "seconds": 38.0}, {"scene_index": 3, "seconds": 15.0},
                {"scene_index": 4, "seconds": 44.0}, {"scene_index": 5, "seconds": 30.0}]

    description, why = finalize_node._with_chapters(
        _context(tmp_path, spoken=measured, runtime=180.0), "")

    assert not why
    # 0, 41+12=53, 53+38+15=106 — none of which is the script's flat 30s a scene.
    assert description.splitlines()[:3] == ["0:00 Seek", "0:53 Figure", "1:46 Halt"]


def test_a_run_with_nothing_naming_its_segments_says_so_and_changes_nothing(tmp_path):
    """A general video has no entity list, and inventing chapter titles from narration
    is the guess this refuses to make."""
    description, why = finalize_node._with_chapters(
        _context(tmp_path, segments=[]), "Subscribe.")

    assert description == "Subscribe."
    assert "names its segments" in why


def test_a_refusal_reaches_the_operator_rather_than_the_description(tmp_path):
    """Two segments is one boundary. The description must come back untouched and the
    reason must be somewhere a human sees it."""
    two = [{"title": "Seek", "scene_indexes": [0, 1, 2]},
           {"title": "Figure", "scene_indexes": [3, 4, 5]}]

    description, why = finalize_node._with_chapters(
        _context(tmp_path, segments=two), "Subscribe.")

    assert description == "Subscribe."
    assert "no chapters written" in why


@pytest.mark.asyncio
async def test_the_node_publishes_the_index_and_logs_a_refusal(tmp_path):
    """The join all the way through: what `final_review` hands the operator to approve."""
    result = await finalize_node.final_review_node(_context(tmp_path))

    assert result.output["metadata"]["description"].startswith("0:00 Seek")
