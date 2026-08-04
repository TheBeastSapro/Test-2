"""Epidemic Sound: voice artists for narration, reached over its MCP server.

## What this service actually is

It was wired into this app as a music library on the strength of its name. That was
wrong on two counts, and both were checked against the live server's own tool schemas
rather than inferred:

* Its narration half is **text-to-speech voiced by real voice artists** — `ListVoices`,
  `GenerateVoiceover`, `PollVoiceoverGenerationStatus`, `DownloadVoiceover`. That is the
  half this module implements first, because narration is a pipeline stage that already
  exists and the local Chatterbox route needs torch and a GPU.
* It also carries recordings and sound effects (`SearchRecordings`, `SearchSoundEffects`,
  `DownloadRecording`, `EditRecording`, `DownloadSoundEffect`, …). That half is now built
  too — see "Music and sound effects", which records who authorised it and what the
  authorisation is conditional on.

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

## Music and sound effects

This section used to sit under "What is deliberately absent" and read:

> **Music and sound effects.** Out of scope for narration, and the licence terms matter
> before anyone adds them: the REST docs state that only *connected users with an active
> Epidemic Sound subscription* may download premium-library tracks, that free-tier tracks
> carry a personal (non-commercial) licence, and that exporting a track into published
> content is a reportable event. A bed baked into a monetised render is none of those
> things by default. Establish the entitlement before building the download.

That paragraph is kept rather than deleted because its reasoning still holds and the code
below is shaped by it. What changed is the one fact it was waiting on: **the operator
holds the subscription, and has asked for the sound stage.** The entitlement is therefore
established rather than waived, and the condition the paragraph set is met by the
operator's own account. The decision is theirs; this note records that it was made and
that it was made by the person who pays for the licence.

Two of that paragraph's worries are now properties of the code rather than notes in a
docstring, which is the difference between a caveat and a control:

* **A subscription is not a licence to spend it by accident.** Nothing here is reachable
  unless a channel names a music vendor: `registry.DEFAULT_ROUTING` lists none at all, so
  music is *chosen* and never *fallen back to*. That is the rule `minimax-voice` and
  `higgsfield` are already under, for the same reason — a vendor that draws on something
  the operator pays for must never be inherited by a run that did not ask for it.
* **"An untraceable bed in a monetised render" is the failure to design against.** So
  every fetch here carries the Epidemic id it came from back to its caller, and the sound
  node writes that id into its output. A track that shipped can be named, which is what
  makes the export reportable rather than merely unreported.

## What is deliberately absent

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
    MusicProvider,
    MusicTrack,
    ProviderError,
    ProviderTimeout,
    SoundEffectAsset,
    Stem,
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

# What a downloaded track is licensed by, carried on every music result so the id and the
# terms travel together. A run's output naming a track id but not what allowed it to be
# used is half a record, and the half that is missing is the half a claim asks about.
LICENCE = ("Epidemic Sound subscription licence, held by the operator of this install. "
           "Publishing a render containing this track is a reportable export.")

# `StemType` (what a search reports a track has) and `RecordingDownloadStemType` (what can
# actually be fetched) are two different enums, and only the second can be asked for. A
# track that advertises a MELODY or CLEAN_VOCALS stem will still be refused one, which
# arrives as a rejected call at the end of a search that appeared to have succeeded.
DOWNLOADABLE_STEMS = ("FULL", "BASS", "DRUMS", "INSTRUMENTS")

# Beds arrive as mp3 and one-shots as wav, which is not an inconsistency. A bed is going to
# be trimmed 13 dB under a voice and re-encoded to AAC in the master either way, and a
# wav of an eight-minute bed is ~90 MB of scratch per run — the operator's own method
# records ten leaked runs filling a 252 GB disk. A one-shot is a few hundred kB and is
# placed on a frame, so its transient is the thing being bought and lossy pre-echo is
# exactly what would smear it.
BED_FILE_TYPE = "MP3"
EFFECT_FILE_TYPE = "WAV"


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


# What is lost when the credential is missing, per capability. One sentence each, because
# the operator reads this under a form and "Epidemic Sound is not connected" on its own
# does not say which half of the run just stopped.
_WITHOUT = {
    "voice": ("its voice artists cannot be listed and narration cannot be generated "
              "from them"),
    "music": "no music bed and no sound effect can be fetched for a render",
}


def available(capability: str = "voice") -> tuple[bool, str]:
    """Can Epidemic Sound be reached, and if not, the one thing that would fix it.

    Phrased as plain text with no backticks: this sentence is printed under a form and
    in a tool result, where a backtick reads as a typo rather than as code.
    """
    lost = _WITHOUT.get(capability, _WITHOUT["voice"])
    conn = load_credential()
    if conn is None:
        return False, (
            f"Epidemic Sound is not connected, so {lost}. Connect it under Settings, "
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
        return await download_asset(asset_url, out_path, provider=self.name,
                                    what="voiceover")


async def download_asset(asset_url: str, out_path: Path, *, provider: str,
                         what: str) -> Path:
    """Fetch one signed asset URL to disk, named after what the bytes actually are.

    Shared by narration, beds and one-shots rather than written three times: every one of
    them comes back as a signed CDN URL from a different tool, and the two ways these go
    wrong — an expired signature answering 200 with a stub, and a container that is not
    the extension anyone assumed — are the same in all three cases.

    An HTTP client, never ffmpeg reading the URL directly: ffmpeg re-encodes the percent
    escapes in a signed URL and the signature stops matching, which surfaces as a 403 and
    reads as an authentication problem rather than as the transport bug it is.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with httpx.AsyncClient(
            timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True
        ) as client:
            response = await client.get(asset_url)
    except httpx.TimeoutException as exc:
        raise ProviderTimeout(f"downloading the {what} timed out: {exc}",
                              provider=provider) from exc
    except httpx.HTTPError as exc:
        raise ProviderError(f"could not download the {what}: {exc}",
                            provider=provider, retryable=True) from exc

    if not response.is_success:
        raise ProviderError(
            f"the {what} download URL returned {response.status_code}",
            provider=provider,
            retryable=response.status_code >= 500 or response.status_code == 429,
        )
    body = response.content
    if len(body) < 512:
        # A signed URL that has already expired answers 200 with a stub, and a
        # stub written as narration fails much later inside ffmpeg concat.
        raise ProviderError(
            f"the {what} download returned {len(body)} bytes, which is too small "
            "to be audio — the signed URL may have expired",
            provider=provider, retryable=True,
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


# --------------------------------------------------------------- music and sound effects


def _tags(node: dict) -> tuple[list[str], list[str]]:
    """A recording's tags split into moods and genres, dropping what is neither.

    Each tag carries a `dimension`, and Epidemic's taxonomy has more of them than this
    app has fields for — decade, world country, featured instrument, theme. Anything not
    recognisably a mood or a genre is dropped rather than shovelled into whichever list is
    nearest: a bed labelled with the genre "1980s" is a search that returns nothing and a
    record that says something false about the track.
    """
    moods: list[str] = []
    genres: list[str] = []
    for tag in node.get("tags") or []:
        if not isinstance(tag, dict):
            continue
        name = str(tag.get("displayName") or "").strip()
        dimension = str((tag.get("dimension") or {}).get("name") or "").lower()
        if not name:
            continue
        if "mood" in dimension:
            moods.append(name)
        elif "genre" in dimension:
            genres.append(name)
    return moods, genres


def _music_track(node: dict) -> MusicTrack | None:
    """One search hit as the `MusicTrack` the edit decision consumes.

    `SearchRecordings` answers `RecordingWithSearchMeta`, which wraps the recording in
    a field of its own, so the recording is unwrapped here rather than at every call
    site — and both shapes are accepted, because a bridge that flattens the wrapper is a
    plausible change on the far side that must not silently return zero tracks.
    """
    inner = node.get("recording")
    recording = inner if isinstance(inner, dict) else node
    track_id = str(recording.get("id") or "")
    if not track_id:
        return None

    audio = recording.get("audioFile") or {}
    stems: list[Stem] = []
    for entry in recording.get("stems") or []:
        if not isinstance(entry, dict) or not entry.get("type"):
            continue
        stem_audio = entry.get("audioFile") or {}
        stems.append(Stem(
            kind=str(entry["type"]).upper(),
            duration_seconds=float(stem_audio.get("durationInMilliseconds") or 0) / 1000.0,
            preview_url=str(stem_audio.get("lqmp3Url") or ""),
        ))

    artists: list[str] = []
    for credit in recording.get("credits") or []:
        if not isinstance(credit, dict):
            continue
        name = str((credit.get("artist") or {}).get("name") or "").strip()
        # Composers and producers are credited too, and listing them as the artists of a
        # bed would put the wrong names in a licence record that exists to be checked.
        if name and str(credit.get("role") or "").upper() in {
            "MAIN_ARTIST", "FEATURED_ARTIST"
        } and name not in artists:
            artists.append(name)

    moods, genres = _tags(recording)
    return MusicTrack(
        track_id=track_id,
        title=str(recording.get("title") or ""),
        artists=artists,
        duration_seconds=float(audio.get("durationInMilliseconds") or 0) / 1000.0,
        bpm=int(recording.get("bpm") or 0),
        moods=moods,
        genres=genres,
        stems=stems,
        # Derived from the stem list, because `Recording` publishes no vocals field of its
        # own. It is a proxy and it reads as one: the search filter is what actually keeps
        # singing out of a bed, and this is only the check that the filter was applied.
        has_vocals=any(stem.kind in {"VOCALS", "CLEAN_VOCALS"} for stem in stems),
        preview_url=str(audio.get("lqmp3Url") or ""),
        waveform_url=str(audio.get("waveformUrl") or ""),
        cover_url=str(recording.get("coverArtUrl") or ""),
        provider="epidemic-music",
    )


def _sound_effect(node: dict) -> SoundEffectAsset | None:
    inner = node.get("soundEffect")
    effect = inner if isinstance(inner, dict) else node
    effect_id = str(effect.get("id") or "")
    if not effect_id:
        return None
    audio = effect.get("audioFile") or {}
    return SoundEffectAsset(
        effect_id=effect_id,
        title=str(effect.get("title") or ""),
        duration_seconds=float(audio.get("durationInMilliseconds") or 0) / 1000.0,
        tags=[str(tag.get("displayName") or "") for tag in (effect.get("tags") or [])
              if isinstance(tag, dict) and tag.get("displayName")],
        preview_url=str(audio.get("lqmp3Url") or ""),
        provider="epidemic-music",
    )


def _recordings_query(term: str, topic: str) -> dict:
    """The search half of a recordings request.

    `term`, `topic` and `externalID` are mutually exclusive — the schema says "specify
    exactly one" — so sending a term *and* a topic is a rejected call rather than a
    narrower search. `term` wins when both are given, because an explicit keyword is the
    more specific instruction and a topic is derived from whatever the video is about.
    """
    if term.strip():
        return {"term": term.strip()}
    if topic.strip():
        return {"topic": topic.strip()}
    return {}


def _match_any(values: tuple[str, ...]) -> dict:
    return {"matchType": "ANY", "values": [str(value) for value in values if value]}


@dataclass
class EpidemicMusicProvider(MusicProvider):
    """Beds and one-shots from Epidemic Sound's catalogue.

    Satisfies `MusicProvider`, so the sound node never names this vendor: it asks the
    registry for whatever the channel chose, exactly as the narration node does. That is
    what would let a second music vendor be added without touching a pipeline stage.
    """

    name: str = "epidemic-music"
    # Unused, and kept for the same reason the voice adapter keeps it: the credential is a
    # connector rather than a provider key, so the registry constructs this with nothing.
    api_key: str = ""

    def available(self) -> tuple[bool, str]:
        return available("music")

    def _credential(self) -> tuple[str, str]:
        conn = load_credential()
        if conn is None or not conn.token:
            raise ProviderError(available("music")[1], provider=self.name)
        return conn.url, conn.token

    # -- search -----------------------------------------------------------------

    async def search_tracks(
        self,
        *,
        term: str = "",
        topic: str = "",
        moods: tuple[str, ...] = (),
        genres: tuple[str, ...] = (),
        bpm_min: int = 0,
        bpm_max: int = 0,
        seconds_min: float = 0.0,
        seconds_max: float = 0.0,
        instrumental_only: bool = False,
        limit: int = 10,
    ) -> list[MusicTrack]:
        url, token = self._credential()

        filters: dict = {}
        if bpm_min or bpm_max:
            # A window, never a point. No catalogue holds a track at exactly 127.4 BPM and
            # asking for one is a search that returns nothing — which then reads as "the
            # library has no music" rather than as a filter that was too tight.
            filters["bpm"] = {k: int(v) for k, v in
                              (("min", bpm_min), ("max", bpm_max)) if v}
        if seconds_min or seconds_max:
            # Milliseconds on the wire. Seconds here, because every other duration in this
            # codebase is seconds and one unit that differs is one unit that gets mixed up.
            filters["duration"] = {k: int(v * 1000) for k, v in
                                   (("min", seconds_min), ("max", seconds_max)) if v}
        if moods:
            filters["moodSlugs"] = _match_any(moods)
        if genres:
            filters["taxonomySlugs"] = _match_any(genres)
        if instrumental_only:
            # The filter, not a post-hoc check on the results: a bed that keeps its lead
            # vocal is a second narrator, and no amount of ducking fixes two people
            # talking at once. Filtering after the fact would spend a whole page of
            # results to find that out.
            filters["vocals"] = False

        args: dict = {"first": max(1, min(int(limit), 50))}
        query = _recordings_query(term, topic)
        if query:
            args["query"] = query
        if filters:
            args["filter"] = filters

        async with open_session(url=url, token=token) as remote:
            payload = await remote.call("SearchRecordings", args)

        found = [
            track for track in
            (_music_track(node) for node in (payload.get("nodes") or [])
             if isinstance(node, dict))
            if track is not None
        ]
        log.info("epidemic sound: %d candidate beds for %s", len(found),
                 query or "an unfiltered browse")
        return found[:limit]

    async def search_sound_effects(
        self, *, term: str = "", tags: tuple[str, ...] = (),
        seconds_max: float = 0.0, limit: int = 10,
    ) -> list[SoundEffectAsset]:
        url, token = self._credential()

        args: dict = {"first": max(1, min(int(limit), 50))}
        if term.strip():
            args["query"] = {"term": term.strip()}
        filters: dict = {}
        if tags:
            filters["tagSlugs"] = _match_any(tags)
        if seconds_max:
            filters["duration"] = {"max": int(seconds_max * 1000)}
        if filters:
            args["filter"] = filters

        async with open_session(url=url, token=token) as remote:
            payload = await remote.call("SearchSoundEffects", args)

        found = [
            effect for effect in
            (_sound_effect(node) for node in (payload.get("nodes") or [])
             if isinstance(node, dict))
            if effect is not None
        ]
        log.info("epidemic sound: %d sound effects for %r", len(found), term)
        return found[:limit]

    # -- download ---------------------------------------------------------------

    async def make_bed(
        self,
        track_id: str,
        *,
        out_path: Path,
        seconds: float,
        stem: str = "",
        hit_points: tuple[tuple[float, float, float], ...] = (),
    ) -> MediaResult:
        if not track_id:
            raise ProviderError("no track to fetch a bed from", provider=self.name)
        seconds = max(1.0, float(seconds))
        url, token = self._credential()

        async with open_session(url=url, token=token) as remote:
            if stem:
                asset_url, meta = await self._stem_asset(remote, track_id, stem)
            else:
                asset_url, meta = await self._edit_asset(
                    remote, track_id, seconds, hit_points
                )

        if not asset_url:
            raise ProviderError(
                f"epidemic sound produced no download URL for track {track_id}",
                provider=self.name, retryable=True,
            )
        path = await download_asset(asset_url, out_path, provider=self.name,
                                    what="music bed")

        from ..render import ffmpeg as ff

        duration = await asyncio.to_thread(ff.ffprobe_duration, path)
        return MediaResult(
            path=path,
            mime=_MIMES.get(path.suffix, "audio/mpeg"),
            # Nothing per track to charge. Every other adapter here converts a published
            # vendor unit price, and `voiceover_credits` derives narration's from the
            # node's own per-thousand-character figure so the estimate and the settled
            # actual cannot drift apart. Music has neither: it comes out of a flat
            # subscription the operator already pays, and `credits.PER_UNIT_COSTS` has no
            # music entry to derive from. Inventing a number would put a fabricated cost
            # in /analytics, which is the failure `voiceover_credits` exists to avoid —
            # here the honest answer happens to be zero rather than a derivation.
            credits=0,
            provider=self.name,
            duration_seconds=duration,
            meta={"track_id": track_id, "licence": LICENCE,
                  "asked_seconds": round(seconds, 2), **meta},
        )

    async def fetch_sound_effect(self, effect_id: str, *, out_path: Path) -> MediaResult:
        if not effect_id:
            raise ProviderError("no sound effect to fetch", provider=self.name)
        url, token = self._credential()

        async with open_session(url=url, token=token) as remote:
            download = await remote.call(
                "DownloadSoundEffect",
                {"id": effect_id, "options": {"fileType": EFFECT_FILE_TYPE}},
            )
        asset_url = str(download.get("assetUrl") or "")
        if not asset_url:
            raise ProviderError(
                f"epidemic sound produced no download URL for effect {effect_id}",
                provider=self.name, retryable=True,
            )
        path = await download_asset(asset_url, out_path, provider=self.name,
                                    what="sound effect")

        from ..render import ffmpeg as ff

        duration = await asyncio.to_thread(ff.ffprobe_duration, path)
        return MediaResult(
            path=path, mime=_MIMES.get(path.suffix, "audio/wav"), credits=0,
            provider=self.name, duration_seconds=duration,
            meta={"effect_id": effect_id, "licence": LICENCE},
        )

    # -- the two routes to a bed ------------------------------------------------

    async def _stem_asset(self, remote: EpidemicSession, track_id: str,
                          stem: str) -> tuple[str, dict]:
        """One isolated layer of the whole track.

        A stem and a length-matched edit cannot be had together: `DownloadRecordingEdit`
        takes only a job and an edit id, with nowhere to name a layer, so an edit is
        always a full mix. Dropping the vocal is worth more than a musical ending under
        narration, so when a stem is asked for this route wins and the length is resolved
        locally by `render.audio.loop_to_length`.
        """
        wanted = stem.upper()
        if wanted not in DOWNLOADABLE_STEMS:
            # MELODY and the vocal stems appear in search results and cannot be fetched.
            # Falling back to the full mix and saying so beats a rejected call, but it is
            # a real downgrade — the bed keeps whatever the stem would have removed.
            log.warning("epidemic sound cannot download the %s stem; taking the full mix",
                        wanted)
            wanted = "FULL"
        download = await remote.call(
            "DownloadRecording",
            {"id": track_id,
             "options": {"fileType": BED_FILE_TYPE, "stemType": wanted}},
        )
        return str(download.get("assetUrl") or ""), {"stem": wanted, "route": "stem"}

    async def _edit_asset(
        self, remote: EpidemicSession, track_id: str, seconds: float,
        hit_points: tuple[tuple[float, float, float], ...],
    ) -> tuple[str, dict]:
        """A version of the track cut to length, musically.

        `targetDurationMs` is capped at 300000 by the vendor: five minutes, which this
        app's default eight-minute target reaches by the *normal* case rather than an edge
        one. Over the cap the request becomes `loopable` — the schema's word for "seamless
        when repeated" — and `render.audio.loop_to_length` repeats it. Stitching several
        independent edits was the alternative and it is worse: each one is cut to resolve
        on its own ending, so every join lands on two resolutions back to back.

        Under the cap nothing loops. `forceDuration` cuts it exactly, which is the whole
        point of the operation: a bed that ends when the video ends, musically, instead of
        being faded out mid-phrase.
        """
        wanted_ms = int(seconds * 1000)
        capped = wanted_ms > EDIT_MAX_DURATION_MS
        target_ms = min(wanted_ms, EDIT_MAX_DURATION_MS)

        edit: dict = {
            "targetDurationMs": target_ms,
            "downloadAudioFormat": BED_FILE_TYPE,
            "forceDuration": not capped,
            "loopable": capped,
            # Nothing downloads an edit's stems — there is no field to ask for one — so
            # generating them is time spent on a file that cannot be fetched.
            "skipStems": True,
            "maxResults": 1,
        }
        if hit_points:
            edit["requiredRegionsAtOffsets"] = [
                {"startMs": int(start * 1000), "endMs": int(end * 1000),
                 "offsetMsInEdit": int(offset * 1000)}
                for start, end, offset in hit_points
            ]

        started = await remote.call("EditRecording", {"id": track_id, "input": edit})
        job_id = str(started.get("id") or "")
        if not job_id:
            raise ProviderError(
                f"epidemic sound accepted the edit of {track_id} but returned no job id, "
                "so there is nothing to poll for",
                provider=self.name, retryable=True,
            )

        state = await self._await_edit(remote, job_id, started)
        edit_id = _first_edit_id(state)
        if not edit_id:
            raise ProviderError(
                f"edit job {job_id} completed without naming an edit to download",
                provider=self.name, retryable=True,
            )

        download = await remote.call(
            "DownloadRecordingEdit", {"input": {"jobId": job_id, "editId": edit_id}}
        )
        return str(download.get("assetUrl") or ""), {
            "route": "edit", "job_id": job_id, "edit_id": edit_id,
            "loopable": capped, "edit_seconds": round(target_ms / 1000.0, 2),
            "polls": state.get("polls", 0),
        }

    async def _await_edit(self, remote: EpidemicSession, job_id: str,
                          started: dict) -> dict:
        """Poll an edit job until it completes, and stop rather than wait forever.

        Its own ceiling rather than narration's: re-cutting audio is the heavier of the
        two jobs, and a timeout sized for a sentence of speech would abandon an edit that
        was going to arrive.
        """
        state = str(started.get("status") or "").upper()
        polls = 0
        deadline = time.monotonic() + EDIT_POLL_TIMEOUT_SECONDS

        while state != "COMPLETED":
            if state == "FAILED":
                raise ProviderError(
                    f"epidemic sound could not cut edit job {job_id} to length",
                    provider=self.name,
                )
            if time.monotonic() >= deadline:
                raise ProviderTimeout(
                    f"edit job {job_id} was still running after "
                    f"{EDIT_POLL_TIMEOUT_SECONDS:.0f}s and polling stopped. Nothing was "
                    "downloaded, so nothing was exported against the licence.",
                    provider=self.name,
                )
            await asyncio.sleep(EDIT_POLL_INTERVAL_SECONDS)
            polls += 1
            started = await remote.call("PollEditRecordingJob", {"id": job_id})
            state = str(started.get("status") or "").upper()

        return {**started, "polls": polls}


def _first_edit_id(state: dict) -> str:
    """The edit to download out of a completed job.

    Both shapes are read because the schema is mid-migration: `edit` is documented as
    deprecated in favour of `edits`, and a server that has finished that migration would
    otherwise complete a job this code then called empty.
    """
    for entry in state.get("edits") or []:
        if isinstance(entry, dict) and entry.get("id"):
            return str(entry["id"])
    single = state.get("edit")
    if isinstance(single, dict) and single.get("id"):
        return str(single["id"])
    return ""


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


# Deterministic beds, shaped like `SearchRecordings` answers rather than like anything
# this app invented. One of the three carries a vocal stem on purpose: the single most
# consequential decision the sound stage makes is refusing a bed that sings over the
# narration, and a roster where every candidate is instrumental cannot demonstrate it.
_MOCK_RECORDINGS: tuple[dict, ...] = (
    {"id": "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa", "title": "Cold Open",
     "bpm": 96, "seconds": 184.0, "moods": ["Serious", "Hopeful"],
     "genres": ["Ambient"], "stems": ["DRUMS", "BASS", "INSTRUMENTS"]},
    {"id": "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb", "title": "Long Division",
     "bpm": 128, "seconds": 212.0, "moods": ["Driving"], "genres": ["Electronica"],
     "stems": ["DRUMS", "BASS", "MELODY", "INSTRUMENTS"]},
    {"id": "cccccccc-3333-4333-8333-cccccccccccc", "title": "Say It Again",
     "bpm": 124, "seconds": 168.0, "moods": ["Driving"], "genres": ["Pop"],
     "stems": ["DRUMS", "BASS", "INSTRUMENTS", "CLEAN_VOCALS", "VOCALS"]},
)

# Enough distinct one-shots that the repetition rules have something to act on. The
# operator's method is explicit that "sounds cheap" means one file played 240 times, so a
# mock palette of one file would make the cooldown untestable offline — which is to say
# untested, since offline is how the suite and every fresh install run.
_MOCK_EFFECTS: tuple[dict, ...] = (
    {"id": "dddddddd-0001-4001-8001-dddddddddddd", "title": "Whoosh Short 01",
     "seconds": 0.9, "tags": ["whoosh", "transition"]},
    {"id": "dddddddd-0002-4002-8002-dddddddddddd", "title": "Whoosh Short 02",
     "seconds": 1.1, "tags": ["whoosh", "transition"]},
    {"id": "dddddddd-0003-4003-8003-dddddddddddd", "title": "Whoosh Long 01",
     "seconds": 1.6, "tags": ["whoosh", "transition"]},
    {"id": "eeeeeeee-0001-4001-8001-eeeeeeeeeeee", "title": "Sub Impact 01",
     "seconds": 2.4, "tags": ["impact", "boom"]},
    {"id": "eeeeeeee-0002-4002-8002-eeeeeeeeeeee", "title": "Sub Impact 02",
     "seconds": 2.1, "tags": ["impact", "boom"]},
    {"id": "ffffffff-0001-4001-8001-ffffffffffff", "title": "Riser 01",
     "seconds": 2.8, "tags": ["riser", "build"]},
    {"id": "ffffffff-0002-4002-8002-ffffffffffff", "title": "Riser 02",
     "seconds": 3.2, "tags": ["riser", "build"]},
)


def _mock_recording(entry: dict) -> dict:
    """One offline track in the vendor's own record shape, not in `MusicTrack`'s.

    Deliberately built as the payload `_music_track` parses rather than as the dataclass
    it returns: the mapping is where a schema change would break, so a mock that skipped
    it would leave the one fragile piece of this adapter unexercised offline.
    """
    return {
        "recording": {
            "id": entry["id"],
            "title": entry["title"],
            "bpm": entry["bpm"],
            "coverArtUrl": "",
            "audioFile": {
                "durationInMilliseconds": int(entry["seconds"] * 1000),
                "lqmp3Url": "", "waveformUrl": "",
            },
            "stems": [
                {"type": kind, "audioFile": {
                    "durationInMilliseconds": int(entry["seconds"] * 1000),
                    "lqmp3Url": "", "waveformUrl": ""}}
                for kind in entry["stems"]
            ],
            "tags": (
                [{"displayName": mood, "dimension": {"name": "mood"}}
                 for mood in entry["moods"]]
                + [{"displayName": genre, "dimension": {"name": "genre"}}
                   for genre in entry["genres"]]
            ),
            "credits": [
                {"role": "MAIN_ARTIST",
                 "artist": {"name": "Offline Stand-in", "slug": "offline-stand-in"}},
                {"role": "COMPOSER",
                 "artist": {"name": "Not The Artist", "slug": "not-the-artist"}},
            ],
        }
    }


@dataclass
class MockEpidemicMusic(MusicProvider):
    """Epidemic Sound's music shapes without Epidemic Sound.

    The filters are applied here rather than ignored, because what the sound stage does
    with a search result — refuse the vocal track, prefer the tempo the reference measured
    — is only demonstrable against a roster that answers a filter differently from an
    unfiltered one.
    """

    name: str = "mock-epidemic-music"
    api_key: str = ""
    fetched: list[str] = field(default_factory=list)

    def available(self) -> tuple[bool, str]:
        return True, ""

    async def search_tracks(
        self, *, term: str = "", topic: str = "", moods: tuple[str, ...] = (),
        genres: tuple[str, ...] = (), bpm_min: int = 0, bpm_max: int = 0,
        seconds_min: float = 0.0, seconds_max: float = 0.0,
        instrumental_only: bool = False, limit: int = 10,
    ) -> list[MusicTrack]:
        found: list[MusicTrack] = []
        for entry in _MOCK_RECORDINGS:
            if bpm_min and entry["bpm"] < bpm_min:
                continue
            if bpm_max and entry["bpm"] > bpm_max:
                continue
            if seconds_min and entry["seconds"] < seconds_min:
                continue
            if seconds_max and entry["seconds"] > seconds_max:
                continue
            if instrumental_only and {"VOCALS", "CLEAN_VOCALS"} & set(entry["stems"]):
                continue
            track = _music_track(_mock_recording(entry))
            if track is not None:
                found.append(track)
        return found[:limit]

    async def search_sound_effects(
        self, *, term: str = "", tags: tuple[str, ...] = (),
        seconds_max: float = 0.0, limit: int = 10,
    ) -> list[SoundEffectAsset]:
        # Matched word by word, because the live search is a relevance query and callers
        # phrase one as "whoosh transition". Comparing the whole phrase to a tag matched
        # nothing, which offline looked exactly like a catalogue with no whooshes in it.
        wanted = {tag.lower() for tag in tags} | set(term.lower().split())
        found: list[SoundEffectAsset] = []
        for entry in _MOCK_EFFECTS:
            if seconds_max and entry["seconds"] > seconds_max:
                continue
            if wanted and not wanted & set(entry["tags"]):
                continue
            effect = _sound_effect({"soundEffect": {
                "id": entry["id"], "title": entry["title"],
                "audioFile": {"durationInMilliseconds": int(entry["seconds"] * 1000),
                              "lqmp3Url": "", "waveformUrl": ""},
                "tags": [{"displayName": tag, "slug": tag} for tag in entry["tags"]],
            }})
            if effect is not None:
                found.append(effect)
        return found[:limit]

    async def make_bed(
        self, track_id: str, *, out_path: Path, seconds: float, stem: str = "",
        hit_points: tuple[tuple[float, float, float], ...] = (),
    ) -> MediaResult:
        from ..render import ffmpeg as ff

        entry = next((item for item in _MOCK_RECORDINGS if item["id"] == track_id), None)
        if entry is None:
            raise ProviderError(f"no offline track {track_id}", provider=self.name)

        # A real file at the asked-for length, not a stub: the stage's whole job is to
        # measure this and duck a voice against it, and neither is possible against a
        # zero-byte placeholder. Pitched from the tempo so two mock beds differ audibly.
        seconds = max(1.0, float(seconds))
        path = ff.make_tone_audio(out_path.with_suffix(".m4a"), seconds,
                                  frequency=int(entry["bpm"]))
        self.fetched.append(track_id)
        return MediaResult(
            path=path, mime="audio/mp4", credits=0, provider=self.name,
            duration_seconds=seconds,
            meta={"track_id": track_id, "licence": LICENCE, "mock": True,
                  "stem": stem.upper() if stem else "",
                  "asked_seconds": round(seconds, 2),
                  "hit_points": len(hit_points)},
        )

    async def fetch_sound_effect(self, effect_id: str, *, out_path: Path) -> MediaResult:
        from ..render import ffmpeg as ff

        entry = next((item for item in _MOCK_EFFECTS if item["id"] == effect_id), None)
        if entry is None:
            raise ProviderError(f"no offline sound effect {effect_id}",
                                provider=self.name)
        path = ff.make_tone_audio(out_path.with_suffix(".m4a"), entry["seconds"],
                                  frequency=440)
        self.fetched.append(effect_id)
        return MediaResult(
            path=path, mime="audio/mp4", credits=0, provider=self.name,
            duration_seconds=entry["seconds"],
            meta={"effect_id": effect_id, "licence": LICENCE, "mock": True},
        )
