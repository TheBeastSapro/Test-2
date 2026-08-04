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

from . import skills_tools

# Namespaced by the server they come from. This is the list the agent may call
# without stopping to ask, and it is deliberately not "everything".
SERVER_NAME = "forgecast"

_READ_ONLY = (
    "studio_status", "list_channels", "study_youtube_channel", "list_runs",
    "run_status", "preview_run", "list_styles", "score_videos", "research_channel",
    "run_files", "cast_voice", "voice_catalogue", "voice_artists",
    # Reading which scripting method each channel writes to. It opens the operator's own
    # documents from a folder and reports what loaded; nothing is written, so it belongs
    # in the pre-allowed set — a check the agent has to ask permission for is a check it
    # stops making, and then the script is written to the agent's defaults instead.
    "list_scripting_styles",
    # Reading a video somebody handed the app, and the paper edits already written from
    # one. All four measure or list; none of them cuts, writes an output or spends.
    # `editing_tools` in particular has to be free to call — it is the question asked
    # *before* a two-gigabyte upload, and a check the agent must ask permission for is a
    # check it stops making.
    "editing_tools", "read_video", "edit_plans",
    # Which engine will actually draw the motion scenes, per channel. Reading it is how
    # the agent can answer "why does this still look like ffmpeg" without changing
    # anything.
    "render_backends",
    # Reading the operator's own instruction documents. See skills_tools.py for why
    # they are read-only and why their descriptions are as long as they are.
    *skills_tools.READ_ONLY,
)
_WRITES = ("create_channel", "update_channel", "start_run", "apply_style",
           "blend_styles", "cancel_run", "sync_voice_artists",
           # Each of these produces a file that can be produced again from the same
           # input, and none of them spends credits or touches a run.
           "plan_edit", "cut_subject", "set_motion_backend", "learn_style",
           # Executing a plan the operator has *already* approved. It is here rather than
           # behind the gate because it cannot get past one: it refuses any plan that is
           # not approved, so the only thing the agent can do with it is carry out a
           # decision that was already taken. Keeping it out would mean an operator
           # approving an edit in the chat and then being sent somewhere else to receive
           # the file, which is the shape of gap this whole direction exists to close.
           "cut_plan")

# `decide_gate` is intentionally absent: approving a gate is the moment the run is
# allowed to spend on the stage behind it, and that is the user's call, not a step
# the agent gets to take because it seemed reasonable.
#
# `approve_edit` is absent for the same reason and it is the same gate in a different
# place. A paper edit fixes every expensive decision that follows it, so accepting one
# is the operator agreeing to the edit — an agent that approves its own plan has turned
# the one cheap place to disagree with the machine into a formality.
ALLOWED = [f"mcp__{SERVER_NAME}__{name}" for name in (*_READ_ONLY, *_WRITES)]

