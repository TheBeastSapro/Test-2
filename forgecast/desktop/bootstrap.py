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

    say("installing dependencies (one time, a minute or two)")
    result = subprocess.run(
        [str(python), "-m", "pip", "install", "--disable-pip-version-check",
         "--quiet", "-e", "."],
        cwd=str(root),
    )
    if result.returncode != 0:
        raise BootstrapError(
            "dependency installation failed. Scroll up for pip's reason — the usual "
            "causes are no network access or a missing compiler toolchain."
        )
    stamp.write_text(wanted, encoding="utf-8")
    return True


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
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
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
    if shutil.which("claude") or shutil.which("claude.cmd"):
        return True, ""
    return False, (
        "The Claude Code CLI was not found, so the chat cannot run. Everything else "
        "works.\n  npm install -g @anthropic-ai/claude-code\n"
        "  then sign in with your Claude subscription — no API key."
    )


def prepare(root: Path, *, force_install: bool = False) -> Path:
    """Run every preparation step. Returns the interpreter the app should run under."""
    check_python()
    python = ensure_venv(root)
    install_dependencies(root, python, force=force_install)
    ensure_env_file(root)
    for ok, warning in (check_ffmpeg(), check_claude()):
        if not ok:
            say("warning: " + warning.replace("\n", "\n  "))
    return python
