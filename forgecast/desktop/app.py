"""The desktop application: prepare, serve, show a window, wait, shut down.

This is phase two. By the time anything here runs, `launcher.py` has already made sure
a virtualenv exists with the dependencies in it and re-executed itself inside that
environment, so imports are safe.

The order below is not arbitrary. Settings are cached for the life of the process, so
the environment has to be complete before the first import that reads it; the schema
has to exist before the owner account is created; the server has to answer `/healthz`
before a window points at it. Each step depends on the one above.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import signal
import sys
from pathlib import Path

from . import bootstrap as prep
from .supervisor import (
    PREFERRED_PORT,
    Supervisor,
    configure_environment,
    free_port,
    wait_for_health,
)
from .window import open_window

log = logging.getLogger("forgecast.desktop")

ROOT = Path(__file__).resolve().parent.parent.parent


def _load_env_file(root: Path) -> dict[str, str]:
    """Read `.env` into the process environment.

    Pydantic settings reads `.env` on its own, but the launcher needs the same values
    *before* it imports anything — the owner email and password decide what account to
    create, and they are needed to configure the environment the server will read.
    Existing environment variables win, matching how every other layer resolves this.
    """
    values: dict[str, str] = {}
    path = root / ".env"
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        values[key] = value
        os.environ.setdefault(key, value)
    return values


def ensure_owner(env: dict[str, str]) -> None:
    """Create the local account and first channel if they are not there already.

    Delegates to the same `bootstrap` command a server deployment runs, rather than
    reimplementing account creation. It is idempotent, so this runs on every launch and
    does nothing on all but the first.
    """
    from argparse import Namespace

    from ..cli import cmd_bootstrap

    email = os.environ.get("FORGECAST_OWNER_EMAIL") or env.get("FORGECAST_OWNER_EMAIL")
    password = os.environ.get("FORGECAST_OWNER_PASSWORD") or env.get("FORGECAST_OWNER_PASSWORD")
    if not email or not password:
        log.warning("no owner configured; the app will show the login page")
        return

    cmd_bootstrap(Namespace(
        email=email, password=password, grant=100_000, channel="My Channel",
        niche="", tone="", seconds=480, reset_password=False,
    ))


def _banner(url: str, health: dict | None, env: dict[str, str], mode: str) -> None:
    ffmpeg_ok = bool((health or {}).get("ffmpeg"))
    provider = (health or {}).get("provider_mode", "?")
    print()
    print("  Forgecast is running.")
    print(f"    address       {url}")
    print(f"    window        {mode}")
    print(f"    provider mode {provider}"
          + ("   (nothing is called and nothing is charged)" if provider == "mock" else ""))
    print(f"    ffmpeg        {'found' if ffmpeg_ok else 'MISSING — rendering will fail'}")
    print(f"    sign-in       {env.get('FORGECAST_OWNER_EMAIL', '?')} / "
          f"{env.get('FORGECAST_OWNER_PASSWORD', '(see .env)')}")
    print()
    print("  Close the window, or press Quit in the app, to stop.")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="forgecast-desktop",
        description="Run Forgecast as a local application on this machine.",
    )
    parser.add_argument("--port", type=int, default=PREFERRED_PORT,
                        help=f"preferred port (default {PREFERRED_PORT}; "
                             "another is chosen if it is taken)")
    parser.add_argument("--window", default="auto",
                        choices=["auto", "webview", "chrome", "browser", "none"],
                        help="how to show the UI; 'none' serves without opening anything")
    parser.add_argument("--no-window", action="store_true",
                        help="same as --window none")
    parser.add_argument("--reinstall", action="store_true",
                        help="reinstall dependencies even if nothing changed")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(name)s: %(message)s",
    )
    # uvicorn's own configuration replaces the root handlers; keep its output but drop
    # the per-request noise, which is not useful in a desktop console.
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

    print("  Forgecast — preparing…")
    prep.ensure_env_file(ROOT)
    env = _load_env_file(ROOT)

    port = free_port(args.port)
    if port != args.port:
        print(f"  port {args.port} is in use; using {port}")
    configure_environment(ROOT, port)

    supervisor = Supervisor(port=port)
    supervisor.migrate()
    ensure_owner(env)
    supervisor.start_server()

    health = wait_for_health(supervisor.url)
    if health is None:
        supervisor.stop()
        print("  the server did not start. Run with --verbose to see why.", file=sys.stderr)
        return 1

    supervisor.start_worker()

    token = os.environ["FORGECAST_LOCAL_HANDOFF_TOKEN"]
    entry = f"{supervisor.url}/local/session?t={token}"

    mode = "none" if args.no_window else args.window
    _banner(supervisor.url, health, env, mode)

    # Ctrl-C in the console has to reach the same shutdown path as closing the window.
    from ..api.local import SHUTDOWN

    def on_signal(*_args) -> None:
        SHUTDOWN.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        # Not the main thread, or a platform without the signal: not fatal.
        with contextlib.suppress(ValueError, OSError):
            signal.signal(sig, on_signal)

    try:
        result = open_window(entry, prefer=mode, stop_event=SHUTDOWN)
        if result.mode == "none":
            print(f"  open this once to sign in:  {entry}")
        elif not result.blocking:
            print(f"  opened in your browser ({result.mode}).")

        if not result.blocking:
            # Nothing to observe the window's lifetime, so wait for an explicit stop.
            # A timeout on each wait keeps Ctrl-C responsive on Windows, where an
            # unbounded wait swallows it.
            while not SHUTDOWN.wait(timeout=0.5):
                if not supervisor.is_running:
                    break
    except KeyboardInterrupt:
        pass
    finally:
        print("  stopping…")
        supervisor.stop()

    print("  Forgecast stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
