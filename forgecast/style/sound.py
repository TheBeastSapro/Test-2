"""Turning a reference video's measured audio into a sound-design brief.

## Why this module exists at all

`vision/audio.py` already measures a reference in detail — whether a music bed is there
and at what tempo, how loud the mix sits, how much of it is silence, how many onsets a
minute, and whether the cuts land on the beat. `vision/profile.py` stores every one of
those numbers on the `StyleProfile`.

And then nothing reads them. `snap_cuts_to_beat` reaches the render spec; the rest is
measured, written down, and ignored. So the app could already tell you that a reference
"runs a bed at 128 BPM, ducked hard, cuts locked to beat" and instead said nothing,
because there was no code between the measurement and a decision.

This is that code. It is deliberately *only* the recommendation: it reads numbers and
returns what to do about them, with the evidence attached. Acting on it is the render's
job, and keeping the two apart means the advice can be shown, argued with and overridden
before anything is bought.

## Why every field carries its evidence

A recommendation of "bed at 120-135 BPM" is worth nothing on its own — the operator
cannot tell whether it came from a measurement or from a default. So each decision names
the number behind it, and where there was no usable number it says so instead of
inventing a plausible one. A reference with no audible bed produces "no bed" with the
reason, not a made-up tempo.

## The one thing it will not do

It will not recommend copying a reference's loudness. Broadcast loudness is a delivery
target, not a style: YouTube normalises to roughly -14 LUFS on playback, so matching a
reference that was mastered at -9 buys nothing except a quieter video after
normalisation. What *is* style is the **relationship** between the bed and the voice —
how far the music sits under the narration — and that is what gets carried across.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Below this the tempo reading is a guess from too few onsets, and a bed bought to match
# it would be matched to noise. `vision/audio.py` grades its own confidence; this is the
# grade at which the number stops being usable.
USABLE_TEMPO = ("medium", "high")

# How far a bed sits under narration, in dB, when the reference cannot say. Measured
# convention for spoken-word video rather than a guess: enough that the voice is never
# competing, not so much that the music stops being present.
DEFAULT_DUCK_DB = 9.0

# A reference whose onsets-per-minute exceeds this is doing percussive sound design —
# hits, whooshes, stings — rather than running a bed under a voice. The distinction
# matters because the advice is completely different.
SFX_DENSE_PER_MINUTE = 40.0

# Under this fraction of silence a mix is wall-to-wall: there is no room for a sting to
# land, and recommending one produces clutter.
ROOM_FOR_ACCENTS = 0.08


@dataclass
class SoundBrief:
    """What to do about a reference's sound, and the numbers behind each decision."""

    music_bed: bool
    reasons: list[str] = field(default_factory=list)
    tempo_bpm: float | None = None
    tempo_range: tuple[float, float] | None = None
    duck_under_db: float = DEFAULT_DUCK_DB
    snap_cuts_to_beat: bool = False
    sfx_density_per_minute: float | None = None
    accents_have_room: bool = True
    confidence: str = "low"
    # What could not be established, in the operator's words rather than a null field.
    unknowns: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "music_bed": self.music_bed,
            "tempo_bpm": self.tempo_bpm,
            "tempo_range": list(self.tempo_range) if self.tempo_range else None,
            "duck_under_db": round(self.duck_under_db, 1),
            "snap_cuts_to_beat": self.snap_cuts_to_beat,
            "sfx_density_per_minute": self.sfx_density_per_minute,
            "accents_have_room": self.accents_have_room,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "unknowns": self.unknowns,
        }

    def search_filter(self) -> dict:
        """The bed to look for, in the shape a catalogue search wants.

        A BPM *range* rather than a point, because no library holds a track at exactly
        127.4 and demanding one returns nothing. The range is what makes the difference
        between a recommendation and a search that fails.
        """
        if not self.music_bed or not self.tempo_range:
            return {}
        low, high = self.tempo_range
        return {"bpm": {"min": round(low), "max": round(high)}, "vocals": False}


def _tempo_range(bpm: float) -> tuple[float, float]:
    """A window around a measured tempo, widening with how fast it is.

    Proportional rather than fixed: ±6 BPM is a different musical distance at 70 than at
    160, and a fixed window either returns nothing at the slow end or anything at all at
    the fast end.
    """
    margin = max(4.0, bpm * 0.06)
    return round(bpm - margin, 1), round(bpm + margin, 1)


