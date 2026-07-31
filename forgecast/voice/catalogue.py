"""A starting catalogue of ElevenLabs stock voices.

**Voice IDs are deliberately absent.** They are resolved by name against
`GET /v1/voices` at runtime. Hard-coding IDs would mean shipping strings that cannot
be verified from here and that rotate per account anyway — a wrong ID fails at
synthesis time with an opaque error, whereas a name that cannot be resolved fails
immediately and says which name it was.

The descriptors below are approximate, and the design accounts for that: they exist
only to *rank* candidates so the operator gets a shortlist instead of ninety options.
The audition sample is what actually decides, which is why casting always produces
samples and always ends at a human choice. Nothing here should be presented to a user
as a measured fact about how a voice sounds.

Pitch bands use the same thresholds as `vision.audio`: low <110Hz, low_mid <165,
mid <215, high >=215. They describe frequency only.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CatalogueVoice:
    name: str
    pitch_band: str
    accent: str
    energy: str                      # calm | measured | warm | energetic
    texture: str                     # clean | breathy | gravelly | bright
    best_for: tuple[str, ...] = ()
    notes: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "pitch_band": self.pitch_band,
            "accent": self.accent,
            "energy": self.energy,
            "texture": self.texture,
            "best_for": list(self.best_for),
            "notes": self.notes,
        }


# Stock voices available on essentially every ElevenLabs account. Kept short on
# purpose — a shortlist the operator will actually audition beats an exhaustive list
# they will scroll past.
STOCK_VOICES: tuple[CatalogueVoice, ...] = (
    CatalogueVoice(
        name="Rachel", pitch_band="mid", accent="american", energy="calm",
        texture="clean", best_for=("narration", "explainer", "documentary"),
        notes="Neutral and unobtrusive; a safe default when the reference voice is "
              "steady rather than characterful.",
    ),
    CatalogueVoice(
        name="Adam", pitch_band="low", accent="american", energy="measured",
        texture="clean", best_for=("documentary", "narration", "trailer"),
        notes="Deep and even. Suits slow, authoritative delivery.",
    ),
    CatalogueVoice(
        name="Antoni", pitch_band="low_mid", accent="american", energy="warm",
        texture="clean", best_for=("narration", "storytelling"),
        notes="Warmer than Adam and less formal; good for first-person scripts.",
    ),
    CatalogueVoice(
        name="Josh", pitch_band="low", accent="american", energy="measured",
        texture="clean", best_for=("documentary", "explainer"),
        notes="Younger-reading low voice; less gravity than Adam.",
    ),
    CatalogueVoice(
        name="Arnold", pitch_band="low_mid", accent="american", energy="energetic",
        texture="clean", best_for=("hype", "shorts", "sports"),
        notes="Forward and punchy. Fits fast cutting and high-energy hooks.",
    ),
    CatalogueVoice(
        name="Bella", pitch_band="high", accent="american", energy="warm",
        texture="breathy", best_for=("storytelling", "lifestyle", "shorts"),
        notes="Soft and close-mic'd in character; carries intimacy better than pace.",
    ),
    CatalogueVoice(
        name="Elli", pitch_band="high", accent="american", energy="energetic",
        texture="bright", best_for=("shorts", "lifestyle", "explainer"),
        notes="Bright and quick; pairs with fast, caption-heavy edits.",
    ),
    CatalogueVoice(
        name="Domi", pitch_band="mid", accent="american", energy="energetic",
        texture="clean", best_for=("explainer", "shorts", "hype"),
        notes="Assertive mid-range; holds up against a loud music bed.",
    ),
    CatalogueVoice(
        name="Sam", pitch_band="low_mid", accent="american", energy="measured",
        texture="clean", best_for=("narration", "explainer"),
        notes="Plain and conversational; recedes behind the information.",
    ),
    CatalogueVoice(
        name="Charlotte", pitch_band="mid", accent="british", energy="calm",
        texture="clean", best_for=("documentary", "history", "narration"),
        notes="Non-American option; suits documentary and history registers.",
    ),
    CatalogueVoice(
        name="Daniel", pitch_band="low", accent="british", energy="measured",
        texture="clean", best_for=("documentary", "news", "history"),
        notes="Formal British read; the closest stock voice to a broadcast narrator.",
    ),
)


def by_name(name: str) -> CatalogueVoice | None:
    lowered = name.strip().lower()
    return next((voice for voice in STOCK_VOICES if voice.name.lower() == lowered), None)


PITCH_ORDER = ("low", "low_mid", "mid", "high")


def pitch_distance(left: str | None, right: str | None) -> int:
    """How many bands apart two pitch descriptions are; 99 when either is unknown."""
    if not left or not right:
        return 99
    try:
        return abs(PITCH_ORDER.index(left) - PITCH_ORDER.index(right))
    except ValueError:
        return 99
