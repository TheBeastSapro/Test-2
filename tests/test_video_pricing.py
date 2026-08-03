"""Per-model image-to-video pricing: the catalogue, and the arithmetic that reads it.

One flat per-second rate was wrong by construction. The models this app routes to span
$0.03 to $0.20 a second on the prices published on 2026-08-03 — and the operational skill's
own table claimed $0.01 to $0.40, which is the same point made twice: the spread is large
and the numbers move. What matters is the direction of the error. A reserve taken too low
is a run that stops in the middle of a batch with money already spent and no way to
recover it, so the tests below pin the conservative choices rather than the convenient ones.
"""

from __future__ import annotations

import httpx
import pytest

from forgecast.credits import USD_PER_CREDIT
from forgecast.providers import media

MARKUP = media._MARKUP


def credits_for(usd: float) -> int:
    return max(1, round(usd * MARKUP / USD_PER_CREDIT))


# ------------------------------------------------------------------- the catalogue


def test_every_entry_is_internally_coherent():
    for slug, model in media.VIDEO_MODELS.items():
        assert model.usd_per_second > 0, slug
        assert 0 < model.sample_seconds <= model.max_seconds, slug
        # The resolution or audio tier the figure belongs to, or the reader cannot tell
        # whether a 4K render is priced by this row.
        assert model.note, slug
        assert "image-to-video" in slug


def test_the_catalogue_spans_a_range_no_flat_rate_could_cover():
    rates = [model.usd_per_second for model in media.VIDEO_MODELS.values()]
    assert max(rates) / min(rates) > 5
    # And the default is a cheap workhorse rather than the dearest thing available, since
    # every shot that nobody chose a model for lands on it.
    assert media.video_model(media.DEFAULT_VIDEO_MODEL).usd_per_second <= 0.1


def test_the_default_is_an_image_to_video_endpoint():
    """A text-to-video slug handed a conditioning still either ignores it — billing for a
    clip of the wrong subject — or rejects the submission."""
    assert "image-to-video" in media.DEFAULT_VIDEO_MODEL
    assert media.DEFAULT_VIDEO_MODEL in media.VIDEO_MODELS


def test_a_six_second_minimum_is_recorded_where_it_exists():
    """The Sample Gate renders at the model's shortest duration, so five is not universal.

    Hard-coding five overspends on a model whose minimum is six and is rejected outright
    by one that will not accept it.
    """
    hailuo = media.video_model(
        "fal-ai/minimax/hailuo-2.3-fast/standard/image-to-video")
    assert hailuo.sample_seconds == 6.0
    assert media.video_model(
        "fal-ai/kling-video/v2.6/pro/image-to-video").sample_seconds == 5.0


# ------------------------------------------------------------- unrecognised models


def test_an_unknown_model_is_priced_at_the_ceiling_not_the_middle():
    """Erring cheap is the failure that cannot be undone.

    An over-estimate is released back when the node settles. An under-estimate is a run
    that dies partway through having already spent the provider's money.
    """
    unknown = media.video_model("some-vendor/brand-new-thing/image-to-video")
    assert unknown.usd_per_second == media.UNPRICED_MODEL.usd_per_second
    assert unknown.usd_per_second >= max(
        model.usd_per_second for model in media.VIDEO_MODELS.values())
    assert "unrecognised" in unknown.note


def test_an_unknown_variant_of_a_known_family_is_priced_from_its_siblings():
    """fal renames and adds variants faster than any table tracks.

    A `kling-video/v3.1/pro` arriving tomorrow should cost about what Kling costs, not
    what the most expensive model in the catalogue costs — an estimate that is 4x too high
    on every shot gets the estimate ignored.
    """
    guessed = media.video_model("fal-ai/kling-video/v3.1/pro/image-to-video")
    klings = [model for slug, model in media.VIDEO_MODELS.items() if "kling" in slug]
    assert guessed.usd_per_second == max(model.usd_per_second for model in klings)
    assert guessed.usd_per_second < media.UNPRICED_MODEL.usd_per_second
    assert "kling" in guessed.note
    # Conservative on duration too: the longest sample and the shortest ceiling.
    assert guessed.sample_seconds == max(model.sample_seconds for model in klings)
    assert guessed.max_seconds == min(model.max_seconds for model in klings)


def test_an_empty_model_name_still_prices_something():
    assert media.video_model("").usd_per_second > 0
    assert media.video_reserve_credits("", 5.0) > 0


# ------------------------------------------------------------- the reserve arithmetic


@pytest.mark.parametrize("slug", sorted(media.VIDEO_MODELS))
def test_the_reserve_reads_the_catalogue_rather_than_a_flat_rate(slug):
    model = media.VIDEO_MODELS[slug]
    seconds = model.sample_seconds
    assert media.video_reserve_credits(slug, seconds) == credits_for(
        model.usd_per_second * seconds)


