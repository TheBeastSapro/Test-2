"""Pipeline specs and graph layout."""

from __future__ import annotations

import pytest

from forgecast.graph.pipelines import PIPELINES, get_pipeline
from forgecast.graph.spec import NodeSpec, PipelineSpec


@pytest.mark.parametrize("name", sorted(PIPELINES))
def test_shipped_pipelines_are_valid_dags(name: str):
    get_pipeline(name).validate()  # raises on cycles or dangling deps


def test_unknown_pipeline_is_reported():
    with pytest.raises(KeyError, match="unknown pipeline"):
        get_pipeline("does_not_exist")


def test_dangling_dependency_is_rejected():
    spec = PipelineSpec(
        name="broken", title="", description="",
        nodes=(NodeSpec(key="a", type="brief", title="A", depends_on=("ghost",)),),
    )
    with pytest.raises(ValueError, match="unknown node"):
        spec.validate()


def test_cycle_is_rejected():
    spec = PipelineSpec(
        name="cyclic", title="", description="",
        nodes=(
            NodeSpec(key="a", type="brief", title="A", depends_on=("b",)),
            NodeSpec(key="b", type="script", title="B", depends_on=("a",)),
        ),
    )
    with pytest.raises(ValueError, match="cycle"):
        spec.validate()


def test_duplicate_keys_are_rejected():
    spec = PipelineSpec(
        name="dupe", title="", description="",
        nodes=(
            NodeSpec(key="a", type="brief", title="A"),
            NodeSpec(key="a", type="script", title="A again"),
        ),
    )
    with pytest.raises(ValueError, match="duplicate"):
        spec.validate()


def test_topological_order_respects_dependencies():
    spec = get_pipeline("faceless_longform")
    order = [node.key for node in spec.topological_order()]
    assert len(order) == len(spec.nodes)
    for node in spec.nodes:
        for dep in node.depends_on:
            assert order.index(dep) < order.index(node.key)


def test_publish_is_gated_by_a_separate_review_node():
    """Publishing must not be a post-hoc gate — you cannot un-upload a video."""
    spec = get_pipeline("faceless_longform")
    by_key = {node.key: node for node in spec.nodes}
    assert by_key["final_review"].requires_approval is True
    assert by_key["publish"].requires_approval is False
    assert "final_review" in by_key["publish"].depends_on


def test_cheap_stages_carry_the_gates():
    """Gates belong on stages that determine cost, not on the ones that incur it."""
    spec = get_pipeline("faceless_longform")
    gated = {node.key for node in spec.nodes if node.requires_approval}
    assert {"brief", "script"} <= gated
    assert "shots" not in gated  # the expensive node must sit behind a gate, not be one


def test_avatar_node_only_appears_when_requested():
    without = {n.key for n in get_pipeline("faceless_longform", use_avatar=False).nodes}
    with_avatar = {n.key for n in get_pipeline("faceless_longform", use_avatar=True).nodes}
    assert "avatar" not in without
    assert "avatar" in with_avatar


def test_publish_can_be_disabled():
    keys = {n.key for n in get_pipeline("faceless_longform", publish=False).nodes}
    assert "publish" not in keys and "final_review" not in keys


def test_longer_targets_plan_more_shots():
    short = get_pipeline("faceless_longform", target_seconds=120)
    long = get_pipeline("faceless_longform", target_seconds=900)
    units = lambda spec: next(
        n.estimated_units for n in spec.nodes if n.key == "shots"
    )
    assert units(long) > units(short)
