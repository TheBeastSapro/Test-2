"""
Claude, running inside the app, able to change the app.

Sapro wanted to log in with his subscription and make changes from in here rather
than switching to a browser. That is `claude-agent-sdk` driving the Claude Code CLI
with his own credentials.

AUTH IS HIS SUBSCRIPTION, NOT AN API KEY
    `claude login` — the browser OAuth flow. There is no API key in this app and
    none is needed.

    The trap, and it costs real money silently: credential resolution checks
    ANTHROPIC_API_KEY *first*, so a leftover key from any earlier experiment
    outranks the subscription login and requests quietly bill an API account
    instead. An empty ANTHROPIC_API_KEY="" still occupies the slot and still wins —
    it has to be genuinely unset, not blanked. `check_auth()` below reports this
    before a single token is spent, and the launcher refuses to start quietly.

    It also needs the Claude Code CLI, not just this Python package:
        npm install -g @anthropic-ai/claude-code
    On Windows the SDK looks for claude.cmd. That is a second runtime — Node as
    well as Python — which is why the installer has two halves.

WHY IT SHIPS ASKING FIRST
    permission_mode accepts 'default', 'acceptEdits', 'plan', 'bypassPermissions',
    'dontAsk' and 'auto'. This ships on 'default': every edit prompts.

    An agent with unattended write access to the pipeline that renders the channel's
    audio is not a convenience worth defaulting into. The failure mode is not a
    crash — it is a silently altered threshold in config.py that changes every
    voiceover afterwards, discovered weeks later in a delivered file.
"""
import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AuthStatus:
    ok: bool
    detail: str
    api_key_shadowing: bool = False
    cli_found: bool = False
    # True when the only thing missing is the sign-in — the one case the app can
    # actually do something about, so the UI offers a button instead of prose.
    can_login: bool = False


def find_cli() -> str | None:
    """The CLI on PATH, or the copy setup put in .\\runtime\\node."""
    found = shutil.which("claude") or shutil.which("claude.cmd")
    if found:
        return found
    local = Path(__file__).resolve().parent.parent / "runtime" / "node"
    for name in ("claude.cmd", "claude"):
        if (local / name).exists():
            return str(local / name)
    return None


def logged_in() -> bool:
    """
    Is there a subscription login on this machine?

    Checked from the credentials on disk rather than by making a request. The
    alternative -- send a probe prompt and see if it fails -- spends tokens to
    answer a question the filesystem already answers, on every page load.
    """
    home = Path.home()
    if (home / ".claude" / ".credentials.json").exists():
        return True
    try:
        import json
        raw = json.loads((home / ".claude.json").read_text(encoding="utf-8"))
        return bool(raw.get("oauthAccount") or raw.get("userID"))
    except Exception:
        return False


def check_auth() -> AuthStatus:
    """Run before offering the assistant. Reports rather than guesses."""
    cli = find_cli()
    key = os.environ.get("ANTHROPIC_API_KEY")

    if key is not None:
        return AuthStatus(
            ok=False,
            detail=("ANTHROPIC_API_KEY is set in this environment. It OVERRIDES your "
                    "Claude subscription login, so requests would bill an API account "
                    "instead. Unset it — note that an empty value still counts as set "
                    "and still wins.\n\n"
                    "    Windows:  setx ANTHROPIC_API_KEY \"\" && set ANTHROPIC_API_KEY=\n"
                    "    then close and reopen the terminal."),
            api_key_shadowing=True, cli_found=bool(cli))

    if not cli:
        return AuthStatus(
            ok=False,
            detail=("The Claude Code CLI was not found. The SDK drives it, so the "
                    "assistant cannot start without it. Open the app folder and run:\n\n"
                    "    runtime\\node\\npm.cmd install -g @anthropic-ai/claude-code "
                    "--prefix runtime\\node"),
            cli_found=False)

    if not logged_in():
        # This was the bug behind "Signed in with your Claude subscription" sitting
        # above a chat that answered "Not logged in - Please run /login": the CLI
        # being present was treated as the CLI being signed in.
        return AuthStatus(
            ok=False,
            detail=("Not signed in yet. Press Sign in — a terminal opens running "
                    "Claude Code. Type /login in it, finish in the browser, then "
                    "close it and press Check again.\n\n"
                    "It is your normal Claude subscription. There is no API key and "
                    "you should not create one."),
            cli_found=True, can_login=True)

    return AuthStatus(True, "Signed in with your Claude subscription. Claude can read "
                            "and edit this app, and is confined to its own folder with "
                            "networking off.",
                      cli_found=True)


