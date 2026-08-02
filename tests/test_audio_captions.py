"""Loudness mastering and caption discipline.

Two stages that had no verification at all until now. The audio stage shipped
whatever level the voice provider returned; the caption stage put one block of text
on screen for the length of a whole scene.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from forgecast.render.audio import PLATFORM_TARGETS, measure, normalise
from forgecast.render.ffmpeg import (
    MAX_CUE_SECONDS,
    MAX_LINE_CHARS,
    MAX_LINES,
    Scene,
    cue_times,
    split_cues,
    write_srt,
)


def _tone(path: Path, *, db: float, seconds: float = 6.0) -> Path:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", f"sine=frequency=180:duration={seconds},tremolo=f=4:d=0.7,volume={db}dB",
         "-c:a", "aac", str(path)],
        check=True,
    )
    return path


# ------------------------------------------------------------------- loudness


@pytest.mark.parametrize("source_db", [-30.0, -3.0])
def test_normalisation_lands_on_target_from_any_starting_level(tmp_path, source_db):
    """The point of the stage: two takes 27 dB apart come out matched."""
    src = _tone(tmp_path / f"src{source_db}.m4a", db=source_db)
    result = normalise(src, tmp_path / f"out{source_db}.m4a", platform="youtube")

    target = PLATFORM_TARGETS["youtube"][0]
    assert abs(result.integrated_lufs - target) < 1.0, result.as_dict()


def test_normalisation_respects_the_true_peak_ceiling(tmp_path):
    src = _tone(tmp_path / "hot.m4a", db=-1.0)
    result = normalise(src, tmp_path / "hot_out.m4a", platform="youtube")
    assert result.true_peak_dbfs <= PLATFORM_TARGETS["youtube"][1] + 0.5


def test_silence_is_left_alone_rather_than_amplified(tmp_path):
    """Normalising silence pulls the noise floor up into an audible hiss."""
    silent = tmp_path / "silent.m4a"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", "anullsrc=r=48000:cl=stereo", "-t", "3", "-c:a", "aac", str(silent)],
        check=True,
    )
    result = normalise(silent, tmp_path / "silent_out.m4a")
    assert result.silent


def test_measurement_reports_a_real_number(tmp_path):
    src = _tone(tmp_path / "m.m4a", db=-20.0)
    reading = measure(src)
    assert -60.0 < reading.integrated_lufs < 0.0
    assert reading.as_dict()["integrated_lufs"] == round(reading.integrated_lufs, 2)


def test_platform_targets_are_all_sane():
    for name, (lufs, peak) in PLATFORM_TARGETS.items():
        if name == "archive":
            continue
        assert -30.0 <= lufs <= -10.0, name
        assert -3.0 <= peak <= 0.0, name


# -------------------------------------------------------------------- captions


def test_a_long_scene_is_split_into_several_cues():
    """Regression: one cue used to be held for the entire scene.

    A 20-second scene showed the same block of text for 20 seconds, which reads as a
    frozen video.
    """
    narration = ("Patricia is seventy two years old. She receives a retirement "
                 "benefit of two thousand four hundred dollars per month. Then the "
                 "letter arrived.")
    cues = cue_times(narration, 20.0)
    assert len(cues) >= 3
    for start, end, _ in cues:
        assert end - start <= MAX_CUE_SECONDS + 1e-6


def test_cues_never_exceed_two_lines_or_the_width_budget():
    narration = " ".join(["word"] * 120)
    for _, _, text in cue_times(narration, 30.0):
        lines = text.split("\n")
        assert len(lines) <= MAX_LINES
        assert max(len(line) for line in lines) <= MAX_LINE_CHARS


def test_cues_stay_inside_the_scene_and_never_overlap():
    cues = cue_times("One. Two. Three. Four. Five. Six. Seven.", 9.0)
    assert cues
    previous_end = 0.0
    for start, end, _ in cues:
        assert start >= previous_end - 1e-6
        assert end <= 9.0 + 1e-6
        previous_end = end


def test_short_sentences_share_a_card_but_long_text_breaks_at_sentence_ends():
    """Packing to the width budget is right for subtitles — two short sentences on
    one card reads fine. What must not happen is a break mid-sentence when a
    sentence boundary was available."""
    assert split_cues("Two facts. One cable.") == ["Two facts. One cable."]

    long_text = ("This first sentence is quite long and fills most of a card. "
                 "This second sentence is also long and cannot fit beside it.")
    cues = split_cues(long_text)
    assert len(cues) >= 2
    assert cues[0].endswith("."), cues


def test_a_very_short_scene_still_gets_one_cue():
    cues = cue_times("Quick note.", 0.8)
    assert len(cues) == 1
    assert cues[0][1] <= 0.8 + 1e-6


def test_empty_narration_produces_nothing():
    assert cue_times("", 5.0) == []
    assert cue_times("   ", 5.0) == []
    assert split_cues("") == []


def test_srt_timings_are_monotonic_across_scenes(tmp_path):
    scenes = [
        Scene(index=0, seconds=8.0, narration="First scene. It has two sentences."),
        Scene(index=1, seconds=8.0, narration="Second scene. Also two sentences."),
    ]
    srt = write_srt(scenes, tmp_path / "c.srt")
    body = srt.read_text(encoding="utf-8")

    stamps = [line for line in body.splitlines() if "-->" in line]
    assert len(stamps) >= 2, body

    def seconds(stamp: str) -> float:
        clock, ms = stamp.split(",")
        h, m, s = (int(part) for part in clock.split(":"))
        return h * 3600 + m * 60 + s + int(ms) / 1000

    starts = [seconds(line.split(" --> ")[0]) for line in stamps]
    assert starts == sorted(starts), starts
    # Scene two is offset by scene one's full length, not restarted at zero.
    assert starts[-1] >= 8.0, starts


def test_srt_skips_scenes_with_no_narration(tmp_path):
    scenes = [Scene(index=0, seconds=5.0, narration="")]
    assert write_srt(scenes, tmp_path / "empty.srt").read_text() == ""
