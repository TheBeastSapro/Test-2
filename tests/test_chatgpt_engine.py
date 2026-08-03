"""ChatGPT as the second agent, and Claude staying exactly as it was.

Like `test_agent.py`, this asserts everything up to and including the point where the
real agent loop would start, plus the honest refusal when it cannot. A ChatGPT turn
needs OpenAI's Codex CLI installed *and* a ChatGPT sign-in, and a test machine has
neither — so the turn itself is driven against a stand-in CLI that replays the JSONL a
real one printed, which is the part this app has to translate correctly.

The recorded streams below are verbatim from codex-cli 0.146.0. The failing one in
particular: fifteen error events and about twenty seconds of retries is what an
unauthenticated turn actually looks like, and it is the first thing an operator will
see, so it is the case with the most tests.
"""

from __future__ import annotations

import json
import os
import sys
import textwrap

import pytest
from fastapi.testclient import TestClient

from forgecast.agent import codex_agent, codex_auth, engines, prefs
from forgecast.api.main import create_app


@pytest.fixture
def client(user):
    with TestClient(create_app()) as test_client:
        token = test_client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "supersecret"},
        ).json()["access_token"]
        test_client.headers["Authorization"] = f"Bearer {token}"
        yield test_client


# --------------------------------------------------------------- Claude is untouched


def test_a_fresh_install_still_talks_to_claude():
    """The whole promise of the setting: not touching it changes nothing."""
    assert prefs.Prefs().engine == "claude"
    assert engines.DEFAULT == "claude"
    assert engines.current(prefs.Prefs()).key == "claude"
    assert engines.resolve(None).key == "claude"
    # Including values that could only come from a newer build or a corrupted file.
    assert engines.resolve("gpt-9").key == "claude"
    assert engines.resolve("").key == "claude"


def test_the_default_engine_runs_the_claude_implementation(user, monkeypatch):
    from forgecast.agent import assistant
    from forgecast.agent.studio import Studio

    called: list[dict] = []

    async def fake_claude(prompt, *, studio, **kwargs):
        called.append(kwargs)
        yield {"type": "text", "text": "claude answered"}

    async def fake_codex(prompt, *, studio, **kwargs):  # pragma: no cover
        raise AssertionError("the default engine must not reach Codex")
        yield {}

    monkeypatch.setattr(assistant, "run", fake_claude)
    monkeypatch.setattr(codex_agent, "run", fake_codex)

    async def drain():
        return [event async for event in engines.run(
            "hello", studio=Studio(user_id=user.id), settings=prefs.Prefs())]

    import anyio

    events = anyio.run(drain)
    assert events == [{"type": "text", "text": "claude answered"}]
    # The Claude-only options still arrive, and the ChatGPT-only one does not leak into
    # ClaudeAgentOptions as an unexpected keyword.
    assert called[0]["model"] == prefs.Prefs().model
    assert "user_id" not in called[0]


def test_selecting_chatgpt_runs_the_codex_implementation(user, monkeypatch):
    from forgecast.agent import assistant
    from forgecast.agent.studio import Studio

    seen: list[dict] = []

    async def fake_claude(prompt, *, studio, **kwargs):  # pragma: no cover
        raise AssertionError("chatgpt must not reach the Claude CLI")
        yield {}

    async def fake_codex(prompt, *, studio, **kwargs):
        seen.append(kwargs)
        yield {"type": "text", "text": "chatgpt answered"}

    monkeypatch.setattr(assistant, "run", fake_claude)
    monkeypatch.setattr(codex_agent, "run", fake_codex)

    async def drain():
        return [event async for event in engines.run(
            "hello", studio=Studio(user_id=user.id),
            settings=prefs.Prefs(engine="chatgpt"), user_id=user.id)]

    import anyio

    assert anyio.run(drain) == [{"type": "text", "text": "chatgpt answered"}]
    assert seen[0]["model"] == prefs.Prefs().chatgpt_model
    assert seen[0]["user_id"] == user.id


# ---------------------------------------------------------------- models per engine


def test_each_engine_keeps_its_own_model_choice():
    """One flat picker would either lose a choice or send a model to the wrong vendor."""
    settings = prefs.Prefs()
    assert settings.model_for("claude").startswith("claude-")
    assert settings.model_for("chatgpt").startswith("gpt-")

    settings.set_model_for("chatgpt", "gpt-5.6-sol")
    assert settings.chatgpt_model == "gpt-5.6-sol"
    # And Claude's pick is untouched by it, so switching back does not lose it.
    assert settings.model == prefs.Prefs().model


def test_no_engine_offers_the_other_ones_models():
    claude = {m["id"] for m in engines.BY_KEY["claude"].models}
    chatgpt = {m["id"] for m in engines.BY_KEY["chatgpt"].models}
    assert not claude & chatgpt
    assert engines.BY_KEY["chatgpt"].default_model in chatgpt
    assert engines.BY_KEY["claude"].default_model in claude


