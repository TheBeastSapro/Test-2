"""Scene subdivision: the narration contract, the visible cut, and the bill.

The defect these cover: `broll_plan` emitted one visual per narration beat and `render`
held it for the whole voiceover line, so a 480-second video was about eight pictures at
a minute each. `render/cutting.py` subdivides. Three things can go wrong when it does,
and each has a test here rather than a comment:

* the shots stop summing to the narration and the audio drifts out of sync,
* the punch-ins creep instead of alternating and none of the planned cuts are visible,
* the plate count follows the shot count and a $14 video becomes a $100 one.

`test_render_actually_cuts` is the only one that proves the wiring: it renders with
ffmpeg and counts the cuts back out of the file with the project's own shot detector.
"""

from __future__ import annotations

import itertools
import math
import subprocess
from pathlib import Path

import pytest

from forgecast.credits import estimate_node
from forgecast.graph.pipelines import get_pipeline
from forgecast.render import Scene, assemble_video
from forgecast.render.cutting import (
    MIN_TARGET_SHOT_SECONDS,
    SECONDS_PER_PLATE,
    SHOTS_PER_PLATE,
    CutPlanError,
    SceneBeat,
    ShotCut,
    default_spec,
    estimate_plates,
    plan_cuts,
    plates_for,
    shot_estimate,
    shots_per_minute,
    spec_for,
    verify,
)
from forgecast.vision import probe
from forgecast.vision.shots import detect


def ms(cuts, scene_index: int) -> int:
    """Total shot length for a scene, in whole milliseconds — the unit that matters."""
    return sum(
        round(cut.seconds * 1000) for cut in cuts if cut.scene_index == scene_index
    )


# ------------------------------------------------------------- the narration contract


@pytest.mark.parametrize(
    "seconds",
    # 7.998 is the number in the bug report; the rest are lengths whose thirds and
    # sevenths are not representable in binary, which is where naive division drifts.
    [7.998, 8.0, 0.7, 1.0, 3.333, 12.1, 19.999, 60.0, 61.667],
)
def test_shots_sum_to_the_narration_exactly(seconds):
    beat = SceneBeat(index=0, seconds=seconds, plates=2)
    cuts = plan_cuts([beat], default_spec())
    assert ms(cuts, 0) == round(seconds * 1000)
    assert math.fsum(cut.seconds for cut in cuts) == pytest.approx(seconds, abs=1e-9)


def test_no_drift_accumulates_across_many_scenes():
    """The failure this prevents is silent: 2ms per scene looks like a lip-sync bug."""
    beats = [SceneBeat(index=i, seconds=7.998 + i * 0.137, plates=2) for i in range(40)]
    cuts = plan_cuts(beats, default_spec())

    for beat in beats:
        assert ms(cuts, beat.index) == round(beat.seconds * 1000)

    total = sum(round(cut.seconds * 1000) for cut in cuts)
    assert total == sum(round(beat.seconds * 1000) for beat in beats)


def test_a_plan_that_does_not_add_up_is_refused():
    beats = [SceneBeat(index=0, seconds=8.0)]
    short = [ShotCut(scene_index=0, shot_index=0, plate_index=0, seconds=7.998)]
    with pytest.raises(CutPlanError) as excinfo:
        verify(beats, short)
    # The message has to name the drift, or the next person reads it as a TTS fault.
    assert "-0.002" in str(excinfo.value)


def test_every_shot_clears_the_glitch_floor():
    from forgecast.vision.apply import MIN_SHOT

    cuts = plan_cuts([SceneBeat(index=0, seconds=17.31)], default_spec())
    assert len(cuts) > 3
    assert min(cut.seconds for cut in cuts) >= MIN_SHOT * 0.999


def test_shots_tile_the_scene_without_gaps():
    cuts = plan_cuts([SceneBeat(index=0, seconds=20.0, plates=3)], default_spec())
    offsets = [cut.source_offset for cut in cuts]
    assert offsets == sorted(offsets)
    for previous, current in itertools.pairwise(cuts):
        assert current.source_offset == pytest.approx(
            previous.source_offset + previous.seconds, abs=1e-6
        )


# ---------------------------------------------------------------- the cut being visible


def test_punch_in_alternates_rather_than_creeping():
    """A reframe under ~15% was detected 1 time in 5. Creeping produces invisible cuts."""
    cuts = plan_cuts([SceneBeat(index=0, seconds=30.0)], default_spec())
    punches = [cut.punch_in for cut in cuts]
    assert len(punches) > 5

    deltas = [abs(b - a) for a, b in itertools.pairwise(punches)]
    assert min(deltas) >= 0.15, f"adjacent reframes too small to register: {deltas}"
    # Creep would make the last shot enormously tighter than the first; alternation
    # keeps the whole scene inside one framing range.
    assert max(punches) - min(punches) < 0.5


