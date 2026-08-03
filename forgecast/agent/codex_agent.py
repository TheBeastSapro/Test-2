"""ChatGPT, running inside the app, holding the app's operations as tools.

The sibling of `assistant.py`. Same contract — `run()` is an async generator of the
same event dicts — so `routes_agent.py` and `chat.js` cannot tell which agent answered
except by what it says.

## Auth is a subscription, not an API key

See `codex_auth.py`. Nothing here takes a key: it drives OpenAI's Codex CLI signed in
with your own `codex login`, exactly as `assistant.py` drives the Claude Code CLI
signed in with `claude login`. That parallel is the whole reason ChatGPT is offered
here at all — "paste a key and pay per token" would not have been the same feature.

## How the 21 tools reach it

Claude gets the studio as an *in-process* MCP server. Codex is a separate binary and
cannot see into this process, so it is pointed at `forgecast.agent.mcp_stdio`, which
serves the very same server object over a pipe. The tools are defined once, in
`tools.py`. There is no second list of function schemas to keep in step, because a
second list is a list that goes stale.

## Nothing is written to the operator's Codex config

MCP servers normally live in `~/.codex/config.toml`, and the tidy-looking move is to
run `codex mcp add`. This app does not: editing a file the operator wrote, to add an
entry they did not ask for, is not something a chat window should do — and it would
leak this app's tools into every unrelated `codex` session on the machine. Everything
is passed per invocation with `-c` overrides instead, plus `--ignore-user-config` so
their own settings cannot silently change what this agent is allowed to do. Both halves
were measured on codex-cli 0.146.0: `codex mcp list --json` reports the server from
`-c` alone, and a turn run this way against an empty `CODEX_HOME` leaves no
`config.toml` behind at all. (Run *without* `--ignore-user-config` the CLI writes its
own `[projects."…"] trust_level` entry there — which is another reason to pass it.)

What the CLI does keep under `CODEX_HOME` is its session store, and that is wanted:
it is what `exec resume` reads, and it is how a ChatGPT thread here remembers the
channel you were setting up three messages ago.

## What this backend cannot do, and why it is not hidden

`codex exec` is non-interactive. There is no way for it to stop mid-turn and ask, so
"confirm before editing" — which Claude honours through its own permission prompt —
has no equivalent, and `decide_gate` is not served to it at all (see `mcp_stdio`). The
picker says both things on screen rather than leaving someone to discover that a
setting they can see is quietly doing nothing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import sys
from collections import deque
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

from . import codex_auth, setup_notice, tools
from .assistant import APP_ROOT, _result_text
from .studio import Studio

log = logging.getLogger("forgecast.agent.codex")

# The list `codex debug models` reports as visible on 0.146.0, in its own priority
# order. Availability follows your plan rather than this list — a plan limit is
# reported by the CLI, not predicted here, which is the same rule `assistant.MODELS`
# follows.
MODELS = [
    {"id": "gpt-5.6-terra", "label": "GPT-5.6 Terra",
     "note": "The default. Balanced, and quick enough to keep a conversation going."},
    {"id": "gpt-5.6-sol", "label": "GPT-5.6 Sol",
     "note": "Strongest. For the decisions you would not want to review twice."},
    {"id": "gpt-5.6-luna", "label": "GPT-5.6 Luna",
     "note": "Fastest and cheapest. Reading and answering, not producing."},
    {"id": "gpt-5.5", "label": "GPT-5.5",
     "note": "The previous frontier model. Steady on long research."},
    {"id": "gpt-5.2", "label": "GPT-5.2",
     "note": "Tuned for long-running agent work rather than chat."},
]
DEFAULT_MODEL = "gpt-5.6-terra"

# Retries the CLI reports while it is still trying. Fifteen of these arrive on an
# unauthenticated turn, and `chat.js` renders an error event by *replacing* the reply
# — so surfacing them one by one leaves the operator reading "Reconnecting... 5/5"
# where the answer should be. They are folded into one notice and the real failure is
# whatever the stream says last.
_RETRY_SIGN = "reconnecting..."

# Stderr worth keeping for the failure sentence. A wedged CLI can print a lot, and the
# useful part is always the end of it.
_STDERR_LINES = 40

# How long to wait for the process to die after the stream ends. Beyond this it is
# killed: a stuck child holding a pipe open would hang the HTTP response forever.
_EXIT_GRACE = 10


def _python() -> str:
    """The interpreter that will run the tool server.

    `sys.executable`, so the subprocess is this virtual environment rather than
    whatever `python` means on the machine's PATH. Getting that wrong produces a tool
    server that cannot import forgecast, reported by the CLI as a server that failed
    to start.
    """
    return sys.executable or "python"


def system_prompt(studio: Studio) -> str:
    """The same instructions Claude gets.

    Imported from `assistant` rather than restated. Every paragraph there exists
    because of something that goes wrong without it, and two copies would mean the
    ChatGPT backend keeps approving gates six months after the Claude one stopped.
    """
    from . import assistant

    return assistant.system_prompt(studio)


def _toml(value) -> str:
    """A TOML scalar or array for a `-c key=value` override.

    Hand-rolled because the values are strings, string lists and booleans and nothing
    else, and because `-c` parses the right-hand side as TOML: an unquoted path with a
    space or a backslash in it is a parse error, and a Windows path is both.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ",".join(_toml(item) for item in value) + "]"
    return json.dumps(str(value))               # JSON strings are valid TOML strings


