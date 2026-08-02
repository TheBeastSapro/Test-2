"""Learning, refining and mixing an editing style.

The discipline these tests enforce is the split the package is built around: `learn`
must be *descriptive* — it reports what the reference does, including what it does
badly — and `refine` must be *prescriptive and explicit* — every departure recorded
with its reason. A test suite that only checked the final numbers would pass equally
well if the two were fused, and then nobody could tell what came from the reference
and what came from us.
"""

from __future__ import annotations

import json

import pytest

from forgecast.graph import formats
from forgecast.style import EditingStyle, available, blend, delete, get, learn, refine
from forgecast.style.editing import slug
from forgecast.style.refine import (
    JITTER_FLOOR,
    MAX_CONTRAST,
    MAX_SATURATION,
    MIN_MOTION_FOR_FACELESS,
    MIN_READABLE_SHOT,
)


def profile(*, shot=4.0, jitter=0.35, contrast=1.0, saturation=1.0, motion=0.5,
            pacing="steady", transition="cut", path="ref.mp4",
            colour_confidence="high", palette=None) -> dict:
    """A measured StyleProfile in the shape `vision` actually emits."""
    return {
        "source": {"path": path},
        "render_spec": {
            "target_shot_seconds": shot,
            "shot_seconds_range": [shot * 0.6, shot * 1.8],
            "cuts_per_minute": 60.0 / shot,
            "jitter": jitter, "transition": transition, "dissolve_share": 0.0,
            "ken_burns": True, "zoom_rate": 0.03, "captions": True,
            "caption_position": "bottom_third", "snap_cuts_to_beat": False,
            "pacing": pacing, "motion_intensity": motion,
            "target_brightness": 0.0, "target_contrast": contrast,
            "target_saturation": saturation,
        },
        "colour": {"palette": palette if palette is not None else [{"hex": "#22303f"}]},
        # `vision` reports confidence as a label, not a number.
        "confidence": {"colour": colour_confidence},
        "shot_rhythm": {"shot_count": 40},
        "overlay": {"has_captions": True},
        "audio": {"has_music": False},
    }


# --------------------------------------------------------------------- learning


def test_learning_needs_at_least_one_reference():
    with pytest.raises(ValueError):
        learn([], name="Nothing")


def test_a_style_is_the_median_of_its_references_not_the_mean():
    """Regression against the obvious implementation.

    One reference three times longer than the others should not drag the style toward
    itself — same reasoning as the outlier scorer. Mean of 4/4/4/40 is 13; median is 4.
    """
    style = learn(
        [profile(shot=4.0), profile(shot=4.0), profile(shot=4.0), profile(shot=40.0)],
        name="Mostly Consistent",
    )
    assert style.target_shot_seconds == 4.0


def test_disagreement_between_references_is_reported_not_hidden():
    """A field the references do not agree on is a field the creator has no rule for."""
    agree = learn([profile(motion=0.5), profile(motion=0.5)], name="Agreed")
    disagree = learn([profile(motion=0.05), profile(motion=0.95)], name="Disagreed")

    assert agree.spread["motion_intensity"] == 0.0
    assert disagree.spread["motion_intensity"] > 0.5


def test_learning_is_descriptive_and_keeps_the_references_flaws():
    """The whole reason `refine` is a separate step.

    If `learn` quietly corrected a metronomic cut or a clipped grade, there would be
    no way to see what the reference actually does.
    """
    style = learn([profile(shot=0.3, jitter=0.02, contrast=1.9, saturation=2.1)],
                  name="Hot Mess")
    assert style.target_shot_seconds == 0.3
    assert style.jitter == 0.02
    assert style.contrast == 1.9
    assert style.saturation == 2.1


def test_a_confidence_label_is_read_as_a_rank_not_a_number():
    """Regression: `vision` emits "high"/"medium"/"low", and `float()` raised on it.

    Found by running the CLI against real measured clips — the synthetic fixtures used
    numbers, so the suite was green while the feature was broken end to end. Ranking
    also has to be explicit, because "high" sorts *below* "low" alphabetically.
    """
    style = learn(
        [
            profile(colour_confidence="low", palette=[{"hex": "#aaaaaa"}]),
            profile(colour_confidence="high", palette=[{"hex": "#112233"}]),
        ],
        name="Mixed Confidence",
    )
    assert style.palette == [{"hex": "#112233"}], "should take the confident palette"