def test_a_scene_too_short_to_subdivide_keeps_one_shot():
    for seconds in (0.4, 0.6, 0.7):
        cuts = plan_cuts([SceneBeat(index=0, seconds=seconds)], default_spec())
        assert len(cuts) == 1, f"{seconds}s was cut into {len(cuts)} shots"
        assert cuts[0].punch_in == 1.0
        assert cuts[0].seconds == pytest.approx(seconds)


def test_a_held_scene_is_never_cut_into():
    """A map animates along its own route; reframing mid-route reads as a mistake."""
    cuts = plan_cuts([SceneBeat(index=0, seconds=45.0, hold=True)], default_spec())
    assert len(cuts) == 1
    assert cuts[0].seconds == pytest.approx(45.0)
    assert cuts[0].punch_in == 1.0


# ------------------------------------------------------------------------ determinism


def test_the_plan_is_deterministic_for_the_same_profile_and_duration():
    beats = [SceneBeat(index=i, seconds=9.4 + i, plates=2) for i in range(5)]
    first = plan_cuts(beats, default_spec())
    second = plan_cuts(beats, default_spec())
    assert [cut.as_dict() for cut in first] == [cut.as_dict() for cut in second]


def test_a_different_profile_produces_a_different_plan():
    beats = [SceneBeat(index=0, seconds=30.0)]
    slow = plan_cuts(beats, spec_for({"render_spec": {"target_shot_seconds": 6.0}}))
    fast = plan_cuts(beats, spec_for({"render_spec": {"target_shot_seconds": 1.5}}))
    assert len(fast) > len(slow) > 1


def test_a_learned_profile_sets_the_cutting_rate():
    spec = spec_for({"render_spec": {"target_shot_seconds": 2.0, "jitter": 0.1}})
    assert spec.target_shot_seconds == 2.0
    rate = shots_per_minute(plan_cuts([SceneBeat(index=0, seconds=60.0)], spec))
    assert 22 <= rate <= 38, rate


def test_an_implausibly_fast_profile_is_floored():
    """Honouring 0.4s literally means a thousand ffmpeg encodes for one video."""
    spec = spec_for({"render_spec": {"target_shot_seconds": 0.4}})
    assert spec.target_shot_seconds == MIN_TARGET_SHOT_SECONDS


def test_no_profile_still_cuts():
    spec = spec_for(None)
    rate = shots_per_minute(plan_cuts([SceneBeat(index=0, seconds=60.0)], spec))
    assert 12 <= rate <= 20, f"default rate {rate} is outside the explainer band"


# ------------------------------------------------------------------------------- cost


def test_cost_does_not_scale_linearly_with_shot_count():
    """The whole point of the punch-in: ten times the cuts must not cost ten times."""
    spec = default_spec()
    seconds = 60.0
    shots = shot_estimate(seconds, spec)
    plates = plates_for(seconds, spec)

    assert shots >= 12, "a minute-long beat should hold a dozen shots"
    # A generated plate is what costs money, so this ratio *is* the multiplier against
    # the pre-subdivision behaviour of one plate held for the whole scene.
    assert shots / plates >= SHOTS_PER_PLATE - 1
    assert plates <= math.ceil(seconds / SECONDS_PER_PLATE)


def test_a_faster_style_buys_more_shots_not_more_plates():
    """A learned profile is a style choice. Letting it drive the bill is the trap."""
    fast = spec_for({"render_spec": {"target_shot_seconds": 1.0}})
    slow = spec_for({"render_spec": {"target_shot_seconds": 6.0}})
    assert plates_for(60.0, fast) == plates_for(60.0, slow)

    fast_cuts = plan_cuts([SceneBeat(index=0, seconds=60.0)], fast)
    slow_cuts = plan_cuts([SceneBeat(index=0, seconds=60.0)], slow)
    assert len(fast_cuts) > len(slow_cuts) * 4


def test_an_animated_plate_is_bought_once_and_sliced():
    spec = default_spec()
    assert plates_for(90.0, spec, reusable=False) == 1
    assert plates_for(90.0, spec, reusable=True) > 1


