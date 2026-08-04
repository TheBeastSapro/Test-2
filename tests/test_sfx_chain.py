"""The sound-effect chain: three tiers, and the one that establishes nothing.

The defect this suite is written against is not a crash. It is the accent palette
quietly coming from the open web on a run that never asked for it, and reading in the
output exactly like a cleared library sound.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from forgecast.providers import sfx
from forgecast.providers.base import MediaResult, ProviderError, SoundEffectAsset
from forgecast.providers.sfx import SfxChain, SfxError, SfxResult


class _Music:
    """A stand-in for the music vendor, implementing only what the chain calls."""

    def __init__(self, assets=None, fails=False):
        self.assets = assets or []
        self.fails = fails

    async def search_sound_effects(self, *, term="", tags=(), seconds_max=0.0, limit=10):
        if self.fails:
            raise ProviderError("subscription down")
        return list(self.assets)[:limit]

    async def fetch_sound_effect(self, effect_id, *, out_path: Path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"audio")
        return MediaResult(path=out_path, mime="audio/mpeg", provider="epidemic",
                           duration_seconds=1.5)


def _asset(effect_id="epidemic:1", title="whoosh"):
    return SoundEffectAsset(effect_id=effect_id, title=title, duration_seconds=1.2,
                            provider="epidemic")


# ------------------------------------------------------------------------- the tiers


def test_the_chain_reports_only_the_tiers_it_actually_has():
    """Reported before it spends, because 'which tiers are live' is the question an
    operator has when a palette comes back thin."""
    assert SfxChain().tiers() == []
    assert SfxChain(music_provider=_Music()).tiers() == ["epidemic"]
    full = SfxChain(music_provider=_Music(), freesound_key="k", allow_web=True)
    assert full.tiers() == ["epidemic", "freesound", "web"]


def test_effects_no_longer_need_a_music_subscription():
    """The failure this whole module exists for: accents are opt-out, so a channel that
    never chose a music vendor had still asked for them and silently got none."""
    assert SfxChain(music_provider=None, freesound_key="k").tiers() == ["freesound"]


def test_a_dead_subscription_falls_through_rather_than_failing(monkeypatch):
    async def freesound(term, *, api_key, seconds_max=0.0, limit=6):
        return [(_asset("freesound:9", "glass"), "cc0", "", "https://freesound.test/9")]

    monkeypatch.setattr(sfx, "search_freesound", freesound)
    chain = SfxChain(music_provider=_Music(fails=True), freesound_key="k")
    found = asyncio.run(chain.search_sound_effects(term="glass", limit=4))
    assert [a.effect_id for a in found] == ["freesound:9"]


# --------------------------------------------------------------------- the licence rule


def test_freesound_licences_that_a_monetised_video_would_breach_are_dropped():
    """A monetised video is commercial use, so `by-nc` is breached by it. Freesound holds
    a great deal of `by-nc` — omitting this would look like the tier working well right
    up until it did not."""
    assert sfx._freesound_licence("http://creativecommons.org/publicdomain/zero/1.0/") == "cc0"
    assert sfx._freesound_licence("https://creativecommons.org/licenses/by/4.0/") == "by"
    for refused in ("https://creativecommons.org/licenses/by-nc/4.0/",
                    "https://creativecommons.org/licenses/by-nd/4.0/", ""):
        assert sfx._freesound_licence(refused) == "", refused


def test_a_web_sound_is_never_marked_safe_and_says_why():
    result = SfxResult(asset=_asset("web:vine boom"), path=Path("x.mp3"),
                       licence="not_established", tier="web", operator_directed=True,
                       flag_reason="fetched from the open web")
    assert not result.commercially_safe
    assert result.needs_attribution
    assert "web" in result.flag_reason


def test_an_epidemic_sound_is_cleared_and_needs_no_credit():
    result = SfxResult(asset=_asset(), path=Path("x.mp3"), licence="epidemic",
                       tier="epidemic")
    assert result.commercially_safe and not result.needs_attribution


# ------------------------------------------------------------------------ the web tier


def test_the_web_tier_cannot_answer_a_search(monkeypatch):
    """It answers 'get me this exact sound', which is one named thing — not a query
    returning candidates the caller believes are interchangeable. Letting it answer a
    search would put an unestablished result into a palette."""
    async def none(term, *, api_key, seconds_max=0.0, limit=6):
        return []

    monkeypatch.setattr(sfx, "search_freesound", none)
    chain = SfxChain(music_provider=None, freesound_key="k", allow_web=True)
    assert asyncio.run(chain.search_sound_effects(term="vine boom")) == []


def test_the_web_tier_is_off_unless_the_run_asked(tmp_path: Path):
    """A flag that appears when nobody asked for it is a flag operators scroll past."""
    chain = SfxChain(allow_web=False)
    with pytest.raises(SfxError, match="not enabled"):
        chain.fetch_named("vine boom", tmp_path / "s")


def test_a_named_sound_is_trimmed_on_arrival(tmp_path: Path, monkeypatch):
    """A later stage that never knew where the file came from should not be able to lay
    ninety seconds of somebody's commentary under a cut."""
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        Path(str(command[-1]).replace(".%(ext)s", ".mp3")).write_bytes(b"audio")
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(sfx.subprocess, "run", fake_run)
    monkeypatch.setattr(sfx, "_ytdlp", lambda: "yt-dlp")

    chain = SfxChain(allow_web=True)
    result = chain.fetch_named("vine boom", tmp_path / "s", seconds=3.0)

    joined = " ".join(calls[0])
    assert "-t 3.00" in joined, "the trim has to reach ffmpeg"
    assert result.operator_directed and not result.commercially_safe
    assert result.flag_reason and "3s" in result.flag_reason


def test_a_missing_ytdlp_names_the_fix(monkeypatch):
    monkeypatch.setattr(sfx.shutil, "which", lambda name: None)
    with pytest.raises(SfxError, match="Setup"):
        sfx._ytdlp()


# ------------------------------------------------------------------------- reporting


def test_the_run_can_tell_which_sounds_need_a_flag_and_which_need_a_credit():
    chain = SfxChain()
    chain.used = [
        SfxResult(asset=_asset(), path=Path("a"), licence="epidemic", tier="epidemic"),
        SfxResult(asset=_asset("freesound:2"), path=Path("b"), licence="by",
                  attribution="glass by someone — BY", tier="freesound"),
        SfxResult(asset=_asset("web:boom"), path=Path("c"), licence="not_established",
                  tier="web", operator_directed=True, flag_reason="fetched from the web"),
    ]
    assert chain.flags() == ["fetched from the web"]
    assert chain.credits() == ["glass by someone — BY"]


def test_fetching_routes_on_the_id_rather_than_on_a_remembered_search(tmp_path: Path):
    """A palette is fetched well after it was searched. A chain relying on its own memory
    fetches the wrong file the first time two roles share a term."""
    chain = SfxChain(music_provider=_Music())
    result = asyncio.run(chain.fetch_sound_effect("epidemic:1", out_path=tmp_path / "a.mp3"))
    assert result.meta["tier"] == "epidemic"
    assert chain.used[-1].licence == "epidemic"


def test_a_key_that_is_absent_skips_its_tier_rather_than_erroring():
    assert asyncio.run(sfx.search_freesound("glass", api_key="")) == []
