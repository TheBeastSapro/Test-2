"""Reading a video somebody hands you, reachable from the application.

`forgecast/ingest`, `forgecast/edit` and `forgecast/layers` were 1,267 lines with their
own tests and **no importer anywhere in the tree** — no route, no template, no agent
tool, no CLI subcommand. A capability that works perfectly and cannot be reached from
the application is indistinguishable from one that does not exist, and this one was
reported as missing. It was not missing; it had no door.

These tests are about the door. `tests/test_ingest.py`, `tests/test_edit_plan.py` and
`tests/test_layers.py` already exercise the rooms behind it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from forgecast.agent.studio import Studio
from forgecast.api.main import create_app

# Every path the desk accepts, so a write endpoint left open is a failure here rather
# than a discovery. A local app still binds a port, and "measure this file" that anyone
# who can reach it may call is a file-existence oracle for the whole disk.
ENDPOINTS = (
    ("get", "/api/edit"),
    ("get", "/api/edit/sources"),
    ("post", "/api/edit/read"),
    ("post", "/api/edit/plan"),
    ("get", "/api/edit/plans"),
    ("get", "/api/edit/plans/anything"),
    ("post", "/api/edit/plans/anything/decision"),
    ("post", "/api/edit/layers"),
)


def _clip(path: Path, *, seconds: float = 2.0) -> Path:
    """A real file with a real silence in the middle of it.

    Built rather than fixtured for the same reason `test_ingest.py` builds one: the
    whole point of the packages behind this desk is that they measure, and a test
    against pre-computed numbers would pass against a module that invented them. Two
    pieces, one with sound and one without, so there is something for the plan to
    decide about rather than a file that is silent throughout.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    parts = []
    for index, source in enumerate((f"sine=frequency=440:duration={seconds}",
                                    f"anullsrc=duration={seconds}")):
        piece = path.parent / f"{path.stem}-part{index}.mp4"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", f"color=c=red:s=320x180:d={seconds}:r=24",
             "-f", "lavfi", "-i", source,
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
             "-y", str(piece)],
            check=True, capture_output=True)
        parts.append(piece)

    listing = path.parent / f"{path.stem}-list.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", str(listing), "-c", "copy", "-y", str(path)],
        check=True, capture_output=True)
    return path


@pytest.fixture
def client(user):
    with TestClient(create_app()) as test_client:
        token = test_client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "supersecret"},
        ).json()["access_token"]
        test_client.headers["Authorization"] = f"Bearer {token}"
        yield test_client


@pytest.fixture(autouse=True)
def no_transcription(monkeypatch):
    """The transcript reading, off.

    Loading it downloads a model on first use, and a test suite that reaches for the
    network is a test suite that fails on an aeroplane. Turning it off also exercises
    the behaviour that matters most here — a reading that could not be taken is *named*
    rather than silently dropped, so an operator can see the plan was built without it.
    """
    from forgecast.ingest import transcript

    monkeypatch.setattr(transcript, "available",
                        lambda: (False, "transcription needs the video editing tools"))


# ------------------------------------------------------------------------ the door


def test_every_endpoint_on_the_desk_needs_an_account():
    with TestClient(create_app()) as anon:
        for method, path in ENDPOINTS:
            answered = (anon.post(path, json={}) if method == "post"
                        else anon.get(path))
            assert answered.status_code == 401, f"{method.upper()} {path} is open"


def test_what_can_be_measured_is_answerable_before_a_file_arrives(client):
    """The question that has to be answerable first.

    Dropping in a two-gigabyte video and being told twenty seconds later that a reader
    is absent is the shape of failure the ingest package refuses to have.
    """
    body = client.get("/api/edit").json()
    assert "probe" in body["can"] or any(
        row["reading"] == "probe" for row in body["cannot"])
    assert body["edit_extra"]["key"] == "edit"
    assert body["edit_extra"]["megabytes"] > 0


def test_a_toolset_that_is_absent_is_offered_as_an_install_not_as_homework(client,
                                                                          monkeypatch):
    """The app installs its own tools. Being handed a command to go and run instead was
    reported as a defect here once already, for a CLI that was never being installed."""
    from forgecast.ingest import shots

    monkeypatch.setattr(shots, "available",
                        lambda: (False, "shot detection needs the video editing tools"))

    body = client.get("/api/edit").json()
    assert [row for row in body["cannot"] if row["reading"] == "shots"]
    assert body["install"], "an absent toolset with no offer to install it"
    assert "pip install" not in body["install"]
    assert "/api/setup/extras/edit" in body["install"]


