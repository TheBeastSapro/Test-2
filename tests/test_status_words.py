"""What the interface calls a status, and which decision a waiting run is holding.

Two small things, both found by starting the app and looking at it rather than by
reading the templates.

`awaiting_approval` was printed into three tables verbatim — an enum value, underscore
and all, which is an internal identifier appearing in the product. And the "waiting on
you" panel showed run number, channel and topic, so a channel iterating on one subject
produced five visually identical cards: the surface the whole gated design exists for,
saying nothing except that something is waiting.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from forgecast.api.main import create_app
from forgecast.api.routes_web import STATUS_WORDS, said
from forgecast.auth import create_access_token
from forgecast.models import Channel, Node, NodeStatus, Run, RunStatus, User


@pytest.fixture
def client(user: User):
    with TestClient(create_app()) as test_client:
        test_client.headers["Authorization"] = f"Bearer {create_access_token(user)}"
        yield test_client


# ------------------------------------------------------------------- the words


def test_the_status_a_person_reads_is_not_the_one_the_engine_branches_on():
    assert said(RunStatus.awaiting_approval) == "waiting on you"
    assert said(NodeStatus.pending) == "not started"
    # Takes the value as well as the enum, because templates hold both.
    assert said("awaiting_approval") == "waiting on you"


def test_the_words_already_in_english_are_left_alone():
    """A table where three statuses are re-worded and three are not reads as two
    vocabularies. These are already what a person would say."""
    for value in ("completed", "running", "failed"):
        assert said(value) == value
        assert value not in STATUS_WORDS


def test_a_status_this_does_not_know_is_still_printed():
    """Dropping it would be worse than printing it plainly — a status nobody mapped is
    still a status, and a blank cell is a bug that looks like a design."""
    assert said("some_new_state") == "some new state"
    assert said(None) == ""


def test_the_run_page_and_its_live_update_share_one_vocabulary(
        client: TestClient, session: Session, user: User, channel: Channel):
    """The page repaints its badges from a stream. A second copy of these words in
    JavaScript is how a page renders "waiting on you" and then replaces it with
    "awaiting_approval" a few seconds later — which is worse than never translating it,
    because the label changes under the reader."""
    run = Run(user_id=user.id, channel_id=channel.id, topic="T",
              status=RunStatus.awaiting_approval)
    session.add(run)
    session.flush()
    session.add(Node(run_id=run.id, key="brief", type="brief",
                     title="Create production brief", requires_approval=True,
                     status=NodeStatus.awaiting_approval))
    session.commit()

    page = client.get(f"/runs/{run.id}").text

    assert "const STATUS_WORDS = " in page
    assert '"awaiting_approval": "waiting on you"' in page
    # The raw value still rides along as the CSS hook and the JS comparison key.
    assert 'class="status awaiting_approval"' in page
    assert ">waiting on you<" in page


# ---------------------------------------------------------------- which gate


@pytest.mark.asyncio
async def test_a_waiting_run_says_which_decision_it_is_holding(
        session: Session, user: User, channel: Channel):
    """Five runs on one channel about one topic rendered five identical cards. What
    differs between them is the gate, so that is what the panel has to carry."""
    from forgecast.agent.studio import Studio
    from forgecast.db import SessionLocal

    for title, key in (("Create production brief", "brief"),
                       ("Write full script", "script")):
        run = Run(user_id=user.id, channel_id=channel.id, topic="One topic",
                  status=RunStatus.awaiting_approval)
        session.add(run)
        session.flush()
        session.add(Node(run_id=run.id, key=key, type=key, title=title,
                         requires_approval=True,
                         status=NodeStatus.awaiting_approval))
    session.commit()

    status = Studio(SessionLocal, user_id=user.id).status()

    gates = {row["gate"] for row in status["runs_waiting_on_you"]}
    assert gates == {"Create production brief", "Write full script"}
    assert all(row["gate_key"] for row in status["runs_waiting_on_you"])


@pytest.mark.asyncio
async def test_a_run_holding_several_gates_names_the_first(
        session: Session, user: User, channel: Channel):
    """The pipeline fans out, so a run can sit at more than one. The earliest is the one
    to answer, and a panel that named an arbitrary one would send somebody to a screen
    they cannot act on yet."""
    from forgecast.agent.studio import Studio
    from forgecast.db import SessionLocal

    run = Run(user_id=user.id, channel_id=channel.id, topic="T",
              status=RunStatus.awaiting_approval)
    session.add(run)
    session.flush()
    session.add(Node(run_id=run.id, key="hook", type="hook", title="Approve the hook",
                     requires_approval=True, status=NodeStatus.awaiting_approval))
    session.add(Node(run_id=run.id, key="sample", type="sample",
                     title="Approve the sample shot", requires_approval=True,
                     status=NodeStatus.awaiting_approval))
    session.commit()

    status = Studio(SessionLocal, user_id=user.id).status()

    assert [row["gate"] for row in status["runs_waiting_on_you"]] == ["Approve the hook"]


@pytest.mark.asyncio
async def test_a_run_waiting_with_no_open_gate_says_nothing_rather_than_guessing(
        session: Session, user: User, channel: Channel):
    """A real state — a run interrupted mid-transition. Naming a gate it is not at
    would send somebody to the wrong screen, so the card falls back to its own wording
    and the run is still listed."""
    from forgecast.agent.studio import Studio
    from forgecast.db import SessionLocal

    session.add(Run(user_id=user.id, channel_id=channel.id, topic="T",
                    status=RunStatus.awaiting_approval))
    session.commit()

    status = Studio(SessionLocal, user_id=user.id).status()

    assert len(status["runs_waiting_on_you"]) == 1
    assert status["runs_waiting_on_you"][0]["gate"] == ""


@pytest.mark.asyncio
async def test_the_gates_are_read_in_one_query_not_one_per_run(
        session: Session, user: User, channel: Channel):
    """This panel is drawn on every page load. One query per waiting run turns a busy
    account's dashboard into a hundred round trips."""
    import inspect

    from forgecast.agent.studio import Studio

    source = inspect.getsource(Studio.status)
    assert "Node.run_id.in_(stalled)" in source