def start_login() -> tuple[bool, str]:
    """
    Open a terminal running the CLI so the browser sign-in can happen.

    A visible console, deliberately. /login is an interactive command inside
    Claude Code -- there is no `claude login` subcommand to run silently -- so
    the sign-in cannot be driven from behind the UI. Hiding the window would
    just mean nothing happens.
    """
    cli = find_cli()
    if not cli:
        return False, "The Claude Code CLI was not found."
    try:
        import subprocess
        if os.name == "nt":
            subprocess.Popen(["cmd", "/k", cli],
                             creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            subprocess.Popen(["x-terminal-emulator", "-e", cli])
        return True, ("A terminal opened. Type /login there, finish in the browser, "
                      "then close it and press Check again.")
    except Exception as exc:
        return False, f"Could not open a terminal: {type(exc).__name__}: {exc}"


def build_options(app_root: Path, permission_mode: str = "default",
                  allow_network: bool = False, budget_usd: float | None = 5.0):
    """
    Confine the agent to this app, on disk and on the network.

    cwd plus a sandbox, not cwd alone. cwd sets where it starts; the sandbox is what
    stops a shell command from wandering out of it. Network is denied by default —
    the assistant's job is editing local pipeline code, and nothing about that
    requires reaching the internet.
    """
    from claude_agent_sdk import ClaudeAgentOptions

    sandbox = {
        "enabled": True,
        # Sandboxed bash may run without a second prompt; the sandbox is the
        # boundary, and prompting twice for the same guarantee trains him to
        # click through prompts.
        "autoAllowBashIfSandboxed": True,
        # No escape hatch. If a command genuinely needs to leave the sandbox,
        # that should be a deliberate config change, not a runtime decision.
        "allowUnsandboxedCommands": False,
        "network": ({"allowLocalBinding": True} if allow_network
                    else {"allowManagedDomainsOnly": True, "allowLocalBinding": True}),
    }

    return ClaudeAgentOptions(
        cwd=str(app_root),
        add_dirs=[],                       # nothing outside the app root
        sandbox=sandbox,
        permission_mode=permission_mode,
        max_budget_usd=budget_usd,
        # The renders and the voice reference are inputs, not things to rewrite.
        # A destructive edit here is unrecoverable — the audio is not in git.
        disallowed_tools=["WebFetch", "WebSearch"] if not allow_network else [],
        system_prompt=(
            "You are working inside ExplainTory VO Studio, Sapro's local voiceover "
            "app. The pipeline's thresholds in vostudio/config.py were each set by a "
            "specific past failure and are annotated with it — do not change one "
            "without a measurement that justifies it. Never edit files under "
            "projects/ or voices/: those are rendered audio and his voice reference, "
            "they are not in git, and they cannot be recovered. Prefer showing a diff "
            "and explaining the tradeoff over making a large change in one step."
        ),
    )


async def ask(prompt: str, app_root: Path, on_text=print, **kwargs):
    """
    One turn. Streams assistant text to `on_text` and returns the full reply.

    Errors are surfaced as text rather than raised, because this runs behind a UI
    where a traceback in a log file is a dead end for the person using it.
    """
    from claude_agent_sdk import query, AssistantMessage, TextBlock, CLINotFoundError

    status = check_auth()
    if not status.ok:
        on_text(status.detail)
        return status.detail

    parts: list[str] = []
    try:
        async for message in query(prompt=prompt,
                                   options=build_options(app_root, **kwargs)):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        parts.append(block.text)
                        on_text(block.text)
    except CLINotFoundError:
        msg = ("Claude Code CLI not found. Install it and log in:\n"
               "    npm install -g @anthropic-ai/claude-code\n    claude login")
        on_text(msg)
        return msg
    except Exception as exc:                                  # pragma: no cover
        msg = f"Assistant error: {type(exc).__name__}: {exc}"
        on_text(msg)
        return msg

    return "".join(parts)
