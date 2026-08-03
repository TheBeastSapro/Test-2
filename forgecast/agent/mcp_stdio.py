"""The same 21 tools, over a pipe, for an agent that does not run in this process.

## Why this file is not a second copy of the tools

`tools.build_server()` defines the studio's operations once, as an in-process MCP
server. Claude reaches it with no transport at all — the agent SDK runs the server
inside this Python process. The Codex CLI cannot: it is a separate binary and it
speaks to MCP servers over stdio or HTTP.

The obvious fix is to write the tool list out a second time as OpenAI function
definitions. That is the thing not to do — twenty-one descriptions maintained in two
places drift within a week, and only one of the two gets the fix. So this module
takes the *same* server object and serves it over stdin/stdout. One definition, two
transports.

## Nothing may be printed

Stdout is the protocol. A stray `print`, a logging handler pointed at stdout, or a
library banner lands in the middle of a JSON-RPC frame and the CLI drops the server
with a parse error that names none of that. Handlers are moved to stderr below, where
the CLI collects them as diagnostics.

## Why a subprocess is not a second copy of the app's state

`Studio` holds a session *factory* and a user id, and opens a fresh session per call
(see its docstring). It caches nothing. So this process reads and writes the same
database through the same code as the pages do — which is the property that mattered,
rather than being the same Python object.

## Why `decide_gate` is not served here

Claude can be handed a tool it must ask before using: the CLI stops and prompts, and
`assistant.build_options` leaves `decide_gate` out of the pre-allowed list for exactly
that reason. `codex exec` is non-interactive — there is nobody to prompt, so a tool
offered to it is a tool it may call. Approving a gate is what releases real spend, so
for this transport the tool is not merely un-allowed, it is absent. The filter is
derived from `tools.ALLOWED`, so adding a tool to the app adds it here too.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys

log = logging.getLogger("forgecast.agent.mcp_stdio")


def _quiet_stdout() -> None:
    """Move every log handler to stderr before a byte of protocol is written.

    Importing the app can configure logging, and a handler that defaults to stdout
    corrupts the first JSON-RPC frame. The failure looks like the CLI refusing the
    server for no reason, which is unbelievably hard to read from the other end.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, logging.StreamHandler) and handler.stream is sys.stdout:
            root.removeHandler(handler)
    if not root.handlers:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)


def _studio():
    """The studio for the account this server was started on behalf of.

    The id is passed in the environment rather than argv because argv is visible in
    every process listing on the machine, and because `Studio` already knows how to
    fall back to the single account or the configured owner when it is absent.
    """
    from ..db import SessionLocal
    from .studio import Studio

    raw = (os.environ.get("FORGECAST_AGENT_USER_ID") or "").strip()
    return Studio(SessionLocal, user_id=int(raw) if raw.isdigit() else None)


def served_tools() -> set[str]:
    """The tool names this transport offers, from the one list that decides it."""
    from . import tools

    return {name.rsplit("__", 1)[-1] for name in tools.ALLOWED}


def _restrict(server, allowed: set[str]) -> None:
    """Filter the built server's handlers rather than building a different server.

    Wrapping the handlers keeps `tools.build_server()` the only place a tool is
    defined. Refusing the call as well as hiding it from the listing is deliberate: a
    model that learned the name from the conversation can still ask for it, and a
    hidden-but-callable tool is not a boundary.
    """
    from mcp.types import CallToolRequest, ListToolsRequest

    list_tools = server.request_handlers[ListToolsRequest]
    call_tool = server.request_handlers[CallToolRequest]

    async def listing(request):
        result = await list_tools(request)
        result.root.tools = [t for t in result.root.tools if t.name in allowed]
        return result

    async def call(request):
        name = request.params.name
        if name not in allowed:
            from mcp.types import CallToolResult, ServerResult, TextContent

            return ServerResult(CallToolResult(
                content=[TextContent(
                    type="text",
                    text=f"{name} is not available to this agent. Approving a gate is "
                         f"the user's decision and this backend cannot stop to ask, so "
                         f"ask them in the chat and let them press the button.")],
                isError=True))
        return await call_tool(request)

    server.request_handlers[ListToolsRequest] = listing
    server.request_handlers[CallToolRequest] = call


async def serve() -> None:
    from mcp.server.stdio import stdio_server

    from . import tools

    server = tools.build_server(_studio())["instance"]
    _restrict(server, served_tools())
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream,
                         server.create_initialization_options())


def main() -> int:
    _quiet_stdout()
    # A closed pipe is how this process is *meant* to end: the CLI exits and the
    # parent's stdout goes away. Letting that surface as a traceback would put a
    # crash in the operator's log for every normal shutdown.
    with contextlib.suppress(KeyboardInterrupt, BrokenPipeError, anyio_closed()):
        asyncio.run(serve())
    return 0


def anyio_closed() -> type[BaseException]:
    """anyio's name for "the other end went away", or a stand-in if it moves."""
    try:
        from anyio import BrokenResourceError

        return BrokenResourceError
    except ImportError:                                           # pragma: no cover
        return BrokenPipeError


if __name__ == "__main__":
    raise SystemExit(main())
