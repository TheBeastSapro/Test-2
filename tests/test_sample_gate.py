"""The Sample Gate's decidable parts: coverage, waivers, and the two-charge arithmetic.

The expensive failure this defends is a batch that renders forty clips against one
approval given for a different motion. So the cases below are mostly about the *near
miss*: setups that look approved because everything except the camera move matches, which
is exactly the case `data/i2v-prompt-cookbook.md` says a human eye passes and the money
does not.
"""

from __future__ import annotations

from dataclasses import fields, replace

import pytest

from forgecast.skills import gates


def setup(**overrides) -> gates.ShotSetup:
    """A complete setup. Every facet filled, because a blank facet is its own case."""
    base = gates.ShotSetup(
        model="fal-ai/kling-video/v2.6-turbo/image-to-video",
        style=gates.StyleKey(register="A", grade="warm natural",
                             lighting="available window light", aspect_ratio="16:9"),
        motion=gates.MotionKey(intensity="subtle", focal_verb="reads",
                               camera="static medium close-up"),
        seconds=8.0,
        shot_id="shot-03",
    )
    style = {k: v for k, v in overrides.items() if k in {"register", "grade", "lighting",
                                                         "aspect_ratio"}}
    motion = {k: v for k, v in overrides.items() if k in {"intensity", "focal_verb",
                                                          "camera"}}
    rest = {k: v for k, v in overrides.items()
            if k not in style and k not in motion}
    return replace(base, style=replace(base.style, **style),
                   motion=replace(base.motion, **motion), **rest)


def approval(**overrides) -> gates.SampleApproval:
    return gates.SampleApproval(
        setup=setup(**overrides), approved_by="operator@example.com",
        approved_at="2026-08-03T10:00:00+00:00", request_id="fal-req-1111",
        sample_seconds=5.0, sample_usd=0.55,
    )


# ----------------------------------------------------------------------- coverage


def test_the_same_style_and_motion_is_covered_and_says_which_sample_covered_it():
    result = gates.coverage(setup(), [approval()])
    assert result.covered is True
    assert result.waived is False
    # The audit question is which charge authorised this render, so the id is in the
    # sentence rather than in a sibling field a log line would drop.
    assert "fal-req-1111" in result.reason
    assert result.approval_request_id == "fal-req-1111"


def test_a_matching_style_with_a_different_motion_is_not_covered():
    """The subtle one, and the whole reason this is code.

    The skill is explicit: style looking consistent is not enough. A grade, register,
    lighting and model that all match make a second setup feel approved, and the camera
    swap is what melts the faces.
    """
    for facet, value, expected in (
        ("camera", "slow orbit around the subject", "the camera move"),
        ("intensity", "high", "the motion intensity"),
        ("focal_verb", "runs", "the action"),
    ):
        result = gates.coverage(setup(**{facet: value}), [approval()])
        assert result.covered is False, facet
        assert expected in result.reason
        assert result.mismatched == (f"motion.{facet}",)


def test_a_matching_motion_with_a_different_style_is_not_covered():
    for facet, value, expected in (
        ("grade", "cool cinematic teal", "the colour grade"),
        ("register", "B", "the visual register"),
        ("lighting", "three-point studio", "the lighting"),
        ("aspect_ratio", "9:16", "the aspect ratio"),
    ):
        result = gates.coverage(setup(**{facet: value}), [approval()])
        assert result.covered is False, facet
        assert expected in result.reason
        assert result.mismatched == (f"style.{facet}",)


def test_a_different_model_is_not_covered_however_alike_the_look():
    result = gates.coverage(setup(model="fal-ai/lightricks/ltx-video-v2.3/image-to-video"),
                            [approval()])
    assert result.covered is False
    assert "the model" in result.reason
    assert result.mismatched == ("model",)


def test_cosmetic_spellings_of_one_facet_are_the_same_setup():
    """A gate that fires on "Push-In" versus "push in" is a gate that gets switched off."""
    covered = gates.coverage(setup(camera="  STATIC  Medium Close-Up "), [approval()])
    assert covered.covered is True
    assert setup(camera="static medium close up").setup_id == setup().setup_id


