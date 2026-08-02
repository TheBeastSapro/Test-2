"""Running the whole application inside one process.

A deployment splits the API and the worker into separate containers so they can scale
and restart independently. A desktop app has neither concern and one very strong
opposite requirement: closing the window must stop *everything*. Two subprocesses is
two ways to leave an orphan behind holding port 8765 and a SQLite write lock, which is
exactly the failure that makes a local app feel broken.

So: one process, two threads, one shutdown path.

* the **server** thread runs uvicorn with its signal handlers disabled, because
  installing them off the main thread raises;
* the **worker** thread runs the same polling loop the container worker runs, in its
  own event loop;
* the **main** thread owns the window and the shutdown.

Shutdown has three triggers — the window closing, Quit pressed in the UI, and Ctrl-C —
and they all end in `stop()`, which asks both threads to drain and waits for them.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import secrets
import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("forgecast.desktop")

LOOPBACK = "127.0.0.1"
PREFERRED_PORT = 8765


def free_port(preferred: int = PREFERRED_PORT) -> int:
    """The preferred port if it is free, otherwise one the OS picks.

    A stable port is worth trying for — bookmarks keep working, and the browser keeps
    the session cookie, which is scoped to origin including port. But a second instance
    or an unrelated service must not turn into a crash at launch.
    """
    for candidate in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((LOOPBACK, candidate))
            except OSError:
                continue
            return sock.getsockname()[1]
    raise RuntimeError("could not bind any port on the loopback interface")


def configure_environment(root: Path, port: int) -> str:
    """Set the process environment the server will read, and return the handoff token.

    Written into `os.environ` before any Forgecast module reads settings. `get_settings`
    is cached for the life of the process, so anything set after the first read is
    ignored — which is a silent failure, not a loud one. Hence: environment first,
    imports later.
    """
    token = secrets.token_urlsafe(32)
    os.environ.setdefault("FORGECAST_STORAGE_DIR", str(root / "storage"))
    os.environ["FORGECAST_BASE_URL"] = f"http://{LOOPBACK}:{port}"
    os.environ["FORGECAST_LOCAL_MODE"] = "true"
    os.environ["FORGECAST_LOCAL_HANDOFF_TOKEN"] = token
    return token


def wait_for_health(url: str, *, timeout: float = 40.0) -> dict | None:
    """Poll `/healthz` until the server answers. Returns its payload, or None.

    Waiting on the health endpoint rather than on the port being open matters: the port
    is listening before the lifespan hook has created tables, and a window opened in
    that gap shows a 500.
    """
    import json

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/healthz", timeout=2.0) as response:
                if response.status == 200:
                    return json.loads(response.read().decode())
        except (urllib.error.URLError, OSError, ValueError):
            pass
        time.sleep(0.15)
    return None


@dataclass
class Supervisor:
    """Owns the server thread, the worker thread, and the shutdown."""

    port: int
    host: str = LOOPBACK

    def __post_init__(self) -> None:
        self._server = None
        self._server_thread: threading.Thread | None = None
        self._worker = None
        self._worker_loop: asyncio.AbstractEventLoop | None = None
        self._worker_thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def is_running(self) -> bool:
        return self._server_thread is not None and self._server_thread.is_alive()

    # ------------------------------------------------------------------- start

    def migrate(self) -> None:
        """Bring the database to the current schema.

        Alembic first so an existing install upgrades properly; `init_db` as the
        fallback for the case where the migration environment is unavailable, which
        would otherwise leave a first-time user staring at a stack trace instead of an
        app.
        """
        from ..db import init_db

        try:
            from alembic import command
            from alembic.config import Config

            root = Path(__file__).resolve().parent.parent.parent
            config = Config(str(root / "alembic.ini"))
            config.set_main_option("script_location", str(root / "migrations"))
            command.upgrade(config, "head")
        except Exception as exc:
            log.warning("alembic upgrade skipped (%s); creating tables directly", exc)
            init_db()

    def start_server(self) -> None:
        import uvicorn

        config = uvicorn.Config(
            "forgecast.api.main:app",
            host=self.host,
            port=self.port,
            log_level="info",
            access_log=False,
        )
        server = uvicorn.Server(config)
        # uvicorn installs SIGINT/SIGTERM handlers in `run()`, and `signal.signal`
        # raises outside the main thread. The main thread handles signals here.
        server.install_signal_handlers = lambda: None
        self._server = server

        thread = threading.Thread(target=server.run, name="forgecast-server", daemon=True)
        thread.start()
        self._server_thread = thread

    def start_worker(self) -> None:
        """Run the durable worker loop alongside the server.

        The API nudges runs forward on create and on approval, so most of the time the
        worker has nothing to do. It matters for the case the nudge cannot cover: a run
        that was mid-flight when the app was last closed. Without it, reopening the app
        shows a run stuck in `running` that never moves.
        """
        from ..worker import Worker

        def run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._worker_loop = loop
            worker = Worker(worker_id="desktop")
            self._worker = worker
            try:
                loop.run_until_complete(worker.run_forever())
            except Exception:
                log.exception("worker stopped unexpectedly")
            finally:
                with contextlib.suppress(Exception):
                    loop.close()

        thread = threading.Thread(target=run, name="forgecast-worker", daemon=True)
        thread.start()
        self._worker_thread = thread

    # -------------------------------------------------------------------- stop

    def stop(self, *, timeout: float = 12.0) -> None:
        """Ask both threads to drain, then wait. Safe to call more than once."""
        if self._worker is not None and self._worker_loop is not None:
            # `request_stop` sets an asyncio.Event, which is not thread-safe; it has to
            # be set from inside the loop that owns it.
            with contextlib.suppress(RuntimeError):
                self._worker_loop.call_soon_threadsafe(self._worker.request_stop)

        if self._server is not None:
            self._server.should_exit = True

        for thread in (self._server_thread, self._worker_thread):
            if thread is not None and thread.is_alive():
                thread.join(timeout=timeout)

        if self._server_thread is not None and self._server_thread.is_alive():
            log.warning("the server thread did not stop in time")