def test_the_uploader_is_the_one_the_chat_already_uses(client, storage_dir):
    """A second uploader would be a second size limit, a second sanitiser and a second
    folder to keep the agent's sandbox in step with."""
    made = _clip(storage_dir / "upload-me.mp4")
    with open(made, "rb") as handle:
        saved = client.post("/api/agent/attach",
                            files={"file": ("upload-me.mp4", handle, "video/mp4")})
    assert saved.status_code == 200
    landed = Path(saved.json()["path"])

    listing = client.get("/api/edit/sources").json()
    assert listing["upload"] == "POST /api/agent/attach"
    assert landed.name in [row["name"] for row in listing["sources"]]
    landed.unlink(missing_ok=True)


def test_a_file_outside_the_install_is_refused_and_says_how_to_supply_one(client):
    """Everything here is reachable over HTTP by a signed-in account, and a reader that
    accepts any absolute path answers "does this exist" for the whole disk."""
    answered = client.post("/api/edit/read", json={"path": "/etc/hostname"})
    assert answered.status_code == 200
    body = answered.json()
    assert body["ok"] is False
    assert "outside this install" in body["error"]
    assert "attach" in body["error"].lower()


# ------------------------------------------------------------------- measure, decide


def test_a_supplied_video_is_measured_and_what_was_not_read_is_named(client,
                                                                    storage_dir):
    made = _clip(storage_dir / "supplied.mp4")
    body = client.post("/api/edit/read", json={"path": str(made)}).json()

    assert body["ok"] is True
    assert body["seconds"] > 0
    assert body["frame"] == "320x180"
    # The transcript is off in this suite, and that is reported rather than left to be
    # inferred from an empty list — an edit built without one is a different edit.
    assert any("transcript" in item for item in body["missing"])


def test_the_plan_is_written_down_and_nothing_is_cut(client, storage_dir):
    """The whole design of `edit/plan.py`. A plan costs nothing to produce, nothing to
    change and nothing to throw away, and it fixes every expensive decision after it."""
    made = _clip(storage_dir / "to-tighten.mp4")
    body = client.post("/api/edit/plan", json={"path": str(made)}).json()

    assert body["ok"] is True
    assert body["state"] == "drafted"
    # Something a person reads and argues with, not a log of spans.
    assert body["markdown"].startswith("# Edit plan")
    # The second half of the clip is silent, so there is a real decision in here and
    # the plan says how much shorter it makes the video.
    assert body["cuts"] >= 1
    assert body["removed_seconds"] > 0
    assert body["tightened_by"] > 0
    # And no video came out of it. `ingest` measures, `edit` decides, `render` executes,
    # and a decision stage that quietly executed would make the plan a formality.
    assert {p.suffix for p in (storage_dir / "edits").glob("*")} == {".json"}


def test_the_plan_waits_for_the_operator_and_the_approval_is_recorded(client,
                                                                     storage_dir):
    made = _clip(storage_dir / "gated.mp4")
    plan_id = client.post("/api/edit/plan", json={"path": str(made)}).json()["plan_id"]

    before = client.get(f"/api/edit/plans/{plan_id}").json()
    assert before["state"] == "drafted"

    after = client.post(f"/api/edit/plans/{plan_id}/decision",
                        json={"approve": True, "note": "keep the pause at the reveal"})
    body = after.json()
    assert body["state"] == "approved"
    assert body["note"] == "keep the pause at the reveal"
    # What a cutting stage would execute, handed over only once somebody agreed to it.
    assert body["keeps"], "an approved plan with nothing to keep"

    assert client.get(f"/api/edit/plans/{plan_id}").json()["state"] == "approved"


def test_rejecting_is_a_first_class_answer_rather_than_a_deletion(client, storage_dir):
    """A plan you cannot argue with is a plan you have to accept or discard whole. The
    note is what the next draft is made against."""
    made = _clip(storage_dir / "rejected.mp4")
    plan_id = client.post("/api/edit/plan", json={"path": str(made)}).json()["plan_id"]

    body = client.post(f"/api/edit/plans/{plan_id}/decision",
                       json={"approve": False, "note": "that pause was the joke"}).json()
    assert body["state"] == "rejected"
    assert body["keeps"] == []
    assert client.get(f"/api/edit/plans/{plan_id}").json()["note"] == "that pause was the joke"


