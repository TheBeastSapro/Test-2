"""Whether the pipeline can actually run the Sample Gate.

`skills/gates.py` carried the whole of this as pure functions from the day it was written,
under a note saying the pipeline "can be wired to this later without either side growing a
dependency on the other". It never was — and `test_sample_gate.py` beside this file has
been testing that arithmetic all along, which is the sharpest version of the problem:
fully specified, fully tested, and unreachable. Three shipped skill documents told the
agent the gate was mandatory, `image-to-video.md` calling it the one rule that outranks all
others, for a gate the application could not run.

So nothing here re-tests the arithmetic. It tests that the node is registered, that it
sits between the plan and the batch in both pipelines, and that the batch cannot start
while the samples are still being looked at.
"""

from __future__ import annotations

from types import SimpleNamespace

import forgecast.nodes  # noqa: F401  - importing registers every handler
from forgecast.credits import estimate_node
from forgecast.graph import pipelines
from forgecast.graph.engine import registry
from forgecast.nodes import sample as sample_node

PIPELINES = ("faceless_longform", "faceless_shorts")


def _nodes(name: str) -> dict:
    return {node.key: node for node in pipelines.get_pipeline(name).nodes}


# ------------------------------------------------------------------ registration


def test_the_handler_is_registered():
    """It was written and never imported, which is the defect this file is about."""
    assert "sample" in registry


def test_the_node_is_in_both_pipelines():
    for name in PIPELINES:
        assert "sample" in _nodes(name), name


# ------------------------------------------------------------------ the gate


def test_it_stops_for_approval():
    """A node that samples and carries straight on has spent money to learn nothing."""
    for name in PIPELINES:
        assert _nodes(name)["sample"].requires_approval is True, name


def test_the_batch_cannot_start_until_the_samples_are_approved():
    """An edge only on the plan would let eighty clips render while the operator was
    still looking at the sample."""
    for name in PIPELINES:
        nodes = _nodes(name)
        assert "sample" in nodes["shots"].depends_on, name
        # And still on the plan, because that is where the shot list comes from.
        assert "broll_plan" in nodes["shots"].depends_on, name


def test_it_sits_after_the_plan_and_before_the_batch():
    for name in PIPELINES:
        assert _nodes(name)["sample"].depends_on == ("broll_plan",), name


def test_the_gate_is_on_the_stage_that_determines_the_spend():
    """ARCHITECTURE.md's own rule, and the shape `final_review` already has.

    The plan is free and decides everything; the batch is about 90% of the video's cost
    and decides nothing. An approval on the batch would be approving a number nobody had
    seen the consequence of.
    """
    for name in PIPELINES:
        nodes = _nodes(name)
        assert nodes["broll_plan"].requires_approval is False, name
        assert nodes["shots"].requires_approval is False, name
        assert nodes["sample"].requires_approval is True, name


# ------------------------------------------------------------------ the money


def test_the_gate_costs_far_less_than_the_batch_it_authorises():
    """If it did not, it would be cheaper to render the batch and throw it away."""
    gate = estimate_node("sample", 3)      # three distinct setups, a busy video
    batch = estimate_node("shots", 80)
    assert batch.credits > gate.credits * 10


def test_a_sample_is_priced_as_video_rather_than_as_a_blended_shot():
    """`shots` blends stills and video because the planner caps animated shots at a
    third of the list. A sample is always generated video, so the blended figure
    under-reserves it."""
    per_sample = estimate_node("sample", 1).credits - estimate_node("sample", 0).credits
    per_shot = estimate_node("shots", 1).credits - estimate_node("shots", 0).credits
    assert per_sample > per_shot


def test_its_base_fee_does_not_rival_its_variable_cost():
    """`credits.py`'s own rule for that table: a base fee that rivals the variable cost
    double-charges the user."""
    base = estimate_node("sample", 0).credits
    assert base < estimate_node("sample", 1).credits / 10


# ------------------------------------------------------------------ the grouping


def test_one_sample_per_setup_rather_than_per_shot():
    """A sample per shot costs as much as the render and gates nothing; one for the whole
    run approves camera moves nobody looked at, which is what `gates.covers` catches."""
    assert sample_node.MAX_SETUPS <= 6


def test_a_shot_with_no_stated_camera_groups_with_the_others_that_named_none():
    """Otherwise every unstated shot forms a setup of its own, the gate fires on all of
    them, and somebody turns it off."""
    from forgecast.prompts import moves

    assert sample_node.DEFAULT_CAMERA == moves.DEFAULT_KEY


def test_style_comes_from_the_channel_and_motion_from_the_shot():
    """Two shots differing only in subject are the same setup. Treating them as different
    is the other way a gate ends up firing on every shot."""

    channel = SimpleNamespace(
        style_profile={"register": "plain", "grade": "cool", "lighting": "low-key"})

    def setup_for(**shot):
        return sample_node._setup_for(
            {"model": "m", "motion": "push_in", "intensity": "subtle",
             "focal_verb": "looks", "seconds": 6, **shot},
            channel, "16:9")

    assert setup_for(scene_index=1).setup_id == setup_for(scene_index=2).setup_id
    # A different camera is a different setup, because motion is where melting happens.
    assert setup_for(motion="crash_zoom").setup_id != setup_for().setup_id
    # And a different model is, because a model is the largest single difference there is.
    other = sample_node._setup_for(
        {"model": "other", "motion": "push_in", "intensity": "subtle",
         "focal_verb": "looks", "seconds": 6}, channel, "16:9")
    assert other.setup_id != setup_for().setup_id
