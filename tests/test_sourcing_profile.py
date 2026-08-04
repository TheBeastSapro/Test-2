"""How a reference gets its pictures, measured — and reaching the run.

Two constants decided what every run cost and how it looked: one beat in three could
animate, one in four could take the premium endpoint. Both were guesses, and both were
wrong for most channels in opposite directions — a white-card explainer moves almost
nothing, a cinematic channel moves nearly everything, and every run paid the difference.

The reference already held the answer. `vision.visual.motion_profile` runs on every shot
of a learned reference and says whether it moved and how; `colour_profile` says what the
frame is made of. Both were measured on every learn and then used for nothing but picking
a Ken Burns rate. This reads them.

The measurement is the easy half. The half this file is really about is the one that keeps
going wrong in this project: a number that is measured, stored, shown, and read by nothing.
`test_the_measurement_changes_what_a_run_reserves` is the assertion that matters.
"""

from __future__ import annotations

from forgecast.credits import estimate_run
from forgecast.graph.pipelines import animation_reserve, get_pipeline
from forgecast.render.cutting import hero_budget, video_budget
from forgecast.style import editing
from forgecast.style.sourcing import SourcingProfile, budgets, measure

# One shot of each kind, in the shape `vision.profile` emits.
STILL = {"seconds": 5.0,
         "motion": {"magnitude": 0.02, "classification": "subtle", "camera_move": "zoom"}}
FOOTAGE = {"seconds": 3.0,
           "motion": {"magnitude": 0.11, "classification": "moderate",
                      "camera_move": "pan_or_handheld"}}
FROZEN = {"seconds": 4.0,
          "motion": {"magnitude": 0.001, "classification": "static", "camera_move": "static"}}

WHITE_CARD = {"palette": [{"hex": "#f0f0f0", "share": 0.42}, {"hex": "#d0d0d0", "share": 0.25},
                          {"hex": "#3070b0", "share": 0.14}]}
PHOTOGRAPHIC = {"palette": [{"hex": "#3070b0", "share": 0.31}, {"hex": "#90b0d0", "share": 0.22},
                            {"hex": "#503010", "share": 0.19}]}


# ------------------------------------------------------------------ what is measurable


def test_a_still_under_a_ken_burns_push_is_not_animation():
    """The distinction the whole budget rests on. This app pushes into every still it
    buys, so counting a zoom as animation would measure every channel at 100% animated
    and price every run as all-video."""
    profile = measure([STILL] * 30, colour=PHOTOGRAPHIC)
    assert profile.animation_share == 0.0


def test_real_footage_is_animation():
    profile = measure([FOOTAGE] * 30, colour=PHOTOGRAPHIC)
    assert profile.animation_share > 0.5


def test_a_frozen_frame_is_not_animation_either():
    profile = measure([FROZEN] * 30, colour=PHOTOGRAPHIC)
    assert profile.animation_share == 0.0


def test_an_explainer_and_a_cinematic_reference_measure_differently():
    """The reason a constant could not be right for both."""
    explainer = measure([STILL] * 27 + [FOOTAGE] * 3, colour=WHITE_CARD)
    cinematic = measure([FOOTAGE] * 24 + [STILL] * 6, colour=PHOTOGRAPHIC)
    assert explainer.animation_share < 0.2
    assert cinematic.animation_share > 0.6
    assert explainer.flat_background and not cinematic.flat_background


def test_the_white_card_survives_the_palette_quantisation():
    """`visual._palette` buckets to three bits a channel, so a graded white card splits
    across #f0f0f0 and #d0d0d0 and no single entry reaches half the frame. Reading the
    largest bucket alone would report the most obviously flat frame in the format as not
    flat, which is why the neutral entries are summed."""
    graded = {"palette": [{"hex": "#f0f0f0", "share": 0.30}, {"hex": "#d0d0d0", "share": 0.28},
                          {"hex": "#b0b0b0", "share": 0.12}, {"hex": "#3070b0", "share": 0.20}]}
    assert measure([STILL] * 20, colour=graded).flat_background


def test_a_flat_brand_colour_is_flat_too():
    """Same cut-out treatment, different field. Rounding it down to 'not flat' would put
    a branded explainer on photographic backgrounds."""
    brand = {"palette": [{"hex": "#3070b0", "share": 0.62}, {"hex": "#f0f0f0", "share": 0.18}]}
    profile = measure([STILL] * 20, colour=brand)
    assert profile.flat_background
    assert profile.background_colour == "#3070b0"


def test_the_clip_length_is_the_moving_shots_not_all_of_them():
    """Stills are held longer than footage, so pooling them would report a cut rhythm
    slower than the one the reference actually uses on its clips."""
    profile = measure([STILL] * 10 + [FOOTAGE] * 10, colour=PHOTOGRAPHIC)
    assert profile.clip_seconds == 3.0


# --------------------------------------------------------------- and what is not claimed


def test_a_thin_reference_is_measured_but_not_trusted():
    """Four shots is an anecdote. Applying it silently is how a channel animates
    everything because one reference happened to open on a montage."""
    profile = measure([FOOTAGE] * 4, colour=PHOTOGRAPHIC)
    assert profile.confidence == "low"
    assert not profile.usable
    assert budgets(profile, 12) == (video_budget(12), hero_budget(12))


