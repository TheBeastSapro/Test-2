"""Routing shots to two models: the tier the planner picks, and the money it moves.

Per-channel model choice landed one change ago, and it prices a whole video at its
dearest shot's rate. That is the wrong unit. On a realistic eighty-shot script the same
460 seconds of footage is $14.70 entirely on Veo 3.1 Lite and $98.00 entirely on Veo 3.1,
and five hero shots on the second with seventy-five on the first is $21.50 — a premium
opening for a fifth of the money. One column, one provider and one rate could not say
that, so the shipped skill's advice to "pick per shot, weighing fidelity against
per-second cost" was advice with nothing behind it.

These tests are about the three places the split silently collapses back into one model,
because each of them looks like working software while it happens:

* **The planner names a slug instead of a tier.** Then it invents endpoints that do not
  exist and quotes prices for them, and both reach the operator as fact.
* **The batch resolves one provider.** Every shot renders on whichever slug it happened
  to hold, at that model's price, with nothing on the clip to say the tier was ignored.
* **The Sample Gate shows one sample for a batch running on two models.** That is the
  exact failure the gate exists to prevent, wearing the gate's own approval.

Nothing here touches a network. Where a test needs to know which endpoint a node asked
for, it hands the node a registry that records the question.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from forgecast.api.main import create_app
from forgecast.auth import create_access_token
from forgecast.graph.engine import ChannelSnapshot, NodeContext
from forgecast.models import Channel, User
from forgecast.nodes import media as media_node
from forgecast.nodes import sample as sample_node
from forgecast.providers import MediaResult, ProviderRegistry
from forgecast.providers.media import (
    DEFAULT_VIDEO_MODEL,
    HERO_TIER,
    STANDARD_TIER,
    model_for_tier,
    video_blend,
    video_catalogue,
    video_model,
    video_tier,
    video_usd,
)

LITE = "fal-ai/veo3.1/lite/image-to-video"
VEO = "fal-ai/veo3.1/image-to-video"
HAILUO = "fal-ai/minimax/hailuo-2.3-fast/standard/image-to-video"


@pytest.fixture
def client(user: User):
    with TestClient(create_app()) as test_client:
        test_client.headers["Authorization"] = f"Bearer {create_access_token(user)}"
        yield test_client


# ------------------------------------------------------------------ tier to slug


def test_a_channel_with_no_hero_model_renders_exactly_where_it_did_before():
    """The only default a cost setting is allowed to have.

    An empty hero model falls through to the batch model, so adding this column changes
    no existing channel's bill by a cent. Shipping a hero default instead would take
    every channel from what it costs today to something dearer on its next run, in
    return for a decision nobody made.
    """
    assert model_for_tier(HERO_TIER, standard=LITE, hero="") == LITE
    assert model_for_tier(STANDARD_TIER, standard=LITE, hero="") == LITE

    blend = video_blend(LITE, "")
    assert blend["usd"] == blend["standard_only_usd"]
    assert blend["upgraded"] is False


def test_a_tier_nobody_recognises_lands_on_the_cheap_model():
    """A typo in a JSON field must not be the most expensive thing in the run.

    The field is written by a language model, so "premium", a misspelling and an omitted
    key all have to land somewhere. Landing on the dear one would mean the planner could
    buy the premium model for a whole video by being vague.
    """
    for written in ("premium", "important", "", None, "STANDARD"):
        assert model_for_tier(written, standard=LITE, hero=VEO) == LITE

    # And the spellings that do mean hero are read loosely, in one place, so the node
    # and the mapping cannot disagree about what the planner wrote.
    for written in ("hero", "Hero", "  HERO ", "hero shot"):
        assert video_tier(written) == HERO_TIER
        assert model_for_tier(written, standard=LITE, hero=VEO) == VEO


def test_choosing_neither_model_still_gets_the_app_default():
    assert model_for_tier(HERO_TIER) == DEFAULT_VIDEO_MODEL
    assert model_for_tier(STANDARD_TIER) == DEFAULT_VIDEO_MODEL


# ------------------------------------------------------------------ the blend


def test_the_blend_is_the_number_the_decision_turns_on():
    """The three figures that justify the whole feature, on the same shot list.

    A page showing $14.70 and $98.00 has told the operator nothing about the choice
    between them, because nobody reads those two numbers and arrives at $21.50 for five
    hero shots. The gap between the guess and the figure is what decides whether the
    premium model is ever used at all.
    """
    assert video_blend(LITE, LITE)["usd"] == 14.70
    assert video_blend(VEO, VEO)["usd"] == 98.00
    assert video_blend(LITE, VEO)["usd"] == 21.50
    # Today's default on every shot, for scale: the split beats it and looks better on
    # the shots anybody remembers.
    assert video_blend("", "")["usd"] == 43.75


def test_the_hero_shots_are_priced_as_the_long_ones():
    """Upgrading the beats you let run, not five shots picked for being cheap.

    A hero beat is a beat with room to breathe, so it sits at the top of the duration
    spread. Pricing the blend off the short end would understate it — here by more than
    a third — and an estimate that comes in under the invoice is the one failure this
    module's pricing rules are all written against.
    """
    blend = video_blend(LITE, VEO)
    upgrade = blend["usd"] - blend["standard_only_usd"]

    # Five shots, each at the longest duration Veo 3.1 will submit, at the difference
    # between the two rates. Any other choice of five shots produces a smaller number.
    assert upgrade == pytest.approx(5 * 8.0 * (0.20 - 0.03), abs=0.01)


def test_a_hero_model_is_priced_for_the_hero_beats_rather_than_as_a_whole_video():
    """$98.00 beside a pick that costs $8.00 talks an operator out of the split.

    It is a true number answering a question the control does not ask: nobody is
    proposing to run eighty shots on the hero model, and the whole argument for having
    one is that you do not have to.
    """
    rows = {row["slug"]: row for row in video_catalogue()}
    assert rows[VEO]["typical_video_usd"] == 98.00
    assert rows[VEO]["hero_shots_usd"] == 8.00

    # And both figures come off the same five shots, so a dropdown row and the blend
    # printed under it cannot be arithmetic about two different videos.
    blend = video_blend(LITE, VEO)
    assert blend["usd"] == (blend["standard_only_usd"]
                            + rows[VEO]["hero_shots_usd"] - rows[LITE]["hero_shots_usd"])


def test_the_blend_is_billed_the_way_the_endpoints_bill():
    """Durations are enums, so `rate x seconds` is not what anything charges.

    Kling offers five seconds or ten and nothing between, so a six-second scene is a
    ten-second submission. Priced naively a mixed plan reports a saving the invoice does
    not contain — and a blend is precisely the number somebody is going to check.
    """
    # Six seconds on Kling is billed as ten; on Veo 3.1 Lite it is billed as six.
    assert video_usd(DEFAULT_VIDEO_MODEL, 6.0) == pytest.approx(0.07 * 10)
    assert video_usd(LITE, 6.0) == pytest.approx(0.03 * 6)
    # Nine seconds is past Veo's ceiling, so it bills at the ceiling rather than raising.
    assert video_usd(LITE, 9.0) == pytest.approx(0.03 * 8)


# ------------------------------------------------------------------ the planner

PROMPT = "a container ship under low cloud, long lens, flat grey water"


def _plan(by_scene: dict[int, dict]) -> dict:
    """A planner answer, in the shape `ask_json` returns it."""
    return {"shots": [{"scene_index": index, "prompt": PROMPT, **fields}
                      for index, fields in by_scene.items()]}


def _context(tmp_path: Path, *, standard: str = "", hero: str = "",
             scenes: int = 8) -> NodeContext:
    return NodeContext(
        run_id=1,
        topic="Why container ships keep getting bigger",
        options={},
        node_key="broll_plan",
        node_type="broll_plan",
        params={},
        attempts=0,
        channel=ChannelSnapshot(
            id=1, name="Test Channel", niche="shipping", language="en",
            voice_id="", avatar_id="", aspect_ratio="16:9",
            target_duration_seconds=300, style_profile={},
            video_model=standard, video_model_hero=hero,
        ),
        registry=ProviderRegistry(mode="mock"),
        workdir=tmp_path / "work",
        upstream_outputs={
            "script": {"scenes": [{"index": index, "narration": f"beat {index}",
                                   "seconds": 8.0, "visual_prompt": PROMPT}
                                  for index in range(scenes)]},
        },
    )


async def _run_plan(tmp_path, plan: dict, monkeypatch, **channel) -> dict:
    """Run `broll_plan` against a fixed planner answer."""
    async def canned(ctx, **_kwargs):
        return plan, 0, "stub-llm"

    monkeypatch.setattr(media_node, "ask_json", canned)
    result = await media_node.broll_plan_node(_context(tmp_path, **channel))
    return result.output


@pytest.mark.asyncio
async def test_the_planner_emits_a_tier_and_the_app_emits_the_model(tmp_path, monkeypatch):
    """The whole division of labour, in one assertion.

    The plan says which beats matter and the app says what that costs. A slug the planner
    wrote is either invented or out of date, and either way it is a paid submission to an
    endpoint nobody chose.
    """
    output = await _run_plan(
        tmp_path,
        _plan({0: {"kind": "video", "tier": "hero"},
                 3: {"kind": "video", "tier": "standard"}}),
        monkeypatch, standard=LITE, hero=VEO)

    animated = [shot for shot in output["shots"] if shot["kind"] == "video"]
    assert [shot["tier"] for shot in animated] == [HERO_TIER, STANDARD_TIER]
    assert [shot["model"] for shot in animated] == [VEO, LITE]


@pytest.mark.asyncio
async def test_a_slug_written_into_the_plan_never_reaches_a_submission(
    tmp_path, monkeypatch,
):
    """The instruction the skill gives the agent, enforced rather than trusted.

    Asked for a model, a language model writes one that does not exist — and a shot
    carrying `fal-ai/veo4/image-to-video` is priced from its family at the dearest known
    sibling and submitted to a 404. The planner's `model` key is not read at all.
    """
    output = await _run_plan(
        tmp_path,
        _plan({0: {"kind": "video", "tier": "hero",
                     "model": "fal-ai/veo4/ultra/image-to-video",
                     "usd_per_second": 0.001}}),
        monkeypatch, standard=LITE, hero=VEO)

    assert {shot["model"] for shot in output["shots"]} <= {"", LITE, VEO}


@pytest.mark.asyncio
async def test_the_opening_beat_is_hero_even_when_the_planner_did_not_say_so(
    tmp_path, monkeypatch,
):
    """Position settles this one without asking.

    The hook is the shot retention is won or lost on and the only shot every viewer
    sees. A plan that forgot to mark it — which is most plans, since the field is new —
    would otherwise open the video on the batch model.
    """
    output = await _run_plan(tmp_path, _plan({0: {"kind": "video"}}),
                             monkeypatch, standard=LITE, hero=VEO)

    opening = output["shots"][0]
    assert opening["scene_index"] == 0
    assert opening["tier"] == HERO_TIER and opening["model"] == VEO


@pytest.mark.asyncio
async def test_a_plan_that_marks_everything_hero_does_not_buy_the_hero_model_for_the_video(
    tmp_path, monkeypatch,
):
    """The cap, and the reason it is a cap rather than an allocation.

    The cheapest way for a language model to satisfy "mark the important shots" is to
    mark all of them. Uncapped, the feature inverts: a settings page promising a fifth of
    the cost renders the whole video on the premium endpoint.
    """
    output = await _run_plan(
        tmp_path,
        _plan({index: {"kind": "video", "tier": "hero"} for index in range(8)}),
        monkeypatch, standard=LITE, hero=VEO, scenes=8)

    animated = [shot for shot in output["shots"] if shot["kind"] == "video"]
    heroes = [shot for shot in animated if shot["tier"] == HERO_TIER]
    assert heroes, "the opening beat is always hero"
    assert len(heroes) <= round(8 * media_node.HERO_SHARE)
    assert output["hero_shots"] == len(heroes)
    # And the downgraded ones actually render on the batch model, rather than being
    # relabelled while still pointing at the dear endpoint.
    assert all(shot["model"] == LITE for shot in animated if shot["tier"] != HERO_TIER)


@pytest.mark.asyncio
async def test_a_still_marked_hero_does_not_spend_the_budget(tmp_path, monkeypatch):
    """A tier is only money where it is a different endpoint.

    A still costs what a still costs whichever tier it carries, so charging it against
    the cap would deny the upgrade to an animated beat that would have used it — and the
    planner marks beats, which have no idea whether they ended up animated.
    """
    output = await _run_plan(
        tmp_path,
        _plan({0: {"kind": "image", "tier": "hero"},
                 1: {"kind": "image", "tier": "hero"},
                 2: {"kind": "video", "tier": "hero"}}),
        monkeypatch, standard=LITE, hero=VEO, scenes=4)

    by_scene = {shot["scene_index"]: shot for shot in output["shots"]}
    assert by_scene[2]["tier"] == HERO_TIER and by_scene[2]["model"] == VEO
    # The still says what the beat was and carries no video endpoint, because it is not
    # generated on one and a slug here would read as though it had been.
    assert by_scene[1]["tier"] == HERO_TIER and by_scene[1]["model"] == ""


@pytest.mark.asyncio
async def test_the_plan_reports_what_the_animation_costs_at_both_rates(
    tmp_path, monkeypatch,
):
    """The stage that decides the spend is the stage that has to report it.

    `credits.py` holds one blended per-clip figure for one model, so a run routed across
    two has no single rate that figure could be. Quoted at either model's rate the number
    is wrong in that model's direction, and the cheap direction is a reserve that runs
    out in the middle of a batch.
    """
    output = await _run_plan(
        tmp_path,
        _plan({0: {"kind": "video", "tier": "hero"},
                 3: {"kind": "video", "tier": "standard"}}),
        monkeypatch, standard=LITE, hero=VEO, scenes=8)

    assert output["video_models"] == {"hero": VEO, "standard": LITE}
    # Eight-second scenes: one on Veo 3.1 at $0.20, one on Lite at $0.03.
    assert output["video_usd"] == pytest.approx(8 * 0.20 + 8 * 0.03, abs=0.01)


# ------------------------------------------------------------------ the batch


class _RecordingVideo:
    """A video provider that costs nothing and remembers what it was asked for."""

    name = "recording-video"

    def __init__(self, model: str) -> None:
        self.model = model
        self.calls: list[float] = []

    async def generate_clip(self, prompt, *, out_path, seconds=5.0, width=1280,
                            height=720, image_path=None) -> MediaResult:
        self.calls.append(seconds)
        return MediaResult(path=Path(out_path).with_suffix(".mp4"), mime="video/mp4",
                           credits=1, provider=self.name, duration_seconds=seconds,
                           meta={"model": self.model})


class _RecordingImage:
    name = "recording-image"

    async def generate(self, prompt, *, out_path, width=1280, height=720) -> MediaResult:
        return MediaResult(path=Path(out_path).with_suffix(".png"), mime="image/png",
                           provider=self.name, meta={})


class _RecordingRegistry(ProviderRegistry):
    """A registry that answers per model and keeps every slug it was asked for.

    The point of the whole change is which endpoint each shot is submitted to, and in
    mock mode every slug resolves to the same offline stand-in — so a test against the
    mock registry would pass whether or not the routing worked.
    """

    def __init__(self, **fields) -> None:
        super().__init__(**fields)
        self.asked: list[str] = []
        self.videos: dict[str, _RecordingVideo] = {}

    def image(self):
        return _RecordingImage()

    def video(self, model: str = ""):
        self.asked.append(model)
        return self.videos.setdefault(model, _RecordingVideo(model))


def _routed_shots() -> list[dict]:
    return [
        {"scene_index": 0, "plate_index": 0, "kind": "video", "tier": HERO_TIER,
         "model": VEO, "prompt": PROMPT, "motion": "push_in", "seconds": 8.0},
        {"scene_index": 1, "plate_index": 0, "kind": "video", "tier": STANDARD_TIER,
         "model": LITE, "prompt": PROMPT, "motion": "push_in", "seconds": 6.0},
        {"scene_index": 2, "plate_index": 0, "kind": "video", "tier": STANDARD_TIER,
         "model": LITE, "prompt": PROMPT, "motion": "push_in", "seconds": 6.0},
    ]


def _batch_context(tmp_path: Path, node: str = "shots") -> NodeContext:
    return NodeContext(
        run_id=1, topic="ships", options={}, node_key=node, node_type=node,
        params={}, attempts=0,
        channel=ChannelSnapshot(
            id=1, name="Test Channel", niche="shipping", language="en", voice_id="",
            avatar_id="", aspect_ratio="16:9", target_duration_seconds=300,
            style_profile={"register": "B", "grade": "cool", "lighting": "available"},
            video_model=LITE, video_model_hero=VEO,
        ),
        registry=_RecordingRegistry(mode="mock"),
        workdir=tmp_path / "work",
        upstream_outputs={"broll_plan": {"shots": _routed_shots()}},
    )


@pytest.mark.asyncio
async def test_each_shot_is_animated_on_the_model_its_tier_chose(tmp_path):
    """One provider for the run renders every shot on whichever slug resolved first.

    Silently, and at that model's price: a hero shot on the batch model is a cheap clip
    where a premium one was budgeted, and a batch shot on the hero model is six times the
    quoted rate across seventy-five clips.
    """
    context = _batch_context(tmp_path)
    result = await media_node.shots_node(context)

    registry = context.registry
    assert sorted(set(registry.asked)) == sorted([LITE, VEO])
    assert len(registry.videos[VEO].calls) == 1
    assert len(registry.videos[LITE].calls) == 2
    assert result.output["clips_by_model"] == {VEO: 1, LITE: 2}


@pytest.mark.asyncio
async def test_the_batch_asks_for_each_model_once_however_many_shots_use_it(tmp_path):
    """The registry caches on vendor and model, so this is cheap — but only if it is
    asked before the loop rather than inside it, which is also what keeps a missing
    video vendor to one warning instead of eighty."""
    context = _batch_context(tmp_path)
    await media_node.shots_node(context)

    assert len(context.registry.asked) == 2


@pytest.mark.asyncio
async def test_the_batch_reports_what_it_spent_per_model(tmp_path):
    """Against the clips that survived, not the ones that were planned.

    A run whose animations mostly fell back to stills must not report the plan's estimate
    as a cost — that is a settled number nobody can reconcile against the ledger.
    """
    result = await media_node.shots_node(_batch_context(tmp_path))

    assert result.output["video_usd"] == pytest.approx(
        8 * 0.20 + 6 * 0.03 + 6 * 0.03, abs=0.01)


@pytest.mark.asyncio
async def test_a_clip_records_the_endpoint_it_came_off(tmp_path):
    """Two clips in one video can now be from two models.

    A charge nobody can attribute to a model cannot be checked against the plan that
    authorised it, and the artifact row is what an audit reads back.
    """
    context = _batch_context(tmp_path)
    await media_node.shots_node(context)

    clips = [item for item in context._artifacts if item.meta.get("role") == "shot"]
    assert {clip.meta["model"] for clip in clips} == {LITE, VEO}
    assert {clip.meta["tier"] for clip in clips} == {HERO_TIER, STANDARD_TIER}


@pytest.mark.asyncio
async def test_a_plan_made_before_shots_carried_a_model_still_prices_correctly(tmp_path):
    """A run paused at the sample gate across this upgrade is the live case.

    It comes back to a stored shot list with no `model` key, and the registry resolves an
    empty slug to the run's standing choice — so the render is right either way. The
    report is what breaks: `video_model("")` prices at the unrecognised-model ceiling of
    $0.40 a second, which is five times what that batch actually cost.
    """
    context = _batch_context(tmp_path)
    for shot in context.upstream_outputs["broll_plan"]["shots"]:
        del shot["model"]
        shot["seconds"] = 6.0

    result = await media_node.shots_node(context)

    assert result.output["clips_by_model"] == {LITE: 3}
    assert result.output["video_usd"] == pytest.approx(3 * 6 * 0.03, abs=0.01)


# ------------------------------------------------------------------ the gate


@pytest.mark.asyncio
async def test_the_gate_samples_every_model_the_batch_will_run_on(tmp_path):
    """`setup_id` has always hashed the model in, and the node used to overwrite it.

    Every shot was stamped with the single resolved provider's model before grouping, so
    the facet `gates.py` calls "the largest single difference there is" was constant by
    construction and could never split a group. A two-model plan would have surfaced one
    sample and rendered the batch across two endpoints, one of which nobody looked at, at
    six times the rate of the one they approved.
    """
    context = _batch_context(tmp_path, node="sample")
    result = await sample_node.sample_node(context)

    assert result.output["setups"] == 2
    assert result.output["sampled"] == 2
    assert result.output["models"] == sorted([LITE, VEO])
    assert {item["model"] for item in result.output["samples"]} == {LITE, VEO}


@pytest.mark.asyncio
async def test_each_sample_comes_off_the_endpoint_its_tier_will_render_on(tmp_path):
    """A hero sample generated on the batch model approves a look nothing will produce.

    It is worse than no sample: an operator who has approved it believes the expensive
    clips were the ones they looked at.
    """
    context = _batch_context(tmp_path, node="sample")
    await sample_node.sample_node(context)

    registry = context.registry
    assert sorted(set(registry.asked)) == sorted([LITE, VEO])
    assert registry.videos[VEO].calls and registry.videos[LITE].calls


@pytest.mark.asyncio
async def test_the_gate_and_the_batch_resolve_a_legacy_plan_the_same_way(tmp_path):
    """Three nodes read this setting, and they must all read it identically.

    If the gate resolved an unmodelled shot differently from the batch, it would approve
    one endpoint while the batch spent on another — the exact failure the Sample Gate
    exists to prevent, reached not through a bug in the gate but through two node files
    reading a channel field in two ways. They share one resolver for that reason.
    """
    context = _batch_context(tmp_path, node="sample")
    for shot in context.upstream_outputs["broll_plan"]["shots"]:
        del shot["model"]

    result = await sample_node.sample_node(context)

    assert result.output["models"] == [LITE]
    assert context.registry.videos[LITE].calls
    # And the approval names the endpoint rather than an empty string, which is what an
    # audit has to match a charge against.
    assert all(item["model"] == LITE for item in result.output["samples"])


@pytest.mark.asyncio
async def test_the_gate_prices_each_tier_on_its_own_model(tmp_path):
    """One rate cannot describe a batch running on two endpoints.

    The hero sample has to cost what the hero model costs, because that figure is the
    whole reason the gate stops: an operator being asked to authorise $6.80 of premium
    animation is answering a different question from one being asked to authorise $0.14.
    """
    result = await sample_node.sample_node(_batch_context(tmp_path, node="sample"))

    by_model = {item["model"]: item["proceeding"] for item in result.output["samples"]}
    assert by_model[VEO]["usd_per_second"] == 0.20
    assert by_model[LITE]["usd_per_second"] == 0.03
    for quote in by_model.values():
        assert quote["charges"][0]["usd"] > 0, "a sample that costs nothing gates nothing"


@pytest.mark.asyncio
async def test_a_sample_is_generated_at_the_models_own_minimum_duration(tmp_path):
    """Five seconds is not universal, and this node used to assume it was.

    The duration envelope was read off the provider as `shortest_seconds` and
    `longest_seconds` — attribute names no adapter in this tree carries — so both came
    back 0.0 and every sample was quoted at five seconds whatever the model. Hailuo's
    shortest generation is six, and Sora takes 4, 8, 12, 16 and 20 with nothing between,
    so five is a number one of them under-quotes and the other rejects outright.
    """
    context = _batch_context(tmp_path, node="sample")
    for shot in context.upstream_outputs["broll_plan"]["shots"]:
        shot["model"] = HAILUO

    await sample_node.sample_node(context)

    assert context.registry.videos[HAILUO].calls == [
        video_model(HAILUO).sample_seconds]


# ------------------------------------------------------------------ the door


def test_the_channel_page_offers_a_hero_model_and_saves_it(client, session: Session,
                                                           channel: Channel):
    """Reachable, and it has to stick — the same two halves the batch model needed."""
    body = client.get(f"/c/{channel.id}").text
    assert 'name="video_model_hero"' in body
    # And the option that means "do not upgrade anything", which is where most channels
    # should stay: without it the only way to express today's behaviour is a coincidence.
    assert "Hero shots: same as above" in body

    answer = client.post(f"/c/{channel.id}/video-model",
                         data={"video_model": LITE, "video_model_hero": VEO},
                         follow_redirects=False)
    assert answer.status_code == 303
    session.expire_all()
    saved = session.get(Channel, channel.id)
    assert (saved.video_model, saved.video_model_hero) == (LITE, VEO)


def test_the_page_shows_what_the_blend_costs_rather_than_one_models_rate(
    client, session: Session, channel: Channel,
):
    """$0.20 a second and $0.03 a second are two true numbers that answer nothing.

    The decision is between $98.00, $14.70 and $21.50 for the same script, and only the
    third of those describes what this channel is actually set to.
    """
    channel.video_model, channel.video_model_hero = LITE, VEO
    session.commit()

    body = client.get(f"/c/{channel.id}").text
    assert "21.50" in body
    assert "a video" in body


def test_a_channel_with_no_hero_model_is_told_what_picking_one_would_do(
    client, channel: Channel,
):
    """The default state is the one that has to sell the feature.

    A card that only prints a blend once you have set one is a card nobody sets one on.
    """
    body = client.get(f"/c/{channel.id}").text
    assert "43.75" in body  # today's default, on every shot
    assert "opening hook" in body


def test_an_unknown_hero_slug_is_refused_rather_than_stored(client, channel: Channel):
    """Same rule as the batch model, and the same reason.

    A slug outside the catalogue is priced from its family at the dearest known sibling,
    so storing one moves the channel onto the conservative estimate for every run.
    """
    answer = client.post(f"/c/{channel.id}/video-model",
                         data={"video_model": LITE,
                               "video_model_hero": "fal-ai/not-a-model/image-to-video"},
                         follow_redirects=False)
    assert answer.status_code == 400


def test_clearing_the_hero_model_means_no_upgrade_rather_than_a_missing_value(
    client, session: Session, channel: Channel,
):
    channel.video_model, channel.video_model_hero = LITE, VEO
    session.commit()

    answer = client.post(f"/c/{channel.id}/video-model",
                         data={"video_model": LITE, "video_model_hero": ""},
                         follow_redirects=False)
    assert answer.status_code == 303
    session.expire_all()
    assert session.get(Channel, channel.id).video_model_hero == ""


def test_the_run_carries_both_models_into_its_snapshot():
    """The snapshot is the only thing a node sees, so both fields have to be on it."""
    snapshot = ChannelSnapshot(
        id=1, name="c", niche="n", language="en", voice_id="", avatar_id="",
        aspect_ratio="16:9", target_duration_seconds=480, style_profile={},
        video_model=LITE, video_model_hero=VEO,
    )
    assert (snapshot.video_model, snapshot.video_model_hero) == (LITE, VEO)

    # Defaulted, so every older construction still works and means "no upgrade".
    plain = ChannelSnapshot(
        id=1, name="c", niche="n", language="en", voice_id="", avatar_id="",
        aspect_ratio="16:9", target_duration_seconds=480, style_profile={},
    )
    assert plain.video_model_hero == ""


def test_one_run_holds_two_video_providers_at_once():
    """The cache key carries the model, which is what makes asking twice correct.

    Keyed on the vendor alone, the second tier would be handed the first tier's adapter
    and every hero shot would render on the batch model at the batch model's price.
    """
    registry = ProviderRegistry(mode="live", user_keys={"fal": "k"},
                                models={"video": LITE})
    assert registry.video().model == LITE
    assert registry.video(VEO).model == VEO
    # And the standing choice is untouched by having asked for something else.
    assert registry.video().model == LITE
    assert registry.video(VEO) is registry.video(VEO)
