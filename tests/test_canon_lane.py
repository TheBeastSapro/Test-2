"""The canon lane, from a named wiki to a shot on the timeline.

This exists because of the defect this codebase keeps rediscovering and has named: a
module measured, documented, tested and never called. `edit/segment.py` wrote the shot
list for four commits while `broll_plan` did not call it, so every run still decided its
shots at render time and the planner was a very well-tested piece of dead code.

So the tests here are mostly about the *joins*, not the parts:

* research fetches the entities only when a wiki was named, and never invents one;
* the plan reaches the shot list, in timeline order, with the real file URL on it;
* a canon scene generates nothing and is charged for nothing;
* the licence stays unresolved all the way to the artifact, because on these wikis it
  genuinely is.

Nothing here touches a network.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from forgecast.graph.engine import ChannelSnapshot, NodeContext
from forgecast.nodes import media as media_node
from forgecast.nodes import research as research_node
from forgecast.providers import ProviderRegistry
from forgecast.research import canon

# Shaped exactly as `canon.gather` returns it — an entity dict with beats, stats and a
# gallery of assets that know whether they are a subject crop or already a shot.
SEEK = {
    "title": "Seek", "asked_for": "Seek", "usable": True,
    "wiki": "doors-game", "url": "https://doors-game.fandom.com/wiki/Seek",
    "attribution": "Seek — art from [Seek2.png](https://doors-game.fandom.com/wiki/"
                   "File:Seek2.png), page [Seek](https://doors-game.fandom.com/wiki/Seek)"
                   " on doors-game.fandom.com (licence not stated)",
    "stats": {"species": "Hostile (Lethal)"},
    "beats": {"appearance": "Seek is amorphous and black. " * 12,
              "behaviour": "Seek chases the player down corridors. " * 12,
              "survival": "Turn when the corridor turns. " * 12},
    "gallery": [
        {"name": "Seek2.png", "url": "https://static.example/Seek2.png",
         "page": "https://doors-game.fandom.com/wiki/File:Seek2.png",
         "size": [1200, 1600], "portrait": True, "licence": {}},
        {"name": "Seeklight.jpeg", "url": "https://static.example/Seeklight.jpeg",
         "page": "https://doors-game.fandom.com/wiki/File:Seeklight.jpeg",
         "size": [1920, 1080], "portrait": False, "licence": {}},
        {"name": "SeekHands.jpg", "url": "https://static.example/SeekHands.jpg",
         "page": "https://doors-game.fandom.com/wiki/File:SeekHands.jpg",
         "size": [1600, 900], "portrait": False, "licence": {}},
        {"name": "EyeRender.png", "url": "https://static.example/EyeRender.png",
         "page": "https://doors-game.fandom.com/wiki/File:EyeRender.png",
         "size": [2000, 2000], "portrait": True,
         "licence": {"LicenseShortName": "CC BY-SA 3.0", "Artist": "somebody"}},
    ],
}

SCENES = [
    {"index": 0, "narration": "Every run of Doors ends the same way.",
     "seconds": 9.0, "visual_prompt": "a dark hotel corridor"},
    {"index": 1, "narration": "Seek is the one nobody outruns the first time.",
     "seconds": 20.0, "visual_prompt": "something black in the dark"},
    {"index": 2, "narration": "Seek fills the corridor behind you.",
     "seconds": 20.0, "visual_prompt": "a corridor"},
    {"index": 3, "narration": "And then the door closes.",
     "seconds": 9.0, "visual_prompt": "a closing door"},
]


def _context(tmp_path: Path, *, entities=(SEEK,), scenes=SCENES,
             node: str = "broll_plan", params=None,
             style_profile=None) -> NodeContext:
    return NodeContext(
        run_id=1, topic="The scariest entities in Doors", options={},
        node_key=node, node_type=node, params=params or {}, attempts=0,
        channel=ChannelSnapshot(
            id=1, name="Test Channel", niche="horror", language="en", voice_id="",
            avatar_id="", aspect_ratio="16:9", target_duration_seconds=300,
            style_profile=style_profile if style_profile is not None else {},
            video_model="", video_model_hero="",
        ),
        registry=ProviderRegistry(mode="mock"),
        workdir=tmp_path / "work",
        upstream_outputs={
            "script": {"scenes": list(scenes)},
            "research": {"canon": {"wiki": "doors-game", "entities": list(entities)}},
        },
    )


async def _plan(tmp_path, monkeypatch, **kwargs) -> dict:
    """Run `broll_plan` with the model's half of the planning stubbed out."""
    asked: list[dict] = []

    async def canned(ctx, **kwargs):
        # The payload reaches the model as JSON text, so the scene list it was actually
        # asked about is read back out of it rather than assumed.
        payload = json.loads(kwargs.get("payload") or "{}")
        asked.append(payload)
        return ({"shots": [{"scene_index": scene["index"], "kind": "image",
                            "prompt": "a generated impression"}
                           for scene in (payload.get("scenes") or [])]}, 7, "stub-llm")

    monkeypatch.setattr(media_node, "ask_json", canned)
    result = await media_node.broll_plan_node(_context(tmp_path, **kwargs))
    result.output["_asked"] = asked
    return result.output


