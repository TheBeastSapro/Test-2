"""The style shelf: what has been learned, what it changed, and where to apply it.

## Why this page could read every style and produce none

It imported `available`, `blend`, `delete`, `get` and `refine` — and not `learn`. The one
importer of `style.learn` in the whole tree was `forgecast/vision/cli.py`, so the
application could apply, mix, improve and delete editing styles and nothing in it could
make one. An empty shelf offered a command to type into a terminal, which is the same
homework this app removes everywhere else; `studio.list_styles` even said so out loud.

Reading and applying is the part that happens often, and it stays synchronous. Learning
is the part that takes minutes — it decodes every reference frame by frame — so it runs
on a worker thread and streams its progress, rather than holding a request open for the
length of a video and dying to the first proxy read timeout.

## One at a time

Two concurrent learns would decode two videos on a machine that is also expected to
render, and the second would finish over the first if both were given the same name. A
second request joins the running job rather than starting another, which is also what a
reload of the page does.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent.studio import Studio
from ..auth import current_user, optional_user
from ..config import get_settings
from ..db import SessionLocal, get_session
from ..graph import formats
from ..models import Channel, User
from ..style import EditingStyle, available, blend, delete, get, refine

log = logging.getLogger("forgecast.api.styles")

router = APIRouter(include_in_schema=False)

# Learning goes through `Studio.learn_style`, which is what the chat's `learn_style` tool
# calls as well. Calling `style.learn` from here instead would mean two copies of the
# measure-learn-upgrade-save sequence, and the copy that gets the fix is never the one
# somebody is using.

# The running learn, process-wide, because it is a process-wide operation on a shared
# folder. A plain dict for the same reason `routes_setup.JOB` is one: the worker thread
# writes it and the streaming generator reads it, and a mapping is easier to reason
# about than an object whose methods either could call.
LEARN: dict = {"running": False, "done": False, "ok": False, "log": [],
               "result": {}, "name": "", "user_id": 0}
LEARN_LOCK = threading.Lock()

# Enough to see what is happening and not enough to grow without bound on a run over
# twenty references.
MAX_LOG = 200


def _directory() -> str:
    return str(get_settings().storage_dir / "styles")


@router.get("/styles", response_class=HTMLResponse)
def styles_page(
    request: Request,
    session: Session = Depends(get_session),
    selected: str = "",
) -> HTMLResponse:
    from ..research import keyless
    from .routes_web import TEMPLATES, shell

    user = optional_user(request, session)
    if user is None:
        return RedirectResponse("/login?next=/styles", 303)  # type: ignore[return-value]

    folder = _directory()
    rows = available(folder)
    chosen: EditingStyle | None = None
    if selected or rows:
        try:
            chosen = get(selected or rows[0]["key"], folder)
        except KeyError:
            chosen = None

    channels = session.execute(
        select(Channel).where(Channel.user_id == user.id).order_by(Channel.id)
    ).scalars().all()

    return TEMPLATES.TemplateResponse(
        request,
        "styles.html",
        {
            **shell(session, user, "styles", channels=channels),
            # Learning from links downloads the videos, which is the same yt-dlp read
            # the research desk uses and the same one YouTube refuses from a datacentre
            # address. Uploading files is unaffected — that is why the caveat sits
            # under the link box rather than at the top of the page.
            "links_note": keyless.BLOCKED_NOTE,
            "styles": rows,
            "chosen": chosen,
            # Refinements are stored on the style rather than recomputed, so the page
            # shows what was actually applied when it was learned — not what the
            # current thresholds would do to it now.
            "refinements": (chosen.provenance.get("refinements") or []) if chosen else [],
            "channels": channels,
            "channel_format": {c.id: formats.format_of_channel(c) for c in channels},
        },
    )


def _learn_state(user_id: int) -> dict:
    """The running learn as the page reads it, scoped to whoever is asking.

    A learn belonging to another account is reported as "busy" without its name, its
    references or its result. This is a single-operator app today and the shelf is
    shared, but the job carries the operator's own file paths and a status endpoint is
    not the place to hand those to a second account.
    """
    mine = int(LEARN.get("user_id") or 0) == int(user_id)
    return {
        "running": bool(LEARN["running"]),
        "mine": mine,
        "done": bool(LEARN["done"]) if mine else False,
        "ok": bool(LEARN["ok"]) if mine else False,
        "name": str(LEARN["name"]) if mine else "",
        "log": list(LEARN["log"][-40:]) if mine else [],
        "result": dict(LEARN["result"]) if mine else {},
    }


def _learn_now(user_id: int, references: list[str], name: str, upgrade: bool) -> None:
    """Measure and save, on a worker thread. Never raises into the thread's exit.

    A failure here has to end up in `LEARN` rather than in a traceback, because the only
    thing watching is a generator polling this dict — an exception that escapes leaves
    `running` true for ever and the page waiting on a job that has stopped.
    """
    def note(line: str) -> None:
        log.info("learn-style: %s", line)
        LEARN["log"].append(line)
        del LEARN["log"][:-MAX_LOG]

    try:
        result = Studio(SessionLocal, user_id=user_id).learn_style(
            references, name=name, upgrade=upgrade, on_note=note)
        LEARN["result"] = result
        LEARN["ok"] = not result.get("error")
        if result.get("error"):
            note(str(result["error"]))
        for failure in result.get("failures") or []:
            note(f"could not measure {failure}")
    except Exception as exc:                                          # pragma: no cover
        log.exception("learning a style failed")
        LEARN["result"] = {"error": f"{type(exc).__name__}: {exc}"}
        LEARN["ok"] = False
        note(f"Failed: {type(exc).__name__}: {exc}")
    finally:
        LEARN["done"] = True
        LEARN["running"] = False


@router.get("/api/styles/learn")
def learn_status(user: User = Depends(current_user)) -> dict:
    """Where the running learn has got to, for a page that was reloaded mid-run."""
    return _learn_state(user.id)


@router.post("/api/styles/learn")
async def learn_style(payload: dict, user: User = Depends(current_user)):
    """Learn an editing style from references, streaming progress as it goes.

    NDJSON over a generator polling a worker thread, which is the shape the setup page
    and the toolchain banner already read. The alternative — measuring inside the
    request — holds a worker for the length of the videos, blocks the event loop for all
    of it, and reports nothing until it is over or the proxy gives up.

    References are attached files or links. The uploader is `POST /api/agent/attach`,
    the same one the chat composer uses; a second one here would be a second set of size
    limits and a second folder to keep the agent's sandbox in step with.
    """
    references = [str(item).strip() for item in (payload.get("references") or [])
                  if str(item).strip()]
    name = str(payload.get("name") or "").strip()
    upgrade = bool(payload.get("upgrade", True))
    if not references:
        raise HTTPException(status_code=400,
                            detail="give at least one reference — a video you have "
                                   "attached, or a link to one")
    if not name:
        raise HTTPException(status_code=400,
                            detail="give the style a name; it is the key it is saved "
                                   "and applied under")

    with LEARN_LOCK:
        if LEARN["running"] and int(LEARN.get("user_id") or 0) != user.id:
            raise HTTPException(status_code=409,
                                detail="another account is already learning a style — "
                                       "they share one folder, so this waits")
        joined = bool(LEARN["running"])
        if not joined:
            # Cleared here, under the lock and before the thread exists, so no stream can
            # read the previous run's verdict and report it for this one. `routes_setup`
            # learned that the expensive way.
            LEARN.update(running=True, done=False, ok=False, log=[], result={},
                         name=name, user_id=user.id)
            threading.Thread(target=_learn_now,
                             args=(user.id, references, name, upgrade),
                             daemon=True, name="forgecast-learn-style").start()

    async def stream():
        if joined:
            yield json.dumps({"type": "joined"}) + "\n"
        sent = 0
        while True:
            while sent < len(LEARN["log"]):
                yield json.dumps({"type": "log", "text": LEARN["log"][sent]}) + "\n"
                sent += 1
            if LEARN["done"] and sent >= len(LEARN["log"]):
                break
            await asyncio.sleep(0.3)
        yield json.dumps({"type": "done", "ok": bool(LEARN["ok"]),
                          "result": LEARN["result"]}) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.post("/styles/{key}/apply")
def apply_style(
    key: str,
    channel_id: int = Form(...),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    """Put a style on a channel, keeping everything the style has no opinion about."""
    channel = session.get(Channel, channel_id)
    if channel is None or channel.user_id != user.id:
        raise HTTPException(status_code=404, detail="channel not found")
    try:
        style = get(key, _directory())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    channel.style_profile = style.to_channel_profile(channel.style_profile)
    session.commit()
    log.info("applied style %s to channel %s", style.key, channel.id)
    return RedirectResponse(f"/styles?selected={key}&applied={channel.id}", 303)


@router.post("/styles/{key}/blend")
def blend_styles(
    key: str,
    other: str = Form(...),
    weight: float = Form(0.5),
    name: str = Form(""),
    _user: User = Depends(current_user),
) -> RedirectResponse:
    folder = _directory()
    try:
        first, second = get(key, folder), get(other, folder)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    mixed = blend(first, second, weight, name=name or f"{first.name} x {second.name}")
    mixed.save(folder)
    return RedirectResponse(f"/styles?selected={mixed.key}", 303)


@router.post("/styles/{key}/refine")
def refine_style(key: str, _user: User = Depends(current_user)) -> RedirectResponse:
    """Run the upgrade pass over a style that was saved raw.

    Saved as a new style rather than in place: the measured version is evidence about
    a reference, and evidence you overwrite is not evidence.
    """
    folder = _directory()
    try:
        style = get(key, folder)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    improved, _changes = refine(style)
    improved.save(folder)
    return RedirectResponse(f"/styles?selected={improved.key}", 303)


@router.post("/styles/{key}/delete")
def delete_style(key: str, _user: User = Depends(current_user)) -> RedirectResponse:
    delete(key, _directory())
    return RedirectResponse("/styles", 303)
