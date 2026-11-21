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
                  allow_network: bool = False, budget_usd: float | None = 5.0,
                  model: str | None = None, studio=None, resume: str | None = None):
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

    # Only passed when set. An empty model= would override the CLI's own default
    # with nothing, which is a worse outcome than not asking.
    extra = {"model": model} if model else {}

    # Reopening a saved conversation. The transcript on screen is replayed from
    # a file, but the AGENT's memory of it is the CLI's session -- without this
    # the chat would show a script it had just been given and the model would
    # have no idea what you were referring to.
    if resume:
        extra["resume"] = resume

    # The studio itself, as tools. Without these Claude can only talk ABOUT the
    # pipeline; with them it runs it -- loads the reference, renders takes,
    # moves the dials, reads the script and renders it.
    if studio is not None:
        from . import agent_tools
        extra["mcp_servers"] = {"vostudio": agent_tools.build_server(studio)}
        # Pre-allowed: every one of them is either read-only or produces audio
        # that can simply be produced again. Nothing here overwrites a profile
        # or deletes a render -- those stayed buttons on purpose.
        extra["allowed_tools"] = agent_tools.ALLOWED

    return ClaudeAgentOptions(
        cwd=str(app_root),
        **extra,
        add_dirs=[],                       # nothing outside the app root
        sandbox=sandbox,
        permission_mode=permission_mode,
        max_budget_usd=budget_usd,
        # The renders and the voice reference are inputs, not things to rewrite.
        # A destructive edit here is unrecoverable — the audio is not in git.
        disallowed_tools=["WebFetch", "WebSearch"] if not allow_network else [],
        system_prompt=(
            "You ARE ExplainTory VO Studio — Sapro's local voiceover studio, running "
            "Chatterbox on his own GPU. You are not an assistant sitting beside the "
            "app; the app's operations are your tools and you do the work with them.\n\n"

            "How the work goes:\n"
            "- A voice reference has to be loaded before anything can be rendered. If "
            "one is missing, ask for a clip: 8-12 seconds of continuous speech, no "
            "music, no long pauses. When he attaches audio, call "
            "use_voice_reference with its path.\n"
            "- To tune a voice: render_take, let him listen, take his note "
            "('feels bit fast', 'too flat'), call adjust_voice, then render_take "
            "again with NO text so it re-reads the same words at the new "
            "settings. Changing the words and the settings in one round means "
            "neither of you can tell which change you are hearing.\n"
            "- When he gives you lines to test, pass them to render_take WHOLE. "
            "Never trim to the first sentence to save time: he asked to hear "
            "those lines, a take costs seconds, and a six-second sample of a "
            "thirty-second passage tells him nothing about how it holds up.\n"
            "- When he pastes a script, call analyse_script and show him what it "
            "becomes — sections, chunks, chapter headers, finished length, render "
            "time — and let him agree before render_script.\n\n"

            "THE SAMPLE GATE — the one rule you do not get to skip.\n"
            "Never run render_script until a take has been rendered and approved "
            "IN THIS CONVERSATION at the settings you are about to use. If he has "
            "not heard one, render_take the opening thirty seconds or so of his "
            "own script -- a real passage, not one sentence -- and ask. A take costs about ten seconds; a full script is tens of minutes "
            "of GPU and the difference between them is the whole reason to check. "
            "The failure is not a crash — it is forty minutes producing a read "
            "that was wrong from the first sentence.\n"
            "The only exception is when he tells you to skip it. Never decide that "
            "yourself, and if the settings have moved since the approved take, the "
            "approval no longer counts.\n\n"

            "HIS INSTRUCTION WINS. Everything above is what to do when he has "
            "not said otherwise. If he asks for the whole passage, read the whole "
            "passage; if he says skip the sample, skip it; if he wants a dial at a "
            "number you would not have chosen, set it and say what you think "
            "rather than quietly doing something else. The only things you do not "
            "do on your own are the ones that cannot be undone — overwriting a "
            "saved profile, deleting audio — and those are his buttons, not your "
            "tools. When you disagree, say so in one sentence and then do what he "
            "asked.\n\n"

            "You CAN show him audio. Every take you render appears as a player "
            "in the chat automatically — never tell him to open a file from disk "
            "or that you have no way to play it. Mention the file name if it is "
            "useful and move on.\n\n"

            "Say what you did and what the numbers were. 'Rendered a take, 11.4s, "
            "speed 1.00 to 0.96' is useful; 'Done!' is not. Report failures with the "
            "actual error.\n\n"

            "You can also read and edit the app's own code. The thresholds in "
            "vostudio/config.py were each set by a specific past failure and are "
            "annotated with it — do not change one without a measurement that "
            "justifies it. Never edit anything under projects/ or voices/: that is "
            "rendered audio and his voice reference, it is not in git, and it cannot "
            "be recovered."
        ),
    )