def test_a_diagnostic_never_becomes_a_style():
    """`insufficient_shots` is a statement about the evidence, not about the edit.

    Adopting it would give the style a pacing nothing downstream can apply.
    """
    style = learn([profile(pacing="insufficient_shots"),
                   profile(pacing="insufficient_shots")], name="Too Short")
    assert style.pacing == "steady"


def test_palettes_are_taken_whole_rather_than_averaged():
    """Mixing two three-colour looks gives six near-greys belonging to neither."""
    style = learn(
        [profile(palette=[{"hex": "#ff0000"}, {"hex": "#00ff00"}], colour_confidence="high"),
         profile(palette=[{"hex": "#0000ff"}], colour_confidence="low")],
        name="Two Looks",
    )
    assert style.palette == [{"hex": "#ff0000"}, {"hex": "#00ff00"}]


def test_provenance_records_what_it_learned_from():
    style = learn([profile(path="a.mp4"), profile(path="b.mp4")], name="Two Refs")
    assert style.provenance["origin"] == "learned"
    assert style.provenance["sample_size"] == 2
    assert set(style.provenance["references"]) == {"a.mp4", "b.mp4"}


def test_an_absurd_measurement_is_ignored_rather_than_inherited():
    """A saturation of 40 is a bug upstream; a style carrying it is unrenderable."""
    style = learn([profile(saturation=40.0), profile(saturation=1.1),
                   profile(saturation=1.0)], name="One Bad Read")
    assert 0.9 < style.saturation < 1.3


# ---------------------------------------------------------------------- refining


def test_refine_never_mutates_the_style_it_was_given():
    """A learned style is evidence, and evidence that changes when you look at it is
    not evidence."""
    original = learn([profile(shot=0.2, jitter=0.01)], name="Frantic")
    before = original.as_dict()
    refine(original)
    assert original.as_dict() == before


def test_every_departure_carries_a_reason():
    _, changes = refine(learn([profile(shot=0.2, jitter=0.01, contrast=1.9,
                                       saturation=2.4, motion=0.0)], name="Everything"))
    assert changes
    for change in changes:
        assert change.why and len(change.why) > 20, change.field
        assert change.was != change.now


def test_a_shot_too_short_to_read_is_raised_to_the_floor():
    improved, _ = refine(learn([profile(shot=0.2)], name="Blink"))
    assert improved.target_shot_seconds == MIN_READABLE_SHOT
    assert improved.shot_seconds_min >= MIN_READABLE_SHOT


def test_the_cut_rate_stays_consistent_with_the_corrected_shot_length():
    """Regression: the style shipped claiming 158 cuts a minute out of half-second
    shots. Two numbers describing the same fact must not disagree."""
    improved, _ = refine(learn([profile(shot=0.38)], name="Fast"))
    implied = 60.0 / improved.target_shot_seconds
    assert improved.cuts_per_minute == pytest.approx(implied, abs=1.0)


def test_metronomic_cutting_gets_some_variation_back():
    improved, _ = refine(learn([profile(jitter=0.02)], name="Metronome"))
    assert improved.jitter == JITTER_FLOOR


def test_a_clipped_grade_is_pulled_back():
    improved, _ = refine(learn([profile(contrast=2.1, saturation=2.4)], name="Crushed"))
    assert improved.contrast == MAX_CONTRAST
    assert improved.saturation == MAX_SATURATION


def test_a_faceless_video_gets_a_floor_of_motion():
    improved, _ = refine(learn([profile(motion=0.0)], name="Slideshow"))
    assert improved.motion_intensity == MIN_MOTION_FOR_FACELESS


