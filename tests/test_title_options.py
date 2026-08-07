"""Choosing the title, at the gate that comes before anything is written.

The title is decided at the brief, which is already the first stage and already a
decision gate — but it offered exactly one, so the gate could only be accepted. There
was nothing to compare against, which made "approve" and "I did not think about the
title" the same click, and left no way to tell them apart afterwards.

These tests cover the two halves that can silently stop working: the normaliser, which
has to survive a model answering in a shape nobody asked for, and the write-back, which
has to land on the key the script stage actually reads. A picker that renders and does
not change the run is worse than no picker.
"""

from __future__ import annotations

from forgecast.nodes.content import MAX_TITLE_OPTIONS, _title_options


def test_the_recommendation_is_always_on_the_ballot_and_first():
    """A default that is not among the options cannot be compared against them, and an
    option nobody can see is not on offer."""
    options = _title_options({
        "working_title": "Why deep-sea cables keep breaking",
        "title_options": [
            {"title": "The Real Reason Cables Snap", "device": "single cause", "why": "x"},
        ],
    })

    assert options[0]["title"] == "Why deep-sea cables keep breaking"
    assert [o["title"] for o in options].count("Why deep-sea cables keep breaking") == 1


def test_the_recommendation_is_promoted_rather_than_duplicated():
    """The usual case: the model lists its recommendation among the options. It should
    move to the top, not appear twice."""
    options = _title_options({
        "working_title": "The Real Reason Cables Snap",
        "title_options": [
            {"title": "What Nobody Tells You", "device": "withheld", "why": "a"},
            {"title": "The Real Reason Cables Snap", "device": "single cause", "why": "b"},
        ],
    })

    assert [o["title"] for o in options] == [
        "The Real Reason Cables Snap", "What Nobody Tells You",
    ]
    assert options[0]["why"] == "b", "promoting must keep the option's own reasoning"


def test_bare_strings_still_produce_a_pickable_list():
    """The gate is the only place a title is chosen, so a model that answers with
    strings instead of objects must not render an empty chooser."""
    options = _title_options({
        "working_title": "One",
        "title_options": ["One", "Two", "Three"],
    })

    assert [o["title"] for o in options] == ["One", "Two", "Three"]
    assert all(set(o) == {"title", "device", "why"} for o in options)


def test_junk_entries_are_dropped_rather_than_rendered_blank():
    options = _title_options({
        "working_title": "Real",
        "title_options": [None, 7, {"device": "no title here"}, {"title": "  "}, "Other"],
    })

    assert [o["title"] for o in options] == ["Real", "Other"]


def test_duplicates_collapse_case_insensitively():
    """Two rows with the same words are one option wearing two hats — and a radio
    group with two identical labels cannot report which was picked."""
    options = _title_options({
        "working_title": "Deep Sea Cables",
        "title_options": ["deep sea cables", "DEEP SEA CABLES", "Something Else"],
    })

    assert [o["title"] for o in options] == ["Deep Sea Cables", "Something Else"]


def test_the_list_is_capped():
    """Past a handful the gate stops being a choice and becomes a reading task, and
    the operator picks the first one — which is what a single title already did."""
    options = _title_options({
        "working_title": "T0",
        "title_options": [f"T{i}" for i in range(20)],
    })

    assert len(options) == MAX_TITLE_OPTIONS


def test_no_options_at_all_still_offers_the_working_title():
    options = _title_options({"working_title": "Only This One"})

    assert [o["title"] for o in options] == ["Only This One"]


def test_a_brief_with_nothing_usable_offers_nothing_rather_than_a_blank_row():
    """The template falls back to plain text when the list is empty. An empty string
    rendered as a radio option would be a choice that erases the title."""
    assert _title_options({}) == []
    assert _title_options({"working_title": "   "}) == []


# ── the write-back ──────────────────────────────────────────────────────────────
#
# A picker that renders and does not change the run is worse than no picker: it looks
# like a decision was taken. The chosen title has to land on `working_title`, because
# that is the key `script_node` reads — anywhere else and the choice is recorded next
# to the run rather than in it.

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from forgecast.db import SessionLocal
from forgecast.graph.engine import create_run
from forgecast.models import Channel, Node, NodeStatus


async def _run_to_the_brief_gate(session: Session, channel: Channel) -> int:
    from forgecast.graph.engine import GraphEngine

    run = create_run(session, channel=channel, topic="Why deep-sea cables keep breaking",
                     pipeline="faceless_shorts", options={"target_seconds": 20})
    run_id = run.id
    session.commit()
    await GraphEngine(SessionLocal, worker_id="test", concurrency=2).advance(run_id)
    return run_id


def _brief(run_id: int) -> Node:
    with SessionLocal() as check:
        return check.execute(
            select(Node).where(Node.run_id == run_id, Node.key == "brief")
        ).scalar_one()


async def test_the_brief_gate_offers_more_than_one_title(session: Session, channel: Channel):
    run_id = await _run_to_the_brief_gate(session, channel)
    node = _brief(run_id)

    assert node.status is NodeStatus.awaiting_approval
    options = (node.output or {}).get("title_options") or []
    assert len(options) > 1, "a gate with one option is a gate you can only accept"
    assert len({o["title"] for o in options}) == len(options)
    # The pre-selected row is what a plain approve posts, so it has to be the title
    # the run would otherwise have used.
    assert options[0]["title"] == node.output["working_title"]


@pytest.mark.parametrize("posted,expected", [
    ("The Real Reason Cables Snap", "The Real Reason Cables Snap"),
    ("", None),                       # nothing posted — the working title stands
])
async def test_the_chosen_title_reaches_the_script(
    session: Session, channel: Channel, posted: str, expected: str | None,
):
    from fastapi.testclient import TestClient

    from forgecast.api.main import app

    run_id = await _run_to_the_brief_gate(session, channel)
    before = _brief(run_id).output["working_title"]

    with TestClient(app) as client:
        signed_in = client.post(
            "/login",
            data={"email": "tester@example.com", "password": "supersecret",
                  "action": "login"},
            follow_redirects=True,
        )
        assert signed_in.status_code == 200
        posted_response = client.post(
            f"/runs/{run_id}/gate/brief",
            data={"decision": "approve", "chosen_title": posted},
            follow_redirects=True,
        )
        assert posted_response.status_code == 200, posted_response.text[:300]

    after = _brief(run_id).output["working_title"]
    assert after == (expected if expected is not None else before)
