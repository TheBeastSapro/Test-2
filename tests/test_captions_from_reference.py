"""Whether captions are burned is a measurement, not a default.

`EditingStyle.captions` is a majority vote over what a reference's own frames do, and
`to_render_spec()` has always emitted it. Nothing read it: both pipelines pinned
`params={"subtitles": True}` and the hook node hard-coded `subtitles=True`, so a
reference measured as caption-free had captions burned over it anyway — the measurement
was recorded and overruled inside the same run.

Found against a real channel. Its screen carries the subject's name, its dimensions and
speech-bubble jokes while the voice carries the prose, and a narration track burned
across the lower third covers all three.
"""

from __future__ import annotations

import pytest

from forgecast.graph.pipelines import burns_captions, get_pipeline

PIPELINES = ("faceless_longform", "faceless_shorts")


def _render_params(name: str, render_spec: dict | None) -> dict:
    spec = get_pipeline(name, target_seconds=120, render_spec=render_spec)
    return next(node for node in spec.nodes if node.key == "render").params


@pytest.mark.parametrize("name", PIPELINES)
def test_a_reference_that_burns_no_captions_gets_none(name):
    assert _render_params(name, {"captions": False})["subtitles"] is False


@pytest.mark.parametrize("name", PIPELINES)
def test_a_reference_that_burns_captions_still_gets_them(name):
    assert _render_params(name, {"captions": True})["subtitles"] is True


@pytest.mark.parametrize("name", PIPELINES)
def test_an_unmeasured_channel_keeps_captions(name):
    """No learned style means no measurement to honour, and captions on is both the
    safer default and what every run did before this existed."""
    assert _render_params(name, None)["subtitles"] is True
    assert _render_params(name, {})["subtitles"] is True


def test_a_spec_without_the_key_keeps_captions():
    """A style learned before this field existed must not silently lose its captions."""
    assert burns_captions({"target_shot_seconds": 3.0}) is True


def test_the_learned_style_actually_carries_the_field_the_pipeline_reads():
    """The two halves are in different modules, so the key is the contract between
    them. This is the assertion that would have caught the gap: `to_render_spec`
    emitted `captions` and the pipeline read nothing."""
    from forgecast.style.editing import EditingStyle

    spec = EditingStyle(name="measured", captions=False).to_render_spec()

    assert "captions" in spec
    assert burns_captions(spec) is False


def test_the_hook_previews_the_captions_the_render_will_produce():
    """The hook is a gate: the operator approves an opening on how it looks. Pinned on,
    it showed a caption track to a channel whose render would have none — the one frame
    they were given to judge was the one guaranteed not to match."""
    from pathlib import Path

    from forgecast import nodes

    source = (Path(nodes.__file__).parent / "hook.py").read_text(encoding="utf-8")

    assert "subtitles=True" not in source, "the hook is pinning captions on again"
    assert "subtitles=burns_captions(" in source
