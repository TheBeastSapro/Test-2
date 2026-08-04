"""What a learned reference SAYS, reaching the script that gets written.

`vision/semantic.py` transcribes a learned reference, cuts it into beats, measures how
fast the creator talks and where their opening beat stops, grades the whole thing and
lands it on the style profile. Nothing read it. The app could tell you a channel says 3.4
words a second and opens in 3.2 seconds, and then wrote every script at 2.6 words a second
and judged every opening on fifteen seconds of video — the same numbers it would have used
having never looked at the reference at all.

That is this project's most expensive recurring defect: a measurement made, stored,
serialised, rendered and consumed by nobody. `test_sourcing_profile.py` was written for the
last instance of it and names the assertion that matters —
`test_the_measurement_changes_what_a_run_reserves`. This file is that assertion for the
narration, and it is the whole reason the file exists:

* **`test_a_measured_reference_changes_the_word_count`** — a channel measured at a
  different pace writes a different number of words for the same target duration, at the
  ledger and at the prompt.
* **`test_a_measured_reference_changes_the_hook_window_the_gate_cuts`** — a channel whose
  references stop their opening beat at three seconds is judged on three seconds of video.

Everything else here holds the two honest: the fallback when nothing is measured has to be
bit-for-bit what shipped, and every number has to be one the reference can actually answer.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import forgecast.nodes  # noqa: F401  - importing registers every handler
from forgecast.graph import pipelines
from forgecast.graph.engine import ChannelSnapshot, NodeContext
from forgecast.ingest.transcript import Line, Word
from forgecast.nodes import content, hook
from forgecast.providers import registry as provider_registry
from forgecast.scripting import method
from forgecast.style import editing
from forgecast.style.editing import (
    HOOK_SECONDS,
    WORDS_PER_SECOND,
    measure_narrative,
    writing_budget,
)
from forgecast.vision import semantic


def _line(index: int, start: float, end: float, text: str,
          probability: float = 0.95) -> Line:
    """One spoken segment in the shape `ingest.transcript.read` returns.

    The same helper `test_semantic.py` uses, for the reason that file gives: the word
    probabilities are not what any assertion here rests on, but a fixture with no words in
    it grades every read as clean by having nothing to grade.
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


def _measured(lines: list[Line], runtime: float) -> dict:
    """A reference's `semantic` block, produced by the real measurement.

    Through `semantic.section` rather than by writing the dict out by hand, because a
    hand-written block is a block that agrees with whatever this file expects. The point of
    the exercise is that the number the transcriber produced is the number the script gets
    written to, and a fixture that skips the measurement skips the half that keeps breaking.
    """
    return semantic.section(lines, runtime=runtime).as_dict()


# A breathless short-form creator: 3.4 words a second of runtime, and an opening beat that
# stops dead at 3.2 seconds. Every gap inside a beat is 0.15s and every gap between beats
# is 0.80s, so the boundaries are pauses rather than positions.
BREATHLESS = _narration([
    # hook — 0.0 to 3.2, read faster than the rest of the video
    (0.00, 1.50, "Your first three seconds decide whether anybody sees the rest."),
    (1.65, 3.20, "Nobody tells you that."),
    (4.00, 6.90, "I pulled the retention curve on forty of my own uploads last night."),
    (7.05, 9.95, "Every single one of them drops in the same place, at about four seconds."),
    (10.10, 13.00, "Not at the end, not in the middle, four seconds in."),
    (13.80, 16.70, "So I cut the first line off ten of them and reuploaded the lot."),
    (16.85, 19.75, "The drop moved. It did not go away, it moved."),
    (19.90, 22.80, "Which means the opening is not a warm up, it is the whole test."),
    (23.60, 26.50, "Here is the part that actually changed how I write."),
    (26.65, 29.55, "The line that held people was never the cleverest one."),
    (29.70, 32.60, "It was the shortest one, every time, without exception."),
    (33.40, 36.30, "Count the words in your first sentence right now."),
    (36.45, 39.35, "If it is over twelve, cut it in half and read it again."),
    (39.50, 42.40, "That is the whole trick and it costs you nothing at all."),
])

