"""Visual analysis tests against fixtures with known ground truth.

Every fixture is synthesised by ffmpeg with cut times, palettes, caption position
and beat phase chosen in advance, so each assertion compares a measurement against
a constructed fact rather than against a previous run's output. Two of these are
regression tests for real bugs found during development, marked below.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from forgecast.vision import analyse_file, probe
from forgecast.vision import audio as audio_mod
from forgecast.vision import shots as shots_mod
from forgecast.vision import visual as visual_mod

FFMPEG = "ffmpeg"


def _run(args: list[str]) -> None:
    proc = subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode(errors="replace")[-500:])


@pytest.fixture(scope="module")
def fixtures(tmp_path_factory) -> dict[str, Path]:
    """Build the test videos once for the module."""
    directory = tmp_path_factory.mktemp("vision")
    made: dict[str, Path] = {}

    # --- five shots, boundaries at 4/7/10/15s, caption burned bottom-centre -----
    # Shot 1 is navy and shot 2 is dark red: similar luma, very different hue. That
    # pairing is what broke a fixed scene-score threshold, so it stays in.
    colours = ["0x1b2a4a", "0x8a2b2b", "0x2b6a4a", "0xd0c060"]
    durations = [4, 3, 5, 3]
    inputs: list[str] = []
    for colour, seconds in zip(colours, durations, strict=True):
        inputs += ["-f", "lavfi", "-i", f"color=c={colour}:s=320x180:d={seconds}:r=30"]
    inputs += ["-f", "lavfi", "-i", "testsrc2=s=320x180:d=3:r=30"]
    # Order: navy(4) red(3) testsrc(3) green(5) yellow(3) -> cuts at 4,7,10,15
    graph = "[0:v][1:v][4:v][2:v][3:v]concat=n=5:v=1:a=0," \
            "drawtext=text='SAMPLE CAPTION':fontcolor=white:fontsize=22" \
            ":x=(w-text_w)/2:y=h-40[v]"
    path = directory / "shots.mp4"
    _run([*inputs, "-filter_complex", graph, "-map", "[v]",
          "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(path)])
    made["shots"] = path

    # --- constant tone, no attacks: must yield zero onsets ---------------------
    path = directory / "tone.mp4"
    _run(["-f", "lavfi", "-i", "color=c=0x202020:s=160x90:d=8:r=30",
          "-f", "lavfi", "-i", "sine=frequency=440:duration=8:sample_rate=48000",
          "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-shortest", str(path)])
    made["tone"] = path

    # --- clicks every 0.5s; cuts every 1.0s land on them ----------------------
    # mod() written as x-0.5*floor(x/0.5): a literal comma inside an aevalsrc
    # expression is eaten by the filtergraph option parser.
    # Shot colours alternate dark/light on purpose. scdet measures *luma* change, so
    # a palette that varies hue while holding brightness constant produces cuts the
    # detector cannot see — an earlier version of this fixture raised red by 21
    # levels while dropping green by 8, which cancelled to a luma delta of 0.5 and
    # made all ten cuts invisible.
    beat_palette = [
        "0x101018", "0xe0e0d0", "0x203040", "0xf0d0b0", "0x181828",
        "0xd0e0f0", "0x282018", "0xf0f0e0", "0x101828", "0xc0d0c0",
    ]
    for name, phase in (("beat_on", "t"), ("beat_off", "t+0.25")):
        inputs = []
        graph_parts = []
        for index, colour in enumerate(beat_palette):
            inputs += ["-f", "lavfi", "-i", f"color=c={colour}:s=160x90:d=1:r=30"]
            graph_parts.append(f"[{index}:v]")
        inputs += ["-f", "lavfi", "-i",
                   f"aevalsrc=0.6*sin(2*PI*1000*t)*exp(-25*(({phase})"
                   f"-0.5*floor(({phase})/0.5))):d=10:s=48000"]
        path = directory / f"{name}.mp4"
        _run([*inputs, "-filter_complex", "".join(graph_parts) + "concat=n=10:v=1:a=0[v]",
              "-map", "[v]", "-map", "10:a",
              "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
              "-c:a", "aac", "-shortest", str(path)])
        made[name] = path

    return made


# ------------------------------------------------------------------------ probe


def test_probe_reads_geometry_and_duration(fixtures):
    meta = probe(fixtures["shots"])
    assert meta.duration == pytest.approx(18.0, abs=0.2)
    assert (meta.width, meta.height) == (320, 180)
    assert meta.aspect_ratio == "16:9"
    assert meta.orientation == "horizontal"
    assert meta.fps == pytest.approx(30.0, abs=0.5)


def test_probe_rejects_missing_file(tmp_path):
    from forgecast.vision import ProbeError

    with pytest.raises(ProbeError, match="no such file"):
        probe(tmp_path / "nope.mp4")


def test_vertical_video_is_labelled(tmp_path):
    path = tmp_path / "vertical.mp4"
    _run(["-f", "lavfi", "-i", "color=c=black:s=180x320:d=2:r=30",
          "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(path)])
    meta = probe(path)
    assert meta.orientation == "vertical"
    assert meta.aspect_ratio == "9:16"


# ------------------------------------------------------------------------ shots


def test_detects_every_constructed_boundary(fixtures):
    meta = probe(fixtures["shots"])
    analysis = shots_mod.detect(meta)
    found = [b.time for b in analysis.boundaries]

    for expected in (4.0, 7.0, 10.0, 15.0):
        assert any(abs(expected - t) < 0.2 for t in found), (
            f"missed the boundary at {expected}s; found {found}"
        )
    assert len(analysis.shots) == 5
    assert all(b.kind == "cut" for b in analysis.boundaries)


def test_low_luma_contrast_cut_is_not_missed(fixtures):
    """Regression: navy -> dark red scores only ~10 on scdet because the two
    colours have near-identical luma. A fixed threshold of 20 silently dropped it."""
    meta = probe(fixtures["shots"])
    curve = shots_mod.score_curve(meta)
    peak_at_four = max(score for time, score in curve if abs(time - 4.0) < 0.1)
    assert peak_at_four < 20, "fixture no longer exercises the low-contrast case"

    boundaries = [b.time for b in shots_mod.detect(meta, curve=curve).boundaries]
    assert any(abs(t - 4.0) < 0.2 for t in boundaries)


def test_luma_neutral_cut_is_a_documented_blind_spot(tmp_path):
    """scdet scores luma change, so a cut where brightness barely moves is faint.

    Measured: an 8-level luma step scores ~2.7 and falls under the floor; a 21-level
    step scores ~7 and is caught. Asserting the limit rather than papering over it —
    dropping the floor to catch 2.7 would make compression noise indistinguishable
    from an edit on real footage.
    """
    def build(delta: int) -> Path:
        path = tmp_path / f"grad{delta}.mp4"
        inputs: list[str] = []
        graph = ""
        for index in range(4):
            level = min(0x40 + index * delta, 0xFF)
            shade = f"0x{level:02x}{level:02x}{level:02x}"
            inputs += ["-f", "lavfi", "-i", f"color=c={shade}:s=160x90:d=1:r=30"]
            graph += f"[{index}:v]"
        _run([*inputs, "-filter_complex", graph + "concat=n=4:v=1:a=0[v]", "-map", "[v]",
              "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(path)])
        return path

    faint = shots_mod.detect(probe(build(8)))
    clear = shots_mod.detect(probe(build(40)))

    assert len(faint.boundaries) == 0, "the documented blind spot has moved"
    assert len(clear.boundaries) == 3, "an obvious cut must still be detected"


def test_threshold_adapts_to_the_noise_floor():
    quiet = [0.0] * 100 + [10.0]
    noisy = [6.0] * 100 + [10.0]
    quiet_threshold, _ = shots_mod.adaptive_threshold(quiet)
    noisy_threshold, noise = shots_mod.adaptive_threshold(noisy)

    assert quiet_threshold == shots_mod.ABSOLUTE_FLOOR  # floor governs a clean source
    assert noisy_threshold > 10.0                       # noise governs a busy one
    assert noise == pytest.approx(6.0)


def test_rhythm_statistics(fixtures):
    meta = probe(fixtures["shots"])
    payload = shots_mod.detect(meta).as_dict(meta.duration)

    assert payload["shot_count"] == 5
    assert payload["cuts_per_minute"] == pytest.approx(13.3, abs=0.5)
    assert payload["shot_length"]["median"] == pytest.approx(3.0, abs=0.2)
    assert payload["transition_mix"]["cut"] == 1.0
    assert "threshold" in payload["detection"]


def test_metronomic_edit_scores_maximum_regularity(fixtures):
    meta = probe(fixtures["beat_on"])
    analysis = shots_mod.detect(meta)
    # Ten shots of exactly 1s.
    assert analysis.regularity() == pytest.approx(1.0, abs=0.05)


# ----------------------------------------------------------------------- visual


def test_frame_sampling_covers_the_whole_video(fixtures):
    meta = probe(fixtures["shots"])
    frames = visual_mod.sample(meta, fps=4.0)
    assert len(frames) == pytest.approx(72, abs=3)
    assert frames.frames.shape[3] == 3
    assert float(frames.times.max()) == pytest.approx(meta.duration, abs=0.5)


def test_frame_budget_lowers_the_rate_rather_than_truncating(fixtures):
    """A style read of the first 10% of a video would misrepresent the edit."""
    meta = probe(fixtures["shots"])
    frames = visual_mod.sample(meta, fps=30.0, max_frames=40)
    assert len(frames) <= 41
    assert frames.fps < 30.0
    assert float(frames.times.max()) > meta.duration * 0.8


def test_palette_recovers_constructed_colours(fixtures):
    meta = probe(fixtures["shots"])
    frames = visual_mod.sample(meta)
    analysis = shots_mod.detect(meta)

    navy = visual_mod.colour_profile(frames.between(0.5, 3.5))
    assert navy.palette[0]["hex"] == "#103050"
    assert navy.warmth < 0                # blue-dominant
    assert "cool" in navy.grade_label()

    yellow_shot = analysis.shots[-1]
    yellow = visual_mod.colour_profile(frames.between(yellow_shot.start + 0.3, yellow_shot.end))
    assert yellow.warmth > 0
    assert yellow.brightness > navy.brightness


def test_static_footage_reports_no_motion(fixtures):
    meta = probe(fixtures["shots"])
    frames = visual_mod.sample(meta)
    motion = visual_mod.motion_profile(frames.between(0.5, 3.5))
    assert motion.classification == "static"
    assert motion.camera_move == "static"
    assert motion.magnitude < 0.015


def test_animated_footage_reports_motion(fixtures):
    """The testsrc2 segment (7-10s) genuinely animates."""
    meta = probe(fixtures["shots"])
    frames = visual_mod.sample(meta)
    motion = visual_mod.motion_profile(frames.between(7.2, 9.8))
    assert motion.classification != "static"
    assert motion.magnitude > 0.015


def test_caption_is_located_in_the_band_it_was_drawn_in(fixtures):
    meta = probe(fixtures["shots"])
    frames = visual_mod.sample(meta)
    overlay = visual_mod.overlay_profile(frames.frames)

    assert overlay.caption_zone == "bottom_third"
    assert overlay.caption_persistence > 0.5
    assert overlay.zone_scores["bottom_third"] > overlay.zone_scores["top_third"]
    assert "no OCR" in overlay.note      # the limitation is stated, not hidden


def test_no_caption_is_reported_when_there_is_none(fixtures):
    meta = probe(fixtures["tone"])
    frames = visual_mod.sample(meta)
    assert visual_mod.overlay_profile(frames.frames).caption_zone == "none"


# ------------------------------------------------------------------------ audio


def test_constant_tone_produces_no_onsets(fixtures):
    """Regression: an adaptive-only flux gate sits in the numerical noise when a
    track has no attacks, turning micro-fluctuations into 38 phantom beats."""
    meta = probe(fixtures["tone"])
    analysis = audio_mod.analyse(meta)

    assert analysis.present is True
    assert analysis.onset_count == 0
    assert analysis.tempo_bpm is None
    assert analysis.likely_music is False


def test_click_track_tempo_is_recovered(fixtures):
    meta = probe(fixtures["beat_on"])
    analysis = audio_mod.analyse(meta)
    # Clicks every 0.5s == 120 BPM; histogram bin width allows a few BPM of slack.
    assert analysis.tempo_bpm == pytest.approx(120, abs=6)
    assert analysis.tempo_confidence in {"medium", "high"}
    assert analysis.onset_count > 12


def test_silent_video_reports_no_audio(tmp_path):
    path = tmp_path / "silent.mp4"
    _run(["-f", "lavfi", "-i", "color=c=black:s=160x90:d=3:r=30",
          "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(path)])
    analysis = audio_mod.analyse(probe(path))
    assert analysis.present is False
    assert analysis.onset_count == 0


def test_cuts_on_the_beat_are_recognised(fixtures):
    meta = probe(fixtures["beat_on"])
    analysis = audio_mod.analyse(meta)
    cuts = [b.time for b in shots_mod.detect(meta).boundaries]
    alignment = audio_mod.beat_alignment(cuts, analysis)

    assert alignment.measured is True
    assert alignment.cuts_on_beat_ratio > 0.85
    assert alignment.verdict == "cuts_locked_to_beat"


def test_cuts_off_the_beat_are_recognised(fixtures):
    """Same cuts, click track phase-shifted 0.25s: the verdict must flip."""
    meta = probe(fixtures["beat_off"])
    analysis = audio_mod.analyse(meta)
    cuts = [b.time for b in shots_mod.detect(meta).boundaries]
    alignment = audio_mod.beat_alignment(cuts, analysis)

    assert alignment.measured is True
    assert alignment.cuts_on_beat_ratio < 0.2
    assert alignment.verdict == "cuts_independent_of_audio"
    assert alignment.median_offset == pytest.approx(0.25, abs=0.08)


def test_alignment_declines_to_guess_without_onsets(fixtures):
    meta = probe(fixtures["tone"])
    analysis = audio_mod.analyse(meta)
    alignment = audio_mod.beat_alignment([1.0, 2.0, 3.0, 4.0], analysis)
    assert alignment.measured is False
    assert alignment.verdict == "not_measured"


# --------------------------------------------------------------- style profile


def test_profile_is_complete_and_json_serialisable(fixtures):
    profile = analyse_file(fixtures["shots"])
    payload = profile.as_dict()

    for key in (
        "schema_version", "source", "shot_rhythm", "colour", "motion", "overlay",
        "audio", "beat_alignment", "render_spec", "edit_signature", "confidence",
    ):
        assert key in payload, f"profile is missing {key}"

    # Must survive the trip to a website or a database unchanged.
    assert json.loads(json.dumps(payload))["schema_version"] == "1.0"
    assert len(payload["per_shot"]) == 5
    assert profile.edit_signature, "signature should never be empty"


def test_render_spec_declines_ken_burns_on_static_source(fixtures):
    """Inventing motion the source never had is the commonest way an 'adapted'
    edit ends up feeling wrong."""
    profile = analyse_file(fixtures["beat_on"])
    spec = profile.render_spec
    assert spec.ken_burns is False
    assert spec.zoom_rate == 0.0
    assert spec.target_shot_seconds == pytest.approx(1.0, abs=0.15)
    assert spec.jitter < 0.15               # metronomic source
    assert spec.snap_cuts_to_beat is True   # click track is beat-locked
    assert spec.transition == "cut"


def test_render_spec_grade_filter_is_valid_ffmpeg(fixtures, tmp_path):
    """The grade string is only useful if ffmpeg actually accepts it."""
    profile = analyse_file(fixtures["shots"])
    out = tmp_path / "graded.mp4"
    _run(["-i", str(fixtures["shots"]), "-t", "1",
          "-vf", profile.render_spec.grade_filter,
          "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(out)])
    assert out.exists() and out.stat().st_size > 1000


def test_confidence_declares_missing_semantic_layer(fixtures):
    profile = analyse_file(fixtures["shots"])
    assert profile.confidence["semantic"] == "absent"
    assert profile.semantic is None
    assert any("semantic" in note for note in profile.confidence["notes"])


def test_low_shot_count_lowers_confidence(tmp_path):
    path = tmp_path / "single.mp4"
    _run(["-f", "lavfi", "-i", "color=c=0x304050:s=160x90:d=3:r=30",
          "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(path)])
    profile = analyse_file(path)
    assert profile.confidence["shot_detection"] == "low"
    assert any("shots detected" in note for note in profile.confidence["notes"])
