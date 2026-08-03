"""Everything Forgecast needs that is not Python, fetched into `./runtime`.

## Why this exists

The app used to *report* what was missing. ffmpeg absent: a banner. The Claude Code
CLI absent: a paragraph telling you to install Node and run npm. Both were honest and
both were the wrong shape for something you double-click — being told to go and
install two other runtimes is not setup, it is homework.

So the launcher installs them. Everything lands in `./runtime` beside the app, nothing
goes on the machine, and deleting the folder is the uninstall.

## What each one is for

* **ffmpeg** — the render stage. Nothing else needs it, which is why the app still
  starts without it.
* **Node + the Claude Code CLI** — the chat. The agent SDK is the Python half only; it
  drives the real CLI, and the CLI is a Node program. Two runtimes is not a design
  choice, it is what the SDK is.
* **The Codex CLI** — the same chat on the ChatGPT backend. It was left out of this
  module for a while, which was reported as "chatgpt cli isn't installing properly".
  It was not installing badly; it was never being installed, so the backend only ever
  worked for someone who had run `npm install -g @openai/codex` themselves. That is
  the homework this module exists to remove, and it is now installed like the rest.

## Rules this file follows

**Stdlib only.** It runs before the virtual environment exists, so `httpx` and
friends are not importable yet. urllib, zipfile, tarfile, subprocess.

**Nothing is re-downloaded.** `missing()` probes what is already there. Setup gets
re-run — a connection drops, someone just wants to check — and a run that restarts
from zero reads as "none of that counted".

**Every download reports bytes, not steps.** A step-counting bar sits at 60% through
a 40 MB download, which is worse than no bar at all.

**Windows gets the downloads; macOS and Linux get a command.** Not laziness: `brew`
and `apt` are how software arrives on those platforms, they put ffmpeg somewhere the
whole machine can use it, and second-guessing them by unpacking a static build into
an app folder is the kind of helpfulness that produces two ffmpegs of different
versions. Node is downloaded everywhere, because the CLI has to be *this* app's copy
for the agent to find it reliably.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

# Pinned. "latest" turns a working install into a broken one on a Tuesday, and the
# whole point of a bundled runtime is that it does not move underneath you.
NODE_VERSION = "22.14.0"
FFMPEG_WIN_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
CLI_PACKAGE = "@anthropic-ai/claude-code"
# Named here rather than read from `codex_auth.PACKAGE`: this module has to keep working
# on a bare interpreter where the agent package may not import at all, and a constant
# that disappears with an ImportError is a constant that cannot be used in the install.
CODEX_PACKAGE = "@openai/codex"

# Rough download sizes in MB, used to weight the progress bar so it tracks reality.
WEIGHT_NODE = 30
WEIGHT_FFMPEG = 80
WEIGHT_CLI = 12
# Heavier than the Claude CLI because the package carries a native build of the agent
# rather than only JavaScript.
WEIGHT_CODEX = 25


def runtime_dir(root: Path) -> Path:
    return root / "runtime"


# ------------------------------------------------------------------ platform bits


def _node_asset() -> tuple[str, str]:
    """The Node archive for this machine, as (url, top-level-directory-name).

    Node's archives contain one top directory named after the build, and unpacking
    has to strip it — otherwise the binaries land at
    `runtime/node/node-v22.14.0-win-x64/node.exe`, which nothing looks for.
    """
    machine = platform.machine().lower()
    arm = machine in ("arm64", "aarch64")

    if os.name == "nt":
        arch = "arm64" if arm else "x64"
        name = f"node-v{NODE_VERSION}-win-{arch}"
        return f"https://nodejs.org/dist/v{NODE_VERSION}/{name}.zip", name
    if sys.platform == "darwin":
        arch = "arm64" if arm else "x64"
        name = f"node-v{NODE_VERSION}-darwin-{arch}"
        return f"https://nodejs.org/dist/v{NODE_VERSION}/{name}.tar.gz", name
    arch = "arm64" if arm else "x64"
    name = f"node-v{NODE_VERSION}-linux-{arch}"
    return f"https://nodejs.org/dist/v{NODE_VERSION}/{name}.tar.xz", name


def run_watched(command: list[str], *, on_line=None, tick=None, timeout: float = 900.0,
                env: dict | None = None, cwd: str | None = None) -> tuple[int, str]:
    """Run a child process without the caller's window freezing.

    ## The failure this fixes

    Reported: the setup window opened, showed its checklist, and then stopped responding —
    Windows greys the title bar and adds "(Not Responding)" — so it looked hung and was
    closed mid-install.

    It was not hung. The window is drawn by pumping Tk between chunks of work, on the main
    thread, because the install *is* the program and a worker thread touching Tk widgets
    crashes on macOS. That works when the work arrives in chunks. It does not work for
    `subprocess.run`, which blocks the one thread that can redraw for as long as the child
    takes — and `npm install -g` takes minutes while printing almost nothing.

    So the child runs here with its output on a pipe, read by a reader thread, while the
    calling thread loops: poll the child, call `tick()`, sleep briefly. `tick` is the
    window's redraw, so it happens about twelve times a second no matter how silent the
    child is. The window stays alive; the work still owns the main thread.

    ## Why the output is both streamed and returned

    `on_line` gets each line as it arrives, which is what puts "fetching…" under the
    progress bar instead of a bar that sits still for two minutes. The full text comes back
    as well, because a failure has to be reportable after the fact — and a failure whose
    output only ever went to a window that has since closed is a failure with no reason
    attached, which is the bug this app has already had once.
    """
    import threading
    import time

    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors="replace", bufsize=1, env=env, cwd=cwd, **_no_window(),
        )
    except OSError as exc:
        return 1, f"{type(exc).__name__}: {exc}"

    collected: list[str] = []

    def drain() -> None:
        # Its own thread because `readline` blocks, and blocking is the thing being
        # avoided. Only appends and calls back; it never touches a widget.
        assert process.stdout is not None
        for line in process.stdout:
            stripped = line.rstrip()
            collected.append(stripped)
            if on_line is not None and stripped:
                on_line(stripped)

    reader = threading.Thread(target=drain, name="forgecast-child-output", daemon=True)
    reader.start()

    deadline = time.monotonic() + timeout
    while process.poll() is None:
        if tick is not None:
            tick()
        if time.monotonic() > deadline:
            process.kill()
            collected.append(f"timed out after {int(timeout)}s")
            break
        # Twelve redraws a second: smooth enough that the window never reads as hung,
        # infrequent enough to cost nothing measurable against a download.
        time.sleep(0.08)

    # Joined with a bound rather than indefinitely. The child has exited by here, so the
    # pipe is closed and the reader returns — but a reader that somehow does not must not
    # hold the install open forever.
    reader.join(timeout=5.0)
    return (process.returncode if process.returncode is not None else 1,
            "\n".join(collected))


def _no_window() -> dict:
    """Creation flags that keep a child process from opening a console.

    Only meaningful on Windows, and only when the parent has no console of its own —
    which is exactly the case for a double-clicked app. Elsewhere it is an empty dict
    so the call sites stay identical on every platform.
    """
    flag = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return {"creationflags": flag} if flag else {}


_CONSOLE_FLAGS_HIDDEN = False

# Flags that mean the caller has already decided about the console. Adding
# CREATE_NO_WINDOW on top of any of them is either contradictory or ignored, so a
# caller that said something explicit is left alone.
_CONSOLE_DECIDED = (
    getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    | getattr(subprocess, "DETACHED_PROCESS", 0)
    | getattr(subprocess, "CREATE_NO_WINDOW", 0)
)


def hide_child_consoles() -> bool:
    """Stop every child process opening a black console window on Windows.

    ## The failure this prevents

    A console application started by a windowed parent gets a console of its own, and
    Windows raises it and gives it focus. This app starts several: the Claude CLI, once
    per turn, and ffmpeg, once per render step. The operator's report was a black window
    titled `claude` appearing over their work, repeatedly, while they were using the app —
    and it is the same complaint they had made about another app and asked us not to
    repeat.

    ## Why this patches `Popen.__init__` rather than passing a flag

    The flag is per-spawn, and the spawn that matters is not ours. `claude_agent_sdk`
    calls `anyio.open_process(...)` with a fixed argument list and no hook for creation
    flags (see `_internal/transport/subprocess_cli.py`), so there is nothing to pass.

    Rebinding the name `subprocess.Popen` would not work either: asyncio's Windows
    support defines `asyncio.windows_utils.Popen` as a subclass, captured at import time,
    so it would keep inheriting from the original. Patching the *method* is what reaches
    both — a subclass that does not override `__init__` gets the wrapped one.

    ## What will break it

    An SDK or CPython release that stops routing through `subprocess.Popen.__init__`.
    That is why `tests/test_toolchain.py` asserts the wrapper is reached and that a
    caller's own creation flags survive it, rather than only asserting the flag value.

    Called only from the desktop launcher, never from a server deployment: patching the
    standard library is a heavy thing to do to a process, and a hosted install has no
    console to protect. Returns whether it did anything, and is safe to call twice.
    """
    global _CONSOLE_FLAGS_HIDDEN

    quiet = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if _CONSOLE_FLAGS_HIDDEN or os.name != "nt" or not quiet:
        return False

    original = subprocess.Popen.__init__

    def __init__(self, *args, **kwargs):
        if not kwargs.get("creationflags", 0) & _CONSOLE_DECIDED:
            kwargs["creationflags"] = kwargs.get("creationflags", 0) | quiet
        original(self, *args, **kwargs)

    subprocess.Popen.__init__ = __init__
    _CONSOLE_FLAGS_HIDDEN = True
    return True


def node_bin(root: Path) -> Path:
    return runtime_dir(root) / "node"


def npm_exe(root: Path) -> Path:
    directory = node_bin(root)
    return directory / ("npm.cmd" if os.name == "nt" else "bin/npm")


def node_exe(root: Path) -> Path:
    directory = node_bin(root)
    return directory / ("node.exe" if os.name == "nt" else "bin/node")


def cli_exe(root: Path) -> Path:
    """Where the CLI ends up after a `--prefix` install into the runtime.

    npm's global layout differs by platform: Windows puts shims in the prefix root,
    everything else puts them in `prefix/bin`. Getting this wrong means installing
    the CLI successfully and then reporting it as missing.
    """
    directory = node_bin(root)
    return directory / ("claude.cmd" if os.name == "nt" else "bin/claude")


def codex_exe(root: Path) -> Path:
    """The shim npm writes for the Codex CLI, in the same prefix and by the same rules.

    Only ever a fallback answer to "is it there". What actually runs is the package's
    own `bin/codex.js` under a bundled node — see `codex_entry` and `codex_auth._argv` —
    because on Windows this shim is a `.cmd` and `CreateProcess` cannot execute one.
    """
    directory = node_bin(root)
    return directory / ("codex.cmd" if os.name == "nt" else "bin/codex")


def codex_entry(root: Path) -> Path | None:
    """The Codex package's entry script under the runtime prefix, or None.

    Both layouts are checked, in the order `codex_auth._bundled_js` checks them, and
    that agreement is the whole point of the function: npm's `--prefix` install puts
    packages under `lib/node_modules` on POSIX and directly under `node_modules` on
    Windows, so an installer that only knew one of them would report a perfectly good
    install as missing on the other platform.
    """
    for base in (node_bin(root) / "lib" / "node_modules", node_bin(root) / "node_modules"):
        script = base / "@openai" / "codex" / "bin" / "codex.js"
        if script.is_file():
            return script
    return None


def ffmpeg_bin(root: Path) -> Path:
    return runtime_dir(root) / "ffmpeg" / "bin"


def ffmpeg_exe(root: Path) -> Path:
    return ffmpeg_bin(root) / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")


# ----------------------------------------------------------------------- probing


@dataclass
class Tool:
    key: str
    label: str
    weight: int
    present: bool
    where: str
    # Set when the tool cannot be installed automatically on this platform.
    manual: str = ""

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "present": self.present,
                "where": self.where, "manual": self.manual}


def claude_where(root: Path) -> str:
    """Where a *runnable* Claude Code CLI is, or "" when there is none.

    The sibling of `codex_where`, and it should have existed from the start. Without it
    `install_claude_cli` verified its own work with `cli_exe(root).exists()` — a file
    check, which passes for the `claude.cmd` npm writes on Windows. `auth.find_cli()`
    refuses that shim, because the SDK will not spawn a batch script. So the installer
    returned success naming a file that the rest of the app treats as absent: one run
    logging both "Claude Code CLI ready at …claude.cmd" and "Still missing: Claude Code
    CLI", with a Try again button that could never succeed.

    The disk probe is the fallback for the launcher's pre-virtualenv run, where the
    agent package cannot be imported. It can only say whether *something* is there,
    which is enough to decide whether to download; the real check runs later.
    """
    try:
        from ..agent import auth as claude_auth
    except ImportError:                                             # pragma: no cover
        claude_auth = None

    if claude_auth is not None:
        found = claude_auth.find_cli()
        return str(found) if found else ""

    candidate = cli_exe(root)
    return str(candidate) if candidate.exists() else ""


def codex_where(root: Path) -> str:
    """Where a *runnable* Codex CLI is on this machine, or "" when there is none.

    Asked through `codex_auth.find_cli` for the same reason the Claude entry is asked
    through `auth.find_cli`: it already knows about this app's own runtime copy, about
    PATH, and about the Windows `.cmd` shim — which Python cannot spawn directly, so a
    probe that just looks for a file called `codex` reports connected on a machine where
    the first message dies with WinError 193. One question, one answer, in one place.

    The disk probe below it is the fallback for the launcher's pre-virtualenv run, where
    the agent package may not import. It can only say whether *something* is there, which
    is enough to decide whether to download; the real check runs later, inside the
    virtualenv, where it works.
    """
    try:
        from ..agent import codex_auth
    except ImportError:                                             # pragma: no cover
        codex_auth = None

    if codex_auth is not None:
        return codex_auth.cli_label(codex_auth.find_cli())

    entry = codex_entry(root)
    if entry is not None:
        return str(entry)
    if codex_exe(root).exists():
        return str(codex_exe(root))
    return shutil.which("codex") or ""


def inventory(root: Path) -> list[Tool]:
    """What is here, before a single byte is downloaded.

    A tool already on PATH counts. Downloading a second ffmpeg next to the one someone
    deliberately installed is not being helpful.

    Each CLI is asked about through the module that runs it — `agent.auth.find_cli` for
    Claude, `agent.codex_auth.find_cli` for Codex — never by looking for the name
    directly, and that is not tidiness. The Claude SDK resolves its own bundled binary
    before it looks at PATH, and on Windows npm's `.cmd` shim is unusable for both: the
    SDK refuses to spawn a batch script, and `CreateProcess` cannot execute one at all.
    So a probe that just checks "is there something called claude" reports connected on
    a machine where the first message dies. One question, one answer, in one place.
    """
    # Imported here, and tolerantly. `inventory()` runs from the launcher on the system
    # interpreter before the virtualenv exists, so anything this reaches must survive a
    # bare Python. If a future import in the agent package breaks that again, the answer
    # is a filesystem probe and a working launcher rather than a traceback on first run.
    try:
        from ..agent import auth
    except ImportError:                                             # pragma: no cover
        auth = None

    tools: list[Tool] = []

    on_path = shutil.which("ffmpeg") and shutil.which("ffprobe")
    bundled_ffmpeg = ffmpeg_exe(root).exists()
    manual = ""
    if not (on_path or bundled_ffmpeg) and os.name != "nt":
        manual = ("brew install ffmpeg" if sys.platform == "darwin"
                  else "sudo apt install ffmpeg")
    tools.append(Tool(
        key="ffmpeg", label="ffmpeg (rendering)", weight=WEIGHT_FFMPEG,
        present=bool(on_path or bundled_ffmpeg),
        where=(str(ffmpeg_exe(root)) if bundled_ffmpeg else (shutil.which("ffmpeg") or "")),
        manual=manual,
    ))

    # `find_cli` is the right answer and a disk probe is the honest fallback: the SDK
    # resolves its own bundled binary before PATH and refuses npm's `claude.cmd` shim, so
    # only `auth` can tell "installed" from "installed unusably". Without it the probe can
    # still say whether *something* is there, which is enough to decide whether to
    # download — and the real check runs later, inside the virtualenv, where it works.
    cli = auth.find_cli() if auth is not None else (
        str(cli_exe(root)) if cli_exe(root).exists() else (shutil.which("claude") or "")
    )
    # No longer marked manual on Windows. It was, with a PowerShell one-liner printed for
    # the operator to run — on the reasoning that a machine-wide installer is not this
    # app's business. That reasoning lost to the evidence: setup finished saying "some
    # things left to do", the chat had no CLI, and the app had asked its user to go and
    # finish installing it. That is exactly the homework this module's docstring says it
    # exists to remove, and it was reported as a broken install rather than as a choice.
    #
    # `install_claude_cli` now runs that official installer itself on Windows and falls
    # back to the printed command only if it fails. What it cannot preserve is "deleting
    # the folder is the uninstall" — the native installer writes to the user profile — so
    # that is said in the setup UI rather than glossed over.
    cli_manual = ""
    tools.append(Tool(
        key="claude", label="Claude Code CLI (the chat)", weight=WEIGHT_CLI,
        present=bool(cli), where=cli or "", manual=cli_manual,
    ))

    # The ChatGPT backend's half of the same job, and it was missing from this list
    # entirely — which is why it was reported as installing improperly. Nothing installed
    # it, so the setup page never offered it, and `codex_auth.check()` told everyone who
    # picked ChatGPT to go and run npm themselves. No `manual` on any platform: unlike
    # ffmpeg there is no package manager that owns this, and unlike the Claude CLI on
    # Windows there is no vendor installer to defer to — one npm install is the whole
    # story, so the app does it.
    codex = codex_where(root)
    tools.append(Tool(
        key="codex", label="Codex CLI (the ChatGPT chat)", weight=WEIGHT_CODEX,
        present=bool(codex), where=codex,
    ))

    # Node is listed only when something still needs it, and either CLI can be that
    # something. It stays hidden once they are here: a 30 MB JavaScript runtime on the
    # setup page of an app that makes videos invites the reasonable question of why, and
    # answering "for a download you did not need" is the wrong answer.
    #
    # The Codex clause carries no platform test, and that is the correction. The Claude
    # one has one because Windows gets its CLI from a vendor installer that brings its
    # own runtime, so Node there would be for nothing. Codex has no bundled build on any
    # platform and no installer but npm, so on Windows the old condition offered the CLI
    # with nothing to run it — an install that could only fail, reported as npm's fault.
    if not codex or (not cli and os.name != "nt"):
        have_node = node_exe(root).exists() or bool(shutil.which("node"))
        tools.append(Tool(
            key="node", label="Node.js (to install the chat CLIs)", weight=WEIGHT_NODE,
            present=have_node,
            where=(str(node_exe(root)) if node_exe(root).exists()
                   else (shutil.which("node") or "")),
        ))
    return tools


def missing(root: Path) -> list[Tool]:
    return [tool for tool in inventory(root) if not tool.present and not tool.manual]


# --------------------------------------------------------------------- fetching


def _download(url: str, dest: Path, on_progress=None) -> Path:
    """Stream a URL to disk, reporting bytes as they arrive.

    Written to a `.part` file and moved into place at the end, so a connection that
    drops halfway does not leave something that looks like a finished download and
    fails to unpack on the next run.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "Forgecast-setup"})

    with urllib.request.urlopen(request, timeout=60) as response:
        total = int(response.headers.get("Content-Length") or 0)
        got = 0
        with open(part, "wb") as out:
            while chunk := response.read(1 << 18):
                out.write(chunk)
                got += len(chunk)
                if on_progress:
                    on_progress(got, total)

    part.replace(dest)
    return dest


