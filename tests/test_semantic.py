"""What a reference says, sectioned — and the socket that finally has something in it.

`profile.build` has taken a `semantic` argument since the day it was written and no
caller ever passed one, so every reference this app has learned came back carrying the
profile's own apology about there being no semantic pass. Meanwhile `ingest/transcript`
transcribed operator-supplied files and never once a *learned reference*. The app could
say a creator cuts every 2.1 seconds and could not say what they were talking about.

Two halves are tested here and only one of them is the measurement.

The half that keeps going wrong in this project is the wiring:
`test_the_learn_path_actually_fills_the_socket` is the assertion this file exists for. A
narrative measured, sectioned, graded and returned to nobody is the same defect as an
animation share nothing reserves against.

The other half is the refusals. A closed vocabulary of six section names and a video
that has five beats is an open invitation to name something a `turn` because it came
fourth, so the tests below spend as much effort on what the module declines to say as on
what it says.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from forgecast.ingest.transcript import Line, Word
from forgecast.vision import analyse_file, probe, semantic

FFMPEG = "ffmpeg"


def _run(args: list[str]) -> None:
    proc = subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode(errors="replace")[-500:])


def _line(index: int, start: float, end: float, text: str,
          probability: float = 0.95) -> Line:
    """One spoken segment in the shape `ingest.transcript.read` returns.

    Word timings are spread evenly across the segment. They are not what any assertion
    below rests on — the sectioning reads segment edges — but `_word_confidence` reads
    per-word probabilities, and a fixture with no words in it would grade every read as
    clean by having nothing to grade.
    """
    parts = text.split()
    step = (end - start) / max(len(parts), 1)
    words = [
        Word(text=word, start=round(start + offset * step, 3),
             end=round(start + (offset + 1) * step, 3), probability=probability)
        for offset, word in enumerate(parts)
    ]
    return Line(index=index, text=text, start=start, end=end, words=words)


def _narration(spec: list[tuple[float, float, str]], probability: float = 0.95) -> list[Line]:
    return [_line(index, start, end, text, probability)
            for index, (start, end, text) in enumerate(spec)]


# A read with all six beats in it, and every one of them separated by evidence rather
# than by position: the boundaries are pauses four times longer than the gaps inside a
# beat, the escalation is a measured rise in words per second, and the turn opens on a
# break two and a half times longer than any other break in the video.
#
# Runtime is 40s while the speech ends at 39.6, because a reference is never speech
# wall to wall and `speech_share` is one of the numbers being checked.
FULL = _narration([
    # hook — 0.0 to 4.0, then the narrator stops for a second
    (0.00, 1.90, "Most people think faster cutting is what keeps a viewer watching."),
    (2.10, 4.00, "It is not."),
    # setup — 4.0 words/s, faster than the beat after it, so the escalation run cannot
    # start here and swallow the slot
    (5.00, 7.90, "So I went back through forty of my own videos and counted every single cut."),
    (8.10, 11.00, "Then I put them next to the retention graph."),
    # escalation, first beat — 3.0 words/s
    (12.00, 14.90, "The videos that held people were not the fast ones."),
    (15.10, 18.00, "They were the ones that changed subject often."),
    # escalation, second beat — 4.67 words/s
    (19.00, 21.90, "A cut inside the same shot is not a change, it is a reframe, and the eye knows."),
    (22.10, 25.00, "Six of those in a row is one idea."),
    # turn — opens on a 2.6s break, the longest in the read
    (27.60, 30.50, "So the number that matters is not the cut rate."),
    (30.70, 33.60, "It is the picture rate."),
    # close
    (34.60, 36.90, "Count how many different pictures your last video showed."),
    (37.10, 39.60, "That is your number."),
])

# The same length of read with the structure taken out: every break is the same length
# and every beat is delivered at the same rate. Nothing here is evidence of anything
# except where the narrator breathed.
FLAT = _narration([
    (0.00, 2.90, "One two three four five six seven eight nine."),
    (3.10, 6.00, "One two three four five six seven eight nine."),
    (7.00, 9.90, "One two three four five six seven eight nine."),
    (10.10, 13.00, "One two three four five six seven eight nine."),
    (14.00, 16.90, "One two three four five six seven eight nine."),
    (17.10, 20.00, "One two three four five six seven eight nine."),
    (21.00, 23.90, "One two three four five six seven eight nine."),
    (24.10, 27.00, "One two three four five six seven eight nine."),
])


@pytest.fixture(scope="module")
def clip(tmp_path_factory) -> Path:
    """Four seconds of colour over a tone. A real file, because the wiring tests run
    through `probe` and the whole engine rather than around them."""
    path = tmp_path_factory.mktemp("semantic") / "reference.mp4"
    _run(["-f", "lavfi", "-i", "color=c=0x203040:s=160x90:d=4:r=30",
          "-f", "lavfi", "-i", "sine=frequency=440:duration=4:sample_rate=48000",
          "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-shortest", str(path)])
    return path


@pytest.fixture(scope="module")
def silent_clip(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("semantic-silent") / "silent.mp4"
    _run(["-f", "lavfi", "-i", "color=c=0x203040:s=160x90:d=4:r=30",
          "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(path)])
    return path


def _hear(monkeypatch, lines: list[Line]) -> None:
    """Make this machine behave as though `faster-whisper` were installed and said this.

    The suite does not install the `edit` extra — that is the point of the extra — so
    without this every test below would exercise the degraded path and none would
    exercise the measurement. Patched on the transcript module itself rather than on a
    copy held by `semantic`, so a future import style there cannot silently make these
    tests stop testing anything.
    """
    monkeypatch.setattr(semantic.transcript, "available", lambda: (True, ""))
    monkeypatch.setattr(semantic.transcript, "read",
                        lambda path, **kwargs: list(lines))


# ------------------------------------------------------------- what can be measured


def test_the_hook_ends_where_the_narrator_first_stops():
    """The one number this module exists to produce. An editor cuts to it and a script
    is written against it, and nothing in the edit measurements can reach it."""
    found = semantic.section(FULL, runtime=40.0)
    assert found.sectioned
    assert found.sections[0].name == "hook"
    assert found.hook_ends_at == 4.0
    assert found.sections[1].opened_on_pause == 1.0


def test_every_section_reports_its_own_timing_words_and_rate():
    found = semantic.section(FULL, runtime=40.0)
    hook = found.sections[0]
    assert (hook.start, hook.end, hook.seconds) == (0.0, 4.0, 4.0)
    assert hook.words == 14
    assert hook.words_per_second == 3.5
    assert hook.share == 0.1        # of a 40s runtime
    assert "Most people think" in hook.text


def test_the_sections_account_for_every_word_that_was_said():
    """Sections partition the transcript. A beat quietly dropped between two boundaries
    is a section of the reference nobody is looking at."""
    found = semantic.section(FULL, runtime=40.0)
    assert sum(section.words for section in found.sections) == found.words
    assert found.words == 111
    # The sum of the spoken segments, not the span from first word to last: the gaps
    # between lines are where the narrator was not talking, and folding them in would
    # report every read as slower than it is.
    assert found.spoken_seconds == pytest.approx(31.8, abs=0.1)
    assert found.speech_share == pytest.approx(0.795, abs=0.01)


def test_a_beat_and_the_whole_reference_are_measured_by_one_rule():
    """Words over the span the thing occupies, at both levels. Two denominators under
    one field name would be two answers to how fast this creator talks, and the
    difference between them is large enough — 166 words a minute against 209 — to
    change what a script written to their style comes out at."""
    found = semantic.section(FULL, runtime=40.0)
    assert found.words_per_second == pytest.approx(111 / 40.0, abs=0.02)
    assert found.words_per_minute == pytest.approx(111 / 40.0 * 60, abs=0.2)
    # The articulation rate is recoverable rather than reported twice.
    assert found.words / found.spoken_seconds == pytest.approx(3.49, abs=0.02)


def test_a_beat_is_named_only_by_the_measurement_that_reaches_it():
    """Six names, six beats, and each one issued by its own rule: the ends are
    positional, the turn is a single measured discontinuity, the escalation is a trend
    across sections, and the setup is what sits between the hook and the rise."""
    found = semantic.section(FULL, runtime=40.0)
    assert [section.name for section in found.sections] == [
        "hook", "setup", "escalation", "escalation", "turn", "close"]
    assert all(section.evidence for section in found.sections)


def test_the_turn_names_the_break_it_was_named_for():
    """Evidence attached to the name, for `style.sound`'s reason: a recommendation with
    no number behind it cannot be argued with, which makes it useless."""
    turn = next(s for s in semantic.section(FULL, runtime=40.0).sections
                if s.name == "turn")
    assert turn.opened_on_pause == 2.6
    assert "2.60s" in turn.evidence


def test_the_delivery_trend_speaks_the_edits_own_words():
    """`shots.pacing_trend` already answers 'does the edit accelerate'. This answers it
    of the read, in the same vocabulary, so the two can be put side by side."""
    assert semantic.section(FULL, runtime=40.0).delivery_trend == "decelerating"
    assert semantic.section(FLAT, runtime=28.0).delivery_trend == "steady"


# ------------------------------------------------------ and what is refused instead


def test_the_payoff_is_never_claimed_and_says_why():
    """The refusal this module is built around. A payoff is a promise being kept, and
    the only marker that would find one is the marker already spent on the turn."""
    for found in (semantic.section(FULL, runtime=40.0),
                  semantic.section(FLAT, runtime=28.0)):
        assert "payoff" not in [section.name for section in found.sections]
        assert "payoff" in found.not_claimed
        assert "meaning" in found.not_claimed["payoff"]


def test_a_flat_read_gets_no_turn_no_escalation_and_no_setup():
    """Four evenly spaced beats read at one rate. Naming any of these would be naming
    them by position, which is exactly how a closed vocabulary invents structure."""
    found = semantic.section(FLAT, runtime=28.0)
    assert [section.name for section in found.sections] == [
        "hook", "body", "body", "close"]
    for refused in ("turn", "escalation", "setup", "payoff"):
        assert found.not_claimed[refused]


def test_an_unnamed_beat_says_it_is_unnamed_rather_than_going_blank():
    body = [s for s in semantic.section(FLAT, runtime=28.0).sections if s.name == "body"]
    assert body and all("no measured marker" in section.evidence for section in body)


def test_no_section_is_ever_called_something_outside_the_vocabulary():
    """A closed list is only closed if nothing writes past it — the whole reason a
    fixed vocabulary makes a shelf of learned references countable."""
    allowed = set(semantic.VOCABULARY) | {semantic.UNNAMED}
    for found in (semantic.section(FULL, runtime=40.0),
                  semantic.section(FLAT, runtime=28.0)):
        assert {section.name for section in found.sections} <= allowed


def test_a_reference_too_short_to_section_says_so_rather_than_inventing_sections():
    """The headline refusal. Two lines can be split into two spans by any pause at all,
    and calling those a hook and a close would be a whole storytelling structure derived
    from one breath."""
    short = _narration([
        (0.0, 2.0, "Here is the thing nobody tells you."),
        (4.0, 7.0, "It takes about a week."),
    ])
    found = semantic.section(short, runtime=8.0)

    assert found.transcribed is True
    assert found.sectioned is False
    assert found.sections == []
    assert found.hook_ends_at is None
    assert found.confidence == "low"
    assert any("too short to section" in note for note in found.notes)


def test_a_read_that_never_pauses_is_one_beat_and_is_reported_as_one():
    """Nothing is wrong with this reference. There is simply no boundary in it, and a
    boundary invented to make six sections appear is a boundary nobody can cut to."""
    breathless = _narration([
        (index * 3.0, index * 3.0 + 2.9, "One two three four five six seven eight.")
        for index in range(8)
    ])
    found = semantic.section(breathless, runtime=24.0)
    assert found.sectioned is False
    assert found.sections == []
    assert any("one continuous beat" in note for note in found.notes)


def test_a_pause_for_effect_is_not_a_section():
    """A single line held between two long breaks is a beat inside a section — dropping
    it in as its own section would put a `turn` on somebody's dramatic silence."""
    dramatic = _narration([
        (0.00, 2.90, "I spent three months building the wrong thing."),
        (3.10, 6.00, "Three months, on a feature nobody had asked for."),
        (6.20, 9.00, "Not one person."),
        (10.00, 10.80, "Nobody."),                      # 0.8s, its own break either side
        (11.80, 14.70, "So I went and asked twenty of them what they actually wanted."),
        (14.90, 17.80, "Every answer was the same three words."),
        (18.00, 20.90, "Make it faster."),
        (21.90, 24.80, "That is the whole roadmap now, and it took a quarter to find."),
        (25.00, 27.90, "Ask first, build second."),
        (28.10, 31.00, "It is not clever and it works."),
    ])
    found = semantic.section(dramatic, runtime=32.0)
    assert len(found.sections) == 3
    assert "Nobody." in found.sections[0].text
    assert found.hook_ends_at == 10.8
    assert all(section.seconds >= semantic.MIN_SECTION_SECONDS
               for section in found.sections)


