"""First-run preparation. Standard library only — nothing else exists yet.

This module runs under whatever Python the operator double-clicked with, before any
dependency is installed. Importing anything from `forgecast` proper here, or any
third-party package, turns the first run into an ImportError traceback. Nothing in
this file may import outside the standard library, and nothing may import the rest of
the application.

## What "prepared" means

1. A Python new enough to run the application.
2. A virtual environment beside the project, with the project installed into it.
3. A `.env` holding secrets generated on this machine, never checked in and never
   shared between installs.
4. ffmpeg on PATH — reported, not enforced, because the app is still usable for
   research and scripting without it and a hard stop at launch is a worse first
   experience than a clear warning.

Every step is idempotent and cheap to re-check. The expensive one — installing
dependencies — is skipped when a fingerprint of `pyproject.toml` matches the one
recorded at the last successful install, so a normal launch costs milliseconds rather
than the thirty seconds pip takes to decide it has nothing to do.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import os
import secrets
import shutil
import subprocess
import sys
import venv
from pathlib import Path

MIN_PYTHON = (3, 11)

VENV_DIR = ".venv"
STAMP_NAME = ".forgecast-install-stamp"
ENV_FILE = ".env"


class BootstrapError(RuntimeError):
    """Something the operator has to fix before the app can start."""


# ------------------------------------------------------------------ small helpers


def say(message: str) -> None:
    print(f"  {message}", flush=True)


def venv_python(root: Path) -> Path:
    """Path to the interpreter inside the project's virtualenv."""
    if os.name == "nt":
        return root / VENV_DIR / "Scripts" / "python.exe"
    return root / VENV_DIR / "bin" / "python"


def running_inside(root: Path) -> bool:
    """True when the current interpreter is the project's own virtualenv.

    Compared by resolved prefix rather than by `sys.executable`, so a symlinked or
    relaunched interpreter still recognises itself and the launcher does not re-exec
    in a loop.
    """
    try:
        return Path(sys.prefix).resolve() == (root / VENV_DIR).resolve()
    except OSError:
        return False


# ---------------------------------------------------------------------- the steps


def check_python() -> None:
    if sys.version_info < MIN_PYTHON:
        raise BootstrapError(
            f"Forgecast needs Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer; this is "
            f"{sys.version.split()[0]} at {sys.executable}.\n"
            "  Install a newer Python and run the launcher again."
        )


def ensure_venv(root: Path) -> Path:
    """Create the virtualenv if it is missing. Returns its interpreter."""
    python = venv_python(root)
    if python.exists():
        return python

    say(f"creating a virtual environment in {VENV_DIR}/ (one time, ~10s)")
    try:
        venv.EnvBuilder(with_pip=True, upgrade_deps=False).create(root / VENV_DIR)
    except Exception as exc:  # pragma: no cover - platform specific
        raise BootstrapError(
            f"could not create a virtual environment: {exc}\n"
            "  On Debian/Ubuntu this usually means the python3-venv package is missing."
        ) from exc

    if not python.exists():
        raise BootstrapError(f"virtual environment created but {python} is not there")
    return python


def _fingerprint(root: Path) -> str:
    """What the install depends on. Changing any of it forces a reinstall.

    The install's *location* is one of those things, and that is not obvious. Installing
    the project with `pip install -e .` writes a finder into the virtualenv that records
    the project's absolute path. Move the folder — a different drive letter, a USB stick
    that remounts, a rename — and that recorded path is stale.

    Usually it is harmless: the launcher puts the real project directory first on
    `sys.path`, so the local copy wins. It stops being harmless when the *old* path
    still exists, which is what happens when someone copies the folder instead of moving
    it. Anything that imports `forgecast` without going through the launcher then loads
    the original folder's code while writing to the copy's database — silently, with no
    error to notice.

    Including the resolved path here means a moved or copied install reinstalls itself
    on first launch and rewrites the finder. It costs one pip run, once, and only for an
    install that actually moved.
    """
    digest = hashlib.sha256()
    digest.update((root / "pyproject.toml").read_bytes())
    digest.update(sys.version.encode())
    digest.update(str(root.resolve()).encode())
    return digest.hexdigest()


