"""
Ten seconds of checks that would have caught every startup break so far.

WHY THIS EXISTS
    Two failures reached Sapro that no ear or GPU was needed to find: an
    @app.get() written above the line that creates `app`, and a window icon the
    backend rejected. Both were a NameError and an ArgumentException -- the
    kind of thing an import and one request catch instantly.

    This does not test audio. It tests that the app can start, that every
    route answers, and that saving a setting saves it. Run it before sending a
    build:

        python smoke.py

    chatterbox is stubbed, because loading a 1 GB model to find out whether a
    route is registered is not a trade worth making.
"""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

for _name in ("chatterbox", "chatterbox.tts", "chatterbox.tts_turbo"):
    sys.modules.setdefault(_name, types.ModuleType(_name))

CHECKS = [
    ("GET", "/", None),
    ("GET", "/api/job", None),
    ("GET", "/api/hardware", None),
    ("GET", "/api/auth", None),
    ("GET", "/api/lab/text", None),
    ("GET", "/api/profile?name=explaintory", None),
    ("GET", "/api/settings", None),
    ("GET", "/api/assistant/prefs", None),
    ("GET", "/api/conversations", None),
    ("POST", "/api/assistant/prefs", {"model": "claude-sonnet-5"}),
    ("POST", "/api/lab/params", {"name": "explaintory", "values": {"speed": 1.0}}),
    ("POST", "/api/settings/reset", {}),
]


def main() -> int:
    import server
    from vostudio import conversations as convos
    from fastapi.testclient import TestClient

    client = TestClient(server.app)
    failed = 0
    # Snapshotted before the first request, because the first request to
    # /api/conversations opens one. Anything not in here is this run's mess and
    # gets cleared up at the end.
    before = {c["id"] for c in convos.summaries(server.ROOT)}

    for method, path, body in CHECKS:
        try:
            r = client.request(method, path, json=body) if body is not None \
                else client.request(method, path)
            ok = r.status_code == 200
        except Exception as exc:
            ok, r = False, exc
        failed += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {method:5} {path:34} "
              f"{getattr(r, 'status_code', r)}")

    # The UI is served as one inlined page; a missing file shows up as a blank
    # window rather than an error, so check the shell actually contains it.
    page = client.get("/").text
    for marker in ("id=\"chat\"", "id=\"chat-input\"", "id=\"params\"",
                   "id=\"convos\"", "id=\"btn-new\"", "--accent", "function send("):
        present = marker in page
        failed += not present
        print(f"  {'ok  ' if present else 'FAIL'} page contains {marker}")

    # Saving has to survive a round trip, which is the whole point of it.
    client.post("/api/assistant/prefs", json={"model": "claude-opus-5"})
    got = client.get("/api/assistant/prefs").json()["model"]
    ok = got == "claude-opus-5"
    failed += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} prefs round-trip -> {got}")
    client.post("/api/assistant/prefs", json={"model": "claude-sonnet-5"})

    # Out-of-range values are clamped by the server, not trusted from the client.
    speed = client.post("/api/lab/params",
                        json={"name": "explaintory", "values": {"speed": 99}}
                        ).json()["profile"]["speed"]
    ok = speed == 1.25
    failed += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} speed clamped -> {speed}")
    client.post("/api/lab/params", json={"name": "explaintory", "values": {"speed": 1.0}})

    # Conversations: created, listed, reopened, deleted. Deleting the one you
    # are in has to land on a real conversation rather than a dangling id --
    # that is the case that would leave the app pointing at a missing file.
    # It cleans up after itself; a smoke run should not leave transcripts in
    # the app's own folder.
    made = client.post("/api/conversations/new", json={}).json()
    cid = made["opened"]
    convos.add_turn(server.ROOT, cid, {"role": "me", "text": "smoke test line", "files": []})

    listed = client.get("/api/conversations").json()
    ok = listed["active"] == cid and any(c["id"] == cid for c in listed["items"])
    failed += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} conversation created and listed")

    opened = client.get(f"/api/conversations/open?id={cid}").json()
    ok = [t.get("text") for t in opened["turns"]] == ["smoke test line"]
    failed += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} transcript replays -> {len(opened['turns'])} turn(s)")

    ok = any(c["id"] == cid and c["title"] == "smoke test line" for c in opened["items"])
    failed += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} conversation named from its first message")

    ok = client.get("/api/conversations/open?id=../../settings").status_code == 404
    failed += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} a path in place of an id is refused")

    gone = client.post("/api/conversations/delete", json={"id": cid}).json()
    ok = (gone["opened"] != cid and not any(c["id"] == cid for c in gone["items"])
          and "turns" in gone)
    failed += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} deleting the open one lands on another")

    for c in convos.summaries(server.ROOT):          # leave no test transcripts
        if c["id"] not in before:
            convos.delete(server.ROOT, c["id"])

    print("\n" + ("ALL PASSED" if not failed else f"{failed} FAILED"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
