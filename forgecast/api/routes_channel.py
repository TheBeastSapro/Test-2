"""One channel as a place in the app, rather than a row in somebody else's table.

## Why this page exists

Every entry in the rail is the account: Studio, the two format workspaces, Research,
Styles, Files, Analytics. With one channel that is invisible, because the account *is*
the channel. With two it is the whole problem — nothing in the app means "this
channel", so "how is the space channel doing" has to be answered by reading an
account-wide table with the other channel in it, and "what is waiting on me *here*"
cannot be asked at all.

So the shell is scoped to a channel: a breadcrumb, the channel's name with a live
status dot, and a nav inside that channel. That is what `/c/{id}` is, and the numbers
on it are the four you act on — what this channel started, what it finished, what is
sitting at a gate waiting for you, and what it has cost.

## Why the status word is derived rather than stored

A `Channel.status` column would be a cache of the runs that only the worker writes,
and a cache like that is wrong in exactly the situation you most need it: a process
killed mid-render leaves a channel claiming to be producing forever, with nothing
producing. The run rows are the fact, so the word is read off them per request and
cannot be stale for longer than a reload.

## Why a foreign channel id is 404 and never 403

A distinguishable "forbidden" confirms that channel 12 exists, and existence is the
part worth not confirming — an id is a small integer, so the whole space is walkable.
`/files` already draws this line for storage paths; drawing the same one here keeps the
two from disagreeing about what a wrong id means.

## Why the spend figure comes from the analytics pass

`spend_report` nets refunds against spends off the ledger, and Analytics prints the
same numbers per channel. Recomputing them here — even from `Run.credits_spent`, which
happens to be maintained — is how a hub and an analytics page come to quote different
costs for the same channel, and then neither is believed. It reads the account's spend
rows rather than this channel's, which is one pass over a table with a `run_id` index
and is the right trade until an account has years of ledger in it; at that point the
pass wants a channel-scoped variant, not a second implementation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import scripting
from ..auth import current_user, optional_user
from ..db import get_session
from ..graph import formats
from ..models import Channel, Run, RunStatus, User
from ..nodes._common import SUPPORTED_HEIGHTS, frame_for, resolve_height
from ..providers.media import VIDEO_MODELS, video_catalogue
from ..render.ffmpeg import SUPPORTED_FPS, resolve_fps
from .routes_analytics import spend_report

router = APIRouter(include_in_schema=False)

# Runs shown on the hub before it stops being a hub and starts being a list. The full
# list is one click away at /c/{id}/runs, so this is a preview and is allowed to be one.
HUB_RUNS = 8

# The whole list, capped. A channel producing daily passes a thousand runs in three
# years, and a page that renders all of them is a page you give up waiting for.
ALL_RUNS = 200

PRODUCING = "producing"
WAITING = "waiting"
IDLE = "idle"

# What each render backend is, in the words a picker needs. Kept here rather than in the
# template because the sentence that matters — which one is actually going to run — is
# resolved in Python, and splitting the two across files is how a label and its state
# come to say different things.
BACKEND_LABELS = {
    "ffmpeg": ("ffmpeg", "One filtergraph. Needs nothing that is not already installed."),
    "remotion": ("Remotion", "Real text layout, blurred shadows, masks and nesting, "
                             "rendered in a headless browser. Slower per frame, and it "
                             "carries its own licence terms."),
}


def motion_backend_state(channel: Channel) -> dict:
    """Which engine will draw this channel's motion graphics, and which was asked for.

    `will_use` is resolved rather than echoed back. `backends.backend_for` downgrades an
    unavailable engine to ffmpeg and says so only in a log line, so a page printing the
    stored word would agree with the setting and disagree with the finished video. That
    is most of how the Remotion renderer came to ship in every archive for months —
    installable, unselectable outside one CLI flag, and silent about which one ran.
    """
    from ..desktop import toolchain
    from ..render.backends import BACKENDS, backend_for

    asked = str((channel.style_profile or {}).get("motion_backend") or "ffmpeg")
    installed, absent = toolchain.extra_installed("motion")
    spec = toolchain.EXTRAS["motion"]
    options = []
    for key, cls in BACKENDS.items():
        label, note = BACKEND_LABELS.get(key, (key, ""))
        options.append({"key": key, "label": label, "note": note,
                        "available": bool(cls().available())})
    return {
        "asked_for": asked,
        "will_use": backend_for(asked).name,
        "options": options,
        "installed": bool(installed),
        "missing": absent,
        "label": spec["label"],
        "megabytes": spec["megabytes"],
    }


def owned_channel(session: Session, user: User, channel_id: int) -> Channel:
    """This account's channel, or 404.

    The one place the URL's id is turned into a row, so there is no second path that
    could forget the ownership half. `get` then compare, rather than a filtered select,
    only because the not-found and not-yours answers are deliberately identical.
    """
    channel = session.get(Channel, channel_id)
    if channel is None or channel.user_id != user.id:
        raise HTTPException(status_code=404, detail="channel not found")
    return channel


def channel_runs(session: Session, user: User, channel: Channel, limit: int) -> list[Run]:
    """This channel's runs, newest first.

    Filtered on the account as well as the channel. The channel was already proved to
    be this account's, so the second predicate is redundant today — and it is what
    keeps a future `Run` written against someone else's account from surfacing here if
    that invariant ever slips. It costs an indexed column in the WHERE clause.
    """
    return list(session.execute(
        select(Run)
        .where(Run.channel_id == channel.id, Run.user_id == user.id)
        .order_by(Run.id.desc())
        .limit(limit)
    ).scalars().all())


def status_word(runs: list[Run]) -> str:
    """What this channel is doing right now, in one word.

    Producing wins over waiting when both are true, because the dot describes the
    machine and the machine is busy. That would hide a gate, so it does not have to:
    "waiting on you" is a number of its own next to the dot, and it is the only figure
    on the page that can ask you for something.

    A queued run is deliberately not producing. Nothing is being produced yet, and the
    case where it stays queued is the worker being down — a dot reading "producing"
    while no worker exists is the exact lie this page is built to not tell.
    """
    live = {run.status for run in runs}
    if RunStatus.running in live:
        return PRODUCING
    if RunStatus.awaiting_approval in live:
        return WAITING
    return IDLE


def hub_facts(session: Session, user: User, channel: Channel, runs: list[Run]) -> dict:
    """The four numbers for one channel, plus the notes that keep them readable.

    `runs` is the channel's whole run list rather than the preview, because a count off
    a truncated list is a wrong count that looks like a right one.
    """
    completed = [run for run in runs if run.status is RunStatus.completed]
    at_gate = [run for run in runs if run.status is RunStatus.awaiting_approval]
    running = [run for run in runs if run.status is RunStatus.running]
    queued = [run for run in runs if run.status is RunStatus.queued]
    failed = [run for run in runs if run.status is RunStatus.failed]

    by_run = spend_report(session, user)["by_run"]
    spent = sum(by_run.get(run.id, 0) for run in runs)

    return {
        "runs": len(runs),
        "completed": len(completed),
        "at_gate": len(at_gate),
        "running": len(running),
        "queued": len(queued),
        "failed": len(failed),
        "in_flight": len(running) + len(queued) + len(at_gate),
        "credits_spent": spent,
        # Printed only when there is a denominator: "0% finished" on a channel that has
        # never been asked for anything reads as a failure rather than as a fresh start.
        "finished_pct": round(len(completed) / len(runs) * 100) if runs else None,
    }


def _context(session: Session, user: User, channel: Channel, view: str) -> dict:
    """Everything both views share, so the header cannot differ between them."""
    from .routes_web import shell

    every_run = channel_runs(session, user, channel, ALL_RUNS)
    shape = formats.get(formats.format_of_channel(channel))
    return {
        # The rail still highlights the format this channel belongs to. A channel page
        # with nothing lit in the rail reads as having navigated out of the app. That
        # alone says "the long-form workspace", which is not where you are, so the
        # channel's own entry in the rail is marked as well.
        **shell(session, user, f"format:{shape.slug}", rail_channel=channel.id),
        "channel": channel,
        "format": shape,
        "view": view,
        "state": status_word(every_run),
        "facts": hub_facts(session, user, channel, every_run),
        "runs": every_run if view == "runs" else every_run[:HUB_RUNS],
        "more_runs": max(0, len(every_run) - HUB_RUNS),
        # The scripting method every script on this channel is written to. Built through
        # `selection` rather than `available` so a style whose folder has gone still
        # appears, marked unavailable with the reason: a `<select>` that omits its own
        # stored value shows the first option instead, and the page then reports a
        # setting the channel does not have — which the next save makes true.
        "scripting_styles": scripting.selection(channel.scripting_style),
        "scripting_folder": scripting.folder_status(),
        # The renderer this channel's motion graphics are drawn with. It was readable by
        # `finalize` and writable by nothing but one CLI flag, so anybody not using the
        # command line rendered with ffmpeg for ever — including after installing the
        # alternative from inside the app.
        "motion_backend": motion_backend_state(channel),
        # Which image-to-video model this channel's shots are generated on. Every entry
        # was already in the catalogue and none of them was reachable: the registry built
        # every video provider as `cls(api_key)`, so the slug the app shipped with was the
        # slug every render on every channel used. Priced per finished video rather than
        # per second, because per-second rates rank these models in the wrong order — see
        # `video_catalogue`.
        "video_models": video_catalogue(channel.video_model),
        # The frame and the rate. Both were constants, and the frame was a constant
        # nobody chose: 9:16 and 1:1 already resolved to 1080 while 16:9 fell back to
        # 720, so the main format was the single one shipping at the lower resolution.
        "frames": [
            {"height": option,
             "label": f"{option}p",
             "frame": "x".join(str(edge)
                               for edge in frame_for(channel.aspect_ratio, option)),
             "chosen": option == resolve_height(channel.video_height or None)}
            for option in SUPPORTED_HEIGHTS
        ],
        "rates": [
            {"fps": option,
             "chosen": option == resolve_fps(channel.video_fps or None)}
            for option in SUPPORTED_FPS
        ],
    }


@router.get("/c/{channel_id}", response_class=HTMLResponse)
def channel_hub(
    channel_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    from .routes_web import TEMPLATES

    user = optional_user(request, session)
    if user is None:
        # `next` so signing in lands back on the channel rather than on the chat, which
        # is what makes a shared link to a hub worth sending.
        return RedirectResponse(f"/login?next=/c/{channel_id}", 303)  # type: ignore[return-value]

    channel = owned_channel(session, user, channel_id)
    return TEMPLATES.TemplateResponse(
        request, "channel.html",
        {**_context(session, user, channel, "hub"),
         "saved": request.query_params.get("saved", "")},
    )


@router.post("/c/{channel_id}/scripting")
def save_scripting_style(
    channel_id: int,
    scripting_style: str = Form(...),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    """Set which scripting method this channel's scripts are written to.

    An unknown slug is refused rather than stored. The alternative — trusting the form —
    stores a slug that resolves to nothing, and because `prompt_block` deliberately falls
    back to the house method rather than failing, the symptom is a channel that quietly
    writes to the wrong method for as long as nobody reads the run log.

    A slug that is currently *unavailable* is a different case and is allowed through:
    the folder being unmounted this morning is not a reason to make the operator re-pick
    their method, and the row is still in `selection()` for exactly that reason.
    """
    channel = owned_channel(session, user, channel_id)
    wanted = (scripting_style or "").strip() or scripting.HOUSE_SLUG
    known = {row["slug"] for row in scripting.selection(channel.scripting_style)}
    if wanted not in known:
        raise HTTPException(status_code=400, detail=f"unknown scripting style {wanted!r}")

    channel.scripting_style = wanted
    session.commit()
    return RedirectResponse(f"/c/{channel_id}?saved=scripting", 303)


@router.post("/c/{channel_id}/video-model")
def save_video_model(
    channel_id: int,
    # Defaulted rather than required, because empty is a meaningful value here: it means
    # "use the app default". `Form(...)` rejected the one submission that expresses it.
    video_model: str = Form(""),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    """Set which image-to-video model this channel's shots are generated on.

    An unknown slug is refused rather than stored, and unlike the scripting method there
    is no "unavailable but keep it" case: a slug that is not in the catalogue is priced
    from its family at the *dearest* known sibling, so storing one silently moves a
    channel onto the conservative estimate for every future run. Empty is allowed and
    means the app default — that is a choice, not a missing value.

    This is the single most expensive setting on the page. The same eighty-shot script is
    $14.70 on one of these models and $98 on another, and until this route existed the
    answer was always whichever slug the app shipped with.
    """
    channel = owned_channel(session, user, channel_id)
    wanted = (video_model or "").strip()
    if wanted and wanted not in VIDEO_MODELS:
        raise HTTPException(status_code=400, detail=f"unknown video model {wanted!r}")

    channel.video_model = wanted
    session.commit()
    return RedirectResponse(f"/c/{channel_id}?saved=video-model", 303)


@router.post("/c/{channel_id}/delivery")
def save_delivery(
    channel_id: int,
    video_height: int = Form(0),
    video_fps: int = Form(0),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    """Set the frame and the frame rate this channel delivers at.

    Snapped rather than refused. Neither of these is a slug that can resolve to nothing —
    they are numbers, and a number outside the supported set has an obvious nearest
    neighbour. Refusing would mean a 400 on a form that offered only valid options, which
    can only happen to somebody posting by hand.

    Stored together because they are one decision. An operator choosing 1440p is choosing
    how long a render takes, and so is one choosing 60fps; splitting them across two forms
    would let the page show a cost the operator has only half agreed to.
    """
    channel = owned_channel(session, user, channel_id)
    channel.video_height = resolve_height(video_height) if video_height else 0
    channel.video_fps = resolve_fps(video_fps) if video_fps else 0
    session.commit()
    return RedirectResponse(f"/c/{channel_id}?saved=delivery", 303)


@router.post("/c/{channel_id}/motion-backend")
def save_motion_backend(
    channel_id: int,
    motion_backend: str = Form(...),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    """Set which engine draws this channel's motion graphics.

    The write goes through `Studio` rather than assigning here, because the chat can set
    the same thing and two writers of one key is how a panel and a transcript come to
    disagree about what a channel is set to. `owned_channel` still does the lookup, so
    this page keeps its own 404-for-everything doctrine.

    An engine that is not installed is *stored* rather than refused. Refusing it would
    mean the choice cannot be recorded until the toolset is present — and the failure
    being fixed here is not that somebody picked something unavailable, it is that
    nobody was ever told the renderer had quietly fallen back.
    """
    from ..agent.studio import Studio
    from ..db import SessionLocal

    channel = owned_channel(session, user, channel_id)
    result = Studio(SessionLocal, user_id=user.id).set_motion_backend(
        channel.id, motion_backend)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return RedirectResponse(f"/c/{channel_id}?saved=motion", 303)


@router.get("/c/{channel_id}/runs", response_class=HTMLResponse)
def channel_run_list(
    channel_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Every run on this channel — the one list in the app that is not account-wide."""
    from .routes_web import TEMPLATES

    user = optional_user(request, session)
    if user is None:
        return RedirectResponse(f"/login?next=/c/{channel_id}/runs", 303)  # type: ignore[return-value]

    channel = owned_channel(session, user, channel_id)
    return TEMPLATES.TemplateResponse(
        request, "channel.html", _context(session, user, channel, "runs")
    )