def test_two_beats_do_not_get_a_close():
    """A hook and the rest of the video. Calling the second half a `close` would claim
    this reference had a middle, and the middle is the part a close is defined against."""
    halved = _narration([
        (0.00, 2.90, "There is one setting in the export dialog that everybody gets wrong."),
        (3.10, 6.00, "It is not the bitrate and it is not the codec."),
        (6.20, 9.00, "It is the keyframe interval."),
        (10.20, 13.10, "Set it to two seconds and the platform stops re-encoding you."),
        (13.30, 16.20, "That is the whole trick."),
        (16.40, 19.00, "Nothing else in that dialog matters as much."),
    ])
    found = semantic.section(halved, runtime=20.0)

    assert [section.name for section in found.sections] == ["hook", "body"]
    assert "second name" in found.not_claimed["close"]
    assert "two beats" in found.not_claimed["escalation"]


def test_a_read_of_nothing_but_short_beats_is_not_sectioned_into_them():
    """Eight one-line beats, each under a second. Every break here is real and none of
    them separates a *section* — reporting four is reporting the punctuation of the read
    as the structure of the story."""
    staccato = _narration([
        (0.00, 0.40, "Stop."),
        (0.50, 0.90, "Look at this."),
        (1.70, 2.10, "Right there."),
        (2.20, 2.60, "See it?"),
        (3.40, 3.80, "One frame."),
        (3.90, 4.30, "That is all."),
        (5.10, 5.50, "Nobody notices."),
        (5.60, 6.00, "You will now."),
    ])
    found = semantic.section(staccato, runtime=7.0)

    assert found.sectioned is False
    assert found.sections == []
    assert any("pauses for effect, not sections" in note for note in found.notes)


