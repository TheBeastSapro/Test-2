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

import inspect
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
    MusicProvider,
    ProviderError,
    VideoProvider,
    VoiceProvider,
)
from .epidemic import (
    EpidemicMusicProvider,
    EpidemicVoiceProvider,
    MockEpidemicMusic,
    MockEpidemicVoice,
)
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
from .minimax_cli import MiniMaxCliVoiceProvider
from .mock import MockAvatar, MockImage, MockLLM, MockVideo, MockVoice
from .pollinations import PollinationsProvider
from .stock import OpenverseProvider

# vendor name -> (capability, class, env/key name)
CATALOGUE: dict[str, tuple[Capability, type, str]] = {
    "openai": (Capability.llm, OpenAIProvider, "openai"),
    "anthropic": (Capability.llm, AnthropicProvider, "anthropic"),
    # Keyless options. The empty key name marks them as needing no credential, so
    # resolution treats them as always-available rather than always-unconfigured.
    "claude-cli": (Capability.llm, ClaudeCliProvider, ""),
    "openverse": (Capability.image, OpenverseProvider, ""),
    # Keyless in the strongest sense in this table: no key, no connector, no account, no
    # billing relationship. It is the only entry that lets a fresh install render an
    # image on its first run, and the only one whose result costs literally nothing.
    "pollinations": (Capability.image, PollinationsProvider, ""),
    # Keyless here means "no ProviderKey row", not "no credential". Epidemic Sound's
    # credential is a *connector* — the agent's connector store, not the Settings key
    # table — so the adapter fetches its own and `available()` is what decides whether
    # this vendor can serve a run. Giving it a key name would have made the registry
    # look for an `epidemic` provider key that nothing ever writes.
    "epidemic-sound": (Capability.voice, EpidemicVoiceProvider, ""),
    # The same connector, the other half of the catalogue. A separate entry rather than
    # one adapter serving two capabilities, because `resolve` keys on capability and a
    # channel must be able to narrate on ElevenLabs while scoring on Epidemic — one entry
    # would have made those two decisions the same decision.
    "epidemic-music": (Capability.music, EpidemicMusicProvider, ""),
    "elevenlabs": (Capability.voice, ElevenLabsProvider, "elevenlabs"),
    "minimax-voice": (Capability.voice, MiniMaxVoiceProvider, "minimax"),
    # The same vendor, reached the other way. No key name, because this route takes no
    # key at all: it drives `mmx` signed in with the operator's subscription, so speech
    # comes out of the plan's quota instead of the API balance. Its `available()` is
    # what refuses it when the CLI is missing, not signed in, or signed in with a key —
    # that last case matters, because a key-authenticated CLI bills per character and
    # letting it through here would move spend while reporting the opposite.
    "minimax-voice-cli": (Capability.voice, MiniMaxCliVoiceProvider, ""),
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
    #
    # `minimax-voice-cli` is absent for a different reason, and the difference is worth
    # keeping straight. It spends nothing per character — it is quota inside a plan — so
    # it is not dangerous to fall back to on the grounds of cost. It is absent because
    # falling back to it would silently change which vendor's voice a channel is
    # narrated in, and a series whose narrator changes halfway through is a worse
    # outcome than a run that stops and says the ElevenLabs key has lapsed. Both MiniMax
    # routes are chosen, never inherited.
    Capability.voice: ["elevenlabs", "epidemic-sound"],
    # `higgsfield` is deliberately absent, for the same reason as `minimax-voice`: it
    # bills per generation against its own credit balance, so it is chosen per channel and
    # never fallen back to. What it is *for* is identity that holds across shots and across
    # episodes, which is a decision about a channel's look rather than a way to make a
    # picture when fal is unavailable.
    # Paid generation, then free generation, then stock search. Pollinations sits above
    # Openverse rather than below it because an image generated from the shot's own
    # prompt is more likely to be the right picture than a stock search for keywords from
    # it — `stock.py`'s own relaxation ladder documents serving "Blue Grass Chemical
    # Agent-Destruction" for a film about undersea cables. It costs nothing either way,
    # so the only thing traded is time: the free tier queues, and a long-form video on it
    # takes tens of minutes it would not take on fal.
    Capability.image: ["fal", "pollinations", "openverse"],
    Capability.video: ["fal-video", "runway"],
    Capability.avatar: ["heygen"],
    # Empty on purpose, and it is the only entry here that is. Every other capability has
    # a fallback because a run with no vendor for it produces no video at all; a run with
    # no music vendor produces a finished video with no music, which is a smaller loss
    # than the one this list would otherwise cause.
    #
    # `epidemic-music` is absent for both of the reasons `minimax-voice` and `higgsfield`
    # are, and they compound. It draws on something the operator pays for — a subscription
    # rather than a balance, but the direction is the same — so a channel that never asked
    # for music must not start spending it because a connector happened to be configured
    # for narration. And a download here is not only a cost: Epidemic's terms make
    # exporting a track into published content a reportable event, so a bed fetched by
    # fallback would put an untraceable track into a monetised render that nobody chose.
    # Music is chosen per channel and never inherited.
    Capability.music: [],
}