def test_prefs_endpoint_offers_both_agents_and_only_the_current_models(client):
    body = client.get("/api/agent/prefs").json()
    assert body["engine"] == "claude"
    # Claude first and ChatGPT second, with any later backends after them. Pinned as a
    # prefix rather than the whole list: the order of the first two is the product
    # decision — Claude is the default and ChatGPT the named alternative — while adding a
    # third (MiniMax) is not a change to that decision and should not fail this.
    keys = [e["key"] for e in body["engines"]]
    assert keys[:2] == ["claude", "chatgpt"]
    assert len(keys) == len(set(keys))
    assert {m["id"] for m in body["models"]} == {
        m["id"] for m in engines.BY_KEY["claude"].models}

    # Every engine has to state how it signs in, because that is the thing being
    # chosen between — and neither of them may claim to want a key.
    for entry in body["engines"]:
        assert "subscription" in entry["signin"].lower() or "plan" in entry["signin"].lower()
        assert "no api key" in entry["signin"].lower()


def test_switching_engine_switches_the_model_list(client):
    switched = client.post("/api/agent/prefs", json={"engine": "chatgpt"}).json()
    assert switched["engine"] == "chatgpt"
    assert switched["model"].startswith("gpt-")
    assert {m["id"] for m in switched["models"]} == {
        m["id"] for m in engines.BY_KEY["chatgpt"].models}
    assert prefs.load().engine == "chatgpt"
    # Claude's stored model is not overwritten by the switch.
    assert prefs.load().model.startswith("claude-")

    assert client.get("/api/agent/prefs").json()["model"].startswith("gpt-")


def test_a_model_is_rejected_for_the_wrong_agent(client):
    unknown = client.post("/api/agent/prefs", json={"engine": "gemini"})
    assert unknown.status_code == 400

    wrong = client.post("/api/agent/prefs",
                        json={"engine": "chatgpt", "model": "claude-opus-5"})
    assert wrong.status_code == 400
    assert "ChatGPT" in wrong.json()["detail"]

    # And the pair the page actually sends when it switches both at once is accepted.
    ok = client.post("/api/agent/prefs",
                     json={"engine": "chatgpt", "model": "gpt-5.6-luna"})
    assert ok.status_code == 200
    assert prefs.load().chatgpt_model == "gpt-5.6-luna"


def test_what_only_claude_can_do_is_stated_rather_than_hidden(client):
    chatgpt = next(e for e in client.get("/api/agent/prefs").json()["engines"]
                   if e["key"] == "chatgpt")
    limits = "\n".join(chatgpt["limits"]).lower()
    # The toggle that has no effect on this backend, and the tool it is never given.
    assert "confirm calls" in limits
    assert "decide_gate" in limits
    assert engines.BY_KEY["claude"].limits == []


# ------------------------------------------------------------------- the sign-in


def test_the_auth_report_has_one_shape_for_both_agents(client):
    for engine in ("", "claude", "chatgpt"):
        report = client.get(f"/api/agent/auth?engine={engine}").json()
        assert set(report) >= {"ok", "headline", "detail", "cli_found", "can_login",
                               "engine"}
        # Whatever this machine's state, it cannot claim to be connected while also
        # offering the sign-in button.
        assert not (report["ok"] and report["can_login"])


def test_a_missing_codex_cli_says_so_and_says_claude_still_works(client, monkeypatch):
    monkeypatch.setattr(codex_auth, "find_cli", lambda: None)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)

    report = client.get("/api/agent/auth?engine=chatgpt").json()
    assert report["ok"] is False
    assert report["engine"] == "chatgpt"
    assert "not installed" in report["headline"]
    joined = report["detail"] + "\n".join(report["fixes"])
    assert "npm install -g @openai/codex" in joined
    # The way out that costs nothing: the other agent needs no install.
    assert "claude" in joined.lower()


def test_not_signed_in_offers_the_button_and_names_the_browser_flow(monkeypatch):
    monkeypatch.setattr(codex_auth, "find_cli", lambda: ["/usr/bin/codex"])
    monkeypatch.setattr(codex_auth, "login_state",
                        lambda cli=None: codex_auth.LoginState(False, detail="Not logged in"))
    monkeypatch.delenv("CODEX_API_KEY", raising=False)

    report = codex_auth.check()
    assert report.ok is False
    assert report.can_login is True
    assert "browser" in report.detail
    # It must not tell anyone to create a key, which is the whole point.
    assert "should not create one" in report.detail
    assert any("device-auth" in fix for fix in report.fixes)


def test_an_environment_api_key_is_reported_before_anything_is_spent(monkeypatch):
    """The trap Codex's own `login status` does not reveal.

    With CODEX_API_KEY set, `codex login status` still prints "Not logged in" while a
    turn authenticates with the key and bills an API account. Measured on 0.146.0: the
    401 changes from "Missing bearer" to "Incorrect API key provided", which is proof
    the key was used. So the environment is checked here rather than trusted to the CLI.
    """
    monkeypatch.setattr(codex_auth, "find_cli", lambda: ["/usr/bin/codex"])
    monkeypatch.setenv("CODEX_API_KEY", "")            # empty still counts as set

    report = codex_auth.check()
    assert report.ok is False
    assert report.api_key_shadowing is True
    assert "plan you already pay for" in report.detail
    assert any("unset CODEX_API_KEY" in fix for fix in report.fixes)


