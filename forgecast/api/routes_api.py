"""JSON API.

Ownership is enforced in one place — `_owned_channel` / `_owned_run` — because every
row in this system belongs to exactly one user and a missed check is a data leak.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import credits as billing
from ..auth import authenticate, create_access_token, current_user, hash_password
from ..config import get_settings
from ..crypto import encrypt, fingerprint, mask
from ..db import get_session
from ..graph.engine import create_run
from ..graph.pipelines import PIPELINE_META, get_pipeline
from ..models import (
    Artifact,
    Channel,
    LedgerEntry,
    Node,
    NodeStatus,
    Plan,
    ProviderKey,
    Run,
    RunEvent,
    RunStatus,
    User,
)
from ..providers.registry import CATALOGUE
from . import runner
from .media import sign_url
from .schemas import (
    ArtifactOut,
    ChannelIn,
    ChannelOut,
    CreditsOut,
    EstimateOut,
    EventOut,
    GateIn,
    LoginIn,
    NodeOut,
    ProviderKeyIn,
    ProviderKeyOut,
    RunIn,
    RunOut,
    SignupIn,
    TokenOut,
    UserOut,
)

router = APIRouter(prefix="/api", tags=["api"])


# ------------------------------------------------------------------------ helpers


def _owned_channel(session: Session, channel_id: int, user: User) -> Channel:
    channel = session.get(Channel, channel_id)
    if channel is None or channel.user_id != user.id:
        raise HTTPException(status_code=404, detail="channel not found")
    return channel


def _owned_run(session: Session, run_id: int, user: User) -> Run:
    run = session.get(Run, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(status_code=404, detail="run not found")
    return run


def artifact_url(path: str | Path, user_id: int) -> str | None:
    """A signed, expiring URL for this user. See `api.media` for why it is signed."""
    return sign_url(path, user_id)


def serialise_run(session: Session, run: Run) -> RunOut:
    node_keys = {node.id: node.key for node in run.nodes}
    artifacts = session.execute(
        select(Artifact).where(Artifact.run_id == run.id).order_by(Artifact.id)
    ).scalars().all()
    return RunOut(
        id=run.id,
        channel_id=run.channel_id,
        topic=run.topic,
        pipeline=run.pipeline,
        status=run.status.value,
        credits_reserved=run.credits_reserved,
        credits_spent=run.credits_spent,
        error=run.error,
        created_at=run.created_at,
        finished_at=run.finished_at,
        nodes=[
            NodeOut(
                id=node.id,
                key=node.key,
                type=node.type,
                title=node.title,
                status=node.status.value,
                depends_on=list(node.depends_on or []),
                requires_approval=node.requires_approval,
                attempts=node.attempts,
                credits_spent=node.credits_spent,
                error=node.error,
                output=node.output or {},
                review_feedback=node.review_feedback,
            )
            for node in run.nodes
        ],
        artifacts=[
            ArtifactOut(
                id=a.id,
                kind=a.kind,
                mime=a.mime,
                size_bytes=a.size_bytes,
                node_key=node_keys.get(a.node_id or -1),
                url=artifact_url(a.path, run.user_id),
                meta=a.meta or {},
            )
            for a in artifacts
        ],
    )


# --------------------------------------------------------------------------- auth


@router.post("/auth/signup", response_model=TokenOut, status_code=201)
def signup(payload: SignupIn, session: Session = Depends(get_session)) -> TokenOut:
    if not get_settings().allow_signup:
        raise HTTPException(
            status_code=403,
            detail="registration is closed on this instance; the owner creates "
                   "accounts with `forgecast bootstrap`",
        )
    email = payload.email.strip().lower()
    if session.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="email already registered")
    user = User(email=email, hashed_password=hash_password(payload.password))
    session.add(user)
    session.flush()
    settings = get_settings()
    if settings.signup_credit_grant:
        billing.grant(
            session, user.id, settings.signup_credit_grant,
            note="signup grant", idempotency_key=f"signup:{user.id}",
        )
    session.commit()
    return TokenOut(access_token=create_access_token(user))


@router.post("/auth/login", response_model=TokenOut)
def login(payload: LoginIn, session: Session = Depends(get_session)) -> TokenOut:
    user = authenticate(session, payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid email or password")
    return TokenOut(access_token=create_access_token(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user), session: Session = Depends(get_session)) -> UserOut:
    return UserOut(
        id=user.id, email=user.email, plan=user.plan.value,
        credits=billing.balance(session, user.id),
    )


# ------------------------------------------------------------------------ channels


@router.get("/channels", response_model=list[ChannelOut])
def list_channels(
    user: User = Depends(current_user), session: Session = Depends(get_session)
) -> list[ChannelOut]:
    rows = session.execute(
        select(Channel).where(Channel.user_id == user.id).order_by(Channel.id)
    ).scalars().all()
    return [_channel_out(channel) for channel in rows]


@router.post("/channels", response_model=ChannelOut, status_code=201)
def create_channel(
    payload: ChannelIn,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> ChannelOut:
    channel = Channel(user_id=user.id, **payload.model_dump())
    session.add(channel)
    session.commit()
    return _channel_out(channel)


@router.patch("/channels/{channel_id}", response_model=ChannelOut)
def update_channel(
    channel_id: int,
    payload: ChannelIn,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> ChannelOut:
    channel = _owned_channel(session, channel_id, user)
    for field, value in payload.model_dump().items():
        setattr(channel, field, value)
    session.commit()
    return _channel_out(channel)


def _channel_out(channel: Channel) -> ChannelOut:
    return ChannelOut(
        id=channel.id,
        name=channel.name,
        niche=channel.niche,
        language=channel.language,
        voice_id=channel.voice_id,
        avatar_id=channel.avatar_id,
        aspect_ratio=channel.aspect_ratio,
        target_duration_seconds=channel.target_duration_seconds,
        style_profile=channel.style_profile or {},
        youtube_connected=bool(channel.youtube_credentials),
        created_at=channel.created_at,
    )


# ----------------------------------------------------------------------- pipelines


@router.get("/pipelines")
def list_pipelines() -> list[dict]:
    return PIPELINE_META


@router.get("/pipelines/{name}/estimate", response_model=EstimateOut)
def estimate_pipeline(
    name: str,
    target_seconds: int = Query(480, ge=15, le=3600),
    use_avatar: bool = False,
    standard_model: str = "",
    hero_model: str = "",
) -> EstimateOut:
    """What a run will cost before committing to it.

    The two model slugs are worth passing, and they are the channel's `video_model` and
    `video_model_hero`. Two of these nodes are priced by the image-to-video endpoint the
    channel chose, and the ones it can choose between span a seven-fold range — so
    without them this answers for the default, and an estimate quoting a different model
    from the one the run will reserve against is worse than no estimate.

    They are query parameters rather than a `channel_id` so this stays open: it is a price
    list, it reads nothing belonging to anyone, and requiring a session to ask what a
    video costs is a sign-up wall in front of the answer that decides whether to sign up.
    """
    try:
        spec = get_pipeline(name, target_seconds=target_seconds, use_avatar=use_avatar,
                            standard_model=standard_model, hero_model=hero_model)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    per_node = []
    total = 0
    for node_spec in spec.topological_order():
        estimate = billing.estimate_node(
            node_spec.type, node_spec.estimated_units, priced=node_spec.estimated_credits
        )
        total += estimate.credits
        per_node.append(
            {
                "key": node_spec.key,
                "title": node_spec.title,
                "gate": node_spec.requires_approval,
                **estimate.as_dict(),
            }
        )
    return EstimateOut(
        pipeline=spec.name,
        total_credits=total,
        total_usd=billing.credits_to_usd(total),
        per_node=per_node,
    )


# ---------------------------------------------------------------------------- runs


@router.post("/runs", response_model=RunOut, status_code=201)
def start_run(
    payload: RunIn,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> RunOut:
    channel = _owned_channel(session, payload.channel_id, user)
    try:
        run = create_run(
            session, channel=channel, topic=payload.topic,
            pipeline=payload.pipeline, options=payload.options,
        )
    except billing.InsufficientCredits as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={"error": "insufficient_credits", "needed": exc.needed,
                    "available": exc.available},
        ) from exc
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session.commit()
    out = serialise_run(session, run)
    runner.schedule(run.id)
    return out


@router.get("/runs", response_model=list[RunOut])
def list_runs(
    channel_id: int | None = None,
    limit: int = Query(25, ge=1, le=100),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[RunOut]:
    stmt = select(Run).where(Run.user_id == user.id)
    if channel_id is not None:
        stmt = stmt.where(Run.channel_id == channel_id)
    rows = session.execute(stmt.order_by(Run.id.desc()).limit(limit)).scalars().all()
    return [serialise_run(session, run) for run in rows]


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(
    run_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> RunOut:
    return serialise_run(session, _owned_run(session, run_id, user))


@router.post("/runs/{run_id}/nodes/{node_key}/gate", response_model=RunOut)
def decide_gate(
    run_id: int,
    node_key: str,
    payload: GateIn,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> RunOut:
    """Approve a gate, or reject it with `feedback` to re-run with instructions."""
    run = _owned_run(session, run_id, user)
    node = session.execute(
        select(Node).where(Node.run_id == run.id, Node.key == node_key)
    ).scalar_one_or_none()
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")

    engine = runner.engine()
    try:
        if payload.feedback:
            engine.revise(session, node, payload.feedback)
        else:
            engine.approve(session, node, note=payload.note, overrides=payload.overrides)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    session.commit()
    out = serialise_run(session, run)
    runner.schedule(run.id)
    return out


@router.post("/runs/{run_id}/cancel", response_model=RunOut)
def cancel_run(
    run_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> RunOut:
    run = _owned_run(session, run_id, user)
    if run.is_terminal:
        raise HTTPException(status_code=409, detail=f"run already {run.status.value}")
    runner.engine().cancel(session, run)
    session.commit()
    return serialise_run(session, run)


@router.post("/runs/{run_id}/retry", response_model=RunOut)
def retry_run(
    run_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> RunOut:
    """Re-queue a failed run: reset the failed nodes, keep completed work."""
    run = _owned_run(session, run_id, user)
    if run.status is not RunStatus.failed:
        raise HTTPException(status_code=409, detail="only failed runs can be retried")
    for node in run.nodes:
        if node.status is NodeStatus.failed:
            node.status = NodeStatus.pending
            node.attempts = 0
            node.error = None
    run.status = RunStatus.queued
    run.error = None
    run.finished_at = None
    session.commit()
    runner.schedule(run.id)
    return serialise_run(session, run)


@router.get("/runs/{run_id}/events", response_model=list[EventOut])
def run_events(
    run_id: int,
    after_id: int = 0,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[EventOut]:
    run = _owned_run(session, run_id, user)
    rows = session.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run.id, RunEvent.id > after_id)
        .order_by(RunEvent.id)
    ).scalars().all()
    return [
        EventOut(
            id=e.id, node_key=e.node_key, level=e.level, message=e.message,
            data=e.data or {}, created_at=e.created_at,
        )
        for e in rows
    ]


@router.get("/runs/{run_id}/stream")
async def stream_run(
    run_id: int,
    since: int = 0,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """Server-sent events: node status changes and log lines as they happen.

    Polling the events table is not elegant, but it is correct across multiple
    workers and needs no message bus. Swap for LISTEN/NOTIFY on Postgres later.

    `since` is the last event id the caller already has. Without it the stream starts
    from zero and replays the whole log — which the page has already rendered, so every
    line appeared twice, and appeared again on each of EventSource's automatic
    reconnects. A long run's log is thousands of lines, so this is bandwidth as well as
    a visible defect. The client also de-duplicates by id, because correctness here
    should not depend on the caller passing the parameter.
    """
    run = _owned_run(session, run_id, user)
    run_id = run.id
    from ..db import session_scope

    async def publish():
        last_event = max(0, int(since))
        last_snapshot = ""
        deadline = datetime.now(UTC).timestamp() + 1800
        while datetime.now(UTC).timestamp() < deadline:
            terminal = False
            with session_scope() as scoped:
                events = scoped.execute(
                    select(RunEvent)
                    .where(RunEvent.run_id == run_id, RunEvent.id > last_event)
                    .order_by(RunEvent.id)
                ).scalars().all()
                for event in events:
                    last_event = event.id
                    yield _sse(
                        "log",
                        {
                            "id": event.id,
                            "node_key": event.node_key,
                            "level": event.level,
                            "message": event.message,
                        },
                    )

                current = scoped.get(Run, run_id)
                snapshot = {
                    "status": current.status.value,
                    "credits_spent": current.credits_spent,
                    "nodes": {n.key: n.status.value for n in current.nodes},
                }
                encoded = json.dumps(snapshot, sort_keys=True)
                if encoded != last_snapshot:
                    last_snapshot = encoded
                    yield _sse("state", snapshot)
                terminal = current.is_terminal

            if terminal:
                yield _sse("done", {"status": snapshot["status"]})
                return
            await asyncio.sleep(1.0)

    return StreamingResponse(
        publish(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ------------------------------------------------------------------- provider keys


@router.get("/provider-keys", response_model=list[ProviderKeyOut])
def list_provider_keys(
    user: User = Depends(current_user), session: Session = Depends(get_session)
) -> list[ProviderKeyOut]:
    rows = session.execute(
        select(ProviderKey).where(ProviderKey.user_id == user.id).order_by(ProviderKey.provider)
    ).scalars().all()
    return [
        ProviderKeyOut(
            id=r.id, provider=r.provider, masked=r.masked,
            fingerprint=r.fingerprint, created_at=r.created_at,
        )
        for r in rows
    ]


@router.put("/provider-keys", response_model=ProviderKeyOut)
def upsert_provider_key(
    payload: ProviderKeyIn,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> ProviderKeyOut:
    known = {entry[2] for entry in CATALOGUE.values()}
    if payload.provider not in known:
        raise HTTPException(
            status_code=400, detail=f"unknown provider; expected one of {sorted(known)}"
        )
    row = session.execute(
        select(ProviderKey).where(
            ProviderKey.user_id == user.id, ProviderKey.provider == payload.provider
        )
    ).scalar_one_or_none()
    if row is None:
        row = ProviderKey(user_id=user.id, provider=payload.provider)
        session.add(row)
    row.ciphertext = encrypt(payload.api_key)
    row.masked = mask(payload.api_key)
    row.fingerprint = fingerprint(payload.api_key)
    session.commit()
    return ProviderKeyOut(
        id=row.id, provider=row.provider, masked=row.masked,
        fingerprint=row.fingerprint, created_at=row.created_at,
    )


@router.delete("/provider-keys/{provider}", status_code=204)
def delete_provider_key(
    provider: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> None:
    row = session.execute(
        select(ProviderKey).where(
            ProviderKey.user_id == user.id, ProviderKey.provider == provider
        )
    ).scalar_one_or_none()
    if row is not None:
        session.delete(row)
        session.commit()


# ------------------------------------------------------------------------- credits


@router.get("/credits", response_model=CreditsOut)
def get_credits(
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
    limit: int = Query(50, ge=1, le=200),
) -> CreditsOut:
    balance = billing.balance(session, user.id)
    rows = session.execute(
        select(LedgerEntry)
        .where(LedgerEntry.user_id == user.id)
        .order_by(LedgerEntry.id.desc())
        .limit(limit)
    ).scalars().all()
    return CreditsOut(
        balance=balance,
        balance_usd=billing.credits_to_usd(balance),
        plan=user.plan.value,
        entries=[
            {
                "id": r.id,
                "kind": r.kind.value,
                "delta": r.delta,
                "balance_after": r.balance_after,
                "run_id": r.run_id,
                "node_key": r.node_key,
                "note": r.note,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
    )


@router.post("/credits/purchase", response_model=CreditsOut)
def purchase_credits(
    amount: int = Query(..., ge=100, le=1_000_000),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> CreditsOut:
    """Dev-only top-up.

    A real deployment must not expose this: credits may only be minted by a
    verified payment webhook (Stripe `checkout.session.completed`), never by a
    request the browser can make. See ARCHITECTURE.md, "Billing".
    """
    if not get_settings().is_mock:
        raise HTTPException(
            status_code=403,
            detail="direct credit purchase is disabled outside mock mode — wire Stripe",
        )
    billing.purchase(session, user.id, amount, note="dev top-up")
    session.commit()
    return get_credits(user=user, session=session)


@router.get("/plans")
def list_plans() -> list[dict]:
    from ..models import PLAN_MONTHLY_CREDITS

    prices = {Plan.free: 0, Plan.pro: 49, Plan.studio: 149, Plan.max: 649}
    return [
        {
            "plan": plan.value,
            "monthly_credits": monthly,
            "usd_per_month": prices[plan],
            "usd_per_credit": round(prices[plan] / monthly, 5) if monthly else None,
        }
        for plan, monthly in PLAN_MONTHLY_CREDITS.items()
    ]
