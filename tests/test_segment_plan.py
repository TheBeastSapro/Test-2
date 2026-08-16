"""The shot list, written before anything is rendered.

An editor does not open the software and start cutting — they write the shot list
first, because "the wide establishes, the push lands on the reveal, the stats come up
under the second line" is cheap on paper and expensive in a timeline. A plan can be
read and argued with in seconds; a render cannot.
"""

from __future__ import annotations

from forgecast.edit.segment import BEAT_SHARE, MIN_HOLD, Segment, plan


def _asset(name, portrait=True, width=2000, height=2000):
    return {"name": name, "portrait": portrait, "size": [width, height]}


ENTITY = {
    "title": "Amber",
    "beats": {"appearance": "tall, reddish-brown, no head",
              "behaviour": "seen galloping along rooftops at night",
              "survival": "stay away from windows"},
    "stats": {"height": "Around 13 to 33 feet", "weight": "456 lbs"},
    "gallery": [_asset(f"amber_{n}.png") for n in range(5)],
}


def test_the_story_is_told_before_the_thing_is_specified():
    """The measured order, and it is NOT the order the wiki lists its sections in. A
    segment that specifies before it tells the story has given the answer before asking
    the question."""
    beats = [shot.beat for shot in plan(ENTITY).shots]

    assert beats[0] == "behaviour"
    assert beats.index("appearance") > beats.index("behaviour")
    assert beats[-1] == "survival"


def test_a_segment_fills_the_time_it_was_given():
    segment = plan(ENTITY, seconds=62.0)

    assert abs(segment.seconds - 62.0) < 0.5


def test_shots_hold_at_a_readable_length():
    """Two to four seconds is the measured rhythm. A plan that produces half-second
    shots has not planned, it has divided."""
    for shot in plan(ENTITY, seconds=62.0).shots:
        assert shot.seconds >= MIN_HOLD


def test_the_name_card_is_on_the_first_shot_and_only_there():
    shots = plan(ENTITY).shots
    carrying = [shot.index for shot in shots if "name card" in shot.overlays]

    assert carrying == [0]


def test_the_numbers_appear_on_the_beat_that_specifies():
    shots = plan(ENTITY).shots
    carrying = [shot for shot in shots if "stat card" in shot.overlays]

    assert len(carrying) == 1
    assert carrying[0].beat == "appearance"


def test_an_entity_with_no_numbers_gets_no_stat_card():
    shots = plan({**ENTITY, "stats": {}}).shots

    assert not any("stat card" in shot.overlays for shot in shots)


def test_the_gallery_is_used_rather_than_one_picture_held():
    """The failure this planner exists for. One image over a 62-second segment is a
    slideshow, and no amount of Ken Burns fixes it."""
    segment = plan(ENTITY, seconds=62.0)

    assert segment.shot_count > 15
    assert segment.assets_used == 5


def test_the_asset_cycle_carries_across_beats():
    """Per-beat round-robin put the identical frame on shots 0, 7 and 17 of a 21-shot
    segment — three separate moments all opening on the same picture."""
    shots = plan(ENTITY, seconds=62.0).shots
    first_of_each_beat = {}
    for shot in shots:
        first_of_each_beat.setdefault(shot.beat, shot.asset)

    assert len(set(first_of_each_beat.values())) == len(first_of_each_beat)


def test_motion_is_rationed_rather_than_sprinkled():
    """The reference animates about twice a minute and lands it on the beat the
    narration is describing. An animated establisher is spend with nothing to show."""
    shots = plan(ENTITY, seconds=62.0).shots
    animated = [shot for shot in shots if shot.animate]

    assert 1 <= len(animated) <= 4
    assert all(shot.beat == "behaviour" for shot in animated)


def test_gags_land_on_the_story_and_never_on_the_name_card():
    """Two things asking to be read at once is neither read."""
    shots = plan(ENTITY, gags=["There's a good snack in this house"]).shots
    bubbles = [shot for shot in shots if any(o.startswith("bubble") for o in shot.overlays)]

    assert len(bubbles) == 1
    assert bubbles[0].beat == "behaviour"
    assert "name card" not in bubbles[0].overlays


def test_a_page_with_no_sections_refuses_rather_than_planning_nothing():
    segment = plan({"title": "Stub", "beats": {}, "gallery": []})

    assert segment.shots == []
    assert any("cannot carry a segment" in warning for warning in segment.warnings)


def test_a_missing_beat_does_not_leave_the_segment_short():
    """A page with no survival section must not produce a segment that runs 82% of its
    length and stops."""
    segment = plan({**ENTITY, "beats": {"appearance": "a", "behaviour": "b"}},
                   seconds=60.0)

    assert abs(segment.seconds - 60.0) < 0.5


