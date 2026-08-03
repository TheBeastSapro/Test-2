"""Connectors: outside services the agent can reach, and how they get wired in.

## What a connector is here

An outside service the agent can *call*, in the same conversation, instead of asking you
to copy numbers between two apps. Connect NexLev and the agent gains its niche finder,
outlier search and channel analytics as things it can reach itself.

There are two kinds, and conflating them was a bug rather than a simplification:

* **`mcp`** — a remote MCP server, which hands the agent a set of tools. A URL and
  usually a token. This is what the module originally assumed everything was.
* **`api`** — a service with a REST API and no MCP server. A credential and no URL.

`Store.active()` used to hand every connected entry to the SDK as an MCP server, so an
API-only service was configured as an endpoint speaking a protocol it has never spoken.
That fails as a 401, which is exactly what a rejected token looks like — so the operator
re-pastes a credential that was never the problem. `active()` now returns only the `mcp`
ones, and `api_credentials()` is how the provider adapter for a given service asks for
its own.

That is a different mechanism from the provider keys on the Settings page. A provider
key lets *the pipeline* call a vendor (ElevenLabs renders the narration). A connector
lets *the agent* call one. Both matter and they are configured separately because
they fail separately: a dead ElevenLabs key breaks a render, a dead connector just
means the agent has fewer tools this turn and should say so.

## Why the URL is asked for rather than hard-coded

A connector's endpoint belongs to your account with that service, and for several of
these it is issued per workspace. Guessing one and shipping it would produce an app
that silently fails to connect and blames the network. So each entry below carries
where to find the URL, and nothing is assumed.

## Storage

The token is encrypted at rest with the same envelope key as provider credentials —
`crypto.encrypt`, keyed from `.env`, which is why `.env` must not be copied between
installs. The URL is not secret and is stored in the clear so a misconfiguration is
readable rather than opaque.
"""

from __future__ import annotations

import contextlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from ..config import get_settings
from ..crypto import decrypt, encrypt, mask

log = logging.getLogger("forgecast.agent.connectors")


@dataclass(frozen=True)
class ConnectorSpec:
    """One service the agent can be given tools from."""

    key: str
    label: str
    # What the agent gains. Written as capabilities, not marketing.
    gives: str
    where: str
    # "mcp" for a service that hands the agent tools over MCP; "api" for one that has a
    # REST API and no MCP server at all.
    #
    # This distinction is not cosmetic and it was missing. `Store.active()` handed every
    # connected entry to the SDK as an MCP server, so an API-only service was wired up as
    # an endpoint that speaks a protocol it has never spoken — a permanent 401 that looks
    # exactly like a bad token, so the operator retries their credentials forever. An
    # `api` connector is never passed to the SDK; it is read by the provider adapter that
    # knows the service, and the agent reaches it through that adapter's tools.
    kind: str = "mcp"
    # "http" or "sse". Remote MCP servers are one or the other; the service says which.
    # Ignored for `api` connectors.
    transport: str = "http"
    # A default endpoint only where the service publishes a single stable one.
    default_url: str = ""
    header: str = "Authorization"
    header_prefix: str = "Bearer "
    docs: str = ""


