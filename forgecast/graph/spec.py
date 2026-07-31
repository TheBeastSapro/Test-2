"""Pipeline definitions as data.

A pipeline is a list of node specs with declared dependencies — a DAG, not a
sequence. Keeping it declarative buys three things: the UI can draw the graph
before anything runs, the reservation can be priced before anything runs, and
adding a stage is a list entry rather than a control-flow edit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Node


@dataclass(frozen=True)
class NodeSpec:
    key: str
    type: str
    title: str
    depends_on: tuple[str, ...] = ()
    requires_approval: bool = False
    params: dict = field(default_factory=dict)
    max_attempts: int = 3
    # Cost estimation hint: how many units this node is expected to consume.
    estimated_units: float = 0.0

    def to_node(self, run_id: int) -> Node:
        params = dict(self.params)
        params["estimated_units"] = self.estimated_units
        return Node(
            run_id=run_id,
            key=self.key,
            type=self.type,
            title=self.title,
            depends_on=list(self.depends_on),
            params=params,
            requires_approval=self.requires_approval,
            max_attempts=self.max_attempts,
        )


@dataclass(frozen=True)
class PipelineSpec:
    name: str
    title: str
    description: str
    nodes: tuple[NodeSpec, ...]

    def validate(self) -> None:
        keys = {spec.key for spec in self.nodes}
        if len(keys) != len(self.nodes):
            raise ValueError(f"pipeline {self.name} has duplicate node keys")
        for spec in self.nodes:
            missing = set(spec.depends_on) - keys
            if missing:
                raise ValueError(f"node {spec.key} depends on unknown node(s) {sorted(missing)}")
        self._assert_acyclic()

    def _assert_acyclic(self) -> None:
        edges = {spec.key: set(spec.depends_on) for spec in self.nodes}
        resolved: set[str] = set()
        while len(resolved) < len(edges):
            layer = {key for key, deps in edges.items() if key not in resolved
                     and deps <= resolved}
            if not layer:
                stuck = sorted(set(edges) - resolved)
                raise ValueError(f"pipeline {self.name} has a dependency cycle among {stuck}")
            resolved |= layer

    def instantiate(self, run_id: int) -> list[Node]:
        self.validate()
        return [spec.to_node(run_id) for spec in self.nodes]

    def topological_order(self) -> list[NodeSpec]:
        by_key = {spec.key: spec for spec in self.nodes}
        order: list[NodeSpec] = []
        resolved: set[str] = set()
        while len(order) < len(self.nodes):
            layer = sorted(
                (s for s in self.nodes if s.key not in resolved and set(s.depends_on) <= resolved),
                key=lambda s: s.key,
            )
            if not layer:
                break
            for spec in layer:
                order.append(by_key[spec.key])
                resolved.add(spec.key)
        return order
