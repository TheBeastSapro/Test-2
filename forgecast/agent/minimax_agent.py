"""MiniMax as an agent backend, spending the subscription rather than an API balance.

## The shape of this, and why it is not the other two

Claude and Codex are *agentic* CLIs: hand them a prompt and they run their own loop,
calling tools until they are done. `mmx text chat` is not that. It is one completion per
invocation — verified from its own help text, which documents `--message`,
`--messages-file`, `--system`, `--tool` and nothing resembling a session or a resume.

So the loop lives here. Send the thread, read the reply, run any tool it asked for, append
the result, send again. That is the same loop `api_agent` runs against an HTTP endpoint,
and the reason it is written twice rather than shared is the one thing that differs and
matters: **the transport is the CLI**, because the CLI is what holds the subscription
login. An HTTP call would need a key, and a key is billed per token — which is the whole
thing this backend exists to avoid.

## What that costs, stated plainly

**No server-side session.** `mmx` has no `resume`, so the thread is re-sent every turn.
A long conversation costs more here than on Claude, and that is a property of the vendor's
CLI, not a choice made here.

**No sandbox of its own.** Claude and Codex police file edits and shell commands inside
their own permission models. There is no CLI sandbox here, so the only tools that exist
are this app's own MCP tools, which touch this app's own data and nothing else. That makes
this a *narrower* backend, not a more dangerous one.

**It cannot ask.** One completion per step, non-interactive, so there is no way to pause
for confirmation. `decide_gate` is therefore never offered — the same rule Codex follows,
for the same reason: approving a gate releases real spend, and a backend that cannot stop
to ask must not hold the tool that does it.

## Verified, not assumed

`mmx text chat --model MiniMax-M3 --system <text> --messages-file - --tool <json-or-path>
--output json --max-tokens <n>` — every flag read from `mmx text chat --help` on the real
binary. The default model it reports is `MiniMax-M3`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

log = logging.getLogger("forgecast.agent.minimax_agent")

# What the CLI itself reports as its default, plus the reasoning variant. Kept short on
# purpose: a picker listing every model a vendor has ever shipped is a picker nobody reads,
# and an id that no longer resolves is a turn that fails after the operator chose it.
MODELS = [
    {"id": "MiniMax-M3", "label": "MiniMax M3",
     "note": "the CLI's own default — general work, fastest"},
    {"id": "MiniMax-M2", "label": "MiniMax M2",
     "note": "the previous generation, if M3 behaves oddly on a task"},
]
DEFAULT_MODEL = "MiniMax-M3"

# Matches `api_agent`. Each step is a CLI round trip and a tool call against this app's own
# data; a loop that can run forty times on a bad prompt is a loop that can waste forty
# turns of a plan. A ceiling on damage, not a target.
MAX_STEPS = 12

# One turn's ceiling. `mmx config show` reports its own timeout as 300s, so this sits just
# past it: the CLI should be the thing that gives up, with its own error message, rather
# than being killed from outside and leaving nothing to report.
TIMEOUT_SECONDS = 330.0


def system_prompt(studio) -> str:
    """The same brief the other backends get, from the one place it is written."""
    from . import assistant

    return assistant.system_prompt(studio)


async def run(
    prompt: str,
    *,
    studio,
    model: str = DEFAULT_MODEL,
    user_id: int = 0,
    allowed: list[str] | None = None,
    history: list[dict] | None = None,
    root=None,
) -> AsyncIterator[dict]:
    """One turn, as the same event stream every other backend emits.

    The contract is `assistant.run`'s and it is not negotiable: `session`, `text`, `tool`,
    `tool_result`, `result`, `error`. `chat.js` renders exactly these, and a seventh shape
    would be a silent hole in the transcript.
    """
    import asyncio

    from . import minimax_auth, tools as tool_module

    cli = minimax_auth.find_cli(root)
    if not cli:
        yield {"type": "error",
               "text": ("The MiniMax CLI is not installed, so this backend cannot run. "
                        f"Install it once: {minimax_auth.INSTALL_HINT} — or switch to "
                        "Claude, which needs nothing new.")}
        return

    state = minimax_auth.login_state(cli)
    if not state.signed_in:
        yield {"type": "error",
               "text": ("Nobody has signed in to MiniMax on this machine. Press Sign in "
                        "under the picker: it opens the browser flow and uses your "
                        "subscription, with no API key.")}
        return

    server = tool_module.build_server(studio)
    built = tool_module.built_tools(server)
    permitted = {name.split("__")[-1] for name in
                 (allowed if allowed is not None else tool_module.ALLOWED)}
    callables = {str(getattr(t, "name", "")): t for t in built}

    from .api_agent import function_schemas

    schemas = function_schemas(server, allowed if allowed is not None
                              else tool_module.ALLOWED)

    messages: list[dict] = list(history or [])
    messages.append({"role": "user", "content": prompt})

    # No provider-side session to resume, so the thread id is the caller's. Emitted anyway
    # so the front end's persistence path is identical across backends.
    yield {"type": "session", "session_id": ""}

    system = system_prompt(studio)

    for step in range(MAX_STEPS):
        argv = [cli, "text", "chat", "--model", model or DEFAULT_MODEL,
                "--system", system, "--messages-file", "-",
                "--output", "json", "--max-tokens", "4096"]
        for schema in schemas:
            # `--tool` is repeatable and takes JSON inline. Passed as an argument rather
            # than written to temporary files: twenty-two files per turn is twenty-two
            # things to clean up after a crash.
            argv += ["--tool", json.dumps(schema)]

        payload, failure = await _call(argv, messages)
        if failure:
            yield {"type": "error", "text": failure}
            return

        text, calls = _reply(payload)
        if text:
            yield {"type": "text", "text": text}

        if not calls:
            usage = (payload.get("usage") or {}) if isinstance(payload, dict) else {}
            yield {"type": "result", "session_id": "", "turns": step + 1,
                   # None rather than 0: this backend spends a subscription, and printing
                   # "$0.00" would claim a precision — and a price — it does not have.
                   "cost_usd": None, "is_error": False,
                   "tokens": usage.get("total_tokens")}
            return

        # Appended verbatim, the assistant message included: a provider handed tool
        # results with no matching request rejects the whole conversation.
        messages.append({"role": "assistant", "content": text or None,
                         "tool_calls": calls})

        for call in calls:
            function = call.get("function") or {}
            name = str(function.get("name") or "")
            call_id = str(call.get("id") or "")
            raw = function.get("arguments") or "{}"
            try:
                arguments = json.loads(raw) if isinstance(raw, str) else dict(raw)
            except ValueError:
                arguments = {}

            yield {"type": "tool", "id": call_id, "name": name, "input": arguments}

            if name not in permitted:
                # Refused here rather than at the tool, so the reason names the backend's
                # limit instead of looking like the tool is broken.
                result, failed = (
                    f"{name} is not available on the MiniMax backend. Approving a gate "
                    f"releases real spend and this backend cannot stop to ask you first.",
                    True)
            else:
                result, failed = await _invoke(callables.get(name), name, arguments)

            yield {"type": "tool_result", "id": call_id, "is_error": failed,
                   "text": result[:4000]}
            messages.append({"role": "tool", "tool_call_id": call_id, "name": name,
                             "content": result[:8000]})

    yield {"type": "error",
           "text": (f"Stopped after {MAX_STEPS} tool calls without finishing. That cap "
                    f"exists so a bad prompt cannot run away — ask for one step at a "
                    f"time, or use Claude for this.")}


async def _call(argv: list[str], messages: list[dict]) -> tuple[dict, str]:
    """One `mmx text chat`, with the thread on stdin. Returns (payload, failure)."""
    import asyncio

    from ..desktop.toolchain import _no_window

    body = json.dumps({"messages": messages}).encode("utf-8")
    try:
        process = await asyncio.create_subprocess_exec(
            *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, **_no_window())
    except OSError as exc:
        return {}, f"Could not start the MiniMax CLI: {type(exc).__name__}: {exc}"

    try:
        out, err = await asyncio.wait_for(process.communicate(body),
                                          timeout=TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        process.kill()
        return {}, (f"MiniMax did not answer within {int(TIMEOUT_SECONDS)}s. Nothing was "
                    f"left running.")

    text = (out or b"").decode("utf-8", "replace")
    trailing = (err or b"").decode("utf-8", "replace").strip()

    payload = _first_json_object(text)
    if payload is None:
        detail = trailing or text.strip() or "no output"
        return {}, f"MiniMax's CLI returned nothing usable:\n{detail[:500]}"

    if isinstance(payload.get("error"), dict):
        error = payload["error"]
        hint = str(error.get("hint") or "").strip()
        return {}, (f"MiniMax refused: {error.get('message') or 'unknown error'}"
                    + (f"\n{hint}" if hint else ""))
    return payload, ""


def _first_json_object(text: str) -> dict | None:
    """The JSON object in the CLI's output, past its banner.

    `mmx` prints an ASCII logo before its payload on some paths, so `json.loads(text)`
    fails on output that is perfectly good. Scanned for the first balanced object rather
    than split on a marker, because the banner is cosmetic and changes between releases.
    """
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    parsed = json.loads(text[start:index + 1])
                except ValueError:
                    start = -1
                    continue
                if isinstance(parsed, dict):
                    return parsed
                start = -1
    return None


def _reply(payload: dict) -> tuple[str, list[dict]]:
    """The assistant's text and its tool calls, from either shape this API answers in.

    MiniMax's Messages API is OpenAI-compatible, so `choices[0].message` is the usual
    place — but the CLI has also been seen to hand back the message object directly when
    it has nothing else to add. Reading only the nested form would present as "the model
    said nothing", which is indistinguishable from a refusal.
    """
    message = {}
    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or {}
    elif isinstance(payload.get("message"), dict):
        message = payload["message"]
    elif "content" in payload or "tool_calls" in payload:
        message = payload

    content = message.get("content") or ""
    if isinstance(content, list):
        # Some builds answer with content blocks rather than a string.
        content = "".join(block.get("text", "") for block in content
                          if isinstance(block, dict))
    calls = message.get("tool_calls") or []
    return str(content), [c for c in calls if isinstance(c, dict)]


async def _invoke(tool: Any, name: str, arguments: dict) -> tuple[str, bool]:
    """Call one MCP tool and flatten its result to text.

    Errors come back as text with the flag set rather than raising, exactly as the MCP
    path does: an exception here would end the turn, where a model given the error can
    usually recover by calling something else.
    """
    if tool is None:
        return (f"No tool called {name!r} exists on this backend.", True)
    handler = getattr(tool, "handler", None) or getattr(tool, "fn", None) or tool
    try:
        result = handler(arguments)
        if hasattr(result, "__await__"):
            result = await result
    except Exception as exc:
        log.warning("tool %s failed: %s", name, exc)
        return (f"{type(exc).__name__}: {exc}", True)

    if isinstance(result, dict):
        failed = bool(result.get("is_error"))
        blocks = result.get("content") or []
        text = "\n".join(str(b.get("text", "")) for b in blocks
                         if isinstance(b, dict)) or json.dumps(result, default=str)
        return (text, failed)
    return (str(result), False)
