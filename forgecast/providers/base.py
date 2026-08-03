"""Provider contracts.

Every external model vendor is reduced to one of five capabilities. Nodes depend
only on these abstract classes, never on a vendor SDK — that is what lets a shot
be routed to Runway today and Kling tomorrow without touching pipeline code, and
what lets the entire graph run offline against `mock`.

Each call reports its own `credits` cost so billing reflects what actually
happened rather than what was estimated.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


class ProviderError(RuntimeError):
    """Vendor call failed in a way the node should surface, not swallow."""

    def __init__(self, message: str, *, provider: str = "", retryable: bool = False) -> None:
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable


class ProviderTimeout(ProviderError):
    def __init__(self, message: str, *, provider: str = "") -> None:
        super().__init__(message, provider=provider, retryable=True)


class Capability(str, enum.Enum):
    llm = "llm"
    voice = "voice"
    image = "image"
    video = "video"
    avatar = "avatar"
    # Sound design: the music bed under the narration, and the effects on top of it.
    # Separate from `voice` because a vendor can serve one and not the other, and
    # because a run with no music provider must still narrate rather than fail.
    music = "music"


@dataclass
class TextResult:
    text: str
    credits: int = 0
    provider: str = ""
    model: str = ""
    meta: dict = field(default_factory=dict)


@dataclass
class MediaResult:
    path: Path
    mime: str
    credits: int = 0
    provider: str = ""
    duration_seconds: float = 0.0
    meta: dict = field(default_factory=dict)

    @property
    def size_bytes(self) -> int:
        return self.path.stat().st_size if self.path.exists() else 0


@dataclass
class Stem:
    """One isolated layer of a track, as the vendor supplies it.

    `kind` is the vendor's own stem name — DRUMS, BASS, MELODY, INSTRUMENTS,
    CLEAN_VOCALS, VOCALS. Worth a type of its own because dropping the vocal stem is how
    a bed stops competing with narration, and that is a choice made per shot rather than
    a property of the search.
    """

    kind: str
    duration_seconds: float = 0.0
    preview_url: str = ""

    def as_dict(self) -> dict:
        return {"kind": self.kind, "seconds": round(self.duration_seconds, 2)}


@dataclass
class MusicTrack:
    """A candidate bed. Carries the numbers an edit decision needs, not just a title."""

    track_id: str
    title: str
    artists: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    # Beats per minute, and it must survive the adapter. The storyboard maths for a
    # beat-locked cut is `bar = 60 / bpm * 4`, so dropping this field turns a cut that
    # can land on a bar into one that lands wherever the scene happened to end.
    bpm: int = 0
    moods: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    stems: list[Stem] = field(default_factory=list)
    has_vocals: bool = False
    # Low-quality mp3, for auditioning and for measurement only. Never rendered with —
    # see the adapter, which keeps the render path on the download asset.
    preview_url: str = ""
    waveform_url: str = ""
    cover_url: str = ""
    provider: str = ""

    @property
    def bar_seconds(self) -> float:
        """One bar in 4/4 at this tempo, or 0 when the tempo is unknown."""
        return round(240.0 / self.bpm, 4) if self.bpm else 0.0

    @property
    def instrumental_stem(self) -> str:
        """The stem to use under narration, if the vendor separated one.

        A bed that keeps its lead vocal competes with the voiceover for the same
        frequencies, and no amount of ducking fixes two people talking at once.
        """
        available = {stem.kind.upper() for stem in self.stems}
        for candidate in ("INSTRUMENTS", "MELODY"):
            if candidate in available:
                return candidate
        return ""

    def as_dict(self) -> dict:
        return {
            "track_id": self.track_id,
            "title": self.title,
            "artists": self.artists,
            "seconds": round(self.duration_seconds, 2),
            "bpm": self.bpm,
            "bar_seconds": self.bar_seconds,
            "moods": self.moods,
            "genres": self.genres,
            "has_vocals": self.has_vocals,
            "stems": [stem.kind for stem in self.stems],
            "instrumental_stem": self.instrumental_stem,
            "provider": self.provider,
        }


@dataclass
class SoundEffectAsset:
    effect_id: str
    title: str
    duration_seconds: float = 0.0
    tags: list[str] = field(default_factory=list)
    preview_url: str = ""
    provider: str = ""

    def as_dict(self) -> dict:
        return {"effect_id": self.effect_id, "title": self.title,
                "seconds": round(self.duration_seconds, 2), "tags": self.tags,
                "provider": self.provider}


class BaseProvider(ABC):
    name: str = "base"
    capability: Capability

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key

    def _require_key(self) -> str:
        if not self.api_key:
            raise ProviderError(f"no API key configured for {self.name}", provider=self.name)
        return self.api_key


class LLMProvider(BaseProvider):
    capability = Capability.llm

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        json_object: bool = False,
        schema_name: str = "",
    ) -> TextResult:
        """Return model text. When `json_object` is set, the text must parse as JSON.

        `schema_name` names the expected shape ("brief", "script", …). Live adapters
        may use it to request structured output; the mock adapter uses it to pick a
        fixture generator.
        """


class VoiceProvider(BaseProvider):
    capability = Capability.voice

    @abstractmethod
    async def synthesize(
        self, text: str, *, voice_id: str, out_path: Path, speed: float = 1.0
    ) -> MediaResult:
        """Render narration to an audio file."""


class ImageProvider(BaseProvider):
    capability = Capability.image

    @abstractmethod
    async def generate(
        self, prompt: str, *, out_path: Path, width: int = 1280, height: int = 720
    ) -> MediaResult:
        """Render a still (thumbnails, B-roll plates)."""


class VideoProvider(BaseProvider):
    capability = Capability.video

    @abstractmethod
    async def generate_clip(
        self,
        prompt: str,
        *,
        out_path: Path,
        seconds: float = 5.0,
        width: int = 1280,
        height: int = 720,
        image_path: Path | None = None,
    ) -> MediaResult:
        """Render one B-roll shot, optionally animating a still."""


class MusicProvider(BaseProvider):
    capability = Capability.music

    @abstractmethod
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
        """Find candidate beds. Returns what the vendor actually holds, never invented."""

    @abstractmethod
    async def make_bed(
        self,
        track_id: str,
        *,
        out_path: Path,
        seconds: float,
        stem: str = "",
        hit_points: tuple[tuple[float, float, float], ...] = (),
    ) -> MediaResult:
        """Produce a bed of exactly `seconds` from one track.

        `stem` names a layer to isolate ("INSTRUMENTS") or is empty for the full mix.
        `hit_points` are `(start_seconds, end_seconds, offset_seconds)` triples: a region
        of the source that must land at a given moment of the output — the mechanism for
        putting a musical change on a reveal instead of near it.
        """

    @abstractmethod
    async def search_sound_effects(
        self, *, term: str = "", tags: tuple[str, ...] = (),
        seconds_max: float = 0.0, limit: int = 10,
    ) -> list[SoundEffectAsset]:
        """Find sound effects by description or tag."""

    @abstractmethod
    async def fetch_sound_effect(self, effect_id: str, *, out_path: Path) -> MediaResult:
        """Download one effect as a renderable file, not a preview."""


class AvatarProvider(BaseProvider):
    capability = Capability.avatar

    @abstractmethod
    async def generate(
        self, *, audio_path: Path, avatar_id: str, out_path: Path, width: int = 1280,
        height: int = 720,
    ) -> MediaResult:
        """Render a talking-head pass lip-synced to narration audio."""