def install_dependencies(root: Path, python: Path, *, force: bool = False) -> bool:
    """Install the project into its virtualenv. Returns True when it actually ran."""
    stamp = root / VENV_DIR / STAMP_NAME
    wanted = _fingerprint(root)
    if not force and stamp.exists() and stamp.read_text(encoding="utf-8").strip() == wanted:
        return False

    unreachable = _pypi_unreachable()
    if unreachable:
        # Asked before pip runs, not after. The first launch is the only one that needs
        # the network, and without this check the operator watches a progress line for a
        # minute or two and is then told the install failed — for a reason that was
        # knowable in three seconds. Reported as a BootstrapError with the remedy rather
        # than a warning, because there is no way to continue: the build backend
        # (setuptools) is not in a fresh virtualenv on Python 3.12 and later, so even a
        # fully cached install has to fetch it.
        raise BootstrapError(
            f"pypi.org is not reachable ({unreachable}).\n"
            "  The first launch is the only one that needs the internet — it downloads "
            "this app's Python packages, and after that it never asks again.\n"
            "  If you are on a corporate network or a VPN, set HTTPS_PROXY to your proxy "
            "and start Forgecast again.")

    say("installing dependencies (one time, a minute or two)")
    log_path = root / "runtime" / "pip.log"

    # Captured rather than inherited, and this is a correction. The previous version let
    # pip write straight to the console and the error message said "scroll up for pip's
    # reason" — which was wrong in two different ways. Under the windowless launcher there
    # is no console to scroll. And even with one, child consoles are suppressed on Windows
    # so that nothing black appears out of nowhere, which is exactly the mechanism that
    # inherited output depends on. A failure reported as "the reason is somewhere above"
    # with nothing above it is worse than no message at all: it says the information
    # exists and sends the operator to look for it.
    #
    # `--quiet` is gone for the same reason. It saved console noise that no longer goes to
    # a console, at the cost of the log being empty in the one case the log matters.
    result = subprocess.run(
        [str(python), "-m", "pip", "install", "--disable-pip-version-check", "-e", "."],
        cwd=str(root), capture_output=True, text=True, errors="replace",
    )
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(output or "(pip produced no output)", encoding="utf-8")
    except OSError:
        log_path = None                                              # read-only install

    if result.returncode != 0:
        raise BootstrapError(_pip_failure(output, log_path))
    stamp.write_text(wanted, encoding="utf-8")
    return True


# Long enough to fail on a genuinely dead network, short enough that nobody notices it on
# a working one. This is a TCP connect, not a request, so it does not wait for a response
# body and it sends nothing.
REACHABILITY_TIMEOUT = 4.0


def _pypi_unreachable() -> str:
    """Why pypi.org cannot be reached, or "" when it can.

    A plain socket connect rather than an HTTP request, because `httpx` is one of the
    packages this function exists to install — nothing here may import outside the
    standard library. And a *connect* rather than a DNS lookup alone, since a machine
    behind a captive portal resolves everything and connects to nothing.

    Skipped entirely when a proxy is configured: the proxy is what would be connected to,
    its host is not knowable from here in every form the variable takes, and a false
    "no network" on a machine that has one would be worse than the slow failure this
    replaces.
    """
    import os as _os

    if any(_os.environ.get(name) for name in
           ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY",
            "PIP_INDEX_URL", "PIP_PROXY")):
        return ""

    import socket

    try:
        with socket.create_connection(("pypi.org", 443), timeout=REACHABILITY_TIMEOUT):
            return ""
    except OSError as exc:
        # The message, not the class: `[Errno 11001] getaddrinfo failed` tells the
        # operator it is DNS, where "OSError" tells them nothing.
        return str(exc) or type(exc).__name__


# How much of pip's output to put in front of the operator. Enough to carry the actual
# error, which pip prints last and which is usually a handful of lines under a
# `note:`/`error:` heading — not so much that the message it is attached to scrolls away.
PIP_TAIL_LINES = 24


def _pip_failure(output: str, log_path: Path | None) -> str:
    """pip's failure, as something to act on rather than a pointer to somewhere else."""
    lines = [line for line in output.splitlines() if line.strip()]
    tail = lines[-PIP_TAIL_LINES:]

    parts = ["dependency installation failed. This is pip's own output:", ""]
    parts += [f"    {line}" for line in tail] or ["    (pip printed nothing at all)"]
    parts += [""]
    if log_path is not None:
        parts.append(f"The whole log is in {log_path}.")

    # The three that account for nearly every real occurrence, each with the specific
    # remedy rather than a general suggestion to check things.
    lowered = output.lower()
    if any(marker in lowered for marker in
           ("could not find a version", "no matching distribution",
            "failed to establish a new connection", "temporary failure in name resolution",
            "connection refused", "read timed out", "proxyerror")):
        parts.append("That reads like no network access. pip needs to reach pypi.org "
                     "once, on the first launch only. If you are behind a proxy, set "
                     "HTTPS_PROXY before starting.")
    elif any(marker in lowered for marker in
             ("microsoft visual c++", "vswhere", "cl.exe", "error: command",
              "building wheel for", "gcc", "unable to find vcvarsall")):
        parts.append("That reads like a package trying to compile. Installing the "
                     "Microsoft C++ Build Tools fixes it, or a newer Python often has a "
                     "prebuilt wheel and needs no compiler at all.")
    elif "permission denied" in lowered or "access is denied" in lowered:
        parts.append("That reads like a permissions problem. Move the Forgecast folder "
                     "somewhere you own — your Desktop or Documents — rather than "
                     "Program Files, and try again.")
    return "\n".join(parts)