def _token_variable(key: str) -> str:
    return "FORGECAST_MCP_TOKEN_" + "".join(
        c if c.isalnum() else "_" for c in key).upper()


def remote_servers() -> tuple[list[str], dict[str, str]]:
    """The operator's connectors, as `-c` overrides plus the environment they need.

    Same connectors the Claude path gets from `connectors.active_servers()`, so the two
    agents hold the same outside tools — the system prompt claims they do, and an agent
    told it has NexLev when it does not will report that a niche cannot be researched.

    Tokens go through a named environment variable (`bearer_token_env_var`) rather than
    inline `http_headers`, because a command line is world-readable: `ps` on a shared
    machine would print somebody's API token in full. The header form is only used for
    a service whose scheme is not `Authorization: Bearer`, which none of the shipped
    connectors are.
    """
    from . import connectors

    overrides: list[str] = []
    env: dict[str, str] = {}
    for key, config in connectors.active_servers().items():
        url = config.get("url")
        if not url:
            continue
        entry = f"mcp_servers.{key}"
        overrides += ["-c", f"{entry}.url={_toml(url)}"]
        headers = dict(config.get("headers") or {})
        bearer = headers.pop("Authorization", "")
        if bearer.startswith("Bearer "):
            variable = _token_variable(key)
            env[variable] = bearer[len("Bearer "):]
            overrides += ["-c", f"{entry}.bearer_token_env_var={_toml(variable)}"]
        elif bearer:
            headers["Authorization"] = bearer
        if headers:
            overrides += ["-c", f"{entry}.http_headers={{" + ",".join(
                f"{name}={_toml(value)}" for name, value in headers.items()) + "}"]
    return overrides, env