def _unpack(archive: Path, into: Path, strip: str = "") -> Path:
    """Unpack a zip or tar, optionally stripping one leading directory.

    `strip` exists because Node's archives wrap everything in a build-named folder,
    and the app looks for `runtime/node/node.exe`, not
    `runtime/node/node-v22.14.0-win-x64/node.exe`.
    """
    into.mkdir(parents=True, exist_ok=True)
    staging = into.parent / (into.name + ".unpack")
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)

    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(staging)
    else:
        # `filter="data"` refuses absolute paths and links pointing outside the
        # destination. Python 3.14 makes it the default and warns before then; an
        # archive from the internet is exactly the case it exists for.
        with tarfile.open(archive) as tf:
            try:
                tf.extractall(staging, filter="data")
            except TypeError:                      # pragma: no cover - Python < 3.12
                tf.extractall(staging)

    source = staging
    if strip:
        candidate = staging / strip
        if candidate.is_dir():
            source = candidate
        else:
            # The archive named its top directory something else. Take the single
            # directory it does contain rather than failing on a version mismatch.
            entries = [p for p in staging.iterdir()]
            if len(entries) == 1 and entries[0].is_dir():
                source = entries[0]

    if into.exists():
        shutil.rmtree(into, ignore_errors=True)
    shutil.move(str(source), str(into))
    shutil.rmtree(staging, ignore_errors=True)
    return into


