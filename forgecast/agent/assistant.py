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

from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

from . import auth, connectors, setup_notice, tools
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
        "view count or a multiple. Without an API key the numbers are read off the "
        "public page and the publish dates are reconstructed from labels like "
        "\"2 months ago\" — where the tool says a multiple could be anywhere in a "
        "range, give the range, not the midpoint. If a channel cannot be read at all, "
        "say why and offer to score numbers they paste.\n"
        "Writing the titles and angles IS your job — do it yourself in the chat, from "
        "the measured numbers. There is no tool for it because you are the tool.\n\n"

        "DO NOT REACH FOR A SHELL. USE YOUR OWN TOOLS.\n"
        "Many machines this runs on refuse unsandboxed shell commands by policy — the "
        "refusal names sandboxing and looks like a machine fault, and it is not one. "
        "Every attempt costs a minute and returns nothing. Use Glob to find files, Grep "
        "to search them and Read to open them; they are not affected. Never shell out to "
        "install anything: this app installs its own tooling, and if something is "
        "genuinely missing, say which Setup row installs it and stop. If a shell command "
        "is refused, do not retry it in another form — the second attempt is refused for "
        "the same reason as the first.\n\n"

        "MEASURE THE REFERENCE BEFORE YOU DECIDE ANYTHING ABOUT IT.\n"
        "When the operator names a channel to model on, pass it as `model_on` to "
        "create_channel. That watches their strongest videos and measures how they "
        "actually write and cut — words a second, where the opening beat ends, how "
        "often the picture changes. Do it as part of setting the channel up, not as an "
        "extra you offer afterwards. It takes minutes; say so and do it.\n"
        "Never choose a format, a method or a skill by guessing the genre. A channel "
        "that looks like a documentary explainer can be an anthology of self-contained "
        "sixty-second segments with no throughline and no cold open at all, and a skill "
        "chosen from the label rather than the measurement will be confidently wrong "
        "about the one thing it was loaded to get right. If the structure has not been "
        "measured, measure it — watch a video, read the transcript — and only then say "
        "what the format is. When the measurement contradicts the genre, the "
        "measurement wins and you say plainly that it did.\n"
        "Learn the pattern; do not lock to it. What was measured is the creator's "
        "template, and the topic in front of you still decides what fills it.\n\n"

        "CHECK THE SKILLS BEFORE YOU WRITE ANYTHING.\n"
        "list_skills is the operator's own craft, written down: each document says the "
        "situation it applies to. Read those lines before writing or rewriting a "
        "script, a hook, a title, a caption or a shot list, load the ones that cover "
        "the task with load_skill, and say which you followed. A skill outranks your "
        "own habits — it exists because someone got tired of retyping it into this "
        "chat every week, and an opening written from instinct while a document about "
        "openings sat unread is work that has to be done a second time. If none "
        "applies, say so once and write it yourself.\n\n"

        "A CHANNEL IS WRITTEN TO A METHOD, AND IT IS NOT YOURS EITHER.\n"
        "list_scripting_styles says which scripting method each channel is set to — the "
        "built-in one, or a folder of the operator's own documents. Read it before "
        "writing or rewriting a script for a channel and follow what it names, because "
        "the pipeline already injects that method into every brief and every script and "
        "a chat draft written to your own defaults is a draft that contradicts the run. "
        "Say which method you followed. If it reports a style that could not be loaded, "
        "tell them which one and that scripts are falling back to the house method — "
        "that is a missing folder, not a change of mind. This is not the same thing as "
        "list_styles, which is how a video is cut.\n\n"

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


