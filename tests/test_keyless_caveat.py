"""Where the keyless YouTube read does not work, said on the pages that offer it.

`keyless` reads the public channel page with yt-dlp, and YouTube answers a datacentre
address with "Sign in to confirm you're not a bot". The path is present, installed,
correct, and refused — so on every hosted install three surfaces offered a fetch that
cannot happen, and the operator found out by getting nothing back and going to check
their link, which is the one thing that was fine.

The sentence lives in `research/keyless`, the module that owns the path. Three copies of
a caveat is how two of them come to say something the third has stopped saying.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from forgecast.api.main import create_app
from forgecast.auth import create_access_token
from forgecast.models import User
from forgecast.research import keyless


@pytest.fixture
def client(user: User):
    with TestClient(create_app()) as test_client:
        test_client.headers["Authorization"] = f"Bearer {create_access_token(user)}"
        yield test_client


def test_the_caveat_is_a_condition_and_not_a_prediction():
    """This cannot know where it is running — the same build reads fine on a laptop —
    so it says what to do if nothing comes back rather than announcing that nothing
    will. And it names both fixes, so the answer is on the page that failed."""
    note = keyless.BLOCKED_NOTE

    assert "if nothing comes back" in note
    assert "NexLev" in note and "YouTube API key" in note
    # Not phrased as a certainty about this machine.
    assert "usually" in note


def test_the_research_desk_says_it_under_the_box_that_offers_the_fetch(
        client: TestClient, monkeypatch):
    """The desk's own copy says "No API key needed", which is true about the capability
    and wrong about a hosted machine."""
    monkeypatch.setattr(keyless, "available", lambda: (True, ""))

    page = client.get("/research").text

    assert "No API key needed" in page
    assert keyless.BLOCKED_NOTE in page


def test_the_styles_page_says_it_under_the_link_box_only(client: TestClient):
    """Uploading files works on any install; only the link path goes through the read
    YouTube refuses. Putting the caveat at the top of the page would warn about a
    limitation the upload box does not have."""
    page = client.get("/styles").text

    assert keyless.BLOCKED_NOTE in page
    marker = page.index(keyless.BLOCKED_NOTE)
    assert page.index('id="links"') < marker, "the caveat should follow the link box"


def test_the_agent_gives_the_same_answer_as_the_pages(monkeypatch):
    """A person who asks the agent and a person who reads the page must not be told two
    different things about the same failure."""
    from forgecast.agent import connectors, studio

    monkeypatch.setattr(connectors.Store, "load",
                        classmethod(lambda cls, path=None: connectors.Store(path=None)))
    monkeypatch.setattr(connectors.Store, "listing",
                        lambda self, **kw: [{"key": "nexlev", "connected": False}])

    assert keyless.BLOCKED_NOTE in studio._other_way_to_read_a_channel()


def test_a_missing_yt_dlp_still_reports_the_install_fix_instead(
        client: TestClient, monkeypatch):
    """Two different failures. yt-dlp absent is fixed by installing it; yt-dlp present
    and refused is fixed by a key or a connector — and telling somebody to install
    something they already have is the same dead end in the other direction."""
    monkeypatch.setattr(keyless, "available", lambda: (False, "yt-dlp is not installed"))

    page = client.get("/research").text

    assert "yt-dlp is not installed" in page
    assert keyless.BLOCKED_NOTE not in page


def test_no_tool_name_is_shown_where_a_sentence_belongs(client: TestClient):
    """`decide_gate` is an identifier from `agent/tools.py`, and it was printed into a
    caveat on Settings. A reader there has no way to know what it names; what they need
    is that this backend cannot approve gates, which is a sentence about the product."""
    page = client.get("/settings").text

    assert "decide_gate" not in page
    assert "never approve a gate for you" in page


# ------------------------------------------------------------ what can fetch comments


def _store(monkeypatch, *, connected: bool):
    from forgecast.agent import connectors

    monkeypatch.setattr(connectors.Store, "load",
                        classmethod(lambda cls, path=None: connectors.Store(path=None)))
    monkeypatch.setattr(connectors.Store, "listing",
                        lambda self, **kw: [{"key": "nexlev", "connected": connected}])


def test_the_comment_miner_says_what_can_actually_fetch_them(monkeypatch):
    """The audience backlog is this format's growth loop — the reference asks for
    requests in its outro and the requests become videos — and nothing in this app can
    fetch a comment. "Fetch them first" is correct and leaves the agent to work out how.

    yt-dlp is not a fallback here even where it is not blocked: comments are not on the
    listing page it reads.
    """
    from forgecast.agent import studio

    _store(monkeypatch, connected=False)

    said = studio._how_to_fetch_comments()

    assert "not on the page yt-dlp reads" in said
    assert "NexLev" in said


def test_when_nexlev_is_linked_the_answer_is_use_it(monkeypatch):
    from forgecast.agent import studio

    _store(monkeypatch, connected=True)

    said = studio._how_to_fetch_comments()

    assert "is connected" in said
    assert "Connect NexLev in Settings" not in said


def test_the_connector_lookup_is_one_function_not_one_per_caller(monkeypatch):
    """Three tools change their suggestion on this. A copy per caller is a copy that
    keeps saying "connect NexLev" after somebody has."""
    import inspect

    from forgecast.agent import studio

    _store(monkeypatch, connected=True)
    assert studio._connected("nexlev") is True
    assert studio._connected("nothing-by-that-name") is None

    # Both callers go through it rather than reading the store themselves.
    for helper in (studio._how_to_fetch_comments, studio._other_way_to_read_a_channel):
        source = inspect.getsource(helper)
        assert "_connected(" in source
        assert "Store.load" not in source
