"""The hold for the two nodes that buy animation, against what they actually spend.

The bug this exists to prevent, stated plainly. `PER_UNIT_COSTS` holds one credit figure
per node type. Both animation nodes are priced almost entirely by *which model the channel
picked*, and the selectable endpoints run from $0.03 a second to $0.20 — so any single
figure in that table is right for one channel and wrong by up to seven times for every
other one. It was wrong in the expensive direction:

  * `shots` held a hand-blended 22 credits a plate. A short video split into twelve beats
    with the premium model on the hero shots costs about 70 a plate.
  * `sample` held one setup on the default model — 43 credits — against a gate that will
    buy one clip per distinct setup, up to the animation budget, on whichever model that
    setup routed to. Four setups on Veo 3.1 is 392.

Neither figure was reachable from the catalogue that decides the real price, so neither
moved when the catalogue did. That is the drift these tests close: every assertion below
is computed from `VIDEO_MODELS`, the budget functions in `render.cutting` and the gate's
own ceiling, so adding a model or changing a cap moves the expectation with it.

Why over-reserving is the safe error and under-reserving is not. A reserve is released
when the node settles, so a hold that is too large costs the user nothing but the wait.
A hold that is too small is a run already under way whose later nodes spend past it —
and `settle_node` has no way to refuse a spend, so the balance simply goes negative.
"""

from __future__ import annotations

import pytest

from forgecast import credits as billing
from forgecast.graph.pipelines import (
    MAX_SETUPS,
    STILL_CREDITS,
    animation_reserve,
    get_pipeline,
)
from forgecast.providers.media import (
    HERO_TIER,
    STANDARD_TIER,
    VIDEO_MODELS,
    model_for_tier,
    video_reserve_credits,
)
from forgecast.render.cutting import (
    hero_budget,
    max_scenes,
    plates_for,
    video_budget,
)

# Every model an operator can actually choose. The superseded rows stay in the catalogue
# so old runs re-price correctly, and they are priced here too — a channel that picked one
# before it was retired still has that slug stored.
SLUGS = sorted(VIDEO_MODELS)


def spend(target_seconds: float, scenes: int, standard: str, hero: str) -> int:
    """What the two nodes bill for a script of this shape, from the nodes' own rules.

    Deliberately a second implementation rather than a call into `animation_reserve`: a
    reserve checked against itself checks nothing. This one follows `broll_plan_node` and
    `sample_node` — one plate and one clip per animated beat, several plates per still
    beat, one sample per setup up to the gate's ceiling.
    """
    seconds = max(0.0, float(target_seconds)) / scenes
    clips = min(video_budget(scenes), scenes)
    heroes = min(clips, hero_budget(scenes))

    hero_slug = model_for_tier(HERO_TIER, standard=standard, hero=hero)
    batch_slug = model_for_tier(STANDARD_TIER, standard=standard, hero=hero)

    plates = clips + (scenes - clips) * plates_for(seconds)
    shots = (plates * STILL_CREDITS
             + heroes * video_reserve_credits(hero_slug, seconds)
             + (clips - heroes) * video_reserve_credits(batch_slug, seconds))

    setups = min(MAX_SETUPS, clips)
    sample = setups * max(video_reserve_credits(hero_slug, 0, samples=1),
                          video_reserve_credits(batch_slug, 0, samples=1))
    return sample, shots


# --------------------------------------------------------------- the hold covers the bill


@pytest.mark.parametrize("slug", SLUGS)
def test_the_hold_covers_every_legal_script_shape_on_every_model(slug: str):
    """The whole point. For each model and each runtime, no legal script may cost more
    than was held for it — and a script's shape is not known when the hold is taken."""
    for target in (30, 45, 60, 80, 180, 480, 600, 720):
        held_sample, held_shots = animation_reserve(target, standard=slug, hero=slug)
        for scenes in range(1, max_scenes(target) + 1):
            bill_sample, bill_shots = spend(target, scenes, slug, slug)
            assert held_shots >= bill_shots, (
                f"{slug} at {target}s in {scenes} beats: held {held_shots}, "
                f"bill {bill_shots}")
            assert held_sample >= bill_sample


@pytest.mark.parametrize("hero", SLUGS)
def test_the_hold_covers_a_run_routed_across_two_models(hero: str):
    """The shape that actually ships: cheap model for the batch, dear one for the beats
    that earn it. The dearest routing is the one the reserve has to survive."""
    standard = "fal-ai/veo3.1/lite/image-to-video"
    for target in (45, 480):
        held_sample, held_shots = animation_reserve(target, standard=standard, hero=hero)
        for scenes in range(1, max_scenes(target) + 1):
            bill_sample, bill_shots = spend(target, scenes, standard, hero)
            assert held_shots >= bill_shots
            assert held_sample >= bill_sample


def test_the_default_channel_is_held_for_too():
    """No model chosen is the common case and it has to be priced, not skipped."""
    sample, shots = animation_reserve(480)
    assert sample > 0 and shots > 0
    for scenes in range(1, max_scenes(480) + 1):
        bill_sample, bill_shots = spend(480, scenes, "", "")
        assert shots >= bill_shots
        assert sample >= bill_sample


