"""The Files browser, and mostly its boundary.

Every path this feature acts on arrives from a browser, and the thing on the other end
of it is the filesystem of the machine the app runs on. So the bulk of what is asserted
here is refusal: a traversal, an absolute path, a symlink pointing out of the storage
folder, and a path that climbs sideways into another account's run. The pleasant part —
text is capped, media goes through the signed-URL mechanism, a directory reads one
level at a time — is asserted too, but it is the smaller half.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from forgecast.api.main import create_app
from forgecast.api.routes_files import MAX_TEXT_BYTES, human_size
from forgecast.api.routes_files import router as files_router
from forgecast.auth import hash_password
from forgecast.models import Channel, Run, User

# A one-pixel PNG. Real bytes rather than a placeholder, because what is being checked
# is that the browser is handed something a browser can actually decode.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


def app_with_files():
    """The app, with this feature's router attached if it is not already.

    Written as a guard rather than as a plain `include_router` because these routes are
    registered in `api.main` too. Attaching them twice would leave a second, shadowed
    copy of every path, and the day one of them stops matching first is the day this
    suite passes while the running app does not.
    """
    app = create_app()
    if not any(getattr(route, "path", "") == "/files" for route in app.routes):
        app.include_router(files_router)
    return app


@pytest.fixture
def client(user):
    with TestClient(app_with_files()) as test_client:
        token = test_client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "supersecret"},
        ).json()["access_token"]
        test_client.headers["Authorization"] = f"Bearer {token}"
        yield test_client


@pytest.fixture
def run_folder(session, user, channel, storage_dir) -> tuple[Run, Path]:
    """A run of this account's, with an empty directory on disk to browse.

    Emptied rather than merely created. The database is dropped between tests but the
    storage directory is not, so run ids start again at 1 and every test after the first
    would otherwise inherit the previous one's files — which is how a test asserting
    that something is *absent* passes or fails depending on the order it ran in.
    """
    run = Run(user_id=user.id, channel_id=channel.id, topic="Does it write anything")
    session.add(run)
    session.commit()
    folder = storage_dir / "runs" / str(run.id)
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    return run, folder


def foreign_run(session, storage_dir, name: str) -> tuple[Run, Path]:
    """Someone else's run, and their folder. Nothing here may reach it."""
    other = User(email=f"{name}@else.test", hashed_password=hash_password("x" * 12))
    session.add(other)
    session.flush()
    channel = Channel(user_id=other.id, name=f"Theirs {name}")
    session.add(channel)
    session.flush()
    run = Run(user_id=other.id, channel_id=channel.id, topic="Not yours")
    session.add(run)
    session.commit()
    folder = storage_dir / "runs" / str(run.id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "script.md").write_text("their script", encoding="utf-8")
    return run, folder


def listing(client, path: str = "") -> dict:
    response = client.get("/api/files/list", params={"path": path})
    assert response.status_code == 200, response.text
    return response.json()


def names(payload: dict) -> list[str]:
    return [entry["name"] for entry in payload["entries"]]


# --------------------------------------------------------------------------- page


def test_the_page_says_what_to_do_before_anything_is_chosen(client, run_folder):
    _run, folder = run_folder
    (folder / "script.md").write_text("# hello", encoding="utf-8")

    page = client.get("/files")
    assert page.status_code == 200
    # The empty state is the whole reason the viewer is not a blank rectangle.
    assert "Select a file on the left to view it." in page.text
    # The sidebar renders, which is what passing shell() through buys.
    assert 'class="side"' in page.text


def test_the_page_ships_one_level_and_not_the_tree(client, run_folder):
    """Laziness is a property of the page, so it is asserted on the page.

    The storage directory holds gigabytes of renders. A recursive walk to draw the tree
    would stat every frame of every run before the first byte of HTML went out, and the
    app would look hung on exactly the install that has the most to show.
    """
    _run, folder = run_folder
    (folder / "unmistakable-leaf.md").write_text("deep", encoding="utf-8")

    body = client.get("/files").text
    assert "runs" in body                       # the first level travels with the page
    assert "unmistakable-leaf.md" not in body   # two levels down, so it must not