# ------------------------------------------------------------- the plan reaches the run


@pytest.mark.asyncio
async def test_the_written_shot_list_is_what_the_run_renders(tmp_path, monkeypatch):
    """The planner is in the pipeline, which for four commits it was not.

    `edit/segment.py` decided the beats, the holds and which picture carries which shot,
    and `broll_plan` ignored all of it. A run still chose each shot at render time and
    the plan was dead code with a test suite.
    """
    output = await _plan(tmp_path, monkeypatch)

    canon_shots = [shot for shot in output["shots"] if shot["kind"] == "canon"]
    assert canon_shots, "the segment plan never reached the shot list"
    assert output["canon_scenes"] == 2      # scenes 1 and 2 name Seek
    assert output["canon_shots"] == len(canon_shots)

    # Every one carries a real file URL off the wiki rather than a prompt to invent one.
    urls = {shot["asset_url"] for shot in canon_shots}
    assert urls and all(url.startswith("https://static.example/") for url in urls)
    # ...and more than one picture, which is the difference between an edit and a
    # slideshow with a Ken Burns push on it.
    assert len({shot["asset"] for shot in canon_shots}) >= 3


@pytest.mark.asyncio
async def test_the_shot_list_stays_in_timeline_order(tmp_path, monkeypatch):
    """Appending the canon block would render fine and cut the video out of sequence.

    `shots_node` walks this list in order and the render assembles in the order it is
    handed, so a scene-3 shot sitting before a scene-1 shot is a defect that produces a
    playable file and a wrong video.
    """
    output = await _plan(tmp_path, monkeypatch)

    keys = [(shot["scene_index"], shot["plate_index"]) for shot in output["shots"]]
    assert keys == sorted(keys)
    # Both lanes are present and interleaved by scene, not grouped by kind.
    assert {shot["kind"] for shot in output["shots"]} == {"image", "canon"}


@pytest.mark.asyncio
async def test_a_canon_scene_is_never_sent_to_the_planner_or_charged_for(
        tmp_path, monkeypatch):
    """It buys nothing, so it must appear in no budget and no prompt.

    Paying planning tokens for a description of a picture the run already holds is the
    small half. The large half is that a planned prompt is a prompt something will
    render, and a generated depiction of a named creature is the substitution this
    audience reliably catches.
    """
    output = await _plan(tmp_path, monkeypatch)

    sent = output["_asked"][0]["scenes"]
    assert [scene["index"] for scene in sent] == [0, 3]

    assert output["video_usd"] == 0.0
    assert output["video_shots"] == 0
    assert output["moving_shots"] == 0
    # The canon shots still count as shots — they are on screen, they just cost nothing.
    assert output["planned_shots"] >= output["canon_shots"]


@pytest.mark.asyncio
async def test_a_wholly_canon_video_asks_the_model_nothing(tmp_path, monkeypatch):
    """With no scene left to plan there is no question to pay for — and an empty scene
    list handed to a planner comes back as a shot list for nothing."""
    every = [dict(scene, narration=f"Seek does something. {scene['narration']}")
             for scene in SCENES]

    output = await _plan(tmp_path, monkeypatch, scenes=every)

    assert output["_asked"] == []
    assert output["canon_scenes"] == 4
    assert all(shot["kind"] == "canon" for shot in output["shots"])