# --------------------------------------------------------------------- installers


def install_node(root: Path, on_progress=None) -> Path:
    """Node into `runtime/node`. Returns the node executable."""
    url, top = _node_asset()
    archive = runtime_dir(root) / Path(url).name
    if not node_exe(root).exists():
        _download(url, archive, on_progress)
        _unpack(archive, node_bin(root), strip=top)
        archive.unlink(missing_ok=True)
        if os.name != "nt":
            for name in ("node", "npm", "npx"):
                target = node_bin(root) / "bin" / name
                if target.exists():
                    target.chmod(0o755)
    return node_exe(root)


def _npm_env(root: Path) -> dict:
    """The environment every `npm install` here runs under. One copy, two installers."""
    env = dict(os.environ)
    # npm resolves its own node from PATH; the bundled one has to come first or a
    # system Node of the wrong major version answers instead.
    binaries = node_bin(root) / ("" if os.name == "nt" else "bin")
    env["PATH"] = str(binaries) + os.pathsep + env.get("PATH", "")
    # npm writes caches and logs; keeping them inside the app folder means the
    # uninstall really is "delete the folder".
    env["npm_config_cache"] = str(runtime_dir(root) / "npm-cache")
    return env


def install_claude_cli(root: Path, on_progress=None, *, on_note=None,
                      on_tick=None) -> tuple[bool, str]:
    """The CLI into `runtime/node`, using that same Node's npm.

    `--prefix` rather than a real global install: this app's copy, in this app's
    folder, uninstalled by deleting the folder. It also means the version cannot be
    changed underneath the app by something else on the machine.
    """
    npm = npm_exe(root)
    if not npm.exists():
        system_npm = shutil.which("npm")
        if not system_npm:
            if os.name == "nt":
                return _install_claude_windows(on_note=on_note, on_tick=on_tick)
            return False, ("Node is installed but npm was not found beside it, so the "
                           "Claude CLI cannot be installed.")
        npm = Path(system_npm)

    if on_progress:
        on_progress(0, WEIGHT_CLI * 1_000_000)

    env = _npm_env(root)

    # `run_watched`, not `subprocess.run`. This step takes minutes and prints almost
    # nothing, and a blocking call holds the only thread that can redraw the setup window —
    # which is why the window was reported as not responding. See `run_watched`.
    code, output = run_watched(
        [str(npm), "install", "-g", CLI_PACKAGE, "--prefix", str(node_bin(root))],
        on_line=on_note, tick=on_tick, timeout=900, env=env)

    if code != 0:
        tail = output.strip().splitlines()
        return False, "npm failed:\n" + "\n".join(tail[-6:])

    if on_progress:
        on_progress(WEIGHT_CLI * 1_000_000, WEIGHT_CLI * 1_000_000)

    # Verified through the module that actually runs it, not through a file existing.
    # `cli_exe(root).exists()` passes for the `claude.cmd` npm writes on Windows, and
    # `auth.find_cli()` refuses that shim — the SDK will not spawn a batch script. So a
    # successful npm install reported `(True, "...claude.cmd")` while the same run's
    # verdict said the CLI was still missing, and "Try again" was a loop with no exit.
    # `install_codex_cli` was written to check through `codex_where`; this one was not
    # brought up to that standard until it had shipped the contradiction.
    if not claude_where(root):
        # On Windows this is the known case — npm writes a shim the SDK refuses — so
        # instead of reporting a dead end, the official installer is tried, which is
        # what a person would do next anyway.
        if os.name == "nt":
            ok, detail = _install_claude_windows(on_note=on_note, on_tick=on_tick)
            if ok:
                return ok, detail
            return False, (f"npm succeeded but no CLI this app can run appeared at "
                           f"{cli_exe(root)}, and the official installer also "
                           f"failed:\n{detail}")
        return False, (f"npm succeeded but no CLI this app can run appeared at "
                       f"{cli_exe(root)}. Look in {node_bin(root)}.")
    return True, claude_where(root)