def test_two_models_on_the_same_shot_reserve_different_amounts():
    cheap = media.video_reserve_credits(
        "fal-ai/minimax/hailuo-2.3-fast/standard/image-to-video", 10.0)
    dear = media.video_reserve_credits("fal-ai/veo3/image-to-video", 10.0)
    assert dear > cheap * 4


def test_a_sample_is_reserved_as_extra_seconds_never_folded_into_the_shot():
    """Two submissions, two charges — the skill is explicit that neither is included in
    the other, and a reserve that added the sample's seconds to the shot's duration would
    be exactly that framing expressed as money."""
    slug = "fal-ai/kling-video/v2.6/pro/image-to-video"
    model = media.VIDEO_MODELS[slug]

    without = media.video_reserve_credits(slug, 8.0)
    with_sample = media.video_reserve_credits(slug, 8.0, samples=1)
    assert with_sample == credits_for(model.usd_per_second * (8.0 + model.sample_seconds))
    assert with_sample > without

    two = media.video_reserve_credits(slug, 8.0, samples=2)
    assert two > with_sample


def test_the_quote_for_a_shot_is_two_charges_from_the_catalogue():
    provider = media.FalVideoProvider(
        "key", model="fal-ai/minimax/hailuo-2.3-fast/standard/image-to-video")
    priced = provider.sample_and_full_quote(10.0)

    # Six seconds, because that is this model's floor — not the five the skill's prose
    # uses as its example.
    assert priced.sample.seconds == 6.0
    assert priced.sample.usd == pytest.approx(0.0317 * 6, rel=1e-3)
    assert priced.remainder.seconds == 10.0
    assert len(priced.charges()) == 2
    assert "separate charges" in priced.sentence()


# --------------------------------------------------------------- the duration clamp


@pytest.mark.parametrize(("slug", "asked", "expected"), [
    ("fal-ai/kling-video/v2.6/pro/image-to-video", 5, 5),
    ("fal-ai/kling-video/v2.6/pro/image-to-video", 30, 10),      # clipped to the ceiling
    ("fal-ai/minimax/hailuo-2.3-fast/standard/image-to-video", 4, 6),   # up to the floor
    ("fal-ai/veo3/image-to-video", 10, 8),                        # veo's fixed length
    ("fal-ai/ltx-2.3/image-to-video/fast", 0, 6),                 # unset means the floor
])
def test_the_duration_is_clamped_to_what_the_endpoint_accepts(slug, asked, expected):
    """Under the floor is a rejected submission; over the ceiling is billed then truncated."""
    assert media.FalVideoProvider("key", model=slug).clamp_seconds(asked) == expected


# ------------------------------------------------------------------ the actual charge


def _stub_transport(monkeypatch, recorder: dict):
    """Answer fal's submit and the download that follows, and record the request body."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            recorder["url"] = str(request.url)
            recorder["body"] = request.read().decode()
            return httpx.Response(200, json={"video": {"url": "https://cdn.invalid/v.mp4"}})
        return httpx.Response(200, content=b"\x00\x01mp4 bytes")

    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(media.httpx, "AsyncClient", factory)


async def test_the_clip_is_billed_on_the_duration_actually_submitted(tmp_path,
                                                                    monkeypatch):
    """A four-second shot on a six-second model is charged for six.

    Settling the requested duration instead of the submitted one puts the difference on
    the house on every clip, and it is invisible: the run reports a cost that is simply
    lower than the provider's invoice.
    """
    recorder: dict = {}
    _stub_transport(monkeypatch, recorder)
    slug = "fal-ai/minimax/hailuo-2.3-fast/standard/image-to-video"
    provider = media.FalVideoProvider("key", model=slug)

    result = await provider.generate_clip("a still lake at dawn",
                                          out_path=tmp_path / "clip", seconds=4.0)

    assert '"duration":"6"' in recorder["body"]
    assert slug in recorder["url"]
    assert result.duration_seconds == 6.0
    assert result.credits == credits_for(0.0317 * 6)
    # The rate is on the artifact, so a later audit can tell which price this was settled
    # at rather than re-deriving it from a catalogue that has since moved.
    assert result.meta["usd_per_second"] == 0.0317
    assert result.meta["billed_seconds"] == 6


async def test_a_dearer_model_costs_more_credits_for_the_same_shot(tmp_path, monkeypatch):
    """The whole point of the catalogue, at the charge site rather than in an estimate."""
    recorder: dict = {}
    _stub_transport(monkeypatch, recorder)

    cheap = await media.FalVideoProvider(
        "key", model="fal-ai/minimax/hailuo-2.3-fast/standard/image-to-video"
    ).generate_clip("x", out_path=tmp_path / "a", seconds=10.0)
    dear = await media.FalVideoProvider(
        "key", model="fal-ai/veo3/image-to-video"
    ).generate_clip("x", out_path=tmp_path / "b", seconds=10.0)

    assert dear.credits > cheap.credits * 4
