"""Learning an editing style, from inside the application.

`routes_styles.py` imported `available`, `blend`, `delete`, `get` and `refine` — and not
`learn`. The only importer of `style.learn` in the tree was `forgecast/vision/cli.py`, so
the app could read, apply, mix, improve and delete editing styles and nothing in it could
produce one. `studio.list_styles` said as much in its own note: learn one with the vision
CLI. That left `forgecast/vision` — three thousand lines that measure a reference — with
no production importer at all.

`tests/test_style.py` and `tests/test_vision.py` cover the measuring and the reduction.
These are about the door.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from forgecast.agent.studio import Studio, styles_dir
from forgecast.api.main import create_app


def _reference(path: Path, *, seconds: float = 1.2) -> Path:
    """A real two-shot clip. The measurement is the point, so it is measured."""
    path.parent.mkdir(parents=True, exist_ok=True)
    parts = []
    for index, colour in enumerate(("red", "blue")):
        piece = path.parent / f"{path.stem}-part{index}.mp4"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", f"color=c={colour}:s=320x180:d={seconds}:r=24",
             "-f", "lavfi", "-i", f"anullsrc=duration={seconds}",
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
def idle_learn_job():
    """No learn in flight, whichever test ran first.

    The job is process-wide because the style folder is, so a test that left it running
    would make the next one join a run that had already finished.
    """
    from forgecast.api import routes_styles

    routes_styles.LEARN.update(running=False, done=False, ok=False, log=[], result={},
                               name="", user_id=0)
    yield


# --------------------------------------------------------------------- the studio


def test_a_style_can_be_produced_and_lands_on_the_shelf_the_page_reads(user,
                                                                       storage_dir):
    """The two halves have to agree about where styles live.

    `editing.DEFAULT_DIRECTORY` is a *relative* path, so a chat that saved there and a
    page that reads the configured storage directory would be a style learned and a
    shelf that never showed it — the same class of failure as having no learner at all.
    """
    made = _reference(storage_dir / "ref.mp4")
    learned = Studio(user_id=user.id).learn_style(made, name="Their Look")

    assert learned["measured"] == 1
    assert learned["key"] == "their_look"
    assert Path(learned["path"]).parent == Path(styles_dir())
    # And it is on the shelf the page renders, not just in a folder somewhere.
    assert "their_look" in [row["key"] for row in Studio(user_id=user.id)
                            .list_styles()["styles"]]


def test_what_the_upgrade_pass_changed_comes_back_named(user, storage_dir):
    """The whole reason `learn` and `refine` are separate. A departure that is applied
    and not reported is the difference between "how they cut" and "how we cut" being
    quietly baked in."""
    made = _reference(storage_dir / "ref.mp4")
    learned = Studio(user_id=user.id).learn_style(made, name="Upgraded")

    assert "departures" in learned
    assert learned["departures_note"]
    saved = json.loads((Path(styles_dir()) / "upgraded.json").read_text())
    assert saved["provenance"]["origin"] == "refined"


def test_a_reference_that_cannot_be_read_costs_one_reference(user, storage_dir):
    """Several references is the point of this, so one bad file must not take the
    others with it."""
    made = _reference(storage_dir / "ref.mp4")
    broken = storage_dir / "not-a-video.mp4"
    broken.write_bytes(b"not a video")

    learned = Studio(user_id=user.id).learn_style(
        [made, broken], name="Partly Measured")
    assert learned["measured"] == 1
    assert any("not-a-video" in item for item in learned["failures"])


def test_nothing_measurable_is_an_error_rather_than_an_empty_style(user, storage_dir):
    broken = storage_dir / "not-a-video.mp4"
    broken.write_bytes(b"not a video")
    learned = Studio(user_id=user.id).learn_style(broken, name="Nothing")
    assert "error" in learned
    assert not (Path(styles_dir()) / "nothing.json").exists()


def test_a_reference_outside_the_install_is_not_read(user):
    learned = Studio(user_id=user.id).learn_style("/etc/hostname", name="Sneaky")
    assert "error" in learned
    assert any("outside this install" in item for item in learned["failures"])


def test_a_style_needs_a_name_because_the_name_is_the_key(user, storage_dir):
    made = _reference(storage_dir / "ref.mp4")
    assert "error" in Studio(user_id=user.id).learn_style(made, name="")


def test_references_arrive_however_the_caller_sent_them(user, storage_dir):
    """A list, a comma-separated string and a pasted column all mean the same thing.
    Rejecting two of the three teaches the agent to send one reference at a time, which
    is exactly the shape of style that is worth nothing."""
    made = _reference(storage_dir / "ref.mp4")
    for form in (str(made), [str(made)], f"{made}\n{made}", f"{made}, {made}"):
        learned = Studio(user_id=user.id).learn_style(form, name="Whatever")
        assert learned.get("measured"), form


# ---------------------------------------------------------------------- the route


def test_learning_needs_an_account():
    with TestClient(create_app()) as anon:
        assert anon.get("/api/styles/learn").status_code == 401
        assert anon.post("/api/styles/learn",
                         json={"references": ["x"], "name": "y"}).status_code == 401


def test_a_learn_with_nothing_to_measure_is_refused_before_a_thread_starts(client):
    assert client.post("/api/styles/learn",
                       json={"references": [], "name": "x"}).status_code == 400
    assert client.post("/api/styles/learn",
                       json={"references": ["x"], "name": ""}).status_code == 400


def test_the_route_streams_progress_and_ends_with_the_style(client, storage_dir):
    """It decodes video, so it cannot be a request that returns when it is done.

    The stream is the same NDJSON the setup page already reads, and the lines name each
    reference as it is measured — a progress bar with no idea how long a video is would
    be a guess drawn as a fact.
    """
    made = _reference(storage_dir / "ref.mp4")
    with client.stream("POST", "/api/styles/learn",
                       json={"references": [str(made)], "name": "Streamed"}) as answered:
        assert answered.status_code == 200
        events = [json.loads(line) for line in answered.iter_lines() if line.strip()]

    assert any(event["type"] == "log" and "Measuring" in event["text"]
               for event in events)
    done = events[-1]
    assert done["type"] == "done"
    assert done["ok"] is True
    assert done["result"]["key"] == "streamed"

    # And the page can now show it, which is the thing that was missing.
    page = client.get("/styles?selected=streamed").text
    assert "Streamed" in page


def test_the_running_job_is_not_visible_to_another_account(client, session):
    from forgecast.api import routes_styles
    from forgecast.auth import hash_password
    from forgecast.models import User

    other = User(email="someone@else.test", hashed_password=hash_password("x" * 12))
    session.add(other)
    session.commit()

    routes_styles.LEARN.update(running=True, done=False, name="Mine",
                               log=["/home/someone/private-clip.mp4"], user_id=999)
    theirs = routes_styles._learn_state(other.id)
    assert theirs["running"] is True          # they can see the folder is busy
    assert theirs["mine"] is False
    assert theirs["name"] == ""               # and nothing about whose it is
    assert theirs["log"] == []


# ----------------------------------------------------------------------- the page


def test_the_page_offers_learning_instead_of_a_command_to_type():
    """An empty shelf used to print two shell commands to paste into a terminal, which
    is the homework this app removes everywhere else."""
    page = (Path(__file__).resolve().parent.parent / "forgecast" / "web"
            / "styles.html").read_text(encoding="utf-8")

    assert "/api/styles/learn" in page
    assert "Learn one from a creator" in page
    # The uploader is the chat composer's, not a second one written for this page.
    assert "/api/agent/attach" in page
    assert "forgecast-vision learn-style" not in page


# ------------------------------------------------------------------- the chat's end


def test_the_chat_can_learn_one_too():
    from forgecast.agent import tools

    assert "mcp__forgecast__learn_style" in tools.ALLOWED
    assert "learn_style" in tools._WRITES