def test_the_deep_link_cannot_close_the_script_tag(client):
    """`?path=` is reflected into the page, so it is one of the two injection points.

    A path is attacker-supplied text landing inside a `<script>` block, and the escape
    that matters there is `</script>` rather than the angle brackets HTML escaping
    usually worries about.
    """
    page = client.get("/files", params={"path": "</script><img src=x onerror=alert(1)>"})
    assert page.status_code == 200
    assert "<img src=x" not in page.text
    assert "\\u003c/script\\u003e" in page.text


def test_a_signed_out_visitor_is_sent_to_login():
    with TestClient(app_with_files()) as anonymous:
        response = anonymous.get("/files", follow_redirects=False)
    assert response.status_code == 303
    assert "/login" in response.headers["location"]


def test_the_api_refuses_a_caller_with_no_session():
    with TestClient(app_with_files()) as anonymous:
        assert anonymous.get("/api/files/list").status_code == 401
        assert anonymous.get("/api/files/content",
                             params={"path": "runs"}).status_code == 401


# ------------------------------------------------------------------------ listing


def test_a_directory_is_read_one_level_at_a_time(client, run_folder):
    _run, folder = run_folder
    (folder / "stills").mkdir(exist_ok=True)
    (folder / "script.md").write_text("# script", encoding="utf-8")

    inside = listing(client, f"runs/{_run.id}")
    assert set(names(inside)) >= {"stills", "script.md"}
    # Directories first, and nothing carries its own children — a nested payload would
    # be the recursive walk arriving by another route.
    assert inside["entries"][0]["is_dir"] is True
    assert all("entries" not in entry for entry in inside["entries"])


def test_runs_are_ordered_as_numbers_not_as_strings(client, session, channel,
                                                    storage_dir):
    """Lexicographic order puts run 10 between 1 and 2, which reads as missing runs."""
    made = []
    for _ in range(11):
        run = Run(user_id=channel.user_id, channel_id=channel.id, topic="ordering")
        session.add(run)
        session.commit()
        (storage_dir / "runs" / str(run.id)).mkdir(parents=True, exist_ok=True)
        made.append(str(run.id))

    listed = [name for name in names(listing(client, "runs")) if name in made]
    assert listed == sorted(made, key=int)


def test_size_and_modification_time_are_reported(client, run_folder):
    """The question a stalled run raises is whether the stage wrote anything."""
    _run, folder = run_folder
    (folder / "voice.wav").write_bytes(b"R" * 4096)

    entry = next(e for e in listing(client, f"runs/{_run.id}")["entries"]
                 if e["name"] == "voice.wav")
    assert entry["size"] == 4096
    assert entry["size_label"] == "4.0 KB"
    assert entry["modified"] and entry["modified_label"]

    # A directory's byte count says nothing about what is under it, and totalling its
    # contents would mean the walk this page avoids.
    folders = [e for e in listing(client, "runs")["entries"] if e["is_dir"]]
    assert folders and all(e["size"] is None and e["size_label"] == "—"
                           for e in folders)


def test_human_size_reads_like_a_file_manager():
    assert human_size(0) == "0 B"
    assert human_size(1536) == "1.5 KB"
    assert human_size(20 * 1024) == "20 KB"
    assert human_size(2 * 1024 ** 3) == "2.0 GB"


# ------------------------------------------------------------------- containment


@pytest.mark.parametrize(
    "escape",
    [
        "../../etc/passwd",
        "/etc/passwd",
        "..",
        "../",
        "runs/../../../../etc/passwd",
        # A traversal that has already been through one round of URL decoding, which is
        # what reaches the handler when a client double-encodes it.
        "..%2F..%2Fetc%2Fpasswd",
        "\x00",
    ],
)
def test_a_path_out_of_the_storage_root_is_refused(client, escape):
    """404 rather than 403 on purpose: a distinguishable refusal confirms what exists."""
    assert client.get("/api/files/list", params={"path": escape}).status_code == 404
    assert client.get("/api/files/content", params={"path": escape}).status_code == 404