def build_command(*, cli: list[str], model: str | None = None,
                  resume: str | None = None, allow_web: bool = True,
                  user_id: int | None = None,
                  extra_config: list[str] | None = None) -> list[str]:
    """The argv for one turn.

    The prompt is deliberately not in here: it is written to stdin and `-` is passed
    in its place. A chat turn carries up to 60,000 characters plus an attachment
    listing, and a single argv argument is capped far below the total command length
    on Linux — passing it as an argument works until someone pastes a script, and then
    fails with a message about the argument list, not about the paste.
    """
    server = f"mcp_servers.{tools.SERVER_NAME}"
    env: dict[str, str] = {}
    if user_id is not None:
        # Which account's studio the tools operate on. Without it the server falls
        # back to the single-account guess, which is wrong on a shared install and
        # silently wrong — it would list somebody else's channels.
        env["FORGECAST_AGENT_USER_ID"] = str(user_id)

    argv = [*cli, "exec"]
    if resume:
        argv += ["resume", resume]
    argv += [
        "--json",
        # `exec` refuses to run outside a git repository unless told to. The app is
        # not necessarily a checkout — a packaged install is not — and refusing to
        # chat because of that would be absurd.
        "--skip-git-repo-check",
        # Their config.toml is not read at all: see the module docstring. Auth still
        # resolves from CODEX_HOME, which the flag's own help states.
        "--ignore-user-config",
    ]
    if not resume:
        # `exec resume` takes neither `-C` nor `-s` on 0.146.0 — it inherits the
        # working root recorded in the session it is resuming, which is this one.
        # Passing them anyway is not a warning, it is `error: unexpected argument`
        # and a dead thread on its second message.
        argv += ["-C", str(APP_ROOT)]
    argv += [
        # Writes confined to the app folder, and network on, because research is half
        # the job. This mirrors `assistant.build_options`'s sandbox rather than
        # inventing a second policy. Set as config rather than with `-s` so the one
        # line covers a resumed turn as well.
        "-c", f"sandbox_mode={_toml('workspace-write')}",
        "-c", f"sandbox_workspace_write.network_access={_toml(True)}",
        "-c", f"tools.web_search={_toml(bool(allow_web))}",
        "-c", f"{server}.command={_toml(_python())}",
        "-c", f"{server}.args={_toml(['-m', 'forgecast.agent.mcp_stdio'])}",
    ]
    if env:
        argv += ["-c", f"{server}.env={{" +
                 ",".join(f"{k}={_toml(v)}" for k, v in env.items()) + "}"]
    argv += list(extra_config or [])
    if model:
        # Only when set, for the same reason as the Claude path: an empty model would
        # override the CLI's own default with nothing.
        argv += ["-m", model]
    argv.append("-")
    return argv


def _tool_event(item: dict) -> dict | None:
    """A Codex item as the tool card the chat already knows how to draw.

    Named the way Claude's tool calls are named — `mcp__forgecast__create_channel` —
    because the front end strips the prefix to get a label and hides a fixed set by
    that short name. A different naming scheme here would show cards Claude hides.
    """
    kind = item.get("type")
    if kind == "mcp_tool_call":
        server = item.get("server") or tools.SERVER_NAME
        return {"name": f"mcp__{server}__{item.get('tool') or 'tool'}",
                "input": item.get("arguments") or {}}
    if kind == "command_execution":
        return {"name": "Bash", "input": {"command": item.get("command") or ""}}
    if kind == "file_change":
        paths = [c.get("path", "") for c in item.get("changes") or []]
        return {"name": "Edit", "input": {"files": paths}}
    if kind == "web_search":
        return {"name": "WebSearch", "input": {"query": item.get("query") or ""}}
    return None


def _tool_result(item: dict) -> tuple[bool, str]:
    """What a finished item produced, and whether it failed."""
    kind = item.get("type")
    failed = item.get("status") == "failed"
    if kind == "mcp_tool_call":
        error = item.get("error") or {}
        if error:
            return True, str(error.get("message") or error)
        result = item.get("result") or {}
        # Reuses the assistant's flattening and its truncation notice, so a long tool
        # result is cut the same way on both backends and says so the same way.
        return failed, _result_text(SimpleNamespace(content=result.get("content") or []))
    if kind == "command_execution":
        output = item.get("aggregated_output") or ""
        code = item.get("exit_code")
        text = _result_text(SimpleNamespace(content=output))
        if code not in (0, None):
            return True, f"exit {code}\n{text}"
        return failed, text
    if kind == "file_change":
        return failed, "\n".join(
            f"{c.get('kind', 'change')} {c.get('path', '')}"
            for c in item.get("changes") or [])
    if kind == "web_search":
        return failed, item.get("query") or ""
    return failed, ""


