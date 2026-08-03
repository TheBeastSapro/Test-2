"""Epidemic Sound as a narration vendor.

The service was wired in as a music library on the strength of its name. It is a
text-to-speech service voiced by real voice artists, reached over an MCP server that
speaks GraphQL — so these tests pin the three things that mis-description would have
got wrong, and that a future refactor could quietly undo:

  1. the credential is a *connector*, readable whichever `kind` the catalogue calls it
  2. narration ranks in the *existing* casting flow, on pitch measured from each
     artist's own preview clip
  3. the async generate/poll/download cycle stops rather than waiting forever

Nothing here touches the network or needs a credential: the whole suite runs in
`FORGECAST_PROVIDER_MODE=mock`, which is also every fresh install's first run.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import httpx
import pytest

from forgecast import credits as billing
from forgecast.agent import connectors, tools
from forgecast.agent.studio import Studio, epidemic_cache_path
from forgecast.config import get_settings
from forgecast.providers import base, epidemic, registry
from forgecast.providers.base import Capability, ProviderError, ProviderTimeout


@pytest.fixture(autouse=True)
def nothing_connected():
    """Every test starts with Epidemic Sound not connected.

    The connector store is a *file* beside the database, and `conftest` only recreates
    the schema between tests — so a connector written by one test was still there for the
    next one. That is not a cosmetic leak: it made "no credential" tests pass for the
    wrong reason and then, once ordering changed, made them attempt a real call to
    epidemicsound.com.
    """
    path = connectors.default_path()
    path.unlink(missing_ok=True)
    yield
    path.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def no_real_mcp_session(monkeypatch):
    """Nothing in this file is allowed to actually reach epidemicsound.com.

    The same reasoning as `conftest.no_real_yt_dlp`: on a machine with network access a
    forgotten patch is a real request — slow, authenticated against nothing, and
    answering differently next week. Tests that want a session substitute their own,
    which overrides this.
    """
    @contextlib.asynccontextmanager
    async def refuse(**kwargs):                                    # pragma: no cover
        raise AssertionError(
            "a test tried to open a real MCP session with Epidemic Sound. "
            "Patch forgecast.providers.epidemic.open_session instead."
        )
        yield  # unreachable; keeps this a valid async generator

    monkeypatch.setattr(epidemic, "open_session", refuse)


# --------------------------------------------------------------------- credential


def _write_connector(*, token: str = "epidemic_live_test", url: str = "",
                     enabled: bool = True) -> Path:
    path = connectors.default_path()
    store = connectors.Store(path=path)
    store.set(epidemic.CONNECTOR_KEY, url, token, enabled)
    return path


def test_absence_is_one_actionable_sentence():
    """No credential must say what to do, not merely that something is missing.

    The failure this guards is the one `research.keyless.available` was written for: a
    capability that reports itself broken teaches the operator the app is broken, while
    one that names the fix gets fixed.
    """
    usable, reason = epidemic.available()
    assert usable is False
    assert "Epidemic Sound" in reason
    assert "Connectors" in reason
    # Printed as plain text under a form, where a backtick reads as a typo.
    assert "`" not in reason


def test_credential_survives_the_kind_being_corrected(monkeypatch):
    """`api` today, `mcp` tomorrow — the provider must read it either way.

    `Store.api_credentials` filters on `spec.kind == "api"`. The catalogue entry is being
    corrected to `kind="mcp"` because the service really is an MCP server, and a provider
    that read the credential through only that one accessor would lose its vendor to a
    one-word change, with no error explaining why narration stopped having a provider.
    """
    _write_connector(token="epidemic_live_abc")

    assert epidemic.load_credential() is not None      # kind="api", as shipped today

    corrected = connectors.ConnectorSpec(
        key=epidemic.CONNECTOR_KEY, label="Epidemic Sound", gives="", where="",
        kind="mcp",
    )
    monkeypatch.setitem(connectors.BY_KEY, epidemic.CONNECTOR_KEY, corrected)

    conn = epidemic.load_credential()
    assert conn is not None and conn.token == "epidemic_live_abc"
    assert epidemic.available() == (True, "")


def test_a_disabled_connector_is_not_a_credential():
    _write_connector(token="epidemic_live_abc", enabled=False)
    assert epidemic.load_credential() is None
    assert epidemic.available()[0] is False


def test_connected_without_a_key_says_so_specifically():
    """Connected-but-keyless is a different fix from not-connected."""
    _write_connector(token="", url="https://example.invalid/mcp")
    usable, reason = epidemic.available()
    assert usable is False
    assert "no API key stored" in reason


# ------------------------------------------------------------------ unit conversions


def test_the_default_speed_is_not_maximum_speed():
    """The two scales collide at exactly the wrong value.

    `VoiceProvider.synthesize` takes a multiplier where 1.0 is normal. Epidemic takes an
    offset where 0.0 is normal and 1.0 is as fast as it will read. Passing the multiplier
    straight through would have requested maximum speed for every default narration.
    """
    assert epidemic.to_epidemic_speed(1.0) == 0.0
    assert epidemic.to_epidemic_speed(1.5) == pytest.approx(0.5)
    assert epidemic.to_epidemic_speed(0.5) == pytest.approx(-0.5)
    # Clamped, because the contract's multiplier has no upper bound and theirs does.
    assert epidemic.to_epidemic_speed(9.0) == 1.0
    assert epidemic.to_epidemic_speed(0.0) == -1.0


def test_narration_is_priced_on_the_same_scale_the_node_reserves():
    """Estimate and actual must agree, or /analytics under-reports every run.

    Epidemic publishes no per-character price, so there is no vendor figure to mark up.
    Deriving from the node's own per-unit cost is what keeps the settled actual equal to
    the released estimate instead of reporting narration as free.
    """
    base_cost = billing.BASE_COSTS["voice"]
    for characters in (1, 250, 1000, 1001, 4200):
        estimate = billing.estimate_node("voice", characters).credits
        assert epidemic.voiceover_credits(characters) == estimate - base_cost

    # Never zero: a call that happened is a cost, however short the line.
    assert epidemic.voiceover_credits(1) > 0


@pytest.mark.parametrize(
    ("body", "suffix"),
    [
        (b"ID3\x04\x00\x00", ".mp3"),
        (b"RIFF\x00\x00\x00\x00WAVE", ".wav"),
        (b"OggS\x00\x02", ".ogg"),
        (b"fLaC\x00\x00", ".flac"),
        (b"\x00\x00\x00\x20ftypM4A ", ".m4a"),
        (b"\xff\xfb\x90\x00", ".mp3"),
    ],
)
def test_the_file_is_named_after_what_it_contains(body, suffix):
    """`DownloadVoiceover` returns a signed URL and never states a format.

    Writing every download as `.mp3` produced files whose extension contradicted their
    contents, and the narration node joins these per-scene files with ffmpeg.
    """
    assert epidemic._suffix_for(body) == suffix


# ------------------------------------------------------------- casting integration


def test_a_voice_artist_becomes_a_castable_voice():
    """The mapping is the whole integration: no second voice-selection path.

    `voice.discover.parse_voice` already turns a vendor record into the `MeasuredVoice`
    that `voice.casting` scores. Emitting that shape is what keeps one ranking instead of
    two that disagree about the same voice.
    """
    from forgecast.voice.discover import parse_voice

    record = epidemic._voice_record({
        "id": "abc-123",
        "title": "Ingrid Solberg",
        "exampleAudioUrl": "https://example.invalid/preview.mp3",
        "languageCode": "en",
        "languages": ["en", "sv"],
        "metadata": {"gender": "female", "location": "Stockholm, Sweden",
                     "biography": "Voice artist.",
                     "characteristics": "calm, warm, documentary"},
    })

    voice = parse_voice(record)
    assert voice.voice_id == "abc-123"
    assert voice.name == "Ingrid Solberg"
    assert voice.preview_url.endswith("preview.mp3")   # so pitch can be measured
    # `location` is the closest thing Epidemic publishes to an accent.
    assert voice.accent == "Stockholm, Sweden"
    # The vendor's own words drive the energy mapping — nothing is invented.
    assert voice.energy == "calm"
    # Left empty on purpose: Epidemic publishes no use case, and casting only scores a
    # real vendor label. A guess here manufactures a reason nobody can check.
    assert voice.use_case == ""
    # These are licensed artists, so casting's ownership ranking treats them as such.
    assert voice.ownership == "professional"
    # The vendor tag, so a merged shortlist can say which service a candidate is on.
    assert voice.provenance == "epidemic"


def test_languages_are_carried_even_though_the_cache_drops_them():
    """`languages` is the honest basis for dubbing, and nothing consumes it yet.

    `MeasuredVoice` has no field for it, so a synced catalogue loses it. The record keeps
    it so the studio tool can report it — which is what makes the gap visible rather than
    quietly absent.
    """
    record = epidemic._voice_record({
        "id": "x", "title": "T", "languageCode": "de",
        "languages": ["de", "en", "fr"], "metadata": {},
    })
    assert record["languages"] == ["de", "en", "fr"]


@pytest.mark.asyncio
async def test_the_offline_roster_measures_for_real():
    """Mock mode must exercise the property that matters, not stub it out.

    Casting's central claim is that pitch is *measured* from each voice's own preview. A
    mock whose preview URL pointed nowhere left that untested and reported every offline
    artist as `preview_download_failed`, so the one thing worth demonstrating was the one
    thing a fresh install could not show.
    """
    from forgecast.voice.discover import measure_preview, parse_voice

    provider = epidemic.MockEpidemicVoice()
    records = await provider.list_voices()
    assert len(records) >= 3

    measured = [measure_preview(parse_voice(record)) for record in records]
    assert all(voice.measurement == "measured" for voice in measured), [
        voice.measurement for voice in measured
    ]
    # Three artists, three different pitches — not one band for everything.
    assert len({voice.pitch_band for voice in measured}) > 1


# ----------------------------------------------------------------- the poll ceiling


class _Remote:
    """Stands in for a live MCP session. Records what was asked of it."""

    def __init__(self, replies: dict[str, list[dict]]) -> None:
        self.replies = {name: list(items) for name, items in replies.items()}
        self.calls: list[tuple[str, dict]] = []

    async def call(self, tool: str, arguments: dict) -> dict:
        self.calls.append((tool, arguments))
        queue = self.replies.get(tool) or []
        return queue.pop(0) if len(queue) > 1 else (queue[0] if queue else {})


@pytest.mark.asyncio
async def test_a_failed_generation_reports_the_vendors_own_reason():
    """`failedReason` verbatim, because it is the only thing that says what to change."""
    provider = epidemic.EpidemicVoiceProvider()
    remote = _Remote({})
    started = {"id": "vo-1", "status": "FAILED",
               "failedReason": "text contains an unsupported language"}

    with pytest.raises(ProviderError) as caught:
        await provider._await_done(remote, "vo-1", started)
    assert "unsupported language" in str(caught.value)


@pytest.mark.asyncio
async def test_polling_stops_instead_of_hanging_the_run(monkeypatch):
    """An unbounded poll loop is how a run sits on a spinner for the rest of the day."""
    monkeypatch.setattr(epidemic, "POLL_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(epidemic, "POLL_TIMEOUT_SECONDS", 0.05)

    provider = epidemic.EpidemicVoiceProvider()
    remote = _Remote({"PollVoiceoverGenerationStatus": [{"id": "vo-2",
                                                        "status": "GENERATING"}]})

    with pytest.raises(ProviderTimeout) as caught:
        await provider._await_done(remote, "vo-2", {"id": "vo-2", "status": "GENERATING"})
    message = str(caught.value)
    assert "vo-2" in message
    # Says what is true of the money as well as of the wait.
    assert "nothing was charged" in message


@pytest.mark.asyncio
async def test_polling_returns_once_the_job_is_done(monkeypatch):
    monkeypatch.setattr(epidemic, "POLL_INTERVAL_SECONDS", 0.0)
    provider = epidemic.EpidemicVoiceProvider()
    remote = _Remote({"PollVoiceoverGenerationStatus": [
        {"id": "vo-3", "status": "GENERATING"},
        {"id": "vo-3", "status": "DONE"},
    ]})

    state = await provider._await_done(remote, "vo-3", {"id": "vo-3",
                                                       "status": "GENERATING"})
    assert state["status"] == "DONE"
    assert state["polls"] >= 1


@pytest.mark.asyncio
async def test_synthesis_generates_polls_downloads_and_prices_itself(monkeypatch, tmp_path):
    """The whole cycle, with the network replaced and nothing else."""
    _write_connector(token="epidemic_live_abc")
    monkeypatch.setattr(epidemic, "POLL_INTERVAL_SECONDS", 0.0)

    remote = _Remote({
        "GenerateVoiceover": [{"id": "vo-9", "status": "GENERATING"}],
        "PollVoiceoverGenerationStatus": [{"id": "vo-9", "status": "DONE"}],
        "DownloadVoiceover": [{"assetUrl": "https://example.invalid/signed.mp3"}],
    })

    @contextlib.asynccontextmanager
    async def fake_session(**_kwargs):
        yield remote

    monkeypatch.setattr(epidemic, "open_session", fake_session)

    async def fake_fetch(self, asset_url, out_path):
        from forgecast.render import ffmpeg as ff

        assert asset_url.endswith("signed.mp3")
        return ff.make_tone_audio(Path(out_path).with_suffix(".m4a"), 1.0)

    monkeypatch.setattr(epidemic.EpidemicVoiceProvider, "_fetch", fake_fetch)

    provider = epidemic.EpidemicVoiceProvider()
    text = "Here is the part everyone leaves out."
    result = await provider.synthesize(
        text, voice_id="voice-uuid", out_path=tmp_path / "scene_000", speed=1.0
    )

    assert result.path.exists()
    assert result.duration_seconds > 0
    assert result.credits == epidemic.voiceover_credits(len(text))
    assert result.meta["voiceover_id"] == "vo-9"
    # The default multiplier must reach the vendor as its own default, not its maximum.
    generate = next(args for name, args in remote.calls if name == "GenerateVoiceover")
    assert generate["input"]["speed"] == 0.0
    assert generate["input"]["voiceId"] == "voice-uuid"
    # No language was configured, so none is asserted — the voice reads in its own.
    assert "languageCode" not in generate["input"]


@pytest.mark.asyncio
async def test_synthesis_without_a_credential_names_the_fix(tmp_path):
    provider = epidemic.EpidemicVoiceProvider()
    with pytest.raises(ProviderError) as caught:
        await provider.synthesize("hello there friend", voice_id="v",
                                  out_path=tmp_path / "x")
    assert "Connectors" in str(caught.value)


def test_graphql_envelopes_are_peeled_but_real_results_are_not():
    """A bridge over GraphQL may nest the answer under `data` and the field name.

    The bound is what makes this safe: peeling only single-key dicts whose value is a
    dict leaves both documented answer shapes alone.
    """
    assert epidemic._unwrap(
        {"data": {"voiceoverGenerate": {"id": "a", "status": "DONE"}}}
    ) == {"id": "a", "status": "DONE"}

    # `ListVoices` — two keys, nothing to peel.
    listing = {"nodes": [], "pageInfo": {"hasMoreItems": False}}
    assert epidemic._unwrap(listing) == listing

    # `DownloadVoiceover` — one key, but its value is a string.
    download = {"assetUrl": "https://example.invalid/a.mp3"}
    assert epidemic._unwrap(download) == download


# ------------------------------------------------------------------ error reporting


def _status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.invalid/mcp")
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


def test_a_rejected_key_survives_the_task_group_wrapper():
    """The most likely failure on this integration must not be reported as a shrug.

    The MCP client runs its transport in an anyio task group, so a 401 arrives as
    "unhandled errors in a TaskGroup (1 sub-exception)" wrapping the real error. Catching
    `httpx.HTTPStatusError` directly reads as correct and can never fire.
    """
    wrapped = BaseExceptionGroup("unhandled errors in a TaskGroup",
                                 [_status_error(401)])
    translated = epidemic._translate(wrapped, "https://example.invalid/mcp")

    assert isinstance(translated, ProviderError)
    assert "401" in str(translated)
    # Names both causes, because a bad key and a wrong endpoint fail identically.
    assert "API key" in str(translated)
    assert "example.invalid" in str(translated)


def test_a_server_error_is_marked_retryable():
    translated = epidemic._translate(
        BaseExceptionGroup("g", [_status_error(503)]), "https://example.invalid/mcp"
    )
    assert translated.retryable is True


def test_a_timeout_inside_the_group_is_still_a_timeout():
    translated = epidemic._translate(
        BaseExceptionGroup("g", [httpx.ConnectTimeout("slow")]),
        "https://example.invalid/mcp",
    )
    assert isinstance(translated, ProviderTimeout)
    assert translated.retryable is True


def test_an_unrecognised_failure_names_the_inner_error_not_the_wrapper():
    """"1 sub-exception" tells the operator how many problems there were, not what."""
    translated = epidemic._translate(
        BaseExceptionGroup("unhandled errors in a TaskGroup",
                           [RuntimeError("the server closed the stream")]),
        "https://example.invalid/mcp",
    )
    assert "the server closed the stream" in str(translated)
    assert "sub-exception" not in str(translated)


# -------------------------------------------------------------------- the registry


def test_mock_mode_can_be_pointed_at_this_vendors_shapes():
    """The generic voice mock answers in ElevenLabs' shape.

    So the fields this adapter maps — `location`, `characteristics`, `languages` — were
    unreachable offline, which is to say untested and undemonstrable on a fresh install.
    """
    generic = registry.ProviderRegistry(mode="mock").voice()
    assert isinstance(generic, base.VoiceProvider)
    assert not isinstance(generic, epidemic.MockEpidemicVoice)

    pointed = registry.ProviderRegistry(
        mode="mock", overrides={"voice": "epidemic-sound"}
    ).voice()
    assert isinstance(pointed, epidemic.MockEpidemicVoice)


def test_an_unusable_provider_is_skipped_not_returned():
    """`available()` returns `(False, why)`, and a non-empty tuple is truthy.

    Read with a plain truth test, an unconnected Epidemic Sound was handed back as the
    voice provider and the run failed later at the vendor call — an error about a missing
    credential in place of a fallback that was sitting right there.
    """
    live = registry.ProviderRegistry(mode="live")
    with pytest.raises(ProviderError) as caught:
        live.resolve(Capability.voice)

    message = str(caught.value)
    assert "epidemic-sound" in message
    # The reason travels with the refusal, so the two ways of having no voice vendor do
    # not produce the same sentence.
    assert "Connectors" in message


def test_a_configured_connector_makes_the_vendor_resolvable():
    _write_connector(token="epidemic_live_abc")
    provider = registry.ProviderRegistry(mode="live").resolve(Capability.voice)
    assert isinstance(provider, epidemic.EpidemicVoiceProvider)


def test_availability_reads_both_shapes():
    """A bool from the CLI provider, a tuple from the connector-backed ones."""
    class Bare:
        pass

    class Boolean:
        def available(self):
            return False

    class Tuple:
        def available(self):
            return False, "not connected"

    assert registry._availability(Bare()) == (True, "")
    assert registry._availability(Boolean())[0] is False
    assert registry._availability(Tuple()) == (False, "not connected")


def test_a_stored_elevenlabs_key_still_wins():
    """Epidemic Sound is a fallback, not a promotion.

    A stored provider key means the operator chose that vendor; Epidemic sits behind it
    so an install with no key narrates instead of failing at the voice node.
    """
    _write_connector(token="epidemic_live_abc")
    chosen = registry.ProviderRegistry(
        mode="live", user_keys={"elevenlabs": "sk-test"}
    ).resolve(Capability.voice)
    assert chosen.name == "elevenlabs"


# ------------------------------------------------------------------- studio + tools


@pytest.mark.asyncio
async def test_voice_artists_reports_languages_and_labels_them_as_claims(user):
    listed = await Studio(user_id=user.id).voice_artists(limit=3)
    assert listed["count"] == 3
    first = listed["artists"][0]
    assert first["voice_id"] and first["name"]
    assert first["languages"]                      # the thing the cache cannot hold
    assert first["has_preview"] is True
    # The vendor's words are labelled as the vendor's words, never as measurements.
    assert "not measurements" in listed["caveat"]


@pytest.mark.asyncio
async def test_voice_artists_without_a_credential_is_an_error_not_an_empty_list(
    user, monkeypatch
):
    """An empty list reads as "you have no voices". That is a different, wrong fact."""
    monkeypatch.setattr(get_settings(), "provider_mode", "live", raising=False)
    result = await Studio(user_id=user.id).voice_artists()
    assert "Connectors" in result["error"]
    assert "artists" not in result


@pytest.mark.asyncio
async def test_sync_puts_the_artists_into_the_existing_casting_pool(user):
    """One ranking across both vendors, on measured pitch — not a parallel flow."""
    studio = Studio(user_id=user.id)
    synced = await studio.sync_voice_artists()
    assert synced["voices"] == 3
    assert synced["measured"] == 3
    assert epidemic_cache_path().exists()

    listed = studio.voice_catalogue()
    assert "epidemic" in listed["vendors"]

    cast = studio.cast_voice(pitch="low", limit=3)
    assert "epidemic" in cast["ranked_across"]
    # The low-pitched artist should be reachable when a low voice is asked for.
    names = {candidate["name"] for candidate in cast["candidates"]}
    assert names


@pytest.mark.asyncio
async def test_sync_leaves_the_other_vendors_catalogue_alone(user, storage_dir):
    """Adding a vendor must not delete one.

    Writing into `voice_catalogue.json` would drop the ElevenLabs catalogue as a side
    effect, and the operator would find out at the next casting.
    """
    shared = storage_dir / "voice_catalogue.json"
    shared.parent.mkdir(parents=True, exist_ok=True)
    shared.write_text('{"voices": [{"voice_id": "keep-me", "name": "Keep"}]}',
                      encoding="utf-8")

    await Studio(user_id=user.id).sync_voice_artists()

    assert "keep-me" in shared.read_text(encoding="utf-8")
    assert epidemic_cache_path() != shared


def test_the_tools_are_registered_with_the_right_permission():
    """Reading the roster is free; writing a catalogue is a write."""
    assert "mcp__forgecast__voice_artists" in tools.ALLOWED
    assert "voice_artists" in tools.ALL_TOOLS
    assert "mcp__forgecast__sync_voice_artists" in tools.ALLOWED
    assert "sync_voice_artists" in tools._WRITES
    # Still true, and this file must not have loosened it.
    assert "mcp__forgecast__decide_gate" not in tools.ALLOWED
