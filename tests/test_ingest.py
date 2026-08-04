"""Reading a video somebody hands you.

Forgecast generates: topic in, video out. There was no way in from the other end at
all — no probe, no shots, no silence map, no transcript — so "here is a video, edit it"
had nothing to attach to.

These tests build real files with ffmpeg and measure them, because the whole point of
this package is that it measures rather than guesses. A test using a fixture of
pre-computed numbers would pass against a module that invented them.
"""

from __future__ import annotations

import subprocess
from itertools import pairwise
from pathlib import Path

import pytest

from forgecast import ingest
from forgecast.ingest import probe, shots, silence
from forgecast.render.ffmpeg import RenderError


def _video(path: Path, *, colours=("red", "blue", "green"), seconds: float = 2.0,
           tone: bool = True) -> Path:
    """A file with real cuts in it, and optionally real sound."""
    parts = []
    for index, colour in enumerate(colours):
        piece = path.parent / f"part{index}.mp4"
        argv = ["ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", f"color=c={colour}:s=320x180:d={seconds}:r=24"]
        if tone:
            # Sound on the first piece only, so there is a real silence to find rather
            # than a file that is silent throughout.
            # `anullsrc` takes its first option after an `=`, not a `:` — the colon
            # form is a filter name with a stray argument and ffmpeg refuses it.
            source = ("sine=frequency=440:duration=" if index == 0
                      else "anullsrc=duration=")
            argv += ["-f", "lavfi", "-i", f"{source}{seconds}"]
        argv += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
        if tone:
            argv += ["-c:a", "aac", "-shortest"]
        argv += ["-y", str(piece)]
        subprocess.run(argv, check=True, capture_output=True)
        parts.append(piece)

    listing = path.parent / "list.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", str(listing), "-c", "copy", "-y", str(path)],
        check=True, capture_output=True)
    return path


# ------------------------------------------------------------------------- the probe


def test_a_file_that_is_not_a_video_is_refused_rather_than_guessed_at(tmp_path):
    """The one reading that cannot degrade. Everything else here is best-effort, but a
    file that will not probe is not a video and there is nothing to carry on with."""
    text = tmp_path / "notes.txt"
    text.write_text("this is not a video", encoding="utf-8")
    with pytest.raises(RenderError):
        probe.read(text)
    with pytest.raises(RenderError):
        probe.read(tmp_path / "does-not-exist.mp4")


def test_the_probe_measures_what_every_later_decision_needs(tmp_path):
    media = probe.read(_video(tmp_path / "clip.mp4", seconds=2.0))
    assert media.duration == pytest.approx(6.0, abs=0.2)
    assert (media.width, media.height) == (320, 180)
    assert media.fps == pytest.approx(24.0, abs=0.5)
    assert media.has_audio is True
    assert media.aspect == "16:9"


def test_an_odd_resolution_still_reports_a_format_the_app_supports():
    """A 1920x1088 upload is 16:9 in every sense that matters. Reporting `30:17` makes
    it look like a shape nothing here can render."""
    assert probe.Media(10, 1920, 1088, 30, True).aspect == "16:9"
    assert probe.Media(10, 1080, 1920, 30, True).aspect == "9:16"
    assert probe.Media(10, 1080, 1080, 30, True).aspect == "1:1"


def test_a_fractional_frame_rate_is_not_rounded_early():
    """29.97 is 30000/1001. Rounding it at the edge is how audio drifts a frame every
    thousand — so the fraction is carried until something has to display it."""
    assert probe._fraction("30000/1001") == pytest.approx(29.97, abs=0.01)
    assert probe._fraction("24") == 24.0
    assert probe._fraction("0/0") == 0.0
    assert probe._fraction("nonsense") == 0.0


# -------------------------------------------------------------------------- the shots


@pytest.mark.skipif(not shots.available()[0], reason="the edit extra is not installed")
def test_the_cuts_that_are_already_in_the_video_are_found(tmp_path):
    """Re-editing has to know which cuts were deliberate, or it cuts across one — and a
    new cut two frames after an existing one reads as a glitch rather than as pace."""
    found = shots.read(_video(tmp_path / "clip.mp4", seconds=2.0))
    assert len(found) == 3, f"expected three shots, got {[s.seconds for s in found]}"
    assert all(shot.seconds > 0 for shot in found)
    assert [shot.index for shot in found] == [0, 1, 2]
    # Contiguous: a gap between shots would mean footage nothing accounts for.
    for earlier, later in pairwise(found):
        assert later.start == pytest.approx(earlier.end, abs=0.1)


# ------------------------------------------------------------------------ the silence