def test_a_well_made_reference_is_left_almost_alone():
    """The corrections must fire on defects, not on choices.

    A slow, restrained, correctly-graded reference should come through with its
    identity intact — otherwise `refine` is just imposing one house style on
    everything, which is the opposite of learning.
    """
    calm = learn([profile(shot=6.0, jitter=0.42, contrast=1.05, saturation=1.02,
                          motion=0.3)], name="Careful")
    improved, changes = refine(calm)

    assert improved.target_shot_seconds == calm.target_shot_seconds
    assert improved.jitter == calm.jitter
    assert improved.contrast == calm.contrast
    assert improved.saturation == calm.saturation
    # Only the front-loading of pace, which applies to everything.
    assert [item.field for item in changes] == ["pacing"]


def test_a_refinement_can_be_skipped_when_the_operator_disagrees():
    """These are strong defaults, not laws."""
    style = learn([profile(jitter=0.02)], name="Deliberately Metronomic")
    improved, changes = refine(style, skip=("rhythm variation",))
    assert improved.jitter == 0.02
    assert "jitter" not in [item.field for item in changes]


def test_refinement_provenance_points_back_at_its_parent():
    style = learn([profile(shot=0.2)], name="Parent")
    improved, _ = refine(style)
    assert improved.provenance["origin"] == "refined"
    assert improved.provenance["parent"] == style.key
    assert improved.provenance["refinements"]


# ---------------------------------------------------------------------- blending


def test_numbers_interpolate_across_a_blend():
    slow = EditingStyle(name="Slow", target_shot_seconds=8.0, jitter=0.5)
    fast = EditingStyle(name="Fast", target_shot_seconds=2.0, jitter=0.1)

    for weight, expected in ((0.0, 8.0), (0.5, 5.0), (1.0, 2.0)):
        mixed = blend(slow, fast, weight)
        assert mixed.target_shot_seconds == pytest.approx(expected)


def test_categoricals_switch_rather_than_average():
    """There is no style halfway between a cut and a dissolve, and averaging
    "bottom third" with "centre" puts the captions where neither creator puts them."""
    a = EditingStyle(name="A", transition="cut", caption_position="bottom_third")
    b = EditingStyle(name="B", transition="dissolve", caption_position="centre")

    assert blend(a, b, 0.4).transition == "cut"
    assert blend(a, b, 0.6).transition == "dissolve"
    assert blend(a, b, 0.6).caption_position == "centre"


def test_a_blend_takes_one_palette_whole():
    a = EditingStyle(name="A", palette=[{"hex": "#ff0000"}])
    b = EditingStyle(name="B", palette=[{"hex": "#0000ff"}])
    assert blend(a, b, 0.9).palette == [{"hex": "#0000ff"}]
    assert blend(a, b, 0.1).palette == [{"hex": "#ff0000"}]


def test_a_blend_records_its_parents():
    mixed = blend(EditingStyle(name="A"), EditingStyle(name="B"), 0.3)
    assert mixed.provenance["origin"] == "blend"
    assert mixed.provenance["parents"] == ["a", "b"]
    assert mixed.provenance["weight"] == 0.3


def test_a_blend_stays_inside_the_sane_bounds():
    wild = EditingStyle(name="Wild", saturation=2.9, contrast=2.1)
    mixed = blend(EditingStyle(name="Plain"), wild, 1.0)
    assert mixed.saturation <= 3.0 and mixed.contrast <= 2.2


# ----------------------------------------------------------------- application


def test_a_style_becomes_a_render_spec_the_renderer_already_understands():
    style = learn([profile(shot=5.0, transition="dissolve")], name="Applied")
    spec = style.to_render_spec()
    for key in ("target_shot_seconds", "shot_seconds_range", "jitter", "transition",
                "ken_burns", "captions", "caption_position", "pacing",
                "motion_intensity", "grade_filter", "palette"):
        assert key in spec, key
    assert spec["shot_seconds_range"][0] < spec["shot_seconds_range"][1]


def test_applying_a_style_keeps_what_the_style_has_no_opinion_about():
    """A channel profile also holds its tone and what the agent learned from
    approvals. Replacing the whole dict would silently discard them."""
    style = EditingStyle(name="Look")
    merged = style.to_channel_profile(
        {"tone": "calm, precise", "learned": {"approved": 12}}
    )
    assert merged["tone"] == "calm, precise"
    assert merged["learned"] == {"approved": 12}
    assert merged["editing_style"] == "look"
    assert "render_spec" in merged