def _fernet_key() -> str:
    """A key in the format `cryptography.fernet` accepts: 32 random bytes, base64url.

    Generated here rather than with `Fernet.generate_key()` so that first-run secret
    generation does not depend on a package that is not installed yet.
    """
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


def ensure_env_file(root: Path) -> dict[str, str]:
    """Create `.env` on first run with secrets generated on this machine.

    Never rewrites an existing file: the encryption key protects provider credentials
    already in the database, and regenerating it would make every stored key
    undecryptable. Missing individual values are added; present ones are left alone.
    """
    path = root / ENV_FILE
    existing: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            existing[key.strip()] = value.strip()

    defaults = {
        "FORGECAST_SECRET_KEY": lambda: secrets.token_urlsafe(48),
        "FORGECAST_ENCRYPTION_KEY": _fernet_key,
        "FORGECAST_PROVIDER_MODE": lambda: "mock",
        "FORGECAST_DATABASE_URL": lambda: "sqlite:///./forgecast.db",
        "FORGECAST_STORAGE_DIR": lambda: "./storage",
        "FORGECAST_OWNER_EMAIL": lambda: "owner@localhost",
        # A random password rather than a fixed one. The desktop window signs in
        # without it, but it is the way back in if the handoff is ever missed, and a
        # predictable local password becomes a real hole the moment the port is
        # forwarded for "just a minute".
        "FORGECAST_OWNER_PASSWORD": lambda: secrets.token_urlsafe(18),
        # Signup stays closed. On a personal instance there is nobody else to sign up.
        "FORGECAST_ALLOW_SIGNUP": lambda: "false",
    }

    added = {key: make() for key, make in defaults.items() if key not in existing}
    if added:
        # Whether the file already had content decides whether a separating blank line
        # is needed — and it has to be measured before opening in append mode, which
        # creates the file and makes the answer "empty" either way.
        had_content = path.exists() and path.stat().st_size > 0
        lines = []
        if not had_content:
            lines.append("# Forgecast local configuration — generated on first run.")
            lines.append("# Machine-specific secrets. Do not commit or copy to another install.")
        lines.extend(f"{key}={value}" for key, value in added.items())
        with path.open("a", encoding="utf-8") as handle:
            if had_content:
                handle.write("\n")
            handle.write("\n".join(lines) + "\n")
        say(f"wrote {len(added)} new setting(s) to {ENV_FILE}")

    # Windows and some filesystems do not implement POSIX modes; not fatal.
    with contextlib.suppress(OSError):
        path.chmod(0o600)

    existing.update(added)
    return existing


def check_ffmpeg() -> tuple[bool, str]:
    """Report whether ffmpeg is usable, and how to get it if not."""
    from . import toolchain

    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return True, ""
    if toolchain.ffmpeg_exe(Path(__file__).resolve().parents[2]).exists():
        return True, ""

    instructions = {
        "nt": "  winget install Gyan.FFmpeg   (then reopen the launcher)",
        "darwin": "  brew install ffmpeg",
    }
    hint = instructions.get(
        "nt" if os.name == "nt" else sys.platform,
        "  apt install ffmpeg   (or your distribution's equivalent)",
    )
    return False, (
        "ffmpeg was not found on PATH. Research, scripting and voice will work; "
        "rendering will not.\n" + hint
    )


def check_claude() -> tuple[bool, str]:
    """Report whether the agent can run, and what to do if not.

    Two separate failures, deliberately reported apart. The CLI can be missing, or a
    stray `ANTHROPIC_API_KEY` can be shadowing the subscription login — and that
    second one is the expensive one, because nothing *breaks*: requests just quietly
    bill an API account instead of the plan you already pay for. An empty value still
    counts as set and still wins.
    """
    if os.environ.get("ANTHROPIC_API_KEY") is not None:
        return False, (
            "ANTHROPIC_API_KEY is set in this environment. It overrides your Claude "
            "subscription, so the agent would bill an API account instead.\n"
            + ("  setx ANTHROPIC_API_KEY \"\" && set ANTHROPIC_API_KEY="
               if os.name == "nt" else "  unset ANTHROPIC_API_KEY")
        )
    from . import toolchain

    root = Path(__file__).resolve().parents[2]
    if (shutil.which("claude") or shutil.which("claude.cmd")
            or toolchain.cli_exe(root).exists()):
        return True, ""
    # No longer an instruction to go and install two runtimes by hand: the setup page
    # in the app does it. This line exists for someone reading the console.
    return False, (
        "The Claude Code CLI is not installed yet, so the chat cannot run. Everything "
        "else works.\n  The app will offer to install it — or do it yourself with\n"
        "  npm install -g @anthropic-ai/claude-code"
    )


