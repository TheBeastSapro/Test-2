"""Credit pricing and the append-only ledger.

The money model, in one paragraph: a run **reserves** the sum of its per-node
estimates before any provider is called, so a user can never start work they
cannot pay for. As each node finishes, its estimate is **released** and its
**actual** cost is spent. Whatever the estimate over-collected flows straight back.
If a run dies halfway, the estimates for nodes that never ran are released too.
Every movement is a row; the current balance is `balance_after` on the newest row.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import PLAN_MONTHLY_CREDITS, LedgerEntry, LedgerKind, Node, Plan, Run, User

# One credit is priced so the Pro tier ($49 / 3,000 credits) sells a credit for
# ~$0.0163. Provider cost per credit is targeted at ~$0.006, i.e. a ~2.7x gross
# margin, which is what pays for the render compute and the free tier.
USD_PER_CREDIT = 49 / 3000


class InsufficientCredits(Exception):
    def __init__(self, needed: int, available: int) -> None:
        self.needed = needed
        self.available = available
        super().__init__(f"need {needed} credits, have {available}")


# --------------------------------------------------------------------------- pricing

# Base cost per node execution: the fixed overhead of the stage, not its output.
# Keep these small — a base fee that rivals the variable cost double-charges the user.
BASE_COSTS: dict[str, int] = {
    "brief": 3,
    "research": 8,        # query planning + one extraction call per fetched page
    "voice_casting": 2,   # a few seconds of TTS per audition
    "script": 5,
    "thumbnail": 2,
    "voice": 2,
    "broll_plan": 3,
    "shots": 5,
    "avatar": 5,
    "render": 3,      # our own CPU, not a vendor
    "compliance": 3,
    "final_review": 1,
    "publish": 2,
}

# Variable component, charged per unit of work the node actually does. Each figure is
# derived from the provider's unit price in forgecast/providers/media.py at the 2x
# markup, converted through USD_PER_CREDIT. If you change a vendor price there, change
# it here in the same commit or the estimate silently stops matching reality.
PER_UNIT_COSTS: dict[str, tuple[str, int, int]] = {
    # node type -> (unit name, credits per unit, unit size)
    "script": ("words", 2, 250),        # LLM output tokens ≈ $0.045/1k words
    "voice": ("characters", 18, 1000),  # ElevenLabs $0.15/1k chars
    "thumbnail": ("images", 5, 1),      # FAL $0.04/image
    "avatar": ("seconds", 12, 10),      # HeyGen $0.60/min
    # Blended: the B-roll planner caps animated shots at a third of the list, so a
    # per-clip estimate of "all video" (≈55) would hold three times what a run spends.
    # 1/3 x 55 (video) + 2/3 x 5 (still) ≈ 22.
    "shots": ("clips", 22, 1),
    "research": ("pages", 4, 1),        # one LLM extraction call per page
    "voice_casting": ("auditions", 3, 1),
}


@dataclass(frozen=True)
class CostEstimate:
    node_type: str
    credits: int
    detail: str

    def as_dict(self) -> dict:
        return {"node_type": self.node_type, "credits": self.credits, "detail": self.detail}


def estimate_node(node_type: str, units: float = 0.0) -> CostEstimate:
    """Estimate one node. `units` is in the node's natural unit (words, clips, …)."""
    base = BASE_COSTS.get(node_type, 5)
    detail = f"base {base}"
    variable = 0
    if node_type in PER_UNIT_COSTS and units:
        unit_name, per, size = PER_UNIT_COSTS[node_type]
        variable = math.ceil(units / size) * per
        detail = f"base {base} + {variable} for {units:g} {unit_name}"
    return CostEstimate(node_type, base + variable, detail)


def estimate_run(nodes: list[Node]) -> int:
    """Reservation amount for a queued run, from its planned node params."""
    total = 0
    for node in nodes:
        units = float(node.params.get("estimated_units", 0) or 0)
        total += estimate_node(node.type, units).credits
    return total


def credits_to_usd(credits: int) -> float:
    return round(credits * USD_PER_CREDIT, 4)


# ---------------------------------------------------------------------------- ledger


