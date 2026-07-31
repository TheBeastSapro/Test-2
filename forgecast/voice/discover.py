"""Build the voice catalogue from the live account — and measure it, don't guess it.

Two things forced this module.

First, a hardcoded name list goes stale. ElevenLabs replaced its old default voice set,
and 8 of 11 names in the static catalogue no longer resolve on a current account. Names
are the right key to cast on, but the list of them has to come from the account.

Second, and more interesting: the API describes a voice with labels (gender, age,
accent, use case) but never states its pitch — and pitch is the strongest signal for
whether two voices read as similar. The tempting shortcut is to infer pitch from the
gender label. That is exactly the guess this codebase refuses to make elsewhere, and it
would be wrong often enough to matter.

So we measure instead. Every voice ships a `preview_url`; we download it and run the
same autocorrelation f0 analyser used on reference videos (verified accurate to ~1% on
known tones). The result is a catalogue whose pitch numbers are observations of the
actual voice, comparable on the same scale as the reference measurement. Previews are
static files and the analysis is local, so building the catalogue is free.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..vision.audio import SAMPLE_RATE, _pitch
from ..vision.probe import FFMPEG

log = logging.getLogger("forgecast.voice.discover")

CACHE_VERSION = "1.0"
DEFAULT_CACHE = Path("storage/voice_catalogue.json")


@dataclass
class MeasuredVoice:
    """A voice from the account, with its pitch actually measured."""

    voice_id: str
    name: str
    display_name: str = ""
    gender: str = ""
    accent: str = ""
    age: str = ""
    use_case: str = ""
    descriptive: str = ""
    category: str = ""
    pitch_hz: float | None = None
    pitch_band: str | None = None
    pitch_spread: float | None = None
    voiced_ratio: float = 0.0
    preview_url: str = ""
    measurement: str = "not_measured"
    descriptors: list[str] = field(default_factory=list)

    @property
    def energy(self) -> str:
        """Map the vendor's descriptors onto the casting vocabulary.

        A mapping, not a measurement — the words come from ElevenLabs' own labels and
        voice titles, so they are the vendor's characterisation rather than ours.
        """
        text = " ".join(
            [self.descriptive, self.use_case, " ".join(self.descriptors)]
        ).lower()
        if any(word in text for word in
               ("energetic", "enthusiast", "hype", "excited", "sassy", "quirky",
                "social_media", "upbeat")):
            return "energetic"
        if any(word in text for word in
               ("calm", "relaxed", "soothing", "meditation", "gentle", "laid-back",
                "laid_back")):
            return "calm"
        if any(word in text for word in ("warm", "friendly", "captivating", "storyteller")):
            return "warm"
        return "measured"

    def as_dict(self) -> dict:
        return {
            "voice_id": self.voice_id,
            "name": self.name,
            "display_name": self.display_name,
            "gender": self.gender,
            "accent": self.accent,
            "age": self.age,
            "use_case": self.use_case,
            "descriptive": self.descriptive,
            "category": self.category,
            "pitch_hz": round(self.pitch_hz, 1) if self.pitch_hz else None,
            "pitch_band": self.pitch_band,
            "voiced_ratio": round(self.voiced_ratio, 3),
            "energy": self.energy,
            "descriptors": self.descriptors,
            "measurement": self.measurement,
            "preview_url": self.preview_url,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MeasuredVoice:
        return cls(
            voice_id=data.get("voice_id", ""),
            name=data.get("name", ""),
            display_name=data.get("display_name", ""),
            gender=data.get("gender", ""),
            accent=data.get("accent", ""),
            age=data.get("age", ""),
            use_case=data.get("use_case", ""),
            descriptive=data.get("descriptive", ""),
            category=data.get("category", ""),
            pitch_hz=data.get("pitch_hz"),
            pitch_band=data.get("pitch_band"),
            voiced_ratio=data.get("voiced_ratio") or 0.0,
            preview_url=data.get("preview_url", ""),
            measurement=data.get("measurement", "not_measured"),
            descriptors=list(data.get("descriptors") or []),
        )


def parse_voice(entry: dict) -> MeasuredVoice:
    """Split an ElevenLabs voice record into name plus descriptors.

    Current voice titles pack characterisation into the name — "Roger - Laid-Back,
    Casual, Resonant" — so the part before the dash is the castable name and the rest
    is free metadata worth keeping.
    """
    raw_name = str(entry.get("name") or "").strip()
    head, _, tail = raw_name.partition(" - ")
    descriptors = [item.strip() for item in tail.split(",") if item.strip()]
    labels = entry.get("labels") or {}

    return MeasuredVoice(
        voice_id=str(entry.get("voice_id") or ""),
        name=head.strip() or raw_name,
        display_name=raw_name,
        gender=str(labels.get("gender") or ""),
        accent=str(labels.get("accent") or ""),
        age=str(labels.get("age") or ""),
        use_case=str(labels.get("use_case") or ""),
        descriptive=str(labels.get("descriptive") or ""),
        category=str(entry.get("category") or ""),
        preview_url=str(entry.get("preview_url") or ""),
        descriptors=descriptors,
    )


def _decode(path: Path) -> np.ndarray | None:
    proc = subprocess.run(
        [FFMPEG, "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SAMPLE_RATE),
         "-f", "s16le", "-acodec", "pcm_s16le", "-"],
        capture_output=True,
        timeout=120,
    )
    if proc.returncode != 0 or not proc.stdout:
        return None
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def measure_preview(voice: MeasuredVoice, *, timeout: float = 45.0) -> MeasuredVoice:
    """Download a voice's preview and measure its pitch."""
    if not voice.preview_url:
        voice.measurement = "no_preview_url"
        return voice

    with tempfile.TemporaryDirectory(prefix="fcvoice-") as tmp:
        target = Path(tmp) / "preview.mp3"
        proc = subprocess.run(
            ["curl", "-fsSL", "--max-time", str(int(timeout)), "-o", str(target),
             voice.preview_url],
            capture_output=True,
        )
        if proc.returncode != 0 or not target.exists():
            voice.measurement = "preview_download_failed"
            return voice

        samples = _decode(target)

    if samples is None or samples.size < SAMPLE_RATE // 2:
        voice.measurement = "preview_undecodable"
        return voice

    pitch_hz, band, spread, voiced = _pitch(samples)
    voice.pitch_hz = pitch_hz
    voice.pitch_band = band
    voice.pitch_spread = spread
    voice.voiced_ratio = voiced
    # Low voiced ratio means the preview gave too little speech to trust, same rule
    # the reference side applies.
    voice.measurement = "measured" if (pitch_hz and voiced >= 0.25) else "inconclusive"
    if voice.measurement == "inconclusive":
        voice.pitch_band = None
    return voice