def _result_text(block) -> str:
    """A tool result is a string or a list of content dicts. Flattened here so
    the UI has one shape to look at."""
    content = getattr(block, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(c.get("text", "") for c in content if isinstance(c, dict))
    return ""


# ONE CONVERSATION, NOT A SERIES OF STRANGERS
#
# Every turn used to call query(), which starts a fresh session. So the script
# pasted in one message was gone by the next, and the agent -- correctly, for
# what it could see -- answered "I do not have the script in front of me". That
# read as a stupid model. It was a backend throwing the conversation away after
# every message.
#
# ClaudeSDKClient holds the session open across turns, the way the CLI does.
_SESSION: dict = {"client": None, "key": None}
_LOCK = None


def _lock():
    """Created lazily: an asyncio.Lock built at import binds to whichever loop
    happens to exist then, which is not the one uvicorn ends up running."""
    global _LOCK
    import asyncio
    if _LOCK is None:
        _LOCK = asyncio.Lock()
    return _LOCK


async def reset_session() -> None:
    """Drop the conversation. New topic, or a session that has gone wrong."""
    client = _SESSION.get("client")
    _SESSION.update(client=None, key=None)
    if client is not None:
        try:
            await client.disconnect()
        except Exception:
            pass


async def run(prompt: str, app_root: Path, conversation: str | None = None, **kwargs):
    """
    One turn, as a stream of events, inside a conversation that persists.

    Yields {"type": "text"|"tool"|"result"|"session"|"error", ...}. Streaming
    because a turn can now RENDER something -- tens of minutes of GPU -- and a
    UI that shows nothing until it finishes is indistinguishable from one that
    has hung.

    `conversation` is the id of the conversation this turn belongs to. It is
    part of the session key, so switching conversations in the sidebar really
    does switch what the agent is talking about; the caller passes resume= to
    hand the CLI back the session that conversation was using.
    """
    from claude_agent_sdk import (ClaudeSDKClient, AssistantMessage, UserMessage,
                                  TextBlock, ToolUseBlock, ToolResultBlock,
                                  ResultMessage, CLINotFoundError)

    status = check_auth()
    if not status.ok:
        yield {"type": "error", "text": status.detail}
        return

    # Turns are serialised. Two in flight would interleave on one session and
    # neither would make sense.
    async with _lock():
        # Model, permission mode or CONVERSATION changing means a new session:
        # they are set when the client connects, and pretending otherwise would
        # silently keep answering on the old model — or, worse, answer in the
        # conversation you just switched away from.
        key = (kwargs.get("model"), kwargs.get("permission_mode"), conversation)
        resumed = bool(kwargs.get("resume"))
        if _SESSION["client"] is None or _SESSION["key"] != key:
            await reset_session()
            try:
                client = ClaudeSDKClient(options=build_options(app_root, **kwargs))
                await client.connect()
            except CLINotFoundError:
                yield {"type": "error", "text":
                       "Claude Code CLI not found. Install it and sign in."}
                return
            except Exception as exc:
                # A stored session id the CLI no longer has -- its history was
                # cleared, or the app folder moved. Without this the
                # conversation is dead for good: every turn resumes the same
                # missing session and fails the same way. Started fresh
                # instead, and the caller is told to forget the id.
                if not resumed:
                    yield {"type": "error", "text": f"{type(exc).__name__}: {exc}"}
                    return
                yield {"type": "forget_session"}
                try:
                    client = ClaudeSDKClient(options=build_options(
                        app_root, **{**kwargs, "resume": None}))
                    await client.connect()
                except Exception as exc2:
                    yield {"type": "error", "text": f"{type(exc2).__name__}: {exc2}"}
                    return
                yield {"type": "text", "text":
                       "(This conversation's earlier context could not be reloaded, "
                       "so I am starting from what is on screen.)\n\n"}
            _SESSION.update(client=client, key=key)

        client = _SESSION["client"]
        try:
            await client.query(prompt)
            async for message in client.receive_response():
                # A tool RESULT comes back as a user message. That is where the
                # rendered file name is, and without forwarding it the app can
                # never put the audio on screen -- which is why it told you it
                # had "no way to embed audio" while sitting inside a UI that
                # plays audio in every other message.
                if isinstance(message, UserMessage):
                    for block in (message.content if isinstance(message.content, list) else []):
                        if isinstance(block, ToolResultBlock):
                            yield {"type": "result", "text": _result_text(block)}
                    continue
                # The CLI's own id for this session. Stored against the
                # conversation so reopening it can resume rather than start
                # over. It is reported at the END of a turn, which is why this
                # is the last thing recorded and not the first.
                if isinstance(message, ResultMessage):
                    sid = getattr(message, "session_id", None)
                    if sid:
                        yield {"type": "session", "id": sid}
                    continue
                if not isinstance(message, AssistantMessage):
                    continue
                for block in message.content:
                    if isinstance(block, TextBlock):
                        yield {"type": "text", "text": block.text}
                    elif isinstance(block, ToolUseBlock):
                        # Named so the transcript shows the work, not just the
                        # answer: "rendering a take" while it happens.
                        yield {"type": "tool", "name": getattr(block, "name", "tool"),
                               "input": getattr(block, "input", {}) or {}}
        except Exception as exc:                              # pragma: no cover
            # A broken session stays broken; drop it so the next turn is clean
            # rather than failing the same way forever.
            await reset_session()
            yield {"type": "error", "text": f"{type(exc).__name__}: {exc}"}


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
