"""
The studio, as tools Claude can call.

WHAT CHANGED AND WHY
    This app used to route messages itself: a long paste was a script, a short
    line was feedback, audio was a reference. That worked, and it was still the
    wrong shape -- it meant talking to a form that happened to look like a chat.
    Rookcast is not a form. You tell the agent what you want and the agent does
    it, because the agent HAS the tools.

    So the pipeline is exposed as MCP tools running in this process. Claude
    loads the reference, renders takes, moves the dials, reads the script and
    runs the render. No routing rules, no keyword table deciding what you meant.

WHAT IS DELIBERATELY NOT A TOOL
    Saving over a voice profile and deleting anything. Renders and takes are
    cheap and reversible; a profile Sapro spent an evening tuning is neither,
    and neither is audio that is not in git. Those stay buttons.

    render_script is a tool, and it is the expensive one -- tens of minutes of
    GPU. It reports what it is about to do first (chunks, estimated time) so a
    wrong instruction is visible in the transcript before it costs an hour.
"""
from pathlib import Path


def build_server(ctx):
    """
    Wrap the studio's operations as an in-process MCP server.

    `ctx` is supplied by server.py rather than imported, because these tools
    need the SAME live settings and the same loaded reference the UI is showing
    -- a second copy of that state would drift within one conversation.
    """
    from claude_agent_sdk import tool, create_sdk_mcp_server

    @tool("voice_status", "What voice reference is loaded right now, if any.", {})
    async def voice_status(args):
        return _text(ctx.voice_status())

    @tool("use_voice_reference",
          "Make an audio file the voice that everything is rendered in. Use the "
          "path of a clip the user attached.",
          {"path": str})
    async def use_voice_reference(args):
        return _text(ctx.set_voice(args["path"]))

    @tool("render_take",
          "Render a sample in the current voice so the user can hear it. Pass "
          "`text` and it reads EXACTLY that, all of it, however long — it "
          "chunks and joins internally. Do not shorten what the user gave you: "
          "if they hand you thirty seconds of script, they want to hear thirty "
          "seconds. Leave `text` out to re-read whatever was tested last, which "
          "is what you want after adjust_voice so the comparison is the same "
          "words at new settings.",
          {"text": str})
    async def render_take(args):
        return _text(ctx.take(args.get("text") or ""))

    @tool("adjust_voice",
          "Move the voice settings from a plain-English note about the read, "
          "such as 'feels bit fast' or 'too flat'. Returns which numbers moved. "
          "Does not render -- call render_take after it.",
          {"feedback": str})
    async def adjust_voice(args):
        return _text(ctx.tune(args["feedback"]))

    @tool("set_voice_parameter",
          "Set one dial directly when you already know the value: exaggeration, "
          "cfg_weight, temperature or speed.",
          {"name": str, "value": float})
    async def set_voice_parameter(args):
        return _text(ctx.set_param(args["name"], args["value"]))

    @tool("analyse_script",
          "What a script would become: sections, chunks, chapter headers, "
          "finished length and render time. Cheap. Always do this before "
          "render_script so the user can see the plan first.",
          {"script": str})
    async def analyse_script(args):
        return _text(ctx.analyse(args["script"]))

    @tool("render_script",
          "Render a full script to a finished, mastered file. EXPENSIVE -- tens "
          "of minutes of GPU. Show the user analyse_script first and let them "
          "agree before calling this.",
          {"script": str, "title": str})
    async def render_script(args):
        return _text(ctx.render(args["script"], args.get("title") or ""))

    @tool("list_elevenlabs_voices",
          "The ElevenLabs voices on the account, with their ids. Only useful "
          "when the engine is elevenlabs. Never invent a voice id — take one "
          "from this list.", {})
    async def list_elevenlabs_voices(args):
        return _text(ctx.eleven_voices())

    @tool("set_engine",
          "Switch which engine renders audio: 'chatterbox' (local, free, on "
          "Sapro's GPU) or 'elevenlabs' (costs per character, needs a key). "
          "Optionally set the ElevenLabs voice at the same time. Say what it "
          "will cost before switching to elevenlabs for a long script.",
          {"engine": str, "voice_id": str})
    async def set_engine(args):
        return _text(ctx.set_engine(args["engine"], args.get("voice_id") or ""))

    @tool("read_render_log",
          "The log of the last full render, including anything the read-check "
          "could not resolve.", {})
    async def read_render_log(args):
        return _text(ctx.render_log())

    return create_sdk_mcp_server(
        name="vostudio", version="1.0.0",
        tools=[voice_status, use_voice_reference, render_take, adjust_voice,
               set_voice_parameter, analyse_script, render_script,
               list_elevenlabs_voices, set_engine, read_render_log],
    )


# Every tool is namespaced by the server it came from, so this is the list the
# agent is allowed to call without a prompt. Rendering audio is not an edit to
# anything that cannot be redone.
ALLOWED = [
    "mcp__vostudio__voice_status",
    "mcp__vostudio__use_voice_reference",
    "mcp__vostudio__render_take",
    "mcp__vostudio__adjust_voice",
    "mcp__vostudio__set_voice_parameter",
    "mcp__vostudio__analyse_script",
    "mcp__vostudio__render_script",
    "mcp__vostudio__list_elevenlabs_voices",
    "mcp__vostudio__set_engine",
    "mcp__vostudio__read_render_log",
]


def _text(payload) -> dict:
    """MCP content, with errors flagged rather than described."""
    import json
    if isinstance(payload, dict) and payload.get("error"):
        return {"content": [{"type": "text", "text": str(payload["error"])}],
                "is_error": True}
    body = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    return {"content": [{"type": "text", "text": body}]}