def test_a_neutral_grade_compiles_to_no_filter_at_all():
    """An `eq` that changes nothing still costs a filter pass on every frame."""
    assert EditingStyle(name="Neutral").grade_filter() == ""
    assert "contrast" in EditingStyle(name="Punchy", contrast=1.3).grade_filter()


# -------------------------------------------------------------------- storage


def test_a_style_round_trips_through_disk(tmp_path):
    style = learn([profile(shot=3.3, saturation=1.2)], name="Round Trip")
    path = style.save(tmp_path)
    assert EditingStyle.load(path).as_dict() == style.as_dict()


def test_the_name_the_filename_and_the_lookup_key_are_one_thing(tmp_path):
    style = EditingStyle(name="Their Look!! 2026")
    style.save(tmp_path)
    assert (tmp_path / f"{slug('Their Look!! 2026')}.json").exists()
    assert get("Their Look!! 2026", tmp_path).name == "Their Look!! 2026"


def test_listing_survives_a_corrupt_file(tmp_path):
    """One bad file must not take out the whole shelf."""
    EditingStyle(name="Good").save(tmp_path)
    (tmp_path / "broken.json").write_text("{ not json", encoding="utf-8")
    assert [row["key"] for row in available(tmp_path)] == ["good"]


def test_an_unknown_style_says_what_is_available(tmp_path):
    EditingStyle(name="Only One").save(tmp_path)
    with pytest.raises(KeyError, match="only_one"):
        get("missing", tmp_path)


def test_delete_reports_whether_it_did_anything(tmp_path):
    EditingStyle(name="Doomed").save(tmp_path)
    assert delete("Doomed", tmp_path) is True
    assert delete("Doomed", tmp_path) is False


def test_a_style_written_by_an_older_version_still_loads(tmp_path):
    """Forward compatibility: unknown keys are dropped rather than raising."""
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"name": "Old", "jitter": 0.4, "a_field_from_the_future": 1}),
                    encoding="utf-8")
    assert EditingStyle.load(path).jitter == 0.4


# --------------------------------------------------------------------- formats


def test_a_channel_belongs_to_the_format_its_aspect_implies():
    class FakeChannel:
        def __init__(self, aspect):
            self.aspect_ratio = aspect

    assert formats.format_of_channel(FakeChannel("9:16")) == formats.SHORTS
    assert formats.format_of_channel(FakeChannel("4:5")) == formats.SHORTS
    assert formats.format_of_channel(FakeChannel("16:9")) == formats.LONGFORM
    assert formats.format_of_channel(FakeChannel("1:1")) == formats.LONGFORM


def test_an_unfamiliar_pipeline_shows_up_rather_than_disappearing():
    """The conservative direction: a workspace showing an unknown run beats one
    silently hiding it."""
    assert formats.format_of_pipeline("something_new") == formats.LONGFORM
    assert formats.format_of_pipeline("faceless_shorts") == formats.SHORTS


def test_a_bad_slug_resolves_to_the_app_rather_than_a_404():
    """Stale bookmarks and hand-typed URLs should land somewhere useful."""
    assert formats.get("nonsense").slug == formats.DEFAULT_FORMAT
    assert formats.get(None).slug == formats.DEFAULT_FORMAT
    assert formats.get("shorts").slug == formats.SHORTS


def test_counts_split_channels_and_runs_between_the_tabs():
    class FakeChannel:
        def __init__(self, aspect):
            self.aspect_ratio = aspect

    class FakeRun:
        def __init__(self, pipeline):
            self.pipeline = pipeline

    tally = formats.counts(
        [FakeChannel("16:9"), FakeChannel("9:16"), FakeChannel("9:16")],
        [FakeRun("faceless_longform"), FakeRun("faceless_shorts")],
    )
    assert tally[formats.LONGFORM] == {"channels": 1, "runs": 1}
    assert tally[formats.SHORTS] == {"channels": 2, "runs": 1}


def test_every_format_names_a_pipeline_that_exists():
    from forgecast.graph.pipelines import PIPELINES

    for item in formats.FORMATS.values():
        assert item.pipeline in PIPELINES, item.slug
        assert item.length_min < item.default_seconds < item.length_max