MOCKS: dict[Capability, type] = {
    Capability.llm: MockLLM,
    Capability.voice: MockVoice,
    Capability.image: MockImage,
    Capability.video: MockVideo,
    Capability.avatar: MockAvatar,
    # The only music vendor there is, so the generic stand-in and the vendor-shaped one
    # are the same class. It is still listed in both places: the day a second music vendor
    # arrives, this line is what says which shape "the generic music mock" means.
    Capability.music: MockEpidemicMusic,
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
    "epidemic-music": MockEpidemicMusic,
}


def _takes_model(cls: type) -> bool:
    """Does this adapter accept a model, as its second positional argument?

    Asked rather than assumed. Most adapters here take `(api_key, model)` — the fal video
    adapter serves six model families through one class — but several take only a key,
    and handing one of those a second argument is a TypeError several minutes into a run
    that has already paid for a script and a voiceover.
    """
    try:
        parameters = inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):  # pragma: no cover - builtins and C extensions
        return False
    return "model" in parameters


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
    # Capability value -> model slug, where the chosen vendor serves more than one model.
    # Separate from `overrides` because a vendor and a model are different decisions: one
    # fal key reaches Kling, Veo, Sora, WAN, LTX and Hailuo, and picking between those is
    # the choice that moves a video's cost from $15 to $98. Until this existed every
    # provider was built as `cls(api_key)` and the model catalogue beside it was
    # unreachable — a table nothing could read.
    models: dict[str, str] = field(default_factory=dict)
    _cache: dict[str, object] = field(default_factory=dict, repr=False)

    # -- key resolution ---------------------------------------------------------

    def key_for(self, key_name: str) -> str:
        return self.user_keys.get(key_name) or get_settings().platform_key(key_name)

    def key_owner(self, key_name: str) -> str:
        return "user" if self.user_keys.get(key_name) else "platform"

    # -- capability resolution --------------------------------------------------

    def resolve(self, capability: Capability, *, model: str = ""):
        """The provider for this capability, optionally pinned to one model.

        `model` is how a single run reaches two models at once, which is the shape
        image-to-video actually has: a plan routes its hero beats to one endpoint and the
        other seventy-five shots to another, and both are the same vendor on the same key.
        It overrides `self.models` rather than replacing it — the standing choice is still
        what an unpinned call gets — because a caller passing a slug has already decided
        something more specific than the channel did.

        Asking twice is cheap and correct: the cache is keyed on vendor *and* model, so
        the second model builds one more adapter and every later shot on either tier hits
        the cache.
        """
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
                wanted = model or self.models.get(capability.value, "")
                if wanted and _takes_model(cls):
                    # The model is in the cache key. Without it a second channel on the
                    # same vendor would be handed the first channel's provider and render
                    # on a model nobody chose — silently, and at the other model's price.
                    # It is also what lets one run hold a hero adapter and a batch adapter
                    # at the same time instead of the second overwriting the first.
                    return self._cached(f"{vendor}:{wanted}", cls, api_key, wanted)
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

    def video(self, model: str = "") -> VideoProvider:
        """The video provider, on `model` where a shot named one.

        The only typed accessor that takes a model, because video is the only capability
        where the model rather than the vendor is the expensive decision — one fal key
        reaches endpoints spanning $0.03 to $0.20 a second, and a shot list routes across
        two of them. Empty means the run's standing choice, so every caller that predates
        per-shot routing keeps getting exactly what it got.
        """
        return self.resolve(Capability.video, model=model)  # type: ignore[return-value]

    def avatar(self) -> AvatarProvider:
        return self.resolve(Capability.avatar)  # type: ignore[return-value]

    def music(self, vendor: str = "") -> MusicProvider:
        """The music vendor this channel chose. There is no default one.

        `vendor` is how a channel's choice reaches a capability that has no routing to
        fall back on — the caller passes what the channel or the run named, and with
        nothing named `DEFAULT_ROUTING` has nothing to offer and this raises rather than
        quietly picking a vendor that spends.

        `setdefault`, not assignment, so a per-run override still wins over the channel's
        standing choice. That is the same precedence the engine applies to narration, and
        for the same reason: "render this one with the other bed" is the more specific
        instruction and must not be silently ignored.
        """
        if vendor:
            self.overrides.setdefault(Capability.music.value, vendor)
        return self.resolve(Capability.music)  # type: ignore[return-value]


def registry_for(
    session: Session, user: User | int, *, overrides: dict[str, str] | None = None,
    models: dict[str, str] | None = None,
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
        mode=settings.provider_mode, user_keys=user_keys, overrides=overrides or {},
        models=models or {},
    )
