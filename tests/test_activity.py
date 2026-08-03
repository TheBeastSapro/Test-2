"""The MCP activity log.

What is worth asserting here is not that the page renders — it is that the numbers on
it are true. A log with a wrong total is worse than no log, because it is the thing you
would reach for to check anything else.

So: the calls belong to the signed-in account and to nobody else, the total and the
breakdown match what was actually written into `ChatMessage.tool_calls`, the filters
narrow rather than reshuffle, the page never renders the whole log, and a conversation
that never used a tool leaves the page standing.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from forgecast.api.main import create_app
from forgecast.api.routes_activity import PAGE_SIZE, tally, tool_calls_for
from forgecast.api.routes_activity import router as activity_router
from forgecast.auth import hash_password
from forgecast.models import ChatMessage, Conversation, User


def _app():
    """The app, with this page mounted whether or not `main.py` has been wired up yet.

    Registered conditionally rather than unconditionally so these tests keep passing
    once the router is included there — a second identical route would otherwise shadow
    the real one and the suite would stop testing what ships.
    """
    app = create_app()
    if not any(getattr(route, "path", "") == "/activity" for route in app.routes):
        app.include_router(activity_router)
    return app


@pytest.fixture
def client(user):
    with TestClient(_app()) as test_client:
        token = test_client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "supersecret"},
        ).json()["access_token"]
        test_client.headers["Authorization"] = f"Bearer {token}"
        yield test_client


@pytest.fixture
def anonymous():
    with TestClient(_app()) as test_client:
        yield test_client


def thread(session, owner, title="Ocean Freight") -> Conversation:
    row = Conversation(user_id=owner.id, title=title)
    session.add(row)
    session.commit()
    return row


def turn(session, conversation, *calls, text="done") -> None:
    """One assistant turn, written the way the chat route writes it."""
    session.add(ChatMessage(conversation_id=conversation.id, role="assistant",
                            text=text, tool_calls=list(calls)))
    session.commit()


def call(name, failed=False, **arguments) -> dict:
    return {"id": f"toolu-{name}", "name": name, "input": arguments,
            "result": "ok", "is_error": failed}


def logged(body: str) -> list[str]:
    """The tool names in the log itself, in order.

    A plain substring search over the page cannot answer "was it filtered out": every
    tool name also appears in the breakdown table and in the filter's dropdown, both of
    which stay whole on purpose.
    """
    return re.findall(r'<span class="tool">([^<]+)</span>', body)


# ------------------------------------------------------------------ whose calls


def test_the_log_is_private_to_its_owner(client, session, user):
    other = User(email="someone@else.test", hashed_password=hash_password("x" * 12))
    session.add(other)
    session.flush()
    turn(session, thread(session, other, "Not yours"), call("their_secret_tool"))
    turn(session, thread(session, user), call("list_channels"))

    body = client.get("/activity").text
    assert "list_channels" in body
    # `ChatMessage` carries no user_id, so a query that forgot to join through the
    # conversation would return this and look perfectly healthy.
    assert "their_secret_tool" not in body
    assert "Not yours" not in body

    assert [row["name"] for row in tool_calls_for(session, user)] == ["list_channels"]


# ------------------------------------------------------- the count and breakdown


def test_the_total_and_the_breakdown_are_measured(client, session, user):
    conversation = thread(session, user)
    turn(session, conversation,
         call("study_youtube_channel", handle="@Kurzgesagt"),
         call("study_youtube_channel", handle="@Veritasium"),
         call("score_videos"))
    turn(session, conversation, call("study_youtube_channel"), call("start_run"))

    calls = tool_calls_for(session, user)
    assert len(calls) == 5
    assert tally(calls) == [
        {"name": "study_youtube_channel", "calls": 3, "failed": 0, "share": 60},
        {"name": "score_videos", "calls": 1, "failed": 0, "share": 20},
        {"name": "start_run", "calls": 1, "failed": 0, "share": 20},
    ]

    body = client.get("/activity").text
    assert "<b>5</b>" in body                     # the total, said once and plainly
    assert "60%" in body                          # and what it went on
    # The arguments are the part that makes a call reviewable rather than a name.
    assert "@Kurzgesagt" in body


def test_calls_are_newest_first_inside_a_turn_as_well_as_between_them(session, user):
    """A turn stores its calls in the order they ran.

    Listing turns newest-first while each turn's own calls read oldest-first produces a
    page that is neither, and "what did it just do" stops being answerable from the top.
    """
    conversation = thread(session, user)
    turn(session, conversation, call("first"), call("second"))
    turn(session, conversation, call("third"))

    assert [row["name"] for row in tool_calls_for(session, user)] == \
        ["third", "second", "first"]


# --------------------------------------------------------------------- filtering


def test_the_failures_filter_shows_only_the_failures(client, session, user):
    conversation = thread(session, user)
    turn(session, conversation,
         call("list_channels"),
         call("research_channel", failed=True, url="https://youtube.com/@nobody"))

    assert sorted(logged(client.get("/activity").text)) == \
        ["list_channels", "research_channel"]

    only_bad = client.get("/activity?failed=1").text
    # The whole point of the filter: the one broken call is not something you should
    # have to find by scrolling past the ninety that worked.
    assert logged(only_bad) == ["research_channel"]
    # The breakdown stays whole, because a breakdown of one filtered tool is a row
    # saying 100% and tells you nothing.
    assert "list_channels" in only_bad


def test_the_tool_filter_narrows_to_one_tool(client, session, user):
    conversation = thread(session, user)
    turn(session, conversation, call("list_channels"), call("start_run"))

    narrowed = client.get("/activity?tool=start_run").text
    assert logged(narrowed) == ["start_run"]
    # Still offered by the dropdown and still counted in the breakdown — only the log
    # is narrowed, so the page can be widened again from itself.
    assert "list_channels" in narrowed

    empty = client.get("/activity?tool=start_run&failed=1").text
    assert "No calls match that filter" in empty


# -------------------------------------------------------------------- pagination


def test_pagination_never_renders_the_whole_log(client, session, user):
    """A month of use is thousands of calls, and all of them is a page that never loads."""
    conversation = thread(session, user)
    for batch in range(3):
        turn(session, conversation,
             *[call(f"tool_{batch}_{index}") for index in range(PAGE_SIZE)])

    first = client.get("/activity").text
    assert first.count('class="log-call') == PAGE_SIZE
    assert "Page 1 of 3" in first
    assert "Older" in first
    assert "Newer" not in first

    second = client.get("/activity?page=2").text
    assert second.count('class="log-call') == PAGE_SIZE
    assert "Page 2 of 3" in second

    # A bookmark from when the log was longer must not render an empty page that reads
    # as though the calls were deleted.
    clamped = client.get("/activity?page=99").text
    assert "Page 3 of 3" in clamped
    assert clamped.count('class="log-call') == PAGE_SIZE


# ------------------------------------------------------------------- resilience


def test_a_conversation_with_no_tool_calls_does_not_break_the_page(client, session, user):
    conversation = thread(session, user, "Just talking")
    session.add(ChatMessage(conversation_id=conversation.id, role="user",
                            text="hello"))
    session.add(ChatMessage(conversation_id=conversation.id, role="assistant",
                            text="hello back", tool_calls=[]))
    session.commit()

    page = client.get("/activity")
    assert page.status_code == 200
    assert "No MCP activity yet." in page.text
    # And the empty state must not be a zero-less blank: the count is the answer.
    assert "<b>0</b>" in page.text
    assert tool_calls_for(session, user) == []


def test_a_malformed_call_is_counted_rather_than_crashing(session, user):
    """The column is JSON written by an earlier build, not a schema.

    A row from a build that stored a bare string, or a call the CLI reported with no
    name, must not take the page down — a log that dies on one odd row is a log you
    cannot rely on precisely when you are debugging.
    """
    conversation = thread(session, user)
    turn(session, conversation, "not a dict", {"input": {"a": 1}}, call("real_tool"))

    names = [row["name"] for row in tool_calls_for(session, user)]
    assert names == ["real_tool", "(unnamed)"]


def test_a_cut_result_says_how_much_is_missing(client, session, user):
    """Truncation has to announce itself, or the visible part reads as the whole."""
    conversation = thread(session, user)
    session.add(ChatMessage(
        conversation_id=conversation.id, role="assistant", text="",
        tool_calls=[{"id": "t", "name": "read_script", "input": {},
                     "result": "x" * 4000, "is_error": False}]))
    session.commit()

    body = client.get("/activity").text
    assert "more characters" in body


def test_the_page_needs_a_signed_in_user(anonymous):
    landing = anonymous.get("/activity", follow_redirects=False)
    assert landing.status_code == 303
    assert landing.headers["location"] == "/login?next=/activity"