ALL_TOOLS = [*_READ_ONLY, *_WRITES, "decide_gate", "approve_edit"]


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
          "are touched. voice_vendor picks who narrates: 'elevenlabs' spends the "
          "character allowance included in that subscription, 'minimax-voice' is billed "
          "per character against the MiniMax API balance, and empty lets the default "
          "routing decide. Say which one is being spent before changing it.",
          {"channel": str, "name": str, "niche": str, "language": str,
           "voice_id": str, "voice_vendor": str, "aspect_ratio": str,
           "target_duration_seconds": int})
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
          "is. No API key needed — it reads the public page when there is no key, and "
          "marks any video whose publish date had to be guessed.",
          {"url": str, "limit": int})
    async def research_channel(args):
        return _text(studio.research_channel(args.get("url") or "",
                                             limit=int(args.get("limit") or 50)))

    @tool("score_videos",
          "Score statistics the user pasted — a table or a JSON array — into ranked "
          "outliers. Use this when the numbers came from somewhere else, or when "
          "research_channel could not read the channel.",
          {"text": str})
    async def score_videos(args):
        return _text(studio.score_videos(args.get("text") or ""))

    # ---------------------------------------------------------------------- voice

    @tool("cast_voice",
          "Shortlist narration voices against a described target — pitch (low/mid/"
          "high), pace (slow/measured/brisk), energy, accent. Returns each candidate "
          "with the reasons it scored and the caveats. Read-only: picking one is the "
          "user's call, applied with update_channel.",
          {"pitch": str, "pace": str, "energy": str, "accent": str, "limit": int})
    async def cast_voice(args):
        return _text(studio.cast_voice(
            pitch=args.get("pitch") or "", pace=args.get("pace") or "",
            energy=args.get("energy") or "", accent=args.get("accent") or "",
            limit=int(args.get("limit") or 3)))

    @tool("voice_catalogue",
          "Which voices are known, from which vendors, and whether each was measured "
          "from the account's own preview clips or assumed from the offline fallback "
          "list.", {})
    async def voice_catalogue(args):
        return _text(studio.voice_catalogue())

    @tool("voice_artists",
          "Epidemic Sound's voice artists for narration: who they are, where they are "
          "from, the vendor's description of each, and which languages each one reads. "
          "Read-only and free. Says what to do instead if Epidemic Sound is not "
          "connected.",
          {"limit": int})
    async def voice_artists(args):
        return _text(await studio.voice_artists(limit=int(args.get("limit") or 20)))

    @tool("sync_voice_artists",
          "Read Epidemic Sound's voice artists and measure the pitch of each one's "
          "preview clip, so cast_voice can rank them on the same measured scale as the "
          "ElevenLabs voices. Writes its own catalogue file and leaves the ElevenLabs "
          "one alone. Spends no credits.",
          {"measure": bool, "limit": int})
    async def sync_voice_artists(args):
        return _text(await studio.sync_voice_artists(
            measure=bool(args.get("measure", True)),
            limit=int(args.get("limit") or 60)))

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

    @tool("list_scripting_styles",
          "Which SCRIPTING methods exist and which channel writes to each: the built-in "
          "house method, plus any folders of the operator's own documents, with the "
          "count of documents read and any that failed to load. This is how a script is "
          "STRUCTURED — payoff schedule, curiosity loops, beat joins, banned phrases — "
          "and it is a different thing from list_styles, which is how a video is CUT. "
          "Read-only. Call it before writing or rewriting a script so you follow the "
          "method the channel is set to rather than your own defaults, and before "
          "changing it with update_channel(scripting_style=...). Say which method you "
          "followed.", {})
    async def list_scripting_styles(args):
        return _text(studio.list_scripting_styles())

    @tool("blend_styles",
          "Mix two styles into a new one. Weight 0 keeps the first, 1 takes the "
          "second. Numbers interpolate; transitions and caption position switch at "
          "the halfway point because there is nothing between a cut and a dissolve.",
          {"first": str, "second": str, "weight": float, "name": str})
    async def blend_styles(args):
        return _text(studio.blend_styles(
            args.get("first") or "", args.get("second") or "",
            weight=float(args.get("weight") or 0.5), name=args.get("name") or ""))

    @tool("learn_style",
          "Learn an editing style from a creator's videos: measure cut rhythm, grade, "
          "captions and motion out of the pixels and save it under a name, so it can "
          "be applied to a channel. References are attached video files or links — "
          "give several by the same creator rather than one, because a style is what "
          "survives across their work. Slow: it decodes each video. Spends no credits "
          "and calls no provider. Report the departures the upgrade pass made, because "
          "those are where the result stops describing the reference.",
          {"references": str, "name": str, "upgrade": bool, "max_seconds": int})
    async def learn_style(args):
        import asyncio

        # Off the loop. It decodes video for minutes, and on the event loop that stalls
        # every other request in the process — including the chat the operator is
        # watching while it runs.
        return _text(await asyncio.to_thread(
            studio.learn_style, args.get("references") or "",
            name=args.get("name") or "",
            upgrade=bool(args.get("upgrade", True)),
            max_seconds=int(args.get("max_seconds") or 0)))

    # ------------------------------------------------------------ render backend

    @tool("render_backends",
          "Which engine draws motion graphics: ffmpeg (always present) or remotion "
          "(real layout, needs the motion toolset). Reports which are installed here, "
          "what each channel is set to, and what will ACTUALLY run — an unavailable "
          "backend downgrades to ffmpeg at render time, so the stored setting and the "
          "finished video can disagree. Read-only.", {})
    async def render_backends(args):
        return _text(studio.render_backends())

    @tool("set_motion_backend",
          "Choose the motion renderer for one channel: 'ffmpeg' or 'remotion'. Stored "
          "on the channel, so every future run uses it. Say whether it will actually be "
          "used — if the motion toolset is not installed the answer says so and renders "
          "fall back to ffmpeg until it is.",
          {"channel": str, "backend": str})
    async def set_motion_backend(args):
        return _text(studio.set_motion_backend(args.get("channel") or "",
                                               args.get("backend") or ""))

    # --------------------------------------------------------- supplied footage

    @tool("editing_tools",
          "What this machine can measure in a video somebody hands the app — shot "
          "boundaries, silence, a word-timed transcript, subject cutouts — and what "
          "would fix anything missing. Free and instant. Call it BEFORE asking for a "
          "large upload, so a missing toolset is found now rather than twenty seconds "
          "after a two-gigabyte file finishes copying.", {})
    async def editing_tools(args):
        return _text(studio.editing_tools())

    @tool("read_video",
          "Measure a supplied video: duration, frame size, frame rate, its existing "
          "shot boundaries and cut rate, every silent stretch, and a word-timed "
          "transcript. Measures only — it decides nothing and cuts nothing. Readings "
          "that could not be taken come back named in `missing` rather than guessed "
          "at. The path is one the chat's attachment upload returned.",
          {"path": str, "want_transcript": bool, "want_shots": bool, "limit": int})
    async def read_video(args):
        import asyncio

        return _text(await asyncio.to_thread(
            studio.read_video, args.get("path") or "",
            want_transcript=bool(args.get("want_transcript", True)),
            want_shots=bool(args.get("want_shots", True)),
            limit=int(args.get("limit") or 12)))

    @tool("plan_edit",
          "Write the paper edit for a supplied video: what comes out, where, and why, "
          "grouped so it can be read in one pass. NOTHING IS CUT — this produces a plan "
          "the operator reads and approves first, which is the whole point of having "
          "one. Show them the markdown it returns and ask; do not approve it yourself.",
          {"path": str, "drop_fillers": bool})
    async def plan_edit(args):
        import asyncio

        return _text(await asyncio.to_thread(
            studio.plan_edit, args.get("path") or "",
            drop_fillers=bool(args.get("drop_fillers", True))))

    @tool("edit_plans",
          "The paper edits already written, or one of them in full with its markdown "
          "and every decision. Read-only. Use it to bring back a plan from earlier in "
          "the conversation instead of measuring the video again.",
          {"plan_id": str, "limit": int})
    async def edit_plans(args):
        return _text(studio.edit_plans(args.get("plan_id") or "",
                                       limit=int(args.get("limit") or 20)))

    @tool("approve_edit",
          "Accept or reject a paper edit. ONLY call this when the user has told you to "
          "in this conversation — approving is them agreeing to the edit, and every "
          "expensive decision downstream is fixed by it. Approving records the decision "
          "and releases the cut; cut_plan is what then makes the file.",
          {"plan_id": str, "approve": bool, "note": str})
    async def approve_edit(args):
        return _text(studio.approve_edit(args.get("plan_id") or "",
                                         approve=bool(args.get("approve", True)),
                                         note=args.get("note") or ""))

    @tool("cut_plan",
          "Cut the video an APPROVED paper edit describes, and report what came out: "
          "how long it is, how much was removed, and where the file is. Refuses any plan "
          "the operator has not approved — approving is theirs, executing is this. Slow: "
          "it re-encodes, because cutting on keyframes lands on the wrong frame. Spends "
          "no credits and calls no provider. Report the finished length against the "
          "length the plan predicted, because a difference there is the one thing that "
          "says the file is not the edit that was agreed to.",
          {"plan_id": str, "fps": int})
    async def cut_plan(args):
        import asyncio

        # Off the loop. It is minutes of ffmpeg on a long source, and on the event loop
        # that stalls every other request in the process — including the chat the
        # operator is watching while it runs.
        return _text(await asyncio.to_thread(
            studio.cut_plan, args.get("plan_id") or "",
            fps=int(args.get("fps") or 0)))

    @tool("cut_subject",
          "Lift the subject of a still onto its own layer with an alpha channel, and "
          "optionally set a title BEHIND it so the subject's shoulder passes in front "
          "of the words. A cutout with a visible fringe is refused and reported rather "
          "than used — say so and fall back to the plain still, because a fringed matte "
          "reads as cheaper than no matte at all.",
          {"image": str, "text": str, "background": str, "out": str})
    async def cut_subject(args):
        import asyncio

        return _text(await asyncio.to_thread(
            studio.cut_subject, args.get("image") or "",
            text=args.get("text") or "",
            background=args.get("background") or None,
            out=args.get("out") or ""))

    # Returned as a list as well as a server, because a backend that is not MCP needs the
    # same operations as function schemas. Introspecting the assembled server for them was
    # the first attempt and it is a dead end: `create_sdk_mcp_server` hands back an opaque
    # MCP `Server` whose tool list is only reachable through a request handler that needs a
    # live request context. The list is right here, so it is exposed here.
    built = [studio_status, list_channels, study_youtube_channel, create_channel,
             update_channel, list_runs, start_run, run_status, decide_gate,
             cancel_run, preview_run, run_files, research_channel, score_videos,
             cast_voice, voice_catalogue, voice_artists, sync_voice_artists,
             list_styles, apply_style, blend_styles, list_scripting_styles,
             learn_style, render_backends, set_motion_backend,
             editing_tools, read_video, plan_edit, edit_plans, approve_edit,
             cut_plan, cut_subject,
             *skills_tools.build(studio)]
    server = create_sdk_mcp_server(name=SERVER_NAME, version="1.0.0", tools=built)
    _BUILT[id(server)] = built
    return server


# Keyed by the server it was built for, so two studios in one process cannot hand each
# other's tools out. Small and bounded — one entry per server, and a server lives as long
# as the conversation it serves.
_BUILT: dict[int, list] = {}


def built_tools(server) -> list:
    """The tool objects that went into `server`, for a non-MCP backend to describe.

    Empty for a server this module did not build, which is the honest answer rather than a
    guess: a caller that gets nothing shows a model with no tools, and a caller that gets
    somebody else's shows a model the wrong ones.
    """
    return list(_BUILT.get(id(server), []))
