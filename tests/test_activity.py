"""The MCP activity log.

What is worth asserting here is not that the page renders — it is that the numbers on
it are true. A log with a wrong total is worse than no log, because it is the thing you
would reach for to check anything else.

So: the calls belong to the signed-in account and to nobody else, the total and the
breakdown match what was actually written into `ChatMessage.tool_calls`, the filters
narrow rather than reshuffle, the page never renders the whole log, and a conversation
that never used a tool leaves the page standing.

Three of the groups below are about how the page behaves under things it does not
control. `tool_calls` is a JSON column with no schema, so its contents are asserted
against every shape JSON can hold rather than the one the chat happens to write today.
Tool names, arguments and results are text the model and the user chose, so they are
asserted to reach the browser as text. And the cost of one page load is measured —
statements and Python memory — because both are things that look fine on a week of use
and decide whether the page still works after a month of it.
"""

from __future__ import annotations

import re
import tracemalloc

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from forgecast.api.main import create_app
from forgecast.api.routes_activity import (
    PAGE_SIZE,
    call_index,
    page_of_calls,
    tally,
)
from forgecast.api.routes_activity import router as activity_router
from forgecast.auth import create_access_token, hash_password
from forgecast.db import engine
from forgecast.models import ChatMessage, Conversation, User

PAYLOAD = "<script>alert(1)</script>"
ATTRIBUTE_BREAK = '"><img src=x onerror=alert(1)>'


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


def account(session, email="someone@else.test") -> User:
    row = User(email=email, hashed_password=hash_password("x" * 12))
    session.add(row)
    session.flush()
    return row


def signed_in_as(owner: User) -> TestClient:
    """A client holding this account's session, for the two-account isolation checks.

    The token is minted rather than logged in for, because the second account in those
    tests is created directly against the session and never has a password typed at it.
    """
    test_client = TestClient(_app())
    test_client.headers["Authorization"] = f"Bearer {create_access_token(owner)}"
    return test_client


def thread(session, owner, title="Ocean Freight") -> Conversation:
    row = Conversation(user_id=owner.id, title=title)
    session.add(row)
    session.commit()
    return row


def turn(session, conversation, *calls, text="done") -> ChatMessage:
    """One assistant turn, written the way the chat route writes it."""
    row = ChatMessage(conversation_id=conversation.id, role="assistant",
                      text=text, tool_calls=list(calls))
    session.add(row)
    session.commit()
    return row


def stored(session, conversation, value) -> ChatMessage:
    """A turn whose `tool_calls` is whatever was passed, valid or not.

    `turn` wraps its arguments in a list, which is exactly the assumption the malformed
    data tests exist to remove.
    """
    row = ChatMessage(conversation_id=conversation.id, role="assistant",
                      text="", tool_calls=value)
    session.add(row)
    session.commit()
    return row


def call(name, failed=False, result="ok", **arguments) -> dict:
    return {"id": f"toolu-{name}", "name": name, "input": arguments,
            "result": result, "is_error": failed}


def logged(body: str) -> list[str]:
    """The tool names in the log itself, in order.

    A plain substring search over the page cannot answer "was it filtered out": every
    tool name also appears in the breakdown table and in the filter's dropdown, both of
    which stay whole on purpose.
    """
    return re.findall(r'<span class="tool">([^<]*)</span>', body)


def rows_of(session, owner) -> list[dict]:
    """The full page rows for everything this account has, newest first."""
    return page_of_calls(session, owner, call_index(session, owner))


def rendered(body: str) -> str:
    """Only what this page put on the document, without the shell around it.

    `base.html` legitimately ends with two `<script>` blocks, so "the string `<script`
    is absent" cannot be asserted against the whole response — and an assertion that has
    to be weakened to pass is one that proves nothing. Every value this page interpolates
    lands inside `<main>`.
    """
    head, _, _rest = body.partition("</main>")
    assert _, "base.html no longer wraps the page in <main>, so this slice is a lie"
    return head


class Statements:
    """Counts SQL statements for a block of work.

    A page that issues one query per conversation reads identically to one that issues
    a single query, right up until the account has three hundred threads. Counting is
    the only way that difference is visible in a test.
    """

    def __init__(self) -> None:
        self.sql: list[str] = []

    def __enter__(self):
        event.listen(engine, "before_cursor_execute", self._record)
        return self

    def __exit__(self, *_exc) -> None:
        event.remove(engine, "before_cursor_execute", self._record)

    def _record(self, _conn, _cursor, statement, *_rest) -> None:
        self.sql.append(statement)

    def against(self, table: str) -> int:
        return sum(1 for statement in self.sql if table in statement)


