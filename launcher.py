#!/usr/bin/env python3
"""Forgecast launcher — the thing you double-click.

    python launcher.py

Two phases, because the first one cannot assume the second one's world exists.

**Phase one** runs under whatever Python opened this file. It may be the system
Python, with none of the project's dependencies installed. So it uses the standard
library only, and its whole job is to build the environment the application needs:
a virtualenv, the project installed into it, and a `.env` with secrets generated on
this machine.

**Phase two** is the application. It runs under the virtualenv's interpreter, which
phase one re-executes into. Everything from `import fastapi` onwards happens there.

The re-exec is what makes a double-click work. Without it the operator has to know to
activate a virtualenv first, which is precisely the knowledge a double-click is
supposed to remove.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Marks the child process so a bug in the prefix comparison cannot produce an infinite
# chain of re-executions — the second attempt stops and says so instead.
RELAUNCH_FLAG = "FORGECAST_LAUNCHER_RELAUNCHED"


def fail(message: str) -> int:
    print()
    print("  Forgecast could not start.")
    print()
    for line in message.splitlines():
        print(f"  {line}")
    print()
    _pause_if_double_clicked()
    return 1


def _pause_if_double_clicked() -> None:
    """Keep the console open long enough to read the error.

    A double-clicked script on Windows opens a console that closes the instant the
    process exits, so an error message that is printed is still an error message
    nobody sees.

    `FORGECAST_NO_PAUSE` is set by `Forgecast.vbs`, which starts this with the window
    hidden. A prompt in a window nobody can see is a process that hangs forever with no
    way to notice, so the hidden path never waits — the .vbs re-runs visibly instead.
    """
    if os.environ.get("FORGECAST_NO_PAUSE"):
        return
    if os.name == "nt" and sys.stdin is not None and sys.stdin.isatty():
        with contextlib.suppress(EOFError, KeyboardInterrupt):
            input("  Press Enter to close…")


def _ensure_streams() -> None:
    """Give this process a stdout and stderr even when Windows did not.

    `pythonw.exe` is `python.exe` without a console, which is how the app starts with no
    black window. The catch is that it leaves `sys.stdout` and `sys.stderr` as **None**,
    and every `print()` in the launcher and the app then raises `AttributeError: 'NoneType'
    object has no attribute 'write'`. A windowless start would fail on its first status
    line, which is a worse bug than the console it removed.

    So the streams are pointed at a file instead of discarded. A log is also the only way
    a windowless failure can be reported at all: there is no console to scroll back.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    log_dir = ROOT / "runtime"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handle = (log_dir / "launch.log").open("a", encoding="utf-8", buffering=1)
    except OSError:
        # A read-only folder must not stop the app. `os.devnull` is always writable and
        # the output was going nowhere before this function existed anyway.
        handle = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = handle
    if sys.stderr is None:
        sys.stderr = handle


def _windowless_python(python: Path) -> Path:
    """`pythonw.exe` beside `python.exe`, when this process has no console to inherit.

    A console child of a *console* parent reuses the parent's window and opens nothing.
    A console child of a **windowless** parent gets a new console, raised and focused —
    which is precisely the black box that appears out of nowhere. Re-executing into
    `pythonw.exe` keeps phase two windowless too, so there is nothing for a grandchild
    to be spawned from.
    """
    if os.name != "nt" or _has_console():
        return python
    candidate = python.with_name("pythonw.exe")
    return candidate if candidate.exists() else python


def _has_console() -> bool:
    """Whether this process owns a console window.

    Asked of Windows rather than inferred from `isatty`: output redirected to a file is
    not a tty, but the process may still own a console — and it is console *ownership*
    that decides whether a child opens a new window.
    """
    if os.name != "nt":
        return True
    try:
        import ctypes

        return bool(ctypes.windll.kernel32.GetConsoleWindow())
    except Exception:
        return True


def main() -> int:
    _ensure_streams()
    sys.path.insert(0, str(ROOT))
    try:
        from forgecast.desktop import bootstrap
    except ImportError as exc:  # pragma: no cover - a broken checkout
        return fail(f"the project files are incomplete: {exc}")

    if bootstrap.running_inside(ROOT):
        # Phase two. The virtualenv is active; hand over to the application.
        from forgecast.desktop.app import main as app_main

        return app_main(sys.argv[1:])

    if os.environ.get(RELAUNCH_FLAG):
        return fail(
            "the virtual environment was created but re-executing into it did not\n"
            f"take effect. Run it directly:\n\n"
            f"    {bootstrap.venv_python(ROOT)} launcher.py"
        )

    # Phase one.
    #
    # Before the first subprocess, not after. Phase one runs pip, creates a virtualenv and
    # unpacks ffmpeg and Node — every one of those a console program, and every one of them
    # a new black window when the parent is windowless. The app calls this too, but by then
    # a dozen children have already flashed up.
    from forgecast.desktop import toolchain

    toolchain.hide_child_consoles()

    print("  Forgecast — checking this machine…")
    try:
        python = bootstrap.prepare(ROOT, force_install="--reinstall" in sys.argv)
    except bootstrap.BootstrapError as exc:
        return fail(str(exc))

    environment = dict(os.environ, **{RELAUNCH_FLAG: "1"})
    try:
        return subprocess.call([str(_windowless_python(python)),
                                str(ROOT / "launcher.py"), *sys.argv[1:]],
                               cwd=str(ROOT), env=environment)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