class _Turn:
    """The JSONL stream, translated. A class only to keep the tool ids in one place.

    Codex reports a tool starting and finishing as two events with the same `item.id`,
    which is exactly what the chat needs to fill in the card it already drew — so the
    ids are passed straight through rather than invented.
    """

    def __init__(self) -> None:
        self.session_id = ""
        self.retries = 0
        self.last_error = ""
        self.open_tools: set[str] = set()

    def translate(self, event: dict) -> list[dict]:
        kind = event.get("type") or ""
        if kind == "thread.started":
            thread = event.get("thread_id") or ""
            if thread and thread != self.session_id:
                self.session_id = thread
                # Emitted the moment it is known, for the reason spelled out in
                # `assistant.run`: a turn that never finishes still leaves the thread
                # resumable.
                return [{"type": "session", "session_id": thread}]
            return []

        if kind in ("item.started", "item.updated", "item.completed"):
            return self._item(kind, event.get("item") or {})

        if kind == "error":
            message = str(event.get("message") or "")
            if _RETRY_SIGN in message.lower():
                self.retries += 1
                return []
            self.last_error = message
            return []

        if kind == "turn.failed":
            self.last_error = str((event.get("error") or {}).get("message")
                                  or self.last_error)
            return []

        if kind == "turn.completed":
            usage = event.get("usage") or {}
            return [{"type": "result", "session_id": self.session_id, "turns": 1,
                     # No cost: this is a subscription, and a made-up dollar figure
                     # beside a plan you already pay for is worse than none.
                     "cost_usd": None, "is_error": False,
                     "tokens": {"input": usage.get("input_tokens"),
                                "output": usage.get("output_tokens"),
                                "cached_input": usage.get("cached_input_tokens")}}]
        return []

    def _item(self, kind: str, item: dict) -> list[dict]:
        item_type = item.get("type")
        item_id = str(item.get("id") or "")

        if item_type == "agent_message":
            return ([{"type": "text", "text": item.get("text") or ""}]
                    if kind == "item.completed" else [])
        if item_type == "reasoning":
            return ([{"type": "thinking", "text": item.get("text") or ""}]
                    if kind == "item.completed" else [])
        if item_type == "error":
            message = str(item.get("message") or "")
            if _RETRY_SIGN in message.lower():
                self.retries += 1
                return []
            self.last_error = message
            return []

        card = _tool_event(item)
        if card is None:
            return []

        out: list[dict] = []
        if item_id not in self.open_tools:
            self.open_tools.add(item_id)
            out.append({"type": "tool", "id": item_id, **card})
        if kind == "item.completed":
            failed, text = _tool_result(item)
            out.append({"type": "tool_result", "id": item_id,
                        "is_error": bool(failed), "text": text})
        return out


def _environment(extra: dict[str, str] | None = None) -> dict:
    """The environment the CLI is spawned with.

    `CODEX_API_KEY` is stripped rather than trusted. `codex_auth.check()` refuses to
    start a turn while it is set, and this is the second lock on the same door: a
    variable that appears after the check — set by a wrapper script, inherited from a
    parent shell — would otherwise bill an API account for a turn the operator
    believes is coming out of their plan. This is the same guarantee `assistant.py`
    relies on for `ANTHROPIC_API_KEY`, which stays unset here too.
    """
    env = dict(os.environ)
    env.pop("CODEX_API_KEY", None)
    env.pop("ANTHROPIC_API_KEY", None)
    env.update(extra or {})
    return env


