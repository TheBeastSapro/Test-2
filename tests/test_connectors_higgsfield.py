"""The Higgsfield connector, and the rule its `kind` has to obey.

Higgsfield is in the catalogue as `mcp` because it really does publish a remote MCP
server — `https://mcp.higgsfield.ai/mcp`, one hosted endpoint for every account, named
on https://higgsfield.ai/mcp. That fact is the whole reason the entry is shaped the way
it is, so it is asserted here rather than left to the reader: if Higgsfield ever
withdraws the server and only the REST API survives, this file fails and the entry has
to be re-thought instead of quietly lying to the operator.

The second half guards the invariant in the other direction. `Store.active()` hands its
result to the SDK as MCP servers, and an `api` entry reaching that dict is the mis-wiring
the connectors module was written to end: it fails as a 401, which is exactly what a
rejected token looks like, so the operator re-pastes a credential that was never wrong.
Flipping any entry to `api` without that being true is therefore a test failure, not a
runtime mystery.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from forgecast.agent import connectors
from forgecast.api.main import app

HIGGSFIELD = "higgsfield"


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def signed_in(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/auth/signup", json={"email": email, "password": "supersecret"}
    )
    assert response.status_code == 201, response.text
    client.cookies.set("forgecast_session", response.json()["access_token"])


# ------------------------------------------------------------------ the entry


def test_higgsfield_is_in_the_catalogue():
    assert HIGGSFIELD in connectors.BY_KEY
    assert HIGGSFIELD in {spec.key for spec in connectors.CATALOGUE}


def test_higgsfield_is_an_mcp_connector_because_the_server_is_real():
    """Established from Higgsfield's own pages, not assumed from the repo names.

    `higgsfield-ai/skills` is a set of agent skills and `higgsfield-ai/cli` is a
    terminal client — neither is MCP. The MCP server is a third, separately published
    thing, and it is the only one of the three this connector describes.
    """
    spec = connectors.BY_KEY[HIGGSFIELD]
    assert spec.kind == "mcp"
    assert spec.default_url == "https://mcp.higgsfield.ai/mcp"
    assert spec.transport == "http"


def test_higgsfield_says_where_the_credential_comes_from():
    """An entry with no `where` is an empty box and a shrug."""
    spec = connectors.BY_KEY[HIGGSFIELD]
    assert spec.where.strip()
    assert spec.gives.strip()
    # The one thing an operator will otherwise waste an evening on: this endpoint
    # authorises by browser sign-in and issues no key, so the copy has to say so
    # instead of leaving a token box to be filled with something invented.
    assert "sign" in spec.where.lower()


def test_the_published_endpoint_reaches_the_page(tmp_path):
    """`default_url` was carried on the spec and read by nobody.

    So a row whose copy says "the URL is already filled in" arrived with an empty box,
    and the operator went hunting for an endpoint the app already knew.
    """
    store = connectors.Store(path=tmp_path / "connectors.json")
    row = next(r for r in store.listing() if r["key"] == HIGGSFIELD)
    assert row["url"] == "https://mcp.higgsfield.ai/mcp"
    assert row["kind"] == "mcp"


# ------------------------------------------------- the rule for `api` entries


@pytest.mark.parametrize("spec", connectors.CATALOGUE, ids=lambda s: s.key)
def test_an_api_connector_is_never_handed_to_the_sdk(spec, tmp_path):
    """Whatever `kind` says, `active()` must only ever yield MCP servers.

    Parametrised over the whole catalogue so this covers Higgsfield today and covers
    it again if someone reclassifies it. An `api` entry in `active()` is configured as
    an endpoint speaking a protocol it has never spoken — a permanent 401 that is
    indistinguishable from a bad token.
    """
    store = connectors.Store(path=tmp_path / "connectors.json")
    store.connections[spec.key] = connectors.Connection(
        key=spec.key, url=spec.default_url or "https://example.invalid/mcp",
        token="tok", enabled=True,
    )
    # Keyed on `supports_mcp`, not on `kind == "api"`. There are three kinds now: the
    # third is `account`, for a service authorised on the Claude account the agent signs
    # in with rather than configured here at all. It has no URL of its own, so handing it
    # to the SDK would be the same mis-wiring by a different route.
    if spec.supports_mcp:
        assert spec.key in store.active()
    else:
        assert spec.key not in store.active()
    if spec.kind == "api":
        assert store.api_credentials(spec.key) is not None


def test_an_api_row_is_not_asked_for_a_server_url(client: TestClient):
    """The page used to render "Server URL" for every row, including the `api` ones.

    Asking for an address that does not exist is how a credential, or a guessed
    endpoint, ends up stored as one — after which the row reports itself connected and
    there is nothing on the other end. Asserted against the served HTML because the
    bug was in what the template emitted, not in the catalogue.
    """
    signed_in(client, "conn@example.com")
    page = client.get("/settings")
    assert page.status_code == 200

    api_keys = [spec.key for spec in connectors.CATALOGUE if spec.kind == "api"]
    assert api_keys, "this test is meaningless with no api connector to check"
    for key in api_keys:
        assert f'id="url-{key}"' not in page.text, f"{key} is an api connector with no URL"
        assert f'id="tok-{key}"' in page.text, f"{key} still needs somewhere for its key"

    # And the MCP rows keep theirs, prefilled where the endpoint is published.
    assert 'id="url-higgsfield"' in page.text
    assert 'value="https://mcp.higgsfield.ai/mcp"' in page.text