def test_an_unknown_plan_is_a_404_rather_than_a_guess(client):
    assert client.get("/api/edit/plans/nothing-here").status_code == 404
    assert client.post("/api/edit/plans/nothing-here/decision",
                       json={"approve": True}).status_code == 404


# ----------------------------------------------------------------------- ownership


def test_a_plan_belongs_to_the_account_that_drafted_it(user, session, storage_dir):
    """Plans are files rather than rows, so there is no foreign key doing this for us.

    Asserted against a second *real* account, not an id that does not exist — the
    latter passes on "no such user" and proves nothing about scoping.
    """
    from forgecast.auth import hash_password
    from forgecast.models import User

    made = _clip(storage_dir / "mine.mp4")
    mine = Studio(user_id=user.id).plan_edit(made)
    assert mine["plan_id"]

    other = User(email="someone@else.test", hashed_password=hash_password("x" * 12))
    session.add(other)
    session.commit()
    theirs = Studio(user_id=other.id)

    assert theirs.edit_plans()["count"] == 0
    assert "error" in theirs.edit_plans(mine["plan_id"])
    assert "error" in theirs.approve_edit(mine["plan_id"])
    # And the plan the owner drafted is untouched by the attempt.
    assert Studio(user_id=user.id).edit_plans(mine["plan_id"])["state"] == "drafted"


def test_a_plan_id_cannot_walk_out_of_its_folder(user, session, storage_dir, tmp_path):
    """The id arrives from a model or a request body, and `../../.env` is a valid
    string. It is matched against the ids this account owns rather than joined onto a
    path."""
    secret = tmp_path / "secret.json"
    secret.write_text('{"id": "secret", "user_id": 1}', encoding="utf-8")
    assert "error" in Studio(user_id=user.id).edit_plans(f"../../{secret.stem}")


# --------------------------------------------------------------------- the layers


def test_a_refused_cutout_is_a_result_and_not_a_failure(client, storage_dir,
                                                        monkeypatch):
    """A fringed matte reads as cheaper than no matte at all, so the quality gate
    turning one down is the feature working — and the caller has to be told which."""
    from forgecast import layers
    from forgecast.layers.matte import Matte

    still = storage_dir / "subject.png"
    still.parent.mkdir(parents=True, exist_ok=True)
    still.write_bytes(b"")

    monkeypatch.setattr(layers.matte, "available", lambda: (True, ""))
    monkeypatch.setattr(
        layers, "cut",
        lambda source, target, **kwargs: Matte(
            source=str(source), path=str(target), width=400, height=400,
            coverage=0.3, soft_edge=0.0, usable=False,
            refused="a jagged fringe where a soft edge belongs"))

    body = client.post("/api/edit/layers", json={"image": str(still),
                                                 "text": "TITLE"}).json()
    assert body["ok"] is True
    assert body["usable"] is False
    assert "fringe" in body["refused"]
    # Refused means refused: no composite was made from a matte that was turned down.
    assert body["composited"] == ""


def test_the_cutout_tools_being_absent_offers_the_install(client, storage_dir,
                                                          monkeypatch):
    from forgecast import layers

    monkeypatch.setattr(layers.matte, "available",
                        lambda: (False, "subject cutouts need the video editing tools"))
    body = client.post("/api/edit/layers",
                       json={"image": str(storage_dir / "nothing.png")}).json()
    assert body["ok"] is False
    assert "pip install" not in body["error"] + body.get("install", "")
    assert "/api/setup/extras/edit" in body["install"]
    # And inside the sentence, not only beside it. The MCP wrapper sends `error` as the
    # whole tool result and drops every sibling key, so an offer kept in one is an offer
    # the agent never reads — and it reports the feature as simply unavailable.
    assert "/api/setup/extras/edit" in body["error"]


# ------------------------------------------------------------------- the chat's end


def test_the_chat_can_do_all_of_this_and_may_not_approve_its_own_plan():
    """The chat is this app's primary surface, so the tools are the door that matters.

    `approve_edit` is deliberately outside the pre-allowed set, for the same reason
    `decide_gate` is: a paper edit fixes every expensive decision that follows it, so an
    agent approving its own plan turns the one cheap place to disagree with the machine
    into a formality.
    """
    from forgecast.agent import tools

    for name in ("editing_tools", "read_video", "plan_edit", "edit_plans",
                 "cut_subject"):
        assert f"mcp__forgecast__{name}" in tools.ALLOWED
        assert name in tools.ALL_TOOLS

    assert "approve_edit" in tools.ALL_TOOLS
    assert "mcp__forgecast__approve_edit" not in tools.ALLOWED