async def run(prompt: str, *, studio: Studio, resume: str | None = None,
              model: str | None = None, allow_web: bool = True,
              user_id: int | None = None, **_ignored) -> AsyncIterator[dict]:
    """One turn, as a stream of events. Same contract as `assistant.run`.

    `**_ignored` swallows the options only Claude has — `permission_mode`,
    `budget_usd`. Accepting and dropping them is deliberate: the caller has one code
    path, and a `TypeError` from an unexpected keyword would present a missing feature
    as a crash. What the operator is told about them is in the picker, not here.
    """
    status = codex_auth.check()
    if not status.ok:
        # A setup notice rather than an error. This is the backend the complaint was
        # about: with no Codex CLI installed, "hi" came back as a paragraph about npm
        # sitting where the answer goes, in the agent's own voice.
        yield setup_notice.notice(status)
        return

    cli = codex_auth.find_cli()
    if not cli:                                                   # pragma: no cover
        yield setup_notice.notice(codex_auth.check())
        return

    connector_config, connector_env = remote_servers()
    argv = build_command(cli=cli, model=model, resume=resume, allow_web=allow_web,
                         user_id=user_id, extra_config=connector_config)
    log.info("codex turn: %s", " ".join(shlex.quote(part) for part in argv[len(cli):]))

    # Instructions go on stdin. Codex reads them there when the prompt is `-`, and it
    # also means a prompt containing a newline or a quote needs no escaping at all.
    full_prompt = f"{system_prompt(studio)}\n\n---\n\n{prompt}" if not resume else prompt

    try:
        process = await asyncio.create_subprocess_exec(
            *argv, cwd=str(APP_ROOT), env=_environment(connector_env),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)
    except OSError as exc:
        yield {"type": "error",
               "text": f"Could not start the Codex CLI at {codex_auth.cli_label(cli)}: "
                       f"{type(exc).__name__}: {exc}"}
        return

    tail: deque[str] = deque(maxlen=_STDERR_LINES)
    turn = _Turn()

    async def drain_stderr() -> None:
        """Read stderr continuously, not at the end.

        The CLI logs every connection retry to stderr. Left unread, that pipe fills,
        the CLI blocks writing to it, and the turn hangs with no output and no error —
        which is the single hardest failure to diagnose from the outside.
        """
        while True:
            line = await process.stderr.readline()
            if not line:
                return
            text = line.decode("utf-8", "replace").rstrip()
            if text:
                tail.append(text)

    stderr_task = asyncio.create_task(drain_stderr())
    try:
        if process.stdin is not None:
            process.stdin.write(full_prompt.encode())
            await process.stdin.drain()
            # Closed, not left open. Codex appends anything still on stdin to the
            # prompt, so an open pipe is a turn that waits for input nobody will send.
            process.stdin.close()

        while True:
            line = await process.stdout.readline()
            if not line:
                break
            raw = line.decode("utf-8", "replace").strip()
            if not raw or not raw.startswith("{"):
                continue
            try:
                event = json.loads(raw)
            except ValueError:
                # A line that is not JSON on a stream documented as JSONL. Kept in the
                # diagnostics rather than dropped, because it is evidence.
                tail.append(raw)
                continue
            for translated in turn.translate(event):
                yield translated

        code = await asyncio.wait_for(process.wait(), _EXIT_GRACE)
    except TimeoutError:                                          # pragma: no cover
        process.kill()
        code = -1
    except Exception as exc:
        log.exception("codex turn failed")
        _terminate(process)
        yield {"type": "error", "text": f"{type(exc).__name__}: {exc}",
               "resume_failed": _looks_like_a_dead_session(str(exc), resume)}
        return
    finally:
        stderr_task.cancel()
        _terminate(process)
    # No `yield` in that `finally`, for the reason `assistant.run` spells out: closing
    # an async generator raises GeneratorExit at the paused yield, and yielding while
    # unwinding aborts teardown — here that would leave the CLI subprocess alive.

    if turn.retries and not turn.last_error:
        yield {"type": "notice",
               "text": f"The connection dropped {turn.retries} times and recovered."}

    if turn.last_error or code not in (0, None):
        detail = turn.last_error or "\n".join(tail) or f"the CLI exited with code {code}"
        yield {"type": "error", "text": _explain(detail, tail, turn.retries),
               "resume_failed": _looks_like_a_dead_session(detail, resume)}


def _terminate(process) -> None:
    """Kill a CLI that outlived its turn, and never raise doing it."""
    try:
        if process.returncode is None:
            process.kill()
    except (ProcessLookupError, OSError):                         # pragma: no cover
        pass