# ------------------------------------------------------- the rest of the identifiers
#
# Same defect, two more places, both found by opening the page. The run header printed
# `faceless_longform` in monospace beside a heading in plain English, and Analytics —
# a page whose whole argument is that it prints honest numbers — labelled its stages
# `voice_casting`, `final_review`, `broll_plan`, and said "Died at voice_casting x1".


def test_a_pipeline_is_named_the_way_the_rest_of_the_app_names_it():
    """`PIPELINE_META` has carried a title for every shipped pipeline since it was
    written, and the activity log two panels down was already using it."""
    from forgecast.api.routes_web import pipeline_title

    assert pipeline_title("faceless_longform") == "Faceless long-form video"
    assert pipeline_title("something_nobody_shipped") == "something nobody shipped"


def test_stage_names_come_from_the_pipelines_rather_than_a_second_table():
    """A separate list of stage names drifts the first time a node is renamed, and the
    page is then confidently wrong rather than merely ugly."""
    from forgecast.graph.pipelines import get_pipeline, stage_title, stage_titles

    assert stage_title("voice_casting") == "Cast the voice"
    assert stage_title("broll_plan") == "Plan B-roll shots"
    assert stage_title("never_shipped") == "never shipped"

    # Every title here is one a pipeline actually gave that node, not a paraphrase.
    spec = get_pipeline("faceless_longform")
    for node in spec.nodes:
        if node.type in stage_titles():
            assert stage_titles()[node.type] in {
                other.title for other in spec.nodes if other.type == node.type}


def test_analytics_labels_its_stages_and_its_deaths_in_english(
        client: TestClient, session: Session, user: User, channel: Channel):
    """The page argues that it only prints numbers it can stand behind. Labelling the
    rows with engine identifiers undercuts that in the first column."""
    from forgecast.models import NodeStatus

    run = Run(user_id=user.id, channel_id=channel.id, topic="T",
              status=RunStatus.failed)
    session.add(run)
    session.flush()
    session.add(Node(run_id=run.id, key="voice_casting", type="voice_casting",
                     title="Cast the voice", status=NodeStatus.failed))
    session.commit()

    page = client.get("/analytics").text

    assert "voice_casting" not in page
    assert "Cast the voice" in page
