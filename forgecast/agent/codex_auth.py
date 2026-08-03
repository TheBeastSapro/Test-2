"""Is ChatGPT actually connected, and if not, what exactly is wrong.

The sibling of `auth.py`, for the other agent. Same question, same refusal to guess,
and — this is the point of the whole ChatGPT backend — the same *kind* of answer:
you sign in to a plan you already pay for, and no key is pasted anywhere.

## It is a subscription, not an API key

`codex login` with no flags is the "Sign in with ChatGPT" browser flow; the API key is
the explicit opt-in (`codex login --with-api-key`, read from stdin). That is the
structural parallel to `claude login`, and it is why this backend can be offered
beside Claude honestly rather than as a paid-per-token consolation.
Verified against codex-cli 0.146.0 and
https://developers.openai.com/codex/auth (served as learn.chatgpt.com/docs/auth).

## The trap, which is worse than Claude's

`ANTHROPIC_API_KEY` shadowing a Claude login at least leaves `claude` reporting the
truth. `CODEX_API_KEY` does not: with it set, `codex login status` still prints
*Not logged in*, while a turn silently authenticates with the key and bills an API
account. Measured on 0.146.0 — with the variable set, a turn's 401 changes from
"Missing bearer or basic authentication" to "Incorrect API key provided", which is
proof the key was used. So the environment is checked here, first, before the CLI's
own answer is trusted.

`OPENAI_API_KEY` alone does *not* shadow it on this version, and is deliberately not
treated as a problem: refusing to start because an unrelated variable exists — the
pipeline's own OpenAI key lives in the same environment — would be a false alarm on a
correctly configured machine.

## Why sign-in is checked with a subprocess and not a prompt

`auth._credentials()` reads Claude's credentials off disk because sending a prompt to
find out whether a prompt would work spends money on every page load. Codex stores
its credential either in `$CODEX_HOME/auth.json` *or* in the OS keyring
(`cli_auth_credentials_store`), so a file check alone reports "not signed in" on a
perfectly good machine. `codex login status` answers it in ~120 ms, costs nothing, and
is the same answer. What is not acceptable is finding out by running a turn: with no
credential, `codex exec` spends about twenty seconds on five WebSocket retries and
five HTTPS retries and emits fifteen error events before failing.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("forgecast.agent.codex_auth")

PACKAGE = "@openai/codex"
INSTALL_HINT = f"npm install -g {PACKAGE}"

# How long the app waits for `login status`. Generous for a command that answered in
# 120 ms in testing: the number that matters is that a wedged CLI cannot hang the
# page, not how fast the happy path is.
STATUS_TIMEOUT = 15

APP_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class CodexStatus:
    """Deliberately the same field names as `auth.AuthStatus`.

    The chat renders one auth panel. Two shapes would mean two renderers and a page
    that shows a stale sentence for whichever backend the code forgot about.
    """

    ok: bool
    headline: str
    detail: str
    cli_found: bool = False
    cli_path: str = ""
    signed_in: bool = False
    api_key_shadowing: bool = False
    can_login: bool = False
    account: str = ""
    fixes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok, "headline": self.headline, "detail": self.detail,
            "cli_found": self.cli_found, "cli_path": self.cli_path,
            "signed_in": self.signed_in, "api_key_shadowing": self.api_key_shadowing,
            "can_login": self.can_login, "account": self.account, "fixes": self.fixes,
        }


def codex_home() -> Path:
    """Where the CLI keeps its credential, sessions and config."""
    override = (os.environ.get("CODEX_HOME") or "").strip()
    return Path(override) if override else Path.home() / ".codex"


# ------------------------------------------------------------------ finding the CLI


def _entry_script(package_root: Path) -> Path:
    return package_root / "bin" / "codex.js"


def _bundled_js() -> tuple[str, str] | None:
    """The app's own copy, as (node, codex.js), if `runtime/` has one.

    Returned as node-plus-script rather than as the shim npm also writes, because
    that is the one form that spawns identically on every platform. See `_argv`.
    npm's `--prefix` layout differs: POSIX puts packages under `lib/node_modules`,
    Windows directly under `node_modules`.
    """
    runtime = APP_ROOT / "runtime" / "node"
    node = runtime / ("node.exe" if os.name == "nt" else "bin/node")
    if not node.is_file():
        return None
    for base in (runtime / "lib" / "node_modules", runtime / "node_modules"):
        script = _entry_script(base / "@openai" / "codex")
        if script.is_file():
            return str(node), str(script)
    return None


def _sibling_js(shim: Path) -> str | None:
    """The real entry point beside a shim npm installed, if it is there.

    npm writes `codex.cmd` next to the package tree it came from. Finding the `.js`
    means the shim never has to be spawned at all.
    """
    for base in (shim.parent / "node_modules", shim.parent / "lib" / "node_modules"):
        script = _entry_script(base / "@openai" / "codex")
        if script.is_file():
            return str(script)
    return None


def _is_shim(path: str) -> bool:
    return path.replace("\\", "/").rsplit("/", 1)[-1].lower().endswith((".cmd", ".bat"))


def _argv(path: str) -> list[str]:
    """A command line this app can actually spawn for a CLI found at `path`.

    `auth._spawnable()` exists because the Claude SDK refuses npm's `claude.cmd`
    shim. The same shim exists for Codex, and Python hits it differently but just as
    hard: `CreateProcess` cannot execute a `.cmd` directly, so spawning it raises
    WinError 193 — "not a valid Win32 application" — which reads like a corrupt
    install rather than a wrapper script.

    Unlike Claude's case this is fixable here, because *this app* does the spawning:
    the shim's own package sits beside it, so `node …/bin/codex.js` runs the identical
    program with no batch layer. `cmd /c` is the last resort for a layout where the
    package cannot be found.
    """
    if not _is_shim(path):
        return [path]
    sibling = _sibling_js(Path(path))
    if sibling:
        node = shutil.which("node")
        if node:
            return [node, sibling]
    return ["cmd", "/c", path]


def find_cli() -> list[str] | None:
    """The command that runs Codex on this machine, or None.

    A list rather than a path: on Windows the answer is sometimes `node script.js`
    rather than a single executable, and collapsing that to a string would have every
    call site re-deciding how to split it.
    """
    bundled = _bundled_js()
    if bundled:
        return [bundled[0], bundled[1]]

    runtime = APP_ROOT / "runtime" / "node"
    for name in ("codex.cmd", "codex") if os.name == "nt" else ("bin/codex", "codex"):
        candidate = runtime / name
        if candidate.is_file():
            return _argv(str(candidate))

    for name in ("codex.exe", "codex.cmd", "codex") if os.name == "nt" else ("codex",):
        found = shutil.which(name)
        if found:
            return _argv(found)
    return None


def cli_label(argv: list[str] | None) -> str:
    """What to show as "where it is". The script, not the interpreter in front of it."""
    if not argv:
        return ""
    return argv[-1] if len(argv) > 1 else argv[0]


# ------------------------------------------------------------------------- sign-in


@dataclass
class LoginState:
    signed_in: bool
    account: str = ""
    with_api_key: bool = False
    detail: str = ""


def login_state(cli: list[str] | None = None) -> LoginState:
    """What `codex login status` says, normalised.

    Branching on the exit code and one substring rather than on the exact sentence:
    the wording of this output is not an API, and a parser that depends on it turns a
    cosmetic CLI change into "you are not signed in" on a machine that is.
    """
    argv = cli or find_cli()
    if not argv:
        return LoginState(False, detail="the Codex CLI was not found")
    try:
        done = subprocess.run([*argv, "login", "status"], capture_output=True,
                              text=True, timeout=STATUS_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        return LoginState(False, detail=f"{type(exc).__name__}: {exc}")

    text = f"{done.stdout}\n{done.stderr}".strip()
    if done.returncode != 0:
        return LoginState(False, detail=text)

    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    account = first
    for prefix in ("Logged in using ", "Logged in as ", "Logged in with ", "Logged in"):
        if first.startswith(prefix):
            account = first[len(prefix):].strip(" .:")
            break
    return LoginState(True, account=account,
                      with_api_key="api key" in text.lower(), detail=text)


def check() -> CodexStatus:
    """Run before offering the chat on this backend. Reports rather than guesses."""
    cli = find_cli()
    path = cli_label(cli)

    # First, because it is the one failure the CLI itself will not tell you about.
    if os.environ.get("CODEX_API_KEY") is not None:
        return CodexStatus(
            ok=False,
            headline="An API key is overriding your ChatGPT plan",
            detail=(
                "CODEX_API_KEY is set in this environment. Codex authenticates with it "
                "in preference to your ChatGPT sign-in, so every turn would bill an "
                "API account per token instead of using the plan you already pay for — "
                "and `codex login status` still reports \"Not logged in\", so nothing "
                "on screen would tell you. An empty value still counts as set."
            ),
            cli_found=bool(cli), cli_path=path, api_key_shadowing=True,
            fixes=[
                'Windows:  setx CODEX_API_KEY "" && set CODEX_API_KEY=',
                "macOS / Linux:  unset CODEX_API_KEY",
                "Then close this app and open it again — the value is read at start-up.",
            ],
        )

    if not cli:
        return CodexStatus(
            ok=False,
            headline="The Codex CLI is not installed",
            detail=(
                "ChatGPT runs this studio through OpenAI's Codex CLI, the same way "
                "Claude runs it through the Claude Code CLI — a local agent signed in "
                "with your own ChatGPT plan. It is a Node program, so it needs Node "
                "and one install. Claude is unaffected and still works."
            ),
            # The app's own installer first, and the npm line kept behind it. For a
            # while this list started at the npm line while nothing in the app installed
            # anything, so the only way forward was a terminal — which is what "chatgpt
            # cli isn't installing properly" was actually describing. `toolchain` now
            # fetches it into `runtime/`, so the button is named before the homework.
            fixes=["Open Setup in this app and press Install — it fetches the CLI into "
                   "runtime/ beside the app, so deleting the folder is the uninstall.",
                   f"Or do it yourself, anywhere Node is installed:  {INSTALL_HINT}",
                   "Then press Check again — no restart needed.",
                   "Or stay on Claude: it is the default and needs nothing new."],
        )

    state = login_state(cli)
    if not state.signed_in:
        return CodexStatus(
            ok=False,
            headline="Not signed in to ChatGPT yet",
            detail=(
                "The Codex CLI is installed but nobody has signed in on this machine. "
                "Press Sign in: a terminal opens running `codex login`, and you finish "
                "in the browser with your ChatGPT account. It is the plan you already "
                "pay for — there is no API key and you should not create one."
            ),
            cli_found=True, cli_path=path, can_login=True,
            fixes=["Press Sign in, then Check again once the browser is done.",
                   "On a machine with no browser:  codex login --device-auth  "
                   "(it prints a URL and a code to use elsewhere)."],
        )

    if state.with_api_key:
        # Signed in, so this works — it is just not what was asked for, and the
        # difference is money. Reported as connected with the caveat in the sentence
        # rather than as an error, because failing a working setup is its own bug.
        return CodexStatus(
            ok=True,
            headline="Connected with an OpenAI API key",
            detail=(
                "This is an API-key sign-in, not your ChatGPT plan: every turn bills "
                "per token against an API account. It works. To use the subscription "
                "instead, run `codex logout` then press Sign in."
            ),
            cli_found=True, cli_path=path, signed_in=True,
            account=state.account or "API key",
            fixes=["codex logout", "then press Sign in for the ChatGPT browser flow."],
        )

    return CodexStatus(
        ok=True,
        headline="Connected with your ChatGPT subscription",
        detail=(
            "ChatGPT can run this studio: research a niche, set up a channel, write "
            "and check a script, tune the voice, build the edit and preview it before "
            "anything renders. It holds the same studio tools Claude does, with one "
            "exception — it cannot stop mid-turn to ask, so it is never given the gate."
        ),
        cli_found=True, cli_path=path, signed_in=True, account=state.account,
    )


def start_login() -> tuple[bool, str]:
    """Open a visible terminal running `codex login`.

    The same choice as `auth.start_login()`, for the same reason: the sign-in ends in
    a browser, and a browser flow driven from behind the UI looks like nothing
    happening. Codex is friendlier than Claude here — `codex login` is a real
    subcommand rather than a slash command inside a TUI — but it still waits on a
    local callback, so it needs a window that stays open.
    """
    cli = find_cli()
    if not cli:
        return False, f"The Codex CLI was not found. Install it: {INSTALL_HINT}"

    command = [*cli, "login"]
    try:
        if os.name == "nt":
            subprocess.Popen(["cmd", "/k", *command],
                             creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        elif shutil.which("open"):                                        # macOS
            # `open -a Terminal` takes a file to open, not a command with arguments,
            # so the command becomes a one-line script. Passing the argv straight
            # through opens Terminal with no command and looks like a dead button.
            subprocess.Popen(["osascript", "-e",
                              'tell application "Terminal" to do script '
                              f'"{" ".join(command)}"',
                              "-e", 'tell application "Terminal" to activate'])
        else:
            terminal = next(
                (t for t in ("x-terminal-emulator", "gnome-terminal", "konsole",
                             "xterm") if shutil.which(t)), "")
            if not terminal:
                return False, (
                    "No terminal emulator was found to open. Run this yourself in a "
                    "shell, finish in the browser, then press Check again:\n\n    "
                    + " ".join(command))
            subprocess.Popen([terminal, "-e", *command])
    except OSError as exc:
        return False, f"Could not open a terminal: {type(exc).__name__}: {exc}"

    return True, ("A terminal opened running codex login. Finish in the browser, then "
                  "close it and press Check again.")
