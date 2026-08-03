"""Turning a reference's measured audio into advice, and admitting what it cannot tell.

Every case here is a dict shaped like the one `StyleProfile` actually stores, because
that is what a learned style has on disk months later — the analysis dataclasses are long
gone by the time anyone asks what the style was.
"""

from __future__ import annotations

from forgecast.style.sound import DEFAULT_DUCK_DB, brief_from, recommend


def measured(**over) -> dict:
    """A reference with a bed at 128 BPM, wide dynamics and room to breathe."""
    return {"present": True, "likely_music": True, "tempo_bpm": 128.0,
            "tempo_confidence": "high", "onsets_per_minute": 52.0,
            "silence_ratio": 0.12, "dynamic_range_db": 26.0, **over}


LOCKED = {"measured": True, "verdict": "cuts_locked_to_beat", "cuts_on_beat_ratio": 0.81}


def test_a_measured_reference_yields_a_searchable_bed():
    brief = brief_from(measured(), LOCKED)

    assert brief.music_bed is True
    assert brief.tempo_bpm == 128.0
    assert brief.confidence == "high"
    # A range, not a point: no library holds a track at exactly 128.0, and asking for one
    # returns nothing. This is the difference between advice and a search that fails.
    assert brief.search_filter() == {"bpm": {"min": 120, "max": 136}, "vocals": False}


def test_the_tempo_window_widens_with_the_tempo():
    """±6 BPM is a different musical distance at 70 than at 160."""
    slow = brief_from(measured(tempo_bpm=70.0)).tempo_range
    fast = brief_from(measured(tempo_bpm=160.0)).tempo_range

    assert slow is not None and fast is not None
    assert (fast[1] - fast[0]) > (slow[1] - slow[0])


def test_a_soft_tempo_reading_is_refused_rather_than_used():
    """A tempo guessed from too few onsets would buy a track matched to noise."""
    brief = brief_from(measured(tempo_confidence="low"))

    assert brief.tempo_bpm is None
    assert brief.search_filter() == {}
    assert any("tempo" in unknown for unknown in brief.unknowns)


def test_a_reference_with_no_bed_is_not_given_one():
    """Adding music to a voice-and-room reference is not matching it."""
    brief = brief_from({"present": True, "likely_music": False,
                        "silence_ratio": 0.19, "dynamic_range_db": 14.0})

    assert brief.music_bed is False
    assert any("no music bed" in reason for reason in brief.reasons)


def test_no_audio_track_produces_defaults_that_say_they_are_defaults():
    brief = brief_from({"present": False})

    assert brief.confidence == "none"
    assert brief.unknowns and "defaults" in brief.unknowns[0]


def test_ducking_follows_the_dynamic_range_and_flags_its_own_ambiguity():
    """A flat mix could be a loud bed or heavy compression, and the two do not separate."""
    wide = brief_from(measured(dynamic_range_db=26.0))
    flat = brief_from(measured(dynamic_range_db=6.0))

    assert wide.duck_under_db > DEFAULT_DUCK_DB > flat.duck_under_db
    assert any("stems" in unknown for unknown in flat.unknowns)
    assert flat.unknowns and not any("stems" in u for u in wide.unknowns)


def test_cuts_on_the_beat_are_carried_across_with_their_evidence():
    assert brief_from(measured(), LOCKED).snap_cuts_to_beat is True
    loose = brief_from(measured(), {"measured": True, "verdict": "cuts_ignore_beat"})
    assert loose.snap_cuts_to_beat is False


def test_a_wall_to_wall_mix_has_no_room_for_an_accent():
    assert brief_from(measured(silence_ratio=0.02)).accents_have_room is False
    assert brief_from(measured(silence_ratio=0.19)).accents_have_room is True


def test_confidence_reports_how_much_was_measured():
    """One number and two conventions must not read like three measurements."""
    assert brief_from(measured(), LOCKED).confidence == "high"
    assert brief_from(measured(), {"measured": False}).confidence == "medium"
    assert brief_from(measured(tempo_confidence="low"), {"measured": False}).confidence == "low"


def test_with_no_reference_the_niche_convention_says_it_is_a_convention():
    narrated = recommend("space documentary")
    assert narrated.confidence == "none"
    assert any("reference video" in unknown for unknown in narrated.unknowns)

    # A music-led format inverts both decisions: the track is the spine.
    drill = recommend("drill music video")
    assert drill.snap_cuts_to_beat is True
    assert drill.duck_under_db < narrated.duck_under_db

    # Ambient has no narration to duck under at all.
    assert recommend("ambient sleep").duck_under_db == 0.0
