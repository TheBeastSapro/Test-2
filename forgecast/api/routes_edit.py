"""Reading a video somebody hands you, reachable. The HTTP end of `ingest`/`edit`/`layers`.

## Why this file exists

Three packages — 1,267 lines with their own tests — measured a supplied video, wrote the
paper edit for it and lifted a subject onto its own layer, and **nothing imported any of
them**. No route, no template, no agent tool, no CLI subcommand. That is the same failure
this app has now hit six times: a capability that works perfectly and cannot be reached
from the application is indistinguishable from one that does not exist, and every time it
gets reported as missing. It was not missing. It had no door.

## The separation the packages keep, kept here

`ingest` measures, `edit` decides, `render` executes, and each of those is its own call:

* `POST /read` measures and returns numbers.
* `POST /plan` returns a paper edit — what comes out, where, and why.
* `POST /plans/{id}/decision` is the operator accepting or rejecting it.
* `POST /plans/{id}/cut` executes one they have accepted, and nothing else.

The plan is the cheapest possible place to disagree with the machine. It costs nothing to
produce, nothing to change and nothing to throw away, and it fixes every expensive
decision that follows it — which is exactly why this app puts its gates on the stage that
*determines* the spend rather than the stage that incurs it. An approval here is that
gate, and it is why no endpoint here goes from a file to an output in one call.

## Why approving does not wait for the cut

Cutting re-encodes — `render/cut.py` has the measurements for why it must — and a
twenty-minute source is minutes of work. An approval that waited for it would be an
operator's decision that could fail because ffmpeg was busy, on a request most proxies
close after sixty seconds anyway.

So the decision is recorded instantly and *releases* the cut, which runs as a job on a
worker thread and streams its progress as NDJSON. That is the same shape `routes_styles`
uses for learning a style and `routes_setup` uses for installing a toolchain, for the same
reason, and it means a page reloaded mid-cut can rejoin rather than start a second one.

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

import asyncio
import json
import logging
import threading
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from ..agent.studio import Studio
from ..auth import current_user
from ..db import SessionLocal
from ..models import User
from .media import sign_url
from .routes_agent import VIDEO_EXT, attach_dir, describe

log = logging.getLogger("forgecast.api.edit")

router = APIRouter(prefix="/api/edit", tags=["edit"])

# What `GET /sources` offers. Anything else in the attachments folder is a document or a
# voice take rather than something these three packages can read, and listing it would
# invite a caller to hand a PDF to the probe.
READABLE = VIDEO_EXT | {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

# The running cut, process-wide, because it is an ffmpeg encode on a machine that is also
# expected to render. A plain dict for the same reason `routes_styles.LEARN` is one: the
# worker thread writes it and the streaming generator reads it, and a mapping is easier to
# reason about than an object whose methods either could call.
CUT: dict = {"running": False, "done": False, "ok": False, "log": [], "result": {},
             "plan_id": "", "user_id": 0, "started": 0.0}
CUT_LOCK = threading.Lock()

# Enough to see what happened to a plan with a lot of cuts in it, and not enough to grow
# without bound on one with thousands.
MAX_LOG = 200


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
    made = found.get("cut") or {}
    if made.get("path"):
        # The point of cutting it is that somebody watches it. A path on the server's
        # disk is not that, so the plan carries a link the browser can actually open —
        # signed, expiring, and for this account only.
        found["cut"] = {**made, "media_url": sign_url(made["path"], user.id),
                        "files": f"/files?path=cuts/{plan_id}.mp4"}
    return found


def _cut_state(user_id: int) -> dict:
    """The running cut as the caller reads it, scoped to whoever is asking.

    A cut belonging to another account is reported as busy without its plan id, its source
    path or its result. This is a single-operator app today, but the job carries the
    operator's own file paths and a status endpoint is not the place to hand those over.
    """
    mine = int(CUT.get("user_id") or 0) == int(user_id)
    return {
        "running": bool(CUT["running"]),
        "mine": mine,
        "done": bool(CUT["done"]) if mine else False,
        "ok": bool(CUT["ok"]) if mine else False,
        "plan_id": str(CUT["plan_id"]) if mine else "",
        "seconds_elapsed": round(time.monotonic() - float(CUT["started"] or 0.0), 1)
                           if CUT["running"] else 0.0,
        "log": list(CUT["log"][-40:]) if mine else [],
        "result": dict(CUT["result"]) if mine else {},
    }


def _cut_now(user_id: int, plan_id: str) -> None:
    """Execute one approved plan, on a worker thread. Never raises into the thread's exit.

    A failure here has to end up in `CUT` rather than in a traceback: the only thing
    watching is a generator polling this dict, and an exception that escapes leaves
    `running` true for ever and the caller waiting on a job that has stopped.
    """
    def note(line: str) -> None:
        log.info("cut-plan: %s", line)
        CUT["log"].append(line)
        del CUT["log"][:-MAX_LOG]

    try:
        result = Studio(SessionLocal, user_id=user_id).cut_plan(plan_id, on_note=note)
        CUT["result"] = result
        CUT["ok"] = not result.get("error")
        if result.get("error"):
            note(str(result["error"]))
    except Exception as exc:                                           # pragma: no cover
        log.exception("cutting an approved plan failed")
        CUT["result"] = {"error": f"{type(exc).__name__}: {exc}"}
        CUT["ok"] = False
        note(f"Failed: {type(exc).__name__}: {exc}")
    finally:
        CUT["done"] = True
        CUT["running"] = False


def _start_cut(user_id: int, plan_id: str) -> tuple[bool, str]:
    """Take the cutting slot for one plan, or say who has it.

    One at a time, process-wide. Two concurrent cuts would run two encodes on a machine
    that is also expected to render, and the second would finish over the first if both
    were given the same plan.
    """
    with CUT_LOCK:
        if CUT["running"]:
            if (int(CUT.get("user_id") or 0) == int(user_id)
                    and str(CUT.get("plan_id")) == str(plan_id)):
                return False, "joined"
            return False, "busy"
        CUT.update(running=True, done=False, ok=False, log=[], result={},
                   plan_id=str(plan_id), user_id=int(user_id),
                   started=time.monotonic())
        threading.Thread(target=_cut_now, args=(int(user_id), str(plan_id)),
                         daemon=True, name="forgecast-cut-plan").start()
        return True, "started"


@router.post("/plans/{plan_id}/decision")
def decide_plan(plan_id: str, payload: dict | None = None,
                user: User = Depends(current_user)) -> dict:
    """Accept or reject a paper edit. This is the gate.

    Rejecting is a first-class outcome rather than a way of deleting the plan: the note
    says what was wrong with it, and the next draft is made against that instead of
    against a blank page.

    Approving releases the cut and starts it, and returns without waiting for it — see the
    module docstring. Pass `cut: false` to approve without starting one, which is what an
    operator approving several plans in a row wants: the decision is the thing that had to
    be recorded, and the encoding can be taken one at a time afterwards.
    """
    body = payload or {}
    approve = bool(body.get("approve", True))
    result = _studio(user).approve_edit(plan_id, approve=approve,
                                        note=str(body.get("note") or ""))
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])

    cut: dict = {"running": False, "started": False}
    if approve and bool(body.get("cut", True)):
        started, why = _start_cut(user.id, plan_id)
        cut = {
            "running": started or why == "joined",
            "started": started,
            "busy": why == "busy",
            "stream": f"POST /api/edit/plans/{plan_id}/cut",
            "status": "GET /api/edit/cut",
            "why": ("a cut is already running — take this one when it finishes"
                    if why == "busy" else ""),
        }
    return {"ok": True, **result, "cut": cut}


@router.get("/cut")
def cut_status(user: User = Depends(current_user)) -> dict:
    """Where the running cut has got to, for a caller that was not watching the stream."""
    return _cut_state(user.id)


@router.post("/plans/{plan_id}/cut")
async def cut_plan(plan_id: str, user: User = Depends(current_user)):
    """Execute an approved paper edit, streaming progress as it goes.

    Refuses a plan that has not been approved — the refusal lives in `Studio.cut_plan`, so
    the chat's tools and this endpoint cannot disagree about what the gate means. NDJSON
    over a generator polling a worker thread, which is the shape the style shelf and the
    setup page already read; the alternative holds a worker for the length of an encode,
    blocks the event loop for all of it and reports nothing until the proxy gives up.
    """
    found = _studio(user).edit_plans(plan_id)
    if found.get("error"):
        raise HTTPException(status_code=404, detail=found["error"])

    _started, why = _start_cut(user.id, plan_id)
    if why == "busy":
        raise HTTPException(status_code=409,
                            detail="a cut is already running — they share one machine, "
                                   "so this one waits")

    async def stream():
        if why == "joined":
            yield json.dumps({"type": "joined"}) + "\n"
        sent = 0
        while True:
            while sent < len(CUT["log"]):
                yield json.dumps({"type": "log", "text": CUT["log"][sent]}) + "\n"
                sent += 1
            if CUT["done"] and sent >= len(CUT["log"]):
                break
            # A heartbeat rather than only log lines. The encode is one ffmpeg call with
            # nothing to say in the middle of it, and a stream that goes quiet for four
            # minutes is a stream an intermediary closes.
            yield json.dumps({"type": "progress",
                              "seconds_elapsed": round(
                                  time.monotonic() - float(CUT["started"] or 0.0), 1)
                              }) + "\n"
            await asyncio.sleep(0.5)

        result = dict(CUT["result"])
        # Minted here rather than in the studio: signing needs the account the link is
        # for, and the studio is the layer that has no idea it is being reached over HTTP.
        if result.get("path") and not result.get("error"):
            result["media_url"] = sign_url(result["path"], user.id)
        yield json.dumps({"type": "done", "ok": bool(CUT["ok"]),
                          "result": result}) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


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