async def connector_permission(tool_name: str, tool_input: dict, context):
    """Answer the SDK's permission question for a connector's tool.

    Three outcomes, and each is a decision the operator can see and change on
    Settings → Connectors:

    * **allow** — the default for a service they went and connected. Asking every time
      is what the app was effectively doing by granting nothing, and the result was not
      a careful operator approving each call.
    * **deny** — refused with the reason, so the agent can say which connector is off
      and carry on rather than retrying a call that will never be permitted.
    * **ask** — nothing here can ask yet, so it is refused *and says so*: it names the
      connector and points at the page that grants it. A refusal that explains itself is
      recoverable in one click; a silent cancellation is the bug this replaced.

    Anything that is not a connector tool falls through to `permission_mode`, which is
    the CLI's own model for file edits and shell commands and is not this app's to
    second-guess.
    """
    decision, why = connectors.Store.load().decide(tool_name)
    if decision == "allow":
        return PermissionResultAllow()
    bare = str(tool_name or "").split("__")[-1]
    if decision == "ask":
        return PermissionResultDeny(
            message=(f"{bare} needs permission and this app cannot prompt for one "
                     f"mid-turn. Grant it on Settings → Connectors ({why}), then ask "
                     f"again. Say that to the operator rather than retrying."))
    return PermissionResultDeny(
        message=f"{bare} is not permitted: {why}. Tell the operator rather than retrying.")


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
        # Every server above hands the agent tools, and `allowed_tools` names only this
        # app's own. Without this callback the rest need a permission prompt, and this
        # app has no surface on which one can be shown or answered — so the CLI recorded
        # them as `user cancelled MCP tool call` and the agent lost every connector it
        # had. Nobody cancelled anything; there was nobody to ask.
        can_use_tool=connector_permission,
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


# A tool result long enough to be a file is not something to paste into a chat
# bubble. The card shows the head of it and says how much was cut, which is honest
# in a way that silently truncating is not.
MAX_RESULT_CHARS = 4000


def _result_text(block) -> str:
    """A tool result as text, whatever shape the block arrived in.

    Content is a string for simple returns and a list of content parts for
    everything else, and image parts have no text at all. Flattening here keeps that
    knowledge in one place instead of in the browser.
    """
    content = getattr(block, "content", "")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text") or f"[{item.get('type', 'content')}]")
            else:
                parts.append(str(item))
        text = "\n".join(parts)
    else:
        text = str(content or "")

    if len(text) > MAX_RESULT_CHARS:
        cut = len(text) - MAX_RESULT_CHARS
        return text[:MAX_RESULT_CHARS] + f"\n\n… {cut:,} more characters"
    return text


async def _streamed(prompt: str) -> AsyncIterator[dict]:
    """One turn's prompt as the stream the SDK requires.

    `build_options` sets `can_use_tool`, and the SDK refuses that callback alongside a
    plain string prompt: a permission callback only means anything if input is still
    open when the agent asks, so streaming mode is a precondition rather than a
    preference. Passing a string raised `ValueError: can_use_tool callback requires
    streaming mode` on *every* turn — the connector permission work made the callback
    unconditional, and nothing here was changed to match, so the whole agent stopped
    answering and the error surfaced in the chat as though the model had produced it.

    One message, then the generator returns, which is what closes the input stream and
    lets the turn end. A generator that stayed open would leave the CLI waiting for a
    second prompt that is never coming, and the turn would hang instead of failing —
    which is the worse of the two, because a hang has no error to read.

    `session_id` is the SDK's own placeholder for the opening message of a turn.
    Resumption is carried by `options.resume`, not by this field.
    """
    yield {
        "type": "user",
        "message": {"role": "user", "content": prompt},
        "parent_tool_use_id": None,
        "session_id": "default",
    }


