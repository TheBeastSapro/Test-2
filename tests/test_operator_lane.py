"""Footage the operator supplies, and the record that they supplied it.

`providers.footage.operator_clip` could ingest a file the operator handed over from the
day footage was added, and nothing ever called it. These hold the lane end to end — and
hold the one thing that must not drift as it becomes reachable: this app establishes no
licence here and never claims one.
"""

from __future__ import annotations

import subprocess

import pytest

from forgecast import operator_lane


def _make_clip(path, seconds=3):
    """A real file, because `strip_audio` shells out to ffmpeg and a stub would not."""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=blue:d={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:d={seconds}",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(path)],
        check=True, capture_output=True)
    return path


@pytest.fixture()
def run_storage(tmp_path, monkeypatch):
    from forgecast import config
    settings = config.get_settings()
    monkeypatch.setattr(settings, "storage_dir", tmp_path, raising=False)
    return tmp_path


def test_a_supplied_clip_lands_where_the_shots_node_looks(run_storage, tmp_path):
    source = _make_clip(tmp_path / "source.mp4")
    record = operator_lane.take(1, 3, source, title="A scene")
    assert operator_lane.clip_for(1, 3) is not None
    assert record["path"].endswith("scene_003.mp4")


def test_the_app_never_claims_a_licence_for_it(run_storage, tmp_path):
    """The one thing that must not drift as this lane becomes reachable."""
    source = _make_clip(tmp_path / "source.mp4")
    record = operator_lane.take(1, 0, source, title="Someone else's film")
    assert record["commercially_safe"] is False
    assert record["licence"] == "operator_supplied"
    assert record["operator_directed"] is True
    assert record["flag_reason"], "the run must carry the position in words"


def test_the_credit_line_never_prints_a_licence_it_was_handed(run_storage, tmp_path):
    """A credit block is exactly where a claim the app never checked would be believed."""
    source = _make_clip(tmp_path / "source.mp4")
    record = operator_lane.take(1, 0, source, title="A clip", creator="Someone")
    assert "CC0" not in record["attribution"]
    assert "licence not established" in record["attribution"].lower()


def test_audio_comes_off_at_ingest(run_storage, tmp_path):
    """Not at render: a muted clip must not be un-mutable by a later stage."""
    source = _make_clip(tmp_path / "source.mp4")
    operator_lane.take(1, 0, source)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=codec_type", "-of", "csv=p=0", str(operator_lane.clip_for(1, 0))],
        capture_output=True, text=True)
    assert probe.stdout.strip() == "", "the clip still carries an audio stream"


def test_a_window_can_be_taken_out_of_a_longer_file(run_storage, tmp_path):
    source = _make_clip(tmp_path / "source.mp4", seconds=10)
    operator_lane.take(1, 0, source, start=2.0, seconds=3.0)
    got = operator_lane.clip_for(1, 0)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
         "csv=p=0", str(got)], capture_output=True, text=True)
    assert 2.0 < float(probe.stdout.strip()) < 4.5


def test_supplying_the_same_scene_again_replaces_it(run_storage, tmp_path):
    first = _make_clip(tmp_path / "a.mp4")
    second = _make_clip(tmp_path / "b.mp4", seconds=5)
    operator_lane.take(1, 0, first)
    operator_lane.take(1, 0, second)
    assert len(list(operator_lane.folder(1).glob("scene_000.mp4"))) == 1


def test_scenes_without_a_supplied_clip_report_nothing(run_storage, tmp_path):
    assert operator_lane.clip_for(1, 7) is None
    assert operator_lane.supplied(1) == {}


def test_a_dropped_clip_is_forgotten(run_storage, tmp_path):
    source = _make_clip(tmp_path / "source.mp4")
    operator_lane.take(1, 2, source)
    assert operator_lane.drop(1, 2) is True
    assert operator_lane.clip_for(1, 2) is None
    assert operator_lane.note_for(1, 2) == {}


def test_the_folder_is_guessable_so_it_can_be_used_by_hand(run_storage):
    """A lane reachable only through a conversation stops being used."""
    path = operator_lane.folder(42)
    assert path.name == "operator"
    assert path.parent.name == "42"
    assert path.exists()


def test_the_lane_is_reachable_from_the_agent():
    from forgecast.agent import tools
    assert "use_clip" in tools.ALL_TOOLS
    assert "supplied_clips" in tools.ALL_TOOLS
