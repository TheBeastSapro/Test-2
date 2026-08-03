"""Server-rendered UI.

Jinja templates and form posts, no build step. The node graph is drawn from the same
`depends_on` data the engine executes, so the picture cannot drift from the pipeline.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import credits as billing
from ..auth import authenticate, create_access_token, current_user, hash_password, optional_user
from ..config import get_settings
from ..db import get_session
from ..graph import formats
from ..graph.engine import create_run
from ..graph.pipelines import PIPELINE_META
from ..models import Channel, Node, Run, RunEvent, User
from ..render.ffmpeg import ffmpeg_available
from . import runner
from .routes_api import _owned_run, artifact_url

router = APIRouter(include_in_schema=False)
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "web"))
# Exposed as a template global rather than passed per-route: every page wants to warn
# about a missing ffmpeg, and threading it through each context is how one page ends up
# silently not warning.
TEMPLATES.env.globals["ffmpeg_ok"] = ffmpeg_available

COOKIE = "forgecast_session"


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def shell(
    session: Session, user: User, nav: str, *,
    channels: list | None = None, runs: list | None = None,
) -> dict:
    """The context every page shares: the format tabs, the nav state, the run list.

    Built in one place rather than per route. The sidebar is on every page, so a route
    that forgot to supply it would render an app with no navigation — a failure that is
    obvious in the browser and invisible in a test that only checks status codes.

    A caller that has already loaded the channels and runs passes them in; the counts
    on the tabs are the same query the workspace just ran, and running it twice on
    every page load is waste for no gain.
    """
    if runs is None:
        runs = list(session.execute(
            select(Run).where(Run.user_id == user.id).order_by(Run.id.desc()).limit(60)
        ).scalars().all())
    if channels is None:
        channels = list(session.execute(
            select(Channel).where(Channel.user_id == user.id)
        ).scalars().all())

    return {
        "nav": nav,
        "recent_runs": runs[:8],
        "formats": list(formats.FORMATS.values()),
        "format_counts": formats.counts(channels, runs),
        "credits": billing.balance(session, user.id),
        "settings": get_settings(),
        "user": user,
    }


def _set_session(response: RedirectResponse, token: str) -> RedirectResponse:
    response.set_cookie(
        COOKIE, token, httponly=True, samesite="lax",
        secure=not get_settings().base_url.startswith("http://"),
        max_age=get_settings().access_token_ttl_minutes * 60,
    )
    return response


# --------------------------------------------------------------------------- auth


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str = "") -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request, "login.html", {"error": error, "settings": get_settings()}
    )


@router.post("/login")
def login_submit(
    email: str = Form(...),
    password: str = Form(...),
    action: str = Form("login"),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    if action == "signup":
        if not get_settings().allow_signup:
            return _redirect("/login?error=Registration+is+closed+on+this+instance")
        existing = session.execute(
            select(User).where(User.email == email.strip().lower())
        ).scalar_one_or_none()
        if existing is not None:
            return _redirect("/login?error=That+email+is+already+registered")
        if len(password) < 8:
            return _redirect("/login?error=Password+must+be+at+least+8+characters")
        user = User(email=email.strip().lower(), hashed_password=hash_password(password))
        session.add(user)
        session.flush()
        grant = get_settings().signup_credit_grant
        if grant:
            billing.grant(session, user.id, grant, note="signup grant",
                          idempotency_key=f"signup:{user.id}")
        session.commit()
    else:
        user = authenticate(session, email, password)
        if user is None:
            return _redirect("/login?error=Invalid+email+or+password")

    return _set_session(_redirect("/"), create_access_token(user))


@router.post("/logout")
def logout() -> RedirectResponse:
    response = _redirect("/login")
    response.delete_cookie(COOKIE)
    return response


# ---------------------------------------------------------------------- dashboard


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    model_on: str = "",
    fmt: str = "",
    user: User | None = Depends(optional_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """The app opens on the chat, because that is the way in.

    It used to open on a workspace of forms — a table of channels, a form to add one,
    a form to start a run. That is where you go to *look* at what happened. It is not
    where the work starts, because the work starts with something you can say in a
    sentence and would have to translate into eight fields.

    The format workspaces are still one click away at `/f/{slug}`, and the sidebar
    remembers which one has your runs in it.
    """
    if user is None:
        return _redirect("/login")  # type: ignore[return-value]

    # A link handed over from the workspace's "model it on a channel" field. It opens
    # a fresh thread and asks the question for you, so pasting a link is one action
    # rather than "copy it, switch tab, paste it again, phrase the request".
    opening = ""
    if model_on.strip():
        shape = formats.get(fmt) if fmt else formats.get(formats.DEFAULT_FORMAT)
        opening = (
            f"Set up a {shape.label.lower()} channel modelled on "
            f"{model_on.strip()} — read what they actually publish first and show me "
            f"what you measured before creating anything."
        )

    return TEMPLATES.TemplateResponse(
        request, "chat.html", {**shell(session, user, "chat"), "opening": opening}
    )


@router.get("/f/{slug}", response_class=HTMLResponse)
def workspace(
    slug: str,
    request: Request,
    user: User | None = Depends(optional_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """One format's workspace: its channels, its runs, its pipeline pre-chosen."""
    if user is None:
        return _redirect("/login")  # type: ignore[return-value]

    chosen = formats.get(slug)
    channels = session.execute(
        select(Channel).where(Channel.user_id == user.id).order_by(Channel.id)
    ).scalars().all()
    runs = session.execute(
        select(Run).where(Run.user_id == user.id).order_by(Run.id.desc()).limit(60)
    ).scalars().all()

    return TEMPLATES.TemplateResponse(
        request,
        "dashboard.html",
        {
            **shell(session, user, f"format:{chosen.slug}", channels=channels, runs=runs),
            "format": chosen,
            "channels": formats.channels_in(channels, chosen.slug),
            "other_channels": [
                item for item in channels
                if formats.format_of_channel(item) != chosen.slug
            ],
            "runs": formats.runs_in(runs, chosen.slug)[:20],
            "pipelines": PIPELINE_META,
            # A topic handed over from the research desk, so "start a run from this
            # idea" lands on a pre-filled form rather than an empty one.
            "topic": request.query_params.get("topic", ""),
        },
    )


