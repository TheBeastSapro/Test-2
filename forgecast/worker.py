"""Background worker.

Deliberately a database-polling loop rather than Redis/Celery. At the scale this
starts at, a `SELECT ... WHERE status IN ('queued','running')` every two seconds is
free, needs no extra service, and survives restarts because all state is already in
the runs table. Swap in a real broker when polling latency, not throughput, becomes
the complaint.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import socket

from sqlalchemy import select

from . import nodes  # noqa: F401 - registers node handlers
from .config import get_settings
from .db import SessionLocal, init_db, session_scope
from .graph.engine import GraphEngine
from .models import Run, RunStatus

log = logging.getLogger("forgecast.worker")

CLAIMABLE = (RunStatus.queued, RunStatus.running)


class Worker:
    def __init__(self, *, worker_id: str | None = None) -> None:
        settings = get_settings()
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self.poll_seconds = settings.worker_poll_seconds
        self.engine = GraphEngine(
            SessionLocal, worker_id=self.worker_id, concurrency=settings.worker_concurrency
        )
        self._stop = asyncio.Event()

    def request_stop(self, *_args) -> None:
        log.info("worker %s draining", self.worker_id)
        self._stop.set()

    def _claimable_runs(self) -> list[tuple[int, RunStatus]]:
        """Runs worth looking at, with the status they had when we looked.

        The status travels with the id because the poll loop needs to know whether a
        tick changed anything — see `tick`.
        """
        with session_scope() as session:
            rows = session.execute(
                select(Run.id, Run.status)
                .where(Run.status.in_(CLAIMABLE))
                .order_by(Run.updated_at)
                .limit(10)
            ).all()
            return [(row[0], row[1]) for row in rows]

    async def tick(self) -> int:
        """Advance every claimable run. Returns how many actually *moved*.

        Counting moves rather than candidates is what keeps the loop from spinning.
        A run can be claimable and yet unadvanceable — most commonly because the API
        process is already driving it in-process, or because every remaining node is
        waiting on a gate. Returning the candidate count made those cases look like
        work, so the loop skipped its sleep and re-polled immediately, at 100% of a
        core, for as long as the condition lasted.

        In a container that only wasted a core. In the desktop app the worker shares
        an interpreter with the server, so the spin held the GIL and made the render it
        was waiting on take minutes instead of seconds.
        """
        progressed = 0
        for run_id, previous in self._claimable_runs():
            if self._stop.is_set():
                break
            try:
                status = await self.engine.advance(run_id)
            except Exception:
                log.exception("run %s crashed the engine", run_id)
                continue
            if status is not previous:
                log.info("run %s -> %s", run_id, status.value)
                progressed += 1
        return progressed

    async def run_forever(self) -> None:
        init_db()
        log.info(
            "worker %s started (mode=%s, concurrency=%s)",
            self.worker_id,
            get_settings().provider_mode,
            get_settings().worker_concurrency,
        )
        while not self._stop.is_set():
            moved = await self.tick()
            if not moved:
                # Sleep until the poll interval elapses, or wake early on shutdown.
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_seconds)
        log.info("worker %s stopped", self.worker_id)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    )
    worker = Worker()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, worker.request_stop)
        except NotImplementedError:  # pragma: no cover - Windows
            signal.signal(sig, worker.request_stop)
    await worker.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