# A documentary at the other end: under two words a second of runtime, and an opening beat
# that runs nine seconds before the narrator first stops. Both channels are legitimate and
# the shipped 2.6 words a second is wrong for each of them in opposite directions.
UNHURRIED = _narration([
    (0.00, 4.00, "In nineteen sixty one a ship left Rotterdam carrying nothing."),
    (4.30, 9.00, "It came back three years later, and its cargo hold was sealed."),
    (10.20, 14.20, "The manifest listed forty tonnes of ballast and one crate."),
    (14.50, 19.20, "The crate is the only thing anybody has ever argued about."),
    (20.40, 24.40, "Nobody who signed for it is alive to be asked."),
    (24.70, 29.40, "The signatures are real and two of the names are not."),
    (30.60, 34.60, "What the archive does hold is a photograph of the dock."),
    (34.90, 39.60, "In it the crate is already open, and it is empty."),
    (40.80, 44.80, "That photograph was taken four days before the ship docked."),
    (45.10, 49.80, "Which is the only fact in this story nobody has explained."),
])

# Two lines and fifteen words. Enough to transcribe, nowhere near enough to write a
# channel's scripts against — `semantic` refuses to section it and this must refuse to
# adopt it.
THIN = _narration([
    (0.0, 2.0, "Here is the thing nobody tells you."),
    (4.0, 7.0, "It takes about a week."),
])


@pytest.fixture(scope="module")
def fast() -> dict:
    """The reference's own `semantic` block, as `vision.profile` carries it."""
    return _measured(BREATHLESS, 45.0)


@pytest.fixture(scope="module")
def slow() -> dict:
    return _measured(UNHURRIED, 60.0)


@pytest.fixture(scope="module")
def fast_profile(fast) -> dict:
    """The same reference as a channel carries it — `learn` pools the `semantic` blocks
    into one profile and `to_channel_profile` puts that on the channel, so this is the
    shape every consumer downstream actually receives."""
    return measure_narrative([fast]).as_dict()


@pytest.fixture(scope="module")
def slow_profile(slow) -> dict:
    return measure_narrative([slow]).as_dict()


def _channel(narrative: dict | None = None, **extra) -> ChannelSnapshot:
    profile = {"tone": "plain"} | ({"narrative": narrative} if narrative else {})
    return ChannelSnapshot(
        id=1, name="Test Channel", niche="infrastructure", language="en",
        voice_id="", avatar_id="", aspect_ratio="16:9",
        target_duration_seconds=120, style_profile=profile, **extra,
    )


def _script_context(tmp_path: Path, narrative: dict | None = None) -> NodeContext:
    return NodeContext(
        run_id=1, topic="Why deep-sea cables keep breaking", options={},
        node_key="script", node_type="script", params={}, attempts=0,
        channel=_channel(narrative),
        registry=None,  # type: ignore[arg-type]
        workdir=tmp_path,
        upstream_outputs={"brief": {"working_title": "Cables",
                                    "target_duration_seconds": 120,
                                    "beats": [{"name": "one"}, {"name": "two"}]}},
    )


def _scene(index: int, seconds: float, words: str = "some narration here") -> dict:
    return {"index": index, "seconds": seconds, "narration": words,
            "visual_prompt": f"a shot for scene {index}", "visual_kind": "image"}


# ============================================================ the two that matter


def test_a_measured_reference_changes_the_word_count(fast_profile, slow_profile):
    """The assertion this file exists for, at the number every script is built out of.

    A target duration becomes a word count exactly once, and it used to become the same
    word count for a breathless shorts channel and an unhurried documentary. Measured,
    they are hundreds of words apart for the same eight minutes — which is the difference
    between a script that lands and one the model pads or truncates to fit.
    """
    shipped = writing_budget(None)
    quick = writing_budget(fast_profile)
    unhurried = writing_budget(slow_profile)

    assert quick.words_per_second > shipped.words_per_second > unhurried.words_per_second
    assert quick.words_for(480) > shipped.words_for(480) > unhurried.words_for(480)
    # Not a rounding difference: the two measured channels are more than 500 words apart
    # over eight minutes, and both were being written at the figure between them.
    assert quick.words_for(480) - unhurried.words_for(480) > 500