BAR_WIDTH = 24

# Windows consoles before Terminal render box-drawing characters as mojibake, and a bar
# that shows as question marks is worse than no bar. ASCII there, blocks everywhere else.
_FILL, _EMPTY = ("#", "-") if os.name == "nt" else ("\u2588", "\u2500")


def _progress_printer(label: str, *, step: str = "", window=None):
    """Progress for one download: into the window when there is one, the console when not.

    Bytes rather than steps, and a bar rather than a bare percentage. A step counter sits
    at 60% through a 40 MB download and says nothing useful; a percentage alone does not
    show that anything is still moving between updates on a slow line. So a bar, the
    percentage, and the megabytes — which is the number someone uses to decide whether to
    wait or go and do something else.

    The console line is redrawn with `\r` and padded, because a shorter line drawn over a
    longer one leaves the tail of the old one behind and reads as corruption.
    """
    state = {"shown": -1}
    prefix = f"{step} " if step else ""

    def report(done: int, total: int) -> None:
        if window is not None:
            window.progress(done, total)
            return
        if not total:
            return
        fraction = min(1.0, max(0.0, done / total))
        percent = int(fraction * 100)
        # Every 2% keeps it visibly moving without redrawing on every 8 KB chunk.
        if percent < state["shown"] + 2 and percent != 100:
            return
        state["shown"] = percent
        filled = int(fraction * BAR_WIDTH)
        bar = _FILL * filled + _EMPTY * (BAR_WIDTH - filled)
        size = f"{done / 1_048_576:5.1f} / {total / 1_048_576:.1f} MB"
        line = f"  {prefix}{label:<22} [{bar}] {percent:3d}%  {size}"
        print(f"\r{line:<78}", end="\n" if percent == 100 else "", flush=True)

    return report