# ------------------------------------------------------------------ and is not absurd


def test_the_hold_is_not_so_large_it_blocks_the_plan_it_protects():
    """The other failure mode. A reserve big enough to be always safe is a reserve that
    refuses runs a user can afford, and the ledger cannot tell that apart from being
    broke. Four times the worst legal bill is the line: enough slack for a shape this
    file has not thought of, not enough to price a channel out of its own plan."""
    for slug in SLUGS:
        for target in (45, 480):
            held_sample, held_shots = animation_reserve(target, standard=slug, hero=slug)
            worst_sample = max(spend(target, n, slug, slug)[0]
                               for n in range(1, max_scenes(target) + 1))
            worst_shots = max(spend(target, n, slug, slug)[1]
                              for n in range(1, max_scenes(target) + 1))
            assert held_shots <= worst_shots * 4
            assert held_sample <= worst_sample * 4


def test_a_premium_channel_is_held_for_more_than_a_cheap_one():
    """The reserve moving with the model is the entire fix. If these matched, the figure
    would be a constant wearing a function's clothes."""
    lite = animation_reserve(480, standard="fal-ai/veo3.1/lite/image-to-video")
    dear = animation_reserve(480, standard="fal-ai/veo3.1/image-to-video")
    assert dear[0] > lite[0] * 3
    assert dear[1] > lite[1] * 2


# --------------------------------------------------------- and reaches the actual run


@pytest.mark.parametrize("pipeline,target", [("faceless_longform", 480),
                                             ("faceless_shorts", 45)])
def test_the_figure_reaches_the_node_and_the_ledger(pipeline: str, target: int):
    """Built but unreachable is this project's most common defect, so the last assertion
    is that the number arrives: on the spec, in the node's params, and in the run total."""
    spec = get_pipeline(pipeline, target_seconds=target,
                        standard_model="fal-ai/sora-2/image-to-video",
                        hero_model="fal-ai/veo3.1/image-to-video")
    by_key = {node.key: node for node in spec.instantiate(1)}
    expected_sample, expected_shots = animation_reserve(
        target, standard="fal-ai/sora-2/image-to-video",
        hero="fal-ai/veo3.1/image-to-video")

    assert by_key["sample"].params["estimated_credits"] == expected_sample
    assert by_key["shots"].params["estimated_credits"] == expected_shots

    # And the ledger reads it rather than falling back to the per-unit table.
    assert billing.node_estimate(by_key["shots"]).credits == (
        billing.BASE_COSTS["shots"] + expected_shots)
    assert billing.node_estimate(by_key["sample"]).credits == (
        billing.BASE_COSTS["sample"] + expected_sample)


def test_the_channels_model_choice_changes_what_the_run_reserves():
    """End to end through `get_pipeline`, because the wiring between a channel column and
    a node's params is four modules long and every previous version of this had a break
    somewhere in it."""
    cheap = billing.estimate_run(get_pipeline(
        "faceless_longform", target_seconds=480,
        standard_model="fal-ai/veo3.1/lite/image-to-video").instantiate(1))
    dear = billing.estimate_run(get_pipeline(
        "faceless_longform", target_seconds=480,
        standard_model="fal-ai/veo3.1/image-to-video").instantiate(1))
    assert dear > cheap


def test_an_explicit_figure_beats_the_per_unit_table():
    """`estimated_credits` has to *replace* the per-unit variable rather than add to it,
    or the two would stack and every animated node would be held for twice."""
    priced = billing.estimate_node("shots", units=44, priced=973)
    assert priced.credits == billing.BASE_COSTS["shots"] + 973
    # And with no figure supplied the table still answers, for any pipeline that has not
    # been taught to price itself.
    table = billing.estimate_node("shots", units=44)
    assert table.credits > billing.BASE_COSTS["shots"]


# ------------------------------------------------------------------- the shared caps


def test_the_planner_and_the_ledger_read_one_animation_budget():
    """Two copies of "one beat in three" would be two answers to how much a run may spend,
    and the one the money model held would be the wrong one.

    Both now go through `style.sourcing.budgets`, which reads the channel's measured
    reference where there is one and falls back to `render.cutting` where there is not.
    Asserting the identity of the function rather than the value, because the value is
    no longer a constant — that is the whole change."""
    from forgecast.graph import pipelines
    from forgecast.nodes import media as media_node
    from forgecast.style import sourcing as sourcing_module

    assert media_node.sourcing.budgets is sourcing_module.budgets
    assert pipelines.style_budgets is sourcing_module.budgets
    # And with no profile, it is still the shipped pair.
    assert sourcing_module.budgets(None, 12) == (video_budget(12), hero_budget(12))


def test_the_gate_and_the_ledger_read_one_setup_ceiling():
    from forgecast.nodes import sample as sample_node

    assert sample_node.MAX_SETUPS == MAX_SETUPS
