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

## Two passes, and why it is not one

The totals and the breakdown are over the whole log, so every row has to be read. The
page shows fifty calls. Those are different amounts of data and the code treats them as
different amounts of data.

The first pass reads every owned row and keeps four small values per call — name,
whether it failed, and where to find it again. It never builds the arguments or the
result. That matters because the result is the weight: the chat caps a captured result
at 4 KB and there is one per call, so a month of heavy use is tens of megabytes of
result text that exists only to be counted. Measured on 3,000 assistant turns carrying
15,000 calls — one month at the top of what one account does — building the full record
for every call peaked at 134 MB of Python objects and retained 35 MB, per request, to
render fifty rows. Four workers and two people pressing reload is a gigabyte. The index
pass reads the same rows in bounded chunks, so peak stops tracking the size of the log.

The second pass then fetches only the messages the page window actually needs and
builds the arguments and results for those. Both passes are a single statement each,
whatever the number of conversations — a per-conversation query would look fine for a
week and crawl after a month.

Note what is *not* read either way: `ChatMessage.text`. Assistant prose is the largest
column in the row and none of it appears here, so the queries name their columns
instead of loading whole ORM objects.

What would still force a real `tool_calls` table with indexed `name`, `created_at` and
`is_error` columns is aggregation the database has to do — calls per tool per day,
across accounts, for billing or a chart — or a single account passing roughly a million
calls, at which point counting them in Python costs more than the request is worth.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import NamedTuple
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import Select, select
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

# How many message rows the counting pass decodes at a time. The number matters less
# than the fact that there is one: the whole log has to be counted, but only this many
# rows' worth of captured results are ever alive in Python at once, so peak memory
# stops growing with the length of the log. Measured over 4, 12 and 36 MB of captured
# result text, peak held at 3.5, 3.6 and 4.2 MB. Raising it to 200 moved that plateau to
# 14 MB for no measurable gain in wall time — the fetches are cheap and the results are
# not.
INDEX_CHUNK_ROWS = 50


class Call(NamedTuple):
    """One tool call, minus its arguments and its result.

    A tuple rather than a dict because there is one of these per call in the account's
    entire history and dict overhead is most of what such a record weighs. `message`
    and `position` are how the page window finds the full record again in one query.
    """

    name: str
    failed: bool
    message: int
    position: int


def _when(moment: datetime | None) -> str:
    """Minutes, not seconds. Nobody reads a log to the second, and the extra digits
    push the columns that carry meaning off the side of the row."""
    return moment.strftime("%Y-%m-%d %H:%M") if moment else "—"


def _preview(text: str, limit: int) -> tuple[str, int]:
    """The visible part and how much was hidden, so truncation can announce itself.

    Silently cutting a result reads as the whole thing — the same trap the chat's own
    tool cards avoid by printing the remaining character count.

    Cutting happens here, on the raw text, and escaping happens in the template. The
    other order — escape then cut — can slice `&lt;` in half and put a bare `&` and a
    live `<` back on the page.
    """
    if len(text) <= limit:
        return text, 0
    return text[:limit], len(text) - limit


