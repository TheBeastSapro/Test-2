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
from .epidemic import EpidemicVoiceProvider, MockEpidemicVoice
from .higgsfield import HiggsfieldProvider
from .llm import AnthropicProvider, OpenAIProvider
from .llm_cli import ClaudeCliProvider
from .media import (
    ElevenLabsProvider,
    FalImageProvider,
    FalVideoProvider,
    HeyGenAvatarProvider,
    MiniMaxVoiceProvider,
    RunwayVideoProvider,
)
from .mock import MockAvatar, MockImage, MockLLM, MockVideo, MockVoice
from .stock import OpenverseProvider

# vendor name -> (capability, class, env/key name)
CATALOGUE: dict[str, tuple[Capability, type, str]] = {
    "openai": (Capability.llm, OpenAIProvider, "openai"),
    "anthropic": (Capability.llm, AnthropicProvider, "anthropic"),
    # Keyless options. The empty key name marks them as needing no credential, so
    # resolution treats them as always-available rather than always-unconfigured.
    "claude-cli": (Capability.llm, ClaudeCliProvider, ""),
    "openverse": (Capability.image, OpenverseProvider, ""),
    # Keyless here means "no ProviderKey row", not "no credential". Epidemic Sound's
    # credential is a *connector* — the agent's connector store, not the Settings key
    # table — so the adapter fetches its own and `available()` is what decides whether
    # this vendor can serve a run. Giving it a key name would have made the registry
    # look for an `epidemic` provider key that nothing ever writes.
    "epidemic-sound": (Capability.voice, EpidemicVoiceProvider, ""),
    "elevenlabs": (Capability.voice, ElevenLabsProvider, "elevenlabs"),
    "minimax-voice": (Capability.voice, MiniMaxVoiceProvider, "minimax"),
    "fal": (Capability.image, FalImageProvider, "fal"),
    # Its own key name, so it can never be satisfied by another vendor's credential.
    "higgsfield": (Capability.image, HiggsfieldProvider, "higgsfield"),
    "fal-video": (Capability.video, FalVideoProvider, "fal"),
    "runway": (Capability.video, RunwayVideoProvider, "runway"),
    "heygen": (Capability.avatar, HeyGenAvatarProvider, "heygen"),
}

# Tried in order when no override is set. First one with a usable key wins.
# Keyless providers sit last: a real API key means the operator chose that vendor, so
# it wins. But they are in the list, which is why a run with no keys at all still
# works instead of failing at the first node.
DEFAULT_ROUTING: dict[Capability, list[str]] = {
    Capability.llm: ["anthropic", "openai", "claude-cli"],
    # ElevenLabs first because a stored provider key means the operator chose it.
    # Epidemic Sound sits behind it for the same reason the keyless providers do: it is
    # there so an install with no ElevenLabs key still narrates instead of failing at
    # the voice node, not because it is the preferred vendor.
    #
    # `minimax-voice` is deliberately absent. It is a fully supported vendor and it wins
    # whenever a channel names it, but it must never be *fallen back* to: ElevenLabs
    # narration comes out of a subscription allowance already paid for, while MiniMax
    # narration draws down an API balance. Putting it in this list would mean a lapsed
    # ElevenLabs key silently moves someone's spend from a plan to a wallet, and the first
    # they hear of it is the balance.
    Capability.voice: ["elevenlabs", "epidemic-sound"],
    # `higgsfield` is deliberately absent, for the same reason as `minimax-voice`: it
    # bills per generation against its own credit balance, so it is chosen per channel and
    # never fallen back to. What it is *for* is identity that holds across shots and across
    # episodes, which is a decision about a channel's look rather than a way to make a
    # picture when fal is unavailable.
    Capability.image: ["fal", "openverse"],
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

# Vendor-shaped offline stand-ins, used in `mock` mode when an override names that vendor.
#
# The generic mock per capability is the right default, but it answers in one vendor's
# shape: `MockVoice.list_voices` mirrors the ElevenLabs catalogue. So the fields a
# different adapter maps — Epidemic Sound's `location`, `characteristics`, `languages` —
# were unreachable offline, which is to say untested and undemonstrable on a fresh
# install. Naming the vendor now gets that vendor's shapes, still with no network.
MOCK_VENDORS: dict[str, type] = {
    "epidemic-sound": MockEpidemicVoice,
}


def _availability(provider) -> tuple[bool, str]:
    """Is this provider usable, and if not, the sentence that says why.

    Two shapes are in the tree and both are legitimate: `ClaudeCliProvider.available()`
    returns a bool, and the connector-backed adapters return `(ok, why_not)` — the shape
    `research.keyless.available` established, because the reason is the useful half.

    Reading them the same way was a bug waiting to happen: `(False, "not connected")` is
    a non-empty tuple, so a plain truth test accepted an unusable provider and the run
    failed later at the vendor call with an error about a missing credential instead of
    falling through to the next vendor.
    """
    checker = getattr(provider, "available", None)
    if checker is None:
        return True, ""
    verdict = checker()
    if isinstance(verdict, tuple):
        ok = bool(verdict[0])
        return ok, "" if ok else str(verdict[1] if len(verdict) > 1 else "")
    return bool(verdict), "" if verdict else "reported itself unavailable"


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
        preferred = self.overrides.get(capability.value)

        if self.mode == "mock":
            stand_in = MOCK_VENDORS.get(preferred or "")
            if stand_in is not None:
                return self._cached(f"mock:{preferred}", stand_in)
            return self._cached(f"mock:{capability.value}", MOCKS[capability])

        candidates = [preferred] if preferred else []
        candidates += [v for v in DEFAULT_ROUTING.get(capability, []) if v != preferred]

        tried: list[str] = []
        # Why each candidate was passed over. Without these the failure said only that
        # nothing was usable, so an operator with a connector configured but disabled got
        # the same sentence as one who had configured nothing at all.
        refused: list[str] = []
        for vendor in candidates:
            entry = CATALOGUE.get(vendor)
            if entry is None:
                continue
            cap, cls, key_name = entry
            if cap is not capability:
                continue
            tried.append(vendor)

            if not key_name:
                # No provider key. Most still have a precondition — the CLI has to be
                # installed, the connector has to be connected — so ask before handing
                # it back.
                candidate = self._cached(f"{vendor}", cls)
                usable, reason = _availability(candidate)
                if usable:
                    return candidate
                if reason:
                    refused.append(f"{vendor}: {reason}")
                continue

            api_key = self.key_for(key_name)
            if api_key:
                return self._cached(f"{vendor}", cls, api_key)
            refused.append(f"{vendor}: no {key_name} key configured")

        detail = (" " + " ".join(refused)) if refused else ""
        raise ProviderError(
            f"no usable {capability.value} provider: tried {tried or candidates} "
            f"and none was usable.{detail} Add a key under Settings → Provider keys, or "
            "run with FORGECAST_PROVIDER_MODE=mock."
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