# Anthropic's own Windows installer. Named as a constant so there is one place to change
# it, and quoted exactly as they publish it.
CLAUDE_WIN_INSTALLER = "https://claude.ai/install.ps1"


def _install_claude_windows(*, on_note=None, on_tick=None) -> tuple[bool, str]:
    """Run the official Windows installer, rather than printing it for someone to run.

    ## Why this is here at all

    The npm-installed shim does not work on Windows, so for a while this step ended by
    telling the operator to paste `irm https://claude.ai/install.ps1 | iex` into
    PowerShell. Setup then reported "some things left to do", the chat had no CLI, and
    the app had asked its own user to finish installing it. An installer that hands out
    homework is the thing this module was written to stop.

    ## What it costs, and why it is said out loud

    This one writes into the user profile, not into `runtime/`, so after it runs
    "delete the folder" is no longer the whole uninstall. That is a real change to a
    promise the app makes, so it is reported in the returned detail and shown — not
    hidden because it is inconvenient.

    ## Why ExecutionPolicy Bypass and not a downgrade of it

    Scoped to this one process, which is the narrowest form that can work: the default
    policy on a normal Windows install refuses to run a downloaded script at all, and
    changing the machine's policy to fix that would outlive this call and every other
    script it then permits. `-Scope Process` cannot.
    """
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        return False, ("PowerShell was not found, so the official installer cannot be "
                       f"run. Install it by hand:  irm {CLAUDE_WIN_INSTALLER} | iex")

    if on_note:
        on_note("running Anthropic's installer for the Claude Code CLI")

    code, output = run_watched(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
         f"irm {CLAUDE_WIN_INSTALLER} | iex"],
        on_line=on_note, tick=on_tick, timeout=600)

    found = shutil.which("claude")
    if not found:
        # The installer puts it on PATH for *new* shells, so this process may not see it
        # yet. Checked where it actually lands before concluding it failed.
        for candidate in (Path.home() / ".local" / "bin" / "claude.exe",
                          Path.home() / ".local" / "bin" / "claude",
                          Path.home() / "AppData" / "Local" / "Programs" / "claude"
                          / "claude.exe"):
            if candidate.exists():
                found = str(candidate)
                break

    if not found:
        tail = "\n".join(output.strip().splitlines()[-6:])
        return False, (f"the official installer exited with {code} and no `claude` "
                       f"appeared.\n{tail}")

    return True, (f"{found}  (installed by Anthropic's own installer, so this one lives "
                  f"in your user profile rather than in runtime/ — deleting the Forgecast "
                  f"folder will not remove it)")