async def build_catalogue(
    provider,
    *,
    cache_path: Path | None = None,
    measure: bool = True,
    limit: int | None = None,
) -> list[MeasuredVoice]:
    """Fetch the account's voices, measure their pitch, and cache the result."""
    entries = await provider.list_voices()
    voices = [parse_voice(entry) for entry in entries if entry.get("voice_id")]
    if limit:
        voices = voices[:limit]
    log.info("found %d voices on the account", len(voices))

    if measure:
        for index, voice in enumerate(voices, start=1):
            measure_preview(voice)
            log.info(
                "[%d/%d] %s -> %s (%s)", index, len(voices), voice.name,
                f"{voice.pitch_hz:.0f}Hz" if voice.pitch_hz else "—", voice.measurement,
            )

    if cache_path:
        save_catalogue(voices, cache_path)
    return voices


def save_catalogue(voices: list[MeasuredVoice], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "cache_version": CACHE_VERSION,
                "count": len(voices),
                "voices": [voice.as_dict() for voice in voices],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def load_catalogue(path: Path | None = None) -> list[MeasuredVoice]:
    """Load a cached catalogue, or return an empty list if there is none."""
    path = path or DEFAULT_CACHE
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("voice catalogue cache at %s is unreadable", path)
        return []
    return [MeasuredVoice.from_dict(entry) for entry in data.get("voices") or []]


def measured_summary(voices: list[MeasuredVoice]) -> str:
    measured = [voice for voice in voices if voice.measurement == "measured"]
    bands: dict[str, int] = {}
    for voice in measured:
        bands[voice.pitch_band or "?"] = bands.get(voice.pitch_band or "?", 0) + 1
    parts = [f"{len(measured)}/{len(voices)} voices measured"]
    if bands:
        parts.append("bands: " + ", ".join(f"{k}={v}" for k, v in sorted(bands.items())))
    return " · ".join(parts)


# --------------------------------------------------- two-stage discovery at scale

# The shared library holds ~15,000 voices. Measuring every preview would mean 15,000
# downloads, so discovery splits in two: rank on the vendor's metadata first, which is
# free and already fetched, then measure pitch only for the handful that survive. The
# expensive, authoritative signal is spent exactly where it changes the answer.
PRERANK_POOL = 20


def metadata_score(target, voice: MeasuredVoice) -> float:
    """Cheap pre-ranking on labels only — no pitch, nothing downloaded.

    Pitch is the signal we actually trust, but we cannot afford it for thousands of
    voices. Gender and age are used *here only* as a coarse proxy for vocal range to
    decide who is worth measuring; the real comparison still happens on measured Hz,
    so a wrong guess at this stage costs a wasted download, never a wrong casting.
    """
    score = 0.0

    if getattr(target, "accent", None):
        wanted = str(target.accent).lower()
        if voice.accent and wanted in voice.accent.lower():
            score += 2.0
        elif voice.accent:
            score -= 1.0

    register = (getattr(target, "register", "") or "").lower()
    if register:
        from .casting import REGISTER_USE_CASES

        if voice.use_case and voice.use_case in REGISTER_USE_CASES.get(register, ()):
            score += 2.0

    if getattr(target, "energy", None) and voice.energy == target.energy:
        score += 1.0

    # Range proxy, only to choose measurement candidates.
    band = getattr(target, "pitch_band", None)
    if (band in {"low", "low_mid"} and voice.gender == "male") or (band in {"mid", "high"} and voice.gender == "female"):
        score += 1.0

    if voice.category == "premade":
        score += 0.75          # account voices are licensed and known-good
    if voice.preview_url:
        score += 0.5           # measurable at all
    # Community usage is weak evidence of quality, worth a nudge and no more.
    return score


def prerank(target, voices: list[MeasuredVoice], *, limit: int = PRERANK_POOL) -> list[MeasuredVoice]:
    ranked = sorted(voices, key=lambda voice: -metadata_score(target, voice))
    return ranked[:limit]


def measure_many(voices: list[MeasuredVoice]) -> list[MeasuredVoice]:
    for index, voice in enumerate(voices, start=1):
        if voice.measurement == "measured":
            continue
        measure_preview(voice)
        log.info("[%d/%d] %s -> %s (%s)", index, len(voices), voice.name,
                 f"{voice.pitch_hz:.0f}Hz" if voice.pitch_hz else "—", voice.measurement)
    return voices


async def gather_all(
    provider,
    *,
    include_shared: bool = False,
    language: str = "en",
    max_shared: int = 1500,
) -> list[MeasuredVoice]:
    """Metadata for every reachable voice: the account's, plus the shared library."""
    account = [parse_voice(entry) for entry in await provider.list_voices()
               if entry.get("voice_id")]
    log.info("account voices: %d", len(account))

    shared: list[MeasuredVoice] = []
    if include_shared and hasattr(provider, "list_shared_voices"):
        entries = await provider.list_shared_voices(
            language=language, max_voices=max_shared
        )
        seen = {voice.voice_id for voice in account}
        shared = [
            parse_voice(entry) for entry in entries
            if entry.get("voice_id") and entry["voice_id"] not in seen
        ]
        log.info("shared library voices: %d", len(shared))

    return account + shared