def test_a_measured_reference_changes_what_the_pipeline_reserves(fast_profile):
    """End to end through `get_pipeline`, because the wiring from a learned style to a
    node's estimate runs through four modules and this project keeps breaking one of them.

    The reserve and the script have to move together. A hold priced at 2.6 words a second
    against a script written at 3.4 is a run that spends past its own hold, which the
    ledger has no way to refuse once it is under way.
    """
    plain = {node.key: node for node in
             pipelines.get_pipeline("faceless_longform", target_seconds=480).nodes}
    measured = {node.key: node for node in
                pipelines.get_pipeline("faceless_longform", target_seconds=480,
                                       narrative=fast_profile).nodes}

    assert measured["script"].estimated_units > plain["script"].estimated_units
    # The voice node is priced in characters off the same word count, so it has to move
    # with it — the narration is what a fast channel actually buys more of.
    assert measured["voice"].estimated_units > plain["voice"].estimated_units


def test_a_measured_reference_changes_the_hook_window_the_gate_cuts(fast_profile, slow_profile):
    """The other assertion this file exists for. A channel whose references stop their
    opening beat at 3.2 seconds should not have its opening judged on fifteen.

    Fifteen seconds of that channel's video is the hook and the setup and part of the
    escalation, and a gate that watches all three cannot tell a slow open — the failure it
    exists to catch — from a normal one.
    """
    quick = writing_budget(fast_profile)
    unhurried = writing_budget(slow_profile)

    assert quick.hook_seconds == pytest.approx(3.2, abs=0.01)
    assert unhurried.hook_seconds == pytest.approx(9.0, abs=0.01)
    assert writing_budget(None).hook_seconds == HOOK_SECONDS

    # And the window is what the gate actually cuts: three four-second scenes cover the
    # shipped window and only the first covers the measured one.
    scenes = [_scene(index, 4.0) for index in range(5)]
    assert len(hook.hook_scenes(scenes, seconds=quick.hook_seconds)) == 1
    assert len(hook.hook_scenes(scenes, seconds=unhurried.hook_seconds)) == 3
    assert len(hook.hook_scenes(scenes, seconds=writing_budget(None).hook_seconds)) == 4


def test_the_gate_cuts_the_measured_window_off_the_channel(tmp_path, fast_profile):
    """Through the node, with the narrative on the channel where a learned style puts it.

    `hook_scenes` taking a parameter proves nothing on its own — the previous version of
    this defect was a function with a parameter nobody passed. What is asserted here is
    that the handler reads the channel and cuts to it.
    """
    scenes = [_scene(index, 5.0, f"Scene {index} narration, several words long.")
              for index in range(4)]

    def run(narrative: dict | None) -> dict:
        context = NodeContext(
            run_id=1, topic="t", options={}, node_key="hook", node_type="hook",
            params={}, attempts=0,
            channel=_channel(narrative, video_height=720),
            registry=provider_registry.ProviderRegistry(mode="mock"),
            workdir=tmp_path / ("measured" if narrative else "shipped"),
            upstream_outputs={"script": {"scenes": scenes, "word_count": 400},
                              "voice_casting": {"selected_voice_id": "voice-1"}},
        )
        return asyncio.run(hook.hook_node(context)).output

    shipped = run(None)
    measured = run(fast_profile)

    # 3.2s of window takes one five-second scene; 15s takes three.
    assert measured["scenes"] == [0]
    assert shipped["scenes"] == [0, 1, 2]
    assert measured["measured_against"]["window_seconds"] == pytest.approx(3.2, abs=0.01)
    assert measured["commits"]["remaining_scenes"] == 3


# ============================================================ and it says what it did


def test_the_script_prompt_is_written_to_the_measured_rate(monkeypatch, tmp_path, fast_profile):
    """The rate reaches the model, not just the arithmetic.

    Both halves or neither: the prompt asks for scene lengths at a rate and
    `_normalise_scenes` recomputes them at a rate, and two rates under one instruction is
    the disagreement `scripting.method` says a model resolves by ignoring both.
    """
    seen: dict[str, str] = {}

    async def fake_ask(ctx, *, role, schema_name, payload, instructions, **kwargs):
        seen[schema_name] = instructions
        return ({"title": "Cables", "description": "d", "tags": [],
                 "scenes": [{"index": 0, "narration": "A cable snapped in the dark.",
                             "visual_prompt": "cable", "visual_kind": "image",
                             "seconds": 3.0, "on_screen_text": ""}]}, 0, "mock-llm")

    monkeypatch.setattr(content, "ask_json", fake_ask)
    asyncio.run(content.script_node(_script_context(tmp_path, fast_profile)))

    rate = f"{writing_budget(fast_profile).words_per_second:.2f}"
    assert f"at {rate} words per second" in seen["script"]
    assert "at 2.60 words per second" not in seen["script"]
    assert "2.6 words per second" not in seen["script"]


