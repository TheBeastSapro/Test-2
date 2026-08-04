"""Reading a video somebody hands you, reachable. The HTTP end of `ingest`/`edit`/`layers`.

## Why this file exists

Three packages — 1,267 lines with their own tests — measured a supplied video, wrote the
paper edit for it and lifted a subject onto its own layer, and **nothing imported any of
them**. No route, no template, no agent tool, no CLI subcommand. That is the same failure
this app has now hit six times: a capability that works perfectly and cannot be reached
from the application is indistinguishable from one that does not exist, and every time it
gets reported as missing. It was not missing. It had no door.

## The separation the packages keep, kept here

`ingest` measures, `edit` decides, `render` executes. Nothing in this module cuts
anything, and that is not an oversight:

* `POST /read` measures and returns numbers.
* `POST /plan` returns a paper edit — what comes out, where, and why.
* `POST /plans/{id}/decision` is the operator accepting or rejecting it.

The plan is the cheapest possible place to disagree with the machine. It costs nothing to
produce, nothing to change and nothing to throw away, and it fixes every expensive
decision that follows it — which is exactly why this app puts its gates on the stage that
*determines* the spend rather than the stage that incurs it. An approval here is that
gate, and it is why no endpoint here goes from a file to an output in one call.

## Where the file comes from

`POST /api/agent/attach` — the chat composer's uploader, already chunked, already size
capped, already writing into the one folder the agent is allowed to open. A second
uploader would be a second set of limits to keep in step, so `GET /sources` lists what
that one has taken instead, and every path this module accepts is checked back against
the same folders (`Studio._supplied`).

## Missing tooling is a state, not an error

`scenedetect`, `faster-whisper` and `rembg` are the `edit` extra and may genuinely be
absent — they are 400 MB that most operators never need. So an absent reading comes back
as an installable state carrying the extra's key, and the app installs it from
`POST /api/setup/extras/edit`. What none of these responses ever contains is a command
for the operator to go and run: being handed homework instead of an install was reported
as a defect here once already.

## Why everything blocking runs in a thread

ffprobe, scene detection and transcription are subprocesses and CPU-bound loops that run
for minutes. On the event loop each of them stalls every other request in the process,
including the chat stream the operator is watching while they wait for the plan.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from ..agent.studio import Studio
from ..auth import current_user
from ..db import SessionLocal
from ..models import User
from .routes_agent import VIDEO_EXT, attach_dir, describe

log = logging.getLogger("forgecast.api.edit")

router = APIRouter(prefix="/api/edit", tags=["edit"])

# What `GET /sources` offers. Anything else in the attachments folder is a document or a
# voice take rather than something these three packages can read, and listing it would
# invite a caller to hand a PDF to the probe.
READABLE = VIDEO_EXT | {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _studio(user: User) -> Studio:
    """One studio per request, bound to the account that asked.

    The same object the chat's tools call, so a plan drafted in the chat and a plan
    drafted from a panel are the same plan in the same place — two implementations of
    "write the paper edit" is how the two halves of an app start disagreeing.
    """
    return Studio(SessionLocal, user_id=user.id)


def _refused(payload: dict) -> dict:
    """A studio error as an HTTP answer, keeping everything else it said.

    Returned as a body rather than raised as a 4xx. Every failure these packages produce
    is one the operator can act on — a missing toolset, a file outside the install, a
    video with no audio — and a bare status code throws away the sentence that says
    which.
    """
    return {"ok": False, **payload}


@router.get("")
async def editing_tools(user: User = Depends(current_user)) -> dict:
    """What can be measured here, and the install for what cannot.

    Answerable before a file exists, which is the point of it. Finding out that the
    transcription model is absent twenty seconds after a two-gigabyte upload finishes
    copying is the shape of failure the `ingest` package refuses to have.
    """
    return await run_in_threadpool(_studio(user).editing_tools)


@router.get("/sources")
def readable_attachments(_user: User = Depends(current_user)) -> dict:
    """The files already handed to this install that these packages can read.

    Not an uploader. `POST /api/agent/attach` is the uploader and stays the only one —
    it is chunked, size capped and writes into the folder the agent is sandboxed to, and
    a second copy of those three decisions is a second copy to keep in step.
    """
    folder = attach_dir()
    rows = []
    for path in sorted(folder.glob("*")):
        if not path.is_file() or path.suffix.lower() not in READABLE:
            continue
        rows.append({"name": path.name, "path": str(path),
                     "bytes": path.stat().st_size, **describe(path)})
    return {"sources": rows, "count": len(rows), "folder": str(folder),
            "upload": "POST /api/agent/attach"}


@router.post("/read")
async def read_video(payload: dict, user: User = Depends(current_user)) -> dict:
    """Measure one supplied video. Decides nothing and writes nothing."""
    result = await run_in_threadpool(
        _studio(user).read_video, str(payload.get("path") or ""),
        want_transcript=bool(payload.get("want_transcript", True)),
        want_shots=bool(payload.get("want_shots", True)))
    if result.get("error"):
        return _refused(result)
    return {"ok": True, **result}


@router.post("/plan")
async def draft_plan(payload: dict, user: User = Depends(current_user)) -> dict:
    """Write the paper edit and save it for the operator to read.

    Deliberately two calls to get from a file to an approved edit. One endpoint that
    measured, decided and cut would leave the operator arguing with a finished render
    instead of with a list they could have corrected in ten seconds.
    """
    result = await run_in_threadpool(
        _studio(user).plan_edit, str(payload.get("path") or ""),
        drop_fillers=bool(payload.get("drop_fillers", True)))
    if result.get("error"):
        return _refused(result)
    return {"ok": True, **result}


@router.get("/plans")
def list_plans(limit: int = 20, user: User = Depends(current_user)) -> dict:
    """Every paper edit this account has drafted, newest first."""
    return _studio(user).edit_plans(limit=limit)


@router.get("/plans/{plan_id}")
def read_plan(plan_id: str, user: User = Depends(current_user)) -> dict:
    """One plan in full, with the markdown an operator actually reads.

    404 rather than 403 for a plan belonging to another account, and identical to the
    answer for a plan that never existed — the ids are short and a distinguishable
    "forbidden" confirms which of them are real.
    """
    found = _studio(user).edit_plans(plan_id)
    if found.get("error"):
        raise HTTPException(status_code=404, detail=found["error"])
    return found


@router.post("/plans/{plan_id}/decision")
def decide_plan(plan_id: str, payload: dict | None = None,
                user: User = Depends(current_user)) -> dict:
    """Accept or reject a paper edit. This is the gate.

    Rejecting is a first-class outcome rather than a way of deleting the plan: the note
    says what was wrong with it, and the next draft is made against that instead of
    against a blank page.
    """
    body = payload or {}
    result = _studio(user).approve_edit(plan_id,
                                        approve=bool(body.get("approve", True)),
                                        note=str(body.get("note") or ""))
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return {"ok": True, **result}


@router.post("/layers")
async def cut_subject(payload: dict, user: User = Depends(current_user)) -> dict:
    """Lift the subject onto its own layer, and optionally put a title behind it.

    A refused matte comes back `ok: True` with `usable: false` and the reason, because
    it is a result and not a failure: a fringed cutout reads as cheaper than no cutout,
    so the quality gate turning one down is the feature working.
    """
    result = await run_in_threadpool(
        _studio(user).cut_subject, str(payload.get("image") or ""),
        text=str(payload.get("text") or ""),
        background=payload.get("background") or None,
        out=str(payload.get("out") or ""))
    if result.get("error"):
        return _refused(result)
    return {"ok": True, **result}