def test_an_unrelated_openai_key_is_not_treated_as_a_problem(monkeypatch):
    """The pipeline's own OpenAI key lives in the same environment.

    `OPENAI_API_KEY` does not shadow the Codex sign-in on 0.146.0 — verified by a turn
    still failing with "Missing bearer" while it was set — so refusing to start because
    it exists would be a false alarm on a correctly configured machine.
    """
    monkeypatch.setattr(codex_auth, "find_cli", lambda: ["/usr/bin/codex"])
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-for-the-render-pipeline")
    monkeypatch.setattr(codex_auth, "login_state",
                        lambda cli=None: codex_auth.LoginState(True, account="you@example.test"))

    report = codex_auth.check()
    assert report.ok is True
    assert report.api_key_shadowing is False
    assert "subscription" in report.headline.lower()


def test_a_key_based_sign_in_is_allowed_but_says_what_it_costs(monkeypatch):
    monkeypatch.setattr(codex_auth, "find_cli", lambda: ["/usr/bin/codex"])
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    monkeypatch.setattr(
        codex_auth, "login_state",
        lambda cli=None: codex_auth.LoginState(True, account="API key",
                                               with_api_key=True))
    report = codex_auth.check()
    # It works, so it is not an error — but the money has to be on screen.
    assert report.ok is True
    assert "per token" in report.detail
    assert "codex logout" in report.detail


def test_login_state_never_raises_when_the_cli_misbehaves(monkeypatch, tmp_path):
    """A CLI that is not there, or that fails, is "not signed in" — not a 500."""
    monkeypatch.setattr(codex_auth, "find_cli", lambda: None)
    assert codex_auth.login_state().signed_in is False

    missing = tmp_path / "not-a-program"
    assert codex_auth.login_state([str(missing)]).signed_in is False


def test_login_status_is_read_rather_than_probed_with_a_turn(monkeypatch):
    """The reason this is a subprocess and not a prompt.

    An unauthenticated `codex exec` spends about twenty seconds on ten retries and
    prints fifteen error events before failing. `codex login status` answers in ~120 ms
    and costs nothing, which is the same trade `auth._credentials()` makes by reading
    Claude's credential off disk.
    """
    calls: list[list[str]] = []

    class Done:
        returncode = 0
        stdout = "Logged in using ChatGPT (you@example.test)"
        stderr = ""

    def fake_run(argv, **kwargs):
        calls.append(argv)
        assert kwargs.get("timeout")            # a wedged CLI cannot hang the page
        return Done()

    monkeypatch.setattr(codex_auth.subprocess, "run", fake_run)
    state = codex_auth.login_state(["/usr/bin/codex"])
    assert calls == [["/usr/bin/codex", "login", "status"]]
    assert state.signed_in is True
    assert state.account == "ChatGPT (you@example.test)"
    assert state.with_api_key is False


# ------------------------------------------------------- the Windows shim, again


def test_a_windows_shim_is_never_spawned_as_a_batch_file(tmp_path):
    """`auth._spawnable()` exists for Claude; this is the same trap for Codex.

    npm's install produces `codex.cmd`, and Python's CreateProcess cannot execute a
    `.cmd` — it raises WinError 193, which reads like a corrupt install rather than a
    wrapper script. Unlike Claude's case it is fixable, because this app does the
    spawning: the real entry point sits beside the shim.
    """
    shim = tmp_path / "codex.cmd"
    shim.write_text("@echo off\r\n")
    entry = tmp_path / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
    entry.parent.mkdir(parents=True)
    entry.write_text("#!/usr/bin/env node\n")

    argv = codex_auth._argv(str(shim))
    assert argv[-1] == str(entry)
    assert not argv[0].lower().endswith((".cmd", ".bat"))

    # With no package beside it there is nothing to run directly, and `cmd /c` is the
    # only thing left — still not a bare batch spawn.
    lonely = tmp_path / "elsewhere" / "codex.cmd"
    lonely.parent.mkdir()
    lonely.write_text("@echo off\r\n")
    assert codex_auth._argv(str(lonely)) == ["cmd", "/c", str(lonely)]

    # A real executable is passed through untouched.
    assert codex_auth._argv("/usr/local/bin/codex") == ["/usr/local/bin/codex"]


# --------------------------------------------------------------- the command line


def test_the_command_never_writes_to_the_operators_codex_config():
    argv = codex_agent.build_command(cli=["codex"], model="gpt-5.6-terra", user_id=7)
    joined = " ".join(argv)

    # The tools are registered per invocation. `codex mcp add` would edit a file the
    # operator wrote and leak this app's tools into every unrelated codex session.
    assert "mcp_servers.forgecast.command=" in joined
    assert "-m" not in [a for a in argv if a == "mcp"]
    assert "mcp" not in argv
    assert "add" not in argv
    # And their own config cannot silently change what this agent may do.
    assert "--ignore-user-config" in argv
    assert "--json" in argv
    assert "--skip-git-repo-check" in argv
    assert argv[-1] == "-"                     # the prompt goes on stdin, not in argv
    assert "FORGECAST_AGENT_USER_ID=\"7\"" in joined
    assert '-m' in argv and 'gpt-5.6-terra' in argv


