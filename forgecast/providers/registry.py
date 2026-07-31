"""Provider resolution.

Two questions this answers, and nothing else:
  1. Which vendor serves a capability for this run?
  2. Whose key pays for it — the user's, or the platform's?

Order of preference: an explicit per-run/channel override, then the user's own key
(bring-your-own-key users should always spend their own quota), then the platform
key. In `mock` mode nothing else applies: every capability resolves to the offline
provider, so no code path can accidentally spend money in development.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..crypto import decrypt
from ..models import ProviderKey, User
from .base import (
    AvatarProvider,
    Capability,
    ImageProvider,
    LLMProvider,
    ProviderError,
    VideoProvider,
    VoiceProvider,
)
from .llm import AnthropicProvider, OpenAIProvider
from .media import (
    ElevenLabsProvider,
    FalImageProvider,
    FalVideoProvider,
    HeyGenAvatarProvider,
    RunwayVideoProvider,
)
from .mock import MockAvatar, MockImage, MockLLM, MockVideo, MockVoice

# vendor name -> (capability, class, env/key name)
CATALOGUE: dict[str, tuple[Capability, type, str]] = {
    "openai": (Capability.llm, OpenAIProvider, "openai"),
    "anthropic": (Capability.llm, AnthropicProvider, "anthropic"),
    "elevenlabs": (Capability.voice, ElevenLabsProvider, "elevenlabs"),
    "fal": (Capability.image, FalImageProvider, "fal"),
    "fal-video": (Capability.video, FalVideoProvider, "fal"),
    "runway": (Capability.video, RunwayVideoProvider, "runway"),
    "heygen": (Capability.avatar, HeyGenAvatarProvider, "heygen"),
}

# Tried in order when no override is set. First one with a usable key wins.
DEFAULT_ROUTING: dict[Capability, list[str]] = {
    Capability.llm: ["anthropic", "openai"],
    Capability.voice: ["elevenlabs"],
    Capability.image: ["fal"],
    Capability.video: ["fal-video", "runway"],
    Capability.avatar: ["heygen"],
}

MOCKS: dict[Capability, type] = {
    Capability.llm: MockLLM,
    Capability.voice: MockVoice,
    Capability.image: MockImage,
    Capability.video: MockVideo,
    Capability.avatar: MockAvatar,
}


@dataclass
class ProviderRegistry:
    mode: str = "mock"
    user_keys: dict[str, str] = field(default_factory=dict)
    overrides: dict[str, str] = field(default_factory=dict)  # capability value -> vendor
    _cache: dict[str, object] = field(default_factory=dict, repr=False)

    # -- key resolution ---------------------------------------------------------

    def key_for(self, key_name: str) -> str:
        return self.user_keys.get(key_name) or get_settings().platform_key(key_name)

    def key_owner(self, key_name: str) -> str:
        return "user" if self.user_keys.get(key_name) else "platform"

    # -- capability resolution --------------------------------------------------

    def resolve(self, capability: Capability):
        if self.mode == "mock":
            return self._cached(f"mock:{capability.value}", MOCKS[capability])

        preferred = self.overrides.get(capability.value)
        candidates = [preferred] if preferred else []
        candidates += [v for v in DEFAULT_ROUTING.get(capability, []) if v != preferred]

        tried: list[str] = []
        for vendor in candidates:
            entry = CATALOGUE.get(vendor)
            if entry is None:
                continue
            cap, cls, key_name = entry
            if cap is not capability:
                continue
            api_key = self.key_for(key_name)
            tried.append(vendor)
            if api_key:
                return self._cached(f"{vendor}", cls, api_key)

        raise ProviderError(
            f"no usable {capability.value} provider: tried {tried or candidates} "
            "and none had an API key. Add one under Settings → Provider keys, "
            "or run with FORGECAST_PROVIDER_MODE=mock."
        )

    def _cached(self, cache_key: str, cls: type, *args):
        if cache_key not in self._cache:
            self._cache[cache_key] = cls(*args)
        return self._cache[cache_key]

    # -- typed accessors --------------------------------------------------------

    def llm(self) -> LLMProvider:
        return self.resolve(Capability.llm)  # type: ignore[return-value]

    def voice(self) -> VoiceProvider:
        return self.resolve(Capability.voice)  # type: ignore[return-value]

    def image(self) -> ImageProvider:
        return self.resolve(Capability.image)  # type: ignore[return-value]

    def video(self) -> VideoProvider:
        return self.resolve(Capability.video)  # type: ignore[return-value]

    def avatar(self) -> AvatarProvider:
        return self.resolve(Capability.avatar)  # type: ignore[return-value]


def registry_for(
    session: Session, user: User | int, *, overrides: dict[str, str] | None = None
) -> ProviderRegistry:
    """Build a registry carrying this user's bring-your-own keys."""
    settings = get_settings()
    user_id = user.id if isinstance(user, User) else int(user)

    user_keys: dict[str, str] = {}
    if not settings.is_mock:
        rows = session.execute(
            select(ProviderKey).where(ProviderKey.user_id == user_id)
        ).scalars().all()
        for row in rows:
            try:
                user_keys[row.provider] = decrypt(row.ciphertext)
            except Exception:  # a rotated encryption key must not break the run
                continue

    return ProviderRegistry(
        mode=settings.provider_mode, user_keys=user_keys, overrides=overrides or {}
    )