def test_the_script_prompt_carries_how_this_channel_opens(monkeypatch, tmp_path, fast_profile):
    """The gate downstream judges the opening against the references. The stage that
    writes it has to have been told the same thing, or the gate is grading a script
    against a standard nobody gave it."""
    seen: dict[str, str] = {}

    async def fake_ask(ctx, *, role, schema_name, payload, instructions, **kwargs):
        seen[schema_name] = instructions
        return ({"title": "t", "description": "d", "tags": [],
                 "scenes": [{"index": 0, "narration": "A cable snapped.",
                             "visual_prompt": "c", "visual_kind": "image",
                             "seconds": 3.0, "on_screen_text": ""}]}, 0, "mock-llm")

    monkeypatch.setattr(content, "ask_json", fake_ask)
    asyncio.run(content.script_node(_script_context(tmp_path, fast_profile)))

    assert "HOW THIS CHANNEL OPENS" in seen["script"]
    assert "3.2 seconds" in seen["script"]
    # The same sentence the gate will hold the finished hook against, from the same block.
    assert writing_budget(fast_profile).hook["sentence"] in seen["script"]


def test_the_scene_timings_use_the_rate_the_prompt_asked_for(fast_profile):
    """A scene length recomputed at a different rate from the one the model was given is
    the same disagreement one stage later, where nobody can see it."""
    raw = [{"index": 0, "narration": " ".join(["word"] * 34), "visual_prompt": "p",
            "visual_kind": "image", "seconds": 0.0, "on_screen_text": ""}]

    shipped = content._normalise_scenes(raw)
    measured = content._normalise_scenes(raw, rate=writing_budget(fast_profile).words_per_second)

    assert shipped[0]["seconds"] == pytest.approx(34 / WORDS_PER_SECOND, abs=0.01)
    assert measured[0]["seconds"] < shipped[0]["seconds"]


def test_the_run_log_says_which_rate_it_wrote_at(monkeypatch, tmp_path, fast_profile):
    """A fallback that does not say it fell back is indistinguishable from a measurement,
    which is exactly how the narrative came to be measured and unread. The run log is
    where somebody looks when a script came out the wrong length."""
    async def fake_ask(ctx, *, role, schema_name, payload, instructions, **kwargs):
        return ({"title": "t", "description": "d", "tags": [],
                 "scenes": [{"index": 0, "narration": "A cable snapped.",
                             "visual_prompt": "c", "visual_kind": "image",
                             "seconds": 3.0, "on_screen_text": ""}]}, 0, "mock-llm")

    monkeypatch.setattr(content, "ask_json", fake_ask)

    measured = _script_context(tmp_path / "measured", fast_profile)
    asyncio.run(content.script_node(measured))
    assert any("learned" in message for _l, message, _d in measured._logs)

    plain = _script_context(tmp_path / "plain", None)
    asyncio.run(content.script_node(plain))
    logged = " | ".join(message for _l, message, _d in plain._logs)
    assert "no reference has been learned" in logged
    assert "shipped 2.6 words a second" in logged


# ============================================================ the gate's judgement


def test_the_gate_holds_the_written_opening_against_the_learned_ones(fast_profile):
    """It used to judge the hook against nothing at all: cut it, show it, ask. An approval
    with nothing on the other side of the scales is a formality — the same argument
    `nodes/sample.py` makes about surfacing a price beside a clip."""
    budget = writing_budget(fast_profile)
    slow_open = hook.measured_against(budget, seconds=12.0, words=40)

    assert slow_open["measured"] is True
    assert slow_open["window_seconds"] == pytest.approx(3.2, abs=0.01)
    assert any("3.2s" in line and "12.0s" in line for line in slow_open["findings"])
    assert any("slow open" in line for line in slow_open["findings"])

    on_pattern = hook.measured_against(budget, seconds=3.4, words=15)
    assert not any("slow open" in line for line in on_pattern["findings"])