@pytest.mark.asyncio
async def test_an_entity_no_scene_names_is_reported_rather_than_forced_in(
        tmp_path, monkeypatch):
    """Fetched and unused is a real outcome and the operator has to hear it.

    Forcing it onto a scene would put a creature's artwork under narration about a
    different creature, which is worse than the hole it fills.
    """
    other = dict(SEEK, title="Figure", asked_for="Figure")

    output = await _plan(tmp_path, monkeypatch, entities=(SEEK, other))

    assert not any(shot.get("prompt", "").startswith("Figure")
                   for shot in output["shots"])
    assert output["canon_scenes"] == 2


@pytest.mark.asyncio
async def test_no_canon_research_leaves_the_old_path_exactly_as_it_was(
        tmp_path, monkeypatch):
    """The lane is an addition. A run with no wiki must plan and spend as before."""
    output = await _plan(tmp_path, monkeypatch, entities=())

    assert output["canon_scenes"] == 0
    assert output["canon_shots"] == 0
    assert [scene["index"] for scene in output["_asked"][0]["scenes"]] == [0, 1, 2, 3]
    assert all(shot["kind"] != "canon" for shot in output["shots"])


# ------------------------------------------------------------------- rights, unresolved


@pytest.mark.asyncio
async def test_the_licence_travels_unresolved_and_is_never_decided_here(
        tmp_path, monkeypatch):
    """Fandom's site text is CC-BY-SA; the uploaded art frequently is not, and the API
    returns no licence fields at all for most of it. So the shot carries the file page
    and whatever did come back — and "not stated" reaches the artifact as itself.

    Guessing the permissive answer is the expensive kind of wrong, and it would be this
    app vouching for a licence it never established.
    """
    output = await _plan(tmp_path, monkeypatch)

    for shot in [shot for shot in output["shots"] if shot["kind"] == "canon"]:
        assert shot["asset_page"].startswith("https://doors-game.fandom.com/wiki/File:")
        assert shot["attribution"]
        assert "licence not stated" in shot["attribution"]
        assert isinstance(shot["licence"], dict)   # empty means unknown, never free


# ------------------------------------------------------------ research names its wiki


class _Recorder:
    """Stands in for `canon.gather`, recording what it was asked for."""

    def __init__(self):
        self.calls: list[tuple[str, list[str]]] = []

    async def __call__(self, wiki, entities, **_kwargs):
        self.calls.append((wiki, list(entities)))
        return canon.Gathered(wiki=wiki)


def _research_context(tmp_path, *, params=None, style_profile=None,
                      brief=None) -> NodeContext:
    return NodeContext(
        run_id=1, topic="The scariest entities in Doors", options={},
        node_key="research", node_type="research", params=params or {}, attempts=0,
        channel=ChannelSnapshot(
            id=1, name="Test", niche="horror", language="en", voice_id="",
            avatar_id="", aspect_ratio="16:9", target_duration_seconds=300,
            style_profile=style_profile or {}, video_model="", video_model_hero="",
        ),
        registry=ProviderRegistry(mode="mock"),
        workdir=tmp_path / "work",
        upstream_outputs={"brief": brief or {}},
    )


@pytest.mark.asyncio
async def test_the_lane_is_off_until_a_wiki_is_named(tmp_path, monkeypatch):
    """A wiki is a real subdomain and no rule derives it from a topic.

    Doors lives on `doors-game`, not `doors`; Siren Head lives on `trevorhenderson`.
    Inferring one would fetch somebody else's abandoned fork and present it as canon —
    which is the failure mode this whole module was built to refuse.
    """
    recorder = _Recorder()
    monkeypatch.setattr(canon, "gather", recorder)

    payload = {}
    await research_node._canon_lane(
        _research_context(tmp_path, brief={"beats": [{"name": "Seek"}]}), payload, {})

    assert recorder.calls == []
    assert "canon" not in payload