def test_a_read_the_model_could_not_hear_is_graded_down():
    """The timings are still where the speech is — whisper's word boundaries survive a
    bad read. The quoted text does not, and a section quoted from words the model was
    unsure of is not evidence of what the reference said."""
    found = semantic.section(_narration([
        (start, end, text) for start, end, text in
        [(line.start, line.end, line.text) for line in FULL]
    ], probability=0.3), runtime=40.0)
    assert found.sectioned is True
    assert found.confidence == "low"
    assert any("confidence per word" in note for note in found.notes)


def test_nothing_said_is_a_finding_not_a_failure():
    found = semantic.section([], runtime=30.0)
    assert found.transcribed is False
    assert found.confidence == "none"
    assert found.notes
    assert found.not_claimed["payoff"]


# ------------------------------------------------------------- degrading in the open


def test_a_machine_with_no_transcriber_is_told_which_tool_is_missing(monkeypatch, clip):
    """`faster-whisper` is the optional `edit` extra and most installs will not have it.
    The learn has to keep going and has to say why this reference is thinner than the
    others — a `semantic` block that silently arrives empty is indistinguishable from
    the socket never having been filled at all."""
    monkeypatch.setattr(semantic.transcript, "available",
                        lambda: (False, "transcription needs Video editing tools — "
                                        "install them in Setup"))
    found = semantic.measure(probe(clip))

    assert found.transcribed is False
    assert found.sectioned is False
    assert found.confidence == "none"
    assert any("Video editing tools" in note for note in found.notes)


