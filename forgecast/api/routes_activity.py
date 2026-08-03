"""The MCP activity log: every tool call the agent has made, in one place.

## Why a page for this at all

The chat already shows tool cards inline, but only for the thread you are looking at.
That answers "what did it just do" and cannot answer the question that decides whether
the agent is worth its context: *what does it actually spend its calls on*. Nine reads
of the same channel and one `start_run` is a different agent from the reverse, and you
cannot see the difference one conversation at a time.

So this page is deliberately cross-thread and deliberately blunt: a total, a breakdown
by tool, and the calls themselves newest first with their arguments — plus the failures
on their own, because a tool that errors every time is the thing you want to find in
one click rather than by scrolling.

## Why there is no table and no migration

`ChatMessage.tool_calls` already holds every call the agent made, written by the chat
turn as `{id, name, input, result, is_error}`. That JSON is the record; a second table
would be a copy of it that can disagree with the transcript, and disagreeing with the
transcript is the one thing an audit log may not do.

Aggregating it in Python is correct at this scale and it is worth being explicit about
why. Heavy use is on the order of a few thousand assistant turns a month for one
account; each carries a handful of calls and a few kilobytes of JSON, so the whole log
is a few megabytes to read and a loop of tens of thousands of dicts to tally — under
the time the browser spends on the response. Two things would force a real
`tool_calls` table with indexed `name`, `created_at` and `is_error` columns: wanting
aggregation the database has to do (calls per tool per day, across accounts, for
billing or a chart), or a single account's log growing past roughly the low hundreds of
thousands of calls, at which point reading every row on every page load — which is what
the totals and the breakdown require — becomes the cost of the page rather than a
rounding error on it.

Note what is *not* read: `ChatMessage.text`. Assistant prose is the largest column in
the row and none of it appears here, so the query names its columns instead of loading
whole ORM objects.
"""

from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import optional_user
from ..db import get_session
from ..models import ChatMessage, Conversation, User

router = APIRouter(include_in_schema=False)

# Enough that a normal day fits on one page, small enough that the page is still a
# page. The thing being prevented is the naive version: a month of use is thousands of
# calls, each carrying up to 4 KB of captured result, and rendering all of them is a
# document the browser is still parsing when you have given up on it.
PAGE_SIZE = 50

# Arguments are shown twice on purpose — a single line on the row, so a column of calls
# can be scanned, and in full inside the fold. The preview is cut short rather than
# wrapped because a row whose height depends on how verbose one call's input was
# destroys the scannability that is the point of the column.
ARGS_PREVIEW_CHARS = 120

# Results were already capped at 4 KB each when the turn was written down. Fifty of
# those is 200 KB of markup the browser parses whether or not anything is ever
# expanded, which is the same failure pagination exists to prevent, one level down.
RESULT_PREVIEW_CHARS = 1500


def _when(moment: datetime | None) -> str:
    """Minutes, not seconds. Nobody reads a log to the second, and the extra digits
    push the columns that carry meaning off the side of the row."""
    return moment.strftime("%Y-%m-%d %H:%M") if moment else "—"


def _preview(text: str, limit: int) -> tuple[str, int]:
    """The visible part and how much was hidden, so truncation can announce itself.

    Silently cutting a result reads as the whole thing — the same trap the chat's own
    tool cards avoid by printing the remaining character count.
    """
    if len(text) <= limit:
        return text, 0
    return text[:limit], len(text) - limit


