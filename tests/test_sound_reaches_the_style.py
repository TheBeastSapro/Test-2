"""The sound stage reading the reference it was told about.

`nodes/sound.py` has always had two branches: a measured brief from the reference's own
audio, and a niche convention when there is none. The measured one could not fire. It
reads `style_profile["audio"]` and `["beat_alignment"]`, `to_channel_profile` wrote
neither, and `learn()` read the audio measurement only to reduce it to three scalars and
drop the rest.

So every run took the fallback — under a message reading "no reference video has been
analysed, so nothing here was measured", on channels where one had been. A wrong answer
delivered in the words of a right one.
"""

from __future__ import annotations

from forgecast.style.editing import EditingStyle, _richest

# The field names `vision.audio` actually stores and `style.sound.brief_from` actually
# reads. Written from the consumer rather than invented: a fixture with plausible-looking
# keys passes the plumbing and proves nothing about the two ends meeting, which is the
# only thing this file is for.
MEASURED = {"present": True, "likely_music": True, "tempo_bpm": 92.0,
            "tempo_confidence": "high", "onsets_per_minute": 128.0,
            "silence_ratio": 0.08, "dynamic_range_db": 12.4}
ALIGNMENT = {"measured": True, "verdict": "cuts_locked_to_beat",
             "cuts_on_beat_ratio": 0.71}


def test_the_measurement_reaches_the_channel():
    profile = EditingStyle(name="learned", audio=MEASURED,
                           beat_alignment=ALIGNMENT).to_channel_profile({})

    assert profile["audio"] == MEASURED
    assert profile["beat_alignment"] == ALIGNMENT


def test_a_style_with_no_audio_does_not_blank_a_working_channel():
    """A style learned before this field existed, or from a reference with no audio
    track, must not overwrite numbers a channel already has with an empty dict — the
    same guard `sourcing` and `narrative` carry."""
    profile = EditingStyle(name="old").to_channel_profile({"audio": {"present": True}})

    assert profile["audio"] == {"present": True}


def test_the_sound_node_takes_the_measured_branch_when_there_is_one():
    """The branch this was all for. It is selected on the presence of the key, so the
    end-to-end assertion is that a learned style puts the key there."""
    from forgecast.style.sound import brief_from

    profile = EditingStyle(name="learned", audio=MEASURED,
                           beat_alignment=ALIGNMENT).to_channel_profile({})
    brief = brief_from(profile["audio"], profile["beat_alignment"])

    assert brief.confidence != "none"
    assert brief.music_bed is True


def test_audio_is_taken_whole_rather_than_averaged_across_references():
    """Bed level, ducking depth and cue placement are one decision read three ways.
    Averaging them across two creators describes a mix neither of them made, which is
    exactly the failure the pooled fields elsewhere are safe from because their fields
    are independent."""
    thin = {"present": True, "likely_music": True}
    full = {"present": True, "likely_music": True, "tempo_bpm": 92.0,
            "dynamic_range_db": 12.4, "silence_ratio": 0.08}

    picked = _richest([{"audio": thin}, {"audio": full}], "audio")

    assert picked == full
    assert picked["tempo_bpm"] == 92.0, "no averaging: the value is one reference's own"


def test_no_reference_measured_anything_yields_nothing_rather_than_a_default():
    assert _richest([{}, {"audio": {}}], "audio") == {}


def test_the_learned_style_round_trips_the_measurement():
    """It has to survive being saved and read back, which is the whole point of keeping
    the dicts rather than the objects."""
    style = EditingStyle(name="learned", audio=MEASURED, beat_alignment=ALIGNMENT)
    again = EditingStyle.from_dict(style.as_dict())

    assert again.audio == MEASURED
    assert again.beat_alignment == ALIGNMENT
