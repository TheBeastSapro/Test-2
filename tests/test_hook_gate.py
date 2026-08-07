"""The Hook Gate: watch fifteen seconds before commissioning eight minutes.

A run's order of spending was upside down relative to its order of risk. The script was
approved as *text*, then the app bought a full voiceover and eighty generated clips, and
only at the end — watching the finished file — did anybody find out whether the opening
landed. By then the whole video was paid for.

Most of what is worth testing here is placement, because that is where the value is: a
gate on the opening that sits after the narration has been bought is a gate that saves
half of what it could.
"""

from __future__ import annotations

from pathlib import Path

import forgecast.nodes  # noqa: F401  - importing registers every handler
from forgecast.credits import estimate_node
from forgecast.graph import pipelines
from forgecast.graph.engine import registry
from forgecast.nodes import hook

PIPELINES = ("faceless_longform", "faceless_shorts")


def _nodes(name: str) -> dict:
    return {node.key: node for node in pipelines.get_pipeline(name).nodes}


def _scene(index: int, seconds: float, words: str = "some narration here") -> dict:
    return {"index": index, "seconds": seconds, "narration": words,
            "visual_prompt": f"a shot for scene {index}", "visual_kind": "still"}


# ------------------------------------------------------------------ registration


def test_the_handler_is_registered_and_in_both_pipelines():
    assert "hook" in registry
    for name in PIPELINES:
        assert "hook" in _nodes(name), name


def test_the_pipeline_and_the_node_agree_on_the_window():
    """The literal is repeated in `pipelines.py` rather than imported — importing it
    would close a cycle, since `nodes/__init__` imports `hook`, `hook` imports
    `graph.engine`, and `graph.engine` imports `pipelines`. `models.py` uses the same
    trick for HOUSE_SLUG, and names the test that keeps the two honest. This is it."""
    assert pipelines.HOOK_SECONDS == hook.HOOK_SECONDS


# ------------------------------------------------------------------ placement


def test_rejecting_the_hook_saves_the_whole_voiceover():
    """A gate on the opening placed after the narration is a gate that has already bought
    five thousand characters of a script about to be rewritten."""
    for name in PIPELINES:
        assert "hook" in _nodes(name)["voice"].depends_on, name


def test_rejecting_the_hook_saves_the_whole_batch():
    """The Sample Gate is downstream of this one, so nothing that spends on generated
    video starts before the opening is approved."""
    for name in PIPELINES:
        assert "hook" in _nodes(name)["sample"].depends_on, name


def test_planning_still_runs_on_the_script_alone():
    """`broll_plan` is free and costs nothing to throw away. Having the shot list in hand
    makes a rejected hook cheaper to act on rather than more expensive, so gating it
    would trade something for nothing."""
    for name in PIPELINES:
        assert _nodes(name)["broll_plan"].depends_on == ("script",), name


def test_it_waits_for_the_cast_voice():
    """A hook read in a different voice from the video approves something nobody is
    going to hear."""
    for name in PIPELINES:
        assert "voice_casting" in _nodes(name)["hook"].depends_on, name


def test_it_stops_for_approval():
    for name in PIPELINES:
        assert _nodes(name)["hook"].requires_approval is True, name


def test_the_two_gates_ask_different_questions_and_both_survive():
    """This one asks whether the opening works — the words, the voice, the pace. The
    Sample Gate asks whether the look works. A hook that reads badly is rewritten; a look
    that comes back wrong is re-prompted. One gate covering both would be approved for
    one reason while the other went unexamined."""
    for name in PIPELINES:
        nodes = _nodes(name)
        assert nodes["hook"].requires_approval
        assert nodes["sample"].requires_approval
        assert nodes["hook"].depends_on != nodes["sample"].depends_on


# ------------------------------------------------------------------ the money