def tool_calls_for(session: Session, user: User) -> list[dict]:
    """Every tool call in every one of this account's conversations, newest first.

    Scoped by joining through `Conversation`, which is where ownership lives —
    `ChatMessage` has no `user_id`, so filtering on the message alone would happily
    return another account's calls.
    """
    rows = session.execute(
        select(
            ChatMessage.id,
            ChatMessage.created_at,
            ChatMessage.tool_calls,
            Conversation.id,
            Conversation.title,
        )
        .join(Conversation, ChatMessage.conversation_id == Conversation.id)
        .where(Conversation.user_id == user.id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
    ).all()

    calls: list[dict] = []
    for _message_id, at, stored, conversation_id, title in rows:
        # Most rows contribute nothing: every user turn and every assistant turn that
        # only talked has an empty list here, and a row written by an older build may
        # have no list at all.
        if not stored:
            continue
        # Reversed within the message as well as between messages. A turn's calls are
        # stored in the order they ran, and a page that claims to be newest-first while
        # each group of five reads oldest-first is a page you cannot trust to answer
        # "what did it just do".
        for entry in reversed(list(stored)):
            if not isinstance(entry, dict):
                continue
            arguments = json.dumps(entry.get("input") or {}, ensure_ascii=False,
                                   sort_keys=True, default=str)
            result = str(entry.get("result") or "")
            result_shown, result_cut = _preview(result, RESULT_PREVIEW_CHARS)
            args_shown, args_cut = _preview(arguments, ARGS_PREVIEW_CHARS)
            calls.append({
                # A call the CLI reported without a name still happened, and dropping
                # it would make the total disagree with the transcript.
                "name": str(entry.get("name") or "").strip() or "(unnamed)",
                "conversation": title or "Untitled",
                "conversation_id": conversation_id,
                "at": _when(at),
                "failed": bool(entry.get("is_error")),
                "arguments": arguments,
                "args_preview": args_shown,
                "args_cut": args_cut,
                "result": result_shown,
                "result_cut": result_cut,
                "has_result": bool(result),
            })
    return calls


def tally(calls: list[dict]) -> list[dict]:
    """Calls per tool, busiest first — the answer to what the agent spends itself on.

    Share is carried alongside the count because a count on its own does not say
    whether 40 reads is most of the log or a corner of it, and that is the whole
    judgement this table exists to support.
    """
    counted: dict[str, dict] = {}
    for call in calls:
        row = counted.setdefault(call["name"],
                                 {"name": call["name"], "calls": 0, "failed": 0})
        row["calls"] += 1
        if call["failed"]:
            row["failed"] += 1

    total = len(calls) or 1
    for row in counted.values():
        row["share"] = round(100 * row["calls"] / total)
    return sorted(counted.values(), key=lambda row: (-row["calls"], row["name"]))


def _link(tool: str, failures_only: bool, page: int) -> str:
    """A URL that keeps the filters. Paging that silently drops the filter you were
    reading through is worse than no paging: page two looks like fresh evidence."""
    params: list[tuple[str, str]] = []
    if tool:
        params.append(("tool", tool))
    if failures_only:
        params.append(("failed", "1"))
    if page > 1:
        params.append(("page", str(page)))
    return "/activity" + (f"?{urlencode(params)}" if params else "")


@router.get("/activity", response_class=HTMLResponse)
def activity_page(
    request: Request,
    session: Session = Depends(get_session),
    tool: str = "",
    failed: str = "",
    page: int = 1,
) -> HTMLResponse:
    from .routes_web import TEMPLATES, shell

    user = optional_user(request, session)
    if user is None:
        return RedirectResponse("/login?next=/activity", 303)  # type: ignore[return-value]

    everything = tool_calls_for(session, user)
    failures_only = failed not in ("", "0", "false")

    # The breakdown and the headline totals are computed before filtering, on purpose.
    # A breakdown that reflects the current filter shows one row saying "100%", which
    # is not a breakdown, and the links in it would have nowhere left to go.
    breakdown = tally(everything)

    selected = tool.strip()
    matching = [
        call for call in everything
        if (not selected or call["name"] == selected)
        and (not failures_only or call["failed"])
    ]

    pages = max(1, -(-len(matching) // PAGE_SIZE))
    # Clamped rather than trusted: a bookmark from when the log was longer, or a hand
    # edited query string, would otherwise render an empty page that looks like the
    # calls were deleted.
    current = min(max(1, page), pages)
    window = matching[(current - 1) * PAGE_SIZE:current * PAGE_SIZE]

    return TEMPLATES.TemplateResponse(
        request,
        "activity.html",
        {
            **shell(session, user, "activity"),
            "calls": window,
            "total": len(everything),
            "failures": sum(1 for call in everything if call["failed"]),
            "matching": len(matching),
            "breakdown": breakdown,
            "tools": [row["name"] for row in breakdown],
            "tool": selected,
            "failures_only": failures_only,
            "page": current,
            "pages": pages,
            "first_index": (current - 1) * PAGE_SIZE + 1,
            "last_index": (current - 1) * PAGE_SIZE + len(window),
            "prev_url": _link(selected, failures_only, current - 1) if current > 1 else "",
            "next_url": _link(selected, failures_only, current + 1) if current < pages else "",
            "clear_url": _link("", False, 1),
            "failures_url": _link(selected, True, 1),
        },
    )