def _explain(detail: str, tail, retries: int) -> str:
    """Turn the CLI's failure into a sentence with something to do in it.

    Every branch below is a state that produced an unreadable message in testing. A
    turn that ends in "unexpected status 401 Unauthorized: Missing bearer or basic
    authentication in header, url: wss://api.openai.com/v1/responses, cf-ray: …" is
    the exact failure this app exists not to have: it is true, it is complete, and it
    tells the operator nothing about pressing Sign in.
    """
    low = detail.lower()
    joined = ("\n".join(tail)).lower()

    if "401" in low or "missing bearer" in low or "unauthorized" in low:
        if "incorrect api key" in low or "invalid_api_key" in low:
            return ("The API key Codex is using was rejected. Run `codex logout`, then "
                    "press Sign in to use your ChatGPT plan instead — this app does "
                    "not need a key.\n\n" + detail)
        return ("ChatGPT rejected the sign-in for this turn. The credential has "
                "probably expired: press Sign in to sign in again with your ChatGPT "
                "account, then send this message a second time.\n\n" + detail)

    if "429" in low or "rate limit" in low or "usage limit" in low or "quota" in low:
        return ("Your ChatGPT plan's limit for Codex has been reached. It resets on a "
                "window rather than at midnight, so the answer is either to wait or to "
                "switch this thread to Claude in the picker.\n\n" + detail)

    if "model" in low and ("not found" in low or "not available" in low
                           or "does not exist" in low or "unsupported" in low
                           or "access" in low):
        return ("That model is not available on your ChatGPT plan. Pick a different one "
                "in the composer — GPT-5.6 Luna is on the widest range of plans — and "
                "send this message again.\n\n" + detail)

    if any(sign in low or sign in joined for sign in
           ("dns", "getaddrinfo", "temporary failure in name resolution",
            "connection refused", "network is unreachable", "timed out",
            "certificate", "tls", "proxy")):
        return ("This machine could not reach api.openai.com. Check the network, and a "
                "VPN or proxy if there is one — nothing was sent, so nothing was "
                f"spent.{f' It retried {retries} times first.' if retries else ''}"
                "\n\n" + detail)

    if "failed to start" in low or ("mcp" in low and "server" in low):
        return ("The studio's tools could not be started, so the agent would have been "
                "able to talk but not to do anything. That is this app's own tool "
                "server, not something you configured: the message below is what it "
                "printed.\n\n" + detail)

    return detail


# Substrings the CLI uses when the session it was asked to resume is gone. Matched on
# text because there is no exit code that distinguishes it, and guessing wrong means
# either a bricked thread or a silent retry that hides a real failure.
_DEAD_SESSION_SIGNS = (
    # The one 0.146.0 actually prints, measured by resuming an id that never existed:
    #   Error: thread/resume: thread/resume failed: no rollout found for thread id …
    # It arrives on stderr with a non-zero exit rather than as a JSONL event, which is
    # why the diagnostics tail is what gets matched and not just the last error event.
    "no rollout found", "thread/resume",
    "no conversation found", "session not found", "no such session",
    "could not resume", "invalid session", "no recorded session",
    "failed to load session", "unknown session",
)


def _looks_like_a_dead_session(detail: str, resume: str | None) -> bool:
    """Did this turn fail *because* the session it tried to resume no longer exists?

    Same recovery as the Claude path: `routes_agent` retries once from scratch. Codex
    keeps its sessions as files under CODEX_HOME, so this happens for the ordinary
    reasons — the folder was cleared, the app was copied to another machine, or the
    turn that created the thread ran with `--ephemeral`.
    """
    if not resume:
        return False
    text = detail.lower()
    return any(sign in text for sign in _DEAD_SESSION_SIGNS)


def session_files() -> Path:
    """Where the CLI keeps resumable sessions. Reported, not managed."""
    return codex_auth.codex_home() / "sessions"