def install_toolchain(root: Path) -> list[str]:
    """Install the tools the app needs, now, before it opens. Returns what is still missing.

    This used to only *check*, print a warning, and open the app anyway — so a first run
    landed on a working chat with no rendering, or a rendering app with no chat, and the
    fix was to find a page inside the app and click a button on it. That was reported,
    twice, as the app asking to be installed after it had said it was installed. Clicking
    the launcher is the operator saying "set this up"; making them then go and ask for the
    rest of the setup is the launcher not doing its job.

    Nothing here is fatal. A download that fails leaves the app usable minus one
    capability, and the reason is printed with what would fix it — the alternative is an
    app that will not open because a video encoder could not be fetched, which is worse
    than an app that opens and says rendering is unavailable.
    """
    from . import toolchain

    missing = [tool for tool in toolchain.inventory(root) if not tool.present]
    if not missing:
        return []

    # A window when one can be drawn, the console when it cannot. `setup_window` is
    # tkinter — standard library — because this runs before the virtualenv exists and a
    # toolkit that needs installing cannot draw the window that installs things.
    from . import setup_window

    window = setup_window.open([tool.label for tool in missing]) or setup_window.silent()
    gui = not isinstance(window, setup_window._Silent)

    # Named before anything is downloaded, because the honest thing to show someone
    # waiting is what they are waiting for — and the total, so the bar that follows is
    # one of a known number rather than an unbounded sequence.
    say(f"{len(missing)} to install: " + ", ".join(tool.label for tool in missing))

    unresolved: list[str] = []
    for index, tool in enumerate(missing, start=1):
        step = f"[{index}/{len(missing)}]"
        window.begin(tool.label)
        if tool.manual:
            # ffmpeg on macOS and Linux, where a package manager owns it and dropping a
            # private build in its place is not this installer's business.
            #
            # `finish` before `continue`, which it did not do. The row stayed on "▸" —
            # the in-progress marker — for the rest of the run, so a step that was never
            # going to be attempted looked like a step still being attempted. That was
            # reported: a window headed "Finished, with some things left to do" above a
            # row that was apparently still working.
            unresolved.append(f"{tool.label} — install it with: {tool.manual}")
            window.finish(tool.label, ok=False)
            continue
        report = _progress_printer(tool.label, step=step,
                                   window=window if gui else None)
        # `on_note` and `on_tick` are keyword-only and default to None, so omitting them
        # was silent: `run_watched`'s `if tick is not None` never fired and nothing
        # pumped Tk for the whole of `npm install -g`. That is the exact
        # "(Not Responding)" freeze `run_watched` and `SetupWindow.tick` were written to
        # fix, and adding the Codex step doubled the frozen interval. Measured at zero
        # redraws where about twenty-four were due.
        try:
            if tool.key == "ffmpeg":
                ok, detail = toolchain.install_ffmpeg(root, report)
            elif tool.key == "node":
                toolchain.install_node(root, report)
                ok, detail = True, ""
            elif tool.key == "claude":
                # Node first: the CLI is installed with the bundled npm, and on a
                # platform whose wheel carries no CLI there may be no npm yet.
                if not toolchain.npm_exe(root).exists() and not shutil.which("npm"):
                    toolchain.install_node(root, _progress_printer(
                        "Node.js", step=step, window=window if gui else None))
                ok, detail = toolchain.install_claude_cli(
                    root, report, on_note=window.note, on_tick=window.tick)
            elif tool.key == "codex":
                # Node first for the same reason, and here on every platform: npm is the
                # only way this CLI arrives, so without it the step can only fail.
                if not toolchain.npm_exe(root).exists() and not shutil.which("npm"):
                    toolchain.install_node(root, _progress_printer(
                        "Node.js", step=step, window=window if gui else None))
                ok, detail = toolchain.install_codex_cli(
                    root, report, on_note=window.note, on_tick=window.tick)
            else:                                                  # pragma: no cover
                continue
        except Exception as exc:
            # Deliberately broad. Every installer here reaches the network and the
            # filesystem, and there is no failure among them worth refusing to open the
            # app over. The reason is printed rather than swallowed.
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        window.finish(tool.label, ok=bool(ok))
        if not ok:
            unresolved.append(f"{tool.label} — {detail or 'could not be installed'}")

    # Left open on failure with the x showing, because a window that vanishes at the
    # moment something went wrong takes the only explanation with it.
    window.done("Everything is installed." if not unresolved else
                "Finished, with some things left to do.")
    if not unresolved:
        window.close()
    elif gui:
        # And *kept alive* while it is open. Leaving it up was right; leaving it up
        # without redrawing it was not. Nothing pumped Tk after this point — the launcher
        # went on to start the server — so Windows marked the window "(Not Responding)"
        # and the Close button it had just enabled did nothing. A window left open to
        # explain a failure has to be a window that can be read and dismissed.
        _wait_for_close(window)
    return unresolved


# How long to keep the failure window alive. Bounded rather than indefinite: this blocks
# the launcher, and an operator who walked away must not come back to an app that never
# started. Ten minutes is far longer than reading two lines takes.
FAILURE_WINDOW_SECONDS = 600.0


def _wait_for_close(window) -> None:
    """Pump the window until it is closed, or the budget runs out.

    Both exits matter. Closing it is the operator saying "read it, carry on", and the app
    then starts normally. The timeout is for the case where nobody is watching — the app
    still comes up, minus whatever could not be installed, which is the behaviour every
    other failure here already has.
    """
    import time

    deadline = time.monotonic() + FAILURE_WINDOW_SECONDS
    while time.monotonic() < deadline:
        try:
            window.tick()
        except Exception:                                            # pragma: no cover
            return                                                   # already gone
        if not _window_alive(window):
            return
        time.sleep(0.05)


def _window_alive(window) -> bool:
    """Whether the Tk window still exists.

    `winfo_exists` rather than catching an exception from `tick`: a destroyed root raises
    on some Tk builds and returns quietly on others, and a loop that depends on which
    one is a loop that spins for ten minutes on the wrong platform.
    """
    root = getattr(window, "_root", None)
    if root is None:
        return False
    try:
        return bool(root.winfo_exists())
    except Exception:
        return False


def prepare(root: Path, *, force_install: bool = False) -> Path:
    """Run every preparation step. Returns the interpreter the app should run under."""
    check_python()
    python = ensure_venv(root)
    install_dependencies(root, python, force=force_install)
    ensure_env_file(root)

    for problem in install_toolchain(root):
        say("could not install: " + problem)

    # Asked again after installing, so what is reported is the state the app will
    # actually start in rather than the state it was in when the launcher opened.
    for ok, warning in (check_ffmpeg(), check_claude()):
        if not ok:
            say("warning: " + warning.replace("\n", "\n  "))
    return python
