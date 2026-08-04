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
from forgecast.render.cutting import (
    SECONDS_PER_PLATE,
    default_spec,
    estimate_plates,
    hero_budget,
    plates_for,
    video_budget,
)
from forgecast.style import editing
from forgecast.style.sourcing import SourcingProfile, budgets, measure, plate_carry

# One shot of each kind, in the shape `vision.profile` emits.
#
# `duration`, not `seconds`. These fixtures said `seconds` for their whole first life and
# every assertion below passed, because the key is only ever read through `.get` — while
# `vision.shots.Shot.as_dict` writes `duration` and always has. The measurement was
# therefore zero on every real reference and correct only here, which is the exact defect
# this suite exists to catch, committed inside the suite meant to catch it.
STILL = {"duration": 5.0,
         "motion": {"magnitude": 0.02, "classification": "subtle", "camera_move": "zoom"}}
FOOTAGE = {"duration": 3.0,
           "motion": {"magnitude": 0.11, "classification": "moderate",
                      "camera_move": "pan_or_handheld"}}
FROZEN = {"duration": 4.0,
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


# ------------------------------------------------------------------------- shot variety


def _shot(palette: list[tuple[str, float]], motion: dict | None = None) -> dict:
    """A per-shot row in the shape `vision.engine` builds one."""
    return {
        "duration": 3.0,
        "motion": dict(motion or STILL["motion"]),
        "colour": {"palette": [{"hex": hexed, "share": share} for hexed, share in palette]},
    }


# One plate, reframed. The shares move a long way as the crop tightens on the subject and
# the colours do not move at all, because a crop can only ever show what the wider frame
# already contained. This is the sequence `SHOTS_PER_PLATE = 4` was chosen against.
REFRAMED = [
    _shot([("#3070b0", 0.50), ("#90b0d0", 0.30), ("#103050", 0.20)]),
    _shot([("#3070b0", 0.22), ("#90b0d0", 0.58), ("#103050", 0.20)]),
    _shot([("#3070b0", 0.36), ("#90b0d0", 0.24), ("#103050", 0.40)]),
    _shot([("#3070b0", 0.61), ("#90b0d0", 0.19), ("#103050", 0.20)]),
] * 8

# Six different pictures in four seconds. Every cut brings colour that was not on screen
# a moment earlier, which is the only thing that separates this from the sequence above.
PICTURES = [
    _shot([("#3070b0", 0.45), ("#90b0d0", 0.33), ("#103050", 0.22)]),
    _shot([("#d05010", 0.45), ("#f09050", 0.33), ("#703010", 0.22)]),
    _shot([("#10b070", 0.45), ("#70d0b0", 0.33), ("#105030", 0.22)]),
] * 11

# The white-background explainer: one background across the whole video, and the only
# thing that ever changes is the cut-out standing on it.
CUTOUTS = [
    _shot([("#f0f0f0", 0.72), ("#d0d0d0", 0.16), ("#3070b0", 0.12)]),
    _shot([("#f0f0f0", 0.72), ("#d0d0d0", 0.16), ("#d05010", 0.12)]),
    _shot([("#f0f0f0", 0.72), ("#d0d0d0", 0.16), ("#10b070", 0.12)]),
] * 11


def test_reframing_one_plate_is_not_a_new_picture():
    """The whole distinction. A punch-in doubles the subject's share and halves the
    background's — the numbers move further than they do across some real cuts — so a
    palette diff would call this six pictures and buy six of them."""
    profile = measure(REFRAMED, colour=PHOTOGRAPHIC)
    assert profile.variety == 0.0
    assert profile.shots_per_plate == 4.0


def test_a_reference_that_changes_picture_every_cut_is_measured_as_doing_so():
    """The case the constant got wrong: a reference showing six different pictures in
    four seconds needs six pictures, and no amount of reframing one will look like it."""
    profile = measure(PICTURES, colour=PHOTOGRAPHIC)
    assert profile.variety == 1.0
    assert profile.shots_per_plate == 1.0


def test_a_shared_background_does_not_hide_the_subject_changing():
    """The white-card explainer, and the reason the threshold is a tenth of the frame
    rather than a share of it. Seven tenths of every shot is the same white; weigh the
    change against the whole frame and this channel reads as never cutting away."""
    profile = measure(CUTOUTS, colour=WHITE_CARD)
    assert profile.variety == 1.0
    assert profile.shots_per_plate == 1.0


def test_the_variety_measurement_changes_what_a_scene_buys():
    """The assertion that matters, in this file's own words: measured, stored, shown, and
    read by nothing is how three features have already been lost here."""
    spec = default_spec()
    varied = measure(PICTURES, colour=PHOTOGRAPHIC).as_dict()
    reframed = measure(REFRAMED, colour=PHOTOGRAPHIC).as_dict()

    scene = SECONDS_PER_PLATE  # exactly one plate's worth under the old constant
    assert plates_for(scene, spec, sourcing=varied) == 4
    assert plates_for(scene, spec, sourcing=reframed) == 1
    assert plates_for(scene, spec, sourcing=None) == 1


def test_the_reserve_moves_with_the_measurement_the_node_spends_against():
    """Held and spent by one rule. A reserve priced at the default while the shots node
    buys a plate a shot is short by exactly the factor the measurement found."""
    varied = measure(PICTURES, colour=PHOTOGRAPHIC).as_dict()
    assert estimate_plates(480, sourcing=varied) > estimate_plates(480)


def test_a_thin_reference_does_not_get_to_buy_a_plate_a_shot():
    """Same gate `budgets` uses, and the same reason. A variety read off four shots is an
    anecdote, and this anecdote costs a plate on every shot of a whole video."""
    thin = measure(PICTURES[:4], colour=PHOTOGRAPHIC)
    assert not thin.usable
    assert plate_carry(thin) is None
    assert plates_for(SECONDS_PER_PLATE, default_spec(), sourcing=thin.as_dict()) == 1


def test_a_channel_with_no_reference_is_left_where_it_was():
    """Most channels have no learned style, and none of them should see a run's picture
    count move because this was added."""
    assert plate_carry(None) is None
    assert plate_carry({}) is None
    for seconds in (3.5, 14.0, 60.0, 240.0):
        assert plates_for(seconds, default_spec()) == plates_for(seconds)
    assert estimate_plates(480) == estimate_plates(480, sourcing=None)


def test_an_unmeasured_channel_still_does_not_pay_for_cutting_fast():
    """The rule `SECONDS_PER_PLATE` was written for, unchanged where nothing was
    measured: a fast cutting rate on its own is no evidence the pictures change."""
    from forgecast.vision.apply import spec_from_dict

    fast = spec_from_dict({"render_spec": {"target_shot_seconds": 1.2}})
    slow = spec_from_dict({"render_spec": {"target_shot_seconds": 6.0}})
    assert plates_for(60.0, fast) == plates_for(60.0, slow)


def test_the_measured_clip_length_reads_the_key_the_analysis_writes():
    """`vision.shots.Shot.as_dict` writes `duration`. This read `seconds` for its whole
    first life, so the number was right in a fixture and zero on every real reference."""
    from forgecast.vision.shots import Shot

    assert "duration" in Shot(index=0, start=0.0, end=3.0).as_dict()
    assert measure([FOOTAGE] * 10, colour=PHOTOGRAPHIC).clip_seconds == 3.0
    # The planner's own shots say `seconds`, and this is the obvious function to hand one.
    seconds_shaped = [{"seconds": 3.0, "motion": FOOTAGE["motion"]}] * 10
    assert measure(seconds_shaped, colour=PHOTOGRAPHIC).clip_seconds == 3.0
