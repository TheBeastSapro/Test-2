"""Credit ledger: the money has to add up exactly, every path."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from forgecast import credits as billing
from forgecast.graph.engine import create_run
from forgecast.models import Channel, LedgerEntry, LedgerKind, User


def test_balance_is_sum_of_deltas(session: Session, user: User):
    billing.grant(session, user.id, 500, note="bonus")
    billing.purchase(session, user.id, 1_000)
    entries = session.execute(
        select(LedgerEntry).where(LedgerEntry.user_id == user.id)
    ).scalars().all()
    assert billing.balance(session, user.id) == sum(e.delta for e in entries) == 11_500


def test_reserve_rejects_when_short(session: Session, user: User, channel: Channel):
    # create_run takes its own hold first, so read the balance after it.
    run = create_run(session, channel=channel, topic="x")
    balance = billing.balance(session, user.id)

    with pytest.raises(billing.InsufficientCredits) as excinfo:
        billing.reserve(session, run, balance + 1)
    assert excinfo.value.available == balance
    assert excinfo.value.needed == balance + 1


def test_starting_a_run_beyond_balance_is_refused(session: Session, user: User,
                                                  channel: Channel):
    """A user must never be able to start work they cannot pay for."""
    balance = billing.balance(session, user.id)
    # A two-hour video reserves ~520 plates and two hours of narration, comfortably past
    # a 10,000 credit balance. It used to say one hour, on a shots estimate of one clip
    # per 6 seconds of runtime — an estimate the node then undershot by ten times. Plates
    # are now budgeted at one per 14 seconds of scene and several shots are cut from each,
    # so an hour is affordable and the refusal has to be tested with something that is not.
    with pytest.raises(billing.InsufficientCredits) as excinfo:
        create_run(session, channel=channel, topic="too expensive",
                   pipeline="faceless_longform", options={"target_seconds": 7200})
    assert excinfo.value.needed > balance


def test_grant_is_idempotent(session: Session, user: User):
    before = billing.balance(session, user.id)
    for _ in range(3):
        billing.grant(session, user.id, 250, idempotency_key="signup:once")
    assert billing.balance(session, user.id) == before + 250


def test_reservation_closes_out_exactly(session: Session, user: User, channel: Channel):
    """Reserve, settle two nodes cheaper than estimated, release the rest."""
    opening = billing.balance(session, user.id)
    run = create_run(session, channel=channel, topic="Test topic", pipeline="faceless_shorts")
    held = run.credits_reserved

    assert held > 0
    assert billing.balance(session, user.id) == opening - held

    brief = next(node for node in run.nodes if node.key == "brief")
    brief.attempts = 1
    estimate = billing.estimate_node(brief.type, 0).credits
    billing.settle_node(session, run, brief, estimated=estimate, actual=2, provider="mock")

    assert billing.balance(session, user.id) == opening - held + estimate - 2
    assert run.credits_spent == 2

    released = billing.release_unused(session, run)
    assert released == held - estimate
    # Everything held is back; only the 2 actually spent is gone.
    assert billing.balance(session, user.id) == opening - 2


def test_release_unused_is_idempotent(session: Session, user: User, channel: Channel):
    run = create_run(session, channel=channel, topic="Topic", pipeline="faceless_shorts")
    first = billing.release_unused(session, run)
    balance = billing.balance(session, user.id)
    billing.release_unused(session, run)
    assert first > 0
    assert billing.balance(session, user.id) == balance


def test_refund_reverses_a_spend(session: Session, user: User, channel: Channel):
    run = create_run(session, channel=channel, topic="Topic", pipeline="faceless_shorts")
    node = next(n for n in run.nodes if n.key == "shots")
    node.attempts = 1
    billing.settle_node(session, run, node, estimated=0, actual=120, provider="fal")
    spent = billing.balance(session, user.id)

    billing.refund_node(session, run, node, 120, note="vendor returned garbage")
    assert billing.balance(session, user.id) == spent + 120
    assert run.credits_spent == 0


def test_estimate_scales_with_units():
    small = billing.estimate_node("voice", 500).credits
    large = billing.estimate_node("voice", 5_000).credits
    assert large > small
    # Base-only nodes cost the same regardless of units.
    assert billing.estimate_node("render", 0) == billing.estimate_node("render", 999)


def test_spend_kinds_are_recorded(session: Session, user: User, channel: Channel):
    run = create_run(session, channel=channel, topic="Topic", pipeline="faceless_shorts")
    kinds = {
        e.kind
        for e in session.execute(
            select(LedgerEntry).where(LedgerEntry.run_id == run.id)
        ).scalars()
    }
    assert kinds == {LedgerKind.reserve}