CATALOGUE: tuple[ConnectorSpec, ...] = (
    ConnectorSpec(
        key="nexlev",
        label="NexLev",
        gives="niche finder, faceless-channel outliers, channel and video analytics, "
              "RPM and monetisation checks, swipe files, and your own YouTube "
              "analytics once NexLev is linked to it",
        # Prefilled, because being asked for a URL you have never been shown is being
        # asked for something that does not exist from where you are standing — which is
        # how this was reported. Observed from a real connection rather than published by
        # NexLev, so it stays editable: if they move the endpoint, the box is the fix.
        default_url="https://prod.dashboard.nexlev.io/api/claude-mcp",
        where="The URL is already filled in. Leave the token empty unless NexLev issued "
              "you one — this endpoint authorises through your NexLev account, and a "
              "wrong token is worse than none.",
        docs="Once connected, ask for outliers in a niche and I will query NexLev "
             "directly instead of asking you to paste numbers. A 401 here means the "
             "connection reached NexLev and was not authorised — the account, not the "
             "URL.",
    ),
    ConnectorSpec(
        key="higgsfield",
        label="Higgsfield",
        gives="generating stills and B-roll clips from a prompt or a reference image "
              "across 30+ image and video models, training a reusable character "
              "identity so a series looks like one series, and reading back what it "
              "has already generated",
        # Higgsfield publishes one hosted endpoint for every account rather than
        # issuing one per workspace, so this is prefilled rather than asked for:
        # https://higgsfield.ai/mcp names it and `claude mcp add` uses the same URL.
        default_url="https://mcp.higgsfield.ai/mcp",
        where="The URL is already filled in — Higgsfield publishes one endpoint for "
              "everybody. Leave the token empty: this server has no API key to paste, "
              "it authorises by signing you in to higgsfield.ai in a browser, and that "
              "sign-in cannot happen from this page. To grant it, run "
              "`claude mcp add --transport http --scope user higgsfield "
              "https://mcp.higgsfield.ai/mcp` in a terminal and complete the sign-in "
              "it opens; the agent runs through that same CLI, so it inherits the "
              "session.",
        # Said here because the failure is otherwise unreadable. `Test` on this entry
        # answers 401 with a `WWW-Authenticate: Bearer` challenge until the browser
        # sign-in has been done — the same 401 a rejected token gives, which is the
        # exact confusion this module exists to stop. Naming it means the operator
        # goes and signs in instead of hunting for a key that Higgsfield never issues.
        docs="Once you are signed in, ask for a shot and I can generate the still or "
             "the clip on Higgsfield instead of routing it to fal.ai. A 401 on Test "
             "here does not mean a bad token — it means the browser sign-in above has "
             "not been completed, because this endpoint issues no key to paste. "
             "Higgsfield also has a separate REST API with real API keys "
             "(cloud.higgsfield.ai); that is a different mechanism and nothing in the "
             "render pipeline uses it yet.",
    ),
    ConnectorSpec(
        key="google_drive",
        label="Google Drive",
        gives="reading scripts, briefs and shot lists you keep in Drive",
        where="A Drive MCP endpoint from your workspace administrator.",
    ),
    ConnectorSpec(
        key="epidemic_sound",
        label="Epidemic Sound",
        gives="searching music and sound effects, and pulling a bed into a render",
        # Epidemic Sound is a REST API, not an MCP server. Listed as `mcp` it was being
        # handed to the SDK as an endpoint speaking a protocol it does not speak, which
        # fails as a 401 — the same symptom as a bad key, so the operator would keep
        # re-pasting a key that was never the problem.
        kind="api",
        where="Epidemic Sound → your partner or developer settings. This one is an API, "
              "so it takes a credential rather than a server URL.",
        docs="Stored and encrypted the same way as an MCP token. The music tools that "
             "use it are not built yet — the credential is accepted and kept, and "
             "nothing calls it until they are.",
    ),
)

BY_KEY = {spec.key: spec for spec in CATALOGUE}


@dataclass
class Connection:
    """A configured connector. `token` is plaintext only in memory, never on disk."""

    key: str
    url: str
    token: str = ""
    enabled: bool = True
    note: str = ""

    @property
    def spec(self) -> ConnectorSpec:
        return BY_KEY.get(self.key, ConnectorSpec(self.key, self.key, "", ""))

    def as_mcp(self) -> dict:
        """The SDK's server config for this connection."""
        spec = self.spec
        headers = {}
        if self.token:
            headers[spec.header] = f"{spec.header_prefix}{self.token}"
        config: dict = {"type": spec.transport, "url": self.url}
        if headers:
            config["headers"] = headers
        return config

    def as_dict(self) -> dict:
        """Safe to send to the page: the token is masked, never returned."""
        spec = self.spec
        return {"key": self.key, "label": spec.label, "gives": spec.gives,
                # The page needs this: an `api` connector has no server URL to ask for,
                # and showing it one is how the wrong thing gets pasted into it.
                "kind": spec.kind,
                "where": spec.where, "docs": spec.docs, "url": self.url,
                "token": mask(self.token) if self.token else "",
                # An `api` connector has no URL, so a URL test reported every one of
                # them as not connected however good the credential was.
                "connected": bool(self.token) if spec.kind == "api" else bool(self.url),
                "enabled": self.enabled,
                "note": self.note}