def test_no_model_flag_when_nothing_was_chosen():
    """An empty `-m` overrides the CLI's own default with nothing."""
    argv = codex_agent.build_command(cli=["codex"], model=None)
    assert "-m" not in argv


def test_a_resumed_turn_drops_the_flags_resume_does_not_accept():
    """`codex exec resume` takes neither -C nor -s on 0.146.0.

    Passing them is not a warning, it is `error: unexpected argument` — a thread that
    works on its first message and dies on its second.
    """
    fresh = codex_agent.build_command(cli=["codex"])
    resumed = codex_agent.build_command(cli=["codex"], resume="019fc7ef-1fb2-7003")

    assert "-C" in fresh and "-s" not in fresh
    assert "-C" not in resumed
    assert resumed[1:4] == ["exec", "resume", "019fc7ef-1fb2-7003"]
    # The sandbox is still applied, as config, which resume does accept.
    assert any(a.startswith("sandbox_mode=") for a in resumed)


def test_the_tool_server_runs_this_virtual_environment():
    argv = codex_agent.build_command(cli=["codex"])
    joined = " ".join(argv)
    assert json.dumps(sys.executable) in joined
    assert "forgecast.agent.mcp_stdio" in joined


def test_no_api_key_is_ever_handed_to_the_cli(monkeypatch):
    """Both keys are stripped from the child's environment.

    `codex_auth.check()` already refuses to start while CODEX_API_KEY is set; this is
    the second lock on the same door, for a variable that appears after the check.
    ANTHROPIC_API_KEY stays unset for the reason `auth.py` is entirely about.
    """
    monkeypatch.setenv("CODEX_API_KEY", "sk-should-not-travel")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-travel")
    env = codex_agent._environment()
    assert "CODEX_API_KEY" not in env
    assert "ANTHROPIC_API_KEY" not in env


# ------------------------------------------------------- the tools, defined once


def test_the_stdio_transport_serves_the_same_tools_and_not_the_gate():
    """One definition, two transports.

    The alternative — writing the twenty-one tools out again as function schemas for
    the second backend — is two lists that drift, and only one of them gets the fix.
    """
    from forgecast.agent import mcp_stdio, tools

    served = mcp_stdio.served_tools()
    assert "studio_status" in served
    assert "start_run" in served
    # Approving a gate releases real spend, and `codex exec` has nobody to ask.
    assert "decide_gate" not in served
    assert served == {name.rsplit("__", 1)[-1] for name in tools.ALLOWED}


