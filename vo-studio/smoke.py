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
    ("POST", "/api/assistant/prefs", {"model": "claude-sonnet-5"}),
    ("POST", "/api/lab/params", {"name": "explaintory", "values": {"speed": 1.0}}),
    ("POST", "/api/settings/reset", {}),
]


def main() -> int:
    import server
    from fastapi.testclient import TestClient

    client = TestClient(server.app)
    failed = 0

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
                   "--accent", "function send("):
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

    print("\n" + ("ALL PASSED" if not failed else f"{failed} FAILED"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
