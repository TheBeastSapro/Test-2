"""The chat, the studio operations behind it, and the connectors.

These exercise the parts that do not need Claude to be signed in. The agent loop
itself needs the CLI and a subscription, which a test machine does not have — so
what is asserted here is everything up to and including the point where the loop
would start, plus the honest refusal when it cannot.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from forgecast.agent import connectors, prefs
from forgecast.agent.studio import Studio, parse_link
from forgecast.api.main import create_app
from forgecast.models import Channel, Conversation


@pytest.fixture
def client(user):
    with TestClient(create_app()) as test_client:
        token = test_client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "supersecret"},
        ).json()["access_token"]
        test_client.headers["Authorization"] = f"Bearer {token}"
        yield test_client


# ------------------------------------------------------------------ link parsing


@pytest.mark.parametrize(
    "text,kind,value",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "video", "dQw4w9WgXcQ"),
        # The share button produces this one, so it is the form most often pasted.
        ("https://youtu.be/dQw4w9WgXcQ?t=42", "video", "dQw4w9WgXcQ"),
        ("https://youtube.com/shorts/AbCdEfGhIjK", "video", "AbCdEfGhIjK"),
        ("https://www.youtube.com/@Kurzgesagt/videos", "handle", "@Kurzgesagt"),
        ("@Veritasium", "handle", "@Veritasium"),
        ("https://www.youtube.com/c/Vsauce", "handle", "Vsauce"),
        ("https://www.youtube.com/channel/UCX6OQ3DkcsbYNE6H8uQQuVA",
         "channel", "UCX6OQ3DkcsbYNE6H8uQQuVA"),
        ("make me a video about ships", "unknown", ""),
    ],
)
def test_parse_link(text, kind, value):
    found = parse_link(text)
    assert (found.kind, found.value) == (kind, value)


# -------------------------------------------------------------- studio, directly


def test_status_reports_this_install(user):
    report = Studio(user_id=user.id).status()
    assert report["account"] == user.email
    assert report["mode"] == "mock"
    # The point of the tool: it says what mock MEANS, so the agent's first sentence
    # is about this machine rather than a generic greeting.
    assert "nothing is called" in report["mode_means"]
    assert report["channels"]["total"] == 0


def test_create_channel_derives_shape_from_format(user):
    studio = Studio(user_id=user.id)
    made = studio.create_channel("Vertical Tales", niche="folklore", fmt="shorts")
    assert made["created"] is True
    assert made["aspect_ratio"] == "9:16"
    assert made["target_seconds"] <= 90

    listed = studio.list_channels(fmt="shorts")
    assert [row["name"] for row in listed["channels"]] == ["Vertical Tales"]
    assert studio.list_channels(fmt="longform")["channels"] == []


def test_duplicate_channel_name_is_refused_with_the_id(user):
    studio = Studio(user_id=user.id)
    first = studio.create_channel("Deep Water")
    clash = studio.create_channel("deep water")
    assert "error" in clash
    assert str(first["id"]) in clash["error"]


def test_channel_can_be_named_instead_of_numbered(user, session):
    studio = Studio(user_id=user.id)
    studio.create_channel("Ocean Freight", niche="logistics")
    # An agent has the name in the conversation and the id nowhere. Requiring the id
    # would mean a list_channels call before every single operation.
    started = studio.start_run("ocean freight", "How the Suez blockage moved prices")
    assert started["started"] is True
    assert studio.run_status(started["run"])["channel"] == "Ocean Freight"


def test_start_run_on_an_unknown_channel_lists_the_real_ones(user):
    studio = Studio(user_id=user.id)
    studio.create_channel("Ocean Freight")
    failed = studio.start_run("Ocean Frieght", "typo")
    assert "error" in failed
    assert failed["channels"] == ["Ocean Freight"]


def test_score_videos_refuses_prose_rather_than_inventing_numbers(user):
    scored = Studio(user_id=user.id).score_videos("some videos did well I think")
    assert "error" in scored
    assert "scoreable" in scored["error"]


def test_score_videos_ranks_a_real_table(user):
    table = "\n".join([
        "title\tviews\tpublished\tsubscribers",
        "Ordinary one\t10000\t2024-01-01\t50000",
        "Ordinary two\t12000\t2024-02-01\t50000",
        "Ordinary three\t9000\t2024-03-01\t50000",
        "Ordinary four\t11000\t2024-04-01\t50000",
        "The breakout\t250000\t2024-05-01\t50000",
    ])
    scored = Studio(user_id=user.id).score_videos(table)
    assert scored["videos"] == 5
    assert scored["count"] >= 1
    assert scored["strongest"]["title"] == "The breakout"
    # It has to be reported as a multiple of the cohort, not as a raw view count —
    # 250k means nothing without the 10k median beside it.
    assert scored["strongest"]["multiple"] > 5


def test_research_with_no_way_to_fetch_names_every_way_out(user, monkeypatch):
    """No key *and* no yt-dlp is the only case that still cannot read a channel.

    A missing key on its own no longer stops anything — see
    tests/test_research_keyless.py, where the public page is read instead.
    """
    from forgecast.research import keyless

    monkeypatch.setattr(keyless, "_executable", lambda: None)
    out = Studio(user_id=user.id).research_channel("https://youtube.com/@someone")

    assert "error" in out
    assert "pip install yt-dlp" in out["error"]
    assert "Settings" in out["error"]
    assert "paste" in out["alternative"]


def test_research_rejects_a_single_video(user):
    out = Studio(user_id=user.id).research_channel("https://youtu.be/dQw4w9WgXcQ")
    assert "cohort" in out["error"]


# ------------------------------------------------------------------- the HTTP end


def test_chat_page_is_the_front_door(client):
    page = client.get("/")
    assert page.status_code == 200
    body = page.text
    # The complaint that started this rebuild: "there's no claude chat I can see".
    assert 'id="chat"' in body
    assert "New chat" in body
    assert "/static/chat.js" in body


def test_auth_endpoint_reports_rather_than_guesses(client):
    report = client.get("/api/agent/auth").json()
    assert set(report) >= {"ok", "headline", "detail", "cli_found", "can_login"}
    # Whatever this machine's state, the report must be self-consistent: it cannot
    # claim to be connected while also offering the sign-in button.
    assert not (report["ok"] and report["can_login"])


def test_threads_are_created_named_and_listed(client):
    made = client.post("/api/agent/threads", json={}).json()
    assert made["title"] == "New chat"

    threads = client.get("/api/agent/threads").json()["threads"]
    assert [t["id"] for t in threads] == [made["id"]]

    client.patch(f"/api/agent/threads/{made['id']}", json={"title": "Ocean Freight"})
    assert client.get(f"/api/agent/threads/{made['id']}").json()["title"] == "Ocean Freight"


def test_threads_are_private_to_their_owner(client, session):
    from forgecast.auth import hash_password
    from forgecast.models import User

    other = User(email="someone@else.test", hashed_password=hash_password("x" * 12))
    session.add(other)
    session.flush()
    theirs = Conversation(user_id=other.id, title="Not yours")
    session.add(theirs)
    session.commit()

    assert client.get(f"/api/agent/threads/{theirs.id}").status_code == 404
    assert client.get("/api/agent/threads").json()["threads"] == []


def test_a_turn_without_claude_saves_the_user_message_and_says_why(client, session):
    """The turn must not vanish when the agent cannot run.

    A failed turn that also loses what you typed is the worst version of this: you
    lose the message AND the reason. So the user's message is stored before the agent
    is asked to do anything, and the refusal is streamed as an error event.
    """
    thread = client.post("/api/agent/threads", json={}).json()
    response = client.post(f"/api/agent/threads/{thread['id']}/chat",
                           json={"message": "set up a channel like @Kurzgesagt"})
    assert response.status_code == 200

    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert events[-1]["type"] == "done"

    stored = client.get(f"/api/agent/threads/{thread['id']}").json()
    assert stored["messages"][0]["role"] == "user"
    assert "Kurzgesagt" in stored["messages"][0]["text"]
    # Named from its first message rather than left as "New chat".
    assert stored["title"].startswith("set up a channel")


def test_an_empty_turn_is_refused(client):
    thread = client.post("/api/agent/threads", json={}).json()
    assert client.post(f"/api/agent/threads/{thread['id']}/chat",
                       json={"message": "   "}).status_code == 400


def test_status_endpoint_matches_the_tool(client, user):
    over_http = client.get("/api/agent/status").json()
    direct = Studio(user_id=user.id).status()
    # One implementation, two doors. If these can disagree, the panel and the agent
    # can describe the same install differently in the same window.
    assert over_http["mode"] == direct["mode"]
    assert over_http["channels"]["total"] == direct["channels"]["total"]


# --------------------------------------------------------------------- connectors


def test_connector_catalogue_includes_nexlev(client):
    listing = client.get("/api/connectors").json()["connectors"]
    keys = [row["key"] for row in listing]
    assert "nexlev" in keys
    nexlev = next(row for row in listing if row["key"] == "nexlev")
    assert nexlev["connected"] is False
    # Every entry has to say where the URL comes from — a connector page that just
    # asks for a URL is a page nobody can fill in.
    assert nexlev["where"]


def test_connector_round_trip_masks_the_token(client, tmp_path, monkeypatch):
    monkeypatch.setattr(connectors, "default_path", lambda: tmp_path / "connectors.json")

    saved = client.post("/api/connectors", json={
        "key": "nexlev", "url": "https://mcp.example.test/mcp", "token": "secret-token",
    }).json()
    assert saved["connected"] is True
    assert "secret-token" not in json.dumps(saved)

    store = connectors.Store.load()
    assert store.connections["nexlev"].token == "secret-token"
    # The shape the SDK is handed: a bearer header, not a query parameter.
    assert store.active()["nexlev"]["headers"]["Authorization"] == "Bearer secret-token"

    # Re-saving with a blank token keeps the stored one, because the page shows a
    # mask and an unedited field submits empty.
    client.post("/api/connectors", json={"key": "nexlev",
                                         "url": "https://mcp.example.test/v2"})
    assert connectors.Store.load().connections["nexlev"].token == "secret-token"


def test_connector_url_must_look_like_one(client, tmp_path, monkeypatch):
    monkeypatch.setattr(connectors, "default_path", lambda: tmp_path / "connectors.json")
    bad = client.post("/api/connectors", json={"key": "nexlev", "url": "mcp.example"})
    assert bad.status_code == 400


def test_disabled_connector_is_not_handed_to_the_agent(tmp_path, monkeypatch):
    monkeypatch.setattr(connectors, "default_path", lambda: tmp_path / "connectors.json")
    store = connectors.Store.load()
    store.set("nexlev", "https://mcp.example.test/mcp", "t", enabled=False)
    assert connectors.Store.load().active() == {}


# -------------------------------------------------------------------------- prefs


def test_prefs_persist_and_reject_an_unknown_model(client):
    assert client.post("/api/agent/prefs", json={"model": "gpt-9"}).status_code == 400

    client.post("/api/agent/prefs", json={"model": "claude-opus-5",
                                          "confirm_edits": False})
    assert prefs.load().model == "claude-opus-5"
    assert prefs.load().confirm_edits is False


# ---------------------------------------------------------------- settings page


def test_settings_page_answers_the_three_questions(client, session, user):
    session.add(Channel(user_id=user.id, name="Anything"))
    session.commit()

    page = client.get("/settings")
    assert page.status_code == 200
    body = page.text
    assert "Connectors" in body        # can I connect integrations?
    assert "NexLev" in body            # the one that was asked for by name
    assert "Provider keys" in body     # where do the keys go?
    assert "Claude" in body            # is Claude connected?


# ------------------------------------------------------------------------- voice


def test_voice_catalogue_says_where_the_names_came_from(user):
    """Measured or assumed, never silently either.

    The offline list is the stock ElevenLabs set and is known to go stale against a
    real account. Ranking against it and presenting the result as a casting decision
    is how you end up choosing a voice that does not exist on your account.
    """
    listed = Studio(user_id=user.id).voice_catalogue()
    assert listed["count"] > 0
    assert listed["source"]
    if listed["source"] == "offline fallback list":
        assert "may not exist on your account" in listed["caveat"]


def test_cast_voice_returns_reasons_not_just_a_score(user):
    cast = Studio(user_id=user.id).cast_voice(pitch="low", pace="measured")
    assert cast["candidates"]
    top = cast["candidates"][0]
    # A bare number is something to trust blindly. The reasons are what let you
    # disagree with the ranking, which is the whole point of a shortlist.
    assert top["reasons"] or top["caveats"]
    assert cast["summary"]
    # What was described and what was left unmeasured are both recorded.
    assert cast["target"]["pitch_band"] == "low"
    assert "energy" in cast["target"]["gaps"]


def test_the_agent_may_not_approve_a_gate_on_its_own(user):
    """decide_gate is deliberately outside the pre-allowed list.

    Approving is the moment a run is allowed to spend on the stage behind it. Every
    other tool here is read-only or re-runnable; this one is neither, so it must stop
    and ask even when the agent is confident.
    """
    from forgecast.agent import tools

    assert "mcp__forgecast__decide_gate" not in tools.ALLOWED
    assert "decide_gate" in tools.ALL_TOOLS
    # And nothing that spends without a gate slipped into the allowed set either.
    assert "mcp__forgecast__start_run" in tools.ALLOWED   # holds credits, then pauses


# ------------------------------------------------------------------ tool cards


def test_a_long_tool_result_is_cut_and_says_so(user):
    """Truncation has to be visible.

    A result silently cut at the boundary reads as the whole thing, and the agent
    will reason about the part it can see as if nothing were missing.
    """
    from forgecast.agent.assistant import MAX_RESULT_CHARS, _result_text

    class Block:
        content = "x" * (MAX_RESULT_CHARS + 500)

    text = _result_text(Block())
    assert len(text) < MAX_RESULT_CHARS + 200
    assert "more characters" in text


def test_tool_results_survive_every_content_shape(user):
    """String, list-of-parts, and a part with no text at all."""
    from forgecast.agent.assistant import _result_text

    class Block:
        def __init__(self, content):
            self.content = content

    assert _result_text(Block("plain")) == "plain"
    assert _result_text(Block([{"type": "text", "text": "one"},
                               {"type": "text", "text": "two"}])) == "one\ntwo"
    # An image part has no text; naming its type beats rendering "None".
    assert _result_text(Block([{"type": "image"}])) == "[image]"


def test_the_studio_panel_reports_why_it_is_asleep(user):
    """A dormant player must say what it is waiting for.

    An empty frame is a worse answer to "what is this panel" than one sentence,
    and it is indistinguishable from a bug.
    """
    studio = Studio(user_id=user.id)
    asleep = studio.current_preview()
    assert asleep["state"] == "asleep"
    assert "no runs yet" in asleep["reason"]

    studio.create_channel("Cargo Lines", niche="shipping")
    studio.start_run("Cargo Lines", "Why the Suez blockage moved prices")
    waking = studio.current_preview()
    # A queued run has no script, so there is genuinely nothing to draw — and it
    # says which run and why rather than showing an empty player.
    assert waking["state"] == "waking"
    assert waking["run"]
    assert "script" in waking["reason"]


def test_the_preview_page_can_render_without_the_chrome(client, user):
    """`embed=1` is what lets the Studio panel show the real preview page.

    A second implementation of the player is two things that have to stay identical
    and will not, so the panel embeds this page — and an embed with a sidebar nested
    inside a sidebar announces itself as one.
    """
    studio = Studio(user_id=user.id)
    studio.create_channel("Cargo Lines")
    run = studio.start_run("Cargo Lines", "Anything")["run"]

    full = client.get(f"/runs/{run}/preview")
    embedded = client.get(f"/runs/{run}/preview?embed=1")
    assert full.status_code == embedded.status_code == 200
    assert 'class="side"' in full.text
    assert 'class="side"' not in embedded.text
    assert "New chat" not in embedded.text


# ------------------------------------------- the VO Studio bugs, checked against this


def test_the_turn_is_saved_even_when_the_client_disconnects(client, session, user):
    """The bug that made the other app's chat have no memory, reached another way.

    The save used to sit after the stream loop inside the response generator. Closing
    the window mid-turn makes Starlette close that generator, which raises
    GeneratorExit at the paused yield — and GeneratorExit is BaseException, so
    `except Exception` never sees it and the statements after the loop never run. The
    reply was lost AND the thread kept no session id, so the next message started a
    brand-new conversation and the agent had forgotten everything.
    """
    import anyio

    from forgecast.agent import assistant
    from forgecast.api import routes_agent

    thread = client.post("/api/agent/threads", json={}).json()

    async def fake_run(prompt, *, studio, resume=None, **kwargs):
        yield {"type": "session", "session_id": "sess-from-a-turn-that-was-cut-off"}
        yield {"type": "text", "text": "half an answer"}
        # Nothing after this is reached: the consumer abandons the stream here.
        await anyio.sleep(30)
        yield {"type": "text", "text": "the rest"}

    original = assistant.run
    assistant.run = fake_run
    try:
        with client.stream("POST", f"/api/agent/threads/{thread['id']}/chat",
                           json={"message": "hello"}) as response:
            # Read one chunk, then walk away — the browser equivalent of closing the
            # window or clicking a link while the agent is still working.
            next(response.iter_lines())
    finally:
        assistant.run = original

    stored = client.get(f"/api/agent/threads/{thread['id']}").json()
    # The session id must survive, or the next turn has no conversation to resume.
    assert stored["resumable"] is True
    # And the in-flight guard must be released, or the thread never talks again.
    assert thread["id"] not in routes_agent._IN_FLIGHT


def test_a_dead_session_id_does_not_brick_the_thread(client, user):
    """A resume= the CLI no longer has must be retried, not surfaced forever.

    It happens for ordinary reasons — the CLI's session store was cleared, the app
    moved machines. Without the retry every later message resumes the same dead id,
    fails identically, and the only escape is abandoning the conversation.
    """
    from forgecast.agent import assistant

    thread = client.post("/api/agent/threads", json={}).json()
    attempts: list[str | None] = []

    async def fake_run(prompt, *, studio, resume=None, **kwargs):
        attempts.append(resume)
        if resume:
            yield {"type": "error", "text": "No conversation found with session ID: x",
                   "resume_failed": True}
            return
        yield {"type": "session", "session_id": "brand-new"}
        yield {"type": "text", "text": "started over"}

    original = assistant.run
    assistant.run = fake_run
    try:
        client.post(f"/api/agent/threads/{thread['id']}/chat", json={"message": "one"})
        first = client.get(f"/api/agent/threads/{thread['id']}").json()
        assert first["resumable"] is True          # a session was recorded

        # Now that session is gone. The next turn must recover by itself.
        body = client.post(f"/api/agent/threads/{thread['id']}/chat",
                           json={"message": "two"}).text
    finally:
        assistant.run = original

    assert attempts == [None, "brand-new", None]   # tried, failed, retried clean
    assert "started over" in body
    assert "expired on this machine" in body       # and said so


def test_the_same_thread_refuses_two_turns_at_once(client, user):
    """Two windows on one conversation would both resume the same session id."""
    from forgecast.api import routes_agent

    thread = client.post("/api/agent/threads", json={}).json()
    routes_agent._IN_FLIGHT.add(thread["id"])
    try:
        clash = client.post(f"/api/agent/threads/{thread['id']}/chat",
                            json={"message": "second window"})
        assert clash.status_code == 409
        assert "still working" in clash.json()["detail"]
    finally:
        routes_agent._IN_FLIGHT.discard(thread["id"])


def test_a_pasted_screenshot_becomes_an_image_the_agent_can_see(client):
    """The clipboard gives you bytes and a MIME type and no filename.

    Uploaded as-is that is a nameless, extension-less file, and `describe()` tells the
    agent it has "a file" rather than an image it can open — so pasting a screenshot
    looked like it worked and then did nothing.
    """
    from forgecast.api.routes_agent import safe_name

    assert safe_name(None, "image/png") == "pasted.png"
    assert safe_name("", "image/png") == "pasted.png"
    assert safe_name("blob", "audio/wav") == "blob.wav"
    # Not just images — a copied audio file or document has to work too.
    assert safe_name(None, "audio/mpeg").endswith(".mp3")
    assert safe_name("report", "application/pdf") == "report.pdf"
    # A real name always wins over anything derived.
    assert safe_name("holiday photo.JPG", "image/png") == "holiday photo.JPG"
    # Traversal is stripped, and a dot-leading name keeps a usable stem.
    assert safe_name("../../etc/passwd", None) == "passwd"
    assert not safe_name(".env", None).startswith(".")

    # Over HTTP with the name browsers actually send for a clipboard blob. An
    # extension-less "blob" is what arrives when the page does not name the part, and
    # it has to come out the other side as an image rather than an opaque file.
    posted = client.post("/api/agent/attach",
                         files={"file": ("blob", b"\x89PNG\r\n\x1a\n", "image/png")})
    assert posted.status_code == 200
    body = posted.json()
    assert body["name"].endswith(".png")
    assert body["kind"] == "image"          # what makes the agent actually open it

    # And an audio paste, because "not only clipboard I should be able to paste
    # audio, files etc" is the actual requirement.
    audio = client.post("/api/agent/attach",
                        files={"file": ("blob", b"RIFF0000WAVE", "audio/wav")}).json()
    assert audio["name"].endswith(".wav")
    assert audio["kind"] == "audio"


def test_the_assistant_stream_does_not_yield_from_a_finally(user):
    """Yielding while unwinding raises "async generator ignored GeneratorExit".

    Which aborts teardown of the CLI subprocess. Asserted on the source because the
    failure only shows up when a generator is closed early — exactly the case that is
    hardest to notice and most likely in a desktop app.
    """
    import ast
    import inspect

    from forgecast.agent import assistant

    tree = ast.parse(inspect.getsource(assistant.run).lstrip())
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and node.finalbody:
            for inner in ast.walk(ast.Module(body=node.finalbody, type_ignores=[])):
                assert not isinstance(inner, ast.Yield), \
                    "run() must not yield from a finally block"


def test_the_cli_the_sdk_will_actually_run_is_the_one_we_report(monkeypatch):
    """"Is there something called claude" is the wrong question on Windows.

    npm's global install produces a `claude.cmd` shim, and the agent SDK refuses to
    spawn a batch script. Reporting that as connected produces the worst failure there
    is: setup goes green, the status chip says connected, and the first message dies
    with a batch-script refusal. So a shim counts as not found, and the fix offered is
    the native installer rather than the npm line that produced the shim.
    """
    from forgecast.agent import auth

    # The bundled binary in the wheel wins, because the SDK checks it before PATH —
    # which is why most installs need nothing at all.
    bundled = auth._bundled_cli()
    if bundled:
        assert auth.find_cli() == bundled

    # `auth.os` is replaced rather than `os.name` patched: setting the real os.name to
    # "nt" on Linux makes pathlib instantiate WindowsPath and takes the rest of the
    # session down with it.
    import os as real_os
    from types import SimpleNamespace

    monkeypatch.setattr(auth, "_bundled_cli", lambda: None)
    monkeypatch.setattr(auth, "os", SimpleNamespace(name="nt", environ=real_os.environ))
    monkeypatch.setattr(auth.shutil, "which",
                        lambda name: r"C:\npm\claude.cmd" if name == "claude" else None)
    assert auth.find_cli() is None                 # a shim is not a usable CLI
    assert auth.shim_only() is True

    report = auth.check()
    assert report.ok is False
    assert "cannot run directly" in report.headline
    joined = "\n".join(report.fixes)
    assert "install.ps1" in joined
    # And it must NOT tell you to run the thing that produced the shim.
    assert "npm install -g" not in joined


def test_every_line_reference_in_the_agent_docs_still_resolves():
    """Documentation that cites line numbers rots the moment code moves.

    `docs/AGENT.md` is built out of `file:line` citations because the non-obvious
    decisions already carry comments naming the failure they prevent, and pointing at
    those beats restating them. The cost is that an insertion twenty lines up makes the
    document quietly wrong — and a maintainer who opens two stale references stops
    trusting the rest of it.

    Only the file and the line's existence are checked. Asserting on the *content* of a
    line would make every reformat a test failure, which is how a guard like this gets
    deleted.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    doc = root / "docs" / "AGENT.md"
    if not doc.exists():                       # the docs are optional in a slim checkout
        pytest.skip("docs/AGENT.md is not present")

    text = doc.read_text(encoding="utf-8")
    # A bare filename in this document means the agent module of that name — the header
    # says so, because there are two auth.py files and only one of them is the agent's.
    search_roots = [root / "forgecast" / "agent", root / "forgecast" / "api",
                    root / "forgecast", root / "tests", root]

    problems: list[str] = []
    seen = 0
    for name, line in re.findall(r"`?([A-Za-z_][\w./]*\.(?:py|md)):(\d+)", text):
        seen += 1
        # Tried as written against each root first, so a partial path like
        # `desktop/bootstrap.py` resolves, then by basename for the bare form.
        target = None
        for base in search_roots:
            for candidate in (base / name, base / Path(name).name):
                if candidate.is_file():
                    target = candidate
                    break
            if target is not None:
                break
        if target is None:
            problems.append(f"{name}:{line} — no such file")
            continue
        total = len(target.read_text(encoding="utf-8").splitlines())
        if int(line) > total:
            problems.append(f"{name}:{line} — past the end of {target.name} "
                            f"({total} lines)")

    assert seen > 20, f"only {seen} citations found; the parser is probably wrong"
    assert not problems, "stale references in docs/AGENT.md:\n  " + "\n  ".join(problems)
