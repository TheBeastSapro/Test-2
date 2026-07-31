"""Audition samples for shortlisted voices.

Samples use a line from the *actual script* rather than a stock sentence, because a
voice that suits "the quick brown fox" tells you nothing about whether it suits your
hook. The hook is usually the right line: it is the most exposed piece of narration
in the video and the hardest for a voice to carry.

In mock mode the sample is a synthesised tone at the catalogue voice's pitch band,
clearly labelled as a placeholder. That is not a substitute for hearing the voice —
it exists so the whole casting flow, gate included, can be built and demonstrated
without a key. When it runs, the report says the samples are placeholders.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..config import get_settings
from .casting import VoiceCandidate

log = logging.getLogger("forgecast.voice.audition")

# Mid-band frequency per pitch band, for the mock placeholder tones.
BAND_FREQUENCY = {"low": 95.0, "low_mid": 135.0, "mid": 185.0, "high": 240.0}
MAX_SAMPLE_WORDS = 28


def sample_line(script: dict | None, brief: dict | None = None, topic: str = "") -> str:
    """Pick the line to audition: the hook if there is one."""
    for source, key in ((brief, "hook"), (script, "title")):
        value = (source or {}).get(key)
        if value and len(str(value).split()) >= 4:
            return " ".join(str(value).split()[:MAX_SAMPLE_WORDS])

    scenes = (script or {}).get("scenes") or []
    if scenes:
        narration = str(scenes[0].get("narration") or "")
        if narration:
            return " ".join(narration.split()[:MAX_SAMPLE_WORDS])

    if topic:
        return f"Here is what most people get wrong about {topic}."
    return "This is a short audition line for voice selection."


async def render_samples(
    candidates: list[VoiceCandidate],
    line: str,
    outdir: Path,
    *,
    registry=None,
    speed: float = 1.0,
) -> tuple[list[VoiceCandidate], dict]:
    """Produce one sample per candidate. Returns (candidates, metadata)."""
    outdir.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    meta: dict = {"line": line, "mode": settings.provider_mode, "placeholder": False}

    if settings.is_mock or registry is None:
        _mock_samples(candidates, outdir)
        meta["placeholder"] = True
        meta["note"] = (
            "Mock mode: samples are labelled placeholder tones at each voice's pitch "
            "band, not the actual voice. Set FORGECAST_PROVIDER_MODE=live with an "
            "ElevenLabs key to audition for real."
        )
        return candidates, meta

    provider = registry.voice()
    # Candidates from the measured catalogue already carry the account's real IDs;
    # only the offline-fallback ones need a name lookup.
    if any(candidate.voice_id is None for candidate in candidates):
        meta["resolved"] = await _resolve_ids(provider, candidates)
    else:
        meta["resolved"] = {"source": "measured_catalogue"}
    credits = 0

    for candidate in candidates:
        if not candidate.voice_id:
            candidate.caveats.append(
                "could not resolve this name to a voice on the account — no sample"
            )
            continue
        try:
            result = await provider.synthesize(
                line,
                voice_id=candidate.voice_id,
                out_path=outdir / f"audition_{candidate.name.lower()}",
                speed=speed,
            )
            candidate.sample_path = str(result.path)
            credits += result.credits
        except Exception as exc:
            log.warning("sample failed for %s: %s", candidate.name, exc)
            candidate.caveats.append(f"sample failed: {exc}")

    meta["credits"] = credits
    return candidates, meta


async def _resolve_ids(provider, candidates: list[VoiceCandidate]) -> dict:
    """Map catalogue names to the account's actual voice IDs."""
    try:
        available = await provider.list_voices()
    except Exception as exc:
        log.warning("could not list voices: %s", exc)
        return {"error": str(exc)}

    lookup = {str(entry.get("name", "")).lower(): entry.get("voice_id") for entry in available}
    matched: dict[str, str | None] = {}
    for candidate in candidates:
        candidate.voice_id = lookup.get(candidate.name.lower())
        matched[candidate.name] = candidate.voice_id
    return {"matched": matched, "available_count": len(available)}


def _mock_samples(candidates: list[VoiceCandidate], outdir: Path) -> None:
    from ..render import ffmpeg as ff

    for candidate in candidates:
        band = candidate.catalogue.pitch_band if candidate.catalogue else "mid"
        frequency = BAND_FREQUENCY.get(band, 185.0)
        path = outdir / f"audition_{candidate.name.lower()}_PLACEHOLDER.m4a"
        try:
            ff.make_tone_audio(path, 2.5, frequency=int(frequency))
            candidate.sample_path = str(path)
            candidate.caveats.append(
                f"placeholder tone at {frequency:.0f}Hz, not the real voice"
            )
        except Exception as exc:
            log.warning("placeholder sample failed for %s: %s", candidate.name, exc)