def test_the_gate_says_when_it_has_nothing_to_judge_against():
    """A missing comparison that looks like a passed comparison is how a measurement stops
    being read. The unmeasured channel gets a sentence saying there is nothing, not an
    empty block that reads as agreement."""
    found = hook.measured_against(writing_budget(None), seconds=14.0, words=36)

    assert found["measured"] is False
    assert found["learned"] == {}
    assert found["findings"]
    assert "nothing is measured" in found["findings"][0]


def test_the_gate_never_claims_to_know_what_kind_of_hook_it_is(fast_profile):
    """The refusal. What kind of opening this is — a question, a cold detail, a flat
    contradiction — is a fact about meaning, and the only pass that reaches a reference's
    narration reads timings. Silence here would read as 'this channel has no pattern'
    rather than 'this cannot be measured'."""
    learned = hook.measured_against(writing_budget(fast_profile), seconds=3.3, words=14)["learned"]

    assert "hook_type" in learned["not_claimed"]
    assert "meaning" in learned["not_claimed"]["hook_type"]
    assert not any(key in learned for key in ("type", "kind", "opening_line", "text"))


def test_no_wording_from_the_reference_travels_into_the_prompt(fast_profile):
    """A length and a pace are what were measured, so a length and a pace is what gets
    passed on. The transcript is sitting right there and quoting an opening line to a
    model is the strongest instruction available — which is the problem: it comes back
    rewritten eight words at a time, off somebody else's channel."""
    block = method.hook_shape(writing_budget(fast_profile).hook)

    assert block
    for phrase in ("Your first three seconds", "Nobody tells you that"):
        assert phrase not in block


def test_the_opening_block_is_absent_rather_than_hedged_for_an_unmeasured_channel():
    """An instruction whose content is 'disregard this' teaches the model that the
    numbered rules are negotiable, and the one it skips next is not this one."""
    assert method.hook_shape({}) == ""
    assert method.hook_shape(None) == ""
    assert method.hook_shape(writing_budget(None).hook) == ""


def test_the_measured_opening_block_is_not_one_of_the_house_rules():
    """`METHOD` is Forgecast's own craft and is true of every script. This is a
    measurement of one channel, and `MethodBlock.body` renders an unfilled placeholder
    rather than raising — so a channel with no reference would be sent a bare
    `$hook_seconds`."""
    assert "hook_shape" not in method.METHOD
    assert method.HOOK_SHAPE not in method.BLOCKS
    assert "$" not in method.render(target_seconds=480)


# ============================================================ what it refuses to adopt


def test_a_reference_too_thin_to_measure_falls_back_and_says_so():
    """Fifteen words is enough to transcribe and nowhere near enough to write a channel's
    scripts against. `semantic` already refuses to section it; this refuses to adopt it,
    on `SourcingProfile.usable`'s gate rather than on a second opinion about it."""
    profile = measure_narrative([_measured(THIN, 8.0)])
    budget = writing_budget(profile.as_dict())

    assert not profile.usable
    assert budget.measured is False
    assert budget.words_per_second == WORDS_PER_SECOND
    assert budget.hook_seconds == HOOK_SECONDS
    assert "shipped" in budget.note


def test_a_reference_nobody_could_transcribe_carries_the_reason_up():
    """`faster-whisper` is the optional `edit` extra and most installs do not have it. The
    learn keeps going and the fallback has to name which tool is missing — the operator's
    next move is to install it, and "no measurement" does not tell them that."""
    blocks = [semantic.Narrative(notes=["transcription needs Video editing tools — "
                                        "install them in Setup"]).as_dict()]
    profile = measure_narrative(blocks)

    assert not profile.usable
    assert any("Video editing tools" in note for note in profile.notes)
    assert "Video editing tools" in writing_budget(profile.as_dict()).note