def test_the_ledger_reserve_covers_what_a_run_spends():
    """A reserve that does not cover the spend is an overdraft; one that covers it ten
    times over is the bug this replaced."""
    target = 480
    reserved = next(
        node.estimated_units
        for node in get_pipeline("faceless_longform", target_seconds=target).nodes
        if node.key == "shots"
    )
    # Every script shape the brief prompt allows, across its 4-12 beats.
    spends = [scenes * plates_for(target / scenes) for scenes in range(4, 13)]
    assert max(spends) <= reserved, f"spends up to {max(spends)} against {reserved}"
    assert reserved <= max(spends) * 1.25, "the reserve is holding money nothing will use"
    # The old reserve was 80 units, 1765 credits, against 181 actually spent.
    assert estimate_node("shots", reserved).credits < 1765


def test_a_longer_video_never_reserves_less():
    units = [estimate_plates(seconds) for seconds in (45, 120, 300, 480, 900)]
    assert units == sorted(units)


# ----------------------------------------------------------------- the measured render


def _plate(path: Path, source: str, seconds: float = 0.0) -> Path:
    """A detailed plate. Flat gradients hide punch-ins; `scdet` measures luma change."""
    args = ["-f", "lavfi", "-i", source]
    if seconds:
        args += ["-t", f"{seconds:.2f}", "-c:v", "libx264", "-preset", "veryfast",
                 "-pix_fmt", "yuv420p", "-r", "30"]
    else:
        args += ["-frames:v", "1"]
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args, str(path)],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode(errors="replace")[-400:])
    return path


def _measured_rate(path: Path) -> float:
    meta = probe(path)
    return detect(meta).cuts_per_minute(meta.duration)


def test_render_actually_cuts(tmp_path):
    """Render the same scenes with and without subdivision, then count the cuts back.

    The claim being tested is not "the plan has more entries" — it is that a viewer sees
    more cuts, which only the file can answer.
    """
    plates = [
        _plate(tmp_path / "p0.png", "mandelbrot=size=640x360"),
        _plate(tmp_path / "p1.png", "testsrc2=size=640x360:rate=1"),
    ]
    scenes = [
        Scene(index=i, seconds=12.0, visual_path=plates[i % 2],
              narration=f"Scene {i} narration for the caption track.",
              plates=[plates[i % 2]])
        for i in range(3)
    ]
    beats = [SceneBeat(index=s.index, seconds=s.seconds, plates=1) for s in scenes]

    before = assemble_video(
        scenes, tmp_path / "before.mp4", workdir=tmp_path / "wb",
        width=640, height=360, subtitles=False, loudness_target="archive",
    )
    after = assemble_video(
        scenes, tmp_path / "after.mp4", workdir=tmp_path / "wa",
        width=640, height=360, subtitles=False, loudness_target="archive",
        shot_cuts=plan_cuts(beats, default_spec()),
    )

    before_rate = _measured_rate(before)
    after_rate = _measured_rate(after)
    assert after_rate > before_rate * 3, f"{before_rate:.1f} -> {after_rate:.1f} cuts/min"
    assert after_rate >= 8, f"only {after_rate:.1f} cuts/min made it into the file"


def test_subdivision_does_not_change_the_rendered_length(tmp_path):
    """The audio is muxed against this; a short bed desynchronises everything after it."""
    from forgecast.render import ffprobe_duration

    plate = _plate(tmp_path / "p.png", "mandelbrot=size=320x180")
    scenes = [
        Scene(index=0, seconds=5.367, visual_path=plate, narration="One.", plates=[plate]),
        Scene(index=1, seconds=4.111, visual_path=plate, narration="Two.", plates=[plate]),
    ]
    beats = [SceneBeat(index=s.index, seconds=s.seconds) for s in scenes]
    out = assemble_video(
        scenes, tmp_path / "out.mp4", workdir=tmp_path / "w",
        width=320, height=180, subtitles=False, loudness_target="archive",
        shot_cuts=plan_cuts(beats, default_spec()),
    )
    assert ffprobe_duration(out) == pytest.approx(5.367 + 4.111, abs=0.2)


def test_a_video_plate_is_sliced_forward_rather_than_replayed(tmp_path):
    """Punch-in plus seek. Seek alone reassembles the clip and contains no cut at all."""
    clip = _plate(tmp_path / "clip.mp4", "testsrc2=size=320x180:rate=30", seconds=12.0)
    scene = Scene(index=0, seconds=12.0, visual_path=clip, narration="Moving.",
                  plates=[clip])
    cuts = plan_cuts([SceneBeat(index=0, seconds=12.0)], default_spec())
    out = assemble_video(
        [scene], tmp_path / "out.mp4", workdir=tmp_path / "w",
        width=320, height=180, subtitles=False, loudness_target="archive",
        shot_cuts=cuts,
    )
    assert _measured_rate(out) > 4
    assert [c.source_offset for c in cuts] == sorted(c.source_offset for c in cuts)