def test_no_artwork_is_reported_as_holes_rather_than_rendered():
    segment = plan({**ENTITY, "gallery": []}, seconds=30.0)

    assert all(shot.asset == "" for shot in segment.shots)
    assert any("hole to fill" in warning for warning in segment.warnings)


def test_leaning_on_too_few_pictures_is_flagged():
    segment = plan({**ENTITY, "gallery": [_asset("only.png")]}, seconds=62.0)

    assert any("leaning on too few" in warning for warning in segment.warnings)


def test_the_shares_are_a_real_split():
    assert abs(sum(BEAT_SHARE.values()) - 1.0) < 1e-9


def test_the_plan_reads_as_a_shot_list():
    """It has to be arguable by a person, which a dict is not."""
    text = plan(ENTITY, seconds=62.0, gags=["ha"]).as_text()

    assert "Amber" in text
    assert "name card" in text
    assert "bubble: ha" in text
    assert "motion" in text
    # A running clock, so a reader can see where in the minute each shot falls.
    assert "\n    0.0" in text


def test_the_dict_and_the_text_describe_the_same_plan():
    segment = plan(ENTITY, seconds=62.0)
    payload = segment.as_dict()

    assert payload["shot_count"] == len(payload["shots"]) == segment.shot_count
    assert isinstance(segment, Segment)


# ── reachability ────────────────────────────────────────────────────────────────
#
# The planner is only worth having if the agent reaches for it before the expensive
# stages. A planning step nothing can call is a planning step that does not happen.

def test_the_planner_is_reachable_as_an_agent_tool():
    from forgecast.agent import tools

    assert "plan_segment" in tools.ALL_TOOLS
    assert "plan_segment" in tools._READ_ONLY


def test_the_tool_tells_the_agent_to_plan_before_making_anything():
    """The description is the only thing that puts this step in the right order. If it
    reads as an optional report, it gets called after the shots exist, which is exactly
    when a plan is worthless."""
    import inspect

    from forgecast.agent import tools

    source = inspect.getsource(tools.build_server)
    block = source[source.index('@tool("plan_segment"'):source.index("async def plan_segment")]

    assert "BEFORE anything is rendered" in block
    assert "spends nothing" in block


def test_the_studio_hands_back_something_a_person_can_argue_with():
    import inspect

    from forgecast.agent.studio import Studio

    source = inspect.getsource(Studio.plan_segment)
    assert '"shot_list"' in source
    assert "attribution" in source, "a plan built on somebody's art carries its credit"


def test_the_creature_comes_off_the_cut_outs_and_never_off_a_screenshot():
    """This rule has been round twice, and the second answer is the right one.

    It began as cut-outs only. I widened it to the whole gallery because Figure's
    appearance beat was cycling three pictures across eight shots while nine sat
    unused, which read as the "one monster shot" failure this format is named for.

    Then a finished video showed what those nine are. Downloading Figure's twelve and
    looking: two are creature art, five are gameplay screenshots with the game's own
    HUD in frame — hotbars, coin counters, a share button — two are dim in-game
    scenes, one is a motion-blurred phone photo, and `Figurebreaksthelamp.jpg` is a
    picture of a room with no creature in it. Widening the pool did not find nine more
    shots of the creature; it put somebody's screen recording on screen.

    The split is total and measurable: of those twelve, the two usable assets are the
    only two with an alpha channel — 62% and 63% transparent against 0.0% for every
    other one.
    """
    gallery = [{"name": f"screenshot{index}.png", "portrait": False} for index in range(9)]
    gallery += [{"name": f"cutout{index}.png", "portrait": True} for index in range(3)]
    entity = {"title": "Figure", "gallery": gallery,
              "stats": {"height": "9 ft"},
              "beats": {"appearance": "tall" * 60, "behaviour": "moves" * 60,
                        "survival": "hide" * 60}}

    planned = plan(entity, seconds=62.0)

    used = {shot.asset for shot in planned.shots if shot.asset}
    assert used, "nothing was planned at all"
    assert all(name.startswith("cutout") for name in used), (
        f"a wide asset reached the timeline as a creature shot: "
        f"{sorted(name for name in used if not name.startswith('cutout'))}")


