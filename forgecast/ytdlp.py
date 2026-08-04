"""Where yt-dlp actually is, which on Windows is not on `PATH`.

## The failure this exists to remove

`yt-dlp` is a base dependency of this app, not an extra — reading a channel from a link
is not an optional part of Forgecast, and `pyproject.toml` says so beside the pin. So it
is installed, in the app's own virtualenv, on every install that ever completed.

Three modules then looked for it with `shutil.which("yt-dlp")`, which searches `PATH` for
an executable. On Windows the console script lands in `.venv\\Scripts\\`, and the app is
started from a `.vbs` that never activates the virtualenv — so `PATH` does not contain
it, `which` returns nothing, and the app reports that yt-dlp is not installed while the
package sits importable in its own environment.

What that cost is worse than a wrong message. The agent believes the app, and the only
remedy it has is a shell command — so it tried `pip install yt-dlp` four times against a
machine whose enterprise policy blocks unsandboxed shell execution, and every attempt
failed with a policy error that has nothing to do with the real problem. An operator
reading that transcript learns their machine is locked down. It is not: the tool was
there the whole time.

## Why the module, not the executable

`python -m yt_dlp` runs the same code through the interpreter that is already running
this app. That interpreter is by definition the one the package was installed into, so
the lookup cannot miss it — no `PATH`, no console script, no shim. The executable is
still preferred when it is genuinely on `PATH`, because a machine that installed yt-dlp
system-wide may have a newer one than the pin.

Resolved per call rather than at import. `vision.acquire` held the result in a module
constant, so a machine that installed yt-dlp *after* the app started went on being told
it had none until the app was restarted — and "restart it and try again" is the kind of
instruction this app exists not to give.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys


def command() -> list[str] | None:
    """The argv prefix that runs yt-dlp, or `None` when it genuinely is not installed.

    A list rather than a string because the module form is three words. Callers splice it
    into their own argv, so neither form is special-cased at the call site.
    """
    found = shutil.which("yt-dlp")
    if found:
        return [found]
    if importlib.util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]
    return None


def available() -> bool:
    return command() is not None


def why_missing() -> str:
    """What to tell an operator when it really is absent.

    Names the app's own installer rather than a pip command, because this app installs
    its own tooling — an operator handed `pip install yt-dlp` has been handed the
    maintainer's job, and on a managed machine it is a job they are not permitted to do.
    """
    return ("yt-dlp is missing from this install, so a channel link cannot be read "
            "without a YouTube Data API key. Reinstall from Setup, or add a key in "
            "Settings.")