def test_an_impossible_share_is_held_back_and_says_so():
    """A reference measured as animating every single shot is far more likely a decode
    that classified badly than a channel with no stills — and inheriting 1.0 puts a whole
    video on the video endpoint at the video endpoint's price."""
    profile = measure([FOOTAGE] * 40, colour=PHOTOGRAPHIC)
    assert profile.animation_share <= 0.85
    assert any("bad decode" in note for note in profile.notes)


def test_nothing_claims_to_know_where_a_picture_came_from():
    """Licensed, generated or lifted — nothing in a decoded frame says which, and a field
    claiming it would be believed. The profile reports motion and colour and stops."""
    fields = set(SourcingProfile().as_dict())
    for invented in ("sourced_share", "licensed", "stock_share", "generated_share"):
        assert invented not in fields


def test_no_shots_is_not_a_measurement():
    profile = measure([], colour=WHITE_CARD)
    assert not profile.usable
    assert profile.notes


# ------------------------------------------------------------------ and it reaches a run


def test_the_measurement_rides_on_the_style_not_the_channel():
    """The operator's choice: learn a creator once, apply that style to three channels,
    and all three source pictures the way that creator does. Two channels modelled on one
    reference cannot drift apart, because there is one measurement."""
    style = editing.EditingStyle(name="Ref", sourcing=measure(
        [FOOTAGE] * 20 + [STILL] * 10, colour=PHOTOGRAPHIC).as_dict())
    profile = style.to_channel_profile({"tone": "kept"})
    assert profile["sourcing"]["animation_share"] > 0.5
    assert profile["tone"] == "kept", "applying a style must not discard what it does not own"


def test_a_style_with_no_measurement_does_not_wipe_a_channels():
    """A style learned before this existed, or from a reference too thin to measure, must
    not overwrite working numbers with an empty dict."""
    style = editing.EditingStyle(name="Old")
    kept = style.to_channel_profile({"sourcing": {"animation_share": 0.8}})
    assert kept["sourcing"]["animation_share"] == 0.8


def test_learning_pools_shots_across_references_rather_than_averaging_shares():
    """A twenty-minute reference and a two-minute one do not get an equal vote on a
    proportion. The honest figure is shots that moved over shots that ran."""
    long_ref = {"per_shot": [FOOTAGE] * 40, "colour": PHOTOGRAPHIC,
                "confidence": {"colour": "high"}}
    short_ref = {"per_shot": [STILL] * 4, "colour": PHOTOGRAPHIC,
                 "confidence": {"colour": "low"}}
    pooled = editing._sourcing_of([long_ref, short_ref])
    # 40 of 44 moved. Averaging the two references' shares would give about 0.5.
    assert pooled["animation_share"] > 0.7
    assert pooled["shots_measured"] == 44


def test_the_measurement_changes_what_a_run_reserves():
    """The assertion this file exists for. Measured, stored and shown is worth nothing if
    nothing reads it — which is the defect this project keeps producing."""
    explainer = measure([STILL] * 27 + [FOOTAGE] * 3, colour=WHITE_CARD).as_dict()
    cinematic = measure([FOOTAGE] * 24 + [STILL] * 6, colour=PHOTOGRAPHIC).as_dict()

    quiet = animation_reserve(480, sourcing=explainer)
    busy = animation_reserve(480, sourcing=cinematic)
    assert busy[1] > quiet[1] * 2, (
        f"a channel that animates most of its beats reserved {busy[1]} against "
        f"{quiet[1]} for one that animates almost none — the profile is not being read")


def test_the_measurement_changes_what_a_pipeline_holds():
    """End to end through `get_pipeline`, because the wiring from a learned style to a
    node's params runs through four modules and every previous version of this had a
    break somewhere in it."""
    cinematic = measure([FOOTAGE] * 24 + [STILL] * 6, colour=PHOTOGRAPHIC).as_dict()
    plain = estimate_run(get_pipeline("faceless_longform", target_seconds=480).instantiate(1))
    busy = estimate_run(get_pipeline("faceless_longform", target_seconds=480,
                                     sourcing=cinematic).instantiate(1))
    assert busy > plain


def test_the_planner_reads_the_same_budget_the_ledger_reserved():
    """One function, two callers. Two copies of this rule would be two answers to how
    much a run may spend, and the one the money model held would be the wrong one."""
    from forgecast.graph import pipelines
    from forgecast.nodes import media as media_node
    from forgecast.style import sourcing as module

    assert media_node.sourcing.budgets is module.budgets
    assert pipelines.style_budgets is module.budgets


def test_a_channel_with_no_learned_style_runs_exactly_as_before():
    """The upgrade case. Most channels have no reference, and none of them should see
    their costs move because this was added."""
    assert budgets(None, 12) == (video_budget(12), hero_budget(12))
    assert budgets({}, 12) == (video_budget(12), hero_budget(12))
    assert animation_reserve(480) == animation_reserve(480, sourcing=None)