def install_codex_cli(root: Path, on_progress=None, *, on_note=None,
                      on_tick=None) -> tuple[bool, str]:
    """The Codex CLI into `runtime/node`, using that same Node's npm.

    The same shape as `install_claude_cli` and into the same prefix on purpose: one
    Node, one npm cache, one folder to delete. It has to be that prefix in particular
    because `codex_auth._bundled_js` looks for the package under `runtime/node` and
    spawns its `bin/codex.js` with the bundled node — a copy installed anywhere else
    would work from a terminal and be invisible to the app.

    There is no vendor installer to fall back to here, the way Windows has one for
    Claude, so every failure is reported as itself rather than papered over: no npm, a
    non-zero npm, or an npm that said yes and left nothing this app can run.
    """
    npm = npm_exe(root)
    if not npm.exists():
        system_npm = shutil.which("npm")
        if not system_npm:
            # Named as the missing thing it is. "The Codex CLI could not be installed"
            # sends someone to look at Codex; npm is what is absent, and Node is what
            # brings it — which is why `inventory` now offers Node whenever this tool
            # is missing, on every platform.
            return False, ("npm was not found — neither beside the bundled Node in "
                           f"{node_bin(root)} nor on PATH — so the Codex CLI cannot be "
                           "installed. Installing Node first provides it.")
        npm = Path(system_npm)

    if on_progress:
        on_progress(0, WEIGHT_CODEX * 1_000_000)

    # `run_watched` for the reason given above `install_claude_cli`'s call: this takes
    # minutes and prints almost nothing, and a blocking call holds the only thread that
    # can redraw the setup window.
    code, output = run_watched(
        [str(npm), "install", "-g", CODEX_PACKAGE, "--prefix", str(node_bin(root))],
        on_line=on_note, tick=on_tick, timeout=900, env=_npm_env(root))

    if code != 0:
        tail = output.strip().splitlines()
        return False, "npm failed:\n" + "\n".join(tail[-6:])

    if on_progress:
        on_progress(WEIGHT_CODEX * 1_000_000, WEIGHT_CODEX * 1_000_000)

    found = codex_where(root)
    if not found:
        # The failure `auth.py` documents for Windows shims, refused here rather than
        # reported as success: an install that produced nothing findable would take the
        # setup page green, the chip to "connected", and the first message to a crash.
        # npm's exit code is not evidence that this app can run what npm wrote, so the
        # answer to "can it be found" is the one that decides.
        entry = codex_entry(root)
        landed = (f"its entry script is at {entry}, so the lookup in "
                  "`codex_auth._bundled_js` is what missed it"
                  if entry is not None else
                  f"nothing was written under {node_bin(root)} at all")
        return False, (f"npm exited 0 but no Codex CLI this app can run was found — "
                       f"{landed}. Its own output:\n"
                       + "\n".join(output.strip().splitlines()[-6:]))

    return True, found