def test_a_read_rate_outside_human_range_is_clamped_and_the_clamp_is_reported():
    """A transcript divided by a runtime that came back short reads as nine words a
    second. Inherited, that is a script three times too long — `sourcing.MAX_SHARE`'s
    reason, applied to a rate."""
    impossible = dict(_measured(BREATHLESS, 45.0), runtime_seconds=12.0)
    profile = measure_narrative([impossible])

    assert profile.words_per_second == editing.MAX_RATE
    assert any("held at" in note for note in profile.notes)


def test_a_reference_that_never_pauses_still_gives_a_rate_and_keeps_the_shipped_window():
    """Two measurements, two gates. A read with no boundary in it has a perfectly good
    words-per-second and no opening beat at all, and collapsing the two would throw away a
    measured rate because the narrator did not stop for breath."""
    breathless = _narration([
        (index * 3.0, index * 3.0 + 2.9,
         "One two three four five six seven eight nine ten eleven twelve.")
        for index in range(8)
    ])
    profile = measure_narrative([_measured(breathless, 24.0)])
    budget = writing_budget(profile.as_dict())

    assert profile.hooks_measured == 0
    assert budget.measured is True
    assert budget.words_per_second != WORDS_PER_SECOND
    assert budget.hook_seconds == HOOK_SECONDS
    assert budget.hook == {}
    assert "reference could be sectioned" in budget.note


# ============================================================ pooling across references


def test_the_rate_is_pooled_across_references_and_the_hook_is_medianed(fast, slow):
    """Two different questions and two different reductions.

    A rate is words over seconds, so the honest figure across references is every word
    over every second — the mean of two rates gives a forty-second short the same vote as
    a twenty-minute documentary. A hook length is not a quantity to be totalled: it is a
    decision the creator makes once per video, so the question is which length they keep
    choosing, which is `learn`'s own median rule.
    """
    pooled = measure_narrative([fast, slow])

    words = fast["words"] + slow["words"]
    runtime = fast["runtime_seconds"] + slow["runtime_seconds"]
    assert pooled.words_per_second == pytest.approx(words / runtime, abs=0.01)
    assert pooled.words_per_second != pytest.approx(
        (fast["words_per_second"] + slow["words_per_second"]) / 2, abs=0.01)

    assert pooled.hook_seconds == pytest.approx((3.2 + 9.0) / 2, abs=0.01)
    assert pooled.references == 2
    assert pooled.hooks_measured == 2
    assert pooled.confidence == "high"


def test_the_opening_is_reported_against_the_pace_of_the_rest(fast_profile):
    """Measured arithmetic, and the one pattern the evidence honestly supports: a creator
    who opens a quarter faster than they run is doing something a writer can copy."""
    pattern = writing_budget(fast_profile).hook

    assert pattern["words_per_second"] > pattern["body_words_per_second"]
    assert "faster" in pattern["opens"]
    assert f"{pattern['seconds']:.1f}s" in pattern["sentence"]


# ============================================================ the wiring, and the floor


def test_the_writer_the_gate_and_the_ledger_read_one_function():
    """One function, three callers. Three copies of this rule would be three answers to
    how long a script is, and the one the money model held would be the wrong one — which
    is what the two literals in `graph/pipelines.py` and `nodes/content.py` already were.
    """
    assert content.writing_budget is editing.writing_budget
    assert hook.writing_budget is editing.writing_budget
    assert pipelines.writing_budget is editing.writing_budget
    # And one shipped default underneath them, rather than a literal per file with a test
    # holding the copies together.
    assert content.WORDS_PER_SECOND is editing.WORDS_PER_SECOND
    assert pipelines.WORDS_PER_SECOND is editing.WORDS_PER_SECOND
    assert hook.HOOK_SECONDS is editing.HOOK_SECONDS
    assert pipelines.HOOK_SECONDS is editing.HOOK_SECONDS


def test_a_channel_with_no_learned_reference_writes_exactly_what_it_wrote_before():
    """The upgrade case, and the one that has to be boring. Most channels have no
    reference and none of them should see a script, a hook window or a hold move because
    this was added."""
    for absent in (None, {}, {"transcribed": False}):
        budget = writing_budget(absent)
        assert budget.words_per_second == 2.6
        assert budget.hook_seconds == 15.0
        assert budget.words_for(480) == 1248

    for name in ("faceless_longform", "faceless_shorts"):
        plain = {node.key: node.estimated_units
                 for node in pipelines.get_pipeline(name).nodes}
        passed = {node.key: node.estimated_units
                  for node in pipelines.get_pipeline(name, narrative=None).nodes}
        assert plain == passed, name