def _owned_messages(user: User) -> Select:
    """The message rows this account is allowed to see, newest first.

    Ownership lives on `Conversation`; `ChatMessage` has no `user_id` at all, so a
    filter written against the message alone returns every account's calls and looks
    perfectly healthy doing it. Both passes go through this one function so neither can
    be the pass that forgot.

    Ordered by `id` as well as `created_at` because turns written inside the same
    second are otherwise in whatever order the database felt like, and a log whose page
    two overlaps page one has lost calls.
    """
    return (
        select(
            ChatMessage.id,
            ChatMessage.created_at,
            ChatMessage.tool_calls,
            Conversation.id.label("conversation_id"),
            Conversation.title,
        )
        .join(Conversation, ChatMessage.conversation_id == Conversation.id)
        .where(Conversation.user_id == user.id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
    )


def _entries(stored: object) -> list[tuple[int, dict]]:
    """The calls inside one row's JSON column, newest first, paired with their position.

    `tool_calls` is a JSON column with nothing enforcing its shape: rows written by
    older builds, or by a chat turn that crashed halfway, can hold anything JSON can
    hold. The list below is the set of things that have to not take the page down,
    because a log that dies on one malformed row dies exactly when you are using it to
    work out what went wrong.

    A bare dict is read as the single call it obviously is — dropping it would make the
    total disagree with the transcript, which is the one thing this page may not do. A
    string, a number, a bool or a null hold no call to recover: `list()` over the first
    of those silently yields characters and over the rest raises `TypeError`, so the
    shape is refused here rather than either faking calls or returning a 500.

    The position is into the stored list so the second pass can go straight to the call
    the page asked for instead of re-deriving the order and hoping it matches.
    """
    if isinstance(stored, dict):
        return [(0, stored)]
    if not isinstance(stored, list):
        return []
    pairs = [(position, entry) for position, entry in enumerate(stored)
             if isinstance(entry, dict)]
    # Reversed within the message as well as between messages. A turn's calls are
    # stored in the order they ran, and a page that claims to be newest-first while
    # each group of five reads oldest-first is a page you cannot trust to answer
    # "what did it just do".
    pairs.reverse()
    return pairs


def _name_of(entry: dict) -> str:
    """The tool's name, or an honest admission that the record has none.

    Only a string is taken as a name. A dict or a list here means whatever wrote the
    row was broken, and printing its Python repr into the column reads as the page
    being corrupt rather than the record. The call is still counted either way: it
    happened, and a total that quietly disagrees with the transcript is worse than an
    ugly row.
    """
    raw = entry.get("name")
    return (raw.strip() or "(unnamed)") if isinstance(raw, str) else "(unnamed)"


def call_index(session: Session, user: User) -> list[Call]:
    """Every tool call in every one of this account's conversations, newest first.

    Deliberately without the arguments and the results — see the module docstring.
    Reading them here is what turns counting the log into holding the log.
    """
    index: list[Call] = []
    # Tool names repeat by the thousand across a log and there are only ever a handful
    # of distinct ones, so one string per name is kept instead of one per call.
    seen_names: dict[str, str] = {}

    rows = session.execute(
        _owned_messages(user).execution_options(yield_per=INDEX_CHUNK_ROWS)
    )
    for message_id, _at, stored, _conversation_id, _title in rows:
        # Most rows contribute nothing: every user turn and every assistant turn that
        # only talked has an empty list here, and a row written by an older build may
        # have no list at all.
        if not stored:
            continue
        for position, entry in _entries(stored):
            name = _name_of(entry)
            index.append(Call(
                name=seen_names.setdefault(name, name),
                failed=bool(entry.get("is_error")),
                message=message_id,
                position=position,
            ))
    return index


def tally(index: Sequence[Call]) -> list[dict]:
    """Calls per tool, busiest first — the answer to what the agent spends itself on.

    Share is carried alongside the count because a count on its own does not say
    whether 40 reads is most of the log or a corner of it, and that is the whole
    judgement this table exists to support.
    """
    counted: dict[str, dict] = {}
    for call in index:
        row = counted.setdefault(call.name,
                                 {"name": call.name, "calls": 0, "failed": 0})
        row["calls"] += 1
        if call.failed:
            row["failed"] += 1

    total = len(index) or 1
    for row in counted.values():
        row["share"] = round(100 * row["calls"] / total)
    return sorted(counted.values(), key=lambda row: (-row["calls"], row["name"]))


def page_of_calls(session: Session, user: User, window: Sequence[Call]) -> list[dict]:
    """The rows for one page: arguments, results, thread and time, for these calls only.

    One statement for the whole window rather than one per call. Ownership is asserted
    again here instead of being inherited from the index: this reads messages by id, and
    a by-id read that trusts an id handed to it is the shape every cross-account leak
    has. The join costs nothing and removes the question.
    """
    if not window:
        return []

    rows = session.execute(
        _owned_messages(user).where(ChatMessage.id.in_({call.message for call in window}))
    ).all()
    fetched = {
        message_id: (at, conversation_id, title, dict(_entries(stored)))
        for message_id, at, stored, conversation_id, title in rows
    }

    page: list[dict] = []
    for call in window:
        found = fetched.get(call.message)
        if found is None:
            # The thread was deleted between the two statements. Skipping keeps the
            # "showing 1-50 of 900" line honest, which is derived from what is here.
            continue
        at, conversation_id, title, entries = found
        entry = entries.get(call.position)
        if entry is None:
            continue

        arguments = json.dumps(entry.get("input") or {}, ensure_ascii=False,
                               sort_keys=True, default=str)
        # `or ""` would report a tool that returned `0` or `false` as having returned
        # nothing at all, which is a different claim and a wrong one.
        raw_result = entry.get("result")
        result = "" if raw_result is None else str(raw_result)
        result_shown, result_cut = _preview(result, RESULT_PREVIEW_CHARS)
        args_shown, args_cut = _preview(arguments, ARGS_PREVIEW_CHARS)
        page.append({
            # Name and failure come from the index, not from the entry, so the badge on
            # the row can never disagree with the filter that selected it or with the
            # count in the breakdown.
            "name": call.name,
            "failed": call.failed,
            "conversation": title or "Untitled",
            "conversation_id": conversation_id,
            "at": _when(at),
            "arguments": arguments,
            "args_preview": args_shown,
            "args_cut": args_cut,
            "result": result_shown,
            "result_cut": result_cut,
            "has_result": bool(result),
        })
    return page


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


def _page_number(raw: str) -> int:
    """Whatever is in the query string, as a page number.

    Declared as a string and parsed here rather than annotated `int`, because FastAPI
    answers `?page=` or `?page=two` with a 422 and a JSON validation body — an API
    error served into a browser tab, from a URL a person edited or an email client
    truncated. There is nothing a bad value can mean except the first page, and it gets
    clamped against the real page count regardless.
    """
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 1


@router.get("/activity", response_class=HTMLResponse)
def activity_page(
    request: Request,
    session: Session = Depends(get_session),
    tool: str = "",
    failed: str = "",
    page: str = "1",
) -> HTMLResponse:
    from .routes_web import TEMPLATES, shell

    user = optional_user(request, session)
    if user is None:
        return RedirectResponse("/login?next=/activity", 303)  # type: ignore[return-value]

    index = call_index(session, user)
    failures_only = failed not in ("", "0", "false")

    # The breakdown and the headline totals are computed before filtering, on purpose.
    # A breakdown that reflects the current filter shows one row saying "100%", which
    # is not a breakdown, and the links in it would have nowhere left to go.
    breakdown = tally(index)

    selected = tool.strip()
    matching = [
        call for call in index
        if (not selected or call.name == selected)
        and (not failures_only or call.failed)
    ]

    pages = max(1, -(-len(matching) // PAGE_SIZE))
    # Clamped rather than trusted: a bookmark from when the log was longer, or a hand
    # edited query string, would otherwise render an empty page that looks like the
    # calls were deleted.
    current = min(max(1, _page_number(page)), pages)
    start = (current - 1) * PAGE_SIZE
    calls = page_of_calls(session, user, matching[start:start + PAGE_SIZE])

    return TEMPLATES.TemplateResponse(
        request,
        "activity.html",
        {
            **shell(session, user, "activity"),
            "calls": calls,
            "total": len(index),
            "failures": sum(1 for call in index if call.failed),
            "matching": len(matching),
            "breakdown": breakdown,
            "tools": [row["name"] for row in breakdown],
            "tool": selected,
            "failures_only": failures_only,
            "page": current,
            "pages": pages,
            "first_index": start + 1,
            # Counted from what was actually built, not from the window that was asked
            # for, so the line cannot claim a row the page is not showing.
            "last_index": start + len(calls),
            "prev_url": _link(selected, failures_only, current - 1) if current > 1 else "",
            "next_url": _link(selected, failures_only, current + 1) if current < pages else "",
            "clear_url": _link("", False, 1),
            "failures_url": _link(selected, True, 1),
        },
    )