def test_a_reference_with_no_audio_is_refused_before_the_model_is_loaded(
        monkeypatch, silent_clip):
    """Checked off the probe rather than by transcribing four seconds of nothing. On a
    ten-minute silent reference the difference is the whole model load and decode."""
    def refuse(*args, **kwargs):                                      # pragma: no cover
        raise AssertionError("a silent reference was sent to the transcriber")

    monkeypatch.setattr(semantic.transcript, "available", lambda: (True, ""))
    monkeypatch.setattr(semantic.transcript, "read", refuse)
    found = semantic.measure(probe(silent_clip))

    assert found.transcribed is False
    assert any("no audio track" in note for note in found.notes)


def test_a_transcriber_that_throws_costs_one_reference_not_the_learn(monkeypatch, clip):
    """The first transcription on a machine downloads model weights, and everything
    from a closed socket to a runtime that will not load on this CPU surfaces as some
    exception nobody enumerated. A learn that dies on the third of five references
    leaves the operator with nothing and no reason."""
    monkeypatch.setattr(semantic.transcript, "available", lambda: (True, ""))
    monkeypatch.setattr(semantic.transcript, "read",
                        lambda path, **kwargs: (_ for _ in ()).throw(
                            OSError("model weights could not be fetched")))
    found = semantic.measure(probe(clip))

    assert found.transcribed is False
    assert any("model weights" in note for note in found.notes)