def test_the_gate_costs_a_fraction_of_what_it_protects():
    """Roughly fifteen seconds of narration and a couple of stills, against the full
    voiceover and eighty clips."""
    gate = estimate_node("hook", pipelines.HOOK_SECONDS * pipelines.WORDS_PER_SECOND * 5.5)
    protected = (estimate_node("voice", 480 * pipelines.WORDS_PER_SECOND * 5.5).credits
                 + estimate_node("shots", 80).credits)
    assert protected > gate.credits * 50


def test_it_is_priced_on_narration_because_that_is_what_it_buys():
    """The stills are inside the base fee — two images at the thumbnail rate is 10
    credits against the ~70 the narration costs, and a second unit on a node that already
    has one is arithmetic nobody can check against a bill."""
    per_thousand = estimate_node("hook", 1000).credits - estimate_node("hook", 0).credits
    assert per_thousand == estimate_node("voice", 1000).credits - estimate_node(
        "voice", 0).credits


# ------------------------------------------------------------------ what it cuts


def test_scenes_are_taken_whole_rather_than_cut_at_fifteen_seconds():
    """Half a sentence tests nothing, and a hook judged on a truncated clause is judged
    on an artefact of the cut."""
    scenes = [_scene(0, 6.0), _scene(1, 6.0), _scene(2, 6.0), _scene(3, 6.0)]
    taken = hook.hook_scenes(scenes)
    assert [scene["index"] for scene in taken] == [0, 1, 2]
    assert sum(scene["seconds"] for scene in taken) >= hook.HOOK_SECONDS


def test_a_single_long_opening_scene_is_the_hook():
    """Returning nothing there would skip the gate on exactly the script that most needs
    it: one opening scene running past fifteen seconds is a slow open, and a slow open is
    the failure this gate is looking for."""
    taken = hook.hook_scenes([_scene(0, 40.0), _scene(1, 6.0)])
    assert [scene["index"] for scene in taken] == [0]


def test_a_run_of_very_short_scenes_does_not_become_the_first_act():
    """A "hook" running to forty seconds because the script opens with eight short scenes
    is a gate that costs what it is guarding."""
    scenes = [_scene(index, 2.0) for index in range(10)]
    taken = hook.hook_scenes(scenes)
    assert len(taken) == hook.MAX_HOOK_SCENES


def test_at_least_one_scene_always_comes_back():
    assert len(hook.hook_scenes([_scene(0, 0.5)])) == 1
    assert hook.hook_scenes([]) == []


# ------------------------------------------------------------------ the node's shape


def test_it_uses_stills_rather_than_generated_video():
    """Generated video here would cost roughly ten times as much to answer a question
    stills already answer, and would answer the Sample Gate's question a second time —
    badly, on three shots."""
    import inspect

    source = inspect.getsource(hook)
    assert "registry.image()" in source
    assert "registry.video()" not in source
    assert "generate_clip" not in source


def test_a_missing_image_provider_does_not_stop_the_gate():
    """A hook with no picture still tests the words, the voice and the pace — three of
    the four things this gate is for."""
    import inspect

    source = inspect.getsource(hook.hook_node)
    guarded = source.split("registry.image()", 1)[1][:600]
    assert "warning" in guarded
    assert "raise" not in guarded


def test_the_scene_length_comes_from_the_audio_rather_than_the_estimate():
    """A hook cut to the script's estimate has the picture change mid-word, which reads
    as a fault in the edit rather than in the timing."""
    import inspect

    source = inspect.getsource(hook.hook_node)
    assert "spoken.duration_seconds" in source


def test_the_hook_is_captioned_exactly_as_the_render_will_be():
    """Captions are part of what is being judged — a hook that reads well and captions
    badly fails on the platform where most of it is watched muted.

    This used to assert `subtitles=True`, which was right for as long as every channel
    burned captions. It stopped being right once the decision came off the reference:
    on a channel measured as caption-free, pinning the hook on meant the operator
    approved an opening with a caption track and the render produced one without, so
    the single frame they were given to judge was the one guaranteed not to match. The
    rule is not "burned" — it is "the same as the render".
    """
    import inspect

    source = inspect.getsource(hook.hook_node)
    assert "subtitles=True" not in source
    assert "subtitles=burns_captions(" in source


