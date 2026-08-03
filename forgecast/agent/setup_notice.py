"""A backend saying "I am not installed" without pretending to be a chat reply.

## The failure this removes

Every backend checks its own sign-in before spending anything, and it was right to.
What was wrong was the shape of the refusal: it came back as `{"type": "error"}`, which
`chat.js` renders by putting the text into the assistant's bubble. So typing *hi* on a
machine with no Codex CLI produced a paragraph about npm, in the agent's own voice, in
the place an answer goes. It was reported as the agent being broken — which is the
correct reading of what was on screen. Nothing had failed. Nothing had even started.

An install problem is not a turn. It has no session, costs nothing, and is fixed by
pressing a button rather than by rephrasing the question. So it gets its own event type
and its own card, and the transcript stays what the agent actually said.

## What a backend fills in, and what it does not

`notice()` takes the status object the backend already has — every one of the three
reports the same field names, by design (`codex_auth.CodexStatus`) — and returns the
event. It deliberately does **not** name the vendor: the module that knows a turn was
routed to ChatGPT is the one that routed it, so `routes_agent.chat()` stamps `engine`
and `engine_label` on the way past. A literal "ChatGPT" in three backend modules is
three strings to keep in step with `engines.ENGINES`, and the one that drifts is the one
nobody reads until it is wrong on screen.

`text` carries the same sentence as `detail`. It is there for any consumer that only
knows how to render `event.text` — the smoke script, a future client, a log line — so an
unrecognised event degrades to a readable sentence rather than to an empty box.
"""

from __future__ import annotations

from typing import Any

TYPE = "setup"


def notice(status: Any) -> dict:
    """The one event a backend emits instead of running, as a plain dict.

    Duck-typed on purpose. `AuthStatus`, `CodexStatus` and `MiniMaxStatus` are three
    separate dataclasses that agreed to share field names; importing all three here to
    write a union type would make this module depend on every backend it exists to keep
    apart.
    """
    detail = str(getattr(status, "detail", "") or "")
    return {
        "type": TYPE,
        "headline": str(getattr(status, "headline", "") or "This agent is not ready"),
        "detail": detail,
        "fixes": [str(line) for line in (getattr(status, "fixes", None) or [])],
        # Whether pressing Sign in can finish the job. A backend whose CLI is missing
        # has nothing to open a browser flow for, and offering the button anyway sends
        # the operator to a terminal printing "command not found".
        "can_login": bool(getattr(status, "can_login", False)),
        "text": detail,
    }