def test_silence_is_measured_from_the_waveform(tmp_path):
    """Not derived from word timings. The space between two words is not the same thing
    as the absence of sound, and the absence of sound is what the viewer hears."""
    quiet = silence.read(_video(tmp_path / "clip.mp4", seconds=2.0))
    assert quiet, "four seconds of silence after the tone was not found"
    assert sum(item.seconds for item in quiet) > 2.0
    assert all(item.end > item.start for item in quiet)


def test_a_short_gap_between_sentences_is_left_alone(tmp_path):
    """Cutting the natural space between sentences produces the breathless, gapless
    rhythm that is the most recognisable sound of an automatically edited video."""
    clip = _video(tmp_path / "clip.mp4", seconds=2.0)
    generous = silence.read(clip, min_seconds=10.0)
    assert generous == [], "a 10s minimum should find nothing in a 6s clip"


# ----------------------------------------------------------------- the whole reading


def test_a_reading_that_cannot_be_taken_is_named_rather_than_dropped(tmp_path):
    """An edit built without a transcript is a different edit, and the operator has to
    be able to see that it was built that way. Silence here is how a worse edit gets
    presented as the intended one."""
    found = ingest.read(_video(tmp_path / "clip.mp4", seconds=2.0),
                        want_transcript=False, want_shots=False)
    assert found.media.duration > 0
    assert found.shots == []
    assert found.lines == []
    # Not asked for is not the same as failed, so neither appears in `missing`.
    assert not any("shots" in item for item in found.missing)


def test_what_this_machine_can_measure_is_answerable_before_a_file_arrives():
    """Dropping a video in and being told twenty seconds later that a model is missing
    is the shape of failure this app keeps removing."""
    report = ingest.available()
    assert set(report) == {"probe", "shots", "silence", "transcript"}
    for name, (ok, why) in report.items():
        assert ok or why, f"{name} is unavailable and does not say why"
        if not ok:
            # The reason has to name the fix, not the internal state.
            assert "install" in why.lower(), f"{name}: {why!r} names no fix"


@pytest.mark.skipif(not shots.available()[0], reason="the edit extra is not installed")
def test_the_summary_reads_without_opening_the_numbers(tmp_path):
    found = ingest.read(_video(tmp_path / "clip.mp4", seconds=2.0),
                        want_transcript=False)
    line = found.summary()
    assert "shots" in line
    assert "320x180" in line
    assert found.shots_per_minute > 0


# ---------------------------------------------------------------- the transcript
#
# Behind an env var, not behind `available()`. The package being installed is not the
# same as the model being on disk, and the first real transcription downloads weights —
# so a suite that ran this by default would make an offline machine hang on an unrelated
# test run. Set FORGECAST_TEST_WHISPER=1 to exercise it.


@pytest.mark.skipif(
    not __import__("os").environ.get("FORGECAST_TEST_WHISPER"),
    reason="set FORGECAST_TEST_WHISPER=1 to allow the model download")
def test_the_transcript_carries_word_timings_not_just_sentences(tmp_path):
    """The difference decides what can be built on top.

    Sentence timings let you cut between sentences. Word timings let you cut a filler
    out of the middle of one, land a caption on the beat, and put a graphic on the word
    it illustrates. Sentence timings are a transcript; word timings are an edit.
    """
    from forgecast.ingest import transcript

    clip = tmp_path / "speech.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "color=c=black:s=320x180:d=6:r=24",
         "-f", "lavfi", "-i",
         "flite=text='The ship was not the problem. It was the schedule.':voice=slt",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
         "-y", str(clip)],
        check=True, capture_output=True)

    lines = transcript.read(clip)
    assert lines, "nothing was transcribed"
    assert any("ship" in line.text.lower() for line in lines)

    words = [word for line in lines for word in line.words]
    assert words, "the segments carry no word timings"
    assert all(word.end >= word.start for word in words)
    # Monotonic across the whole file, or a caption timed from these jumps backwards.
    for earlier, later in pairwise(words):
        assert later.start >= earlier.start - 0.01
    assert any(word.probability < 1.0 for word in words), (
        "no confidence was recorded — a caption that is confidently wrong is worse "
        "than no caption")


def test_a_filler_is_recognised_without_a_model():
    """Short and English-only on purpose. A list long enough to be clever starts cutting
    words that carry meaning — "like" is a filler in one sentence and a verb in the
    next, which is why it is not in it."""
    from forgecast.ingest.transcript import Word

    assert Word("um", 0, 1).is_filler
    assert Word("Uh,", 0, 1).is_filler
    assert not Word("like", 0, 1).is_filler
    assert not Word("ship", 0, 1).is_filler
