"""Naming the canon wiki, from the page an operator actually opens.

The lane behind this shipped with no way to reach it: a run fetched its entities off a
wiki only when a param or a channel field named one, and nothing in the app ever asked
the question. A capability with no control is the same defect as a module with no
caller, arriving one layer out.

The interesting rule here is the one that differs from every other setter on this page.
Everywhere else, an unavailable choice is *stored* and the downgrade reported — the run
still produces a video and the operator needs to know what they got. A wrong wiki does
not downgrade. It silently fetches nothing, on every run, for ever, and the only symptom
is a video that generated its creatures. So this one is verified before it is stored.

The two tests that reach the network are marked; the rest do not.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from forgecast.agent.studio import Studio
from forgecast.api.main import create_app
from forgecast.auth import create_access_token
from forgecast.models import Channel, User
from forgecast.research import canon


@pytest.fixture
def client(user: User):
    with TestClient(create_app()) as test_client:
        test_client.headers["Authorization"] = f"Bearer {create_access_token(user)}"
        yield test_client


def _studio(user: User, monkeypatch, *, exists: bool = True):
    """A Studio whose wiki probe answers without a network."""
    from forgecast.db import SessionLocal

    async def probe(name, *, timeout=20.0):
        return canon.Wiki(name=name, title="DOORS Wiki", articles=321,
                          url=f"https://{name}.fandom.com") if exists else None

    monkeypatch.setattr(canon, "_probe", probe)
    return Studio(SessionLocal, user_id=user.id)


# --------------------------------------------------------------- verified, then stored


@pytest.mark.asyncio
async def test_a_wiki_that_answers_is_stored_with_what_it_is(
        session: Session, user: User, channel: Channel, monkeypatch):
    result = await _studio(user, monkeypatch).set_canon_wiki(channel.id, "doors-game")

    assert result["canon_wiki"] == "doors-game"
    assert "321 articles" in result["note"]
    session.refresh(channel)
    assert channel.style_profile["canon_wiki"] == "doors-game"


@pytest.mark.asyncio
async def test_a_wiki_that_does_not_exist_is_refused_rather_than_stored(
        session: Session, user: User, channel: Channel, monkeypatch):
    """The one setting on this page that refuses.

    Stored, it would fetch nothing on every run for ever, and the only symptom would be
    a video that generated its creatures — which is the exact substitution this lane
    exists to prevent, arriving through a typo.
    """
    result = await _studio(user, monkeypatch, exists=False).set_canon_wiki(
        channel.id, "doorsgame")

    assert "no wiki at doorsgame.fandom.com" in result["error"]
    session.refresh(channel)
    assert "canon_wiki" not in (channel.style_profile or {})


@pytest.mark.asyncio
async def test_a_pasted_url_is_named_as_the_mistake_it_is(
        session: Session, user: User, channel: Channel, monkeypatch):
    """Pasting the address is the obvious thing to do and it is nearly right. Saying
    which part of it to keep costs one sentence and saves the guess."""
    result = await _studio(user, monkeypatch).set_canon_wiki(
        channel.id, "https://doors-game.fandom.com/wiki/Seek")

    assert "is not a wiki name" in result["error"]
    assert "doors-game" in result["error"]


@pytest.mark.asyncio
async def test_the_suffix_is_accepted_because_people_will_paste_it(
        session: Session, user: User, channel: Channel, monkeypatch):
    result = await _studio(user, monkeypatch).set_canon_wiki(
        channel.id, "  DOORS-GAME.fandom.com  ")

    assert result["canon_wiki"] == "doors-game"


@pytest.mark.asyncio
async def test_blank_clears_it_and_is_the_way_back(
        session: Session, user: User, channel: Channel, monkeypatch):
    """Off is a real state and has to be reachable, or the first typo is permanent."""
    studio = _studio(user, monkeypatch)
    await studio.set_canon_wiki(channel.id, "doors-game")

    result = await studio.set_canon_wiki(channel.id, "")

    assert result["canon_wiki"] == ""
    session.refresh(channel)
    assert "canon_wiki" not in (channel.style_profile or {})


@pytest.mark.asyncio
async def test_setting_it_leaves_the_rest_of_the_profile_alone(
        session: Session, user: User, channel: Channel, monkeypatch):
    """A targeted setter, for the reason `set_motion_backend` records: writing the whole
    profile to change one key is how a channel's learned render spec gets wiped by a
    caller that only meant to name a wiki."""
    await _studio(user, monkeypatch).set_canon_wiki(channel.id, "doors-game")

    session.refresh(channel)
    assert channel.style_profile["tone"] == "calm and precise"


# ------------------------------------------------------------------------ the page


def test_the_page_carries_the_control_and_the_rights_warning(
        client: TestClient, channel: Channel):
    page = client.get(f"/c/{channel.id}").text

    assert "Canon wiki" in page
    assert f'action="/c/{channel.id}/canon-wiki"' in page
    # Rights are the part this cannot answer, so the page has to say so rather than
    # letting a green "Saved." read as clearance to publish.
    assert "not stated" in page


def test_a_bad_wiki_comes_back_on_the_page_and_keeps_the_old_value(
        client: TestClient, channel: Channel, session: Session, monkeypatch):
    """A 400 with a JSON body is a dead end for somebody who just wants to try
    `doors-game` instead of `doors`."""
    async def probe(name, *, timeout=20.0):
        return (canon.Wiki(name=name, title="DOORS Wiki", articles=321)
                if name == "doors-game" else None)

    monkeypatch.setattr(canon, "_probe", probe)
    client.post(f"/c/{channel.id}/canon-wiki", data={"canon_wiki": "doors-game"})

    landed = client.post(f"/c/{channel.id}/canon-wiki", data={"canon_wiki": "nope123"})

    assert landed.status_code == 200
    assert "no wiki at nope123.fandom.com" in landed.text
    assert "doors-game.fandom.com" in landed.text   # the good one is still set


# ------------------------------------------------- what to do when the name is wrong


class _Search:
    """A search provider that returns fandom links, as Tavily and Brave do."""

    name = "stub-search"

    def __init__(self, urls):
        self.urls = urls
        self.asked: list[str] = []

    async def search(self, query):
        self.asked.append(query)
        return [{"url": url, "title": url} for url in self.urls]


@pytest.mark.asyncio
async def test_a_wrong_name_offers_wikis_that_do_exist(
        session: Session, user: User, channel: Channel, monkeypatch):
    """Discovery belongs on the failure, not on a button.

    A "find my wiki" control is dead on a fresh install — Fandom's own cross-wiki
    search sits behind a bot check, so this needs a search vendor — and the moment
    somebody is stuck is the moment their guess just came back empty.
    """
    from forgecast.providers import search as search_module

    finder = _Search(["https://doors-game.fandom.com/wiki/Seek",
                      "https://community.fandom.com/wiki/Help"])
    monkeypatch.setattr(search_module, "provider_for", lambda keys: finder)

    async def probe(name, *, timeout=20.0):
        return (canon.Wiki(name=name, title="DOORS Wiki", articles=321)
                if name == "doors-game" else None)

    monkeypatch.setattr(canon, "_probe", probe)

    from forgecast.db import SessionLocal
    result = await Studio(SessionLocal, user_id=user.id).set_canon_wiki(
        channel.id, "doorsgame")

    assert "no wiki at doorsgame.fandom.com" in result["error"]
    assert "doors-game (DOORS Wiki, 321 articles)" in result["error"]
    # Every suggestion was read out of a URL the search returned, never constructed —
    # and fandom's own plumbing is not offered as a wiki about anything.
    assert "community" not in result["error"]
    session.refresh(channel)
    assert "canon_wiki" not in (channel.style_profile or {})


@pytest.mark.asyncio
async def test_without_a_search_vendor_it_says_how_to_find_it_by_hand(
        session: Session, user: User, channel: Channel, monkeypatch):
    """The manual route works on every install, so it is always the last sentence."""
    from forgecast.providers import search as search_module

    monkeypatch.setattr(search_module, "provider_for", lambda keys: _Search([]))

    async def probe(name, *, timeout=20.0):
        return None

    monkeypatch.setattr(canon, "_probe", probe)

    from forgecast.db import SessionLocal
    result = await Studio(SessionLocal, user_id=user.id).set_canon_wiki(
        channel.id, "doorsgame")

    assert "copy the part of the address before .fandom.com" in result["error"]


# ------------------------------------------------- when a channel cannot be read here


def test_a_channel_that_cannot_be_read_names_the_actual_cause(monkeypatch):
    """The failure is almost never the operator's link.

    Without a YouTube API key the read falls back to yt-dlp, and YouTube blocks that
    from datacentre addresses outright — so the same link that works on a laptop fails
    on every hosted install. A message saying only "I could not read that channel"
    sends somebody to check the URL, which is the one thing that is fine.
    """
    from forgecast.agent import connectors, studio

    monkeypatch.setattr(connectors.Store, "load",
                        classmethod(lambda cls, path=None: connectors.Store(path=None)))
    monkeypatch.setattr(connectors.Store, "listing",
                        lambda self, **kw: [{"key": "nexlev", "connected": False}])

    said = studio._other_way_to_read_a_channel()

    assert "yt-dlp" in said and "datacentre" in said
    assert "NexLev" in said


def test_when_nexlev_is_already_connected_it_says_to_use_it(monkeypatch):
    """Telling somebody to connect a thing they already connected is its own dead end —
    and the agent holding those tools should reach for them rather than reporting a
    failure it can route around."""
    from forgecast.agent import connectors, studio

    monkeypatch.setattr(connectors.Store, "load",
                        classmethod(lambda cls, path=None: connectors.Store(path=None)))
    monkeypatch.setattr(connectors.Store, "listing",
                        lambda self, **kw: [{"key": "nexlev", "connected": True}])

    said = studio._other_way_to_read_a_channel()

    assert "is connected" in said
    assert "Settings" not in said
