"""In-process run advancement.

The API nudges a run forward immediately after creation or an approval instead of
waiting for the worker's next poll — it makes the UI feel live. The standalone
worker is still the durable path; this is just latency. `_inflight` keeps one task
per run so a burst of approvals cannot start two engines on the same graph.
"""

from __future__ import annotations

import asyncio
import logging

from ..config import get_settings
from ..db import SessionLocal
from ..graph.engine import GraphEngine

log = logging.getLogger("forgecast.api.runner")

_inflight: set[int] = set()
_tasks: set[asyncio.Task] = set()
_loop: asyncio.AbstractEventLoop | None = None


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Remember the server's event loop.

    Required because FastAPI executes `def` (non-async) endpoints in a worker
    thread, where `asyncio.get_running_loop()` raises. Without this the nudge below
    silently did nothing and every run sat in `queued` until the worker polled it.
    """
    global _loop
    _loop = loop


def engine() -> GraphEngine:
    return GraphEngine(
        SessionLocal, worker_id="api", concurrency=get_settings().worker_concurrency
    )


async def _advance(run_id: int) -> None:
    try:
        status = await engine().advance(run_id)
        log.info("run %s advanced to %s", run_id, status.value)
    except Exception:
        log.exception("advancing run %s failed", run_id)
    finally:
        _inflight.discard(run_id)


def schedule(run_id: int) -> bool:
    """Kick a run forward in the background.

    Returns False when the run is already in flight, or when there is no server
    loop to schedule on (the CLI, for instance, advances runs explicitly instead).
    """
    if run_id in _inflight:
        return False

    try:  # already on the loop (async endpoint, tests)
        loop = asyncio.get_running_loop()
        _inflight.add(run_id)
        task = loop.create_task(_advance(run_id))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
        return True
    except RuntimeError:
        pass

    if _loop is None or _loop.is_closed():
        return False

    # Called from a threadpool worker: hand the coroutine to the server loop.
    _inflight.add(run_id)
    try:
        asyncio.run_coroutine_threadsafe(_advance(run_id), _loop)
    except RuntimeError:
        _inflight.discard(run_id)
        return False
    return True
