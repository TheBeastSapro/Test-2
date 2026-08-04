"""Modelling a channel on a creator means measuring that creator.

The failure this holds shut is invisible from the outside, which is what made it
expensive. "Set up a channel modelled on @them" read their titles, view counts and
median length — metadata — and stopped. Nothing ever watched a video. The channel was
created with no learned style, every run afterwards logged "no reference has been
learned for this channel", and the script came out at the shipped 2.6 words a second
with a 15-second hook window.

Nothing errored. The run completed, the script was competent, and it was written to a
house template with somebody else's view counts stapled to the front. The operator had
to know to ask for a style as a separate step, and the app never said so.
"""

from __future__ import annotations

import pytest

from forgecast.agent.studio import Studio


@pytest.fixture
def studio(user):
    return Studio(user_id=user.id)


def test_a_channel_modelled_on_nobody_is_created_without_measuring(studio):
    """The plain case still works and still costs nothing: no reference, no decode."""
    made = studio.create_channel("Plain", niche="test")
    assert made["created"]
    assert "style_learned" not in made, "nothing was modelled, so nothing was measured"


def test_modelling_measures_the_reference_rather_than_borrowing_its_numbers(
    studio, monkeypatch
):
    """The whole point. `model_on` must reach `learn_style`, and the style must be
    applied to the channel that was just made — a measurement saved to a shelf and not
    attached is the same as no measurement."""
    seen: dict = {}

    monkeypatch.setattr(Studio, "best_videos",
                        lambda self, ref, count=3: ["https://youtu.be/aaa",
                                                    "https://youtu.be/bbb"])

    def fake_learn(self, references, *, name="", upgrade=True, max_seconds=0, on_note=None):
        seen["references"] = list(references)
        return {"learned": name or "Ref", "key": "ref-style", "summary": "9.0s shots",
                "measured": len(list(references)), "failures": []}

    def fake_apply(self, style, channel):
        seen["applied"] = (style, channel)
        return {"applied": style}

    monkeypatch.setattr(Studio, "learn_style", fake_learn)
    monkeypatch.setattr(Studio, "apply_style", fake_apply)

    made = studio.create_channel("Modelled", niche="horror",
                                 model_on="https://youtube.com/@them")

    assert made["created"] and made["style_learned"]
    assert seen["references"] == ["https://youtu.be/aaa", "https://youtu.be/bbb"]
    # style first, channel second — reversed, this returns "no such style" naming a
    # channel id, which reads as a broken channel rather than a swapped argument.
    assert seen["applied"] == ("ref-style", made["id"])
    assert made["measured_from"]


def test_a_reference_that_cannot_be_read_still_creates_the_channel(studio, monkeypatch):
    """A channel that exists with no style can be measured later. A channel that failed
    to be created cannot be anything."""
    monkeypatch.setattr(Studio, "best_videos", lambda self, ref, count=3: [])

    made = studio.create_channel("Unreadable", model_on="https://youtube.com/@ghost")
    assert made["created"]
    assert made["style_learned"] is False
    assert "no learned style" in made["style_note"]


def test_a_failed_measurement_says_so_instead_of_reading_as_measured(studio, monkeypatch):
    """The silent version of this is the bug: a channel that looks modelled, writes to
    the house method, and says nothing about the difference."""
    monkeypatch.setattr(Studio, "best_videos", lambda self, ref, count=3: ["https://y/1"])
    monkeypatch.setattr(
        Studio, "learn_style",
        lambda self, refs, **kw: {"error": "every reference failed to decode"})

    made = studio.create_channel("Broken", model_on="https://youtube.com/@them")
    assert made["created"]
    assert made["style_learned"] is False
    assert "house method" in made["style_note"]


def test_the_agent_can_actually_pass_a_reference_to_measure():
    """A parameter the tool schema does not expose is a parameter the agent cannot use,
    which is how a capability ships and never runs."""
    import inspect

    from forgecast.agent import tools

    source = inspect.getsource(tools)
    assert '"model_on": str' in source, "the tool schema must expose it"
    assert "model_on=args.get" in source, "and the handler must forward it"