def test_the_stdio_server_answers_a_real_mcp_handshake(tmp_path):
    """Spawned for real, because the failure this catches is a stray byte on stdout.

    Stdout is the protocol. A logging handler pointed at stdout lands in the middle of
    a JSON-RPC frame, and the CLI reports a server that would not start — naming none
    of that.
    """
    import subprocess

    # Written and read a frame at a time, with stdin held open — which is what a real
    # client does. Piping everything in at once and closing closes the read side at
    # EOF, and the session tears down with the last request still in flight.
    server = subprocess.Popen(
        [sys.executable, "-m", "forgecast.agent.mcp_stdio"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, cwd=str(codex_agent.APP_ROOT),
        env={**os.environ, "FORGECAST_AGENT_USER_ID": "1"},
    )

    def ask(message, expect_reply=True):
        server.stdin.write(json.dumps(message) + "\n")
        server.stdin.flush()
        return json.loads(server.stdout.readline()) if expect_reply else None

    try:
        by_id = {}
        by_id[1] = ask({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                   "clientInfo": {"name": "test", "version": "1"}}})
        ask({"jsonrpc": "2.0", "method": "notifications/initialized"},
            expect_reply=False)
        by_id[2] = ask({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        by_id[3] = ask({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": "decide_gate", "arguments": {"run_id": 1}}})
    finally:
        server.stdin.close()
        try:
            server.wait(timeout=30)
        except subprocess.TimeoutExpired:                          # pragma: no cover
            server.kill()

    # A clean exit when the pipe goes away, not a traceback in the operator's log.
    assert server.returncode == 0

    assert by_id[1]["result"]["serverInfo"]["name"] == "forgecast"
    listed = {tool["name"] for tool in by_id[2]["result"]["tools"]}
    assert "studio_status" in listed
    assert "decide_gate" not in listed
    # Hidden is not a boundary: a model that learned the name anyway must be refused.
    refused = by_id[3]["result"]
    assert refused["isError"] is True
    assert "not available" in json.dumps(refused)
    # And every schema arrives — a tool with no parameters is not a tool with none.
    schemas = {t["name"]: t["inputSchema"] for t in by_id[2]["result"]["tools"]}
    assert schemas["create_channel"]["properties"]["niche"]["type"] == "string"


# -------------------------------------------------- translating the event stream


# Verbatim from codex-cli 0.146.0, with the tool call pointed at this app's server.
GOOD_TURN = [
    {"type": "thread.started", "thread_id": "019fc7ef-1fb2-7003-b2ef-be78ff9bdcc0"},
    {"type": "turn.started"},
    {"type": "item.completed",
     "item": {"id": "item_0", "type": "reasoning", "text": "**Checking the install**"}},
    {"type": "item.started",
     "item": {"id": "item_1", "type": "mcp_tool_call", "server": "forgecast",
              "tool": "studio_status", "arguments": {}, "result": None, "error": None,
              "status": "in_progress"}},
    {"type": "item.completed",
     "item": {"id": "item_1", "type": "mcp_tool_call", "server": "forgecast",
              "tool": "studio_status", "arguments": {},
              "result": {"content": [{"type": "text", "text": '{"mode": "mock"}'}]},
              "error": None, "status": "completed"}},
    {"type": "item.completed",
     "item": {"id": "item_2", "type": "agent_message",
              "text": "This install is in mock mode, with no channels yet."}},
    {"type": "turn.completed",
     "usage": {"input_tokens": 24763, "cached_input_tokens": 24448,
               "output_tokens": 122}},
]

# Also verbatim: this is what an unauthenticated turn prints. Trimmed from fifteen
# retries to four, because the count is not what is being asserted.
UNAUTHENTICATED_TURN = [
    {"type": "thread.started", "thread_id": "019fc7ef-1fb2-7003-b2ef-be78ff9bdcc0"},
    {"type": "turn.started"},
    {"type": "error", "message": "Reconnecting... 2/5 (unexpected status 401 Unauthorized: Missing bearer or basic authentication in header, url: wss://api.openai.com/v1/responses, cf-ray: a255dcbb0f10966d-IAD)"},
    {"type": "error", "message": "Reconnecting... 3/5 (unexpected status 401 Unauthorized: Missing bearer or basic authentication in header, url: wss://api.openai.com/v1/responses, cf-ray: a255dcc2895e52d5-IAD)"},
    {"type": "item.completed",
     "item": {"id": "item_0", "type": "error",
              "message": "Falling back from WebSockets to HTTPS transport. unexpected status 401 Unauthorized: Missing bearer or basic authentication in header"}},
    {"type": "error", "message": "unexpected status 401 Unauthorized: Missing bearer or basic authentication in header, url: https://api.openai.com/v1/responses, cf-ray: a255dd330d290db7-IAD, request id: req_f3b0c1ee041c41da9a0488b8c1cd815d"},
    {"type": "turn.failed",
     "error": {"message": "unexpected status 401 Unauthorized: Missing bearer or basic authentication in header, url: https://api.openai.com/v1/responses"}},
]


def translate(stream):
    turn = codex_agent._Turn()
    out = []
    for event in stream:
        out.extend(turn.translate(event))
    return turn, out


def test_a_good_turn_becomes_the_events_the_chat_already_renders():
    turn, events = translate(GOOD_TURN)
    kinds = [event["type"] for event in events]
    assert kinds == ["session", "thinking", "tool", "tool_result", "text", "result"]

    assert events[0]["session_id"] == "019fc7ef-1fb2-7003-b2ef-be78ff9bdcc0"
    # Named the way Claude names them, because the front end strips the prefix for a
    # label and hides a fixed set by the short name.
    assert events[2]["name"] == "mcp__forgecast__studio_status"
    # The result is matched back onto its call by the id the CLI gave it.
    assert events[3]["id"] == events[2]["id"] == "item_1"
    assert events[3]["is_error"] is False
    assert '"mode": "mock"' in events[3]["text"]
    assert events[4]["text"].startswith("This install is in mock mode")
    assert events[5]["session_id"] == turn.session_id
    # A subscription has no per-turn dollar figure, and inventing one would be worse
    # than leaving it out.
    assert events[5]["cost_usd"] is None
    assert events[5]["tokens"]["output"] == 122


def test_the_retry_storm_does_not_become_the_reply():
    """`chat.js` renders an error event by *replacing* the reply.

    Streamed one by one, these leave the operator reading "Reconnecting... 5/5" where
    the answer should be — true, useless, and it buries the real failure.
    """
    turn, events = translate(UNAUTHENTICATED_TURN)
    assert [event["type"] for event in events] == ["session"]
    assert turn.retries == 2
    assert "401" in turn.last_error


def test_a_failed_tool_call_is_marked_failed():
    stream = [
        {"type": "item.started",
         "item": {"id": "t1", "type": "mcp_tool_call", "server": "forgecast",
                  "tool": "start_run", "arguments": {"channel": "Nope"},
                  "status": "in_progress"}},
        {"type": "item.completed",
         "item": {"id": "t1", "type": "mcp_tool_call", "server": "forgecast",
                  "tool": "start_run", "arguments": {"channel": "Nope"},
                  "error": {"message": "no channel called 'Nope'"}, "status": "failed"}},
    ]
    _, events = translate(stream)
    assert events[1]["is_error"] is True
    assert "no channel called" in events[1]["text"]


def test_a_shell_command_and_a_file_change_both_get_a_card():
    stream = [
        {"type": "item.started",
         "item": {"id": "c1", "type": "command_execution", "command": "bash -lc ls",
                  "aggregated_output": "", "exit_code": None, "status": "in_progress"}},
        {"type": "item.completed",
         "item": {"id": "c1", "type": "command_execution", "command": "bash -lc ls",
                  "aggregated_output": "docs\nsrc\n", "exit_code": 0,
                  "status": "completed"}},
        {"type": "item.completed",
         "item": {"id": "f1", "type": "file_change", "status": "completed",
                  "changes": [{"path": "forgecast/x.py", "kind": "update"}]}},
    ]
    _, events = translate(stream)
    assert events[0]["name"] == "Bash"
    assert events[1]["text"].strip() == "docs\nsrc"
    assert events[2]["name"] == "Edit"
    assert "forgecast/x.py" in events[3]["text"]

    # A non-zero exit is a failure even when the CLI does not say "failed".
    _, failed = translate([
        {"type": "item.completed",
         "item": {"id": "c2", "type": "command_execution", "command": "false",
                  "aggregated_output": "", "exit_code": 1, "status": "completed"}},
    ])
    assert failed[-1]["is_error"] is True


def test_a_long_tool_result_is_cut_the_same_way_on_both_backends():
    from forgecast.agent.assistant import MAX_RESULT_CHARS

    _, events = translate([
        {"type": "item.completed",
         "item": {"id": "t9", "type": "mcp_tool_call", "server": "forgecast",
                  "tool": "research_channel", "arguments": {},
                  "result": {"content": [{"type": "text",
                                          "text": "x" * (MAX_RESULT_CHARS + 900)}]},
                  "status": "completed"}},
    ])
    assert "more characters" in events[-1]["text"]


# --------------------------------------------------------- every failure sentence


@pytest.mark.parametrize("detail,expected", [
    ("unexpected status 401 Unauthorized: Missing bearer or basic authentication in "
     "header, url: https://api.openai.com/v1/responses", "press Sign in"),
    ("unexpected status 401 Unauthorized: Incorrect API key provided (invalid_api_key)",
     "codex logout"),
    ("stream error: 429 Too Many Requests — usage limit reached", "plan's limit"),
    ("model gpt-5.9-nope is not available to your account", "not available on your "
                                                            "ChatGPT plan"),
    ("error sending request: dns error: failed to lookup address information",
     "could not reach api.openai.com"),
    ("mcp server forgecast failed to start", "studio's tools could not be started"),
])
def test_every_failure_gets_a_sentence_with_something_to_do_in_it(detail, expected):
    """The exact failure this app exists not to have is a true, complete, useless line.

    "unexpected status 401 Unauthorized: Missing bearer or basic authentication in
    header, url: wss://api.openai.com/v1/responses, cf-ray: …" tells the operator
    nothing about pressing Sign in.
    """
    said = codex_agent._explain(detail, [], 0)
    assert expected in said
    # The original is always kept underneath, because the sentence is an explanation
    # and not a replacement for the evidence.
    assert detail in said


def test_an_unrecognised_failure_is_passed_through_rather_than_dressed_up():
    assert codex_agent._explain("something new and strange", [], 0) == \
        "something new and strange"


def test_a_resume_that_no_longer_exists_is_recognised():
    """Measured by resuming an id that never existed on 0.146.0:

        Error: thread/resume: thread/resume failed: no rollout found for thread id …

    It arrives on stderr with a non-zero exit rather than as a JSONL event, which is
    why the diagnostics tail is what gets matched.
    """
    dead = "thread/resume failed: no rollout found for thread id 0000"
    assert codex_agent._looks_like_a_dead_session(dead, "0000") is True
    # Without a resume there is no dead session to blame, whatever the text says.
    assert codex_agent._looks_like_a_dead_session(dead, None) is False
    assert codex_agent._looks_like_a_dead_session("401 Unauthorized", "0000") is False


# ------------------------------------------------- the turn, against a stand-in CLI


FAKE_CLI = textwrap.dedent('''
    """A stand-in for `codex exec --json`. Replays a recorded stream."""
    import json, os, sys

    record = os.environ["FAKE_CODEX_RECORD"]
    with open(record, "w", encoding="utf-8") as out:
        json.dump({"argv": sys.argv[1:], "stdin": sys.stdin.read()}, out)

    sys.stderr.write("2026-01-01T00:00:00Z INFO codex: starting\\n")
    for line in json.loads(os.environ["FAKE_CODEX_STREAM"]):
        sys.stdout.write(json.dumps(line) + "\\n")
        sys.stdout.flush()
    if os.environ.get("FAKE_CODEX_STDERR"):
        sys.stderr.write(os.environ["FAKE_CODEX_STDERR"] + "\\n")
    sys.exit(int(os.environ.get("FAKE_CODEX_EXIT", "0")))
''')


@pytest.fixture
def fake_codex(tmp_path, monkeypatch):
    """Point the backend at a CLI that replays JSONL instead of calling OpenAI.

    A real end-to-end turn cannot run here: it needs the Codex CLI installed and a
    ChatGPT sign-in, and a test machine has neither. What can be tested is everything
    this app is responsible for — the command line, the prompt going down stdin, the
    translation, and the teardown.
    """
    script = tmp_path / "fake_codex.py"
    script.write_text(FAKE_CLI)
    record = tmp_path / "record.json"
    monkeypatch.setenv("FAKE_CODEX_RECORD", str(record))
    monkeypatch.setattr(codex_auth, "find_cli", lambda: [sys.executable, str(script)])
    monkeypatch.setattr(
        codex_auth, "check",
        lambda: codex_auth.CodexStatus(ok=True, headline="Connected",
                                       detail="pretend", signed_in=True))

    def configure(stream, exit_code=0, stderr=""):
        monkeypatch.setenv("FAKE_CODEX_STREAM", json.dumps(stream))
        monkeypatch.setenv("FAKE_CODEX_EXIT", str(exit_code))
        monkeypatch.setenv("FAKE_CODEX_STDERR", stderr)
        return record

    return configure


def drive(prompt, **kwargs):
    import anyio

    from forgecast.agent.studio import Studio

    async def go():
        return [event async for event in codex_agent.run(
            prompt, studio=Studio(), **kwargs)]

    return anyio.run(go)


def test_a_whole_turn_streams_through_the_subprocess(fake_codex, user):
    record = fake_codex(GOOD_TURN)
    events = drive("what is this install?", model="gpt-5.6-luna", user_id=user.id)

    assert [event["type"] for event in events] == [
        "session", "thinking", "tool", "tool_result", "text", "result"]
    assert events[-1]["is_error"] is False

    written = json.loads(record.read_text())
    # The prompt travels on stdin. In argv it would work until someone pastes a script.
    assert "what is this install?" in written["stdin"]
    assert "what is this install?" not in " ".join(written["argv"])
    # And the system prompt goes with it, since `codex exec` has no system-prompt flag.
    assert "You ARE Forgecast" in written["stdin"]
    assert written["argv"][-1] == "-"
    assert "gpt-5.6-luna" in written["argv"]


def test_a_resumed_turn_does_not_repeat_the_system_prompt(fake_codex, user):
    record = fake_codex(GOOD_TURN)
    drive("and now?", resume="019fc7ef-1fb2-7003", user_id=user.id)
    written = json.loads(record.read_text())
    # The session already has it. Sending it again every turn is thousands of tokens
    # of the same paragraphs, and it invites the model to start over.
    assert "You ARE Forgecast" not in written["stdin"]
    assert written["stdin"].strip() == "and now?"


def test_an_unauthenticated_turn_ends_in_one_actionable_error(fake_codex, user):
    fake_codex(UNAUTHENTICATED_TURN, exit_code=1)
    events = drive("hello", user_id=user.id)

    errors = [event for event in events if event["type"] == "error"]
    assert len(errors) == 1
    assert "press Sign in" in errors[0]["text"]
    # The evidence is still underneath it.
    assert "401" in errors[0]["text"]
    # And the retries are reported as what they were, not as the answer.
    notices = [event for event in events if event["type"] == "notice"]
    assert notices == [] or "dropped" in notices[0]["text"]


def test_a_dead_session_asks_the_caller_to_retry_from_scratch(fake_codex, user):
    """The recovery `routes_agent` already implements for Claude, reached the same way.

    Without the flag the thread is bricked: every later message resumes the same dead
    id and fails identically.
    """
    # The wording 0.146.0 actually prints, on stderr, with a non-zero exit — there is
    # no JSONL event for it, so the diagnostics tail is the only place it appears.
    fake_codex(
        [], exit_code=1,
        stderr="Error: thread/resume: thread/resume failed: no rollout found for "
               "thread id 019fc7ef-dead (code -32600)")
    events = drive("hello", resume="019fc7ef-dead", user_id=user.id)
    error = next(event for event in events if event["type"] == "error")
    assert error["resume_failed"] is True
    assert "no rollout found" in error["text"]

    # A turn that failed for any other reason must not claim the session is dead: the
    # caller would silently start a fresh conversation and hide a real failure.
    fake_codex(UNAUTHENTICATED_TURN, exit_code=1)
    other = drive("hello", resume="019fc7ef-dead", user_id=user.id)
    assert next(e for e in other if e["type"] == "error")["resume_failed"] is False


def test_the_backend_refuses_before_spawning_anything_when_not_signed_in(monkeypatch,
                                                                        user):
    monkeypatch.setattr(codex_auth, "find_cli", lambda: None)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)

    def forbidden(*args, **kwargs):             # pragma: no cover
        raise AssertionError("nothing may be spawned before the sign-in is checked")

    monkeypatch.setattr(codex_agent.asyncio, "create_subprocess_exec", forbidden)
    events = drive("hello", user_id=user.id)
    assert len(events) == 1
    # A setup notice, not an error. An error is rendered as the assistant's reply, so
    # this exact case — no Codex CLI, someone types "hi" — put a paragraph about npm
    # where the answer goes, and it read as the agent being broken.
    assert events[0]["type"] == "setup"
    assert "Codex CLI" in events[0]["text"]
    assert events[0]["headline"]
    assert events[0]["fixes"]
    # Nothing to sign in to yet, so the button that would open a browser flow is not
    # offered: it could only open a terminal printing "command not found".
    assert events[0]["can_login"] is False


def test_the_stream_never_yields_from_a_finally():
    """Yielding while unwinding raises "async generator ignored GeneratorExit".

    Which aborts teardown — here, of the Codex subprocess, leaving a CLI running after
    the window was closed. Asserted on the source for the same reason `test_agent.py`
    does it for the Claude path: the failure only shows up when a generator is closed
    early, which is the case hardest to notice.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(codex_agent.run).lstrip())
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and node.finalbody:
            for inner in ast.walk(ast.Module(body=node.finalbody, type_ignores=[])):
                assert not isinstance(inner, ast.Yield), \
                    "run() must not yield from a finally block"


# ---------------------------------------------------------------------- the page


def test_the_composer_lets_you_choose_the_agent_and_says_what_it_signs_in_with(client):
    page = client.get("/")
    assert page.status_code == 200
    body = page.text
    assert 'id="engine-pick"' in body
    assert 'id="model-pick"' in body
    # The sentence about how each one authenticates has to be on screen where the
    # choice is made, not in a document.
    assert 'id="engine-note"' in body
    assert 'id="engine-limits"' in body


# --------------------------------------------------------------------- connectors


def test_the_connectors_reach_chatgpt_too_without_their_tokens_in_the_command(tmp_path,
                                                                             monkeypatch):
    """Both agents get the same outside tools, and the token stays out of `ps`.

    The system prompt tells the agent which services it holds. Wiring the connectors
    into one backend and not the other means ChatGPT is told it has NexLev and then
    reports that a niche cannot be researched — worse than not having it.
    """
    from forgecast.agent import connectors

    monkeypatch.setattr(connectors, "default_path", lambda: tmp_path / "connectors.json")
    store = connectors.Store.load()
    store.set("nexlev", "https://mcp.example.test/mcp", "a-real-token")

    overrides, env = codex_agent.remote_servers()
    joined = " ".join(overrides)
    assert "mcp_servers.nexlev.url=" in joined
    assert "bearer_token_env_var=" in joined
    # The token itself must not be on the command line, which any other user on the
    # machine can read out of the process table.
    assert "a-real-token" not in joined
    assert "a-real-token" in env.values()

    argv = codex_agent.build_command(cli=["codex"], extra_config=overrides)
    assert "a-real-token" not in " ".join(argv)
    assert codex_agent._environment(env)["FORGECAST_MCP_TOKEN_NEXLEV"] == "a-real-token"


def test_a_connector_with_no_url_is_not_offered_as_a_server(tmp_path, monkeypatch):
    """An API connector is not an MCP endpoint — the same split `connectors` makes."""
    from forgecast.agent import connectors

    monkeypatch.setattr(connectors, "default_path", lambda: tmp_path / "connectors.json")
    store = connectors.Store.load()
    store.set("epidemic_sound", "", "a-credential")

    overrides, env = codex_agent.remote_servers()
    assert overrides == []
    assert env == {}


def test_an_install_into_the_apps_own_runtime_is_found_and_run_with_its_node(tmp_path,
                                                                            monkeypatch):
    """What `desktop/toolchain.py` produces, and how this finds it.

    `npm install -g @openai/codex --prefix runtime/node` writes
    `runtime/node/lib/node_modules/@openai/codex/bin/codex.js` plus a `bin/codex` shim —
    measured, not assumed. The script is preferred over the shim so the spawn is
    identical on Windows, where the shim is a `.cmd` that CreateProcess cannot run.
    """
    runtime = tmp_path / "runtime" / "node"
    node = runtime / "bin" / "node"
    node.parent.mkdir(parents=True)
    node.write_text("#!/bin/sh\n")
    entry = runtime / "lib" / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
    entry.parent.mkdir(parents=True)
    entry.write_text("#!/usr/bin/env node\n")
    shim = runtime / "bin" / "codex"
    shim.write_text("#!/bin/sh\n")

    monkeypatch.setattr(codex_auth, "APP_ROOT", tmp_path)
    assert codex_auth.find_cli() == [str(node), str(entry)]
    # And what the panel shows is the program, not the interpreter in front of it.
    assert codex_auth.cli_label(codex_auth.find_cli()) == str(entry)

    # With no bundled Node there is nothing to run the script with, so the shim it is.
    node.unlink()
    assert codex_auth.find_cli() == [str(shim)]
