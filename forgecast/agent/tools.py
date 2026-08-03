"""The studio as tools Claude can call.

## Why this replaced the forms

The app used to be a dashboard: a page for channels, a page for runs, a page for
research, each with a form. That works, and it is still the wrong shape — it means
filling in a form that happens to be attached to an agent. You already know what you
want; typing it into eight fields first is the app making you do the translating.

So the operations are exposed as MCP tools running inside this process. You say
"set up a channel like this one" with a link, and the agent reads the channel,
measures what it publishes, creates it and starts the first run. No routing rules, no
keyword table deciding what you meant.

The forms are still there. They are just no longer the only way in, and neither is
the agent — both call `studio.py`, so they cannot disagree.

## What is deliberately NOT a tool

Deleting anything, and spending money without a gate. Every tool here is either
read-only or produces something that can be produced again:

* `start_run` costs credits, but it stops at the first gate before spending on the
  expensive stages, and it reports the hold it took.
* `decide_gate` is the one that releases real spend — and it is the one the agent is
  told never to call on its own judgement.

Deleting a channel, deleting a style and clearing credentials stay buttons. Those are
not reversible by re-running them, and finding out afterwards is not an option.
"""

from __future__ import annotations

import json
from typing import Any

# Namespaced by the server they come from. This is the list the agent may call
# without stopping to ask, and it is deliberately not "everything".
SERVER_NAME = "forgecast"

_READ_ONLY = (
    "studio_status", "list_channels", "study_youtube_channel", "list_runs",
    "run_status", "preview_run", "list_styles", "score_videos", "research_channel",
    "run_files",
)
_WRITES = ("create_channel", "update_channel", "start_run", "apply_style",
           "blend_styles", "cancel_run")

# `decide_gate` is intentionally absent: approving a gate is the moment the run is
# allowed to spend on the stage behind it, and that is the user's call, not a step
# the agent gets to take because it seemed reasonable.
ALLOWED = [f"mcp__{SERVER_NAME}__{name}" for name in (*_READ_ONLY, *_WRITES)]

ALL_TOOLS = [*_READ_ONLY, *_WRITES, "decide_gate"]


def _text(payload: Any) -> dict:
    """MCP content, with errors flagged rather than merely described.

    `is_error` matters: without it a returned `{"error": ...}` reads to the model as
    a successful call whose result happens to mention a problem, and it carries on.
    """
    if isinstance(payload, dict) and payload.get("error"):
        return {"content": [{"type": "text", "text": str(payload["error"])}],
                "is_error": True}
    body = payload if isinstance(payload, str) else json.dumps(payload, default=str,
                                                               indent=1)
    return {"content": [{"type": "text", "text": body}]}