def install_ffmpeg(root: Path, on_progress=None) -> tuple[bool, str]:
    """ffmpeg into `runtime/ffmpeg`. Windows only — elsewhere use the package manager."""
    if os.name != "nt":
        return False, ("brew install ffmpeg" if sys.platform == "darwin"
                       else "sudo apt install ffmpeg")
    if ffmpeg_exe(root).exists():
        return True, str(ffmpeg_exe(root))

    archive = runtime_dir(root) / "ffmpeg.zip"
    try:
        _download(FFMPEG_WIN_URL, archive, on_progress)
    except (urllib.error.URLError, OSError) as exc:
        return False, f"could not download ffmpeg: {exc}"

    _unpack(archive, runtime_dir(root) / "ffmpeg", strip="ffmpeg")
    archive.unlink(missing_ok=True)

    if not ffmpeg_exe(root).exists():
        # The build's top folder is named with its version, which changes. Find the
        # binary wherever it landed and flatten to the layout the app expects.
        found = next(runtime_dir(root).joinpath("ffmpeg").rglob("ffmpeg.exe"), None)
        if found is None:
            return False, "the ffmpeg archive did not contain ffmpeg.exe"
        target = ffmpeg_bin(root)
        target.mkdir(parents=True, exist_ok=True)
        for name in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe"):
            source = found.parent / name
            if source.exists() and source.parent != target:
                shutil.copy2(source, target / name)
    return True, str(ffmpeg_exe(root))


