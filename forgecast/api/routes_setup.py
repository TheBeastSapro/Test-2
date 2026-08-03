"""First-run setup, inside the app's own window.

## Why it is not a console and not a tkinter box

Two obvious places to put this and both are worse. A console scrolling pip and npm
output is not an installer — it is a log that happens to end in a working app. A
tkinter window is a second UI toolkit, drawn in a style nothing else in the app uses,
that has to be written blind because it cannot be styled with the stylesheet.

The app already opens a window. So setup is a page in it: the same surface, the same
type, real progress bars, and the thing you were going to look at anyway is already
on screen when it finishes.

The chicken-and-egg is smaller than it looks. Python and the virtual environment are
handled before this exists — they have to be, because this is Python code — and those
take seconds with the launcher's own console output. What is left is the part that
takes minutes and deserves a bar: Node, the two chat CLIs — Claude Code and Codex —
and ffmpeg.

## Streaming

Newline-delimited JSON, one object per progress tick. `StreamingResponse` over a
generator that runs the install on a worker thread: the download is blocking stdlib
code and running it on the event loop would freeze every other request, including the
ones this page is making.

Only one install runs at a time. A second POST joins the first rather than starting a
parallel download of the same 30 MB — which is what a reload during setup would
otherwise do.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from ..auth import optional_user
from ..config import get_settings
from ..db import get_session
from ..desktop import toolchain

log = logging.getLogger("forgecast.api.setup")

router = APIRouter(include_in_schema=False)

# The install is a process-wide operation on a shared folder, so its state is
# process-wide too. A dict rather than a class: it is read by the SSE generator and
# written by the worker thread, and one plain mapping is easier to reason about than
# an object with methods that could be called from either.
JOB: dict = {"running": False, "log": [], "done": False, "ok": False,
             "step": "", "bytes": 0, "total": 0, "weight_done": 0, "weight_total": 1,
             # The weight of the tool being installed right now. Sent so the page can
             # scale the current download against *its own* share of the run. Without
             # it the bar had only "everything still to do" to scale against, so every
             # tool drove it to the end on its own and the next one reset it — measured
             # at 98% four times in one run, worst jump backwards 98.0% → 54.4%.
             "weight_step": 0}
LOCK = threading.Lock()


def app_root() -> Path:
    """The folder the app was unzipped into.

    Resolved from this module rather than from the working directory: a launcher
    started from somewhere else, or a shortcut with the wrong "start in", would
    otherwise install the runtime into an unrelated folder.
    """
    return Path(__file__).resolve().parents[2]


def needs_setup() -> bool:
    """Is anything missing that this page could actually install?

    A tool that has to be installed with a package manager does not count — the page
    would show a step it cannot perform, and a setup screen you cannot complete is
    worse than a banner.
    """
    return bool(toolchain.missing(app_root()))


def state() -> dict:
    root = app_root()
    tools = [tool.as_dict() for tool in toolchain.inventory(root)]
    return {
        "tools": tools,
        "ready": not any(t for t in tools if not t["present"] and not t["manual"]),
        "runtime": str(toolchain.runtime_dir(root)),
        "job": {k: v for k, v in JOB.items() if k != "log"},
        "log": JOB["log"][-40:],
    }


@router.get("/api/setup/state")
def setup_state() -> dict:
    return state()


def _begin_job() -> None:
    """Clear the previous run, synchronously, before any stream can look.

    This used to happen on the worker, after `toolchain.missing(root)` — a disk probe
    measured at 317 ms cold. `install()` set `running=True`, started the thread and
    returned, and the stream polled inside that gap: it saw the *previous* run's
    `done=True`, replayed that run's log lines, and reported its `ok` while the real
    install was still going. Pressing Install a second time — which is what the page's
    own "Try again" leads to — therefore answered instantly with the last run's verdict.
    Measured 5/5: a stream closed in 0.015 s against a 1.5 s install, reporting failure
    for a run that went on to succeed.
    """
    JOB.update(done=False, ok=False, log=[], step="", bytes=0, total=0,
               weight_done=0, weight_total=1, weight_step=0)


def _install_everything(root: Path) -> None:
    """Run the installs in order, updating JOB as it goes. Worker thread."""
    wanted = toolchain.missing(root)
    JOB.update(weight_total=max(1, sum(t.weight for t in wanted)))

    def note(line: str) -> None:
        log.info("setup: %s", line)
        JOB["log"].append(line)

    def progress(got: int, total: int) -> None:
        JOB["bytes"] = got
        JOB["total"] = total

    def ensure_node() -> None:
        """Node, with its own failure named as Node's.

        It used to be called bare inside the Claude and Codex branches, so a dropped
        connection during the download raised straight past every remaining tool into
        the outer handler — the whole log was two lines ending `Failed: URLError: …`,
        naming neither Node nor the tool that wanted it. That is the same abandonment
        the per-tool reporting below was added to prevent; only the `return` path had
        been fixed, not the `raise` path.
        """
        if toolchain.node_exe(root).exists() or toolchain.npm_exe(root).exists():
            return
        try:
            toolchain.install_node(root, progress)
        except Exception as exc:
            raise RuntimeError(
                f"Node.js could not be downloaded ({type(exc).__name__}: {exc}), and "
                f"it is the only way this CLI installs") from exc

    try:
        for tool in wanted:
            JOB.update(step=tool.label, bytes=0, total=0,
                       weight_step=tool.weight)
            note(f"Installing {tool.label}…")

            try:
                _install_one(tool, root, note, progress, ensure_node)
            except Exception as exc:
                # Per tool, so one failure costs one tool rather than the rest of the
                # run. The verdict at the end re-probes the disk either way.
                log.exception("setup step failed: %s", tool.label)
                note(f"{tool.label} failed — {type(exc).__name__}: {exc}")

            JOB["weight_done"] = JOB["weight_done"] + tool.weight

        toolchain.activate(root)
        remaining = toolchain.missing(root)
        JOB.update(done=True, ok=not remaining, step="")
        note("Setup finished." if not remaining else
             "Still missing: " + ", ".join(t.label for t in remaining))
    except Exception as exc:                                   # pragma: no cover
        log.exception("setup failed")
        note(f"Failed: {type(exc).__name__}: {exc}")
        JOB.update(done=True, ok=False, step="")
    finally:
        JOB["running"] = False


def _install_one(tool, root: Path, note, progress, ensure_node) -> None:
    """One tool, start to finish. Raises on failure so the caller can name it.

    Raising rather than returning `(ok, detail)` is the point: every failure here now
    reaches exactly one handler, which logs it against the tool that produced it and
    lets the run carry on. The previous shape had two ways to fail — a returned `False`
    that was reported, and a raised exception that abandoned every remaining tool with a
    message naming none of them.
    """
    if tool.key == "node":
        toolchain.install_node(root, progress)
        # Verified rather than announced. `install_node` returns its expected path
        # whether or not anything is there and does not raise on a wrong unpack layout,
        # so "Node ready at …" was a sentence that could be false.
        landed = toolchain.node_exe(root)
        if not landed.exists():
            raise RuntimeError(f"the download finished but no Node appeared at {landed}")
        note(f"Node ready at {landed}")

    elif tool.key == "claude":
        ensure_node()
        ok, detail = toolchain.install_claude_cli(
            root, progress, on_note=note)
        if not ok:
            raise RuntimeError(detail or "the Claude Code CLI could not be installed")
        note(f"Claude Code CLI ready at {detail}")

    elif tool.key == "codex":
        ensure_node()
        ok, detail = toolchain.install_codex_cli(root, progress, on_note=note)
        if not ok:
            raise RuntimeError(detail or "the Codex CLI could not be installed")
        note(f"Codex CLI ready at {detail}")

    elif tool.key == "ffmpeg":
        ok, detail = toolchain.install_ffmpeg(root, progress)
        if not ok:
            raise RuntimeError(detail or "ffmpeg could not be installed")
        note(f"ffmpeg ready at {detail}")


@router.post("/api/setup/install")
async def install(_request: Request):
    root = app_root()

    with LOCK:
        already = JOB["running"]
        if not already:
            # Cleared here, under the lock, before the thread exists and therefore
            # before any stream can read it. See `_begin_job`.
            _begin_job()
            JOB["running"] = True
            threading.Thread(target=_install_everything, args=(root,),
                             daemon=True, name="forgecast-setup").start()

    async def stream():
        # A reload mid-install joins the running job rather than starting a second
        # download of the same archive.
        if already:
            yield json.dumps({"type": "joined"}) + "\n"
        sent = 0
        while True:
            while sent < len(JOB["log"]):
                yield json.dumps({"type": "log", "text": JOB["log"][sent]}) + "\n"
                sent += 1
            yield json.dumps({
                "type": "progress", "step": JOB["step"],
                "bytes": JOB["bytes"], "total": JOB["total"],
                "weight_done": JOB["weight_done"], "weight_total": JOB["weight_total"],
                "weight_step": JOB["weight_step"],
            }) + "\n"
            if JOB["done"] and sent >= len(JOB["log"]):
                break
            await asyncio.sleep(0.4)
        yield json.dumps({"type": "done", "ok": JOB["ok"], **state()}) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    from .routes_web import TEMPLATES, shell

    user = optional_user(request, session)
    settings = get_settings()
    context: dict = {
        "settings": settings,
        "user": user,
        # The sidebar needs its context, and on a first run there is no account yet —
        # so the shell is only built when there is someone to build it for.
        **(shell(session, user, "setup") if user is not None else
           {"nav": "setup", "formats": [], "format_counts": {}, "credits": 0,
            "recent_runs": []}),
        **state(),
    }
    return TEMPLATES.TemplateResponse(request, "setup.html", context)


@router.post("/api/setup/skip")
def skip() -> RedirectResponse:
    """Carry on without the missing tools.

    Deliberately possible. Everything except rendering and the chat works without
    them, and an installer you cannot dismiss is a wall in front of an app that would
    otherwise run. The banner and the Claude chip keep saying what is missing.
    """
    JOB["skipped"] = True
    return RedirectResponse("/", 303)


def was_skipped() -> bool:
    return bool(JOB.get("skipped"))
