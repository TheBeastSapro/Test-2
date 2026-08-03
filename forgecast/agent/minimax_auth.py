"""Is MiniMax signed in, and on what — the plan, or a key.

## Why this exists

The operator has a MiniMax subscription and asked to use it rather than pay per token.
Their subscription covers `mmx`, MiniMax's own CLI, which authenticates by OAuth in a
browser exactly the way Claude Code and Codex do. So the same trick works: sign in to the
plan once, and let the CLI spend it.

What the subscription does **not** cover is text-to-speech. `providers.media`'s MiniMax
voice adapter bills the API balance per character and says so, and nothing in this file
changes that — there is no CLI subcommand, no scope and no token that routes T2A through
the plan. Two different MiniMax things, paid for two different ways, and conflating them
would be a lie about someone's money.

## Verified rather than assumed

Every string below was read off `mmx-cli` itself, not from documentation:

* `mmx auth login [--api-key <key>] [--recommend] [--region=global|cn]` — `--recommend`
  skips the menu and goes straight to OAuth, which is the subscription flow.
* `mmx auth status --output json` — reports `{"error": {"code": 3, "message": "No
  credentials found.", "hint": …}}` when nobody has signed in.
* `mmx config show --output json` — `region`, `base_url`, `config_file`.
* Credentials live at `~/.mmx/config.json`, and `MMX_CONFIG_DIR` moves them.

## One hazard this backend does *not* have

Claude and Codex both read an API key out of the environment in preference to the plan —
`ANTHROPIC_API_KEY`, `CODEX_API_KEY` — which silently moves spend from a subscription to
an invoice, and both of those are checked for and reported. `mmx` does not: setting
`MMX_API_KEY` was tested and `auth status` still reports no credentials. A key can only
arrive through `--api-key`, which is an argument this app constructs and never passes. So
there is no environment check here, because inventing one would imply a danger that was
measured and found not to exist.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("forgecast.agent.minimax_auth")

PACKAGE = "mmx-cli"
INSTALL_HINT = f"npm install -g {PACKAGE}"

# Short. `auth status` is a local file read plus, at most, one quota call; a slow answer
# means something is wrong and a spinner that never resolves is worse than a report.
STATUS_TIMEOUT = 20.0


@dataclass
class MiniMaxStatus:
    """Deliberately the same field names as `AuthStatus` and `CodexStatus`.

    The panel that renders this is one template for all three backends. A fourth shape
    would mean a fourth branch in the front end, and the branch nobody tests is the one
    that shows a blank box.
    """

    ok: bool
    headline: str
    detail: str
    cli_found: bool = False
    cli_path: str = ""
    signed_in: bool = False
    can_login: bool = False
    account: str = ""
    # Named for symmetry with the other two backends even though it is always False here —
    # see the module docstring. The front end reads it; making it absent would be a
    # KeyError in one of three cases.
    api_key_shadowing: bool = False
    fixes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"ok": self.ok, "headline": self.headline, "detail": self.detail,
                "cli_found": self.cli_found, "cli_path": self.cli_path,
                "signed_in": self.signed_in, "can_login": self.can_login,
                "account": self.account, "api_key_shadowing": self.api_key_shadowing,
                "fixes": list(self.fixes)}


def config_home() -> Path:
    """Where `mmx` keeps its credential, honouring its own override."""
    override = os.environ.get("MMX_CONFIG_DIR")
    return Path(override) if override else Path.home() / ".mmx"


def find_cli(root: Path | None = None) -> str:
    """The `mmx` executable, this app's copy first.

    The app's own `runtime/node` copy wins over anything on PATH for the same reason the
    Claude CLI does: a version the operator upgraded for another project is a version this
    app did not test against, and the failure would look like ours.
    """
    if root is not None:
        from ..desktop import toolchain

        binaries = toolchain.node_bin(root)
        local = binaries / ("mmx.cmd" if os.name == "nt" else "bin/mmx")
        if local.exists():
            return str(local)
        # npm's --prefix layout differs between platforms; check the flat form too.
        flat = binaries / ("mmx.cmd" if os.name == "nt" else "mmx")
        if flat.exists():
            return str(flat)
    return shutil.which("mmx") or ""


def _run(argv: list[str], timeout: float = STATUS_TIMEOUT) -> tuple[int, str]:
    """One CLI call, with its console suppressed on Windows."""
    from ..desktop.toolchain import _no_window

    try:
        result = subprocess.run(argv, capture_output=True, text=True, errors="replace",
                                timeout=timeout, **_no_window())
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, f"{type(exc).__name__}: {exc}"
    return result.returncode, (result.stdout or "") + (result.stderr or "")


@dataclass
class LoginState:
    signed_in: bool = False
    account: str = ""
    region: str = ""
    with_api_key: bool = False
    raw: dict = field(default_factory=dict)


def login_state(cli: str = "") -> LoginState:
    """What `mmx auth status` reports, parsed.

    Read as JSON because the CLI offers it, and a machine-readable answer is the whole
    reason not to scrape the banner — `mmx` prints an ASCII logo before its human output,
    and a substring match against that is a check that breaks on a cosmetic release.
    """
    cli = cli or find_cli()
    if not cli:
        return LoginState()

    code, output = _run([cli, "auth", "status", "--output", "json"])
    try:
        payload = json.loads(output[output.index("{"):output.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return LoginState(raw={"unparsed": output[:400]})

    if isinstance(payload.get("error"), dict):
        # `code: 3` is "No credentials found." Not signed in is not a failure — it is the
        # state before signing in — so it is reported as such rather than as an error.
        return LoginState(raw=payload)

    # The account is under whichever key this build uses; all three have been seen in
    # MiniMax's own JSON across surfaces, so none of them is assumed to be the one.
    account = str(payload.get("email") or payload.get("account")
                  or payload.get("user") or "").strip()
    method = str(payload.get("auth_method") or payload.get("method") or "").lower()
    return LoginState(
        signed_in=True,
        account=account,
        region=str(payload.get("region") or ""),
        # An API-key sign-in works; it just is not the plan, and the difference is money.
        with_api_key="key" in method,
        raw=payload,
    )


def check(root: Path | None = None) -> MiniMaxStatus:
    """Run before offering the chat on this backend. Reports rather than guesses."""
    cli = find_cli(root)

    if not cli:
        return MiniMaxStatus(
            ok=False,
            headline="The MiniMax CLI is not installed",
            detail=(
                "MiniMax runs this studio through its own CLI, the same way Claude and "
                "ChatGPT do — that is what lets it use the subscription you already pay "
                f"for instead of billing per token. Install it once: {INSTALL_HINT}"
            ),
            fixes=[INSTALL_HINT, "Then press Check again."],
        )

    state = login_state(cli)

    if not state.signed_in:
        return MiniMaxStatus(
            ok=False,
            headline="Not signed in yet",
            detail=(
                "The CLI is installed but nobody has signed in on this machine. Press "
                "Sign in: a terminal opens running the MiniMax browser flow, and you "
                "finish in the browser. It is your normal MiniMax subscription — there "
                "is no API key to paste."
            ),
            cli_found=True, cli_path=cli, can_login=True,
            fixes=["Press Sign in, then Check again once the browser is done."],
        )

    if state.with_api_key:
        return MiniMaxStatus(
            ok=True,
            headline="Connected with a MiniMax API key",
            detail=(
                "This is an API-key sign-in, not your subscription: every turn bills per "
                "token against the API balance. It works. To use the plan instead, run "
                "`mmx auth logout` and press Sign in."
            ),
            cli_found=True, cli_path=cli, signed_in=True,
            account=state.account or "API key",
            fixes=["mmx auth logout", "then press Sign in for the browser flow."],
        )

    return MiniMaxStatus(
        ok=True,
        headline="Connected with your MiniMax subscription",
        detail=(
            "MiniMax can run this studio: research a niche, set up a channel, write and "
            "check a script, tune the voice, build the edit and preview it before "
            "anything renders. It holds the same studio tools Claude does, with one "
            "exception — it cannot stop mid-turn to ask, so it is never given the gate. "
            "Narration is separate and is still billed to your MiniMax API balance; the "
            "subscription covers this chat, not text-to-speech."
        ),
        cli_found=True, cli_path=cli, signed_in=True,
        account=state.account or (f"{state.region} region" if state.region else ""),
    )


def start_login(root: Path | None = None) -> tuple[bool, str]:
    """Open a terminal running the browser sign-in.

    A visible console, deliberately, and for the same reason as the other two backends:
    the flow prints a URL and a code and waits. Behind a hidden window that is a button
    that appears to do nothing.

    `--recommend` skips the CLI's interactive menu and goes straight to OAuth, which is
    the whole point — the menu's other branch is "paste an API key", and offering that
    here would undo the reason this backend exists.
    """
    cli = find_cli(root)
    if not cli:
        return False, f"The MiniMax CLI was not found. Install it: {INSTALL_HINT}"

    command = [cli, "auth", "login", "--recommend"]
    try:
        if os.name == "nt":
            # A real console, so the URL and the prompt are readable. `start` returns
            # immediately, which is wanted: the browser step is the operator's, not ours.
            subprocess.Popen(["cmd", "/c", "start", "MiniMax sign-in", *command],
                             creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        elif os.uname().sysname == "Darwin":
            script = " ".join(f'"{part}"' for part in command)
            subprocess.Popen(["osascript", "-e",
                              f'tell app "Terminal" to do script "{script}"'])
        else:
            opened = False
            for terminal in ("x-terminal-emulator", "gnome-terminal", "konsole", "xterm"):
                if shutil.which(terminal):
                    subprocess.Popen([terminal, "-e", *command])
                    opened = True
                    break
            if not opened:
                return False, ("No terminal emulator was found. Run this yourself:  "
                               + " ".join(command))
    except OSError as exc:
        return False, f"Could not open a terminal: {exc}"

    return True, ("A terminal is opening. Complete the MiniMax sign-in in your browser, "
                  "then press Check again.")