def test_a_square_asset_with_no_alpha_channel_is_not_treated_as_a_creature_shot():
    """The shape is not the test, and on a real page the difference is a third of the
    pool.

    Figure's gallery has three roughly-square images. Two are the creature's artwork;
    the third — `FIGURE WITH EARS OMGGG.png` — is a near-black motion-blurred capture
    of the game, and the API reports it as `truecolour` where the other two are
    `truecolour-alpha`. On shape alone it was one subject shot in three.
    """
    gallery = [{"name": "cutout0.png", "portrait": True, "alpha": True},
               {"name": "cutout1.png", "portrait": True, "alpha": True},
               {"name": "blurry.png", "portrait": True, "alpha": False}]
    gallery += [{"name": f"screenshot{i}.jpg", "portrait": False, "alpha": False}
                for i in range(9)]
    entity = {"title": "Figure", "gallery": gallery, "stats": {},
              "beats": {"appearance": "tall" * 60, "behaviour": "moves" * 60,
                        "survival": "hide" * 60}}

    planned = plan(entity, seconds=62.0)

    used = {shot.asset for shot in planned.shots if shot.asset}
    assert used == {"cutout0.png", "cutout1.png"}, (
        f"an asset with no alpha channel reached the timeline as a creature shot: "
        f"{sorted(used - {'cutout0.png', 'cutout1.png'})}")


def test_a_gallery_that_says_nothing_about_alpha_is_still_planned_on_shape():
    """Only PNGs report a colour type, so a page of WEBP artwork carries no alpha flag
    at all. Treating silence as 'not a cut-out' would empty the subject pool for a whole
    wiki; the render-time test still checks the pixels."""
    gallery = [{"name": f"cutout{index}.png", "portrait": True} for index in range(3)]
    gallery += [{"name": "wide.png", "portrait": False}]
    entity = {"title": "Seek", "gallery": gallery, "stats": {},
              "beats": {"appearance": "tall" * 60, "behaviour": "moves" * 60}}

    planned = plan(entity, seconds=62.0)

    assert {shot.asset for shot in planned.shots} == {
        "cutout0.png", "cutout1.png", "cutout2.png"}


def test_every_cut_out_still_gets_used_before_any_is_repeated():
    """The half of the old concern that was right. Narrowing the pool to cut-outs is
    not licence to hammer one of them — the reference reuses a creature image across a
    segment, but it uses the ones it has."""
    gallery = [{"name": f"cutout{index}.png", "portrait": True} for index in range(4)]
    entity = {"title": "Seek", "gallery": gallery, "stats": {},
              "beats": {"appearance": "tall" * 60, "behaviour": "moves" * 60}}

    planned = plan(entity, seconds=62.0)

    assert len({shot.asset for shot in planned.shots}) == 4


def test_a_page_with_only_screenshots_still_makes_a_segment():
    """Some pages have no cut-out at all. Refusing would drop the entity entirely, and
    a screenshot of the creature is a worse shot than its artwork but a better one than
    a hole in the video."""
    gallery = [{"name": f"shot{index}.jpg", "portrait": False} for index in range(4)]
    entity = {"title": "Halt", "gallery": gallery, "stats": {},
              "beats": {"behaviour": "moves" * 60}}

    planned = plan(entity, seconds=40.0)

    assert planned.shots
    assert {shot.asset for shot in planned.shots} <= {f"shot{i}.jpg" for i in range(4)}


def test_motion_is_only_planned_where_there_is_something_to_move():
    """The ration used to land on exactly the shots that could not take it.

    Motion was assigned per shot as "the story beat, positions 0 and half way", and the
    story beat opens on a wide — so the two marked shots were the two with no cut-out in
    them. The renderer moves a subject against a still plate; handed a whole scene image
    it has no layer to separate. Every run planned two animated shots and rendered none,
    and neither the plan nor the video said anything was wrong.

    Found by running the real nodes against a real wiki page and counting the files that
    came out: sixteen shots, two marked for motion, zero clips.
    """
    gallery = [{"name": f"wide{index}.png", "portrait": False} for index in range(6)]
    gallery += [{"name": f"tall{index}.png", "portrait": True} for index in range(6)]
    entity = {"title": "Seek", "gallery": gallery, "stats": {"height": "3,3 m"},
              "beats": {"appearance": "tall " * 90, "behaviour": "moves " * 90,
                        "survival": "hide " * 90}}

    planned = plan(entity, seconds=62.0)

    moving = [shot for shot in planned.shots if shot.animate]
    assert moving, "nothing was marked for motion at all"
    assert all(shot.composite for shot in moving), \
        "a shot was marked for motion with no cut-out in it to move"


def test_a_segment_with_no_cutout_says_so_rather_than_marking_a_shot_anyway():
    """A page whose art is all scene shots cannot animate, and the honest output is a
    warning — not two shots marked for a move the renderer will silently decline."""
    entity = {"title": "Halt",
              "gallery": [{"name": f"wide{index}.png", "portrait": False}
                          for index in range(5)],
              "stats": {}, "beats": {"behaviour": "moves " * 90}}

    planned = plan(entity, seconds=40.0)

    assert not any(shot.animate for shot in planned.shots)
    assert any("nothing can move" in note for note in planned.warnings)
