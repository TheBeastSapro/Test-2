"""Voice casting: derive a target from the reference, then shortlist and audition.

The rule this module exists to enforce: **never silently pick a voice.** Voice is the
single most audible choice in a faceless video and the one an operator has the
strongest opinion about, so the system proposes a ranked shortlist with reasons and
audition samples, and a human decides at a gate.

Ranking is driven by what was actually measured off the reference audio — median
pitch, speaking rate, energy, silence — not by adjectives. Where the reference gives
no signal, the candidate says so rather than inventing a justification, because a
confident-sounding reason for an arbitrary pick is worse than admitting the pick is a
default.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .catalogue import STOCK_VOICES, CatalogueVoice, pitch_distance

# Speaking-rate bands, from vision.audio's WPM measurement where a transcript exists.
PACE_BANDS = ((110, "slow"), (150, "measured"), (180, "brisk"), (210, "fast"))


@dataclass
class VoiceTarget:
    """What we are casting toward, and how confident each part is."""

    pitch_band: str | None = None
    pitch_hz: float | None = None
    pace: str | None = None
    words_per_minute: float | None = None
    energy: str | None = None
    accent: str | None = None
    register: str | None = None          # from the channel/style, e.g. "documentary"
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
    voice_id: str | None = None          # resolved at synthesis time
    sample_path: str | None = None
    catalogue: CatalogueVoice | None = None

    def as_dict(self) -> dict:
        payload = {
            "name": self.name,
            "score": round(self.score, 3),
            "reasons": self.reasons,
            "caveats": self.caveats,
            "voice_id": self.voice_id,
            "sample_path": self.sample_path,
        }
        if self.catalogue:
            payload["profile"] = self.catalogue.as_dict()
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
    # A low voiced ratio means the pitch reading came from very little speech —
    # a music bed or a click track will happily report a confident f0.
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
        target.evidence.append(f"reference narration runs {words_per_minute:.0f} WPM "
                               f"({target.pace})")
    else:
        target.gaps.append("no transcript, so speaking rate is unknown")

    silence = audio.get("silence_ratio")
    loudness_range = audio.get("dynamic_range_db")
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
    if loudness_range and loudness_range > 40:
        target.evidence.append(
            f"wide dynamic range ({loudness_range:.0f}dB) — expressive rather than flat"
        )

    # A fast, hard-cut edit wants a voice that can keep up; the edit is evidence
    # about delivery even when the audio is inconclusive.
    rhythm = (style_profile or {}).get("shot_rhythm") or {}
    cuts = rhythm.get("cuts_per_minute")
    if cuts and cuts > 30 and target.energy in (None, "measured"):
        target.energy = "energetic"
        target.evidence.append(
            f"{cuts:.0f} cuts/min — the edit implies an energetic read"
        )

    return target


def shortlist(
    target: VoiceTarget,
    *,
    limit: int = 3,
    catalogue: tuple[CatalogueVoice, ...] = STOCK_VOICES,
) -> list[VoiceCandidate]:
    """Rank catalogue voices against the target. Highest score first."""
    candidates: list[VoiceCandidate] = []

    for voice in catalogue:
        score = 0.0
        reasons: list[str] = []
        caveats: list[str] = []

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
                f"{distance} bands from the reference ({voice.pitch_band} vs "
                f"{target.pitch_band})"
            )

        if target.energy and voice.energy == target.energy:
            score += 2.0
            reasons.append(f"energy matches ({voice.energy})")
        elif target.energy:
            # Calm against energetic is a real mismatch; the adjacent pairs are not.
            opposed = {("calm", "energetic"), ("energetic", "calm")}
            if (target.energy, voice.energy) in opposed:
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

        candidates.append(
            VoiceCandidate(
                name=voice.name, score=score, reasons=reasons,
                caveats=caveats, catalogue=voice,
            )
        )

    candidates.sort(key=lambda item: (-item.score, item.name))
    top = candidates[: max(1, limit)]

    # Deliberately include one voice that is *not* a close match. Casting purely on
    # similarity converges on the same three voices forever, and the operator often
    # wants to hear the alternative before rejecting it.
    if len(candidates) > limit:
        contrast = next(
            (item for item in reversed(candidates)
             if item.name not in {entry.name for entry in top}),
            None,
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
    for index, candidate in enumerate(candidates, start=1):
        detail = "; ".join(candidate.reasons)
        lines.append(f"{index}. {candidate.name} — {detail}")
        for caveat in candidate.caveats:
            lines.append(f"     caveat: {caveat}")
    lines.append(
        "Listen to the samples before choosing. The rankings come from approximate "
        "catalogue descriptors, so they narrow the field rather than settle it."
    )
    return lines
