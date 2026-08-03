"""HTTP surface: authentication, tenant isolation, validation, and gate wiring.

Run completion is covered in test_engine.py; these tests care about the boundary.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from forgecast.api.main import app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def register(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/auth/signup", json={"email": email, "password": "supersecret"}
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict:
    return {"authorization": f"Bearer {token}"}


def make_channel(client: TestClient, token: str, name: str = "Chan") -> int:
    response = client.post(
        "/api/channels",
        headers=auth(token),
        json={"name": name, "niche": "space", "target_duration_seconds": 20,
              "voice_id": "v1"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


# ------------------------------------------------------------------------ health


def test_healthz(client: TestClient):
    assert client.get("/healthz").json()["ok"] is True


# -------------------------------------------------------------------------- auth


def test_signup_grants_starting_credits(client: TestClient):
    token = register(client, "new@example.com")
    me = client.get("/api/me", headers=auth(token)).json()
    assert me["email"] == "new@example.com"
    assert me["credits"] > 0


def test_duplicate_signup_is_rejected(client: TestClient):
    register(client, "dupe@example.com")
    response = client.post(
        "/api/auth/signup", json={"email": "dupe@example.com", "password": "supersecret"}
    )
    assert response.status_code == 409


def test_short_password_is_rejected(client: TestClient):
    response = client.post(
        "/api/auth/signup", json={"email": "weak@example.com", "password": "short"}
    )
    assert response.status_code == 422


def test_login_round_trip(client: TestClient):
    register(client, "login@example.com")
    ok = client.post(
        "/api/auth/login", json={"email": "login@example.com", "password": "supersecret"}
    )
    assert ok.status_code == 200 and ok.json()["access_token"]

    bad = client.post(
        "/api/auth/login", json={"email": "login@example.com", "password": "wrongwrong"}
    )
    assert bad.status_code == 401


def test_protected_routes_require_a_token(client: TestClient):
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/channels").status_code == 401


def test_a_forged_token_is_rejected(client: TestClient):
    assert client.get("/api/me", headers=auth("not.a.jwt")).status_code == 401


# --------------------------------------------------------------- tenant isolation


def test_users_cannot_see_each_others_channels(client: TestClient):
    alice = register(client, "alice@example.com")
    bob = register(client, "bob@example.com")
    channel_id = make_channel(client, alice, "Alice's channel")

    assert client.get("/api/channels", headers=auth(bob)).json() == []
    leak = client.patch(
        f"/api/channels/{channel_id}",
        headers=auth(bob),
        json={"name": "stolen", "target_duration_seconds": 60},
    )
    assert leak.status_code == 404


def test_users_cannot_read_or_gate_each_others_runs(client: TestClient):
    alice = register(client, "alice2@example.com")
    bob = register(client, "bob2@example.com")
    channel_id = make_channel(client, alice)

    run = client.post(
        "/api/runs",
        headers=auth(alice),
        json={"channel_id": channel_id, "topic": "Alice's topic",
              "pipeline": "faceless_shorts", "options": {"target_seconds": 20}},
    )
    assert run.status_code == 201, run.text
    run_id = run.json()["id"]

    assert client.get(f"/api/runs/{run_id}", headers=auth(bob)).status_code == 404
    assert client.post(
        f"/api/runs/{run_id}/nodes/brief/gate", headers=auth(bob), json={}
    ).status_code == 404
    assert client.post(f"/api/runs/{run_id}/cancel", headers=auth(bob)).status_code == 404


def test_starting_a_run_on_someone_elses_channel_is_refused(client: TestClient):
    alice = register(client, "alice3@example.com")
    bob = register(client, "bob3@example.com")
    channel_id = make_channel(client, alice)

    response = client.post(
        "/api/runs",
        headers=auth(bob),
        json={"channel_id": channel_id, "topic": "not mine", "pipeline": "faceless_shorts"},
    )
    assert response.status_code == 404


# ----------------------------------------------------------------------- pipelines


def test_estimate_is_itemised_and_adds_up(client: TestClient):
    response = client.get(
        "/api/pipelines/faceless_longform/estimate", params={"target_seconds": 120}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_credits"] == sum(node["credits"] for node in body["per_node"])
    assert body["total_usd"] > 0
    # B-roll should dominate; if it does not, the pricing table drifted.
    shots = next(n for n in body["per_node"] if n["key"] == "shots")
    assert shots["credits"] > body["total_credits"] * 0.5


def test_estimate_of_unknown_pipeline_is_404(client: TestClient):
    assert client.get("/api/pipelines/nope/estimate").status_code == 404


def test_pipelines_are_listed(client: TestClient):
    names = {entry["name"] for entry in client.get("/api/pipelines").json()}
    assert {"faceless_longform", "faceless_shorts"} <= names


# ---------------------------------------------------------------------------- runs


def test_run_is_created_with_a_full_graph_and_a_hold(client: TestClient):
    token = register(client, "runner@example.com")
    channel_id = make_channel(client, token)

    response = client.post(
        "/api/runs",
        headers=auth(token),
        json={"channel_id": channel_id, "topic": "Graph shape",
              "pipeline": "faceless_shorts", "options": {"target_seconds": 20}},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["credits_reserved"] > 0
    keys = {node["key"] for node in body["nodes"]}
    assert {"brief", "script", "voice", "shots", "render", "publish"} <= keys
    assert any(node["requires_approval"] for node in body["nodes"])


def test_run_beyond_balance_returns_402(client: TestClient):
    token = register(client, "broke@example.com")
    channel_id = make_channel(client, token)
    response = client.post(
        "/api/runs",
        headers=auth(token),
        json={"channel_id": channel_id, "topic": "way too long",
              "pipeline": "faceless_longform", "options": {"target_seconds": 3600}},
    )
    assert response.status_code == 402
    assert response.json()["detail"]["error"] == "insufficient_credits"


def test_gating_a_node_that_is_not_waiting_is_409(client: TestClient):
    token = register(client, "gate@example.com")
    channel_id = make_channel(client, token)
    run_id = client.post(
        "/api/runs",
        headers=auth(token),
        json={"channel_id": channel_id, "topic": "Gate state",
              "pipeline": "faceless_shorts", "options": {"target_seconds": 20}},
    ).json()["id"]

    # `render` is pending, not awaiting approval.
    response = client.post(
        f"/api/runs/{run_id}/nodes/render/gate", headers=auth(token), json={}
    )
    assert response.status_code == 409


def test_gating_an_unknown_node_is_404(client: TestClient):
    token = register(client, "gate2@example.com")
    channel_id = make_channel(client, token)
    run_id = client.post(
        "/api/runs",
        headers=auth(token),
        json={"channel_id": channel_id, "topic": "Unknown node test",
              "pipeline": "faceless_shorts"},
    ).json()["id"]
    assert client.post(
        f"/api/runs/{run_id}/nodes/ghost/gate", headers=auth(token), json={}
    ).status_code == 404


def test_too_short_topic_is_rejected(client: TestClient):
    token = register(client, "shorttopic@example.com")
    channel_id = make_channel(client, token)
    response = client.post(
        "/api/runs",
        headers=auth(token),
        json={"channel_id": channel_id, "topic": "x", "pipeline": "faceless_shorts"},
    )
    assert response.status_code == 422


def test_cancelling_releases_the_hold(client: TestClient):
    token = register(client, "cancel@example.com")
    channel_id = make_channel(client, token)
    opening = client.get("/api/me", headers=auth(token)).json()["credits"]

    run_id = client.post(
        "/api/runs",
        headers=auth(token),
        json={"channel_id": channel_id, "topic": "Cancel", "pipeline": "faceless_shorts",
              "options": {"target_seconds": 20}},
    ).json()["id"]
    assert client.get("/api/me", headers=auth(token)).json()["credits"] < opening

    cancelled = client.post(f"/api/runs/{run_id}/cancel", headers=auth(token))
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    spent = cancelled.json()["credits_spent"]
    assert client.get("/api/me", headers=auth(token)).json()["credits"] == opening - spent

    # Cancelling twice is a conflict, not a second refund.
    assert client.post(f"/api/runs/{run_id}/cancel", headers=auth(token)).status_code == 409


# ------------------------------------------------------------------- provider keys


def test_provider_keys_are_stored_masked_and_never_returned(client: TestClient):
    token = register(client, "keys@example.com")
    secret = "sk-live-abcdef1234567890"

    response = client.put(
        "/api/provider-keys", headers=auth(token),
        json={"provider": "elevenlabs", "api_key": secret},
    )
    assert response.status_code == 200
    body = response.json()
    assert secret not in response.text
    assert body["masked"].startswith("sk-l") and body["masked"].endswith("7890")

    listing = client.get("/api/provider-keys", headers=auth(token))
    assert secret not in listing.text
    assert len(listing.json()) == 1

    # Upsert replaces rather than duplicating.
    client.put(
        "/api/provider-keys", headers=auth(token),
        json={"provider": "elevenlabs", "api_key": "sk-live-zzzzzzzzzzzzzzzz"},
    )
    assert len(client.get("/api/provider-keys", headers=auth(token)).json()) == 1

    assert client.delete("/api/provider-keys/elevenlabs", headers=auth(token)).status_code == 204
    assert client.get("/api/provider-keys", headers=auth(token)).json() == []


def test_unknown_provider_is_rejected(client: TestClient):
    token = register(client, "keys2@example.com")
    response = client.put(
        "/api/provider-keys", headers=auth(token),
        json={"provider": "not-a-vendor", "api_key": "0123456789"},
    )
    assert response.status_code == 400


def test_stored_key_round_trips_through_encryption(client: TestClient):
    """The ciphertext in the database must decrypt back to the original."""
    from sqlalchemy import select

    from forgecast.crypto import decrypt
    from forgecast.db import SessionLocal
    from forgecast.models import ProviderKey

    token = register(client, "keys3@example.com")
    secret = "fal-key-9876543210"
    client.put(
        "/api/provider-keys", headers=auth(token),
        json={"provider": "fal", "api_key": secret},
    )
    with SessionLocal() as session:
        row = session.execute(select(ProviderKey)).scalars().one()
        assert row.ciphertext != secret
        assert decrypt(row.ciphertext) == secret


# ------------------------------------------------------------------------- credits


def test_ledger_is_visible_to_its_owner(client: TestClient):
    token = register(client, "ledger@example.com")
    body = client.get("/api/credits", headers=auth(token)).json()
    assert body["balance"] > 0
    assert body["entries"][0]["kind"] == "grant"


def test_plans_expose_price_per_credit(client: TestClient):
    plans = {entry["plan"]: entry for entry in client.get("/api/plans").json()}
    assert plans["pro"]["monthly_credits"] == 3000
    assert 0 < plans["pro"]["usd_per_credit"] < 0.05


# ----------------------------------------------------------------------- web pages


def test_web_pages_render(client: TestClient):
    """The root is the chat, and both format workspaces still render.

    Asserted against the format's own label rather than a fixed word on the page:
    tying this to "Channels" is what broke it when the dashboard became per-format,
    even though the page was rendering perfectly.
    """
    token = register(client, "web@example.com")
    assert client.get("/login").status_code == 200

    client.cookies.set("forgecast_session", token)
    # The front door is the agent, not a table. The workspaces are a click away in
    # the rail; they are where you look at what happened, not where work starts.
    landing = client.get("/", follow_redirects=False)
    assert landing.status_code == 200
    assert 'id="chat-input"' in landing.text

    for slug, label in (("longform", "Long-form"), ("shorts", "Shorts")):
        page = client.get(f"/f/{slug}")
        assert page.status_code == 200
        assert label in page.text

    # With a channel to run against, the tab's own pipeline is carried by the form —
    # the whole point of splitting the workspaces is that it is no longer a dropdown.
    client.post(
        "/channels",
        data={"name": "Vertical", "aspect_ratio": "9:16",
              "target_duration_seconds": "45"},
        follow_redirects=False,
    )
    shorts = client.get("/f/shorts")
    assert 'name="pipeline" value="faceless_shorts"' in shorts.text
    assert "Vertical" in shorts.text

    # And it does not leak into the other tab's *workspace*. Cut at `</aside>` because
    # the sidebar is account-wide on purpose — it lists every channel so that one of
    # them is reachable while you are looking at the other — so asserting against the
    # whole document would fail for the rail doing its job.
    def workspace(body: str) -> str:
        assert "</aside>" in body, "the page rendered without its sidebar"
        return body.split("</aside>", 1)[1]

    assert "Vertical" in workspace(shorts.text)
    assert "Vertical" not in workspace(client.get("/f/longform").text)


def test_dashboard_redirects_when_signed_out(client: TestClient):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