def balance(session: Session, user_id: int) -> int:
    row = session.execute(
        select(LedgerEntry.balance_after)
        .where(LedgerEntry.user_id == user_id)
        .order_by(LedgerEntry.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    return int(row or 0)


def _append(
    session: Session,
    *,
    user_id: int,
    kind: LedgerKind,
    delta: int,
    run_id: int | None = None,
    node_key: str | None = None,
    provider: str | None = None,
    note: str = "",
    idempotency_key: str | None = None,
) -> LedgerEntry:
    if idempotency_key:
        existing = session.execute(
            select(LedgerEntry).where(LedgerEntry.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        if existing is not None:
            return existing

    current = balance(session, user_id)
    entry = LedgerEntry(
        user_id=user_id,
        kind=kind,
        delta=delta,
        balance_after=current + delta,
        run_id=run_id,
        node_key=node_key,
        provider=provider,
        note=note,
        idempotency_key=idempotency_key,
    )
    session.add(entry)
    session.flush()
    return entry


def grant(
    session: Session,
    user_id: int,
    amount: int,
    note: str = "",
    idempotency_key: str | None = None,
) -> LedgerEntry:
    return _append(
        session,
        user_id=user_id,
        kind=LedgerKind.grant,
        delta=abs(amount),
        note=note,
        idempotency_key=idempotency_key,
    )


def purchase(session: Session, user_id: int, amount: int, note: str = "") -> LedgerEntry:
    return _append(
        session, user_id=user_id, kind=LedgerKind.purchase, delta=abs(amount), note=note
    )


def apply_plan_renewal(session: Session, user: User, period_key: str) -> LedgerEntry | None:
    """Idempotent monthly top-up. `period_key` is e.g. '2026-07'."""
    amount = PLAN_MONTHLY_CREDITS.get(Plan(user.plan), 0)
    if amount <= 0:
        return None
    return grant(
        session,
        user.id,
        amount,
        note=f"{user.plan.value} plan credits for {period_key}",
        idempotency_key=f"plan:{user.id}:{period_key}",
    )


def reserve(session: Session, run: Run, amount: int) -> LedgerEntry:
    available = balance(session, run.user_id)
    if amount > available:
        raise InsufficientCredits(amount, available)
    run.credits_reserved = amount
    return _append(
        session,
        user_id=run.user_id,
        kind=LedgerKind.reserve,
        delta=-abs(amount),
        run_id=run.id,
        note=f"hold for run {run.id}",
        idempotency_key=f"run:{run.id}:reserve",
    )


def settle_node(
    session: Session,
    run: Run,
    node: Node,
    *,
    estimated: int,
    actual: int,
    provider: str | None = None,
) -> None:
    """Release this node's slice of the hold, then charge what it really cost."""
    take = node.attempts
    if estimated:
        _append(
            session,
            user_id=run.user_id,
            kind=LedgerKind.release,
            delta=abs(estimated),
            run_id=run.id,
            node_key=node.key,
            note=f"release estimate for {node.key}",
            idempotency_key=f"run:{run.id}:{node.key}:take{take}:release",
        )
    if actual:
        _append(
            session,
            user_id=run.user_id,
            kind=LedgerKind.spend,
            delta=-abs(actual),
            run_id=run.id,
            node_key=node.key,
            provider=provider,
            note=f"{node.type} execution",
            idempotency_key=f"run:{run.id}:{node.key}:take{take}:spend",
        )
    node.credits_spent = (node.credits_spent or 0) + actual
    run.credits_spent = (run.credits_spent or 0) + actual


def release_unused(session: Session, run: Run) -> int:
    """On terminal runs, hand back the hold for every node that never settled."""
    settled = session.execute(
        select(LedgerEntry).where(
            LedgerEntry.run_id == run.id, LedgerEntry.kind == LedgerKind.release
        )
    ).scalars().all()
    released = sum(e.delta for e in settled)
    remaining = max(0, (run.credits_reserved or 0) - released)
    if remaining:
        _append(
            session,
            user_id=run.user_id,
            kind=LedgerKind.release,
            delta=remaining,
            run_id=run.id,
            note=f"release unused hold for run {run.id}",
            idempotency_key=f"run:{run.id}:final-release",
        )
    return remaining


def refund_node(session: Session, run: Run, node: Node, amount: int, note: str = "") -> None:
    """Provider took money and returned garbage — give the credits back."""
    _append(
        session,
        user_id=run.user_id,
        kind=LedgerKind.refund,
        delta=abs(amount),
        run_id=run.id,
        node_key=node.key,
        note=note or f"refund for {node.key}",
        idempotency_key=f"run:{run.id}:{node.key}:take{node.attempts}:refund",
    )
    run.credits_spent = max(0, (run.credits_spent or 0) - amount)