# ------------------------------------------------------------------------ PATH


def activate(root: Path) -> dict[str, str]:
    """Put the bundled tools on PATH for this process and its children.

    Called at start-up rather than written into a shell profile. The app's own copies
    are for the app; putting them on the machine's PATH would mean an uninstall that
    leaves something behind, and a version of ffmpeg the user did not choose winning
    in their terminal.
    """
    added: list[str] = []
    for directory in (ffmpeg_bin(root), node_bin(root),
                      node_bin(root) / "bin"):
        if directory.is_dir():
            added.append(str(directory))

    if added:
        os.environ["PATH"] = os.pathsep.join(added) + os.pathsep + os.environ.get("PATH", "")

    # A set ANTHROPIC_API_KEY outranks the Claude subscription login and silently
    # bills an API account. An empty value still counts as set, so it is removed
    # rather than blanked — for this process only, which is the one that matters
    # because it is the one that spawns the CLI.
    shadowed = os.environ.pop("ANTHROPIC_API_KEY", None)

    return {"path_added": os.pathsep.join(added),
            "api_key_removed": "yes" if shadowed is not None else "no"}


def summary(root: Path) -> str:
    """One line per tool, for the launcher's banner."""
    lines = []
    for tool in inventory(root):
        state = "found" if tool.present else (tool.manual or "MISSING")
        lines.append(f"    {tool.label:<28} {state}")
    return "\n".join(lines)