@pytest.mark.asyncio
async def test_the_entity_list_comes_from_the_run_and_not_from_the_topic(
        tmp_path, monkeypatch):
    """Run params settle it; failing that the brief's beat names, which for this format
    *are* the creatures. Never the topic string — "seven scariest creatures" names no
    creature, and a lane that produced seven would have invented them."""
    recorder = _Recorder()
    monkeypatch.setattr(canon, "gather", recorder)

    brief = {"beats": [{"name": "Seek"}, {"name": "Figure"}, {"name": "Halt"}]}
    context = _research_context(tmp_path, params={"wiki": "doors-game"}, brief=brief)
    await research_node._canon_lane(context, {}, brief)

    assert recorder.calls == [("doors-game", ["Seek", "Figure", "Halt"])]


@pytest.mark.asyncio
async def test_an_operator_list_beats_the_brief(tmp_path, monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr(canon, "gather", recorder)

    brief = {"beats": [{"name": "Beat 1"}, {"name": "Beat 2"}]}
    context = _research_context(
        tmp_path, params={"wiki": "doors-game", "entities": "Seek, Figure"}, brief=brief)
    await research_node._canon_lane(context, {}, brief)

    assert recorder.calls == [("doors-game", ["Seek", "Figure"])]


@pytest.mark.asyncio
async def test_a_channel_can_carry_its_wiki_so_every_run_does_not_retype_it(
        tmp_path, monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr(canon, "gather", recorder)

    brief = {"beats": [{"name": "Seek"}]}
    context = _research_context(
        tmp_path, style_profile={"canon_wiki": "doors-game"}, brief=brief)
    await research_node._canon_lane(context, {}, brief)

    assert recorder.calls == [("doors-game", ["Seek"])]


@pytest.mark.asyncio
async def test_a_wiki_that_cannot_be_read_does_not_stop_the_run(tmp_path, monkeypatch):
    """The lane is an enrichment. A run whose wiki is unreachable should produce the
    video the open-web research supports, not die holding a network error."""
    async def explode(*_args, **_kwargs):
        raise RuntimeError("the wiki is down")

    monkeypatch.setattr(canon, "gather", explode)

    payload = {"counts": {}}
    brief = {"beats": [{"name": "Seek"}]}
    await research_node._canon_lane(
        _research_context(tmp_path, params={"wiki": "doors-game"}, brief=brief),
        payload, brief)

    assert "canon" not in payload


# ------------------------------------------------------------------ names off real URLs


def test_a_wiki_name_is_read_out_of_a_url_and_never_constructed():
    """Every candidate appeared in a link somebody's search returned, so the worst case
    is a wiki that exists and is wrong — never a subdomain nobody registered."""
    names = canon.wiki_names([
        "https://doors-game.fandom.com/wiki/Seek",
        "https://community.fandom.com/wiki/Help:Contents",   # fandom's own plumbing
        "https://trevorhenderson.wikia.com/wiki/Siren_Head",  # the legacy host
        "https://en.wikipedia.org/wiki/Doors",                # not fandom at all
        "https://doors-game.fandom.com/wiki/Figure",          # already seen
    ])

    assert names == ["doors-game", "trevorhenderson"]


@pytest.mark.asyncio
async def test_discovery_without_a_search_provider_returns_nothing_not_a_guess():
    """An empty list is a caller's cue to ask which wiki. A constructed subdomain is a
    wrong answer wearing a right answer's clothes."""
    assert await canon.discover("Doors", search=None) == []


# ------------------------------------------------------------- the shot reaches the disk


class _CountingImages:
    """An image provider that records every plate it was asked to make."""

    def __init__(self, tmp_path: Path):
        self.prompts: list[str] = []
        self._tmp = tmp_path

    async def generate(self, prompt, *, out_path, width, height):
        from PIL import Image

        from forgecast.providers import MediaResult

        self.prompts.append(prompt)
        path = Path(f"{out_path}.png")
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (width, height), (40, 40, 60)).save(path)
        return MediaResult(path=path, mime="image/png", credits=1, provider="stub")


def _canon_shot(**over) -> dict:
    shot = {"scene_index": 1, "plate_index": 0, "plates": 2, "planned_shots": 2,
            "kind": "canon", "seconds": 3.0, "beat": "appearance",
            "prompt": "Seek — appearance", "asset": "Seek2.png",
            "asset_url": "https://static.example/Seek2.png",
            "asset_page": "https://doors-game.fandom.com/wiki/File:Seek2.png",
            "licence": {}, "attribution": "Seek — art from ... (licence not stated)",
            "source_page": "https://doors-game.fandom.com/wiki/Seek",
            "composite": True, "plate_group": "Seek",
            "plate_prompt": "Background plate: a dark hotel corridor. Empty environment "
                            "only. No creature, no figure, no person.",
            "plate_asset": "Seeklight.jpeg",
            "plate_url": "https://static.example/Seeklight.jpeg",
            "overlays": [], "animate": False, "tier": "standard", "model": "",
            "places": []}
    shot.update(over)
    return shot


@pytest.mark.asyncio
async def test_one_plate_is_bought_for_a_segment_and_not_one_per_shot(
        tmp_path, monkeypatch):
    """The reference reuses its plate across a creature's whole segment.

    A plate a shot would pay twenty times over for a location the format only has one
    of — and to the eye it reads as the creature teleporting between cuts.
    """
    from PIL import Image

    def fake_fetch(ctx, shot, slug):
        path = Path(ctx.path_for(f"{slug}.png"))
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (600, 600), (200, 30, 30, 255)).save(path)
        return path

    monkeypatch.setattr(media_node, "_fetch_canon", fake_fetch)
    images = _CountingImages(tmp_path)

    context = _context(tmp_path, node="shots")
    context.upstream_outputs["broll_plan"] = {
        "shots": [_canon_shot(plate_index=index, scene_index=1 + index // 3)
                  for index in range(6)]}
    monkeypatch.setattr(context.registry, "image", lambda: images)

    result = await media_node.shots_node(context)

    assert len(images.prompts) == 1, images.prompts
    assert len(result.output["shots"]) == 6
    assert {shot["kind"] for shot in result.output["shots"]} == {"canon"}


@pytest.mark.asyncio
async def test_the_plate_prompt_forbids_the_subject_it_will_be_composited_under(
        tmp_path, monkeypatch):
    """A generation model handed scene text about a creature draws the creature.

    The cut-out goes on top, so a plate with its own creature in it renders two — and
    the second one is the generated depiction this whole lane exists to avoid.
    """
    prompt = media_node._plate_prompt(
        {"title": "Seek"},
        [{"visual_prompt": "Seek looms in a dark hotel corridor"}])

    assert "No creature" in prompt
    assert "No text, no logo, no interface" in prompt
    assert "dark hotel corridor" in prompt


@pytest.mark.asyncio
async def test_a_subject_that_cannot_be_fetched_is_a_hole_and_never_a_substitute(
        tmp_path, monkeypatch):
    """The honest failure for a canon shot is a missing shot an operator can fix.

    Falling through to generation would put an invented depiction of a named creature
    on screen — which is the one substitution this audience reliably catches, arriving
    through the error path rather than the happy one.
    """
    from forgecast.providers import ProviderError

    monkeypatch.setattr(media_node, "_fetch_canon", lambda ctx, shot, slug: None)
    images = _CountingImages(tmp_path)

    context = _context(tmp_path, node="shots")
    context.upstream_outputs["broll_plan"] = {"shots": [_canon_shot()]}
    monkeypatch.setattr(context.registry, "image", lambda: images)

    # A run whose only shot could not be fetched has produced no video, and saying so
    # is right. The point of the test is what it did *not* do on the way there.
    with pytest.raises(ProviderError):
        await media_node.shots_node(context)

    assert images.prompts == [], "a failed canon fetch bought a generated stand-in"


# ------------------------------------------------------- the planner's marks on screen


def test_the_planner_s_words_map_onto_the_renderer_s_kinds():
    """Two vocabularies for one set of things, and the mapping is where it goes quiet.

    `edit/segment.py` writes what an editor writes on a shot list — "name card",
    "bubble: it can smell you". `render/motion_layer.py` dispatches on identifiers —
    `name_card`, `bubble`. An unmapped label falls through to no motion, so the run
    renders a video with none of the graphics its plan chose and nothing says so.
    """
    from forgecast.render.motion_layer import OVERLAY_KINDS, from_overlays

    assert from_overlays(["name card"], entity="Seek") == {
        "kind": "name_card", "lines": ["Seek"]}
    assert from_overlays(["bubble: it can smell you"]) == {
        "kind": "bubble", "lines": ["it can smell you"]}
    assert from_overlays(["stat card"], stats={"height": "3,3 m"}) == {
        "kind": "stat_card", "lines": ["height  3,3 m"]}

    # Every label the planner can write has a kind here. This is the assertion that
    # fails when somebody adds a fourth element to the planner and stops there.
    from forgecast.edit import segment as planner

    source = inspect.getsource(planner)
    for label in OVERLAY_KINDS:
        assert f'"{label}' in source, f"{label!r} is mapped but the planner never writes it"


def test_a_scene_gets_one_element_and_the_name_card_wins():
    """Motion is applied per scene — `assemble_video` says so — so several marks on one
    scene's shots is a real choice. The name card opens the segment and is the thing a
    viewer has to read before anything else on screen means anything."""
    from forgecast.render.motion_layer import from_overlays

    both = from_overlays(["stat card", "bubble: hi", "name card"],
                         entity="Seek", stats={"height": "3,3 m"})

    assert both == {"kind": "name_card", "lines": ["Seek"]}


def test_an_element_with_nothing_to_draw_is_not_planned():
    """A stat card for a page with no stats is an empty box, and a name card with no
    name is worse than no card."""
    from forgecast.render.motion_layer import from_overlays

    assert from_overlays(["stat card"], entity="Seek", stats={}) == {}
    assert from_overlays(["name card"], entity="") == {}
    assert from_overlays(["something nobody defined"], entity="Seek") == {}


def test_a_stat_row_of_prose_is_reduced_to_its_figures_and_never_invents_one():
    """Wiki infoboxes write sentences into number fields.

    Siren Head's height is "Varies, though commonly set at 40 feet/12.19 meters."
    Truncated to a row it reads "Varies, though commonly set at 40…" — losing the
    figure and keeping the hedge, which is the worst of both. Every value below is live
    off a real page.
    """
    from forgecast.motion.presets import STAT_VALUE_CHARS, _figures

    assert _figures("Varies, though commonly set at 40 feet/12.19 meters.",
                    STAT_VALUE_CHARS) == "40 feet / 12.19 meters"
    # No measurement in it, so nothing is invented — it truncates like any other prose.
    assert _figures("Variable (usually dwarfs humans in size)",
                    STAT_VALUE_CHARS) == "Variable (usually dwarfs humans in size)"
    # A real answer that happens not to be a number.
    assert _figures("Immeasurable", STAT_VALUE_CHARS) == "Immeasurable"
    # Already fits, so it is never touched — including its European decimal comma.
    assert _figures("3,3 m", STAT_VALUE_CHARS) == "3,3 m"


# ---------------------------------------------------- which scene an entity actually is


RUSH = dict(SEEK, title="Rush", asked_for="Rush")


def _scenes(*narrations):
    return [{"index": index, "narration": text, "seconds": 20.0, "visual_prompt": "x"}
            for index, text in enumerate(narrations)]


def test_a_creature_named_after_a_common_word_does_not_claim_every_scene():
    """Doors has entities called Rush and Halt.

    Substring matching gave "do not rush the last door" and "a halt in the music" a
    segment each — the wrong creature's artwork under narration about something else,
    which is worse than the hole it fills and is exactly the error this audience
    catches. A creature is a proper noun and a script writes it as one, so the capital
    is evidence.
    """
    scenes = _scenes("Do not rush through the last door.",
                     "Rush appears as a black smear in the corridor.",
                     "Whatever you do, do not rush.")

    owned, loose = media_node._scenes_for(RUSH, scenes)

    assert [scene["index"] for scene in owned] == [1]
    assert not loose


def test_a_script_that_lower_cases_its_names_still_works_and_says_so():
    """The fallback is a fallback, not the rule. A run should still produce a video —
    and an operator should be able to see why a scene was claimed."""
    scenes = _scenes("the rush comes down the corridor at you.",
                     "Nothing to do with it.")

    owned, loose = media_node._scenes_for(RUSH, scenes)

    assert [scene["index"] for scene in owned] == [0]
    assert "ignoring case" in loose


def test_a_name_inside_a_longer_word_is_not_a_match():
    """"Rushing" is not Rush, and "Seeker" is not Seek."""
    owned, _ = media_node._scenes_for(RUSH, _scenes("Rushing water fills the room."))

    assert owned == []