def test_a_symlink_pointing_out_of_the_root_is_refused_and_never_listed(
    client, run_folder, tmp_path,
):
    """`resolve()` follows symlinks, so containment must be judged after resolving.

    A link is the one traversal that survives every check made on the string: nothing
    about `runs/3/notes.txt` looks like an escape until the filesystem is asked where
    it actually goes.
    """
    run, folder = run_folder
    secret = tmp_path / "passwd"
    secret.write_text("root:x:0:0", encoding="utf-8")
    link = folder / "notes.txt"
    try:
        link.symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("this platform will not let the test create a symlink")

    assert client.get("/api/files/content",
                      params={"path": f"runs/{run.id}/notes.txt"}).status_code == 404
    # And it is left out of the tree rather than listed and refused on click, so the
    # browser only ever shows what it can open.
    assert "notes.txt" not in names(listing(client, f"runs/{run.id}"))


def test_a_symlinked_directory_out_of_the_root_is_refused(client, run_folder, tmp_path):
    run, folder = run_folder
    (tmp_path / "elsewhere").mkdir(exist_ok=True)
    (tmp_path / "elsewhere" / "secret.txt").write_text("x", encoding="utf-8")
    try:
        (folder / "stills").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this platform will not let the test create a symlink")

    assert client.get("/api/files/list",
                      params={"path": f"runs/{run.id}/stills"}).status_code == 404


# --------------------------------------------------------------------- ownership


def test_another_accounts_run_is_invisible(client, session, storage_dir, run_folder):
    theirs, _folder = foreign_run(session, storage_dir, "invisible")

    assert str(theirs.id) not in names(listing(client, "runs"))
    assert client.get("/api/files/list",
                      params={"path": f"runs/{theirs.id}"}).status_code == 404
    assert client.get("/api/files/content",
                      params={"path": f"runs/{theirs.id}/script.md"}).status_code == 404


def test_climbing_sideways_into_another_run_is_refused(client, session, storage_dir,
                                                       run_folder):
    """Ownership is decided on the resolved path, not on the string that arrived.

    `runs/<mine>/../<theirs>/script.md` stays inside the storage root, so containment
    is satisfied. It names another account's run all the same, and a check made on the
    raw text would read the leading segment and see only the caller's own run.
    """
    mine, _folder = run_folder
    theirs, _ = foreign_run(session, storage_dir, "sideways")

    sideways = f"runs/{mine.id}/../{theirs.id}/script.md"
    assert client.get("/api/files/content",
                      params={"path": sideways}).status_code == 404


def test_a_numbered_folder_with_no_run_left_is_hidden(client, storage_dir):
    """Deleting a run must not be the moment its files become everybody's.

    An orphan folder cannot be attributed to an account, so it is hidden rather than
    treated as installation-wide the way `motion_presets/` is.
    """
    orphan = storage_dir / "runs" / "987654"
    orphan.mkdir(parents=True, exist_ok=True)
    (orphan / "script.md").write_text("whose is this", encoding="utf-8")

    assert "987654" not in names(listing(client, "runs"))
    assert client.get("/api/files/list",
                      params={"path": "runs/987654"}).status_code == 404


def test_the_installations_own_folders_stay_readable(client, storage_dir):
    """Motion presets and learned styles describe the machine, not one account."""
    presets = storage_dir / "motion_presets"
    presets.mkdir(parents=True, exist_ok=True)
    (presets / "kinetic.json") .write_text('{"name": "kinetic"}', encoding="utf-8")

    assert "motion_presets" in names(listing(client))
    assert "kinetic.json" in names(listing(client, "motion_presets"))


# ----------------------------------------------------------------------- viewing


def test_text_is_capped_and_says_it_was_cut(client, run_folder):
    """Truncation has to be visible, or the first quarter-megabyte reads as the file."""
    run, folder = run_folder
    (folder / "transcript.txt").write_text("a" * (MAX_TEXT_BYTES + 5000),
                                           encoding="utf-8")

    file = client.get("/api/files/content",
                      params={"path": f"runs/{run.id}/transcript.txt"}).json()
    assert file["kind"] == "text"
    assert len(file["text"]) == MAX_TEXT_BYTES
    assert file["truncated"] is True
    assert "first" in file["note"] and "256" in file["note"]


