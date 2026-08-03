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

## Two ways in, and the page used to offer only the worse one

Several of these services authorise a remote MCP server by **browser sign-in**, not by
a pasted token. NexLev is one: it issues an `nlv_` API key, and it also accepts an OAuth
sign-in, which is what its claude.ai connector uses. Higgsfield is the same and issues
no key for its MCP at all.

For a long time this page could only ask for a token, and said so — the NexLev entry
carried the sentence "this page cannot open a browser flow, which is why it asks for
the key instead", and the Higgsfield entry told the operator to go and run
`claude mcp add` in a terminal themselves. Both were honest and both were the app
asking its user to finish connecting it, which is the same failure the toolchain
module exists to remove. It was reported as exactly that: the browser sign-in should
work here the way it works for a connector you add yourself.

`start_browser_signin()` does it. It runs `claude mcp add --transport … --scope user`
in a visible terminal; the CLI opens the browser, completes OAuth and stores the grant
under the user scope. The agent runs through that same CLI, so it inherits the session
with nothing further to configure — which is *why* this works and why there is no
token to store afterwards. `cli_servers()` reads back what the CLI holds, so a
connector authorised this way is reported as connected instead of looking untouched.

Three consequences worth knowing before changing any of it:

* **A browser-authorised connector has no token in `connectors.json`, and that is
  correct.** Reporting it as unconfigured because this file has no row for it is how
  the operator is sent to paste a credential the service never issued.