def test_the_hook_reserve_is_priced_on_the_window_the_gate_actually_cuts(fast_profile):
    """A hold priced on fifteen seconds for a gate that cuts three is a hold nobody can
    reconcile against the bill — and the reverse, on a slow channel, is a hold that does
    not cover its own node."""
    plain = {node.key: node for node in pipelines.get_pipeline("faceless_longform").nodes}
    measured = {node.key: node for node in
                pipelines.get_pipeline("faceless_longform", narrative=fast_profile).nodes}

    budget = writing_budget(fast_profile)
    assert measured["hook"].estimated_units == pytest.approx(
        budget.hook_seconds * budget.words_per_second * 5.5)
    assert plain["hook"].estimated_units == pytest.approx(
        HOOK_SECONDS * WORDS_PER_SECOND * 5.5)
    assert measured["hook"].estimated_units < plain["hook"].estimated_units


# ============================================================ reaching the style


def test_the_measurement_rides_on_the_style_not_the_channel(fast_profile):
    """`sourcing`'s reasoning, unchanged: it is a property of the look, not of the
    account. Learn a creator once, apply that style to three channels, and all three write
    to that creator's pace — two channels modelled on one reference cannot drift apart,
    because there is one measurement."""
    style = editing.EditingStyle(name="Ref", narrative=dict(fast_profile))
    profile = style.to_channel_profile({"tone": "kept"})

    assert profile["narrative"]["words_per_second"] > WORDS_PER_SECOND
    assert profile["tone"] == "kept", "applying a style must not discard what it does not own"
    assert writing_budget(profile["narrative"]).hook_seconds == pytest.approx(3.2, abs=0.01)


def test_a_style_with_no_narrative_does_not_wipe_a_channels():
    """A style learned before this field existed carries an empty dict, and writing that
    would silently return a working channel to the shipped constants."""
    kept = editing.EditingStyle(name="Old").to_channel_profile(
        {"narrative": {"words_per_second": 3.4}})
    assert kept["narrative"]["words_per_second"] == 3.4


def test_learning_a_style_reads_the_semantic_block_off_every_reference(fast, slow):
    """The join this whole exercise is about. `learn` takes measured profiles and reduces
    them into a style; the `semantic` block has been sitting on every one of those profiles
    since it was added, and nothing reached for it."""
    style = editing.learn(
        [{"render_spec": {}, "semantic": fast, "source": {"path": "a.mp4"}},
         {"render_spec": {}, "semantic": slow, "source": {"path": "b.mp4"}}],
        name="Two references")

    assert style.narrative["references"] == 2
    assert style.narrative["hooks_measured"] == 2
    assert style.narrative["words_per_second"] != WORDS_PER_SECOND
    # And it survives the trip to disk and back, like every other field on a style.
    assert editing.EditingStyle.from_dict(style.as_dict()).narrative == style.narrative


def test_a_style_learned_from_references_nobody_transcribed_stays_empty():
    """`{}` rather than a profile full of defaults, so `to_channel_profile` leaves a
    working channel alone. A style learned before this existed must look the same as one
    learned on a machine with no transcriber."""
    style = editing.learn([{"render_spec": {}, "semantic": None}], name="No audio")
    assert style.narrative == {}
    assert "narrative" not in style.to_channel_profile({})


def test_a_vision_providers_semantic_block_contributes_nothing(fast):
    """The socket's original purpose is still open: a caller holding a vision provider's
    description of the shots may pass one, and it has no words and no runtime in it. It
    must not be counted as a reference that was measured and came back at zero."""
    supplied = {"described_by": "a vision provider", "shots": []}
    style = editing.learn(
        [{"render_spec": {}, "semantic": supplied},
         {"render_spec": {}, "semantic": fast}], name="Mixed")

    assert style.narrative["references"] == 1
    assert style.narrative["words_per_second"] == pytest.approx(
        fast["words"] / fast["runtime_seconds"], abs=0.01)