# ------------------------------------------------------------------ whose calls


def test_the_log_is_private_to_its_owner(client, session, user):
    other = account(session)
    turn(session, thread(session, other, "Not yours"), call("their_secret_tool"))
    turn(session, thread(session, user), call("list_channels"))

    body = client.get("/activity").text
    assert "list_channels" in body
    # `ChatMessage` carries no user_id, so a query that forgot to join through the
    # conversation would return this and look perfectly healthy.
    assert "their_secret_tool" not in body
    assert "Not yours" not in body

    assert [row.name for row in call_index(session, user)] == ["list_channels"]


def test_two_accounts_each_see_exactly_their_own_calls(session, user):
    """Isolation asserted from both sides, and through every count on the page.

    A one-sided test passes against a query that returns the union, as long as the
    account under test happens to own the row the assertion looks for.
    """
    other = account(session)
    mine = thread(session, user, "Mine")
    theirs = thread(session, other, "Theirs")
    turn(session, mine, call("mine_one"), call("mine_two"), call("mine_three"))
    turn(session, theirs, call("theirs_one", failed=True))

    assert [row.name for row in call_index(session, user)] == \
        ["mine_three", "mine_two", "mine_one"]
    assert [row.name for row in call_index(session, other)] == ["theirs_one"]

    with signed_in_as(user) as as_me, signed_in_as(other) as as_them:
        page_of_mine = as_me.get("/activity").text
        page_of_theirs = as_them.get("/activity").text

    assert logged(page_of_mine) == ["mine_three", "mine_two", "mine_one"]
    assert "theirs_one" not in page_of_mine
    assert logged(page_of_theirs) == ["theirs_one"]
    assert "mine_" not in page_of_theirs
    # The failure counter is its own aggregate and its own chance to leak: mine is 0
    # and theirs is 1, and a shared query would show 1 on both pages.
    assert "<b>3</b>" in page_of_mine and "<b>0</b>" in page_of_mine
    assert "<b>1</b>" in page_of_theirs


def test_a_filter_cannot_reach_another_accounts_calls(session, user):
    """The filters are the part a URL can aim.

    Asking for a tool only the other account ever used, on a page that is not theirs,
    must find nothing rather than find theirs.
    """
    other = account(session)
    turn(session, thread(session, other, "Theirs"), call("their_secret_tool", failed=True))
    turn(session, thread(session, user, "Mine"), call("list_channels"))

    with signed_in_as(user) as as_me:
        by_name = as_me.get("/activity?tool=their_secret_tool").text
        by_failure = as_me.get("/activity?failed=1").text

    assert logged(by_name) == []
    assert "No calls match that filter" in by_name
    assert logged(by_failure) == []
    assert "their_secret_tool" not in by_name + by_failure


def test_the_window_query_is_scoped_and_not_keyed_on_id_alone(session, user):
    """`page_of_calls` reads messages by id, which is the shape of every leak.

    Handed an index entry pointing at another account's message — which is what a
    caller confusing two users, or a future filter built the wrong way round, produces
    — it must return nothing rather than that message's arguments.
    """
    other = account(session)
    their_message = turn(session, thread(session, other, "Theirs"),
                         call("their_secret_tool", token="hunter2"))
    their_index = call_index(session, other)
    assert len(their_index) == 1

    assert page_of_calls(session, other, their_index)[0]["arguments"] == \
        '{"token": "hunter2"}'
    # Same index, wrong owner. The join is what refuses it.
    assert page_of_calls(session, user, their_index) == []
    assert their_message.id is not None


# ------------------------------------------------------- the count and breakdown