async def run(prompt: str, *, studio: Studio, resume: str | None = None,
              **kwargs) -> AsyncIterator[dict]:
    """One turn, as a stream of events.

    Yields `{"type": "text"|"tool"|"result"|"setup"|"error", ...}`. Streamed rather
    than returned at the end because a turn can start a render or read fifty videos,
    and a UI that shows nothing until it finishes is indistinguishable from one that
    hung.

    `setup` is the only one that is not part of a turn — see `setup_notice`. It means
    the backend is not installed or not signed in, so nothing ran and nothing was
    spent, and it is rendered as an install to finish rather than as a reply.

    The `result` event carries the session id. The caller stores it and passes it back
    as `resume` next turn — that is what makes this a conversation.
    """
    from claude_agent_sdk import (
        AssistantMessage,
        CLINotFoundError,
        ResultMessage,
        SystemMessage,
        TextBlock,
        ThinkingBlock,
        ToolResultBlock,
        ToolUseBlock,
        UserMessage,
        query,
    )

    status = auth.check()
    if not status.ok:
        # A setup notice, not an error: nothing failed, because nothing started. Sent
        # as an error event it landed in the assistant's bubble, and "not signed in"
        # read as the agent answering strangely rather than as an install to finish.
        yield setup_notice.notice(status)
        return

    options = build_options(studio=studio, resume=resume, **kwargs)
    session_id = resume or ""
    try:
        async for message in query(prompt=_streamed(prompt), options=options):
            if isinstance(message, SystemMessage):
                # The opening message names every tool the agent actually holds, fully
                # namespaced. It is the only way to see inside a connector authorised by
                # browser sign-in — that grant lives in the CLI, this app has no token
                # for it, and cannot ask the server itself. Recorded so Settings can
                # show what was granted rather than an empty list.
                listed = (getattr(message, "data", None) or {}).get("tools")
                if isinstance(listed, list):
                    connectors.learn_session_tools([str(name) for name in listed])
            if isinstance(message, AssistantMessage):
                fresh = getattr(message, "session_id", "") or ""
                if fresh and fresh != session_id:
                    session_id = fresh
                    # Emitted the moment it is known rather than at the end of the
                    # turn. The caller writes it down here, so a turn that never
                    # finishes still leaves the thread resumable — which is the
                    # difference between a chat with a memory and one without.
                    yield {"type": "session", "session_id": session_id}
                for block in message.content:
                    if isinstance(block, TextBlock):
                        yield {"type": "text", "text": block.text}
                    elif isinstance(block, ThinkingBlock):
                        yield {"type": "thinking", "text": block.thinking}
                    elif isinstance(block, ToolUseBlock):
                        # Named so the transcript shows the work rather than only the
                        # answer: "reading that channel" while it happens.
                        yield {"type": "tool",
                               "id": getattr(block, "id", ""),
                               "name": getattr(block, "name", "tool"),
                               "input": getattr(block, "input", {}) or {}}
            elif isinstance(message, UserMessage):
                # What each tool actually returned. Sent so the transcript can show
                # the measurement rather than only the sentence the agent wrote about
                # it — the numbers are the part worth scrolling back to, and a claim
                # you cannot check against its source is a claim you have to take on
                # trust.
                for block in getattr(message, "content", None) or []:
                    if isinstance(block, ToolResultBlock):
                        yield {"type": "tool_result",
                               "id": getattr(block, "tool_use_id", ""),
                               "is_error": bool(getattr(block, "is_error", False)),
                               "text": _result_text(block)}
            elif isinstance(message, ResultMessage):
                session_id = message.session_id or session_id
                yield {"type": "result", "session_id": session_id,
                       "turns": message.num_turns,
                       "cost_usd": message.total_cost_usd,
                       "is_error": bool(message.is_error)}
    except CLINotFoundError:
        yield {"type": "error",
               "text": f"Claude Code CLI not found. Install it: {auth.INSTALL_HINT}"}
    except Exception as exc:
        log.exception("agent turn failed")
        yield {"type": "error", "text": f"{type(exc).__name__}: {exc}",
               "resume_failed": _looks_like_a_dead_session(exc, resume)}
    # Deliberately no `finally` that yields. Closing an async generator raises
    # GeneratorExit at the paused `yield`, and yielding again from the `finally`
    # while unwinding raises "async generator ignored GeneratorExit" — which aborts
    # teardown of the CLI subprocess. The session id is emitted above, as soon as it
    # is known, which is both earlier and safe.


# Substrings the CLI uses when the session it was asked to resume is gone. Matched on
# text because the SDK raises a generic ProcessError for it — there is no typed error
# to catch, and guessing wrong here means either a bricked thread or a silent retry
# that hides a real failure.
_DEAD_SESSION_SIGNS = (
    "no conversation found", "session not found", "no such session",
    "could not resume", "invalid session", "--resume",
)


def _looks_like_a_dead_session(exc: BaseException, resume: str | None) -> bool:
    """Did this turn fail *because* the session it tried to resume no longer exists?

    It happens for ordinary reasons: the CLI's session store was cleared, the app was
    copied to another machine, or storage was reset. Without this the thread is
    bricked — every future message resumes the same dead id and fails the same way,
    and the only escape is starting a new chat and losing the history.
    """
    if not resume:
        return False
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(sign in text for sign in _DEAD_SESSION_SIGNS)
