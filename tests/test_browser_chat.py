"""Browser tests for the one class of bug Python tests cannot see.

Everything about a streamed turn that matters — which container the output lands in,
what happens to the transcript when you switch threads mid-stream, whether a paste
becomes a file — is DOM behaviour. A request-level test proves the server sent the
right bytes and says nothing about where the browser put them.

Skipped, not failed, when Playwright or a browser is not installed: this must not be
the reason a checkout cannot run its tests. Run it with a browser present and it is
deterministic — the chat stream is served by the test, so there is no race with a real
agent and no network.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("playwright", reason="playwright is not installed")

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent

# The events that arrive AFTER the user has switched away. Every one is a DOM write,
# and every one used to land in whichever conversation was open at the time.
LATE_EVENTS = [
    {"type": "tool", "id": "t1", "name": "mcp__forgecast__research_channel",
     "input": {"url": "https://youtube.com/@leaked"}},
    {"type": "tool_result", "id": "t1", "is_error": False, "text": "LEAKED RESULT"},
    {"type": "text", "text": "LEAKED PROSE belonging to the other thread."},
    {"type": "result", "session_id": "sess-x", "turns": 1, "cost_usd": 0.01,
     "is_error": False},
    {"type": "done"},
]


def _browser_path() -> str | None:
    for candidate in ("/opt/pw-browsers/chromium",):
        if Path(candidate).exists():
            return candidate
    return None


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture(scope="module")
def live_app(tmp_path_factory):
    """A real server on a real port, because a browser cannot talk to a TestClient."""
    workdir = tmp_path_factory.mktemp("browser")
    port = _free_port()
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(workdir),
        "PYTHONPATH": str(ROOT),
        "FORGECAST_DATABASE_URL": f"sqlite:///{workdir / 'app.db'}",
        "FORGECAST_STORAGE_DIR": str(workdir / "storage"),
        "FORGECAST_SECRET_KEY": "browser-test-secret-not-for-production",
        "FORGECAST_PROVIDER_MODE": "mock",
        "FORGECAST_ALLOW_SIGNUP": "true",
    }
    seed = ROOT / "tests" / "_browser_seed.py"
    seed.write_text(
        "from forgecast.db import SessionLocal, init_db\n"
        "from forgecast.auth import hash_password\n"
        "from forgecast import credits\n"
        "from forgecast.models import User\n"
        "init_db()\n"
        "with SessionLocal() as s:\n"
        "    if not s.query(User).first():\n"
        "        u = User(email='b@t.local', hashed_password=hash_password('browserpass'))\n"
        "        s.add(u); s.flush(); credits.grant(s, u.id, 500, note='seed'); s.commit()\n",
        encoding="utf-8",
    )
    subprocess.run([sys.executable, str(seed)], env=env, check=True,
                   capture_output=True)
    seed.unlink(missing_ok=True)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "forgecast.api.main:app",
         "--port", str(port), "--log-level", "warning"],
        env=env, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(120):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                break
        except OSError:
            if server.poll() is not None:
                pytest.skip("the server did not start")
            time.sleep(0.25)
    else:
        server.kill()
        pytest.skip("the server did not become reachable")

    yield base
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:              # pragma: no cover
        server.kill()


@pytest.fixture(scope="module")
def page(live_app):
    executable = _browser_path()
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(
                **({"executable_path": executable} if executable else {}))
        except Exception as exc:                   # pragma: no cover
            pytest.skip(f"no chromium available: {exc}")
        tab = browser.new_page(viewport={"width": 1400, "height": 900})
        tab.goto(f"{live_app}/login")
        tab.fill('input[name="email"]', "b@t.local")
        tab.fill('input[name="password"]', "browserpass")
        tab.click("button")
        tab.wait_for_load_state("networkidle")
        yield tab
        browser.close()


def test_a_turn_running_in_one_thread_never_paints_into_another(page, live_app):
    """Switching threads mid-stream must not move the running turn's output.

    `chat().innerHTML = ''` detaches the running turn's container, and the two DOM
    writers used to fall back to the live transcript when that happened — so thread
    A's tool cards and prose appeared in thread B, and B's greeter was wiped on the
    way in. The reply is persisted server-side against thread A, so reopening A shows
    it; nothing should reach B.
    """
    def slow_stream(route):
        # Long enough for the switch to happen first, then every late event at once.
        time.sleep(3.0)
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/x-ndjson"},
            body="".join(json.dumps(event) + "\n" for event in LATE_EVENTS),
        )

    page.goto(f"{live_app}/")
    page.wait_for_timeout(1200)
    page.route("**/api/agent/threads/*/chat", slow_stream)

    page.click("#btn-new")
    page.wait_for_timeout(400)
    page.fill("#chat-input", "mine this niche")
    page.press("#chat-input", "Enter")
    page.wait_for_timeout(700)                     # in flight, nothing streamed yet

    page.click("#btn-new")                         # switch away
    page.wait_for_timeout(500)
    assert page.query_selector("#chat-empty") is not None, "the new chat lost its opener"

    page.wait_for_timeout(4500)                    # the late events land in here

    body = page.inner_text("#chat")
    assert "LEAKED" not in body
    assert page.query_selector_all("#chat .tool") == []
    assert page.query_selector_all("#chat .msg") == []
    # And the greeter survives, which is the half that is easy to miss: the writer
    # cleared the placeholder before choosing where to append.
    assert page.query_selector("#chat-empty") is not None

    page.unroute("**/api/agent/threads/*/chat")


def test_a_clipboard_file_with_no_name_is_attached_as_what_it_is(page, live_app):
    """The clipboard gives bytes and a MIME type and no filename.

    Uploaded as-is that reaches the agent as an opaque file it cannot open, which is
    why pasting a screenshot looked like it worked and then did nothing.
    """
    page.goto(f"{live_app}/")
    page.wait_for_timeout(1200)

    png = ("iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAFUlEQVR42mP8z8Dwn4"
           "GBgYGJgYGBAQAeAAH/8y0dwwAAAABJRU5ErkJggg==")
    page.evaluate(
        """(b64) => {
            const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
            const file = new File([bytes], '', {type: 'image/png'});
            const data = new DataTransfer();
            data.items.add(file);
            document.dispatchEvent(new ClipboardEvent('paste', {
                clipboardData: data, bubbles: true, cancelable: true}));
        }""",
        png,
    )
    page.wait_for_selector("#attached .att", timeout=8000)
    chip = page.inner_text("#attached .att")
    assert ".png" in chip                 # an extension was derived from the MIME type
    assert "image" in chip                # and it is classified as something visible