def test_a_short_text_file_is_not_reported_as_cut(client, run_folder):
    run, folder = run_folder
    (folder / "brief.md").write_text("# Brief\n\nships", encoding="utf-8")

    file = client.get("/api/files/content",
                      params={"path": f"runs/{run.id}/brief.md"}).json()
    assert file["text"] == "# Brief\n\nships"
    assert file["truncated"] is False
    assert file["note"] == ""


def test_an_unfamiliar_extension_that_reads_as_text_is_still_shown(client, run_folder):
    """Run folders collect extension-less files, and refusing them sends people back
    to the file manager this page exists to replace."""
    run, folder = run_folder
    (folder / "manifest").write_text('{"stills": 12}', encoding="utf-8")

    file = client.get("/api/files/content",
                      params={"path": f"runs/{run.id}/manifest"}).json()
    assert file["kind"] == "text"
    assert file["text"] == '{"stills": 12}'


def test_accented_text_is_not_mistaken_for_binary(client, run_folder):
    """The sniff window lands mid-character in any UTF-8 file long enough to matter."""
    run, folder = run_folder
    (folder / "script.md").write_text("é" * 9000, encoding="utf-8")

    file = client.get("/api/files/content",
                      params={"path": f"runs/{run.id}/script.md"}).json()
    assert file["kind"] == "text"


def test_something_unreadable_says_what_it_is_and_offers_nothing(client, run_folder):
    """No link, no player, no <pre>. A 2 GB blob rendered as text is a frozen tab."""
    run, folder = run_folder
    (folder / "cache.bin").write_bytes(b"\x00\x01\x02" * 4000)

    file = client.get("/api/files/content",
                      params={"path": f"runs/{run.id}/cache.bin"}).json()
    assert file["kind"] == "other"
    assert file["text"] is None
    assert file["media_url"] is None
    assert ".bin" in file["note"] and "KB" in file["note"]


def test_media_is_served_through_the_signed_url_mechanism(client, run_folder):
    """Bytes go through `api.media`, not through this JSON.

    Which is what makes a signed link work in a `<video>` tag: the browser will not
    attach a bearer token to one, so the URL has to carry its own authority. Fetched
    here with a client that has no session at all, because that is the whole claim.
    """
    run, folder = run_folder
    (folder / "still-01.png").write_bytes(PNG)

    file = client.get("/api/files/content",
                      params={"path": f"runs/{run.id}/still-01.png"}).json()
    assert file["kind"] == "image"
    assert file["media_url"].startswith("/media/")
    assert "sig=" in file["media_url"] and "exp=" in file["media_url"]

    with TestClient(app_with_files()) as anonymous:
        fetched = anonymous.get(file["media_url"])
    assert fetched.status_code == 200
    assert fetched.content == PNG
    assert fetched.headers["content-type"] == "image/png"


def test_video_and_audio_get_a_player_and_an_honest_caveat(client, run_folder):
    run, folder = run_folder
    (folder / "final.mp4").write_bytes(b"\x00\x00\x00 ftypmp42")
    (folder / "take-1.wav").write_bytes(b"RIFF0000WAVE")
    (folder / "reference.mkv").write_bytes(b"\x1a\x45\xdf\xa3")

    def read(name: str) -> dict:
        return client.get("/api/files/content",
                          params={"path": f"runs/{run.id}/{name}"}).json()

    assert read("final.mp4")["kind"] == "video"
    assert read("final.mp4")["media_url"]
    assert read("final.mp4")["note"] == ""
    assert read("take-1.wav")["kind"] == "audio"
    # A container the browser will not decode has to say so, or it shows an empty
    # player and reads as a corrupt file.
    assert "may not be able to play" in read("reference.mkv")["note"]


def test_a_directory_is_not_offered_as_a_file(client, run_folder):
    run, _folder = run_folder
    assert client.get("/api/files/content",
                      params={"path": f"runs/{run.id}"}).status_code == 404
    assert client.get("/api/files/list",
                      params={"path": f"runs/{run.id}/nothing-here"}
                      ).status_code == 404
