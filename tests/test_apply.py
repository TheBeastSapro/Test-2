"""Style application: shot planning, grade calibration, and the closed loop.

The headline test is `test_closed_loop_*`: analyse a reference, conform a differently
paced source to it, re-analyse the output, and check the numbers converged. That is
the only test that proves the system does what it claims — everything else checks a
part in isolation.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from forgecast.vision import analyse_file, probe
from forgecast.vision.apply import (
    MIN_SHOT,
    PUNCH_LEVELS,
    build_plan,
    grade_transfer,
    plan_shot_lengths,
    refine_grade,
    spec_from_dict,
)
from forgecast.vision.profile import RenderSpec


def _run(args: list[str]) -> None:
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode(errors="replace")[-400:])


def make_spec(**overrides) -> RenderSpec:
    base = {
        "target_shot_seconds": 1.0,
        "shot_seconds_range": (1.0, 1.0),
        "cuts_per_minute": 60.0,
        "jitter": 0.0,
        "transition": "cut",
        "dissolve_share": 0.0,
        "ken_burns": False,
        "zoom_rate": 0.0,
        "captions": False,
        "caption_position": "none",
        "snap_cuts_to_beat": False,
        "pacing": "steady",
        "grade_filter": "eq=brightness=0.0:contrast=1.0:saturation=1.0",
        "target_brightness": 130.0,
        "target_contrast": 55.0,
        "target_saturation": 0.5,
        "palette": [],
    }
    base.update(overrides)
    return RenderSpec(**base)


# --------------------------------------------------------------- shot planning


def test_plan_lengths_sum_to_the_scene():
    """A plan that does not sum to the scene truncates or overruns the voiceover."""
    for total in (3.0, 7.5, 20.0, 63.0):
        lengths = plan_shot_lengths(total, make_spec(target_shot_seconds=1.5))
        assert sum(d for d, _ in lengths) == pytest.approx(total, abs=0.01)


def test_plan_hits_the_target_shot_length():
    lengths = [d for d, _ in plan_shot_lengths(30.0, make_spec(target_shot_seconds=2.0))]
    assert len(lengths) == pytest.approx(15, abs=2)
    assert sum(lengths) / len(lengths) == pytest.approx(2.0, abs=0.4)


def test_zero_jitter_gives_even_shots_and_high_jitter_does_not():
    even = [d for d, _ in plan_shot_lengths(40.0, make_spec(jitter=0.0))]
    varied = [d for d, _ in plan_shot_lengths(40.0, make_spec(jitter=0.9))]

    def spread(values: list[float]) -> float:
        mean = sum(values) / len(values)
        return (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5 / mean

    assert spread(even) < 0.05
    assert spread(varied) > spread(even) * 3


def test_planning_is_deterministic():
    """Two renders of the same brief must not drift apart for no reason."""
    spec = make_spec(jitter=0.6)
    first = plan_shot_lengths(25.0, spec, salt="scene0")
    second = plan_shot_lengths(25.0, spec, salt="scene0")
    assert first == second
    assert plan_shot_lengths(25.0, spec, salt="scene1") != first


def test_no_shot_falls_below_the_minimum():
    for target in (0.1, 0.4, 1.0):
        lengths = [d for d, _ in plan_shot_lengths(10.0, make_spec(target_shot_seconds=target))]
        assert min(lengths) >= MIN_SHOT * 0.5


def test_short_scene_is_left_as_one_shot():
    assert len(plan_shot_lengths(0.5, make_spec(target_shot_seconds=1.0))) == 1


def test_beat_snapping_moves_cuts_onto_beats():
    beats = [i * 0.5 for i in range(1, 40)]
    spec = make_spec(target_shot_seconds=1.0, jitter=0.5, snap_cuts_to_beat=True)
    lengths = plan_shot_lengths(15.0, spec, beats=beats)

    snapped = [flag for _, flag in lengths if flag]
    assert len(snapped) >= 5, "expected several cuts to snap onto the click grid"

    cursor = 0.0
    offsets = []
    for duration, flag in lengths[:-1]:
        cursor += duration
        if flag:
            offsets.append(min(abs(beat - cursor) for beat in beats))
    assert max(offsets) < 0.02, "a snapped cut should sit on the beat"


def test_snapping_is_skipped_without_beats():
    spec = make_spec(snap_cuts_to_beat=True)
    assert not any(flag for _, flag in plan_shot_lengths(10.0, spec, beats=None))


# ------------------------------------------------------------------ punch-in


def test_punch_levels_clear_the_reframe_detection_floor():
    """A reframe under ~15% is not visible as a cut; measured at 6% -> 1/5 detected."""
    assert abs(PUNCH_LEVELS[1] - PUNCH_LEVELS[0]) >= 0.15


def test_successive_shots_alternate_framing_not_creep():
    plan = build_plan([10.0], make_spec(target_shot_seconds=1.0))
    punches = [shot.punch_in for shot in plan.shots]
    assert len(punches) > 4

    deltas = [abs(punches[i + 1] - punches[i]) for i in range(len(punches) - 1)]
    assert min(deltas) >= 0.15, f"adjacent reframes too small to register: {deltas}"


def test_single_shot_scene_gets_no_punch_in():
    plan = build_plan([0.5], make_spec(target_shot_seconds=2.0))
    assert len(plan.shots) == 1
    assert plan.shots[0].punch_in == 1.0


# --------------------------------------------------------------------- plan


def test_scenes_keep_their_boundaries():
    """Applying a style must subdivide scenes, never move them — the narration is fixed."""
    scenes = [4.0, 2.5, 9.0]
    plan = build_plan(scenes, make_spec(target_shot_seconds=1.0))

    for index, expected in enumerate(scenes):
        total = sum(shot.duration for shot in plan.shots if shot.scene_index == index)
        assert total == pytest.approx(expected, abs=0.02), f"scene {index} changed length"

    assert sum(shot.duration for shot in plan.shots) == pytest.approx(sum(scenes), abs=0.05)
    starts = [shot.start for shot in plan.shots]
    assert starts == sorted(starts), "shots must stay in order"


def test_dissolve_length_scales_with_shot_length():
    fast = build_plan([20.0], make_spec(target_shot_seconds=0.8, transition="dissolve"))
    slow = build_plan([20.0], make_spec(target_shot_seconds=6.0, transition="dissolve"))
    assert 0 < fast.dissolve_seconds < slow.dissolve_seconds


def test_cut_style_has_no_dissolve():
    assert build_plan([10.0], make_spec(transition="cut")).dissolve_seconds == 0.0


# --------------------------------------------------------------------- grade


def test_grade_lifts_a_dark_source_toward_a_bright_target():
    filter_string = grade_transfer(60.0, 40.0, 0.30, make_spec(target_brightness=180.0))
    brightness = float(filter_string.split("brightness=")[1].split(":")[0])
    assert brightness > 0.2


def test_grade_darkens_a_bright_source():
    filter_string = grade_transfer(200.0, 50.0, 0.30, make_spec(target_brightness=80.0))
    brightness = float(filter_string.split("brightness=")[1].split(":")[0])
    assert brightness < -0.2


def test_grade_from_neutral_source_is_close_to_neutral():
    spec = make_spec(target_brightness=128.0, target_contrast=55.0, target_saturation=0.30)
    filter_string = grade_transfer(128.0, 55.0, 0.30, spec)
    assert "brightness=0.000" in filter_string
    assert "contrast=1.000" in filter_string
    assert "saturation=1.000" in filter_string


def test_refine_corrects_a_measured_residual():
    """The reason this exists: lifting brightness desaturates, so pass one misses."""
    spec = make_spec(target_brightness=130.0, target_saturation=0.50)
    first = "eq=brightness=0.200:contrast=1.000:saturation=1.000"
    # Pretend the result came out bright enough but flat.
    refined = refine_grade(first, 130.0, 55.0, 0.25, spec)
    saturation = float(refined.split("saturation=")[1])
    assert saturation > 1.5, "saturation should be pushed up to recover the loss"


def test_grade_values_stay_in_ffmpeg_range():
    absurd = grade_transfer(1.0, 1.0, 0.001, make_spec(
        target_brightness=255.0, target_contrast=200.0, target_saturation=1.0
    ))
    brightness = float(absurd.split("brightness=")[1].split(":")[0])
    saturation = float(absurd.split("saturation=")[1])
    assert -1.0 <= brightness <= 1.0
    assert 0.0 < saturation <= 4.0


# ------------------------------------------------------------- spec round trip


def test_spec_survives_a_json_round_trip(tmp_path):
    path = tmp_path / "clip.mp4"
    _run(["-f", "lavfi", "-i", "testsrc2=s=160x90:d=4:r=30",
          "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(path)])
    profile = analyse_file(path)
    rebuilt = spec_from_dict(profile.as_dict())

    assert rebuilt.target_shot_seconds == pytest.approx(
        profile.render_spec.target_shot_seconds, abs=0.01
    )
    assert rebuilt.grade_filter == profile.render_spec.grade_filter
    assert rebuilt.snap_cuts_to_beat == profile.render_spec.snap_cuts_to_beat
    assert rebuilt.target_contrast == pytest.approx(
        profile.render_spec.target_contrast, abs=0.01
    )


# ----------------------------------------------------------------- closed loop


@pytest.fixture(scope="module")
def loop_fixtures(tmp_path_factory) -> dict[str, Path]:
    directory = tmp_path_factory.mktemp("apply")

    # Reference: fast, 1s shots, alternating light/dark so every cut is visible.
    palette = ["0x101018", "0xe0e0d0", "0x203040", "0xf0d0b0",
               "0x181828", "0xd0e0f0", "0x282018", "0xf0f0e0"]
    inputs: list[str] = []
    graph = ""
    for index, colour in enumerate(palette):
        inputs += ["-f", "lavfi", "-i", f"color=c={colour}:s=320x180:d=1:r=30"]
        graph += f"[{index}:v]"
    reference = directory / "reference_fast.mp4"
    _run([*inputs, "-filter_complex", graph + f"concat=n={len(palette)}:v=1:a=0[v]",
          "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast",
          "-pix_fmt", "yuv420p", str(reference)])

    # Source: slow, 5s shots, with real detail so a reframe is a visible cut.
    source = directory / "source_slow.mp4"
    _run(["-f", "lavfi", "-i", "testsrc2=s=480x270:d=20:r=30",
          "-vf", "eq=brightness=-0.15:saturation=0.5",
          "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(source)])

    return {"reference": reference, "source": source, "dir": directory}


def test_closed_loop_transfers_the_cutting_rhythm(loop_fixtures):
    """Analyse a fast reference, conform a slow source, re-measure the output."""
    from forgecast.vision.restyle import restyle

    reference = analyse_file(loop_fixtures["reference"])
    assert reference.render_spec.target_shot_seconds == pytest.approx(1.0, abs=0.2), (
        "reference fixture is not the fast edit this test assumes"
    )

    source = analyse_file(loop_fixtures["source"])
    assert source.shot_rhythm["shot_count"] <= 2, "source should start as one long shot"

    out = loop_fixtures["dir"] / "restyled.mp4"
    result = restyle(loop_fixtures["source"], reference.render_spec, out, keep_audio=False)
    assert result.shot_count > 10

    produced = analyse_file(out)
    # The rhythm must move from the source's toward the reference's.
    assert produced.shot_rhythm["shot_count"] > source.shot_rhythm["shot_count"] * 3
    median = produced.shot_rhythm["shot_length"]["median"]
    assert median == pytest.approx(1.0, abs=0.6), f"median shot came out {median}s"
    assert produced.source["duration_seconds"] == pytest.approx(
        source.source["duration_seconds"], abs=0.5
    ), "restyling must not change the runtime"


def test_closed_loop_transfers_the_grade(loop_fixtures):
    """Calibration should land brightness close, not merely in the right direction."""
    from forgecast.vision.restyle import restyle

    reference = analyse_file(loop_fixtures["reference"])
    source = analyse_file(loop_fixtures["source"])
    out = loop_fixtures["dir"] / "graded.mp4"
    restyle(loop_fixtures["source"], reference.render_spec, out, keep_audio=False)
    produced = analyse_file(out)

    target = reference.colour["brightness"]
    before = abs(source.colour["brightness"] - target)
    after = abs(produced.colour["brightness"] - target)

    assert after < before / 2, (
        f"grade barely moved: {source.colour['brightness']:.1f} -> "
        f"{produced.colour['brightness']:.1f}, target {target:.1f}"
    )
    assert after < 20, f"brightness landed {after:.1f} off target"


def test_restyle_keeps_audio_when_asked(loop_fixtures, tmp_path):
    from forgecast.vision.restyle import restyle

    with_sound = tmp_path / "with_sound.mp4"
    _run(["-i", str(loop_fixtures["source"]),
          "-f", "lavfi", "-i", "sine=frequency=440:duration=20:sample_rate=48000",
          "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
          "-shortest", str(with_sound)])

    reference = analyse_file(loop_fixtures["reference"])
    out = tmp_path / "restyled_audio.mp4"
    restyle(with_sound, reference.render_spec, out, keep_audio=True)

    assert probe(out).has_audio is True