* **The terminal is visible on purpose.** See `terminal.open_terminal`.
* **It needs the Claude CLI**, because the grant lives in that CLI's user scope. On the
  ChatGPT backend the same connector has to be reached with a token, and the page says
  so rather than showing a button that would silently grant the wrong agent.

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
    # How this service can be reached: "mcp", "api", or "both".
    #
    # The distinction is not cosmetic and it was missing. `Store.active()` handed every
    # connected entry to the SDK as an MCP server, so an API-only service was wired up as
    # an endpoint that speaks a protocol it has never spoken — a permanent 401 that looks
    # exactly like a bad token, so the operator retries their credentials forever. An
    # `api` connector is never passed to the SDK; it is read by the provider adapter that
    # knows the service, and the agent reaches it through that adapter's tools.
    #
    # "both" is not a choice between them, which is why it is a third state rather than a
    # flag. Epidemic Sound is the case: it has an MCP server the *agent* can call in a
    # conversation, and a GraphQL API the *render pipeline* needs, because a pipeline node
    # runs on a worker thread with no conversation around it and cannot call an MCP tool.
    # Both may be configured at once, they authorise separately, and one working is not
    # evidence about the other — so they are stored and reported separately.
    kind: str = "mcp"

    @property
    def supports_mcp(self) -> bool:
        return self.kind in ("mcp", "both")

    @property
    def supports_api(self) -> bool:
        return self.kind in ("api", "both")
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
        # The credential NexLev's own 401 asks for, quoted from it rather than guessed:
        # "Provide either: 1) OAuth Bearer token, or 2) API key in Authorization header
        # (Bearer nlv_...), x-api-key header, or api_key query parameter."
        where="The URL is already filled in, so press Sign in and finish in the browser "
              "— that is the OAuth flow NexLev's own claude.ai connector uses, and it "
              "leaves nothing to paste back here. If you would rather use a key, it is "
              "a NexLev API key starting with `nlv_`, from your dashboard under API "
              "access. A session cookie, a JWT or a password will be refused: NexLev "
              "issues several kinds of credential and only the `nlv_` key works over "
              "this endpoint.",
        docs="Once connected, ask for outliers in a niche and I will query NexLev "
             "directly instead of asking you to paste numbers. A 401 on Test means the "
             "connection reached NexLev and the credential was not the one it wanted; "
             "the reply quotes NexLev's own words for which kinds it accepts. If you "
             "signed in through the browser rather than pasting a key, the grant lives "
             "in the Claude CLI and the agent reads it from there — which is why this "
             "row can be working with both boxes empty.",
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
              "everybody. Leave the token empty: this server has no API key to paste. "
              "Press Sign in and finish in the browser; the grant is stored by the "
              "Claude CLI that the agent runs through, so it inherits the session and "
              "there is nothing to bring back here.",
        # Said here because the failure is otherwise unreadable. `Test` on this entry
        # answers 401 with a `WWW-Authenticate: Bearer` challenge until the browser
        # sign-in has been done — the same 401 a rejected token gives, which is the
        # exact confusion this module exists to stop. Naming it means the operator
        # goes and signs in instead of hunting for a key that Higgsfield never issues.
        docs="Once you are signed in, ask for a shot and I can generate the still or "
             "the clip on Higgsfield instead of routing it to fal.ai. A 401 on Test "
             "here does not mean a bad token — it means the browser sign-in has not "
             "been completed, because this endpoint issues no key to paste. "
             "There is a second, separate way in: the REST API at "
             "platform.higgsfield.ai, whose credential is a `key:secret` pair pasted "
             "under Settings → Provider keys. That one the render pipeline does use — "
             "set a channel's image vendor to `higgsfield` and its plates are generated "
             "there, which is how a recurring character keeps the same face across "
             "shots and across episodes. The MCP is for asking; the key is for "
             "rendering. Both bill Higgsfield credits per generation, so neither is "
             "used unless it has been chosen.",
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
    # The API credential, kept apart from `token` rather than reusing it. On a `both`
    # service the two are different secrets for different mechanisms — an MCP bearer and
    # an API key — and one field holding either would make "is the API configured"
    # unanswerable, so the page could not tell the operator which half is live.
    api_key: str = ""
    enabled: bool = True
    note: str = ""

    @property
    def spec(self) -> ConnectorSpec:
        return BY_KEY.get(self.key, ConnectorSpec(self.key, self.key, "", ""))

    def credential(self) -> str:
        """The API credential, wherever this connection happens to keep it.

        An `api`-only connector predates the separate field and stores its key in
        `token`, so reading `api_key` alone would report every one of those as
        unconfigured after an upgrade — the file on disk is the operator's, and it does
        not get rewritten just because the schema grew a field.
        """
        return self.api_key or (self.token if self.spec.kind == "api" else "")

    @property
    def mcp_ready(self) -> bool:
        return self.spec.supports_mcp and bool(self.url)

    @property
    def api_ready(self) -> bool:
        return self.spec.supports_api and bool(self.credential())

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
                "api_key": mask(self.credential()) if self.credential() else "",
                # Reported apart, because on a `both` service they authorise separately
                # and one working says nothing about the other. Collapsing them into a
                # single "connected" would show a green dot for a service whose API half
                # — the half the render pipeline needs — was never configured.
                "mcp_ready": self.mcp_ready,
                "api_ready": self.api_ready,
                "connected": self.mcp_ready or self.api_ready,
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

        Filtering on `supports_mcp` is the fix for a real mis-wiring: without it an
        API-only service was handed to the SDK as an MCP endpoint, which fails with a 401
        that is indistinguishable from a rejected token — so the operator re-pastes
        working credentials indefinitely.

        A `both` service with only its API half configured is correctly absent: it has no
        URL, so there is nothing to hand over, and inventing one would recreate exactly
        the 401 this filter exists to prevent.
        """
        return {key: conn.as_mcp() for key, conn in self.connections.items()
                if conn.enabled and conn.mcp_ready}

    def api_credentials(self, key: str) -> Connection | None:
        """A configured API connector, for the provider adapter that speaks to it.

        Separate from `active()` because these never go near the SDK. The adapter asks for
        its own service by name and gets the credential or nothing. `both` services answer
        here as well as appearing in `active()` — a pipeline node runs on a worker thread
        with no conversation around it, so it cannot call an MCP tool however well that
        half is configured, and the API half is the only way it can reach the service.
        """
        conn = self.connections.get(key)
        if conn is None or not conn.enabled or not conn.api_ready:
            return None
        return conn

    def listing(self, *, cli_held: set[str] | None = None) -> list[dict]:
        """Every connector in the catalogue, connected or not, in catalogue order.

        `cli_held` is the set of servers the Claude CLI already holds — pass
        `cli_servers()`. It is a parameter rather than a call inside this method
        because this method is used in tests and in a request that must not spawn a
        subprocess just to draw a list; the caller decides whether it can afford to
        ask. Omitted means "not asked", which renders as the ordinary state.
        """
        held = cli_held or set()
        rows = []
        for spec in CATALOGUE:
            conn = self.connections.get(spec.key)
            row = conn.as_dict() if conn else {
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
            }
            rows.append(self._signin_fields(row, spec, held))
        # Anything configured that is not in the catalogue still belongs on the page;
        # dropping it would make it invisible and unremovable.
        for key, conn in self.connections.items():
            if key not in BY_KEY:
                rows.append(self._signin_fields(conn.as_dict(), conn.spec, held))
        return rows

    @staticmethod
    def _signin_fields(row: dict, spec: ConnectorSpec, held: set[str]) -> dict:
        """What the page needs to offer a browser sign-in, and to report one that
        already happened.

        `connected` is widened here rather than in `Connection.mcp_ready`, which is
        about this app's own stored configuration and should stay that. A grant made in
        the browser lives in the CLI and leaves nothing behind in `connectors.json`, so
        a row can be genuinely working with no URL and no token of ours — and reporting
        that as unconfigured is what sends the operator hunting for a key the service
        never issued.
        """
        signed_in = spec.supports_mcp and row["key"].lower() in held
        return {**row,
                "browser_signin": spec.supports_mcp,
                "cli_signed_in": signed_in,
                "connected": bool(row.get("connected")) or signed_in}


def default_path() -> Path:
    return get_settings().storage_dir / "connectors.json"


def active_servers() -> dict[str, dict]:
    """Convenience for the assistant: every live connector, ready for the SDK."""
    try:
        return Store.load().active()
    except Exception:                                  # pragma: no cover
        log.exception("could not load connectors — the agent will run without them")
        return {}


# ------------------------------------------------------------ the browser sign-in


def cli_servers() -> set[str]:
    """Which MCP servers the Claude CLI already holds, by name.

    Read from `claude mcp list` because that is where a browser-authorised grant
    lives: the OAuth token belongs to the CLI's user scope, not to this app, and
    `connectors.json` will never have a row for it. Without this read, a connector
    signed in through the browser looks untouched on the page, and the operator is
    invited to go and find a key that the service does not issue.

    Never raises and never blocks for long. A missing CLI, a slow one, or output in a
    shape this does not recognise all mean the same thing here — "cannot tell" — and
    the honest rendering of that is the page's ordinary unconfigured state, not an
    error. The grant still works either way, because the agent reads it from the CLI
    rather than from anything reported here.
    """
    import subprocess

    from . import auth

    cli = auth.find_cli()
    if not cli:
        return set()
    try:
        done = subprocess.run([cli, "mcp", "list"], capture_output=True, text=True,
                              errors="replace", timeout=10)
    except (OSError, subprocess.SubprocessError):
        return set()
    if done.returncode != 0:
        return set()

    # Matched on the leading name rather than on the whole line. The list prints
    # `name: url (status)` today, and a parser keyed to that exact shape turns a
    # cosmetic CLI change into "nothing is connected" on a machine where everything is.
    found: set[str] = set()
    for line in (done.stdout or "").splitlines():
        head = line.strip().split(":", 1)[0].strip()
        if head and " " not in head:
            found.add(head.lower())
    return found


def start_browser_signin(key: str, url: str = "") -> tuple[bool, str]:
    """Authorise one MCP connector in the browser, through the Claude CLI.

    Returns (opened, message). The message is shown verbatim, so it says what to do
    next rather than reporting an internal state.
    """
    from . import auth, terminal

    spec = BY_KEY.get(key)
    if spec is not None and not spec.supports_mcp:
        return False, (f"{spec.label} has no MCP server to sign in to — it is a REST "
                       "API, and it takes a key rather than a browser sign-in.")

    endpoint = (url or "").strip() or (spec.default_url if spec else "")
    if not endpoint:
        stored = Store.load().connections.get(key)
        endpoint = stored.url if stored else ""
    if not endpoint:
        return False, ("Fill in the server URL first — the sign-in has to be pointed at "
                       "an endpoint, and this connector does not publish a single one.")

    cli = auth.find_cli()
    if not cli:
        return False, ("The browser sign-in runs through the Claude Code CLI, which was "
                       f"not found. Install it: {auth.INSTALL_HINT}")

    transport = spec.transport if spec else "http"
    argv = [cli, "mcp", "add", "--transport", transport, "--scope", "user",
            key, endpoint]
    label = spec.label if spec else key
    return terminal.open_terminal(
        argv,
        done=(f"A terminal opened to sign in to {label}. Finish in the browser, close "
              "the window, then press Test — the agent picks the grant up from the CLI, "
              "so there is nothing to paste back here."),
        manual=(f"No terminal emulator was found to open. Run this yourself to sign in "
                f"to {label}, finish in the browser, then press Test:"),
    )