def build_server(studio):
    """Wrap the studio's operations as an in-process MCP server.

    `studio` is passed in rather than constructed here so the tools and the pages
    share one object. A second copy would drift inside a single conversation — the
    panel showing a channel the agent has already renamed.
    """
    from claude_agent_sdk import create_sdk_mcp_server, tool

    @tool("studio_status",
          "What this install is: which account, mock or live, whether ffmpeg is "
          "present, credit balance, how many channels, and which runs are waiting "
          "for a decision. Call this at the start of a conversation.", {})
    async def studio_status(args):
        return _text(studio.status())

    # ------------------------------------------------------------------ channels

    @tool("list_channels",
          "Every channel, with its format, length and how many runs it has. "
          "Pass format 'longform' or 'shorts' to narrow it.",
          {"format": str})
    async def list_channels(args):
        return _text(studio.list_channels(fmt=(args.get("format") or "").strip()))

    @tool("study_youtube_channel",
          "Read a real YouTube channel from a link or @handle and report what it "
          "publishes: name, subscribers, median upload length, whether that makes it "
          "long-form or Shorts, recent titles, and which uploads beat their own "
          "cohort. Read-only — use it before create_channel so the setup is measured "
          "rather than guessed.",
          {"url": str})
    async def study_youtube_channel(args):
        return _text(studio.study_youtube_channel(args.get("url") or ""))

    @tool("create_channel",
          "Create a channel. `format` is 'longform' or 'shorts' and decides the "
          "aspect ratio and default length. Give `niche` in plain words — it steers "
          "every script written for this channel.",
          {"name": str, "niche": str, "format": str, "language": str,
           "target_seconds": int, "youtube_channel_id": str})
    async def create_channel(args):
        return _text(studio.create_channel(
            args.get("name") or "",
            niche=args.get("niche") or "",
            fmt=(args.get("format") or "longform"),
            language=args.get("language") or "en",
            target_seconds=int(args.get("target_seconds") or 0),
            youtube_channel_id=args.get("youtube_channel_id") or "",
        ))

    @tool("update_channel",
          "Change a channel. Identify it by id or by name. Only the fields you pass "
          "are touched.",
          {"channel": str, "name": str, "niche": str, "language": str,
           "voice_id": str, "aspect_ratio": str, "target_duration_seconds": int})
    async def update_channel(args):
        changes = {k: v for k, v in args.items() if k != "channel"}
        return _text(studio.update_channel(args.get("channel"), **changes))

    # ---------------------------------------------------------------------- runs

    @tool("list_runs",
          "Recent runs and where each one is. Narrow by channel or by format.",
          {"channel": str, "format": str, "limit": int})
    async def list_runs(args):
        return _text(studio.list_runs(
            channel=args.get("channel") or None,
            fmt=(args.get("format") or "").strip(),
            limit=int(args.get("limit") or 20)))

    @tool("start_run",
          "Queue a video on a channel. Takes a credit hold and stops at the first "
          "gate — it does not run to completion on its own. Say what it reserved.",
          {"channel": str, "topic": str})
    async def start_run(args):
        return _text(studio.start_run(args.get("channel"), args.get("topic") or ""))

    @tool("run_status",
          "One run in full: every node and its state, what the waiting gate is "
          "asking, credits held and spent, and the last few events.",
          {"run_id": int})
    async def run_status(args):
        return _text(studio.run_status(int(args.get("run_id") or 0)))

    @tool("decide_gate",
          "Approve the gate a run is waiting on, or send it back with feedback. "
          "ONLY call this when the user has told you to in this conversation — "
          "approving is what allows the next stage to spend.",
          {"run_id": int, "approve": bool, "node_key": str, "note": str,
           "feedback": str})
    async def decide_gate(args):
        return _text(studio.decide_gate(
            int(args.get("run_id") or 0),
            approve=bool(args.get("approve", True)),
            node_key=args.get("node_key") or "",
            note=args.get("note") or "",
            feedback=args.get("feedback") or ""))

    @tool("cancel_run",
          "Stop a run and release the unspent part of its credit hold.",
          {"run_id": int})
    async def cancel_run(args):
        return _text(studio.cancel_run(int(args.get("run_id") or 0)))

    @tool("preview_run",
          "The edit as a timeline before anything renders: scene count, running "
          "length, frame size, the opening scenes, and which stages the preview is "
          "not yet showing. Free.",
          {"run_id": int})
    async def preview_run(args):
        return _text(studio.preview(int(args.get("run_id") or 0)))

    @tool("run_files", "What a run has written to disk so far.", {"run_id": int})
    async def run_files(args):
        return _text(studio.open_folder(int(args.get("run_id") or 0)))

    # ------------------------------------------------------------------- research

    @tool("research_channel",
          "Mine a YouTube channel for outliers from a link or @handle: which of its "
          "uploads beat their own cohort, by how much, and how reliable each number "
          "is. Needs a YouTube Data API key.",
          {"url": str, "limit": int})
    async def research_channel(args):
        return _text(studio.research_channel(args.get("url") or "",
                                             limit=int(args.get("limit") or 50)))

    @tool("score_videos",
          "Score statistics the user pasted — a table or a JSON array — into ranked "
          "outliers. Use this when there is no API key or the numbers came from "
          "somewhere else.",
          {"text": str})
    async def score_videos(args):
        return _text(studio.score_videos(args.get("text") or ""))

    # --------------------------------------------------------------------- styles

    @tool("list_styles",
          "Editing styles available: what each was learned from and what it does to "
          "cut rhythm, grade, captions and motion.", {})
    async def list_styles(args):
        return _text(studio.list_styles())

    @tool("apply_style",
          "Apply an editing style to a channel. Replaces its render spec, motion "
          "preset and map style; its tone and learned memory stay.",
          {"style": str, "channel": str})
    async def apply_style(args):
        return _text(studio.apply_style(args.get("style") or "",
                                        args.get("channel") or ""))

    @tool("blend_styles",
          "Mix two styles into a new one. Weight 0 keeps the first, 1 takes the "
          "second. Numbers interpolate; transitions and caption position switch at "
          "the halfway point because there is nothing between a cut and a dissolve.",
          {"first": str, "second": str, "weight": float, "name": str})
    async def blend_styles(args):
        return _text(studio.blend_styles(
            args.get("first") or "", args.get("second") or "",
            weight=float(args.get("weight") or 0.5), name=args.get("name") or ""))

    return create_sdk_mcp_server(
        name=SERVER_NAME, version="1.0.0",
        tools=[studio_status, list_channels, study_youtube_channel, create_channel,
               update_channel, list_runs, start_run, run_status, decide_gate,
               cancel_run, preview_run, run_files, research_channel, score_videos,
               list_styles, apply_style, blend_styles],
    )
