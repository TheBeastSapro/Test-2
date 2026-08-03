"""Analytics: the four numbers that change a decision.

## Why this page exists

Forgecast already records everything worth knowing and shows almost none of it. A run
page tells you about one run; the sidebar tells you a run exists. Neither answers the
questions you actually have after a fortnight of production:

* which channel finishes what it starts, and which one keeps dying — and *where*;
* how long a video really takes from asking for it to having it;
* what a finished video costs, and which stage is eating the credits;
* which gate you keep sending back, because that is a prompt with a bug in it.

Every figure here is one you would act on. There is deliberately nothing that is
merely interesting: no runs-per-day sparkline, no vanity totals. A number that cannot
change what you do next is decoration, and decoration on an operations page is worse
than a blank space because it competes for the attention the real numbers need.

## Why the gate figures come from channel memory

Approving and revising are recorded three ways: on the node (`reviewed_at`,
`review_feedback`), as a `RunEvent`, and as a `ChannelMemory` written by
`learn_from_approval` / `learn_from_revision`. Only the memory rows are usable for
counting. The node is *reset* by a revision — output cleared, status back to pending,
`reviewed_at` wiped when it is invalidated downstream — so a node that was sent back
three times and finally approved looks, in its own row, like a node that was approved
once. Run events survive but carry prose and a node key rather than a node type.
The memory rows are append-only, carry the node type, and are written by the only two
code paths that can pass or fail a gate.

## Why small samples are refused rather than rounded

A median of two runs printed with the same confidence as a median of fifty is worse
than printing nothing: it invites a scheduling promise the data cannot support. Below
`MIN_SAMPLE` finished runs the page says so in place of the figure. This is the whole
difference between measurement and a dashboard.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from statistics import median

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import optional_user
from ..db import get_session
from ..graph import formats
from ..models import (
    Channel,
    ChannelMemory,
    LedgerEntry,
    LedgerKind,
    MemoryKind,
    Node,
    NodeStatus,
    Run,
    RunStatus,
    User,
)

router = APIRouter(include_in_schema=False)

# Finished runs needed before a median or a per-video cost is printed at all. Five is
# the point at which one unlucky run stops being the whole answer.
MIN_SAMPLE = 5

# Gate decisions needed on a node type before its revision rate is called a verdict.
# The raw counts are always honest; a *rate* off two decisions is not.
MIN_GATE_SAMPLE = 5

# A node type is flagged when it is sent back at least this often. Half is the line
# that matters: a stage you disagree with more than you agree with is not a stage you
# are reviewing, it is a stage you are rewriting.
REVISE_ALARM = 0.5


def _naive(value: datetime | None) -> datetime | None:
    """Drop the offset so two timestamps can always be subtracted.

    `created_at` and `finished_at` are both `DateTime(timezone=True)`, but SQLite
    hands back naive datetimes while Postgres hands back aware ones, and a row written
    by one and read after a migration to the other mixes the two. Subtracting a naive
    from an aware datetime raises, which would take the whole page down over a
    formatting detail.
    """
    if value is None:
        return None
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def _elapsed_seconds(run: Run) -> float | None:
    """Wall clock from being asked for to being finished.

    Deliberately not the sum of node durations. The gaps are the honest part of this
    number: a run that spent two days waiting at the script gate took two days, and
    a figure that hides that is useless for answering "when will it be ready".
    """
    start, end = _naive(run.created_at), _naive(run.finished_at)
    if start is None or end is None:
        return None
    seconds = (end - start).total_seconds()
    return seconds if seconds >= 0 else None


def human_duration(seconds: float | None) -> str:
    """Formatted here rather than in the template, so the units can be chosen.

    Nine seconds and nine hours want different units, and a Jinja filter that picks
    one for both prints either "0.0h" or "32400s".
    """
    if seconds is None:
        return "—"
    seconds = round(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60:02d}s"
    hours, rest = divmod(seconds, 3600)
    if hours < 48:
        return f"{hours}h {rest // 60:02d}m"
    return f"{hours // 24}d {hours % 24}h"


def _bar(value: float, largest: float) -> float:
    """A bar width in percent, scaled to the biggest row rather than to the total.

    Scaling to the total is what makes every bar on a twelve-stage breakdown a stub.
    The comparison that matters is against the worst offender, and an empty account
    has a largest of zero — hence the guard, which is the division this page would
    otherwise die on.
    """
    if largest <= 0:
        return 0.0
    return round(max(0.0, value) / largest * 100, 2)


def spend_report(session: Session, user: User) -> dict:
    """Net credits spent, per run and per node type, from the ledger.

    Both cuts come out of one pass on purpose. The per-video cost on a channel and the
    stage breakdown across the account are the same credits counted two ways, and
    computing them from two different sources — the ledger for one, `Run.credits_spent`
    for the other — is how the two halves of this page end up disagreeing about what a
    video cost.

    The ledger rather than the row counters, and net of refunds, because those are the
    same fact: `refund_node` hands the credits back and decrements the run, but never
    the node's own counter. Summing node rows bills you for output a provider was
    already refunded for returning garbage, and the stage that fails most often is the
    one that overstates worst.
    """
    movements = session.execute(
        select(LedgerEntry.run_id, LedgerEntry.node_key, LedgerEntry.kind,
               LedgerEntry.delta)
        .where(
            LedgerEntry.user_id == user.id,
            LedgerEntry.kind.in_([LedgerKind.spend, LedgerKind.refund]),
        )
    ).all()
    if not movements:
        return {"by_run": {}, "by_stage": []}

    # The ledger stores a node *key*, and a key is not a type — two shot-generating
    # nodes in one pipeline have distinct keys. Resolved through the node rows, which
    # are the only place that mapping lives.
    keyed_types = {
        (run_id, key): node_type
        for run_id, key, node_type in session.execute(
            select(Node.run_id, Node.key, Node.type)
            .join(Run, Node.run_id == Run.id)
            .where(Run.user_id == user.id)
        ).all()
    }

    by_run: Counter[int] = Counter()
    by_stage: Counter[str] = Counter()
    for run_id, node_key, kind, delta in movements:
        # A spend whose run has since been deleted keeps its key but loses its node.
        # Reporting the key beats dropping the credits, which would make the breakdown
        # quietly stop adding up to the total.
        label = keyed_types.get((run_id, node_key)) or node_key or "unattributed"
        signed = -abs(int(delta)) if kind is LedgerKind.refund else abs(int(delta))
        by_stage[label] += signed
        if run_id is not None:
            by_run[run_id] += signed

    # A stage refunded more than it ever spent would otherwise draw a negative bar.
    net = {node_type: total for node_type, total in by_stage.items() if total > 0}
    grand = sum(net.values())
    largest = max(net.values(), default=0)
    stages = [
        {"node_type": node_type, "credits": credits,
         "share": round(credits / grand * 100, 1) if grand else 0.0,
         "bar": _bar(credits, largest)}
        for node_type, credits in sorted(
            net.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {"by_run": {run_id: max(0, total) for run_id, total in by_run.items()},
            "by_stage": stages}


def channel_rows(session: Session, user: User, spend_by_run: dict[int, int]) -> list[dict]:
    """Per channel: what it starts, what it finishes, where it dies, and the cost.

    One query for the runs and one for the failed nodes. Asking per channel would be
    a query per row, which is fine at three channels and not at fifty.
    """
    channels = session.execute(
        select(Channel).where(Channel.user_id == user.id).order_by(Channel.id)
    ).scalars().all()
    runs = session.execute(
        select(Run).where(Run.user_id == user.id).order_by(Run.id)
    ).scalars().all()

    # Which stage the failed runs failed at. Read off the node rather than the run:
    # `run.error` is the message, and the message is not a node type.
    failed_stage: dict[int, str] = {}
    failed_ids = [run.id for run in runs if run.status is RunStatus.failed]
    if failed_ids:
        for run_id, node_type in session.execute(
            select(Node.run_id, Node.type)
            .where(Node.run_id.in_(failed_ids), Node.status == NodeStatus.failed)
            .order_by(Node.id)
        ).all():
            failed_stage.setdefault(run_id, node_type)

    by_channel: dict[int, list[Run]] = {}
    for run in runs:
        by_channel.setdefault(run.channel_id, []).append(run)

    rows: list[dict] = []
    for channel in channels:
        mine = by_channel.get(channel.id, [])
        completed = [run for run in mine if run.status is RunStatus.completed]
        failed = [run for run in mine if run.status is RunStatus.failed]
        cancelled = [run for run in mine if run.status is RunStatus.cancelled]

        durations = [
            seconds for seconds in (_elapsed_seconds(run) for run in completed)
            if seconds is not None
        ]
        spent = sum(spend_by_run.get(run.id, 0) for run in completed)
        enough = len(completed) >= MIN_SAMPLE

        deaths = Counter(
            failed_stage.get(run.id, "unknown") for run in failed
        )
        in_flight = len(mine) - len(completed) - len(failed) - len(cancelled)
        rows.append({
            "id": channel.id,
            "name": channel.name,
            "format": formats.get(formats.format_of_channel(channel)).label,
            "started": len(mine),
            "completed": len(completed),
            "failed": len(failed),
            "cancelled": len(cancelled),
            "in_flight": in_flight,
            "complete_pct": _bar(len(completed), len(mine)),
            # Which of the shared status colours the channel's tally earns. Decided
            # here rather than in the template so that "any failure at all" cannot
            # quietly become the rule: a channel with six finished videos and one dead
            # run is not a failing channel, and colouring it red says it is.
            #
            # Ordered by what is most worth knowing, which is why work in flight comes
            # first. The mixed case has to be handled explicitly — falling through to
            # "queued" labelled a channel with five finished videos and one dead run
            # with a state it was not in, and greyed it out for having shipped.
            "health": ("running" if in_flight
                       else "completed" if completed
                       else "failed" if failed
                       else "queued"),
            # Withheld rather than rounded below the sample floor. `enough` is what
            # the template branches on so the reason travels with the gap.
            "enough": enough,
            "median_seconds": median(durations) if enough and durations else None,
            "median_label": human_duration(
                median(durations) if enough and durations else None),
            "credits_per_video": round(spent / len(completed), 1) if enough else None,
            "credits_spent": spent,
            "deaths": [
                {"node_type": node_type, "count": count}
                for node_type, count in deaths.most_common()
            ],
        })
    return rows


def gate_rows(session: Session, user: User) -> list[dict]:
    """Approved versus sent back, per node type.

    The one measurement nothing else in the app surfaces, and the one most likely to
    change what you do: a stage you revise more often than you accept is a prompt to
    fix, not a stage to keep babysitting.
    """
    decisions = session.execute(
        select(ChannelMemory.node_type, ChannelMemory.kind)
        .join(Channel, ChannelMemory.channel_id == Channel.id)
        .where(
            Channel.user_id == user.id,
            ChannelMemory.kind.in_([MemoryKind.decision, MemoryKind.revision]),
        )
    ).all()

    approved: Counter[str] = Counter()
    revised: Counter[str] = Counter()
    for node_type, kind in decisions:
        target = revised if kind is MemoryKind.revision else approved
        target[node_type or "unknown"] += 1

    rows: list[dict] = []
    for node_type in sorted(set(approved) | set(revised)):
        passes, sendbacks = approved[node_type], revised[node_type]
        total = passes + sendbacks
        rate = sendbacks / total if total else 0.0
        rows.append({
            "node_type": node_type,
            "approved": passes,
            "revised": sendbacks,
            "total": total,
            "revise_pct": round(rate * 100),
            "approved_bar": _bar(passes, total),
            "revised_bar": _bar(sendbacks, total),
            # Counts are printed at any sample size; the verdict waits for one.
            "reliable": total >= MIN_GATE_SAMPLE,
            "needs_work": total >= MIN_GATE_SAMPLE and rate >= REVISE_ALARM,
        })
    # Worst *readable* rate first. Sorting on the rate alone floats a stage with one
    # send-back and no approvals to the top at 100%, which puts the least trustworthy
    # row where the eye lands and buries the stage actually costing you afternoons.
    rows.sort(key=lambda row: (row["reliable"], row["revise_pct"], row["revised"]),
              reverse=True)
    return rows


def report(session: Session, user: User) -> dict:
    """Everything the page shows, in one call the tests can check by hand."""
    spend = spend_report(session, user)
    channels = channel_rows(session, user, spend["by_run"])
    credits = spend["by_stage"]
    gates = gate_rows(session, user)

    started = sum(row["started"] for row in channels)
    completed = sum(row["completed"] for row in channels)
    failed = sum(row["failed"] for row in channels)
    spent = sum(row["credits"] for row in credits)

    # The account-wide median is computed over every finished run rather than averaged
    # from the per-channel medians, which would weight a channel with one run the same
    # as a channel with forty.
    finished = session.execute(
        select(Run).where(Run.user_id == user.id, Run.status == RunStatus.completed)
    ).scalars().all()
    durations = [
        seconds for seconds in (_elapsed_seconds(run) for run in finished)
        if seconds is not None
    ]
    enough = len(finished) >= MIN_SAMPLE

    return {
        "channels": channels,
        "credit_rows": credits,
        "gates": gates,
        "totals": {
            "started": started,
            "completed": completed,
            "failed": failed,
            "credits_spent": spent,
            "enough": enough,
            "sample_floor": MIN_SAMPLE,
            "median_label": human_duration(
                median(durations) if enough and durations else None),
            "credits_per_video": round(spent / len(finished), 1) if enough else None,
            "completion_pct": round(completed / started * 100) if started else 0,
        },
    }


@router.get("/analytics", response_class=HTMLResponse)
def analytics_page(
    request: Request, session: Session = Depends(get_session),
) -> HTMLResponse:
    from .routes_web import TEMPLATES, shell

    user = optional_user(request, session)
    if user is None:
        return RedirectResponse("/login?next=/analytics", 303)  # type: ignore[return-value]

    return TEMPLATES.TemplateResponse(
        request,
        "analytics.html",
        {**shell(session, user, "analytics"), **report(session, user)},
    )