def test_an_unstated_facet_is_a_difference_rather_than_a_wildcard():
    """A shot that never said what its camera does does not match every camera.

    Treating unknown as "same" is precisely how a whip-pan renders under a locked-camera
    approval, and the missing field means nobody looked.
    """
    result = gates.coverage(setup(camera=""), [approval()])
    assert result.covered is False
    assert result.mismatched == ("motion.camera",)

    # And the reverse: an approval recorded without a camera does not cover a stated one.
    assert gates.coverage(setup(), [approval(camera="")]).covered is False


def test_an_approval_with_no_billed_submission_covers_nothing():
    """A sample that cannot be pointed at is a full render called a sample afterwards."""
    claimed = replace(approval(), request_id="")
    result = gates.coverage(setup(), [claimed])
    assert result.covered is False
    assert "no sample submission" in result.reason


def test_the_setup_id_ignores_what_varies_inside_one_approved_setup():
    """Duration and shot id must not be part of the identity.

    Folded in, every shot gets its own id, every shot needs its own sample, and the gate
    that was meant to cost one clip costs forty.
    """
    assert setup(seconds=4.0, shot_id="shot-11").setup_id == setup().setup_id
    assert setup(camera="whip pan").setup_id != setup().setup_id
    assert len(setup().setup_id) == 12


def test_with_no_approvals_at_all_the_reason_says_so():
    result = gates.coverage(setup(), [])
    assert result.covered is False
    assert "no sample has been approved" in result.reason
    assert result.waivable is False


def test_the_closest_miss_is_the_one_reported():
    """One facet named points at the fix; four named reads as an unrelated setup.

    An operator who cannot see the fix waives the gate, which costs more than the sample.
    """
    unrelated = approval(model="fal-ai/veo3/image-to-video", register="B",
                         grade="cool cinematic", lighting="three-point")
    near = approval(camera="slow orbit")
    result = gates.coverage(setup(), [unrelated, near])
    assert result.mismatched == ("motion.camera",)


# ------------------------------------------------------------------------ waivers


def test_a_short_shot_is_reported_as_waivable_but_never_waived_here():
    """The skill permits skipping under three seconds and then says never decide alone.

    So the predicate reports the permission and refuses on its own behalf. Code that
    granted it would be the app waiving the operator's cost protection for them.
    """
    result = gates.coverage(setup(seconds=2.5, camera="whip pan"), [approval()])
    assert result.covered is False
    assert result.waivable is True

    assert gates.coverage(setup(seconds=3.0, camera="whip pan"),
                          [approval()]).waivable is False


def test_an_operator_waiver_covers_the_shot_and_records_who_and_why():
    waiver = gates.Waiver(reason="pilot batch, I accept the risk",
                          granted_by="operator@example.com", scope="batch",
                          granted_at="2026-08-03T11:00:00+00:00")
    result = gates.coverage(setup(camera="whip pan"), [approval()], waiver=waiver)
    assert result.covered is True
    assert result.waived is True
    assert "operator@example.com" in result.reason
    assert "pilot batch" in result.reason
    # Still carries what would have needed a sample, so the record says what was skipped.
    assert result.mismatched == ("motion.camera",)


# -------------------------------------------------------------------- the sample size


@pytest.mark.parametrize(("shortest", "longest", "expected"), [
    (5.0, 10.0, 5.0),      # the common case: the minimum is the target
    (6.0, 10.0, 6.0),      # a six-second minimum samples at six
    (2.0, 10.0, 5.0),      # a two-second sample shows a start and no development
    (0.0, 0.0, 5.0),       # unknown minimum still samples at the target
    (8.0, 4.0, 4.0),       # a cap below the target wins: nothing else is submittable
])
def test_the_sample_duration_respects_the_minimum_and_the_target(shortest, longest,
                                                                 expected):
    assert gates.sample_seconds_for(shortest, longest_supported=longest) == expected


# ------------------------------------------------------------------- the two charges


def test_the_sample_and_the_full_render_are_two_charges_and_never_one():
    priced = gates.quote(model="kling", usd_per_second=0.11, full_seconds=8.0,
                         shortest_supported=5.0)

    charges = priced.charges()
    assert [charge.label for charge in charges] == ["sample", "full render"]
    assert charges[0].usd == pytest.approx(0.55)
    # The full render is the full length. Not eight minus the five already paid for: the
    # sample bought information, not the first five seconds of the delivered clip.
    assert charges[1].seconds == 8.0
    assert charges[1].usd == pytest.approx(0.88)
    assert priced.sum_usd() == pytest.approx(1.43)

    # No field that could be quoted alone as "the cost", because a single number is
    # indistinguishable from "the full render, sample included" — the phrasing the skill
    # forbids, and the one that turns two ledger rows into one.
    assert "total" not in {field.name for field in fields(gates.Quote)}
    assert priced.as_dict()["billed_separately"] is True
    assert len(priced.as_dict()["charges"]) == 2


