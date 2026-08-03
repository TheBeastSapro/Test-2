"""Narration on the MiniMax subscription instead of the API balance.

Two routes reach the same vendor and the only difference that matters is which account
pays. Every test here is about keeping that difference true and visible, because the
failure mode is silent: a render that works perfectly and bills the wrong meter.

The CLI itself is never run. What is exercised is everything that decides whether it
*would* be run, the argv it would be run with, and what is recorded afterwards.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forgecast.agent import minimax_auth
from forgecast.providers import ProviderError
from forgecast.providers.minimax_cli import MiniMaxCliVoiceProvider
from forgecast.providers.registry import CATALOGUE, DEFAULT_ROUTING, Capability


def _status(**fields):
    from forgecast.agent.minimax_auth import MiniMaxStatus

    base = {"ok": False, "headline": "", "detail": ""}
    return MiniMaxStatus(**{**base, **fields})


# ----------------------------------------------------------------- when it is offered


def test_it_is_a_voice_vendor_you_can_choose():
    cap, cls, key_name = CATALOGUE["minimax-voice-cli"]
    assert cap is Capability.voice
    assert cls is MiniMaxCliVoiceProvider
    # No key name. This route takes no credential at all — that is the point of it, and
    # a key name here would send the registry looking for a provider key that nothing
    # writes, so the vendor would be permanently unconfigured.
    assert key_name == ""


def test_neither_minimax_route_is_ever_fallen_back_to():
    """Both are chosen per channel, never inherited.

    The paid route must not be reached by accident because it spends money. The
    subscription route must not be reached by accident either, for a different reason:
    it would change which voice a series is narrated in, halfway through the series.
    """
    voice = DEFAULT_ROUTING[Capability.voice]
    assert "minimax-voice" not in voice
    assert "minimax-voice-cli" not in voice


# --------------------------------------------------------------- refusing, and saying why


def test_a_missing_cli_names_the_install_and_the_other_route(monkeypatch):
    monkeypatch.setattr(minimax_auth, "check",
                        lambda root=None: _status(cli_found=False))
    ready, reason = MiniMaxCliVoiceProvider.available()
    assert ready is False
    assert "npm install -g mmx-cli" in reason
    # And it says what happens if you do nothing, because the alternative is a run that
    # stops with no idea that a working second route exists.
    assert "API balance" in reason


def test_not_signed_in_is_a_sign_in_instruction_not_an_install_one(monkeypatch):
    monkeypatch.setattr(minimax_auth, "check",
                        lambda root=None: _status(cli_found=True, signed_in=False))
    ready, reason = MiniMaxCliVoiceProvider.available()
    assert ready is False
    assert "sign" in reason.lower()
    assert "npm install" not in reason


def test_a_key_authenticated_cli_is_refused_rather_than_reported_as_the_plan(monkeypatch):
    """This is the one that protects someone's money.

    `mmx auth login --api-key …` produces a CLI that is signed in and works — and bills
    per character, exactly like the HTTP route. Accepting it here would render narration
    that draws down the API balance while every artifact says it came out of the
    subscription quota, which is a lie in the one field an operator would check.
    """
    monkeypatch.setattr(
        minimax_auth, "check",
        lambda root=None: _status(cli_found=True, signed_in=True, with_api_key=True))
    ready, reason = MiniMaxCliVoiceProvider.available()
    assert ready is False
    assert "api key" in reason.lower()
    assert "mmx auth logout" in reason


def test_ready_when_signed_in_on_the_subscription(monkeypatch):
    monkeypatch.setattr(
        minimax_auth, "check",
        lambda root=None: _status(ok=True, cli_found=True, signed_in=True,
                                  with_api_key=False))
    assert MiniMaxCliVoiceProvider.available() == (True, "")


# ------------------------------------------------------------------ the call it makes


@pytest.mark.asyncio
async def test_the_script_goes_on_stdin_and_the_flags_are_the_cli_s(monkeypatch, tmp_path):
    """Narration contains quotes, apostrophes and newlines.

    Passed as `--text "…"` every one of those is a way for an argument list to be
    parsed into something other than what was written, and the failure is silent — a
    voiceover that is subtly not the script. stdin has no quoting rules to get wrong.
    """
    monkeypatch.setattr(
        minimax_auth, "check",
        lambda root=None: _status(ok=True, cli_found=True, signed_in=True))
    monkeypatch.setattr(minimax_auth, "find_cli", lambda root=None: "/usr/bin/mmx")

    seen: dict = {}
    out_file = tmp_path / "vo.mp3"

    async def fake_run(self, argv, stdin_text):
        seen["argv"] = argv
        seen["stdin"] = stdin_text
        out_file.write_bytes(b"\x00" * 512)
        return 0, ""

    monkeypatch.setattr(MiniMaxCliVoiceProvider, "_run", fake_run)
    monkeypatch.setattr("forgecast.render.ffmpeg.ffprobe_duration", lambda p: 12.5)

    script = 'She said "no", and then — nothing.\nNot a word.'
    result = await MiniMaxCliVoiceProvider().synthesize(
        script, voice_id="English_CalmWoman", out_path=out_file, speed=1.1)

    assert seen["stdin"] == script
    assert "--text-file" in seen["argv"] and "-" in seen["argv"]
    assert not any(script in part for part in seen["argv"])
    assert seen["argv"][1:3] == ["speech", "synthesize"]
    assert "English_CalmWoman" in seen["argv"]

    # And the meter is recorded rather than inferred. This field is how anyone reading a
    # run's artifacts finds out what a voiceover cost.
    assert result.meta["billing"] == "minimax subscription quota"
    assert result.credits == 0
    assert result.duration_seconds == 12.5


@pytest.mark.asyncio
async def test_speed_is_clamped_to_what_the_vendor_accepts(monkeypatch, tmp_path):
    """The caller's speed comes from a style profile that knows nothing about MiniMax.

    Out of range is a rejected request, several minutes into a run that has already paid
    for everything upstream of the voice node.
    """
    monkeypatch.setattr(
        minimax_auth, "check",
        lambda root=None: _status(ok=True, cli_found=True, signed_in=True))
    monkeypatch.setattr(minimax_auth, "find_cli", lambda root=None: "/usr/bin/mmx")
    monkeypatch.setattr("forgecast.render.ffmpeg.ffprobe_duration", lambda p: 1.0)

    seen: dict = {}
    out_file = tmp_path / "vo.mp3"

    async def fake_run(self, argv, stdin_text):
        seen["speed"] = argv[argv.index("--speed") + 1]
        out_file.write_bytes(b"\x00" * 16)
        return 0, ""

    monkeypatch.setattr(MiniMaxCliVoiceProvider, "_run", fake_run)
    await MiniMaxCliVoiceProvider().synthesize(
        "hello", voice_id="v", out_path=out_file, speed=9.0)
    assert float(seen["speed"]) == 2.0


@pytest.mark.asyncio
async def test_success_with_no_audio_is_a_failure(monkeypatch, tmp_path):
    """A zero-byte file passed downstream becomes a rendered video with silence where
    the narration goes — discovered after the render has been paid for."""
    monkeypatch.setattr(
        minimax_auth, "check",
        lambda root=None: _status(ok=True, cli_found=True, signed_in=True))
    monkeypatch.setattr(minimax_auth, "find_cli", lambda root=None: "/usr/bin/mmx")

    async def wrote_nothing(self, argv, stdin_text):
        return 0, "done"

    monkeypatch.setattr(MiniMaxCliVoiceProvider, "_run", wrote_nothing)
    with pytest.raises(ProviderError) as caught:
        await MiniMaxCliVoiceProvider().synthesize(
            "hello", voice_id="v", out_path=tmp_path / "vo.mp3")
    assert "wrote no audio" in str(caught.value)


@pytest.mark.asyncio
async def test_a_used_up_quota_says_what_to_do_instead(monkeypatch, tmp_path):
    """The CLI returns 1 for everything, so the exit code carries no information and
    the text is all there is. An unrecognised failure is passed through whole rather
    than replaced by a generic sentence."""
    monkeypatch.setattr(
        minimax_auth, "check",
        lambda root=None: _status(ok=True, cli_found=True, signed_in=True))
    monkeypatch.setattr(minimax_auth, "find_cli", lambda root=None: "/usr/bin/mmx")

    async def out_of_quota(self, argv, stdin_text):
        return 1, "Error: speech quota exhausted for this window"

    monkeypatch.setattr(MiniMaxCliVoiceProvider, "_run", out_of_quota)
    with pytest.raises(ProviderError) as caught:
        await MiniMaxCliVoiceProvider().synthesize(
            "hello", voice_id="v", out_path=tmp_path / "vo.mp3")
    message = str(caught.value)
    assert "quota" in message
    assert "ElevenLabs" in message or "minimax-voice" in message


@pytest.mark.asyncio
async def test_a_script_over_the_limit_is_refused_before_the_cli_runs(monkeypatch,
                                                                     tmp_path):
    monkeypatch.setattr(
        minimax_auth, "check",
        lambda root=None: _status(ok=True, cli_found=True, signed_in=True))

    async def forbidden(self, argv, stdin_text):                      # pragma: no cover
        raise AssertionError("the length check has to happen before the call")

    monkeypatch.setattr(MiniMaxCliVoiceProvider, "_run", forbidden)
    with pytest.raises(ProviderError) as caught:
        await MiniMaxCliVoiceProvider().synthesize(
            "x" * 10_001, voice_id="v", out_path=tmp_path / "vo.mp3")
    assert "10000" in str(caught.value).replace(",", "")


@pytest.mark.asyncio
async def test_an_unusable_route_raises_rather_than_writing_a_file(monkeypatch,
                                                                  tmp_path):
    monkeypatch.setattr(minimax_auth, "check",
                        lambda root=None: _status(cli_found=False))
    target = tmp_path / "vo.mp3"
    with pytest.raises(ProviderError):
        await MiniMaxCliVoiceProvider().synthesize(
            "hello", voice_id="v", out_path=target)
    assert not target.exists()


# ---------------------------------------------------------------- the voice catalogue


def test_an_unreadable_voice_list_falls_back_instead_of_showing_nothing(monkeypatch):
    """Empty means "could not ask", never "there are none".

    An empty picker reads as a broken app, and the static catalogue is the same system
    voice set — so a machine that cannot run the CLI still casts a voice.
    """
    from forgecast.providers import minimax_cli

    monkeypatch.setattr(minimax_auth, "find_cli", lambda root=None: "")
    assert minimax_cli.cli_voices() == []

    monkeypatch.setattr(minimax_auth, "find_cli",
                        lambda root=None: str(Path("/nonexistent/mmx")))
    assert minimax_cli.cli_voices() == []
