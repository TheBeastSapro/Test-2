"""Connector tools: granted, shown, and enforceable.

The reported bug, in the shape it reached the operator. Every call the agent made came
back as `user cancelled MCP tool call` — twice in a row on `studio_status`, so the agent
could not even open a conversation. Nobody had cancelled anything.

What was actually wrong:

* `assistant.build_options` hands the SDK every connected server (`mcp_servers`) and
  listed only this app's own tools in `allowed_tools`. So a connector's tools — all 59
  of NexLev's, every one of Epidemic's — needed a permission that was never granted.
* Nothing supplied `can_use_tool`, and this app has no surface on which a permission
  prompt can be shown or answered. So the request went nowhere and came back refused,
  reported in the CLI's words as a cancellation.
* The Settings page never showed what a connector could do, so the operator could not
  see the permission, let alone give it.

Three failures, one cause: a decision the app needs to make with no place to make it.
That is the third time this pattern has cost a working feature — the run gates and the
paper edit were the other two — so the invariant is a test rather than a comment.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from forgecast.agent import assistant, connectors, tools


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "connectors.json"
    monkeypatch.setattr(connectors, "default_path", lambda: path)
    made = connectors.Store.load(path)
    made.set("nexlev", "https://prod.dashboard.nexlev.io/api/claude-mcp", "nlv_key")
    made.remember_tools("nexlev", [
        {"name": "youtube_search", "description": "search", "read_only": True},
        {"name": "save_to_swipefile", "description": "writes", "read_only": False},
    ])
    return connectors.Store.load(path)


# ------------------------------------------------------------------ the grant exists


def test_a_connected_service_is_allowed_by_default(store):
    """The operator went and connected it. Asking every time is what the app was already
    effectively doing by granting nothing, and the outcome was not careful review."""
    assert store.decide("mcp__nexlev__youtube_search")[0] == "allow"
    assert store.decide("mcp__nexlev__save_to_swipefile")[0] == "allow"


def test_a_switched_off_connector_is_refused_with_a_reason(store):
    store.set("nexlev", store.connections["nexlev"].url, enabled=False)
    decision, why = connectors.Store.load(store.path).decide("mcp__nexlev__youtube_search")
    assert decision == "deny"
    assert "Settings" in why, "a refusal the operator cannot act on is a dead end"


def test_a_server_this_app_did_not_configure_is_asked_about(store):
    """Something added with `claude mcp add` by hand. Neither allowing nor refusing it
    silently is right — the honest answer is that nobody has decided."""
    decision, why = store.decide("mcp__someone_else__do_a_thing")
    assert decision == "ask"
    assert "someone_else" in why


def test_this_apps_own_tools_are_never_touched_by_connector_policy(store):
    """`studio_status` is Forgecast's own, in `allowed_tools`, and must not be routed
    through a connector rule that has nothing to say about it.

    This is the reported failure exactly: `studio_status` came back cancelled twice, so
    the agent could not open a conversation. The unknown-server branch below answers
    `ask`, and `ask` is refused — so without this the mechanism built to fix the bug
    would have re-created it.
    """
    from forgecast.agent import tools as tool_module

    assert connectors.OWN_SERVER == tool_module.SERVER_NAME
    assert store.decide("mcp__forgecast__studio_status")[0] == "allow"
    assert store.decide("Read")[0] == "allow"


def test_a_per_tool_override_beats_the_connector_default(store):
    store.set_policy("nexlev", tools={"save_to_swipefile": "deny"})
    fresh = connectors.Store.load(store.path)
    assert fresh.decide("mcp__nexlev__save_to_swipefile")[0] == "deny"
    assert fresh.decide("mcp__nexlev__youtube_search")[0] == "allow"


def test_the_connector_default_can_be_tightened(store):
    store.set_policy("nexlev", default="ask")
    fresh = connectors.Store.load(store.path)
    assert fresh.decide("mcp__nexlev__youtube_search")[0] == "ask"


def test_policy_survives_a_re_save_of_the_url(store):
    """Saving the row is how a URL gets corrected, and a correction must not silently
    re-grant tools the operator had narrowed down."""
    store.set_policy("nexlev", default="deny", tools={"youtube_search": "allow"})
    url = store.connections["nexlev"].url
    connectors.Store.load(store.path).set("nexlev", url)
    fresh = connectors.Store.load(store.path)
    assert fresh.connections["nexlev"].default_policy == "deny"
    assert fresh.decide("mcp__nexlev__youtube_search")[0] == "allow"


def test_a_changed_endpoint_drops_the_tool_list(store):
    """A different server's inventory is not this one's, and showing the old list beside
    a new URL is the page stating something it does not know."""
    connectors.Store.load(store.path).set("nexlev", "https://elsewhere.example/mcp")
    assert connectors.Store.load(store.path).connections["nexlev"].tools == []


# --------------------------------------------------------- and the SDK is told about it


def test_the_options_carry_a_permission_callback():
    """The load-bearing assertion. Without this every connector tool needs a prompt that
    nothing in this app can show, and the CLI records the silence as a cancellation."""
    import inspect

    source = inspect.getsource(assistant.build_options)
    assert "can_use_tool" in source, (
        "build_options hands the SDK connector servers without a way to decide their "
        "tools — every call will come back 'user cancelled MCP tool call'")


def test_every_server_handed_to_the_sdk_can_be_decided_about(store, monkeypatch):
    """The invariant that was missing. A server may reach `mcp_servers` only if there is
    something that can answer a permission question about its tools."""
    monkeypatch.setattr(connectors, "active_servers",
                        lambda: {"nexlev": {}, "epidemic-sound": {}})
    fresh = connectors.Store.load(store.path)
    fresh.set("epidemic-sound", "https://example.test/mcp", "tok")

    for server in connectors.active_servers():
        decision, why = connectors.Store.load(store.path).decide(f"mcp__{server}__anything")
        assert decision in {"allow", "ask", "deny"}, server
        assert why, f"{server} was decided with no reason to show"


def test_the_callback_allows_denies_and_explains(store):
    async def ask(name):
        return await assistant.connector_permission(name, {}, None)

    allowed = asyncio.run(ask("mcp__nexlev__youtube_search"))
    assert allowed.behavior == "allow"

    connectors.Store.load(store.path).set_policy("nexlev", default="deny")
    refused = asyncio.run(ask("mcp__nexlev__youtube_search"))
    assert refused.behavior == "deny"
    # The message is the whole point: an agent told only "no" retries, and an operator
    # reading the transcript cannot tell a policy from an outage.
    assert "youtube_search" in refused.message
    assert "not permitted" in refused.message


def test_ask_is_refused_out_loud_rather_than_left_hanging(store):
    """Nothing here can prompt mid-turn yet. Refusing with the reason and the page that
    fixes it is recoverable in one click; a silent cancellation is the reported bug."""
    connectors.Store.load(store.path).set_policy("nexlev", default="ask")
    result = asyncio.run(
        assistant.connector_permission("mcp__nexlev__youtube_search", {}, None))
    assert result.behavior == "deny"
    assert "Settings" in result.message and "Connectors" in result.message


def test_forgecasts_own_tools_are_allowed_by_the_callback(store):
    """They are already in `allowed_tools`, so the callback should not normally see one —
    but if it does, refusing it would break the app with its own safety mechanism."""
    for name in list(tools.ALLOWED)[:5]:
        assert asyncio.run(
            assistant.connector_permission(name, {}, None)).behavior == "allow"


# --------------------------------------------------------------- and the operator sees it


def test_the_row_reports_its_tools_and_its_policy(store):
    row = store.connections["nexlev"].as_dict()
    assert row["tool_count"] == 2
    assert row["default_policy"] == "allow"
    assert {t["name"] for t in row["tools"]} == {"youtube_search", "save_to_swipefile"}
    assert all(t["decision"] == "allow" for t in row["tools"])


def test_the_settings_page_shows_permissions_on_every_connector_not_one(store):
    """Reported as "make sure to show those permissions while connecting mcp, not only
    for nexlev" — so the block is in the row template, which every connector renders,
    and is not keyed to any service by name."""
    from pathlib import Path

    from forgecast.api import routes_web

    page = (Path(routes_web.__file__).resolve().parent.parent / "web" / "settings.html"
            ).read_text(encoding="utf-8")
    assert 'data-role="perms"' in page
    assert "Tool permissions" in page
    # Inside the `{% for item in connectors %}` loop, and not special-cased.
    before, _, after = page.partition('data-role="perms"')
    assert "{% for item in connectors %}" in before
    assert "{% endfor %}" in after
    # Keyed off the loop variable, so it renders for whatever is in the catalogue rather
    # than for a service named in the markup.
    assert "{{ item.key }}" in page
    assert "item.key" in page.split('data-role="perms"')[0].rsplit(
        "{% for item in connectors %}", 1)[-1]


def test_the_page_can_set_both_levels_of_policy(store):
    from pathlib import Path

    from forgecast.api import routes_web

    page = (Path(routes_web.__file__).resolve().parent.parent / "web" / "settings.html"
            ).read_text(encoding="utf-8")
    assert "/policy" in page, "the page shows a permission it cannot change"
    assert "/tools" in page, "nothing asks the server what it offers"
    assert "Always allow" in page and "Ask each time" in page and "Never allow" in page


# ------------------------------------------------------------------------ discovery


def test_a_tools_list_answer_becomes_rows():
    payload = {"tools": [
        {"name": "b_tool", "description": "  spaced   out  ",
         "annotations": {"readOnlyHint": True}},
        {"name": "a_tool", "title": "A"},
        {"description": "no name at all"},
    ]}
    rows = connectors._tool_rows(payload)
    assert [row["name"] for row in rows] == ["a_tool", "b_tool"]
    assert rows[1]["description"] == "spaced out"
    assert rows[1]["read_only"] is True
    # Not flattened to False. A page that labels an unannotated tool "writes" is a page
    # that makes the operator switch off a connector that only reads.
    assert rows[0]["read_only"] is None


def test_an_sse_answer_is_read_as_well_as_a_json_one():
    """MCP over HTTP may answer either way and which one arrives is the server's choice.
    A reader that only handles JSON reports half of them as unreachable."""
    body = "event: message\ndata: " + json.dumps(
        {"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "x"}]}}) + "\n\n"
    assert connectors._decode_mcp(body) == {"tools": [{"name": "x"}]}
    assert connectors._decode_mcp('{"result": {"tools": []}}') == {"tools": []}
    assert connectors._decode_mcp("not json at all") == {}


def test_a_browser_signed_in_connector_says_why_it_cannot_be_probed(store):
    """Its grant is in the Claude CLI and this app holds no token, so a direct request
    can only ever be 401. Saying so beats an empty list that reads as "no tools"."""
    store.set("higgsfield", "https://example.test/mcp")
    conn = connectors.Store.load(store.path).connections["higgsfield"]
    rows, why = asyncio.run(connectors.probe_tools(conn))
    assert rows == []
    assert "Claude CLI" in why


def test_a_live_session_fills_in_what_a_probe_cannot(store, monkeypatch):
    """The other half of discovery. The SDK's opening message names every tool the agent
    holds, which is the only view into a connector this app cannot authenticate to."""
    monkeypatch.setattr(connectors, "default_path", lambda: store.path)
    connectors.learn_session_tools([
        "mcp__nexlev__get_channel_analytics",
        "mcp__forgecast__studio_status",     # ours, not a connector
        "Read",                              # not an MCP tool at all
    ])
    fresh = connectors.Store.load(store.path)
    names = {row["name"] for row in fresh.connections["nexlev"].tools}
    assert "get_channel_analytics" in names
    assert "youtube_search" in names, "an earlier probe's rows must not be dropped"
    assert "forgecast" not in fresh.connections


def test_an_upgrade_does_not_silently_switch_a_connector_off(tmp_path):
    """A file written before any of this existed is a connector already being handed to
    the agent. Defaulting it to `ask` on load would turn it off without saying so."""
    path = tmp_path / "connectors.json"
    path.write_text(json.dumps({"connectors": {
        "nexlev": {"url": "https://example.test/mcp", "token": "", "enabled": True},
    }}), encoding="utf-8")
    loaded = connectors.Store.load(path)
    assert loaded.connections["nexlev"].default_policy == "allow"
    assert loaded.decide("mcp__nexlev__anything")[0] == "allow"