def test_the_quoted_sentence_says_both_prices_and_the_words_separate_charges():
    sentence = gates.quote(model="kling", usd_per_second=0.11, full_seconds=8.0,
                           shortest_supported=5.0).sentence()
    assert "$0.55" in sentence
    assert "$0.88" in sentence
    assert "separate charges" in sentence
    for forbidden in ("included", "rolled in", "free"):
        assert forbidden not in sentence


def test_a_verified_continuation_endpoint_is_still_two_charges():
    priced = gates.quote(model="kling", usd_per_second=0.11, full_seconds=8.0,
                         shortest_supported=5.0, extension_seconds=3.0)
    assert [charge.label for charge in priced.charges()] == ["sample", "extension"]
    assert priced.remainder.usd == pytest.approx(0.33)
    assert priced.sum_usd() == pytest.approx(0.88)


def test_a_forty_times_price_difference_reaches_the_quote():
    """The reason a flat per-second rate cannot stay: the spread is the whole decision."""
    cheap = gates.quote(model="ltx", usd_per_second=0.01, full_seconds=8.0,
                        shortest_supported=5.0)
    dear = gates.quote(model="kling-pro", usd_per_second=0.40, full_seconds=8.0,
                       shortest_supported=5.0)
    assert dear.sum_usd() == pytest.approx(cheap.sum_usd() * 40)


# ------------------------------------------------------------------- the batch budget


def test_two_shots_in_one_setup_owe_one_sample_between_them():
    first, second = setup(shot_id="a"), setup(shot_id="b", seconds=6.0)
    assert first.setup_id == second.setup_id

    quotes = {shot.setup_id: gates.quote(model=shot.model, usd_per_second=0.11,
                                         full_seconds=shot.seconds,
                                         shortest_supported=5.0)
              for shot in (first, second)}
    budget = gates.batch_budget(quotes)
    assert budget.setups == 1
    assert budget.samples_usd == pytest.approx(0.55)


def test_the_batch_budget_surfaces_every_sample_a_multi_setup_batch_owes():
    """Six samples owed before the first production clip is the number that changes a
    mind, and finding it out at the sixth gate is finding it out after paying five."""
    shots = [setup(camera=move) for move in
             ("static", "slow push in", "truck right", "tilt down", "handheld", "arc")]
    quotes = {shot.setup_id: gates.quote(model=shot.model, usd_per_second=0.11,
                                         full_seconds=8.0, shortest_supported=5.0)
              for shot in shots}
    budget = gates.batch_budget(quotes)

    assert budget.setups == 6
    assert budget.samples_usd == pytest.approx(3.30)
    assert budget.renders_usd == pytest.approx(5.28)
    assert budget.sum_usd() == pytest.approx(8.58)
    assert "6 samples" in budget.sentence()


# ----------------------------------------------------------------------- the surface


def test_the_surfaced_payload_carries_all_four_things_the_decision_needs():
    """Clip, prompt, spent, and cost to proceed. Three of the four is not a gate."""
    priced = gates.quote(model="kling", usd_per_second=0.11, full_seconds=8.0,
                         shortest_supported=5.0)
    payload = gates.surface(setup=setup(), prompt="a 70-year-old grandmother reads a letter",
                            clip_path="/runs/12/sample_003.mp4", quote_=priced,
                            usd_spent_so_far=0.42)

    assert payload["clip"] == "/runs/12/sample_003.mp4"
    assert "grandmother" in payload["prompt"]
    assert payload["usd_spent_so_far"] == 0.42
    assert payload["proceeding"]["charges"][1]["usd"] == 0.88
    assert payload["setup_id"] == setup().setup_id
    # And what the approval is understood to cover, in the same breath as the question.
    assert "style and motion" in payload["approves"]
    assert "$0.42" in payload["question"]
    assert "separate charges" in payload["question"]
