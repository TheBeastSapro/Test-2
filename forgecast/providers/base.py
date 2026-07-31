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


class AvatarProvider(BaseProvider):
    capability = Capability.avatar

    @abstractmethod
    async def generate(
        self, *, audio_path: Path, avatar_id: str, out_path: Path, width: int = 1280,
        height: int = 720,
    ) -> MediaResult:
        """Render a talking-head pass lip-synced to narration audio."""
