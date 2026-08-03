"""A tool-calling agent over any OpenAI-compatible chat API.

## Why this exists alongside the two subscription backends

Claude and ChatGPT both run through a CLI you sign in to, on a plan you already pay for.
That is the better deal and they stay the default and the first alternative. But it is not
the only deal, and refusing to offer anything else means the operator's answer to "can I
use MiniMax" is no — when the honest answer is "yes, and it bills differently."

So this is the third kind of backend: a base URL, a key, and per-token billing, stated
plainly at the point of choosing rather than buried. MiniMax is the instance that was
asked for; DeepSeek, Together, Groq, OpenRouter and OpenAI's own API speak the same
dialect and cost nothing extra to support, because the dialect is what this file
implements rather than any one vendor.

## What it is honest about

**It bills per token.** `Engine.billing` says so under the picker, and it is not softened.
Someone switching from Claude to this is changing what a conversation costs them, and
finding that out from an invoice is not acceptable.

**It has no sandbox.** The two CLI backends run inside their own permission model — file
edits, shell commands, web access are theirs to police. Here there is no CLI, so the only
tools that exist are this app's own MCP tools, which read and write this app's own data
and nothing else. That is a *narrower* backend, not a more dangerous one, and the picker
says which capabilities are missing rather than letting the operator discover it.

**It cannot ask.** One HTTP round trip per step, non-interactive, so there is no way to
pause and confirm. `decide_gate` is therefore not offered to it at all — the same rule the
Codex backend follows, for the same reason: approving a gate releases real spend, and a
backend that cannot stop to ask must not be holding the tool that does it.

## Why the tools are not defined twice

`tools.build_server()` already describes every operation once, for MCP. Its tool objects
carry a name, a description and a parameter schema, which is exactly what an OpenAI
`functions` array needs — so the schemas are *derived* from that object here. A second
hand-written list would drift within a week, and only one of the two would get fixed.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

log = logging.getLogger("forgecast.agent.api_agent")

# Kept low deliberately. Each step is a network round trip and a tool call against this
# app's own data; a loop that can run forty times on a bad prompt is a loop that can spend
# forty times. The cap is a ceiling on damage, not a target.
MAX_STEPS = 12

# One turn's ceiling. Long enough for a research call that reads a channel, short enough
# that a hung provider does not hold a browser request open indefinitely.
TIMEOUT_SECONDS = 180.0


class VENDORS:
    """The dialects known to work, with the endpoint each one publishes.

    Named rather than free-typed so a typo in a base URL is a missing entry rather than a
    connection that times out with no explanation. Anything not here can still be used by
    giving a base URL directly — the point of the list is a working default, not a gate.
    """

    MINIMAX = "minimax"
    OPENAI = "openai"
    DEEPSEEK = "deepseek"


BASE_URLS = {
    VENDORS.MINIMAX: "https://api.minimax.io/v1",
    VENDORS.OPENAI: "https://api.openai.com/v1",
    VENDORS.DEEPSEEK: "https://api.deepseek.com/v1",
}


def function_schemas(server: Any, allowed: list[str] | None = None) -> list[dict]:
    """Every MCP tool on `server`, as OpenAI function definitions.

    Derived from the server object rather than written out, so the two backends cannot
    describe the same operation differently. `allowed` is the un-namespaced set this
    backend may hold; anything outside it is dropped here rather than refused later,
    because a model that can see a tool will eventually call it.
    """
    permitted = None if allowed is None else {name.split("__")[-1] for name in allowed}
    out: list[dict] = []

    for tool in _tools_of(server):
        name = str(getattr(tool, "name", "") or "")
        if not name or (permitted is not None and name not in permitted):
            continue
        schema = getattr(tool, "input_schema", None) or getattr(tool, "schema", None) or {}
        if not isinstance(schema, dict) or "properties" not in schema:
            # The SDK accepts a plain `{"field": str}` mapping as well as JSON Schema.
            schema = _schema_from_mapping(schema if isinstance(schema, dict) else {})
        out.append({
            "type": "function",
            "function": {
                "name": name,
                "description": str(getattr(tool, "description", "") or "")[:900],
                "parameters": schema,
            },
        })
    return out


def _tools_of(server: Any) -> list[Any]:
    """The tool objects that went into this server.

    Asked of `tools.built_tools` rather than read off the server, because
    `create_sdk_mcp_server` returns an opaque MCP `Server` whose tool list is reachable
    only through a request handler that needs a live request context. Introspecting it was
    the first attempt: it silently returned nothing, which presents as "the model ignored
    its tools" and costs a day of debugging the prompt for a problem in the plumbing.
    """
    from . import tools as tool_module

    return tool_module.built_tools(server)


_JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _schema_from_mapping(mapping: dict) -> dict:
    """`{"url": str}` into JSON Schema.

    Nothing is marked required. The SDK's own builder marks every parameter required,
    which is why `create_channel` demands all six fields on the MCP backends — a
    pre-existing bug worth not reproducing here.
    """
    properties = {
        key: {"type": _JSON_TYPES.get(value, "string")}
        for key, value in mapping.items()
        if not key.startswith("_")
    }
    return {"type": "object", "properties": properties, "required": []}


async def run(
    prompt: str,
    *,
    studio,
    system: str,
    model: str,
    api_key: str,
    base_url: str,
    allowed: list[str] | None = None,
    history: list[dict] | None = None,
) -> AsyncIterator[dict]:
    """One turn, as the same event stream the other backends emit.

    The contract is `assistant.run`'s and it is not negotiable: `session`, `text`,
    `tool`, `tool_result`, `result`, `error`. `chat.js` renders these and a fourth
    shape would be a silent hole in the transcript.

    `history` is this backend's session: there is no server-side conversation to resume
    the way the CLI backends have one, so the caller replays the thread. That is stated
    here because it is the one real difference in behaviour — a very long thread costs
    more per turn on this backend than on the others, since the whole thing is re-sent.
    """
    import httpx

    from . import tools as tool_module

    if not api_key:
        yield {"type": "error",
               "text": "No API key for this backend. Settings → the agent's key. "
                       "Or switch back to Claude, which signs in with your subscription "
                       "and needs no key."}
        return

    server = tool_module.build_server(studio)
    schemas = function_schemas(server, allowed if allowed is not None else tool_module.ALLOWED)
    callables = {str(getattr(t, "name", "")): t for t in _tools_of(server)}

    messages: list[dict] = [{"role": "system", "content": system}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": prompt})

    # There is no provider-side session, so the thread id is the caller's. Emitted anyway
    # so the front end's persistence path is identical across backends.
    yield {"type": "session", "session_id": ""}

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            for step in range(MAX_STEPS):
                body = {"model": model, "messages": messages}
                if schemas:
                    body["tools"] = schemas
                    body["tool_choice"] = "auto"

                response = await client.post(f"{base_url.rstrip('/')}/chat/completions",
                                             json=body, headers=headers)
                if response.status_code != 200:
                    yield {"type": "error", "text": _explain(response)}
                    return

                payload = response.json()
                choice = (payload.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                text = message.get("content") or ""
                calls = message.get("tool_calls") or []

                if text:
                    yield {"type": "text", "text": text}

                if not calls:
                    usage = payload.get("usage") or {}
                    yield {"type": "result", "session_id": "", "turns": step + 1,
                           "cost_usd": None, "is_error": False,
                           "tokens": usage.get("total_tokens")}
                    return

                # Appended verbatim, including the assistant message that requested the
                # calls: a provider that receives tool results with no matching request
                # rejects the whole conversation.
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

                    yield {"type": "tool", "id": call_id, "name": name,
                           "input": arguments}

                    result, failed = await _invoke(callables.get(name), name, arguments)
                    yield {"type": "tool_result", "id": call_id, "is_error": failed,
                           "text": result[:4000]}
                    messages.append({"role": "tool", "tool_call_id": call_id,
                                     "name": name, "content": result[:8000]})

            yield {"type": "error",
                   "text": f"Stopped after {MAX_STEPS} tool calls without finishing. "
                           f"That cap exists so a bad prompt cannot spend without limit — "
                           f"ask for one step at a time, or use Claude for this."}
    except httpx.HTTPError as exc:
        yield {"type": "error",
               "text": f"Could not reach {base_url}: {type(exc).__name__}: {exc}. "
                       f"Nothing was sent, so nothing was spent."}


async def _invoke(tool: Any, name: str, arguments: dict) -> tuple[str, bool]:
    """Call one MCP tool and flatten its result to text.

    Errors come back as text with the flag set rather than raising, exactly as the MCP
    path does: an exception here would end the turn, where the model given the error can
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


def _explain(response: Any) -> str:
    """A provider's HTTP failure, as something to act on.

    The status alone tells the operator nothing they can use, and the raw body is usually
    a nested JSON blob. Each of these is a different action.
    """
    body = ""
    try:
        body = json.dumps(response.json())[:300]
    except Exception:
        body = (getattr(response, "text", "") or "")[:300]

    code = response.status_code
    if code in (401, 403):
        return ("The API key was rejected. Check it in Settings for a trailing space, "
                f"and that it is for this provider.\n{body}")
    if code == 404:
        return (f"That model is not available on this key.\n{body}")
    if code == 429:
        return ("Rate limited, or the account is out of credit. This backend bills per "
                f"token — check the balance with the provider.\n{body}")
    if code >= 500:
        return f"The provider returned {code}. Nothing was charged for a failed call.\n{body}"
    return f"The provider returned {code}.\n{body}"
