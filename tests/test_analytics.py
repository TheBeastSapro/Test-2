"""Analytics, checked against fixtures whose answers are worked out by hand.

Every assertion here is a number a person computed on paper first — six durations
whose median is 210 seconds, three stages whose spend adds to 300 credits. That is
deliberate: a test that asserts the page agrees with itself would pass just as happily
if the median were the mean and the shares were normalised to the wrong total.

The two failures worth guarding hardest are the quiet ones. A confident median of two
runs is worse than no median, and an empty account is the one input the page is
guaranteed to meet before any other — so both get their own test.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from forgecast import credits as billing
from forgecast.api.main import create_app
from forgecast.api.routes_analytics import human_duration, report
from forgecast.api.routes_analytics import router as analytics_router
from forgecast.auth import hash_password
from forgecast.db import SessionLocal
from forgecast.graph.engine import GraphEngine, create_run
from forgecast.memory import learn_from_approval, learn_from_revision
from forgecast.models import Channel, Node, NodeStatus, Run, RunStatus, User

QUEUED_AT = datetime(2026, 3, 1, 9, 0, 0)


@pytest.fixture
def client(user):
    """The page mounted explicitly as well as by the app.

    `main.py` already registers this router, and including it a second time is
    harmless because the first matching route wins and both are this module's. It stays
    because the alternative is a suite that goes green on a build where the page was
    never mounted — the one failure these tests exist to catch and the one they would
    be blind to.
    """
    app = create_app()
    app.include_router(analytics_router)
    with TestClient(app) as test_client:
        token = test_client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "supersecret"},
        ).json()["access_token"]
        test_client.headers["Authorization"] = f"Bearer {token}"
        yield test_client


def a_run(
    session: Session, channel: Channel, *,
    seconds: int | None = None,
    spend: int = 0,
    stage: str = "render",
    status: RunStatus = RunStatus.completed,
    died_at: str = "",
) -> Run:
    """One run with a known wall-clock time, and optionally what it spent or died at.

    Credits go in through `billing.settle_node` rather than by setting
    `Run.credits_spent`, because the page reads the ledger. A fixture that only set the
    counter would test a code path the app does not have.
    """
    run = Run(
        channel_id=channel.id,
        user_id=channel.user_id,
        topic="Anything",
        status=status,
        created_at=QUEUED_AT,
        finished_at=None if seconds is None else QUEUED_AT + timedelta(seconds=seconds),
    )
    session.add(run)
    session.flush()
    if died_at:
        session.add(Node(run_id=run.id, key=died_at, type=died_at, title=died_at,
                         status=NodeStatus.failed))
        session.flush()
    if spend:
        node = Node(run_id=run.id, key=stage, type=stage, title=stage,
                    status=NodeStatus.completed, attempts=1)
        session.add(node)
        session.flush()
        billing.settle_node(session, run, node, estimated=0, actual=spend,
                            provider="mock")
    return run


# ------------------------------------------------------------------ the arithmetic


def test_human_duration_picks_units_a_person_would_use():
    assert human_duration(None) == "—"
    assert human_duration(42) == "42s"
    assert human_duration(210) == "3m 30s"
    assert human_duration(4_500) == "1h 15m"
    # Three days at a gate is three days, not "76h".
    assert human_duration(3 * 86_400 + 3_600) == "3d 1h"


def test_per_channel_numbers_are_the_ones_worked_out_by_hand(session, user):
    channel = Channel(user_id=user.id, name="Ocean Freight", aspect_ratio="16:9")
    session.add(channel)
    session.flush()

    # Six finished runs: 60, 120, 180, 240, 300, 600 seconds. The median of an even
    # sample is the mean of the middle pair — (180 + 240) / 2 = 210 = 3m 30s.
    for seconds, spent in zip((60, 120, 180, 240, 300, 600),
                              (100, 100, 100, 100, 100, 160), strict=True):
        a_run(session, channel, seconds=seconds, spend=spent)
    # 660 credits over 6 finished videos = 110.0 each.
    a_run(session, channel, seconds=90, status=RunStatus.failed, died_at="render")
    a_run(session, channel, seconds=95, status=RunStatus.failed, died_at="render")
    a_run(session, channel, seconds=30, status=RunStatus.failed, died_at="voice")
    a_run(session, channel, seconds=10, status=RunStatus.cancelled)
    a_run(session, channel, status=RunStatus.running)
    session.commit()

    row = report(session, user)["channels"][0]
    assert (row["started"], row["completed"], row["failed"]) == (11, 6, 3)
    assert (row["cancelled"], row["in_flight"]) == (1, 1)
    assert row["median_seconds"] == 210
    assert row["median_label"] == "3m 30s"
    assert row["credits_per_video"] == 110.0
    # Where the deaths happened, worst stage first — the whole point of counting them.
    assert row["deaths"] == [{"node_type": "render", "count": 2},
                             {"node_type": "voice", "count": 1}]
    assert row["complete_pct"] == pytest.approx(54.55, abs=0.01)
    # Six finished videos and three dead runs is not a failing channel: red here would
    # be a verdict the numbers do not support, on the screen someone checks before
    # deciding to abandon a channel. This fixture also has a run still going, and that
    # outranks everything else because it is the one worth looking at.
    assert row["in_flight"] == 1
    assert row["health"] == "running"


def test_a_median_of_two_runs_is_refused_rather_than_printed(session, user, client):
    """The failure this prevents is a scheduling promise built on two afternoons."""
    channel = Channel(user_id=user.id, name="Thin Sample", aspect_ratio="16:9")
    session.add(channel)
    session.flush()
    a_run(session, channel, seconds=120, spend=100)
    a_run(session, channel, seconds=7_200, spend=100)
    session.commit()

    summary = report(session, user)
    row = summary["channels"][0]
    assert row["completed"] == 2               # the count is exact
    assert row["enough"] is False
    assert row["median_seconds"] is None       # the median is not offered
    assert row["credits_per_video"] is None
    assert summary["totals"]["enough"] is False
    assert summary["totals"]["credits_per_video"] is None

    page = client.get("/analytics")
    assert page.status_code == 200
    assert "not yet meaningful" in page.text
    # And the number it would have printed appears nowhere: the median of those two is
    # 3660s, which is 1h 01m.
    assert "1h 01m" not in page.text


def test_the_median_appears_once_the_sample_is_large_enough(session, user, client):
    channel = Channel(user_id=user.id, name="Enough Runs", aspect_ratio="16:9")
    session.add(channel)
    session.flush()
    # Five runs, 60/120/180/240/300 — an odd sample, so the median is the middle one.
    for seconds in (60, 120, 180, 240, 300):
        a_run(session, channel, seconds=seconds, spend=40)
    session.commit()

    totals = report(session, user)["totals"]
    assert totals["enough"] is True
    assert totals["median_label"] == "3m 00s"
    assert totals["credits_per_video"] == 40.0
    assert "3m 00s" in client.get("/analytics").text


# ------------------------------------------------------------------------ credits


def test_credits_are_attributed_to_the_stage_that_spent_them(session, user):
    channel = Channel(user_id=user.id, name="Spend Test", aspect_ratio="16:9")
    session.add(channel)
    session.flush()
    run = a_run(session, channel, seconds=300)

    nodes = {}
    for key, node_type in (("script", "script"), ("voice", "voice"), ("shots", "shots")):
        node = Node(run_id=run.id, key=key, type=node_type, title=key,
                    status=NodeStatus.completed, attempts=1)
        session.add(node)
        nodes[key] = node
    session.flush()

    # Settled through the real billing path, so the ledger rows are the shape the app
    # actually writes rather than a fixture's idea of them.
    for key, actual in (("script", 20), ("voice", 60), ("shots", 220)):
        billing.settle_node(session, run, nodes[key], estimated=0, actual=actual,
                            provider="mock")
    session.commit()

    rows = report(session, user)["credit_rows"]
    # 220 + 60 + 20 = 300, so the shares are 73.3 / 20.0 / 6.7 and the bars scale to
    # the biggest stage rather than to the total: 100 / 27.27 / 9.09.
    assert [row["node_type"] for row in rows] == ["shots", "voice", "script"]
    assert [row["credits"] for row in rows] == [220, 60, 20]
    assert [row["share"] for row in rows] == [73.3, 20.0, 6.7]
    assert [row["bar"] for row in rows] == [100.0, 27.27, 9.09]
    assert report(session, user)["totals"]["credits_spent"] == 300


def test_a_refunded_stage_is_not_billed_for_what_it_gave_back(session, user):
    """The reason this reads the ledger instead of `Node.credits_spent`.

    `refund_node` hands the credits back and decrements the run, but never the node's
    own counter. Summing node rows would keep charging the shots stage for output the
    provider was already refunded for — and shots is the stage that fails most, so it
    is the one the wrong sum overstates worst.
    """
    channel = Channel(user_id=user.id, name="Refund Test", aspect_ratio="16:9")
    session.add(channel)
    session.flush()
    run = a_run(session, channel, seconds=120)
    node = Node(run_id=run.id, key="shots", type="shots", title="shots",
                status=NodeStatus.completed, attempts=1)
    session.add(node)
    session.flush()

    billing.settle_node(session, run, node, estimated=0, actual=200, provider="fal")
    billing.refund_node(session, run, node, 150, note="provider returned noise")
    session.commit()

    assert node.credits_spent == 200                    # the node still says 200
    rows = report(session, user)["credit_rows"]
    assert rows == [{"node_type": "shots", "credits": 50, "share": 100.0, "bar": 100.0}]


# ------------------------------------------------------------------ gate behaviour


def test_gate_behaviour_is_counted_per_stage_and_worst_first(session, user):
    channel = Channel(user_id=user.id, name="Gate Test", aspect_ratio="16:9")
    session.add(channel)
    session.flush()

    # script: 2 approved, 4 sent back — 67%, over the line and past the sample floor.
    for _ in range(2):
        learn_from_approval(session, channel.id, "script", "fine")
    for _ in range(4):
        learn_from_revision(session, channel.id, "script", "blunter hook")
    # brief: 5 approved, 1 sent back — 17%, a stage that works.
    for _ in range(5):
        learn_from_approval(session, channel.id, "brief", "fine")
    learn_from_revision(session, channel.id, "brief", "wrong angle")
    # thumbnail: one decision. A rate off one decision is not a rate.
    learn_from_revision(session, channel.id, "thumbnail", "text too small")
    session.commit()

    rows = {row["node_type"]: row for row in report(session, user)["gates"]}
    # Worst readable rate first, and the one-decision stage last: a 100% send-back rate
    # off a single gate is not the thing to look at first.
    assert [row["node_type"] for row in report(session, user)["gates"]] == \
        ["script", "brief", "thumbnail"]

    script = rows["script"]
    assert (script["approved"], script["revised"], script["total"]) == (2, 4, 6)
    assert script["revise_pct"] == 67
    assert script["needs_work"] is True
    # Two segments of one bar, so they have to add to the full width.
    assert script["approved_bar"] + script["revised_bar"] == pytest.approx(100.0)

    assert rows["brief"]["needs_work"] is False
    assert rows["brief"]["revise_pct"] == 17

    thin = rows["thumbnail"]
    assert (thin["revised"], thin["reliable"], thin["needs_work"]) == (1, False, False)


async def test_a_real_gate_decision_shows_up_on_the_page(session, channel, user, client):
    """Counted from the path the app actually takes, not from a fixture's shortcut.

    A revision *resets* the node — status back to pending, output cleared — so counting
    approvals off node rows would report this run as one decision instead of two. This
    drives the engine to a real gate and asserts both decisions survive.
    """
    run = create_run(session, channel=channel, topic="Gate wiring",
                     pipeline="faceless_shorts")
    run_id = run.id
    session.commit()

    graph = GraphEngine(SessionLocal, worker_id="test-analytics", concurrency=2)
    assert await graph.advance(run_id) is RunStatus.awaiting_approval

    with SessionLocal() as db:
        gate = db.execute(
            select(Node).where(Node.run_id == run_id,
                               Node.status == NodeStatus.awaiting_approval)
        ).scalars().one()
        assert gate.type == "brief"
        graph.revise(db, gate, "narrower angle, and lose the second beat")
        db.commit()

    await graph.advance(run_id)
    with SessionLocal() as db:
        gate = db.execute(
            select(Node).where(Node.run_id == run_id,
                               Node.status == NodeStatus.awaiting_approval)
        ).scalars().one()
        graph.approve(db, gate, note="better")
        db.commit()

    with SessionLocal() as db:
        brief = next(row for row in report(db, db.get(User, user.id))["gates"]
                     if row["node_type"] == "brief")
    assert (brief["approved"], brief["revised"]) == (1, 1)
    assert "brief" in client.get("/analytics").text


# ------------------------------------------------------------------- what is drawn


def test_every_bar_is_a_server_rendered_width_and_nothing_is_fetched(session, user, client):
    """The page has to draw itself on a machine with no network.

    A charting library from a CDN renders as an empty box exactly when it is needed —
    offline, which is every machine this app runs on — so the bars are divs with a
    width computed on the server. Asserted on the markup because "it looked fine in
    the browser" is a test that only passes on a connected laptop.
    """
    channel = Channel(user_id=user.id, name="Busy Channel", aspect_ratio="16:9")
    session.add(channel)
    session.flush()
    for seconds in (60, 120, 180, 240, 300):
        a_run(session, channel, seconds=seconds, spend=100, stage="shots")
    a_run(session, channel, seconds=45, status=RunStatus.failed, died_at="render")
    for _ in range(4):
        learn_from_revision(session, channel.id, "script", "blunter hook")
    for _ in range(2):
        learn_from_approval(session, channel.id, "script", "fine")
    session.commit()

    page = client.get("/analytics")
    assert page.status_code == 200
    body = page.text
    # The widest bar is the biggest stage, drawn inline.
    assert 'style="width:100.0%"' in body
    assert 'style="width:66.67%"' in body        # 4 of 6 script gates sent back
    assert "Died at" in body and "render" in body
    assert "needs work" in body                  # the verdict the counts earn
    # Nothing is loaded from anywhere but this app's own static mount, and no canvas
    # is waiting for a script to fill it in.
    assert 'src="http' not in body and 'href="http' not in body
    assert "<canvas" not in body


# ------------------------------------------------------------ the awkward accounts


def test_an_empty_account_renders_without_dividing_by_zero(session, user, client):
    """No channels, no runs, no ledger — every ratio on this page has a zero divisor.

    This is the first input the page ever meets, so it gets a test of its own rather
    than being assumed to fall out of the others.
    """
    summary = report(session, user)
    assert summary["channels"] == []
    assert summary["credit_rows"] == []
    assert summary["gates"] == []
    assert summary["totals"]["started"] == 0
    assert summary["totals"]["completion_pct"] == 0
    assert summary["totals"]["median_label"] == "—"
    assert summary["totals"]["credits_per_video"] is None

    page = client.get("/analytics")
    assert page.status_code == 200
    # It has to say why it is empty. A blank page is indistinguishable from a bug.
    assert "No runs yet" in page.text


def test_a_channel_with_no_runs_at_all_is_listed_without_arithmetic(session, user):
    channel = Channel(user_id=user.id, name="Never Used", aspect_ratio="9:16")
    session.add(channel)
    session.commit()

    row = report(session, user)["channels"][0]
    assert (row["started"], row["completed"], row["complete_pct"]) == (0, 0, 0.0)
    assert row["median_seconds"] is None
    assert row["format"] == "Shorts"


def test_another_account_is_never_counted(session, user):
    """Every figure is scoped to the signed-in user, or this page leaks a business."""
    theirs = User(email="rival@example.test", hashed_password=hash_password("x" * 12))
    session.add(theirs)
    session.flush()
    their_channel = Channel(user_id=theirs.id, name="Rival Channel", aspect_ratio="16:9")
    session.add(their_channel)
    session.flush()
    for seconds in (60, 120, 180, 240, 300):
        a_run(session, their_channel, seconds=seconds, spend=99)
    learn_from_revision(session, their_channel.id, "script", "not your business")

    mine = Channel(user_id=user.id, name="Mine", aspect_ratio="16:9")
    session.add(mine)
    session.flush()
    a_run(session, mine, seconds=60, spend=10)
    session.commit()

    summary = report(session, user)
    assert [row["name"] for row in summary["channels"]] == ["Mine"]
    assert summary["totals"]["started"] == 1
    assert summary["gates"] == []
    assert "Rival Channel" not in str(summary)


def test_the_page_sends_a_stranger_to_the_login(session):
    app = create_app()
    app.include_router(analytics_router)
    with TestClient(app) as anonymous:
        page = anonymous.get("/analytics", follow_redirects=False)
    assert page.status_code == 303
    assert page.headers["location"] == "/login?next=/analytics"


def test_a_channel_that_has_shipped_is_not_greyed_out_for_one_death(session, user):
    """The mixed case needs its own answer.

    Five finished videos and one dead run used to fall through to "queued" — a state
    the channel was not in — and the shared status colour for queued is grey, so a
    channel that had shipped five videos looked dormant. Not red either: one death
    beside five successes is not a failing channel, which is the whole reason the
    fallback exists.
    """
    from datetime import UTC, datetime, timedelta

    from forgecast.api.routes_analytics import channel_rows
    from forgecast.models import Channel, Run, RunStatus

    channel = Channel(user_id=user.id, name="Shipped", aspect_ratio="16:9")
    session.add(channel)
    session.flush()

    start = datetime.now(UTC) - timedelta(days=1)
    for index in range(5):
        session.add(Run(channel_id=channel.id, user_id=user.id, topic=f"done {index}",
                        pipeline="faceless_longform", status=RunStatus.completed,
                        created_at=start,
                        finished_at=start + timedelta(seconds=100 * (index + 1))))
    session.add(Run(channel_id=channel.id, user_id=user.id, topic="died",
                    pipeline="faceless_longform", status=RunStatus.failed,
                    created_at=start, finished_at=start + timedelta(seconds=60)))
    session.commit()

    row = next(r for r in channel_rows(session, user, {}) if r["name"] == "Shipped")
    assert (row["completed"], row["failed"], row["in_flight"]) == (5, 1, 0)
    assert row["health"] == "completed"

    # Work still going outranks both, because that is the one worth looking at.
    session.add(Run(channel_id=channel.id, user_id=user.id, topic="running",
                    pipeline="faceless_longform", status=RunStatus.running))
    session.commit()
    row = next(r for r in channel_rows(session, user, {}) if r["name"] == "Shipped")
    assert row["health"] == "running"

    # And exactly five finished is the sample floor, so the median is published.
    assert row["enough"] is True
    assert row["median_seconds"] == 300.0
