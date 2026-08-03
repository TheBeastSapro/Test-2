"""MiniMax narration: the two things that would cost real money if they were wrong.

The first is the API's failure convention. `POST /t2a_v2` answers **HTTP 200** with an
error inside `base_resp`, so every generic status check in this codebase reads a rejected
request as a successful one. Left alone, that writes an empty file, hands back a
`MediaResult` saying there is a voiceover on disk, and the symptom arrives at the render
as thirteen minutes of silence under the pictures.

The second is routing. ElevenLabs narration is drawn from a subscription character
allowance that is already paid for; MiniMax narration is drawn from an API balance. Those
are not interchangeable, so MiniMax must be reachable by being *chosen* and unreachable by
being *fallen back to* — a lapsed ElevenLabs key must fail loudly rather than quietly start
spending somewhere else.
"""

from __future__ import annotations

import httpx
import pytest

from forgecast.providers import media
from forgecast.providers.base import Capability, ProviderError
from forgecast.providers.registry import CATALOGUE, DEFAULT_ROUTING, ProviderRegistry

pytestmark = pytest.mark.anyio

# A tiny valid MP3-ish payload. The bytes do not have to decode — what is asserted is that
# exactly these bytes reach the file, so a hex-decoding mistake cannot pass.
AUDIO = b"\xff\xfb\x90\x00forgecast"

OK_BODY = {
    "data": {"audio": AUDIO.hex(), "status": 2},
    "extra_info": {"audio_length": 11124, "usage_characters": 163,
                   "audio_sample_rate": 44100, "audio_format": "mp3"},
    "base_resp": {"status_code": 0, "status_msg": "success"},
}


