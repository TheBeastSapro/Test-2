"""Epidemic Sound: voice artists for narration, reached over its MCP server.

## What this service actually is

It was wired into this app as a music library on the strength of its name. That was
wrong on two counts, and both were checked against the live server's own tool schemas
rather than inferred:

* Its narration half is **text-to-speech voiced by real voice artists** — `ListVoices`,
  `GenerateVoiceover`, `PollVoiceoverGenerationStatus`, `DownloadVoiceover`. That is the
  half this module implements, because narration is a pipeline stage that already exists
  and the local Chatterbox route needs torch and a GPU.
* It also carries recordings and sound effects (`SearchRecordings`, `SearchSoundEffects`,
  `DownloadRecording`, …). Not built here — see "What is deliberately absent".

Two shape facts that a REST-shaped adapter would have got wrong:

* The catalogue is **GraphQL**. The operations above are GraphQL fields, so there is no
  path-and-query-string endpoint to call and no place to put a `?mood=` parameter.
* It is reached through an **MCP server** at one published URL, not an API host.
  https://developers.epidemicsound.com/docs/mcp/ publishes both the URL and the two auth
  options: OAuth dynamic client registration, or `Authorization: Bearer <api key>`. Only
  the second is usable from a server with no browser and no redirect route, so that is
  what this reads.

Epidemic Sound *also* runs a separate REST Partner Content API (base
`https://partner-content-api.epidemicsound.com`, documented at
https://developers.epidemicsound.com/docs/api-reference/). It is a different product
surface, it is partner-only, and it has no voiceover endpoints at all — which is the
evidence that the MCP server is the door for narration rather than a wrapper over it.

## Why the fit with the existing casting flow is the whole point

`voice/casting.py` ranks voices on **measured** pitch: it downloads each voice's own
preview clip and runs the same f0 estimator used on the reference video, so the central
comparison is a measurement against a measurement rather than against an adjective.
Every Epidemic voice carries an `exampleAudioUrl`, so its artists can be measured on
exactly that basis.

So `list_voices` below emits the record shape `voice.discover.parse_voice` already
consumes, and casting, the audition samples and the gate all work unchanged. A second
voice-selection path would have meant two rankings that disagree about the same voice,
with no way to tell which one the operator was looking at.

## What is deliberately absent

* **Music and sound effects.** Out of scope for narration, and the licence terms matter
  before anyone adds them: the REST docs state that only *connected users with an active
  Epidemic Sound subscription* may download premium-library tracks, that free-tier tracks
  carry a personal (non-commercial) licence, and that exporting a track into published
  content is a reportable event. A bed baked into a monetised render is none of those
  things by default. Establish the entitlement before building the download.
* **Dubbing.** Each voice reports `languages: [String!]!`, which is the honest basis for
  narrating one script in several languages. `list_voices` passes that list through, but
  nothing consumes it yet: `voice.discover.MeasuredVoice` has no language field, so the
  cached catalogue drops it. That field is the change dubbing needs, and inventing a
  parallel catalogue to hold it here would fork voice selection in two.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import httpx

from ..credits import PER_UNIT_COSTS
from .base import (
    MediaResult,
    ProviderError,
    ProviderTimeout,
    VoiceProvider,
)

log = logging.getLogger("forgecast.providers.epidemic")

CONNECTOR_KEY = "epidemic_sound"

# Published as a single stable endpoint at https://developers.epidemicsound.com/docs/mcp/,
# which is the one case connectors.py allows a default URL for. A connector that carries
# its own URL still wins, so an operator is never stuck behind a moved endpoint.
DEFAULT_MCP_URL = "https://www.epidemicsound.com/a/mcp-service/mcp"

# Generation is asynchronous: `GenerateVoiceover` returns GENERATING and the audio only
# exists once a poll reports DONE. An unbounded poll loop is how a run sits on a spinner
# for the rest of the day, so the wait has a ceiling and the timeout says what to do next.
POLL_INTERVAL_SECONDS = 2.0
POLL_TIMEOUT_SECONDS = 180.0

# Editing a recording is the heavier job of the two — it re-cuts audio and, unless asked
# not to, separates stems — so it gets its own ceiling rather than sharing narration's.
EDIT_POLL_INTERVAL_SECONDS = 3.0
EDIT_POLL_TIMEOUT_SECONDS = 420.0

# `targetDurationMs` is capped at 300000 by the vendor: five minutes. This app's default
# long-form target is eight, so the cap is reached by the *normal* case, not an edge one.
#
# The resolution is `loopable`, which the schema documents as "seamless when repeated":
# ask for a five-minute loopable edit and repeat it with `render.audio.loop_to_length`,
# which already exists for exactly this. Stitching several independent edits was the
# alternative and it is worse — each edit is cut to resolve on its own ending, so the
# joins would land on two resolutions back to back.
#
# Under the cap nothing loops: the edit is cut to the exact length with `forceDuration`,
# which is the whole point of the operation — a bed that ends when the video ends,
# musically, instead of being faded out mid-phrase.
EDIT_MAX_DURATION_MS = 300_000

# One MCP round trip. Generous enough for a cold server, short enough that a hung
# connection fails inside a node rather than outliving the run.
CALL_TIMEOUT_SECONDS = 60.0
_DOWNLOAD_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)

# Container signatures, because `DownloadVoiceover` returns a signed `assetUrl` and does
# not state a format. Writing every download as `.mp3` produced files whose extension
# contradicted their contents, which is a demuxer guess waiting to go wrong at concat
# time — the narration node joins these per-scene files with ffmpeg.
_SIGNATURES = (
    (b"ID3", ".mp3"),
    (b"RIFF", ".wav"),
    (b"OggS", ".ogg"),
    (b"fLaC", ".flac"),
)
_MIMES = {
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
    ".flac": "audio/flac", ".m4a": "audio/mp4",
}


# --------------------------------------------------------------------- credential


def load_credential():
    """The Epidemic Sound connector, whichever `kind` the catalogue currently calls it.

    Deliberately not `api_credentials()` alone. That accessor filters on
    `spec.kind == "api"`, and this entry is being corrected to `kind="mcp"` because the
    service really is an MCP server — reading it through only one of the two accessors
    would make this provider vanish the moment that one-word fix lands, with no error to
    explain why narration suddenly had no vendor.

    One function so a test can substitute it without reaching into the store, for the
    same reason `research.keyless._run` exists: patching the store itself would replace
    it for every other connector in the same interpreter.

    `connectors` is imported inside the function on purpose: `forgecast.agent` pulls in
    the studio, which pulls in the graph engine, which reaches back for the provider
    registry. At module scope that is an import cycle that only shows up depending on
    which module the process happens to load first.
    """
    from ..agent import connectors

    try:
        store = connectors.Store.load()
    except Exception:                                              # pragma: no cover
        log.exception("could not read the connector store")
        return None

    conn = store.api_credentials(CONNECTOR_KEY)
    if conn is not None:
        return conn

    conn = store.connections.get(CONNECTOR_KEY)
    if conn is None or not conn.enabled:
        return None
    return conn if (conn.token or conn.url) else None


def available() -> tuple[bool, str]:
    """Can Epidemic Sound be reached, and if not, the one thing that would fix it.

    Phrased as plain text with no backticks: this sentence is printed under a form and
    in a tool result, where a backtick reads as a typo rather than as code.
    """
    conn = load_credential()
    if conn is None:
        return False, (
            "Epidemic Sound is not connected, so its voice artists cannot be listed and "
            "narration cannot be generated from them. Connect it under Settings, "
            "Connectors — it takes the API key from your Epidemic Sound developer portal."
        )
    if not conn.token:
        return False, (
            "Epidemic Sound is connected but has no API key stored, and its MCP server "
            "authorises every call with one. Paste the key from your Epidemic Sound "
            "developer portal under Settings, Connectors."
        )
    return True, ""


# ------------------------------------------------------------------- the MCP call


def _payload(result) -> dict:
    """The one JSON object an MCP tool result carries, or an error that names the text.

    `structuredContent` is preferred where the server sends it; otherwise the text block
    is parsed. A result that is neither is surfaced verbatim rather than as "unexpected
    response", because on this server the unparseable case is usually the vendor
    explaining what it objected to and that sentence is the only useful thing present.
    """
    if getattr(result, "isError", False):
        raise ProviderError(
            f"epidemic sound rejected the call: {_text(result) or 'no detail given'}",
            provider="epidemic-sound",
        )

    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return _unwrap(structured)

    text = _text(result)
    if not text:
        raise ProviderError("epidemic sound returned an empty result",
                            provider="epidemic-sound")
    try:
        parsed = json.loads(text)
    except ValueError as exc:
        raise ProviderError(
            f"epidemic sound returned something that was not JSON: {text[:300]}",
            provider="epidemic-sound",
        ) from exc
    if not isinstance(parsed, dict):
        raise ProviderError(
            f"epidemic sound returned {type(parsed).__name__}, not an object: {text[:200]}",
            provider="epidemic-sound",
        )
    return _unwrap(parsed)


def _unwrap(payload: dict, *, depth: int = 4) -> dict:
    """Strip GraphQL envelopes so callers see the object the schema documents.

    This is an MCP bridge over a GraphQL API, and a GraphQL answer is nested under
    `data` and then under the field's own name. Which of those layers a bridge keeps is
    not something the tool schemas state, so peeling single-key wrappers means the caller
    reads `status` and `assetUrl` where they are documented rather than guessing at a
    shape that could change under it.

    Only a *single-key* dict is peeled, and only while its value is itself a dict. That is
    what stops it eating a real result: `ListVoices` answers `{nodes, pageInfo}` and
    `DownloadVoiceover` answers `{assetUrl}` whose value is a string — neither qualifies.
    """
    for _ in range(depth):
        if len(payload) != 1:
            return payload
        inner = next(iter(payload.values()))
        if not isinstance(inner, dict):
            return payload
        payload = inner
    return payload


def _text(result) -> str:
    parts = []
    for block in getattr(result, "content", None) or []:
        value = getattr(block, "text", None)
        if value:
            parts.append(str(value))
    return "\n".join(parts).strip()


@dataclass
class EpidemicSession:
    """A live MCP session, held open across the calls of one operation.

    Generating one line of narration is generate, then poll until done, then download.
    Opening a fresh session for each of those would pay the initialise handshake three
    times per scene, and a ten-scene script narrates scene by scene.
    """

    session: object
    url: str

    async def call(self, tool: str, arguments: dict) -> dict:
        try:
            result = await self.session.call_tool(  # type: ignore[attr-defined]
                tool, arguments,
                read_timeout_seconds=timedelta(seconds=CALL_TIMEOUT_SECONDS),
            )
        except TimeoutError as exc:
            raise ProviderTimeout(
                f"epidemic sound did not answer {tool} within "
                f"{CALL_TIMEOUT_SECONDS:.0f}s",
                provider="epidemic-sound",
            ) from exc
        return _payload(result)


@contextlib.asynccontextmanager
async def open_session(*, url: str = "", token: str = ""):
    """Connect to the MCP server, or explain what is missing.

    `mcp` is imported here rather than at module scope for two reasons: it arrives as a
    dependency of claude-agent-sdk rather than a direct pin of this project, and nothing
    that merely imports this module should pay for a protocol library it will not use.
    """
    if not token:
        raise ProviderError(available()[1], provider="epidemic-sound")

    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    endpoint = url or DEFAULT_MCP_URL
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with streamablehttp_client(
            endpoint, headers=headers, timeout=CALL_TIMEOUT_SECONDS
        ) as (read, write, _get_session_id), ClientSession(read, write) as session:
            await session.initialize()
            yield EpidemicSession(session=session, url=endpoint)
    except (ProviderError, ProviderTimeout):
        raise
    except BaseException as exc:
        # BaseException, not Exception: anyio raises an ExceptionGroup, which on older
        # interpreters derives from BaseException rather than Exception, so catching
        # Exception let the real transport failure escape untranslated.
        raise _translate(exc, endpoint) from exc


def _flatten(exc: BaseException) -> list[BaseException]:
    """Every exception inside a possibly-nested ExceptionGroup, plus its `__cause__`s.

    The MCP client runs its transport in an anyio task group, so a 401 from the server
    does not arrive as an `httpx.HTTPStatusError` — it arrives as "unhandled errors in a
    TaskGroup (1 sub-exception)" wrapping one. Catching httpx exceptions directly looked
    correct and could never fire, which turned the single most likely failure on this
    integration, a rejected API key, into a sentence with no actionable content in it.
    """
    found: list[BaseException] = []
    # Identity, not equality: exceptions of the same type with the same message compare
    # equal in some libraries, and dropping one of those loses the only frame that named
    # the real cause. A cycle through `__cause__` would otherwise loop forever.
    seen: set[int] = set()
    queue: list[BaseException] = [exc]
    while queue:
        current = queue.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        found.append(current)
        if isinstance(current, BaseExceptionGroup):
            queue.extend(current.exceptions)
        if current.__cause__ is not None:
            queue.append(current.__cause__)
    return found


def _translate(exc: BaseException, endpoint: str) -> ProviderError:
    """Turn whatever the transport raised into something the operator can act on."""
    inner = _flatten(exc)

    for item in inner:
        if isinstance(item, httpx.HTTPStatusError):
            status = item.response.status_code
            if status in (401, 403):
                # A rejected key and a wrong endpoint both surface as an auth failure,
                # so the message names both rather than sending the operator off to
                # re-paste a key that was never the problem.
                return ProviderError(
                    f"epidemic sound refused the connection ({status}). Either the "
                    f"stored API key is not valid, or {endpoint} is not the MCP endpoint "
                    "for your account — both fail this way. Check the key under "
                    "Settings, Connectors.",
                    provider="epidemic-sound",
                )
            return ProviderError(
                f"epidemic sound returned {status} connecting to {endpoint}",
                provider="epidemic-sound",
                retryable=status >= 500 or status == 429,
            )

    for item in inner:
        if isinstance(item, httpx.TimeoutException | TimeoutError):
            return ProviderTimeout(
                f"could not reach {endpoint} within {CALL_TIMEOUT_SECONDS:.0f}s",
                provider="epidemic-sound",
            )

    # Name the innermost real error rather than the task-group wrapper, whose message
    # only ever says how many sub-exceptions there were.
    detail = next(
        (f"{type(item).__name__}: {item}" for item in reversed(inner)
         if not isinstance(item, BaseExceptionGroup) and str(item)),
        str(exc) or type(exc).__name__,
    )
    return ProviderError(
        f"could not open an MCP session with epidemic sound at {endpoint} — {detail}",
        provider="epidemic-sound", retryable=True,
    )


# ------------------------------------------------------------------- the provider


def voiceover_credits(characters: int) -> int:
    """Price narration on the same scale the node's own estimate uses.

    Every other adapter here converts a *published* vendor unit price at a 2x markup.
    Epidemic Sound publishes no per-character price for partner voiceover — it is
    included in a negotiated agreement — so there is no figure to convert and inventing
    one would put a fabricated cost in `/analytics`.

    What can be stated is that this is narration, and `credits.PER_UNIT_COSTS["voice"]`
    is already what a voice node reserves per thousand characters. Deriving from it keeps
    the estimate and the settled actual identical by construction, which is the property
    that matters: returning 0 instead would report narration as free and quietly make
    every run's spend look smaller than its hold.
    """
    _unit, per, size = PER_UNIT_COSTS["voice"]
    return max(1, math.ceil(max(characters, 1) / size) * per)


def to_epidemic_speed(multiplier: float) -> float:
    """Turn the pipeline's speed *multiplier* into Epidemic's -1..1 offset.

    The two scales collide at exactly the wrong place. `VoiceProvider.synthesize` takes a
    multiplier where 1.0 means normal, and Epidemic takes an offset where 0.0 means
    normal and 1.0 is the fastest it will read. Passing the multiplier straight through
    would have requested maximum speed for every default narration in the app.
    """
    return max(-1.0, min(1.0, float(multiplier) - 1.0))


def _voice_record(node: dict) -> dict:
    """One `Voice` as the record `voice.discover.parse_voice` already consumes.

    Mapping rather than a new dataclass, so Epidemic artists rank in the existing casting
    flow instead of a parallel one. Two choices worth stating:

    * `location` fills `accent`. It is where the artist is from — the closest thing
      Epidemic publishes to an accent, and not the same claim. Casting matches accent by
      substring, so asking for "british" against "London, United Kingdom" does not score
      as a match; it comes back as the caveat "London, United Kingdom accent, not
      british", which is the true statement. Translating locations into accent names
      here would turn that caveat into a false match.
    * `use_case` is left empty. Epidemic publishes none, and casting's
      REGISTER_USE_CASES scoring only fires on a real vendor label — filling it with a
      guess would manufacture a reason the operator cannot check.
    """
    metadata = node.get("metadata") or {}
    return {
        "voice_id": str(node.get("id") or ""),
        "name": str(node.get("title") or ""),
        # These are licensed voice artists, not synthetic presets. `professional` is the
        # category casting already treats that way when it ranks ownership.
        "category": "professional",
        # The vendor tag. `MeasuredVoice.provenance` only special-cases "library", so
        # this is free to carry the vendor's name — and it has to carry something, or a
        # merged shortlist cannot tell the operator which service a candidate is on.
        "provenance": "epidemic",
        "labels": {
            "gender": str(metadata.get("gender") or ""),
            "accent": str(metadata.get("location") or ""),
            "descriptive": str(metadata.get("characteristics") or ""),
            "use_case": "",
            "language": str(node.get("languageCode") or ""),
        },
        "preview_url": str(node.get("exampleAudioUrl") or ""),
        # Passed through for the studio tool. The cached catalogue drops these because
        # MeasuredVoice has no field for them; see the module docstring on dubbing.
        "languages": [str(item) for item in (node.get("languages") or [])],
        "biography": str(metadata.get("biography") or ""),
    }


@dataclass
class EpidemicVoiceProvider(VoiceProvider):
    """Narration from Epidemic Sound's voice artists.

    Satisfies `VoiceProvider` so the narration node cannot tell it apart from
    ElevenLabs, which is what lets a channel be re-pointed at either without touching
    pipeline code.
    """

    name: str = "epidemic-sound"
    # Unused: the credential is a connector, not a provider key, so the registry
    # constructs this with nothing and it reads its own. Kept because BaseProvider's
    # contract has it and dropping it would break `cls(api_key)` construction.
    api_key: str = ""
    # Empty means "let the voice read in its own language". The `VoiceProvider` contract
    # has no language parameter and widening it would break the two adapters this file
    # does not own, so a channel language is set here or not at all.
    language: str = ""

    def available(self) -> tuple[bool, str]:
        return available()

    def _credential(self) -> tuple[str, str]:
        conn = load_credential()
        if conn is None or not conn.token:
            raise ProviderError(available()[1], provider=self.name)
        return conn.url, conn.token

    # -- catalogue --------------------------------------------------------------

    async def list_voices(self, *, limit: int = 200) -> list[dict]:
        """Every voice artist, in the record shape the casting catalogue consumes.

        Paged because `ListVoices` reports `pageInfo.hasMoreItems` and a single page is
        not the catalogue — stopping at the first would have cast against a slice of the
        roster while reporting it as the whole one.
        """
        url, token = self._credential()
        collected: list[dict] = []
        async with open_session(url=url, token=token) as remote:
            offset = 0
            page_size = max(1, min(int(limit), 100))
            while len(collected) < limit:
                payload = await remote.call(
                    "ListVoices", {"limit": page_size, "offset": offset}
                )
                nodes = payload.get("nodes") or []
                collected += [_voice_record(node) for node in nodes
                              if isinstance(node, dict) and node.get("id")]
                page = payload.get("pageInfo") or {}
                if not page.get("hasMoreItems") or not nodes:
                    break
                offset += len(nodes)

        log.info("epidemic sound: %d voice artists", len(collected))
        return collected[:limit]

    # -- synthesis --------------------------------------------------------------

    async def synthesize(
        self, text: str, *, voice_id: str, out_path: Path, speed: float = 1.0
    ) -> MediaResult:
        if not voice_id:
            raise ProviderError("no voice_id set on the channel", provider=self.name)
        if not text.strip():
            raise ProviderError("nothing to narrate", provider=self.name)

        url, token = self._credential()
        request: dict = {
            "voiceId": voice_id,
            "text": text,
            "speed": to_epidemic_speed(speed),
        }
        if self.language:
            request["languageCode"] = self.language

        async with open_session(url=url, token=token) as remote:
            started = await remote.call("GenerateVoiceover", {"input": request})
            voiceover_id = str(started.get("id") or "")
            if not voiceover_id:
                raise ProviderError(
                    "epidemic sound accepted the text but returned no voiceover id, so "
                    "there is nothing to poll for",
                    provider=self.name, retryable=True,
                )
            status = await self._await_done(remote, voiceover_id, started)
            download = await remote.call("DownloadVoiceover",
                                         {"input": {"id": voiceover_id}})

        asset_url = str(download.get("assetUrl") or "")
        if not asset_url:
            raise ProviderError(
                f"voiceover {voiceover_id} finished but no download URL came back",
                provider=self.name, retryable=True,
            )

        path = await self._fetch(asset_url, out_path)

        from ..render import ffmpeg as ff

        duration = await asyncio.to_thread(ff.ffprobe_duration, path)
        return MediaResult(
            path=path,
            mime=_MIMES.get(path.suffix, "audio/mpeg"),
            credits=voiceover_credits(len(text)),
            provider=self.name,
            duration_seconds=duration,
            meta={
                "characters": len(text),
                "voice_id": voice_id,
                "voiceover_id": voiceover_id,
                "speed": request["speed"],
                "language": self.language or "voice default",
                "polls": status.get("polls", 0),
            },
        )

    async def _await_done(self, remote: EpidemicSession, voiceover_id: str,
                          started: dict) -> dict:
        """Poll until DONE, and stop rather than wait forever.

        `failedReason` is carried through verbatim. Replacing it with a generic failure
        was the difference between "the text contains an unsupported language" and
        "voiceover failed", and only one of those tells the operator what to change.
        """
        state = str(started.get("status") or "").upper()
        polls = 0
        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS

        while state != "DONE":
            if state == "FAILED":
                reason = str(started.get("failedReason") or "").strip()
                raise ProviderError(
                    f"epidemic sound could not generate that narration: "
                    f"{reason or 'no reason given'}",
                    provider=self.name,
                )
            if time.monotonic() >= deadline:
                raise ProviderTimeout(
                    f"voiceover {voiceover_id} was still generating after "
                    f"{POLL_TIMEOUT_SECONDS:.0f}s and polling stopped. The job may yet "
                    "finish on Epidemic Sound's side — nothing was charged for it here.",
                    provider=self.name,
                )
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            polls += 1
            started = await remote.call("PollVoiceoverGenerationStatus",
                                        {"id": voiceover_id})
            state = str(started.get("status") or "").upper()

        return {**started, "polls": polls}

    async def _fetch(self, asset_url: str, out_path: Path) -> Path:
        """Download the finished audio, naming the file after what it actually is."""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            async with httpx.AsyncClient(
                timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True
            ) as client:
                response = await client.get(asset_url)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"downloading the voiceover timed out: {exc}",
                                  provider=self.name) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"could not download the voiceover: {exc}",
                                provider=self.name, retryable=True) from exc

        if not response.is_success:
            raise ProviderError(
                f"the voiceover download URL returned {response.status_code}",
                provider=self.name,
                retryable=response.status_code >= 500 or response.status_code == 429,
            )
        body = response.content
        if len(body) < 512:
            # A signed URL that has already expired answers 200 with a stub, and a
            # stub written as narration fails much later inside ffmpeg concat.
            raise ProviderError(
                f"the voiceover download returned {len(body)} bytes, which is too small "
                "to be audio — the signed URL may have expired",
                provider=self.name, retryable=True,
            )

        final = out_path.with_suffix(_suffix_for(body))
        final.write_bytes(body)
        return final


def _suffix_for(body: bytes) -> str:
    for signature, suffix in _SIGNATURES:
        if body.startswith(signature):
            return suffix
    if body[4:8] == b"ftyp":
        return ".m4a"
    # A bare MPEG frame sync has no magic string, so mp3 is the residual case rather
    # than a guess about an unknown container.
    if body[:1] == b"\xff":
        return ".mp3"
    log.warning("epidemic sound returned audio with no recognised container signature")
    return ".mp3"


# ------------------------------------------------------------------------- offline


# Deterministic voice artists for `FORGECAST_PROVIDER_MODE=mock`. Shaped like Epidemic's
# own records — `location`, `characteristics`, a `languages` list — rather than like
# ElevenLabs', because the generic voice mock mirrors the ElevenLabs catalogue and so
# never exercised the fields this adapter maps. The whole casting path, gate included,
# runs against these with no credential and no network.
_MOCK_ARTISTS: tuple[dict, ...] = (
    {"id": "11111111-1111-4111-8111-111111111111", "title": "Mock Halvorsen",
     "gender": "male", "location": "Oslo, Norway", "languages": ["en", "nb"],
     "characteristics": "calm, deep, documentary narration",
     "biography": "Offline stand-in for an Epidemic Sound voice artist."},
    {"id": "22222222-2222-4222-8222-222222222222", "title": "Mock Adeyemi",
     "gender": "female", "location": "London, United Kingdom", "languages": ["en"],
     "characteristics": "warm, measured, storyteller",
     "biography": "Offline stand-in for an Epidemic Sound voice artist."},
    {"id": "33333333-3333-4333-8333-333333333333", "title": "Mock Rivera",
     "gender": "female", "location": "Austin, United States",
     "languages": ["en", "es"],
     "characteristics": "energetic, bright, upbeat social media reads",
     "biography": "Offline stand-in for an Epidemic Sound voice artist."},
)

# Pitch per artist for the placeholder tone, so two mock voices are audibly different
# and a measured catalogue built offline does not collapse every voice onto one band.
_MOCK_PITCH = {"Mock Halvorsen": 98, "Mock Adeyemi": 172, "Mock Rivera": 214}


def _mock_preview_url(artist: dict) -> str:
    """A preview clip that can actually be measured, as a local file URL.

    The point of wiring these voices into casting is that each one's pitch is *measured*
    from its own preview rather than read off a label. A mock whose `exampleAudioUrl`
    pointed nowhere left that path untested and reported every offline artist as
    `preview_download_failed`, so the one property worth demonstrating was the one thing
    mock mode could not show. `voice.discover.measure_preview` fetches with curl, which
    speaks `file://`, so a tone written to disk measures for real with no network.

    A tone, not speech: `_pitch` is an autocorrelation estimator verified accurate to
    about 1% on known tones, so the measured f0 comes back as the frequency written here
    and the three mock artists land in three different pitch bands.
    """
    from ..config import get_settings
    from ..render import ffmpeg as ff

    path = (get_settings().storage_dir / "mock_epidemic_previews"
            / f"{artist['id']}.m4a")
    if not path.exists():
        try:
            ff.make_tone_audio(path, 3.0,
                               frequency=_MOCK_PITCH.get(artist["title"], 150))
        except Exception as exc:                                   # pragma: no cover
            # ffmpeg absent is a legitimate state on a fresh install, and it must not
            # turn listing voices into a crash — casting simply has no pitch to use.
            log.warning("could not write a mock preview clip: %s", exc)
            return ""
    return path.resolve().as_uri()


@dataclass
class MockEpidemicVoice(VoiceProvider):
    """Epidemic Sound's shapes without Epidemic Sound.

    Not a test double bolted on: mock mode is how every test and every fresh install
    runs, so an adapter with no offline twin is an adapter whose surrounding code cannot
    be exercised at all.
    """

    name: str = "mock-epidemic-voice"
    api_key: str = ""
    language: str = ""
    generated: list[str] = field(default_factory=list)

    def available(self) -> tuple[bool, str]:
        return True, ""

    async def list_voices(self, *, limit: int = 200) -> list[dict]:
        return [
            _voice_record({
                "id": artist["id"],
                "title": artist["title"],
                "exampleAudioUrl": _mock_preview_url(artist),
                "languageCode": artist["languages"][0],
                "languages": artist["languages"],
                "metadata": {
                    "gender": artist["gender"],
                    "location": artist["location"],
                    "biography": artist["biography"],
                    "characteristics": artist["characteristics"],
                },
            })
            for artist in _MOCK_ARTISTS[:limit]
        ]

    async def synthesize(
        self, text: str, *, voice_id: str, out_path: Path, speed: float = 1.0
    ) -> MediaResult:
        if not voice_id:
            raise ProviderError("no voice_id set on the channel", provider=self.name)

        from ..render import ffmpeg as ff
        from .mock import WORDS_PER_SECOND

        title = next((artist["title"] for artist in _MOCK_ARTISTS
                      if artist["id"] == voice_id), "")
        words = max(len(text.split()), 1)
        seconds = round(words / (WORDS_PER_SECOND * max(speed, 0.1)), 2)
        path = out_path.with_suffix(".m4a")
        ff.make_tone_audio(path, seconds, frequency=_MOCK_PITCH.get(title, 150))
        self.generated.append(voice_id)

        return MediaResult(
            path=path,
            mime="audio/mp4",
            credits=0,          # nothing was called; do not invent a charge
            provider=self.name,
            duration_seconds=seconds,
            meta={
                "characters": len(text),
                "voice_id": voice_id,
                "artist": title or "unknown",
                # What the live adapter *would* have charged, so the billing maths can
                # be checked offline without pretending money moved.
                "would_charge_credits": voiceover_credits(len(text)),
                "speed": to_epidemic_speed(speed),
                "mock": True,
            },
        )