@dataclass
class Store:
    """Connections on disk, beside the database rather than inside it.

    A file rather than a table for one reason: the agent's MCP servers have to be
    resolved before a request exists, from a worker thread, at CLI start-up. Reaching
    for a request-scoped database session in that context is how a config load ends
    up holding a connection it should not have.
    """

    path: Path
    connections: dict[str, Connection] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> Store:
        target = Path(path) if path else default_path()
        store = cls(path=target)
        if not target.exists():
            return store
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("connectors file at %s is unreadable — starting empty", target)
            return store

        for key, entry in (raw.get("connectors") or {}).items():
            token = ""
            if entry.get("token"):
                try:
                    token = decrypt(entry["token"])
                except Exception:
                    # A token encrypted with a different `.env` key. Say so rather
                    # than crashing the page — the fix is to paste it again.
                    log.warning("could not decrypt the %s token (wrong .env key?)", key)
                    entry["note"] = ("Token could not be decrypted — this install has "
                                     "a different encryption key. Paste it again.")
            store.connections[key] = Connection(
                key=key, url=entry.get("url", ""), token=token,
                enabled=bool(entry.get("enabled", True)), note=entry.get("note", ""),
            )
        return store

    def save(self) -> None:
        payload = {"connectors": {
            key: {"url": conn.url,
                  "token": encrypt(conn.token) if conn.token else "",
                  "enabled": conn.enabled, "note": conn.note}
            for key, conn in self.connections.items()
        }}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        with contextlib.suppress(OSError):             # Windows and odd filesystems
            self.path.chmod(0o600)

    def set(self, key: str, url: str, token: str = "", enabled: bool = True) -> Connection:
        url = (url or "").strip()
        existing = self.connections.get(key)
        # An empty token on an existing connection means "leave it alone", not
        # "clear it" — the page shows a mask, so an unedited field submits blank.
        if not token and existing is not None:
            token = existing.token
        conn = Connection(key=key, url=url, token=token.strip(), enabled=enabled)
        self.connections[key] = conn
        self.save()
        return conn

    def remove(self, key: str) -> bool:
        if key in self.connections:
            del self.connections[key]
            self.save()
            return True
        return False

    def active(self) -> dict[str, dict]:
        """MCP server configs for everything connected, switched on, and *actually MCP*.

        The `kind == "mcp"` filter is the fix for a real mis-wiring: without it an
        API-only service was handed to the SDK as an MCP endpoint, which fails with a 401
        that is indistinguishable from a rejected token — so the operator re-pastes
        working credentials indefinitely.
        """
        return {key: conn.as_mcp() for key, conn in self.connections.items()
                if conn.enabled and conn.url and conn.spec.kind == "mcp"}

    def api_credentials(self, key: str) -> Connection | None:
        """A configured `api` connector, for the provider adapter that speaks to it.

        Separate from `active()` because these never go near the SDK. The adapter asks
        for its own service by name and gets the credential or nothing.
        """
        conn = self.connections.get(key)
        if conn is None or not conn.enabled or conn.spec.kind != "api":
            return None
        return conn if (conn.token or conn.url) else None

    def listing(self) -> list[dict]:
        """Every connector in the catalogue, connected or not, in catalogue order."""
        rows = []
        for spec in CATALOGUE:
            conn = self.connections.get(spec.key)
            rows.append(conn.as_dict() if conn else {
                "key": spec.key, "label": spec.label, "gives": spec.gives,
                "kind": spec.kind,
                "where": spec.where, "docs": spec.docs,
                # `default_url` was carried on the spec and never read, so a row that
                # says "the URL is already filled in" arrived with an empty box — the
                # copy and the page disagreed, and the operator went looking for an
                # endpoint the app already knew. An unconfigured row starts from the
                # published default; a configured one keeps whatever was saved.
                "url": spec.default_url, "token": "",
                "connected": False, "enabled": False, "note": "",
            })
        # Anything configured that is not in the catalogue still belongs on the page;
        # dropping it would make it invisible and unremovable.
        for key, conn in self.connections.items():
            if key not in BY_KEY:
                rows.append(conn.as_dict())
        return rows


def default_path() -> Path:
    return get_settings().storage_dir / "connectors.json"


def active_servers() -> dict[str, dict]:
    """Convenience for the assistant: every live connector, ready for the SDK."""
    try:
        return Store.load().active()
    except Exception:                                  # pragma: no cover
        log.exception("could not load connectors — the agent will run without them")
        return {}
