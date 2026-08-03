"""The channel hub: one channel as a place, and the four numbers on it.

Two things are worth guarding here and they are different in kind.

The first is the boundary. `/c/{id}` takes a small integer out of a URL, so the whole
id space is walkable by hand, and the only acceptable answer for someone else's channel
is the answer for a channel that does not exist. The test therefore checks the status
*and* that the name never reaches the body — a 404 that still renders the page is a
leak with a reassuring status line on it.

The second is arithmetic. Every figure asserted below was worked out on paper first:
five runs, two finished, one at a gate, and 40 + 60 + 25 + 0 + (30 − 10) = 145 credits.
A test that only asserted the page agrees with itself would pass just as happily if the
hub counted the other channel's runs too — which is the one mistake a per-channel page
can make that looks completely normal on screen.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from forgecast import credits as billing
from forgecast.api.main import create_app
from forgecast.api.routes_channel import (
    HUB_RUNS,
    IDLE,
    PRODUCING,
    WAITING,
    hub_facts,
    status_word,
)
from forgecast.auth import create_access_token, hash_password
from forgecast.db import SessionLocal
from forgecast.models import Channel, Node, Run, RunStatus, User


def test_the_hub_is_registered_in_the_app_that_actually_serves():
    """Both routes answer on `create_app()`, not only on an app a test assembled.

    These tests were written while `main.py` belonged to another workstream, so they
    mounted the router themselves — and passed while `/c/1` was a 404 on the real app.
    A test that builds its own app can prove a handler works and prove nothing about
    whether anyone can reach it.

    Asked as a request rather than by reading `app.routes`, because this FastAPI keeps
    an included router as one opaque entry there instead of flattening its paths in —
    so a route-list check reports "not registered" for every router in the app. An
    unregistered path 404s; a registered one sends a signed-out visitor to the login
    page, and the difference is the whole assertion.
    """
    with TestClient(create_app()) as anonymous:
        for path in ("/c/1", "/c/1/runs"):
            answer = anonymous.get(path, follow_redirects=False)
            assert answer.status_code == 303, f"{path} is not reachable in the real app"


@pytest.fixture
def client(user: User):
    with TestClient(create_app()) as test_client:
        test_client.headers["Authorization"] = f"Bearer {create_access_token(user)}"
        yield test_client


def a_run(
    session: Session,
    channel: Channel,
    *,
    status: RunStatus = RunStatus.completed,
    spend: int = 0,
    refund: int = 0,
    topic: str = "Anything",
) -> Run:
    """One run on a channel, with what it really cost.

    Credits go in through the ledger calls the engine uses rather than by setting
    `Run.credits_spent`, because the hub reads the ledger. A fixture that only set the
    counter would be testing a code path the app does not have.
    """
    run = Run(
        channel_id=channel.id,
        user_id=channel.user_id,
        topic=topic,
        status=status,
    )
    session.add(run)
    session.flush()
    if spend or refund:
        node = Node(run_id=run.id, key="script", type="script", title="Script")
        session.add(node)
        session.flush()
        if spend:
            billing.settle_node(session, run, node, estimated=0, actual=spend)
        if refund:
            billing.refund_node(session, run, node, refund, note="provider returned junk")
    session.commit()
    return run


def page(body: str) -> str:
    """The channel's own content, without the shell around it.

    The left rail is account-wide by design: it lists every recent run and both format
    tabs. Asserting against the whole document therefore passes for the wrong reason —
    "Shorts" is in the rail on every page, and another channel's run topic is in the
    rail while being correctly absent from this hub. Cutting at the breadcrumb, which
    is the first thing this template emits, is what makes these assertions about the
    page rather than about the sidebar.
    """
    marker = 'aria-label="Breadcrumb"'
    assert marker in body, "the hub rendered without its breadcrumb"
    return body.split(marker, 1)[1]


def another_account(session: Session) -> Channel:
    """A second account with a channel of its own — the thing that must never render."""
    stranger = User(email="stranger@example.com", hashed_password=hash_password("supersecret"))
    session.add(stranger)
    session.flush()
    theirs = Channel(user_id=stranger.id, name="Someone Else Entirely", niche="cars")
    session.add(theirs)
    session.commit()
    return theirs


# ------------------------------------------------------------------- the boundary


def test_hub_renders_for_an_owned_channel(client, channel: Channel):
    response = client.get(f"/c/{channel.id}")
    assert response.status_code == 200
    body = page(response.text)
    assert channel.name in body
    # The breadcrumb reads "/ <channel> / hub", so the segment naming the view is there.
    assert ">hub</span>" in body
    # The derived format, not a stored column: a 16:9 channel is long-form.
    assert ">▬ Long-form</span>" in body
    # The nav inside the channel keeps the id, so neither entry drops you back out.
    assert f'href="/c/{channel.id}/runs"' in body


def test_shorts_channel_shows_its_derived_format(client, session: Session, user: User):
    vertical = Channel(user_id=user.id, name="Quick Cuts", aspect_ratio="9:16")
    session.add(vertical)
    session.commit()

    body = page(client.get(f"/c/{vertical.id}").text)
    assert ">▮ Shorts</span>" in body
    assert "Long-form" not in body


def test_another_accounts_channel_is_404_and_renders_nothing(client, session: Session):
    theirs = another_account(session)

    response = client.get(f"/c/{theirs.id}")
    assert response.status_code == 404
    # Not 403. A distinguishable refusal confirms the id exists, which is the part
    # worth not confirming when ids are small integers.
    assert response.status_code != 403
    assert theirs.name not in response.text


def test_another_accounts_channel_runs_are_404_too(client, session: Session):
    theirs = another_account(session)

    response = client.get(f"/c/{theirs.id}/runs")
    assert response.status_code == 404
    assert theirs.name not in response.text


def test_missing_channel_is_404(client, channel: Channel):
    assert client.get(f"/c/{channel.id + 5000}").status_code == 404


def test_signed_out_is_sent_to_login_and_back(channel: Channel):
    with TestClient(create_app()) as anonymous:
        response = anonymous.get(f"/c/{channel.id}", follow_redirects=False)
    assert response.status_code == 303
    # Back to the channel after signing in, which is what makes a shared hub link work.
    assert response.headers["location"] == f"/login?next=/c/{channel.id}"


# ---------------------------------------------------------------- the status word


def test_status_word_is_idle_with_nothing_happening():
    assert status_word([]) == IDLE
    assert status_word([Run(status=RunStatus.completed)]) == IDLE
    # A queued run is not producing: nothing is being produced, and the case where it
    # stays queued is the worker being down.
    assert status_word([Run(status=RunStatus.queued)]) == IDLE


def test_status_word_is_producing_while_a_run_runs():
    assert status_word([Run(status=RunStatus.completed),
                        Run(status=RunStatus.running)]) == PRODUCING


def test_status_word_is_waiting_at_a_gate():
    assert status_word([Run(status=RunStatus.completed),
                        Run(status=RunStatus.awaiting_approval)]) == WAITING


def test_producing_wins_over_waiting():
    """The dot describes the machine, and the machine is busy.

    The gate is not hidden by this: "waiting on you" is its own number on the page, and
    that test is below.
    """
    assert status_word([Run(status=RunStatus.awaiting_approval),
                        Run(status=RunStatus.running)]) == PRODUCING


@pytest.mark.parametrize(
    "status,word",
    [
        (RunStatus.running, PRODUCING),
        (RunStatus.awaiting_approval, WAITING),
        (RunStatus.completed, IDLE),
    ],
)
def test_the_page_prints_the_word(client, session: Session, channel: Channel, status, word):
    a_run(session, channel, status=status)

    body = page(client.get(f"/c/{channel.id}").text)
    assert f'class="state {word}"' in body


# ------------------------------------------------------------- the four numbers


@pytest.fixture
def counted(session: Session, channel: Channel, user: User) -> Channel:
    """Five runs on the channel under test, and one expensive run on another.

    Worked out by hand: 5 runs, 2 finished, 1 at a gate, 1 dead, 2 in flight, and
    40 + 60 + 25 + 0 + (30 − 10) = 145 credits. The 500 on the second channel is the
    trap — it belongs to the same account, so an unscoped sum picks it up and every
    figure still looks plausible.
    """
    a_run(session, channel, status=RunStatus.completed, spend=40)
    a_run(session, channel, status=RunStatus.completed, spend=60)
    a_run(session, channel, status=RunStatus.running, spend=25)
    a_run(session, channel, status=RunStatus.awaiting_approval)
    a_run(session, channel, status=RunStatus.failed, spend=30, refund=10)

    elsewhere = Channel(user_id=user.id, name="Other Channel", aspect_ratio="9:16")
    session.add(elsewhere)
    session.commit()
    a_run(session, elsewhere, status=RunStatus.completed, spend=500)
    return channel


def test_facts_match_the_hand_computed_fixture(counted: Channel, user: User):
    with SessionLocal() as read:
        channel = read.get(Channel, counted.id)
        runs = list(channel.runs)
        facts = hub_facts(read, read.get(User, user.id), channel, runs)

    assert facts["runs"] == 5
    assert facts["completed"] == 2
    assert facts["at_gate"] == 1
    assert facts["failed"] == 1
    assert facts["running"] == 1
    assert facts["in_flight"] == 2
    assert facts["finished_pct"] == 40
    # Net of the refund, and nothing from the other channel.
    assert facts["credits_spent"] == 145


def test_the_hub_prints_those_numbers(client, counted: Channel):
    body = page(client.get(f"/c/{counted.id}").text)
    assert "145" in body
    # The other channel's spend never appears, on the hub or in the total.
    assert "500" not in body
    assert "Other Channel" not in body
    # The gate tile earns its colour only when something is actually waiting.
    assert 'class="tile asks"' in body


def test_a_channel_with_no_runs_says_so_rather_than_zeroes(client, channel: Channel):
    body = page(client.get(f"/c/{channel.id}").text)
    assert "nothing asked for yet" in body
    # A percentage off no runs would be a "0% finished" verdict on a fresh channel.
    assert "% of what it started" not in body
    # And the spend tile's note is about a number that exists: "net of refunds" under a
    # zero is an accounting rule for a channel that has never been asked for anything.
    assert "nothing has cost anything yet" in body
    assert "net of refunds" not in body


def test_facts_are_not_taken_from_the_truncated_preview(
    session: Session, channel: Channel, user: User, client,
):
    """The hub shows eight runs and must still count all of them.

    The failure this prevents is the easy one: passing the preview list to the counter,
    so a busy channel reports "8 runs" forever.
    """
    for index in range(11):
        a_run(session, channel, status=RunStatus.completed, spend=1, topic=f"Run {index}")

    with SessionLocal() as read:
        facts = hub_facts(read, read.get(User, user.id), read.get(Channel, channel.id),
                          list(read.get(Channel, channel.id).runs))
    assert facts["runs"] == 11
    assert facts["credits_spent"] == 11

    body = page(client.get(f"/c/{channel.id}").text)
    assert "3 older runs" in body


# --------------------------------------------------------------- the runs view


def test_the_runs_view_lists_every_run_on_this_channel(client, counted: Channel):
    body = page(client.get(f"/c/{counted.id}/runs").text)
    assert ">runs</span>" in body
    assert body.count('<span class="status ') == 5


def test_the_runs_view_excludes_other_channels_runs(
    client, session: Session, channel: Channel, user: User,
):
    elsewhere = Channel(user_id=user.id, name="Other Channel", aspect_ratio="9:16")
    session.add(elsewhere)
    session.commit()
    a_run(session, channel, topic="Mine to see")
    a_run(session, elsewhere, topic="Not on this hub")

    body = page(client.get(f"/c/{channel.id}/runs").text)
    assert "Mine to see" in body
    assert "Not on this hub" not in body


# ------------------------------------------------------- the lane in the rail


def rail(body: str) -> str:
    """The shell around the page, which is where the Channels lane lives.

    The mirror of `page` above, cut at the same marker: the lane renders on every page
    in the app, so the assertions about it are about the half of the document the hub
    did not write.
    """
    marker = 'aria-label="Breadcrumb"'
    assert marker in body, "the hub rendered without its breadcrumb"
    return body.split(marker, 1)[0]


def test_the_lane_is_absent_until_there_is_a_channel(client, user: User):
    """No channels, no lane — not a lane header with nothing under it.

    The header is the only part that does not come from a loop, so this is the one
    empty state the lane can get wrong, and it is on every page of a new account.
    """
    body = client.get("/").text
    assert ">Channels</div>" not in body


def test_the_lane_marks_the_channel_whose_hub_is_open(
    client, session: Session, channel: Channel, user: User,
):
    """Exactly one entry is "here", and it is this channel's.

    The rail also lights the format tab on a channel page, and that alone reads as
    "you are in the long-form workspace" — an account-wide list of every channel,
    which is the one place this page exists to not send you.
    """
    elsewhere = Channel(user_id=user.id, name="Other Channel", aspect_ratio="9:16")
    session.add(elsewhere)
    session.commit()

    lane = rail(client.get(f"/c/{channel.id}").text)
    assert f'class="chan here" href="/c/{channel.id}"' in lane
    assert lane.count('aria-current="page"') == 1
    assert f'href="/c/{elsewhere.id}"' in lane

    # And nothing is marked on a page that is not a channel's.
    assert 'aria-current="page"' not in client.get("/analytics").text


@pytest.mark.parametrize(
    "status,word",
    [
        (RunStatus.running, PRODUCING),
        (RunStatus.awaiting_approval, WAITING),
        (RunStatus.completed, IDLE),
    ],
)
def test_the_lane_dot_and_the_page_word_are_one_fact(
    client, session: Session, channel: Channel, status, word,
):
    """The dot is named after the word, so the two cannot be given different colours.

    They were: the lane used the generic ok/warn pair, so a channel sitting at a gate
    had an amber dot in the rail while the hub eighteen inches to the right printed the
    same gate in violet, and a running one was green in the rail and mint on the page.
    Two hues for one state is the app claiming two different things at once.
    """
    a_run(session, channel, status=status)

    body = client.get(f"/c/{channel.id}").text
    assert f'class="dot dot-{word}"' in rail(body)
    assert f'class="state {word}"' in page(body)


def test_the_lane_orders_channels_the_same_way_on_every_page(
    client, session: Session, channel: Channel, user: User,
):
    """A fixed order, because after a day of use the lane is navigated by position.

    The query behind it had no ORDER BY. On SQLite that happens to come back in
    insertion order and on Postgres it is free not to — a sidebar whose entries move
    between two pages of the same app.
    """
    for name in ("Zulu", "Alpha", "Mike"):
        session.add(Channel(user_id=user.id, name=name))
    session.commit()

    lane = rail(client.get(f"/c/{channel.id}").text)
    seen = [lane.index(name) for name in ("Test Channel", "Zulu", "Alpha", "Mike")]
    assert seen == sorted(seen), "the lane is not in the order the channels were made"


def test_the_lane_dot_palette_is_scoped_to_the_rail(client, channel: Channel):
    """A page's own bare `.dot` must not be able to repaint a dot in the sidebar.

    `/runs/{id}/preview` styles a bare `.dot` for its player's stage marker, and its
    `{% block head %}` lands after app.css — so on that one page the Claude chip in the
    rail's foot came out grey while every other page in the app showed the same
    unconnected account in amber. The channel dots were already defended; the foot was
    not, and both are the rail reporting a live fact.
    """
    body = client.get(f"/c/{channel.id}").text
    for word in ("ok", "warn", "bad", "idle"):
        assert f".side .dot-{word}" in body, f"the rail's {word} dot is undefended"


def test_the_here_mark_is_not_the_hover_mark(client, channel: Channel):
    """Being in a channel and hovering one must not look the same.

    `.chan:hover` is `--raise-2`, and `.chan.here` was `--raise-2` and nothing else — so
    the entry under the cursor was indistinguishable from the channel you were actually
    in, and a four-channel rail gave two answers to "where am I". The rule that separates
    them is CSS, so what is pinned here is that the mark hover does not have is still on
    the element; the browser check is what proved it reads.
    """
    body = client.get(f"/c/{channel.id}").text
    assert "inset 2px 0 0 var(--accent)" in body


@pytest.mark.parametrize("dead,expected", [(1, "1 run died on"), (2, "2 runs died on")])
def test_the_dead_run_line_is_written_out_rather_than_run_s(
    client, session: Session, channel: Channel, dead, expected,
):
    """"run(s)" is a note a writer left themselves, on the one line read after a failure."""
    for _ in range(dead):
        a_run(session, channel, status=RunStatus.failed)

    body = page(client.get(f"/c/{channel.id}").text)
    assert expected in body
    assert "run(s)" not in body


def test_one_older_run_is_not_pluralised_either(client, session: Session, channel: Channel):
    for index in range(HUB_RUNS + 1):
        a_run(session, channel, topic=f"Run {index}")

    body = page(client.get(f"/c/{channel.id}").text)
    assert ">1 older run</a>" in body


def test_a_channel_name_with_no_break_in_it_cannot_widen_the_page(
    client, session: Session, user: User,
):
    """45 characters and nowhere to wrap, which is a real channel name.

    At 430px that name is wider than the viewport in 24px type, and an `h1` that cannot
    break does not overflow by itself — it widens `main`, and then every row under it
    scrolls sideways. The rule that fixes it is CSS, so the only honest check is a
    browser; what is pinned here is that the rule is still on the elements that carry
    user input, because deleting it fails nothing else.
    """
    unbroken = Channel(user_id=user.id, name="AbandonedInfrastructureAndForgottenEngineering")
    session.add(unbroken)
    session.commit()

    body = client.get(f"/c/{unbroken.id}").text
    assert unbroken.name in page(body)
    assert "overflow-wrap: anywhere" in body