@router.post("/channels")
def create_channel_form(
    name: str = Form(...),
    niche: str = Form(""),
    voice_id: str = Form(""),
    avatar_id: str = Form(""),
    aspect_ratio: str = Form("16:9"),
    target_duration_seconds: int = Form(480),
    tone: str = Form(""),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    channel = Channel(
        user_id=user.id,
        name=name.strip(),
        niche=niche.strip(),
        voice_id=voice_id.strip(),
        avatar_id=avatar_id.strip(),
        aspect_ratio=aspect_ratio,
        target_duration_seconds=max(15, min(3600, target_duration_seconds)),
        style_profile={"tone": tone.strip()} if tone.strip() else {},
    )
    session.add(channel)
    session.commit()
    # Back to the workspace the new channel belongs to, which is not necessarily the
    # one it was created from — a vertical channel made on the long-form tab is a
    # Shorts channel, and landing on the tab that will not list it reads as a failure.
    return _redirect(f"/f/{formats.format_of_channel(channel)}")


@router.post("/runs")
def create_run_form(
    channel_id: int = Form(...),
    topic: str = Form(...),
    pipeline: str = Form("faceless_longform"),
    target_seconds: int = Form(0),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    channel = session.get(Channel, channel_id)
    if channel is None or channel.user_id != user.id:
        raise HTTPException(status_code=404, detail="channel not found")

    options = {"target_seconds": target_seconds} if target_seconds else {}
    try:
        run = create_run(
            session, channel=channel, topic=topic, pipeline=pipeline, options=options
        )
    except billing.InsufficientCredits as exc:
        slug = formats.format_of_pipeline(pipeline)
        return _redirect(
            f"/f/{slug}?error=Not+enough+credits:+need+{exc.needed},+have+{exc.available}"
        )
    session.commit()
    runner.schedule(run.id)
    return _redirect(f"/runs/{run.id}")


# ---------------------------------------------------------------------- run detail


@router.get("/runs/{run_id}", response_class=HTMLResponse)
def run_page(
    run_id: int,
    request: Request,
    user: User | None = Depends(optional_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    if user is None:
        return _redirect("/login")  # type: ignore[return-value]
    run = _owned_run(session, run_id, user)

    layers = _layout(list(run.nodes))
    events = session.execute(
        select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.id)
    ).scalars().all()

    artifacts = []
    node_keys = {node.id: node.key for node in run.nodes}
    for artifact in run.artifacts:
        artifacts.append(
            {
                "kind": artifact.kind,
                "node_key": node_keys.get(artifact.node_id or -1, ""),
                "url": artifact_url(artifact.path, user.id),
                "size_mb": artifact.size_bytes / 1_048_576,
                "meta": artifact.meta or {},
            }
        )

    gate = next((n for n in run.nodes if n.status.value == "awaiting_approval"), None)
    return TEMPLATES.TemplateResponse(
        request,
        "run.html",
        {
            **shell(session, user, "run"),
            "run": run,
            "layers": layers,
            "events": events,
            "artifacts": artifacts,
            "gate": gate,
            "usd": billing.credits_to_usd,
        },
    )


@router.post("/runs/{run_id}/gate/{node_key}")
def gate_form(
    run_id: int,
    node_key: str,
    decision: str = Form("approve"),
    feedback: str = Form(""),
    title: str = Form(""),
    privacy_status: str = Form(""),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    run = _owned_run(session, run_id, user)
    node = session.execute(
        select(Node).where(Node.run_id == run.id, Node.key == node_key)
    ).scalar_one_or_none()
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")

    engine = runner.engine()
    try:
        if decision == "revise":
            engine.revise(session, node, feedback or "please try a different approach")
        else:
            # Let the operator edit publish metadata at the final gate.
            overrides: dict = {}
            if node.type == "final_review" and (title or privacy_status):
                metadata = dict((node.output or {}).get("metadata") or {})
                if title:
                    metadata["title"] = title[:100]
                if privacy_status:
                    metadata["privacy_status"] = privacy_status
                overrides["metadata"] = metadata
            engine.approve(session, node, overrides=overrides or None)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    session.commit()
    runner.schedule(run.id)
    return _redirect(f"/runs/{run_id}")


@router.post("/runs/{run_id}/cancel")
def cancel_form(
    run_id: int,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    run = _owned_run(session, run_id, user)
    if not run.is_terminal:
        runner.engine().cancel(session, run)
        session.commit()
    return _redirect(f"/runs/{run_id}")


def _layout(nodes: list[Node]) -> list[list[Node]]:
    """Group nodes into dependency layers — one column per layer in the graph view."""
    by_key = {node.key: node for node in nodes}
    depth: dict[str, int] = {}

    def resolve(key: str, seen: frozenset[str] = frozenset()) -> int:
        if key in depth:
            return depth[key]
        node = by_key.get(key)
        if node is None or key in seen:
            return 0
        deps = [d for d in (node.depends_on or []) if d in by_key]
        value = 0 if not deps else 1 + max(resolve(d, seen | {key}) for d in deps)
        depth[key] = value
        return value

    for node in nodes:
        resolve(node.key)

    layers: dict[int, list[Node]] = {}
    for node in nodes:
        layers.setdefault(depth.get(node.key, 0), []).append(node)
    return [layers[index] for index in sorted(layers)]