def test_the_approval_is_made_against_what_it_commits_to():
    """An approval with no cost beside it is a formality. The Sample Gate surfaces the
    same shape for the same reason."""
    import inspect

    source = inspect.getsource(hook.hook_node)
    assert "remaining_scenes" in source
    assert "remaining_seconds" in source


# ------------------------------------------------------------------ end to end


def test_the_node_produces_a_watchable_hook(tmp_path):
    """The gate is worth nothing if what it surfaces is not a real clip.

    Mock providers, real ffmpeg: the assembly, the caption burn and the mux are this
    node's actual work, and they are the part that breaks.
    """
    import asyncio
    import subprocess

    from forgecast.graph.engine import ChannelSnapshot, NodeContext
    from forgecast.providers import registry

    scenes = [_scene(0, 5.0, "Nobody noticed when the first cable went dark."),
              _scene(1, 5.0, "Then the second one did, four hundred miles away."),
              _scene(2, 5.0, "By Friday, three countries were offline.")]

    context = NodeContext(
        run_id=1,
        topic="Why deep-sea cables keep breaking",
        options={},
        node_key="hook",
        node_type="hook",
        params={},
        attempts=0,
        channel=ChannelSnapshot(
            id=1, name="Test Channel", niche="infrastructure documentary", language="en",
            voice_id="", avatar_id="", aspect_ratio="16:9",
            target_duration_seconds=480, style_profile={},
            # 720 so the test render is quick; the node reads the channel like any other.
            video_height=720,
        ),
        registry=registry.ProviderRegistry(mode="mock"),
        workdir=tmp_path / "work",
        upstream_outputs={
            "script": {"title": "The cables that hold the internet up",
                       "scenes": scenes, "word_count": 900},
            # As the casting gate leaves it. The hook reads in the voice that was cast,
            # because a hook read in a different voice from the video approves something
            # nobody is going to hear.
            "voice_casting": {"selected_voice_id": "voice-1", "selected": "Narrator"},
        },
    )

    result = asyncio.run(hook.hook_node(context))

    made = Path(result.output["hook_path"])
    assert made.exists(), "the node reported a hook it did not write"

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-show_entries", "stream=width,height,codec_type", "-of", "csv=p=0", str(made)],
        capture_output=True, text=True, timeout=120, check=True)
    # Both streams present: a hook with no audio tests neither the voice nor the pace.
    assert "audio" in probe.stdout
    assert "1280,720" in probe.stdout

    # It says what proceeding commits to, which is what makes the approval a decision.
    assert result.output["commits"]["remaining_scenes"] == 0
    assert result.output["words"] > 0


def test_a_hook_is_cut_from_the_opening_and_leaves_the_rest_uncommitted(tmp_path):
    """The number the operator is approving against: what is still to be bought."""
    import asyncio

    from forgecast.graph.engine import ChannelSnapshot, NodeContext
    from forgecast.providers import registry

    scenes = [_scene(index, 8.0, f"Scene {index} narration.") for index in range(10)]
    context = NodeContext(
        run_id=1, topic="t", options={}, node_key="hook", node_type="hook",
        params={}, attempts=0,
        channel=ChannelSnapshot(
            id=1, name="c", niche="n", language="en", voice_id="", avatar_id="",
            aspect_ratio="16:9", target_duration_seconds=480, style_profile={},
            video_height=720),
        registry=registry.ProviderRegistry(mode="mock"),
        workdir=tmp_path / "work",
        upstream_outputs={"script": {"scenes": scenes, "word_count": 300},
                          "voice_casting": {"selected_voice_id": "voice-1"}},
    )
    result = asyncio.run(hook.hook_node(context))

    # Two eight-second scenes cover the window; eight are left to pay for.
    assert result.output["commits"]["remaining_scenes"] == 8
    assert result.output["commits"]["remaining_seconds"] == 64.0
