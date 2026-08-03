"""Claude, running inside the app, holding the app's operations as tools.

## The shape

You talk to the agent; the agent does the work. It is not an assistant sitting beside
a dashboard offering advice about the buttons — the buttons and the agent call the
same functions in `studio.py`, and the agent can call them itself.

## Auth is a subscription, not an API key

See `auth.py`. Nothing here takes a key; the Claude Code CLI is driven with your own
`claude login`. `check()` runs before a single token is spent so "is Claude
connected?" has an answer other than watching something fail.

## Conversations persist

Each thread keeps the CLI's own session id and resumes it on the next turn, so the
agent remembers the channel you were setting up three messages ago. A fresh `query`
per message — which is the obvious implementation — produces an agent with amnesia
that re-reads the same state every turn and still contradicts itself.

## Why it ships asking before it edits

`permission_mode` defaults to `'default'`: every file edit prompts. An agent with
unattended write access to the code that renders your videos is not a convenience
worth defaulting into. The failure mode is not a crash — it is a silently changed
threshold, discovered weeks later in a delivered file.

Tool calls are different from file edits. The studio tools are pre-allowed because
each is read-only or re-runnable; `decide_gate` is excluded, because approving a gate
is what lets the next stage spend.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path

from . import auth, connectors, tools
from .studio import Studio

log = logging.getLogger("forgecast.agent")

APP_ROOT = Path(__file__).resolve().parents[2]

# What the picker offers. Availability follows your plan rather than this list — a
# plan limit is reported by the CLI, not predicted here.
MODELS = [
    {"id": "claude-sonnet-5", "label": "Sonnet 5",
     "note": "The default. Fast, and cheap enough on a subscription to keep going."},
    {"id": "claude-opus-5", "label": "Opus 5",
     "note": "Strongest. For the decisions you would not want to review twice."},
    {"id": "claude-fable-5", "label": "Fable 5",
     "note": "The writing model. Scripts, titles and hooks — not code."},
    {"id": "claude-haiku-4-5-20251001", "label": "Haiku 4.5",
     "note": "Quickest. Reading and answering, not producing."},
]
DEFAULT_MODEL = "claude-sonnet-5"


def system_prompt(studio: Studio) -> str:
    """Written against the failures this app actually has.

    Every paragraph below exists because of something that goes wrong without it —
    a run approved on the agent's own judgement, a claim about a video nobody
    measured, a forty-minute render started from a script that was wrong in its first
    sentence.
    """
    return (
        "You ARE Forgecast — a studio that builds and runs faceless YouTube channels, "
        "running locally on this machine. You are not an assistant beside the app: the "
        "app's operations are your tools and you do the work with them.\n\n"

        "Open by calling studio_status. Say what this install actually is — live or "
        "mock, what is connected, what is waiting on a decision — before offering to "
        "do anything. A greeting that could have been written before seeing the "
        "machine is worth nothing.\n\n"

        "SETTING UP A CHANNEL STARTS WITH A LINK.\n"
        "When someone wants a channel like an existing one, ask for the YouTube link "
        "and call study_youtube_channel. It measures median upload length, subscriber "
        "count, recent titles and which uploads beat their own cohort. Show what you "
        "measured, then create the channel from it. Do not present a form of "
        "questions whose answers are sitting in a channel you can read.\n"
        "The one thing you cannot measure is the niche in their words — ask for that "
        "and nothing else.\n\n"

        "RESEARCH IS MEASUREMENT, NOT OPINION.\n"
        "research_channel and score_videos compare a video against its own cohort. "
        "Quote the multiple and say whether it is reliable — a video too young to "
        "score, or one whose cohort is too small, is marked as such and you must "
        "repeat that rather than round it up into a recommendation. Never invent a "
        "view count or a multiple. If there is no API key, say so and offer to score "
        "numbers they paste.\n"
        "Writing the titles and angles IS your job — do it yourself in the chat, from "
        "the measured numbers. There is no tool for it because you are the tool.\n\n"

        "THE GATE IS THEIRS, NOT YOURS.\n"
        "Never call decide_gate unless they have told you to approve or reject in "
        "this conversation. A run pauses at a gate because approving it is what lets "
        "the next stage spend real credits and real GPU time. Present what the gate "
        "is holding — the brief, the script, the shot list — say what you think and "
        "why, and then stop and wait. 'It looked fine so I approved it' is the single "
        "worst thing you can do in this app.\n\n"

        "PREVIEW BEFORE RENDER.\n"
        "preview_run is free and shows the edit as a timeline. A render is minutes of "
        "machine time and the difference between them is the whole reason the preview "
        "exists. When a preview reports missing stages, name them — a partial preview "
        "presented as the finished video is a lie by omission.\n\n"

        "SAY WHAT YOU DID AND WHAT THE NUMBERS WERE.\n"
        "'Started run 14 on Ocean Freight, 62 credits held, waiting at the brief "
        "gate' is useful. 'Done!' is not. Report failures with the actual error, not "
        "a summary of it.\n\n"

        f"{_connector_note()}"

        "You can also read and edit this app's own code — it is in the folder you are "
        "running from. Never touch anything under storage/: those are rendered "
        "videos, voice takes and the database, they are not in git, and they cannot "
        "be recovered."
    )


def _connector_note() -> str:
    live = connectors.Store.load()
    connected = [c.spec.label for c in live.connections.values() if c.enabled and c.url]
    if not connected:
        return ("No outside connectors are wired up yet. If someone asks for niche "
                "research you cannot do with the tools you have, point them at "
                "Settings → Connectors — NexLev is the one that adds niche finding "
                "and faceless-channel outliers.\n\n")
    return ("Connected services, whose tools you also hold: "
            + ", ".join(connected) + ". Prefer them over guessing, and name which "
            "one an answer came from.\n\n")


def build_options(*, studio: Studio, permission_mode: str = "default",
                  model: str | None = None, resume: str | None = None,
                  allow_web: bool = True, budget_usd: float | None = None):
    """Confine the agent to this app, and hand it the studio.

    cwd plus a sandbox, not cwd alone: cwd says where it starts, the sandbox is what
    stops a shell command wandering out. Network stays on because research is half
    the job, but it is limited to managed domains rather than the whole internet.
    """
    from claude_agent_sdk import ClaudeAgentOptions

    servers: dict = {tools.SERVER_NAME: tools.build_server(studio)}
    servers.update(connectors.active_servers())

    extra: dict = {}
    if model:
        # Only when set. An empty model= would override the CLI's own default with
        # nothing, which is worse than not asking.
        extra["model"] = model
    if resume:
        extra["resume"] = resume
    if budget_usd:
        extra["max_budget_usd"] = budget_usd

    return ClaudeAgentOptions(
        cwd=str(APP_ROOT),
        add_dirs=[],                                   # nothing outside the app root
        mcp_servers=servers,
        allowed_tools=list(tools.ALLOWED),
        permission_mode=permission_mode,
        sandbox={
            "enabled": True,
            # Sandboxed bash may run without a second prompt. The sandbox is the
            # boundary; prompting twice for the same guarantee trains people to
            # click through prompts.
            "autoAllowBashIfSandboxed": True,
            "allowUnsandboxedCommands": False,
            "network": {"allowManagedDomainsOnly": not allow_web,
                        "allowLocalBinding": True},
        },
        disallowed_tools=[] if allow_web else ["WebFetch", "WebSearch"],
        system_prompt=system_prompt(studio),
        **extra,
    )


async def run(prompt: str, *, studio: Studio, resume: str | None = None,
              **kwargs) -> AsyncIterator[dict]:
    """One turn, as a stream of events.

    Yields `{"type": "text"|"tool"|"result"|"error", ...}`. Streamed rather than
    returned at the end because a turn can start a render or read fifty videos, and a
    UI that shows nothing until it finishes is indistinguishable from one that hung.

    The `result` event carries the session id. The caller stores it and passes it back
    as `resume` next turn — that is what makes this a conversation.
    """
    from claude_agent_sdk import (AssistantMessage, CLINotFoundError, ResultMessage,
                                  TextBlock, ThinkingBlock, ToolUseBlock, query)

    status = auth.check()
    if not status.ok:
        yield {"type": "error", "text": status.detail, "auth": status.as_dict()}
        return

    options = build_options(studio=studio, resume=resume, **kwargs)
    session_id = resume or ""
    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                session_id = getattr(message, "session_id", "") or session_id
                for block in message.content:
                    if isinstance(block, TextBlock):
                        yield {"type": "text", "text": block.text}
                    elif isinstance(block, ThinkingBlock):
                        yield {"type": "thinking", "text": block.thinking}
                    elif isinstance(block, ToolUseBlock):
                        # Named so the transcript shows the work rather than only the
                        # answer: "reading that channel" while it happens.
                        yield {"type": "tool",
                               "name": getattr(block, "name", "tool"),
                               "input": getattr(block, "input", {}) or {}}
            elif isinstance(message, ResultMessage):
                session_id = message.session_id or session_id
                yield {"type": "result", "session_id": session_id,
                       "turns": message.num_turns,
                       "cost_usd": message.total_cost_usd,
                       "is_error": bool(message.is_error)}
    except CLINotFoundError:
        yield {"type": "error",
               "text": f"Claude Code CLI not found. Install it: {auth.INSTALL_HINT}"}
    except Exception as exc:                                      # pragma: no cover
        log.exception("agent turn failed")
        yield {"type": "error", "text": f"{type(exc).__name__}: {exc}"}
    finally:
        if session_id and session_id != resume:
            yield {"type": "session", "session_id": session_id}
