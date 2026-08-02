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
    """
    if os.name == "nt" and sys.stdin is not None and sys.stdin.isatty():
        with contextlib.suppress(EOFError, KeyboardInterrupt):
            input("  Press Enter to close…")


def main() -> int:
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
    print("  Forgecast — checking this machine…")
    try:
        python = bootstrap.prepare(ROOT, force_install="--reinstall" in sys.argv)
    except bootstrap.BootstrapError as exc:
        return fail(str(exc))

    environment = dict(os.environ, **{RELAUNCH_FLAG: "1"})
    try:
        return subprocess.call([str(python), str(ROOT / "launcher.py"), *sys.argv[1:]],
                               cwd=str(ROOT), env=environment)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