def test_the_total_and_the_breakdown_are_measured(client, session, user):
    conversation = thread(session, user)
    turn(session, conversation,
         call("study_youtube_channel", handle="@Kurzgesagt"),
         call("study_youtube_channel", handle="@Veritasium"),
         call("score_videos"))
    turn(session, conversation, call("study_youtube_channel"), call("start_run"))

    index = call_index(session, user)
    assert len(index) == 5
    assert tally(index) == [
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

    assert [row.name for row in call_index(session, user)] == ["third", "second", "first"]
    # And the page rows keep that order, which is a separate step: they are rebuilt from
    # a second query whose own row order is whatever the database returns.
    assert [row["name"] for row in rows_of(session, user)] == ["third", "second", "first"]


def test_the_arguments_shown_belong_to_the_call_they_are_shown_against(session, user):
    """The window is rebuilt by (message, position), so an off-by-one here is silent.

    Every call would still be listed, the total would still be right, and each row
    would carry somebody else's arguments — the failure mode that makes a log actively
    misleading rather than merely wrong.
    """
    conversation = thread(session, user)
    turn(session, conversation,
         call("read", path="alpha"), call("read", path="beta"), call("read", path="gamma"))
    turn(session, conversation, call("read", path="delta"))

    assert [row["arguments"] for row in rows_of(session, user)] == [
        '{"path": "delta"}',
        '{"path": "gamma"}',
        '{"path": "beta"}',
        '{"path": "alpha"}',
    ]


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


def test_a_tool_name_that_does_not_exist_empties_the_log_and_nothing_else(client,
                                                                         session, user):
    turn(session, thread(session, user), call("list_channels"))

    body = client.get("/activity?tool=no_such_tool").text
    assert body.count('class="log-call') == 0
    assert "No calls match that filter" in body
    # The totals are pre-filter, so an unmatched filter must not read as an empty log.
    assert "<b>1</b>" in body
    assert "No MCP activity yet." not in body


def test_both_filters_at_once_intersect(client, session, user):
    conversation = thread(session, user)
    turn(session, conversation,
         call("read_channel", failed=True),
         call("read_channel"),
         call("start_run", failed=True))

    both = client.get("/activity?tool=read_channel&failed=1").text
    assert logged(both) == ["read_channel"]
    assert both.count('class="log-call') == 1


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


def test_the_pages_partition_the_log_rather_than_overlapping_it(client, session, user):
    """Two pages that share a row have lost a different one.

    Turns written inside the same second sort by `created_at` alone in an order the
    database picks, so paging without a tiebreaker silently drops calls.
    """
    conversation = thread(session, user)
    for batch in range(3):
        turn(session, conversation,
             *[call(f"tool_{batch * PAGE_SIZE + index}") for index in range(PAGE_SIZE)])

    seen: list[str] = []
    for number in (1, 2, 3):
        seen += logged(client.get(f"/activity?page={number}").text)

    assert len(seen) == 3 * PAGE_SIZE
    assert len(set(seen)) == 3 * PAGE_SIZE
    assert seen == [row.name for row in call_index(session, user)]


@pytest.mark.parametrize("query", ["page=0", "page=-4", "page=two", "page=", "page=2.5",
                                   "page=99999999999999999999"])
def test_a_page_number_that_is_not_a_page_number_still_renders_the_page(client, session,
                                                                       user, query):
    """A query string gets hand-edited, truncated by mail clients, and guessed at.

    Annotating `page` as an int hands those to FastAPI, which answers with a 422 and a
    JSON validation body — an API error in a browser tab, on a page whose whole design
    is to clamp instead of complain.
    """
    turn(session, thread(session, user), call("list_channels"))

    response = client.get(f"/activity?{query}")
    assert response.status_code == 200
    assert logged(response.text) == ["list_channels"]
    assert "Page 1 of 1" in response.text


def test_the_showing_line_counts_the_rows_that_are_actually_there(client, session, user):
    conversation = thread(session, user)
    turn(session, conversation, *[call(f"tool_{index}") for index in range(PAGE_SIZE + 3)])

    last = client.get("/activity?page=2").text
    assert f"Showing {PAGE_SIZE + 1}–{PAGE_SIZE + 3} of {PAGE_SIZE + 3}" in last
    assert last.count('class="log-call') == 3


# ------------------------------------------------------- what one page load costs


def test_one_page_load_is_a_fixed_number_of_queries(client, session, user):
    """Aggregating in Python is only defensible if it is not also aggregating in SQL.

    One query per conversation is the version that passes every test written against a
    fixture with two threads and takes seconds per page against an account with three
    hundred. Sixty conversations here, and the statement count is compared against the
    same page load with one.
    """
    lonely = thread(session, user, "only thread")
    turn(session, lonely, call("read_channel"))

    with Statements() as few:
        client.get("/activity")

    for number in range(60):
        conversation = thread(session, user, f"thread {number}")
        turn(session, conversation, call("read_channel"), call("start_run"))

    with Statements() as many:
        client.get("/activity")

    assert many.against("chat_messages") == few.against("chat_messages")
    # Two: the index over everything, and the window the page shows.
    assert many.against("chat_messages") == 2
    assert len(many.sql) == len(few.sql)


RESULT_CHARS = 4000        # what the chat caps a captured result at
CALLS_PER_TURN = 5


def _grow_log(session, user, turns) -> None:
    conversation = thread(session, user, f"{turns} more turns")
    payload = "R" * RESULT_CHARS
    for _batch in range(turns):
        session.add(ChatMessage(
            conversation_id=conversation.id, role="assistant", text="",
            tool_calls=[call(f"tool_{index}", result=payload)
                        for index in range(CALLS_PER_TURN)]))
    session.commit()
    session.expunge_all()


def _measure_index(session, user) -> tuple[int, int, int]:
    """Bytes retained and peaked while counting the whole log, and its size in results.

    The third number is what the memory has to stay decoupled from: how much captured
    result text the pass had to read past to reach the totals.
    """
    tracemalloc.start()
    try:
        index = call_index(session, user)
        retained, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return retained, peak, len(index) * RESULT_CHARS


def test_counting_the_log_does_not_mean_holding_the_log(session, user):
    """The captured results are the weight, and none of them are needed to count.

    The chat caps a result at 4 KB and writes one per call, so a month of heavy use is
    tens of megabytes of result text that the totals have to read past and nothing has
    to keep. Tripling the log below triples the text read and must not triple either
    number measured: what is retained is a few tuples a call, and what peaks is one
    bounded chunk of rows.

    Building the full record for every call — arguments, result preview and all, while
    counting — retained 35 MB and peaked at 134 MB on 15,000 calls, per request, to
    render fifty rows.
    """
    _grow_log(session, user, 400)
    small_retained, small_peak, small_text = _measure_index(session, user)

    _grow_log(session, user, 800)
    big_retained, big_peak, big_text = _measure_index(session, user)

    assert big_text == 3 * small_text == 3 * 400 * CALLS_PER_TURN * RESULT_CHARS
    # Retained grows with the number of calls, which is the point: it is the index. What
    # it may not do is grow with the size of what those calls returned.
    assert big_retained < small_retained + 1_000_000, (
        f"retained {small_retained} then {big_retained} bytes while the result text "
        f"went from {small_text} to {big_text}"
    )
    assert big_peak < 1.5 * small_peak, (
        f"peak went {small_peak} -> {big_peak} bytes for 3x the log, which is the "
        "whole log being alive at once"
    )
    # And in absolute terms: 24 MB of results read, single-digit megabytes held.
    assert big_peak < big_text // 4, f"peaked at {big_peak} of {big_text} bytes read"


def test_the_window_query_reads_only_the_messages_on_the_page(session, user):
    conversation = thread(session, user)
    for batch in range(4):
        turn(session, conversation,
             *[call(f"tool_{batch}_{index}") for index in range(PAGE_SIZE)])

    index = call_index(session, user)
    with Statements() as counted:
        rows = page_of_calls(session, user, index[:PAGE_SIZE])

    assert len(rows) == PAGE_SIZE
    assert counted.against("chat_messages") == 1


# -------------------------------------------------------- malformed stored JSON


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
    assert call_index(session, user) == []


def test_a_malformed_call_is_counted_rather_than_crashing(session, user):
    """The column is JSON written by an earlier build, not a schema.

    A row from a build that stored a bare string, or a call the CLI reported with no
    name, must not take the page down — a log that dies on one odd row is a log you
    cannot rely on precisely when you are debugging.
    """
    conversation = thread(session, user)
    turn(session, conversation, "not a dict", {"input": {"a": 1}}, call("real_tool"))

    assert [row.name for row in call_index(session, user)] == ["real_tool", "(unnamed)"]


@pytest.mark.parametrize("value", [
    None,                          # written before the column existed
    [],
    "study_youtube_channel",       # a string where a list belongs
    ["read", "write"],             # a list of strings: `list()` yields them, no dicts
    0,
    7,                             # a scalar: `list()` raises TypeError, page 500s
    1.5,
    True,
    [None, None],
    [[{"name": "nested"}]],
])
def test_no_shape_of_stored_json_can_take_the_page_down(client, session, user, value):
    """`tool_calls` is JSON with nothing enforcing what goes in it.

    The numbers and the bool are the interesting ones: `list()` over them raises, and
    the row is reached inside the loop that builds the totals, so one such row turns the
    whole page into a 500 for that account, permanently, with no way to clear it from
    the UI.
    """
    conversation = thread(session, user, "Odd row")
    stored(session, conversation, value)
    turn(session, conversation, call("real_tool"))

    response = client.get("/activity")
    assert response.status_code == 200
    assert "real_tool" in response.text
    # Nothing invented from a shape that holds no call, and nothing lost from the row
    # next to it.
    assert [row.name for row in call_index(session, user)] == ["real_tool"]


def test_a_call_stored_without_its_list_is_still_counted(session, user):
    """A dict where a list belongs is unambiguously one call.

    Dropping it would make the total disagree with the transcript, and a total that
    disagrees with the transcript is the one thing this page may not do.
    """
    conversation = thread(session, user)
    stored(session, conversation, call("unwrapped", handle="@x"))

    index = call_index(session, user)
    assert [row.name for row in index] == ["unwrapped"]
    assert page_of_calls(session, user, index)[0]["arguments"] == '{"handle": "@x"}'


@pytest.mark.parametrize("name", [None, "", "   ", 42, 3.5, True, ["read"],
                                  {"tool": "read"}])
def test_a_name_that_is_not_a_name_does_not_lose_the_call(client, session, user, name):
    conversation = thread(session, user)
    stored(session, conversation, [{"id": "t", "name": name, "input": {},
                                    "result": "ok", "is_error": False}])

    index = call_index(session, user)
    assert [row.name for row in index] == ["(unnamed)"]
    assert client.get("/activity").status_code == 200
    # A Python repr of a dict or a list on screen reads as the page being broken rather
    # than the record, so it is not shown at all.
    assert "'tool'" not in client.get("/activity").text


@pytest.mark.parametrize("entry", [
    {"name": "read", "input": "a bare string"},
    {"name": "read", "input": ["a", "list"]},
    {"name": "read", "input": 5},
    {"name": "read", "result": {"nested": "dict"}},
    {"name": "read", "result": ["a", "list"]},
    {"name": "read", "is_error": "yes"},
    {"name": "read", "is_error": None},
    {"name": "read"},
])
def test_an_input_or_a_result_of_the_wrong_type_still_renders(client, session, user,
                                                             entry):
    stored(session, thread(session, user), [entry])

    response = client.get("/activity")
    assert response.status_code == 200
    assert logged(response.text) == ["read"]


def test_a_result_of_zero_is_not_reported_as_no_result(session, user):
    """`or ""` would collapse a falsy result into "nothing came back".

    That is a different claim from the one the record makes, and on an audit log the
    difference is the whole point.
    """
    conversation = thread(session, user)
    stored(session, conversation, [{"name": "count_videos", "input": {},
                                    "result": 0, "is_error": False}])

    row = page_of_calls(session, user, call_index(session, user))[0]
    assert row["has_result"] is True
    assert row["result"] == "0"


def test_a_cut_result_says_how_much_is_missing(client, session, user):
    """Truncation has to announce itself, or the visible part reads as the whole."""
    conversation = thread(session, user)
    stored(session, conversation, [{"id": "t", "name": "read_script", "input": {},
                                    "result": "x" * 4000, "is_error": False}])

    body = client.get("/activity").text
    assert "more characters" in body


# --------------------------------------------------------------- injected markup


def test_a_payload_in_a_tool_input_cannot_execute(client, session, user):
    """Tool inputs are text the model wrote from something the user typed.

    Both are attacker-reachable — "research this channel" carries whatever is in the
    channel's name — and both are interpolated into the row twice, once truncated to a
    preview and once in full.
    """
    conversation = thread(session, user)
    turn(session, conversation, call("research_channel", handle=PAYLOAD,
                                     note=ATTRIBUTE_BREAK))

    body = rendered(client.get("/activity").text)
    assert "<script" not in body
    assert "<img" not in body
    # `onerror` as escaped text, or percent-encoded inside an href, is inert. `onerror`
    # as an attribute on a real tag is not, and that is what the assertion has to be
    # about — a flat substring search cannot tell the two apart and so proves nothing.
    assert not re.search(r"<[^<>]*\sonerror\s*=", body)
    # Escaped, not dropped: the argument is the reviewable part of a call, and silently
    # deleting it would hide what the agent was actually asked to do.
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
    assert "&#34;&gt;&lt;img src=x onerror=alert(1)&gt;" in body


def test_a_payload_in_a_tool_result_cannot_execute(client, session, user):
    """A result is a third party's HTML as often as not — this page renders what a
    scraped channel description said, and that is not text anyone controls."""
    conversation = thread(session, user)
    turn(session, conversation,
         call("read_page", result=f"fetched: {PAYLOAD} {ATTRIBUTE_BREAK}"))

    body = rendered(client.get("/activity").text)
    assert "<script" not in body
    assert "<img" not in body
    assert not re.search(r"<[^<>]*\sonerror\s*=", body)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body


def test_a_payload_cut_by_the_preview_boundary_cannot_leave_live_markup(client, session,
                                                                       user):
    """The preview cuts at a character count, and the cut can land anywhere.

    Cutting raw text and escaping afterwards is safe. Escaping first and cutting after
    is not: the boundary lands inside `&lt;` and puts a bare `<` back on the page. This
    aims a payload at the boundary so the wrong order is a failing test rather than a
    code review someone skipped.
    """
    conversation = thread(session, user)
    padding = "p" * 200
    turn(session, conversation,
         call("read_page", pad=padding, tail=PAYLOAD,
              result=padding + PAYLOAD + padding))

    body = rendered(client.get("/activity").text)
    assert "<script" not in body
    assert "&lt;" in body
    # A cut that split an entity leaves a stray `&` followed by nothing that resolves.
    assert not re.search(r"&(?![a-zA-Z]+;|#\d+;|#x[0-9a-fA-F]+;)", body)


def test_a_payload_in_a_tool_name_cannot_break_out_of_the_filter_dropdown(client,
                                                                         session, user):
    """A tool name reaches the page in five places, one of them an attribute value.

    The row, the breakdown's link text, the dropdown option's text, the option's `value`
    and the breakdown's `href`. `value` is the one where a bare `"` ends the attribute
    and starts a tag, so it is the one this payload is shaped for — and it only takes the
    single interpolation that was missed.
    """
    conversation = thread(session, user)
    turn(session, conversation, call(f"read{ATTRIBUTE_BREAK}"))

    body = rendered(client.get("/activity").text)
    assert "<img" not in body
    assert '"><img' not in body
    # Four escaped as text or attribute text, and the href percent-encoded instead. The
    # count is exact so that a fifth place growing an unescaped copy fails here.
    assert body.count("&#34;&gt;&lt;img src=x onerror=alert(1)&gt;") == 4
    assert "tool=read%22%3E%3Cimg%20src%3Dx%20onerror%3Dalert%281%29%3E" in body


def test_a_payload_in_a_conversation_title_cannot_execute(client, session, user):
    """The thread name is on every row, and a thread gets its name from the first thing
    the user typed into it."""
    conversation = thread(session, user, f"Ocean {PAYLOAD}")
    turn(session, conversation, call("list_channels"))

    body = rendered(client.get("/activity").text)
    assert "<script" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body


def test_nothing_in_the_template_opts_out_of_escaping():
    """There are three ways to turn escaping off, and all three would be a live XSS here.

    `|safe` on a value, `{% autoescape false %}` around a region, and `{% filter safe %}`
    over a block. Asserted against the file because the line that reintroduces one will
    arrive looking like a formatting fix on a page whose every value is model output.
    """
    from pathlib import Path

    import forgecast

    source = (Path(forgecast.__file__).parent / "web" / "activity.html").read_text()
    dense = "".join(source.split())
    assert "|safe" not in dense
    assert "autoescape" not in dense
    assert "filtersafe" not in dense


def test_autoescaping_is_actually_on_for_this_template():
    """Autoescaping is a property of the shared environment, not of this file.

    If `select_autoescape` were ever configured with a narrower extension list, or the
    page renamed to something outside it, every assertion above would keep passing on
    the strings and the browser would still execute them.
    """
    from forgecast.api.routes_web import TEMPLATES

    assert TEMPLATES.env.autoescape("activity.html") is True
    assert TEMPLATES.env.get_template("activity.html") is not None


# ------------------------------------------------------------------------ access


def test_the_page_needs_a_signed_in_user(anonymous):
    landing = anonymous.get("/activity", follow_redirects=False)
    assert landing.status_code == 303
    assert landing.headers["location"] == "/login?next=/activity"
