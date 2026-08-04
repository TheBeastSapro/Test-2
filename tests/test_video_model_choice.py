"""Choosing the image-to-video model: the door, not the room behind it.

`VIDEO_MODELS` has carried a per-model price table for as long as it has existed, and the
skills shipped beside it told the agent to "pick per shot, weighing fidelity against
per-second cost". Nothing could. The registry built every provider as `cls(api_key)`, so
`FalVideoProvider` took its module-level default and there was no per-run, per-channel or
per-shot path to any other slug. Eleven priced alternatives, one reachable.

That matters more here than anywhere else in the app: image-to-video is about 90% of a
long-form video's cost, and the same eighty-shot script runs from about $15 to about $98
depending on this one field. So these tests are mostly about reachability — the settings
page offering it, the save changing the row, the row reaching a run's registry — because
the arithmetic was never the part that was broken.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from forgecast.api.main import create_app
from forgecast.auth import create_access_token
from forgecast.models import Channel, User
from forgecast.providers.media import (
    DEFAULT_VIDEO_MODEL,
    VIDEO_MODELS,
    video_catalogue,
)
from forgecast.providers.registry import ProviderRegistry, _takes_model

FLOW = "fal-ai/veo3.1/lite/image-to-video"


@pytest.fixture
def client(user: User):
    with TestClient(create_app()) as test_client:
        test_client.headers["Authorization"] = f"Bearer {create_access_token(user)}"
        yield test_client


# ------------------------------------------------------------------ the catalogue


def test_the_catalogue_prices_a_whole_video_not_a_second():
    """Per-second rates rank these models in the wrong order, and not by a little.

    Durations are enums. Kling offers five seconds or ten and nothing between, so a
    six-second scene is billed at ten and over a third of the spend never reaches the
    screen. Ranked on rate Kling sits mid-table; ranked on what a video costs it is near
    the top, above two models with a higher per-second price.
    """
    rows = {row["slug"]: row for row in video_catalogue()}
    kling = rows["fal-ai/kling-video/v2.6/pro/image-to-video"]
    veo_fast = rows["fal-ai/veo3.1/fast/image-to-video"]

    assert kling["usd_per_second"] < veo_fast["usd_per_second"]
    assert kling["billed_ratio"] > 1.3
    # Only about 7% wasted, because 4/6/8 matches how scenes actually run.
    assert veo_fast["billed_ratio"] < 1.1


def test_the_catalogue_is_ordered_by_what_a_video_costs():
    rows = video_catalogue()
    assert rows == sorted(rows, key=lambda row: row["typical_video_usd"])
    # The spread is the reason this setting exists at all.
    assert rows[-1]["typical_video_usd"] > rows[0]["typical_video_usd"] * 5


def test_superseded_models_are_priced_but_never_offered():
    """Old runs still have to price correctly when they are re-read.

    Offering them is a different question: veo3 costs what veo3.1 costs and is the
    earlier model, so choosing one is choosing worse output at the same rate.
    """
    offered = {row["slug"] for row in video_catalogue()}
    assert "fal-ai/veo3/image-to-video" in VIDEO_MODELS
    assert "fal-ai/veo3/image-to-video" not in offered
    assert DEFAULT_VIDEO_MODEL in offered


def test_the_default_is_marked_so_the_page_can_say_which_one_it_is():
    marked = [row for row in video_catalogue() if row["is_default"]]
    assert [row["slug"] for row in marked] == [DEFAULT_VIDEO_MODEL]
    # With nothing chosen, the default is what shows as selected.
    assert [row["slug"] for row in video_catalogue() if row["chosen"]] == [
        DEFAULT_VIDEO_MODEL]
    assert [row["slug"] for row in video_catalogue(FLOW) if row["chosen"]] == [FLOW]


# ------------------------------------------------------------------ the door


def test_the_channel_page_offers_the_models_and_saves_one(
    client, session: Session, channel: Channel,
):
    """The whole defect, in one test: it has to be reachable and it has to stick."""
    body = client.get(f"/c/{channel.id}").text
    assert 'name="video_model"' in body
    assert FLOW in body
    # Named for what an operator is looking for, not for its URL slug.
    assert "Google Flow" in body

    answer = client.post(f"/c/{channel.id}/video-model", data={"video_model": FLOW},
                         follow_redirects=False)
    assert answer.status_code == 303
    session.expire_all()
    assert session.get(Channel, channel.id).video_model == FLOW


def test_the_page_shows_the_cost_of_a_video_rather_than_a_rate(client, channel: Channel):
    """$0.07 a second means nothing to somebody deciding. $43.75 a video does."""
    body = client.get(f"/c/{channel.id}").text
    assert "a video" in body
    assert "14.70" in body  # Veo 3.1 Lite, the cheapest
    assert "98.00" in body  # Veo 3.1 standard, the dearest


def test_an_unknown_slug_is_refused_rather_than_stored(client, channel: Channel):
    """Unlike a scripting method there is no keep-it-anyway case.

    A slug outside the catalogue is priced from its family at the dearest known sibling,
    so storing one silently moves the channel onto the conservative estimate for every
    future run.
    """
    answer = client.post(f"/c/{channel.id}/video-model",
                         data={"video_model": "fal-ai/not-a-model/image-to-video"},
                         follow_redirects=False)
    assert answer.status_code == 400


def test_empty_is_allowed_and_means_the_app_default(
    client, session: Session, channel: Channel,
):
    """Clearing the field is a choice, not a missing value."""
    channel.video_model = FLOW
    session.commit()

    answer = client.post(f"/c/{channel.id}/video-model", data={"video_model": ""},
                         follow_redirects=False)
    assert answer.status_code == 303
    session.expire_all()
    assert session.get(Channel, channel.id).video_model == ""


# ------------------------------------------------------------------ the run


def test_a_chosen_model_reaches_the_provider_the_run_uses():
    registry = ProviderRegistry(mode="live", user_keys={"fal": "k"},
                                models={"video": FLOW})
    assert registry.video().model == FLOW
    assert registry.video().usd_per_second == 0.03


def test_choosing_nothing_still_gets_the_default():
    registry = ProviderRegistry(mode="live", user_keys={"fal": "k"})
    assert registry.video().model == DEFAULT_VIDEO_MODEL


def test_two_channels_in_one_process_do_not_share_a_provider():
    """The model is in the cache key, and it has to be.

    Without it the second channel is handed the first channel's provider and renders on
    a model nobody chose — silently, and at the other model's price.
    """
    first = ProviderRegistry(mode="live", user_keys={"fal": "k"}, models={"video": FLOW})
    second = ProviderRegistry(mode="live", user_keys={"fal": "k"},
                              models={"video": "fal-ai/sora-2/image-to-video"})
    assert first.video().model != second.video().model


def test_an_adapter_that_takes_no_model_is_not_handed_one():
    """Asked rather than assumed.

    Several adapters here take only a key. Handing one of those a second positional
    argument is a TypeError several minutes into a run that has already paid for a
    script and a voiceover.
    """
    from forgecast.providers.llm_cli import ClaudeCliProvider
    from forgecast.providers.media import FalVideoProvider

    assert _takes_model(FalVideoProvider)
    assert not _takes_model(ClaudeCliProvider)


def test_the_run_carries_the_channels_choice_into_its_registry():
    """The snapshot is the only thing a node sees, so the field has to be on it."""
    from forgecast.graph.engine import ChannelSnapshot

    snapshot = ChannelSnapshot(
        id=1, name="c", niche="n", language="en", voice_id="", avatar_id="",
        aspect_ratio="16:9", target_duration_seconds=480, style_profile={},
        video_model=FLOW,
    )
    assert snapshot.video_model == FLOW
    # Defaulted, so every older construction of this snapshot still works and means
    # "let the app default decide".
    plain = ChannelSnapshot(
        id=1, name="c", niche="n", language="en", voice_id="", avatar_id="",
        aspect_ratio="16:9", target_duration_seconds=480, style_profile={},
    )
    assert plain.video_model == ""
