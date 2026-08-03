"""The smoke script's own checks, run against the TestClient instead of a live server.

`tools/smoke.py` is the thing that says a built install works, which makes it the one
script whose failure is invisible: a check that can never fail sits there printing "pass"
forever and the release it was guarding goes out broken. So these tests do two things,
and the second is the one that matters.

1. Every check passes against the app as it is. That is a real assertion — most of them
   fail if a route, a template or a static file goes missing.
2. Every check *fails* when the answer is wrong. Each one is handed a stub client
   returning a specific plausible lie, and the check has to catch it. A check that passes
   both halves of that is a check worth running.

The TestClient rather than a subprocess on purpose. `serve()` is the one part not
exercised here — starting a real uvicorn in a unit test makes the suite depend on a free
port, a cold start and a clean shutdown, which is three ways for an unrelated commit to
go red. What it does is asserted structurally instead, at the bottom of this file.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from forgecast.api.main import create_app

SMOKE_PATH = Path(__file__).resolve().parents[1] / "tools" / "smoke.py"


def load_smoke():
    """Import `tools/smoke.py` by path.

    `tools/` is deliberately not a package — it is a folder of scripts, and `package.py`
    is run as one — so there is nothing to import normally. Loading by path keeps that
    true rather than adding an `__init__.py` to make a test tidier.
    """
    spec = importlib.util.spec_from_file_location("forgecast_smoke", SMOKE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered before it is executed, not after. `@dataclass` looks its own module up in
    # `sys.modules` while deciding whether an annotation is `KW_ONLY`, and finding nothing
    # there fails with an `AttributeError` on `None` that says nothing about the cause.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


smoke = load_smoke()


@pytest.fixture
def client(user):
    """A signed-in TestClient, authenticated the way the script authenticates.

    Through `smoke.sign_in` rather than by setting a header directly, so the sign-in path
    the script actually uses is covered too — a login endpoint that changed shape would
    otherwise break the script and pass the tests.
    """
    with TestClient(create_app()) as test_client:
        smoke.sign_in(test_client, user.email, "supersecret")
        yield test_client


# ------------------------------------------------------- the checks against the real app


def test_every_check_passes_against_the_app(client):
    results = smoke.run_checks(client)
    failed = [f"{result.name}: {result.detail}" for result in results if not result.ok]
    assert not failed, "\n".join(failed)
    # Every check has to say what it saw. A blank detail means a check that reports a tick
    # and nothing else, which is useless the moment a later one fails.
    assert all(result.detail.strip() for result in results)


def test_report_returns_zero_only_when_everything_passed(capsys):
    passing = [smoke.Result("a", True, "saw a thing")]
    assert smoke.report(passing) == 0

    mixed = [smoke.Result("a", True, "saw a thing"),
             smoke.Result("b", False, "did not see the other thing")]
    assert smoke.report(mixed) == 1
    printed = capsys.readouterr().out
    # The failure and its reason both have to be in the output, or the exit code is the
    # only information the operator gets.
    assert "did not see the other thing" in printed
    assert "FAIL" in printed


def test_the_checks_cover_what_the_script_claims_to_check(client):
    """The named checks, and no silently dropped ones.

    `CHECKS` is a hand-written tuple, so a check can be defined and never registered —
    which presents as a green run that never looked at the thing that broke.
    """
    registered = {check.run for check in smoke.CHECKS}
    defined = {value for name, value in vars(smoke).items()
               if name.startswith("check_") and callable(value)}
    assert defined == registered
    assert len(smoke.CHECKS) == len(defined)


# ------------------------------------------------------ the checks against wrong answers


class Stub:
    """A client that answers whatever the test says, for one route at a time.

    Only the four verbs the checks use. Anything not in `answers` falls through to the
    real client, so a test can break exactly one endpoint and leave the rest working —
    which is how a genuine regression arrives.
    """

    def __init__(self, real, answers: dict):
        self._real = real
        self._answers = answers

    def _dispatch(self, verb: str, url: str, **kwargs):
        for path, response in self._answers.items():
            if url.split("?")[0] == path:
                return response
        return getattr(self._real, verb)(url, **kwargs)

    def get(self, url, **kwargs):
        return self._dispatch("get", url, **kwargs)

    def post(self, url, **kwargs):
        return self._dispatch("post", url, **kwargs)

    def patch(self, url, **kwargs):
        return self._dispatch("patch", url, **kwargs)

    def delete(self, url, **kwargs):
        return self._dispatch("delete", url, **kwargs)


class Canned:
    """The parts of an httpx response the checks read."""

    def __init__(self, payload, status_code: int = 200, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text or payload is None else json.dumps(payload)
        self.content = self.text.encode()
        self.request = type("R", (), {"url": type("U", (), {"path": "/stubbed"})()})()

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def fails(check, client, answers: dict) -> str:
    """Run one check against a lie and return the complaint, insisting there is one."""
    with pytest.raises(smoke.Wrong) as raised:
        check(Stub(client, answers))
    return str(raised.value)


def test_serving_check_fails_when_the_app_is_not(client):
    complaint = fails(smoke.check_serving, client,
                      {"/healthz": Canned(None, 502, text="Bad Gateway")})
    assert "502" in complaint


def test_healthz_check_fails_on_an_incoherent_report(client):
    assert "ok=False" in fails(smoke.check_healthz, client,
                               {"/healthz": Canned({"ok": False, "provider_mode": "mock",
                                                    "ffmpeg": True})})
    # A provider mode nobody implements is how a typo in configuration presents.
    assert "provider_mode" in fails(
        smoke.check_healthz, client,
        {"/healthz": Canned({"ok": True, "provider_mode": "moc", "ffmpeg": True})})
    # ffmpeg reported as a string reads as present to anything that tests truthiness.
    assert "ffmpeg" in fails(
        smoke.check_healthz, client,
        {"/healthz": Canned({"ok": True, "provider_mode": "mock", "ffmpeg": "yes"})})
    # An HTML error page where JSON was expected has to be named, not decoded.
    assert "not JSON" in fails(smoke.check_healthz, client,
                               {"/healthz": Canned(None, 200, text="<html>nope</html>")})


def test_chat_page_check_fails_when_the_page_lost_the_chat(client):
    """The two failures a missing shipped file actually produces."""
    real = client.get("/").text
    assert "without the chat itself" in fails(
        smoke.check_chat_page, client,
        {"/": Canned(None, 200, text=real.replace('id="chat"', 'id="something-else"'))})
    assert "chat.js" in fails(
        smoke.check_chat_page, client,
        {"/": Canned(None, 200, text=real.replace("/static/chat.js", "/static/gone.js"))})
    # A static mount resolved from the working directory serves the page and 404s the
    # script, which is the shipped-install version of this and looks like nothing at all.
    assert "static mount" in fails(smoke.check_chat_page, client,
                                   {"/static/chat.js": Canned(None, 404)})
    # And a signed-out client gets a redirect, which must not read as a broken page.
    assert "not signed in" in fails(smoke.check_chat_page, client, {"/": Canned(None, 303)})


def test_setup_check_fails_when_the_toolchain_is_not_reported(client):
    assert "no toolchain" in fails(smoke.check_setup_state, client,
                                   {"/api/setup/state": Canned({"tools": [],
                                                                "ready": True})})
    # A report that omits the two tools the app installs is a setup page offering nothing.
    thin = {"tools": [{"key": "node", "label": "Node.js", "present": True}],
            "ready": True}
    assert "ffmpeg" in fails(smoke.check_setup_state, client,
                             {"/api/setup/state": Canned(thin)})
    # `present` as a string is truthy whatever it says, so "false" would read as found.
    lying = {"tools": [{"key": "ffmpeg", "label": "ffmpeg", "present": "false"},
                       {"key": "claude", "label": "CLI", "present": True}],
             "ready": True}
    assert "not a boolean" in fails(smoke.check_setup_state, client,
                                    {"/api/setup/state": Canned(lying)})


def test_auth_check_catches_the_contradiction_it_exists_for(client):
    """Connected, and also offering a sign-in button. This shipped once."""
    contradiction = {"ok": True, "headline": "Connected with your Claude subscription",
                     "detail": "", "cli_found": True, "signed_in": True,
                     "can_login": True, "fixes": []}
    complaint = fails(smoke.check_agent_auth, client,
                      {"/api/agent/auth": Canned(contradiction)})
    assert "sign-in button" in complaint

    # Connected without anyone having signed in: the CLI being present treated as the CLI
    # being signed in, which is the same bug reached from the other side.
    assert "without anyone being signed in" in fails(
        smoke.check_agent_auth, client,
        {"/api/agent/auth": Canned({**contradiction, "can_login": False,
                                    "signed_in": False})})

    # A refusal with no fix and no button tells the operator no and nothing else.
    assert "neither a fix" in fails(
        smoke.check_agent_auth, client,
        {"/api/agent/auth": Canned({"ok": False, "headline": "Not signed in yet",
                                    "detail": "", "cli_found": True, "signed_in": False,
                                    "can_login": False, "fixes": []})})

    assert "missing" in fails(smoke.check_agent_auth, client,
                              {"/api/agent/auth": Canned({"ok": True})})


def test_auth_check_accepts_an_honest_refusal(client):
    """Not connected is a valid install, and must not be reported as a failure.

    Everything except the chat and rendering works without the CLI. A smoke check that
    demanded a Claude subscription would fail on every CI machine and be switched off.
    """
    refusal = {"ok": False, "headline": "The Claude Code CLI is not installed",
               "detail": "The agent drives the Claude Code CLI.", "cli_found": False,
               "signed_in": False, "can_login": False,
               "fixes": ["npm install -g @anthropic-ai/claude-code"]}
    saw = smoke.check_agent_auth(Stub(client, {"/api/agent/auth": Canned(refusal)}))
    assert "not installed" in saw


def test_thread_check_fails_when_the_round_trip_does_not_survive(client):
    made = client.post("/api/agent/threads", json={}).json()
    try:
        # A create that answers without an id: the tables are missing, or the commit was
        # rolled back and the row never got one.
        assert "without an id" in fails(smoke.check_thread_round_trip, client,
                                        {"/api/agent/threads": Canned({"title": "New chat"})})
        # The rename read back as the old title — a session that was never committed.
        assert "did not survive" in fails(
            smoke.check_thread_round_trip, client,
            {f"/api/agent/threads/{made['id'] + 1}": Canned({"title": "New chat",
                                                             "messages": []})})
    finally:
        client.delete(f"/api/agent/threads/{made['id']}")


def test_attachment_check_fails_when_the_kind_is_wrong(client):
    """kind is what decides whether the agent opens the file or ignores it."""
    complaint = fails(smoke.check_attachment, client,
                      {"/api/agent/attach": Canned({"name": "blob", "kind": "file",
                                                    "size": 8, "path": "/tmp/blob"})})
    assert "cannot open it" in complaint

    # A derived extension is the whole reason a clipboard paste works at all.
    assert "no extension" in fails(
        smoke.check_attachment, client,
        {"/api/agent/attach": Canned({"name": "blob", "kind": "image", "size": 8,
                                      "path": "/tmp/blob"})})

    assert "413" in fails(smoke.check_attachment, client,
                          {"/api/agent/attach": Canned(None, 413, text="too big")})


def test_the_attachment_check_leaves_nothing_behind(client):
    """It runs against installs people use, so it has to clean up after itself."""
    from forgecast.api.routes_agent import attach_dir

    before = {path.name for path in attach_dir().iterdir()}
    smoke.check_attachment(client)
    assert {path.name for path in attach_dir().iterdir()} == before


def test_the_thread_check_leaves_nothing_behind(client):
    before = client.get("/api/agent/threads").json()["threads"]
    smoke.check_thread_round_trip(client)
    assert client.get("/api/agent/threads").json()["threads"] == before


def test_the_research_check_accepts_both_honest_states(client):
    """An open box and a shut box that names the fix are both fine."""
    open_box = '<input id="channel" placeholder="@handle">'
    assert "open" in smoke.check_research_can_fetch(
        Stub(client, {"/research": Canned(None, 200, text=open_box)})
    )

    shut_with_a_way_out = (
        '<input id="channel" disabled>'
        "<p>yt-dlp is not installed. Install it with pip install yt-dlp.</p>"
    )
    assert "names the fix" in smoke.check_research_can_fetch(
        Stub(client, {"/research": Canned(None, 200, text=shut_with_a_way_out)})
    )


def test_the_research_check_fails_on_a_dead_end(client):
    """The original complaint: disabled, with nothing saying what would enable it."""
    dead_end = '<input id="channel" disabled><p>Fetching is unavailable.</p>'
    complaint = fails(smoke.check_research_can_fetch, client,
                      {"/research": Canned(None, 200, text=dead_end)})
    assert "reads as the feature being broken" in complaint

    # And a page with no box at all is a different failure with its own sentence.
    assert "no channel box" in fails(
        smoke.check_research_can_fetch, client,
        {"/research": Canned(None, 200, text="<h1>Research</h1>")},
    )


# ------------------------------------------------------------------ the parts around them


def test_a_closed_instance_is_told_how_to_make_an_account(client, monkeypatch):
    """Signup being closed is the shipped default, not a failure to paper over.

    The message has to name `forgecast bootstrap`, because the alternative is an operator
    concluding the app is broken when it is behaving exactly as configured.
    """
    from forgecast.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "allow_signup", False)
    with pytest.raises(smoke.Wrong) as raised:
        smoke.sign_in(client, "nobody@example.com", "not-a-real-password")
    assert "forgecast bootstrap" in str(raised.value)


def test_a_check_that_explodes_is_reported_rather_than_raised(client):
    """A shipped install fails in ways this script did not predict.

    An exception escaping `run_checks` would abandon every later check and the cleanup
    inside them, so anything that is not a `Wrong` still has to come back as a result.
    """
    def explodes(_client):
        raise RuntimeError("the proxy hung up")

    results = smoke.run_checks(client, (smoke.Check("boom", explodes),))
    assert [(result.name, result.ok) for result in results] == [("boom", False)]
    assert "RuntimeError: the proxy hung up" in results[0].detail


def test_the_server_it_starts_is_a_real_one(client):
    """`serve()` must run uvicorn in a subprocess, not the app in this process.

    Asserted on the source because starting a real server here would make the suite depend
    on a free port and a clean shutdown. The reason it matters: half of what the script
    checks is the start-up that only happens in a real server — the lifespan hook that
    runs `init_db`, creates `storage/` and binds the runner's loop. A `TestClient` inside
    `serve()` would skip the part most likely to be broken in a shipped install, and every
    check downstream would still pass.
    """
    import ast

    tree = ast.parse(SMOKE_PATH.read_text(encoding="utf-8"))
    found = next(node for node in ast.walk(tree)
                 if isinstance(node, ast.FunctionDef) and node.name == "serve")
    # The docstring is dropped before matching. Asserting against prose means a comment
    # explaining why something is not done can satisfy a test that it is done.
    code = ast.unparse(ast.Module(body=found.body[1:], type_ignores=[]))
    assert "uvicorn" in code
    assert "subprocess.Popen" in code
    assert "TestClient" not in code
    # And it has to stop what it started, however badly that goes.
    assert "terminate()" in code and "kill()" in code


def test_it_creates_its_own_account_only_when_it_owns_the_server():
    """The split that keeps this script safe to point at a real install.

    Starting its own server means it owns that instance, so creating the account it
    signs in as is correct — and necessary, because registration is closed on a shipped
    install and every check would otherwise stop at the sign-in having verified nothing.
    Pointed at someone else's server with `--url`, it must create nothing at all.
    """
    import inspect

    from tools import smoke

    # `serve()` bootstraps; nothing else does.
    assert "ensure_account" in inspect.getsource(smoke.serve)
    creators = [
        name for name, fn in vars(smoke).items()
        if callable(fn) and getattr(fn, "__module__", "") == smoke.__name__
        and name not in ("serve", "ensure_account")
        and "ensure_account" in inspect.getsource(fn)
    ]
    assert creators == [], f"{creators} also create an account"

    # And `serve()` is only entered when no --url was given.
    main = inspect.getsource(smoke.main)
    assert "args.url.rstrip" in main
    assert "or stack.enter_context" in main


def test_a_failing_check_makes_the_script_exit_non_zero():
    """A smoke script that reports failures and exits 0 is worse than none.

    It would go green in CI while the install is broken, which is the one outcome that
    makes the whole thing pointless.
    """
    from tools import smoke

    passed = smoke.Result(name="fine", ok=True, detail="saw it")
    failed = smoke.Result(name="broken", ok=False, detail="did not")
    assert smoke.report([passed]) == 0
    assert smoke.report([passed, failed]) == 1
    assert smoke.report([]) != 0            # nothing checked is not success
