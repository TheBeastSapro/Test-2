"""Connectors: outside services the agent can reach, and how they get wired in.

## What a connector is here

Not another API key field. A connector is a **remote MCP server** — a service that
hands the agent a set of tools. Connect NexLev and the agent gains NexLev's niche
finder, outlier search and channel analytics as things it can *call*, in the same
conversation, without you copying numbers between two apps.

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
    # "http" or "sse". Remote MCP servers are one or the other; the service says which.
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
        where="NexLev → Settings → MCP / integrations. Copy the server URL and token "
              "issued for your workspace.",
        docs="Once connected, ask for outliers in a niche and I will query NexLev "
             "directly instead of asking you to paste numbers.",
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
        where="Epidemic Sound → integrations.",
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
                "where": spec.where, "docs": spec.docs, "url": self.url,
                "token": mask(self.token) if self.token else "",
                "connected": bool(self.url), "enabled": self.enabled,
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
        """MCP server configs for everything connected and switched on."""
        return {key: conn.as_mcp() for key, conn in self.connections.items()
                if conn.enabled and conn.url}

    def listing(self) -> list[dict]:
        """Every connector in the catalogue, connected or not, in catalogue order."""
        rows = []
        for spec in CATALOGUE:
            conn = self.connections.get(spec.key)
            rows.append(conn.as_dict() if conn else {
                "key": spec.key, "label": spec.label, "gives": spec.gives,
                "where": spec.where, "docs": spec.docs, "url": "", "token": "",
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