def test_the_narrative_needs_no_provider_no_key_and_no_network(monkeypatch, clip):
    """A vision provider was the only thing that was ever going to fill `semantic`, and
    there has never been one configured. Every number here comes out of the reference's
    own audio, so the block arrives on an install with no keys at all."""
    import httpx

    def refuse(*args, **kwargs):                                      # pragma: no cover
        raise AssertionError("the narrative pass opened an HTTP client")

    monkeypatch.setattr(httpx, "Client", refuse)
    monkeypatch.setattr(httpx, "AsyncClient", refuse)
    _hear(monkeypatch, FULL)

    found = semantic.measure(probe(clip))
    assert found.sectioned is True
    assert found.confidence == "high"


# ------------------------------------------------------------ and it reaches the run


def test_the_learn_path_actually_fills_the_socket(clip):
    """The assertion this file exists for. `profile.build` has taken a `semantic`
    argument since it was written and every caller passed `None`, so the field was
    documented, serialised, rendered and empty on every reference ever learned."""
    profile = analyse_file(clip, narrative=True)

    assert profile.semantic is not None, "the narrative pass did not reach the profile"
    assert profile.confidence["semantic"] == "present"
    assert not any("no semantic pass" in note for note in profile.confidence["notes"])
    # Even on this machine, which has no transcriber: the block is present and says so.
    assert profile.semantic["notes"]


def test_the_measured_narrative_survives_the_trip_into_the_profile(monkeypatch, clip):
    """Through `analyse_file` rather than by calling `section` and asserting on it. The
    wiring between a measurement and the profile is where this project keeps losing
    features, so the sections are checked on the far side of it."""
    _hear(monkeypatch, FULL)
    profile = analyse_file(clip, narrative=True)

    block = profile.semantic
    assert block["sectioned"] is True
    assert block["hook_ends_at"] == 4.0
    assert [section["name"] for section in block["sections"]][:2] == ["hook", "setup"]
    assert block["not_claimed"]["payoff"]
    # Must survive the trip to a database or a website unchanged, like every other
    # block on the profile.
    assert json.loads(json.dumps(profile.as_dict()))["semantic"]["hook_ends_at"] == 4.0


def test_analysing_without_the_flag_leaves_the_socket_alone(clip):
    """Opt-in, because it transcribes. `compare` and `restyle --verify` re-measure a
    file to check an edit landed and would only be paying for the wait."""
    profile = analyse_file(clip)
    assert profile.semantic is None
    assert profile.confidence["semantic"] == "absent"


def test_a_supplied_semantic_block_still_wins(clip):
    """The socket's original purpose. A caller holding a vision provider's description
    of the shots has more than this can derive, and must not have it overwritten."""
    supplied = {"described_by": "a vision provider", "shots": []}
    profile = analyse_file(clip, semantic=supplied, narrative=True)
    assert profile.semantic == supplied


def test_the_cli_learn_path_asks_for_the_narrative(monkeypatch, tmp_path):
    """`forgecast-vision learn-style` is one of the two ways a style is ever produced.
    `_profile_from` is the only function in that CLI that measures a reference *in order
    to keep it*, which is why the flag is set there and nowhere else in the file."""
    from forgecast.vision import cli

    seen: dict = {}

    class Measured:
        def as_dict(self, **_kwargs) -> dict:
            return {"render_spec": {}, "source": {"path": "ref.mp4"}}

    monkeypatch.setattr(cli, "analyse_file",
                        lambda path, **kwargs: (seen.update(kwargs), Measured())[1])
    reference = tmp_path / "ref.mp4"
    reference.write_bytes(b"not really a video, and never opened")

    cli._profile_from(str(reference))
    assert seen.get("narrative") is True


def test_the_app_learn_path_asks_for_the_narrative(monkeypatch, tmp_path):
    """The other way — the one the `/styles` page and the agent's `learn_style` tool
    both run through. A feature reachable only from a CLI flag is most of the way to
    being unreachable, which is the defect this whole exercise is about."""
    from forgecast import vision
    from forgecast.agent.studio import Studio

    seen: dict = {}

    class Measured:
        def as_dict(self, **_kwargs) -> dict:
            return {"render_spec": {}, "source": {"path": "ref.mp4"}}

    monkeypatch.setattr(vision, "analyse_file",
                        lambda path, **kwargs: (seen.update(kwargs), Measured())[1])
    reference = tmp_path / "ref.mp4"
    reference.write_bytes(b"not really a video, and never opened")
    monkeypatch.setattr(Studio, "_supplied",
                        staticmethod(lambda path: (Path(str(path)), "")))

    result = Studio().learn_style(str(reference), name="Reference Look")
    assert seen.get("narrative") is True
    assert result.get("learned") == "Reference Look"