def _transport(monkeypatch, response: httpx.Response, recorder: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if recorder is not None:
            recorder["url"] = str(request.url)
            recorder["auth"] = request.headers.get("Authorization", "")
            recorder["body"] = request.read().decode()
        return response

    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(media.httpx, "AsyncClient", factory)


# ------------------------------------------------------------------ the 200-error trap


async def test_an_error_inside_a_200_is_a_failure_not_a_voiceover(tmp_path, monkeypatch):
    """The whole reason this adapter inspects the body.

    `base_resp.status_code` non-zero with HTTP 200 is how this API declines. A provider
    that returns a MediaResult here has told the pipeline a file exists.
    """
    _transport(monkeypatch, httpx.Response(200, json={
        "base_resp": {"status_code": 1004, "status_msg": "invalid api key"},
    }))
    provider = media.MiniMaxVoiceProvider(api_key="k")

    with pytest.raises(ProviderError) as caught:
        await provider.synthesize("hello", voice_id="English_CalmWoman",
                                  out_path=tmp_path / "vo")

    # The vendor's own words, so the fix is obvious rather than guessed at.
    assert "invalid api key" in str(caught.value)
    assert "1004" in str(caught.value)
    assert not (tmp_path / "vo.mp3").exists(), "a rejected request must leave no file"


async def test_a_200_carrying_no_audio_is_also_a_failure(tmp_path, monkeypatch):
    """`status_code: 0` and an empty `data.audio` has been seen from this API.

    Without this branch, `bytes.fromhex("")` succeeds and writes a zero-byte MP3 that
    ffprobe reports as 0.0 seconds — which the render treats as a video with no narration
    rather than as a failed step.
    """
    _transport(monkeypatch, httpx.Response(200, json={
        "data": {"audio": ""}, "base_resp": {"status_code": 0, "status_msg": "success"},
    }))
    provider = media.MiniMaxVoiceProvider(api_key="k")

    with pytest.raises(ProviderError, match="no audio"):
        await provider.synthesize("hello", voice_id="v", out_path=tmp_path / "vo")


async def test_non_hex_audio_is_reported_rather_than_written(tmp_path, monkeypatch):
    _transport(monkeypatch, httpx.Response(200, json={
        "data": {"audio": "not hex at all"},
        "base_resp": {"status_code": 0},
    }))
    provider = media.MiniMaxVoiceProvider(api_key="k")

    with pytest.raises(ProviderError, match="valid hex"):
        await provider.synthesize("hello", voice_id="v", out_path=tmp_path / "vo")


# ------------------------------------------------------------------- the happy path


async def test_the_audio_is_decoded_from_hex_byte_for_byte(tmp_path, monkeypatch):
    _transport(monkeypatch, httpx.Response(200, json=OK_BODY))
    provider = media.MiniMaxVoiceProvider(api_key="k")

    result = await provider.synthesize("a script", voice_id="English_CalmWoman",
                                       out_path=tmp_path / "vo")

    assert result.path.read_bytes() == AUDIO
    assert result.path.suffix == ".mp3"
    assert result.mime == "audio/mpeg"


async def test_the_duration_comes_from_the_vendors_measurement(tmp_path, monkeypatch):
    """`audio_length` is milliseconds. Probing the file instead would need ffmpeg for a
    number the response already carries — and these test bytes are not decodable."""
    _transport(monkeypatch, httpx.Response(200, json=OK_BODY))
    provider = media.MiniMaxVoiceProvider(api_key="k")

    result = await provider.synthesize("a script", voice_id="v", out_path=tmp_path / "vo")

    assert result.duration_seconds == pytest.approx(11.124)


async def test_billing_follows_the_characters_the_vendor_counted(tmp_path, monkeypatch):
    """163 characters were charged for, whatever the local `len()` says.

    Settling on `len(text)` would put the difference on the house on every voiceover, and
    it would be invisible: the run simply reports a cost lower than the invoice.
    """
    _transport(monkeypatch, httpx.Response(200, json=OK_BODY))
    provider = media.MiniMaxVoiceProvider(api_key="k")

    result = await provider.synthesize("short", voice_id="v", out_path=tmp_path / "vo")

    assert result.meta["characters"] == 163
    assert result.credits > 0
    assert result.meta["billing"] == "minimax api balance"


async def test_turbo_is_billed_at_the_turbo_rate(tmp_path, monkeypatch):
    """The two model families cost $60 and $100 per million characters.

    One rate for both would overcharge turbo by two thirds or undercharge HD by 40%.
    """
    _transport(monkeypatch, httpx.Response(200, json=OK_BODY))
    hd = media.MiniMaxVoiceProvider(api_key="k", model="speech-2.6-hd")
    turbo = media.MiniMaxVoiceProvider(api_key="k", model="speech-2.6-turbo")

    assert turbo._rate() < hd._rate()
    dear = await hd.synthesize("x", voice_id="v", out_path=tmp_path / "a")
    cheap = await turbo.synthesize("x", voice_id="v", out_path=tmp_path / "b")
    assert cheap.credits <= dear.credits


# ----------------------------------------------------------------- the request itself


async def test_the_request_is_shaped_the_way_this_api_expects(tmp_path, monkeypatch):
    recorder: dict = {}
    _transport(monkeypatch, httpx.Response(200, json=OK_BODY), recorder)
    provider = media.MiniMaxVoiceProvider(api_key="secret-key")

    await provider.synthesize("a script", voice_id="English_Wiselady",
                              out_path=tmp_path / "vo")

    assert recorder["url"].endswith("/v1/t2a_v2")
    # Bearer, not ElevenLabs' `xi-api-key`. Copying the neighbouring adapter's header is
    # the obvious mistake and it presents as an unexplained 401.
    assert recorder["auth"] == "Bearer secret-key"
    # Compact JSON — httpx serialises without spaces, so these are the real substrings.
    assert '"voice_id":"English_Wiselady"' in recorder["body"]
    assert '"output_format":"hex"' in recorder["body"]


@pytest.mark.parametrize(("asked", "sent"), [(0.1, 0.5), (1.0, 1.0), (9.0, 2.0)])
async def test_speed_is_clamped_to_the_range_the_api_accepts(asked, sent, tmp_path,
                                                             monkeypatch):
    """0.5–2.0. Out of range is a rejected request, and the caller's speed comes from a
    style profile that knows nothing about this vendor's limits."""
    recorder: dict = {}
    _transport(monkeypatch, httpx.Response(200, json=OK_BODY), recorder)
    provider = media.MiniMaxVoiceProvider(api_key="k")

    await provider.synthesize("x", voice_id="v", out_path=tmp_path / "vo", speed=asked)

    assert f'"speed":{sent}' in recorder["body"]


async def test_a_script_over_the_character_cap_is_refused_before_the_request(tmp_path,
                                                                            monkeypatch):
    """10,000 characters is roughly eleven minutes, so long-form scripts exceed it.

    Refused locally with the number and the remedy, because the alternative is a rejected
    request partway through a run that has already paid for images.
    """
    _transport(monkeypatch, httpx.Response(500, text="should never be reached"))
    provider = media.MiniMaxVoiceProvider(api_key="k")

    with pytest.raises(ProviderError) as caught:
        await provider.synthesize("x" * 10_001, voice_id="v", out_path=tmp_path / "vo")

    assert "10000" in str(caught.value).replace(",", "")
    assert "split" in str(caught.value)


async def test_a_missing_key_is_refused_before_the_network(tmp_path, monkeypatch):
    _transport(monkeypatch, httpx.Response(500, text="should never be reached"))
    with pytest.raises(ProviderError):
        await media.MiniMaxVoiceProvider(api_key="").synthesize(
            "x", voice_id="v", out_path=tmp_path / "vo")


# --------------------------------------------------------------------- the routing


def test_minimax_is_never_fallen_back_to():
    """The rule that keeps subscription spend and balance spend apart.

    If this vendor appears in the default chain then an expired ElevenLabs key stops
    being an error and starts being a silent switch to per-character billing.
    """
    assert "minimax-voice" not in DEFAULT_ROUTING[Capability.voice]
    assert "elevenlabs" in DEFAULT_ROUTING[Capability.voice]


def test_but_naming_it_resolves_to_it():
    """Chosen, it must actually be reachable — otherwise the option is decoration."""
    capability, klass, key_name = CATALOGUE["minimax-voice"]
    assert capability is Capability.voice
    assert klass is media.MiniMaxVoiceProvider
    # Its own key name, so it cannot be satisfied by the ElevenLabs credential.
    assert key_name == "minimax"

    registry = ProviderRegistry(mode="live", user_keys={"minimax": "k"},
                                overrides={"voice": "minimax-voice"})
    assert isinstance(registry.voice(), media.MiniMaxVoiceProvider)


def test_choosing_it_without_a_key_falls_back_in_the_safe_direction():
    """An override with no key falls through, and the direction of that matters.

    This is the registry's long-standing behaviour for every vendor and it is not changed
    here — what is pinned is that the fall-through can only ever run *towards* the
    subscription. Naming MiniMax with no MiniMax key lands on ElevenLabs and spends an
    allowance already paid for; the reverse cannot happen, because MiniMax is not in the
    default chain at all. One direction costs nothing new, the other would be a surprise
    on an invoice.
    """
    registry = ProviderRegistry(mode="live", user_keys={"elevenlabs": "el"},
                                overrides={"voice": "minimax-voice"})
    assert isinstance(registry.voice(), media.ElevenLabsProvider)

    # And with neither key it is an error naming both, rather than a silent no-op.
    bare = ProviderRegistry(mode="live", user_keys={},
                            overrides={"voice": "minimax-voice"})
    with pytest.raises(ProviderError) as caught:
        bare.voice()
    assert "minimax" in str(caught.value)
