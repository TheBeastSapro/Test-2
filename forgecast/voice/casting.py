"""Voice casting: derive a target from the reference, then shortlist and audition.

The rule this module enforces: **never silently pick a voice.** Voice is the most
audible choice in a faceless video and the one an operator has the strongest opinion
about, so the system proposes a ranked shortlist with reasons and audition samples,
and a human decides at a gate.

Ranking runs on measurements wherever it can. The reference's median pitch comes from
its audio; each candidate's pitch comes from its own preview clip, analysed with the
same estimator. That means the central comparison is measured-against-measured on one
scale, rather than a measurement against an adjective.

Where the vendor supplies only words — `use_case`, `descriptive`, the descriptors in a
voice's title — those are used as vendor characterisation and labelled as such. And
where the reference gives no signal, the candidate says so instead of manufacturing a
justification: a confident reason for an arbitrary pick is worse than an admitted default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .catalogue import STOCK_VOICES, CatalogueVoice, pitch_distance
from .discover import MeasuredVoice, load_catalogue

# Speaking-rate bands, from the WPM measurement where a transcript exists.
PACE_BANDS = ((110, "slow"), (150, "measured"), (180, "brisk"), (210, "fast"))

# Use cases that suit a given register, for scoring the vendor's own label.
REGISTER_USE_CASES = {
    "documentary": ("narrative_story", "informative_educational", "entertainment_tv"),
    "explainer": ("informative_educational", "conversational"),
    "history": ("narrative_story", "informative_educational"),
    "shorts": ("social_media", "conversational"),
    "narration": ("narrative_story", "informative_educational"),
    "news": ("news", "informative_educational"),
    "advertisement": ("advertisement",),
}


@dataclass
class VoiceTarget:
    """What we are casting toward, and how confident each part is."""

    pitch_band: str | None = None
    pitch_hz: float | None = None
    pace: str | None = None
    words_per_minute: float | None = None
    energy: str | None = None
    accent: str | None = None
    register: str | None = None
    evidence: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "pitch_band": self.pitch_band,
            "pitch_hz": round(self.pitch_hz, 1) if self.pitch_hz else None,
            "pace": self.pace,
            "words_per_minute": (
                round(self.words_per_minute, 1) if self.words_per_minute else None
            ),
            "energy": self.energy,
            "accent": self.accent,
            "register": self.register,
            "evidence": self.evidence,
            "gaps": self.gaps,
        }


@dataclass
class VoiceCandidate:
    name: str
    score: float
    reasons: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    voice_id: str | None = None
    sample_path: str | None = None
    catalogue: CatalogueVoice | None = None
    measured: MeasuredVoice | None = None

    @property
    def pitch_band(self) -> str | None:
        if self.measured:
            return self.measured.pitch_band
        return self.catalogue.pitch_band if self.catalogue else None

    def as_dict(self) -> dict:
        payload = {
            "name": self.name,
            "score": round(self.score, 3),
            "reasons": self.reasons,
            "caveats": self.caveats,
            "voice_id": self.voice_id,
            "sample_path": self.sample_path,
        }
        if self.measured:
            payload["profile"] = self.measured.as_dict()
            payload["source"] = "measured_from_account"
        elif self.catalogue:
            payload["profile"] = self.catalogue.as_dict()
            payload["source"] = "static_catalogue"
        return payload


def pace_band(words_per_minute: float | None) -> str | None:
    if not words_per_minute:
        return None
    for threshold, name in PACE_BANDS:
        if words_per_minute < threshold:
            return name
    return "very_fast"


def target_from_reference(
    style_profile: dict | None = None,
    *,
    words_per_minute: float | None = None,
    register: str | None = None,
    accent: str | None = None,
) -> VoiceTarget:
    """Build a casting target from a measured StyleProfile (and optional WPM)."""
    target = VoiceTarget(register=register, accent=accent)
    audio = ((style_profile or {}).get("audio")) or {}

    pitch_hz = audio.get("pitch_hz")
    voiced_ratio = audio.get("voiced_ratio") or 0.0
    # A low voiced ratio means the pitch came from very little speech — a music bed
    # or click track reports a confident f0 that means nothing.
    if pitch_hz and voiced_ratio >= 0.25:
        target.pitch_hz = float(pitch_hz)
        target.pitch_band = audio.get("pitch_band")
        target.evidence.append(
            f"reference speaks at ~{float(pitch_hz):.0f}Hz median "
            f"({target.pitch_band} band, {voiced_ratio:.0%} of frames voiced)"
        )
    elif pitch_hz:
        target.gaps.append(
            f"pitch measured at {float(pitch_hz):.0f}Hz but only {voiced_ratio:.0%} of "
            "frames were voiced — too little speech to cast against, so pitch is ignored"
        )
    else:
        target.gaps.append("no pitch could be measured from the reference audio")

    if words_per_minute:
        target.words_per_minute = words_per_minute
        target.pace = pace_band(words_per_minute)
        target.evidence.append(
            f"reference narration runs {words_per_minute:.0f} WPM ({target.pace})"
        )
    else:
        target.gaps.append("no transcript, so speaking rate is unknown")

    silence = audio.get("silence_ratio")
    if silence is not None:
        if silence < 0.08:
            target.energy = "energetic"
            target.evidence.append(
                f"almost no silence ({silence:.0%}) — wall-to-wall delivery"
            )
        elif silence > 0.30:
            target.energy = "calm"
            target.evidence.append(f"{silence:.0%} silence — deliberate, paced delivery")
        else:
            target.energy = "measured"

    loudness_range = audio.get("dynamic_range_db")
    if loudness_range and loudness_range > 40:
        target.evidence.append(
            f"wide dynamic range ({loudness_range:.0f}dB) — expressive rather than flat"
        )

    rhythm = (style_profile or {}).get("shot_rhythm") or {}
    cuts = rhythm.get("cuts_per_minute")
    if cuts and cuts > 30 and target.energy in (None, "measured"):
        target.energy = "energetic"
        target.evidence.append(f"{cuts:.0f} cuts/min — the edit implies an energetic read")

    return target


# --------------------------------------------------------------------- shortlist


def _score_measured(target: VoiceTarget, voice: MeasuredVoice) -> tuple[float, list, list]:
    score = 0.0
    reasons: list[str] = []
    caveats: list[str] = []

    # Measured-against-measured: the strongest comparison available.
    if target.pitch_hz and voice.pitch_hz:
        difference = abs(target.pitch_hz - voice.pitch_hz)
        if difference <= 12:
            score += 4.0
            reasons.append(
                f"pitch within {difference:.0f}Hz of the reference "
                f"({voice.pitch_hz:.0f}Hz vs {target.pitch_hz:.0f}Hz)"
            )
        elif difference <= 30:
            score += 2.5
            reasons.append(
                f"pitch {difference:.0f}Hz from the reference ({voice.pitch_hz:.0f}Hz)"
            )
        elif difference <= 60:
            score += 0.5
            caveats.append(f"pitch {difference:.0f}Hz from the reference")
        else:
            caveats.append(
                f"pitch {difference:.0f}Hz from the reference — a clearly different voice"
            )
    elif not target.pitch_hz:
        caveats.append("no reference pitch to compare against")
    elif not voice.pitch_hz:
        caveats.append(f"this voice's pitch could not be measured ({voice.measurement})")

    if target.energy and voice.energy == target.energy:
        score += 1.5
        reasons.append(f"vendor labels suggest a {voice.energy} read, matching the reference")
    elif target.energy and (target.energy, voice.energy) in {
        ("calm", "energetic"), ("energetic", "calm")
    }:
        score -= 1.0
        caveats.append(f"labelled {voice.energy} against a {target.energy} reference")

    if target.register:
        wanted = REGISTER_USE_CASES.get(target.register.lower(), ())
        if voice.use_case and voice.use_case in wanted:
            score += 1.5
            reasons.append(f"vendor use case is {voice.use_case}, suited to {target.register}")

    if target.pace in {"brisk", "fast", "very_fast"} and voice.energy == "energetic":
        score += 0.75
        reasons.append("labelled energetic, which holds up at the reference's speaking rate")
    if target.pace == "slow" and voice.energy in {"calm", "measured"}:
        score += 0.75
        reasons.append("suits a slow, deliberate read")

    if target.accent:
        wanted = target.accent.lower()
        if voice.accent and wanted in voice.accent.lower():
            score += 1.0
            reasons.append(f"{voice.accent} accent as requested")
        elif voice.accent:
            score -= 0.5
            caveats.append(f"{voice.accent} accent, not {target.accent}")

    # Ownership. A voice the operator cloned themselves is nearly always the right
    # answer when it also fits, so it outranks a marginally closer library match.
    ownership_bonus = {"own_clone": 3.0, "professional": 1.0, "stock": 0.0}.get(
        voice.ownership, 0.0
    )
    score += ownership_bonus
    if voice.ownership == "own_clone":
        reasons.insert(0, "your own cloned voice")
    elif voice.ownership == "professional":
        reasons.insert(0, "professional voice on your account")
    elif voice.ownership == "library":
        caveats.append(
            "from the public shared library rather than your account (usable directly)"
        )

    # Prefer a voice whose preview actually resolved over one that did not.
    if voice.measurement != "measured":
        score -= 0.5

    if not reasons:
        reasons.append("nothing in the reference favours or rules it out")
    return score, reasons, caveats


def _score_static(target: VoiceTarget, voice: CatalogueVoice) -> tuple[float, list, list]:
    score = 0.0
    reasons: list[str] = []
    caveats: list[str] = [
        "from the offline fallback catalogue — descriptors are approximate and the "
        "name may not exist on your account"
    ]

    distance = pitch_distance(target.pitch_band, voice.pitch_band)
    if distance == 0:
        score += 3.0
        reasons.append(f"same pitch band as the reference ({voice.pitch_band})")
    elif distance == 1:
        score += 1.5
        reasons.append(f"one band from the reference ({voice.pitch_band})")
    elif distance == 99:
        caveats.append("pitch could not be compared — reference gave no usable f0")
    else:
        caveats.append(
            f"{distance} bands from the reference ({voice.pitch_band} vs {target.pitch_band})"
        )

    if target.energy and voice.energy == target.energy:
        score += 2.0
        reasons.append(f"energy matches ({voice.energy})")
    elif target.energy and (target.energy, voice.energy) in {
        ("calm", "energetic"), ("energetic", "calm")
    }:
        score -= 1.0
        caveats.append(f"{voice.energy} read against a {target.energy} reference")

    if target.pace in {"brisk", "fast", "very_fast"} and voice.energy == "energetic":
        score += 1.0
        reasons.append("holds up at the reference's speaking rate")
    if target.pace == "slow" and voice.energy in {"calm", "measured"}:
        score += 1.0
        reasons.append("suits a slow, deliberate read")

    if target.register and target.register.lower() in {
        item.lower() for item in voice.best_for
    }:
        score += 1.5
        reasons.append(f"listed for {target.register}")

    if target.accent:
        if voice.accent == target.accent.lower():
            score += 1.0
            reasons.append(f"{voice.accent} accent as requested")
        else:
            score -= 0.5
            caveats.append(f"{voice.accent} accent, not {target.accent}")

    if not reasons:
        reasons.append("catalogue default — nothing in the reference favours it")
    return score, reasons, caveats


def shortlist(
    target: VoiceTarget,
    *,
    limit: int = 3,
    measured: list[MeasuredVoice] | None = None,
    cache_path: Path | None = None,
    catalogue: tuple[CatalogueVoice, ...] = STOCK_VOICES,
) -> list[VoiceCandidate]:
    """Rank voices against the target, highest first.

    Prefers the measured catalogue built from the account. Falls back to the static
    list only when no cache exists, and says so on every candidate — the static names
    are known to be stale against current ElevenLabs accounts.
    """
    if measured is None:
        measured = load_catalogue(cache_path)

    candidates: list[VoiceCandidate] = []
    if measured:
        for voice in measured:
            score, reasons, caveats = _score_measured(target, voice)
            candidates.append(
                VoiceCandidate(
                    name=voice.name, score=score, reasons=reasons, caveats=caveats,
                    voice_id=voice.voice_id, measured=voice,
                )
            )
    else:
        for entry in catalogue:
            score, reasons, caveats = _score_static(target, entry)
            candidates.append(
                VoiceCandidate(
                    name=entry.name, score=score, reasons=reasons,
                    caveats=caveats, catalogue=entry,
                )
            )

    candidates.sort(key=lambda item: (-item.score, item.name))
    top = candidates[: max(1, limit)]

    # Always include one voice that is *not* a close match. Casting purely on
    # similarity converges on the same three voices forever, and an operator often
    # wants to hear the alternative before rejecting it.
    if len(candidates) > limit:
        chosen = {entry.name for entry in top}
        contrast = next(
            (item for item in reversed(candidates) if item.name not in chosen), None
        )
        if contrast:
            contrast.caveats.insert(0, "included as a deliberate contrast, not a match")
            top.append(contrast)

    return top


def casting_summary(target: VoiceTarget, candidates: list[VoiceCandidate]) -> list[str]:
    """Human-readable lines for the gate."""
    lines: list[str] = []
    if target.evidence:
        lines.append("Cast from: " + "; ".join(target.evidence))
    if target.gaps:
        lines.append("Not measurable: " + "; ".join(target.gaps))

    using_measured = any(candidate.measured for candidate in candidates)
    lines.append(
        "Candidates ranked against pitch measured from each voice's own preview clip."
        if using_measured
        else "No account catalogue cached — ranking from the offline fallback list, "
             "whose names may not exist on your account. Run `forgecast-voice sync`."
    )

    for index, candidate in enumerate(candidates, start=1):
        pitch = ""
        if candidate.measured and candidate.measured.pitch_hz:
            pitch = f" [{candidate.measured.pitch_hz:.0f}Hz]"
        lines.append(f"{index}. {candidate.name}{pitch} — {'; '.join(candidate.reasons)}")
        for caveat in candidate.caveats:
            lines.append(f"     caveat: {caveat}")

    lines.append(
        "Listen to the samples before choosing. Pitch is measured, but everything else "
        "is the vendor's own characterisation, so the rankings narrow the field rather "
        "than settle it."
    )
    return lines
