"""Is Claude actually connected, and if not, what exactly is wrong.

The complaint this answers is "idk if it's connected claude". The old app looked
identical whether Claude was reachable or not, right up until something failed.

## It is a subscription, not an API key

The agent runs through the Claude Code CLI signed in with your own Claude
subscription — the same `/login` browser flow you already use. There is no API key
in this app and you should not create one.

The trap is worth stating because it costs real money silently: credential
resolution checks `ANTHROPIC_API_KEY` **first**, so a leftover key from any earlier
experiment outranks the subscription login and requests quietly bill an API
account instead. An empty `ANTHROPIC_API_KEY=""` still occupies the slot and still
wins — it has to be genuinely unset, not blanked.

So this module reports before a single token is spent, and it reports the three
states separately, because they need three different actions:

* the CLI is missing → install it;
* a key is shadowing the login → unset it;
* the CLI is there but nobody has signed in → press Sign in.

That last one was a real bug in the app this pattern comes from: "signed in with
your subscription" sat above a chat answering *Not logged in*, because the CLI
being **present** had been treated as the CLI being **signed in**. They are
checked separately here.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Installing the CLI needs Node, which is a second runtime and worth naming rather
# than hiding behind "installation failed".
INSTALL_HINT = "npm install -g @anthropic-ai/claude-code"


@dataclass
class AuthStatus:
    ok: bool
    headline: str
    detail: str
    cli_found: bool = False
    cli_path: str = ""
    signed_in: bool = False
    api_key_shadowing: bool = False
    # True only when the sign-in is the one thing missing — the single case the app
    # can do something about, so the UI shows a button instead of prose.
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


def find_cli() -> str | None:
    """The CLI on PATH, or a copy inside the app folder.

    `claude.cmd` as well as `claude`: on Windows the shim npm installs is a .cmd and
    `shutil.which("claude")` does not find it unless PATHEXT happens to cooperate.
    """
    for name in ("claude", "claude.cmd"):
        found = shutil.which(name)
        if found:
            return found
    local = Path(__file__).resolve().parents[2] / "runtime" / "node"
    for name in ("claude.cmd", "claude"):
        if (local / name).exists():
            return str(local / name)
    return None


def _credentials() -> dict:
    """Whatever the CLI wrote about the signed-in account, or an empty dict.

    Read from disk rather than probed with a request. Sending a prompt to find out
    whether a prompt would work spends tokens on every page load to answer a
    question the filesystem already answers.
    """
    home = Path.home()
    creds = home / ".claude" / ".credentials.json"
    if creds.exists():
        try:
            return json.loads(creds.read_text(encoding="utf-8")) or {}
        except (OSError, ValueError):
            return {"_present": True}
    try:
        raw = json.loads((home / ".claude.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if (raw.get("oauthAccount") or raw.get("userID")) else {}


def _account_label(raw: dict) -> str:
    account = raw.get("oauthAccount") or {}
    if isinstance(account, dict):
        for key in ("emailAddress", "email", "accountUuid"):
            if account.get(key):
                return str(account[key])
    scopes = raw.get("claudeAiOauth") or {}
    if isinstance(scopes, dict) and scopes.get("subscriptionType"):
        return f"{scopes['subscriptionType']} subscription"
    return ""


def signed_in() -> bool:
    return bool(_credentials())


def check() -> AuthStatus:
    """Run before offering the chat. Reports rather than guesses."""
    cli = find_cli()
    key = os.environ.get("ANTHROPIC_API_KEY")

    if key is not None:
        return AuthStatus(
            ok=False,
            headline="An API key is overriding your subscription",
            detail=(
                "ANTHROPIC_API_KEY is set in this environment. Credentials resolve to "
                "it before your Claude subscription, so every request would bill an "
                "API account instead of the plan you already pay for. An empty value "
                "still counts as set and still wins — it has to be unset."
            ),
            cli_found=bool(cli), cli_path=cli or "", api_key_shadowing=True,
            fixes=[
                'Windows:  setx ANTHROPIC_API_KEY "" && set ANTHROPIC_API_KEY=',
                "macOS / Linux:  unset ANTHROPIC_API_KEY",
                "Then close this app and open it again — the value is read at start-up.",
            ],
        )

    if not cli:
        return AuthStatus(
            ok=False,
            headline="The Claude Code CLI is not installed",
            detail=(
                "The agent drives the Claude Code CLI, so it cannot start without it. "
                "It needs Node.js, which is a separate runtime from Python."
            ),
            fixes=[INSTALL_HINT, "Then press Check again — no restart needed."],
        )

    raw = _credentials()
    if not raw:
        return AuthStatus(
            ok=False,
            headline="Not signed in yet",
            detail=(
                "The CLI is installed but nobody has signed in on this machine. Press "
                "Sign in: a terminal opens running Claude Code, you type /login, and "
                "finish in the browser. It is your normal Claude subscription — there "
                "is no API key and you should not create one."
            ),
            cli_found=True, cli_path=cli, can_login=True,
            fixes=["Press Sign in, then Check again once the browser is done."],
        )

    return AuthStatus(
        ok=True,
        headline="Connected with your Claude subscription",
        detail=(
            "Claude can run this studio: research a niche, set up a channel, write "
            "and check a script, tune the voice, build the edit and preview it before "
            "anything renders."
        ),
        cli_found=True, cli_path=cli, signed_in=True,
        account=_account_label(raw),
    )


def start_login() -> tuple[bool, str]:
    """Open a terminal running the CLI so the browser sign-in can happen.

    A visible console, deliberately. `/login` is an interactive command *inside*
    Claude Code — there is no `claude login` subcommand to run silently — so the
    sign-in cannot be driven from behind the UI. Hiding the window would just mean
    nothing happens and the button looks broken.
    """
    cli = find_cli()
    if not cli:
        return False, f"The Claude Code CLI was not found. Install it: {INSTALL_HINT}"

    try:
        if os.name == "nt":
            subprocess.Popen(["cmd", "/k", cli],
                             creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        elif shutil.which("open"):                                    # macOS
            subprocess.Popen(["open", "-a", "Terminal", cli])
        else:
            terminal = next(
                (t for t in ("x-terminal-emulator", "gnome-terminal", "konsole",
                             "xterm") if shutil.which(t)), "")
            if not terminal:
                return False, (
                    "No terminal emulator was found to open. Run this yourself in a "
                    f"shell, type /login, then press Check again:\n\n    {cli}")
            subprocess.Popen([terminal, "-e", cli])
    except OSError as exc:
        return False, f"Could not open a terminal: {type(exc).__name__}: {exc}"

    return True, ("A terminal opened. Type /login there, finish in the browser, then "
                  "close it and press Check again.")