def brief_from(audio: dict, alignment: dict | None = None) -> SoundBrief:
    """A sound-design brief from a reference's measured audio.

    Takes the dicts `StyleProfile` stores rather than the dataclasses, because that is
    what a learned style has on disk months later — the analysis objects are long gone by
    the time anyone asks what the style was.
    """
    audio = audio or {}
    alignment = alignment or {}
    reasons: list[str] = []
    unknowns: list[str] = []

    if not audio.get("present"):
        return SoundBrief(
            music_bed=False, confidence="none",
            reasons=["the reference has no audio track, so nothing about its sound "
                     "could be measured"],
            unknowns=["everything — this brief is defaults, not evidence"],
        )

    likely_music = bool(audio.get("likely_music"))
    bpm = audio.get("tempo_bpm")
    tempo_grade = str(audio.get("tempo_confidence") or "low")
    per_minute = audio.get("onsets_per_minute")
    silence = float(audio.get("silence_ratio") or 0.0)
    dynamic = float(audio.get("dynamic_range_db") or 0.0)

    tempo_usable = bool(bpm) and tempo_grade in USABLE_TEMPO
    if likely_music and tempo_usable:
        reasons.append(f"a music bed is present and its tempo reads {bpm:.0f} BPM "
                       f"({tempo_grade} confidence)")
    elif likely_music:
        reasons.append("a music bed is present, but its tempo could not be pinned down")
        unknowns.append(f"tempo — read as {bpm:.0f} BPM at {tempo_grade} confidence, "
                        f"too soft to buy a track against" if bpm else
                        "tempo — too few onsets to estimate one")
    else:
        reasons.append("no music bed was detected — this reference is voice and room, "
                       "so adding one would not be matching it")

    # Dynamic range is the honest proxy for how hard the bed is ducked. A mix with a bed
    # riding close to the voice is compressed flat; one that opens up between lines has
    # the bed pulled well down. This is a proxy and it says so — a real measurement
    # needs the stems, which a finished video does not have.
    if dynamic >= 24.0:
        duck = 12.0
        reasons.append(f"{dynamic:.0f} dB of dynamic range, so the bed drops well under "
                       f"the voice — duck about {duck:.0f} dB")
    elif dynamic >= 12.0:
        duck = DEFAULT_DUCK_DB
        reasons.append(f"{dynamic:.0f} dB of dynamic range — a conventional bed, "
                       f"about {duck:.0f} dB under")
    else:
        duck = 6.0
        reasons.append(f"only {dynamic:.0f} dB of dynamic range, so the mix sits flat "
                       f"and the bed rides close — about {duck:.0f} dB under")
        unknowns.append("ducking depth — a flat mix could equally be heavy compression "
                        "rather than a loud bed, and the two are not separable without "
                        "the stems")

    dense = per_minute is not None and float(per_minute) >= SFX_DENSE_PER_MINUTE
    if dense:
        reasons.append(f"{float(per_minute):.0f} onsets a minute is percussive sound "
                       f"design — hits and stings, not just a bed")

    room = silence >= ROOM_FOR_ACCENTS
    if not room:
        reasons.append(f"only {silence * 100:.0f}% silence, so the mix is wall to wall "
                       f"and there is no gap for an accent to land in")

    snap = str(alignment.get("verdict") or "") == "cuts_locked_to_beat"
    if snap:
        ratio = alignment.get("cuts_on_beat_ratio")
        reasons.append(
            f"{float(ratio) * 100:.0f}% of its cuts land on the beat — cut to the music"
            if ratio is not None else "its cuts are locked to the beat — cut to the music"
        )
    elif not alignment.get("measured"):
        unknowns.append("whether its cuts follow the music — not measured")

    return SoundBrief(
        music_bed=likely_music,
        tempo_bpm=round(float(bpm), 1) if tempo_usable else None,
        tempo_range=_tempo_range(float(bpm)) if tempo_usable else None,
        duck_under_db=duck,
        snap_cuts_to_beat=snap,
        sfx_density_per_minute=round(float(per_minute), 1) if per_minute is not None else None,
        accents_have_room=room,
        confidence=_confidence(likely_music, tempo_usable, bool(alignment.get("measured"))),
        reasons=reasons,
        unknowns=unknowns,
    )


def _confidence(has_music: bool, tempo_usable: bool, alignment_measured: bool) -> str:
    """How much of the brief rests on measurement rather than convention.

    Reported rather than hidden, because a brief built from one usable number and two
    defaults should not read the same as one built from three measurements.
    """
    measured = sum((has_music, tempo_usable, alignment_measured))
    if measured >= 3:
        return "high"
    if measured == 2:
        return "medium"
    return "low"


def recommend(niche: str = "") -> SoundBrief:
    """A brief with no reference at all, from the niche's convention.

    Offered because "give me a reference video" is not always answerable — a new channel
    in a known niche has no reference and still needs a starting point. Every field here
    is convention, so `confidence` is "none" and `reasons` says so: this is a suggestion
    to argue with, not a measurement to trust.
    """
    topic = (niche or "").lower()

    # Narrated explainer and documentary work sits quiet and cuts on sense, not on the
    # beat. Music-led formats invert both.
    music_led = any(word in topic for word in
                    ("music", "drill", "rap", "propaganda", "montage", "trailer"))
    ambient = any(word in topic for word in ("ambient", "sleep", "focus", "study", "lofi"))

    if music_led:
        return SoundBrief(
            music_bed=True, tempo_bpm=140.0, tempo_range=(130.0, 150.0),
            duck_under_db=3.0, snap_cuts_to_beat=True, confidence="none",
            reasons=["a music-led format, so the track is the spine: cuts land on the "
                     "beat and the bed sits near the front"],
            unknowns=["all of it — no reference was given, so this is the convention "
                      "for the niche rather than anything measured"],
        )
    if ambient:
        return SoundBrief(
            music_bed=True, tempo_bpm=70.0, tempo_range=(60.0, 85.0),
            duck_under_db=0.0, snap_cuts_to_beat=False, confidence="none",
            reasons=["an ambient format, so the bed is the content and there is no "
                     "narration to duck under"],
            unknowns=["all of it — convention for the niche, not a measurement"],
        )
    return SoundBrief(
        music_bed=True, tempo_bpm=None, tempo_range=(75.0, 110.0),
        duck_under_db=DEFAULT_DUCK_DB, snap_cuts_to_beat=False, confidence="none",
        reasons=["a narrated format, so a quiet bed well under the voice, and cuts on "
                 "sense rather than on the beat"],
        unknowns=["all of it — convention for narrated video, not a measurement. Give "
                  "me a reference video and I will measure it instead."],
    )
