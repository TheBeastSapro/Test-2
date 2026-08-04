"""The scene plan holds type, and nothing in the tree still asks it for a card.

## Why this file exists

A `card` element — one still, centred and tilted with a shadow — was declared in
`render/scene_plan.py`, mirrored in `remotion/src/types.ts`, and drawn by the React
renderer and by the browser preview player. Three implementations, and no builder
anywhere emitted one, so no run could produce it. It was removed rather than wired,
because a plan describes a whole scene while `render.cutting` has already cut that
scene into shots across a plate each — see `scene_plan`'s module docstring for the
argument in full.

These tests are the part that keeps it removed. Deleting dead code is easy; the
expensive failure is the next person re-declaring the type on one side, seeing the
other side already draw it, and shipping the same unreachable element again. So the
assertions here are about *reach*: what a plan can actually contain when it is built
the way the backends build it, and whether either side of the contract has grown a
declaration the other cannot honour.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

import pytest

from forgecast.motion.presets import LIBRARY
from forgecast.render import cutting
from forgecast.render.scene_plan import ScenePlan, plan_from
from forgecast.style.editing import EditingStyle
from forgecast.vision import apply as vision_apply

REPO = Path(__file__).resolve().parent.parent
REMOTION = REPO / "remotion" / "src"

# Every kind `render.motion_layer.plan` can put on a MotionPlan. `none` never reaches
# `plan_from` — the backends return the untouched clip first — so the reachable set is
# these three plus the unknown-kind path exercised separately below.
KINDS = ("title", "lower_third", "kinetic")

# What the contract may contain. Kept as a literal rather than read off the module, so
# that adding a dataclass to `scene_plan` fails here instead of being waved through.
ELEMENT_KINDS = {"text", "band"}


def _every_reachable_element():
    """Every element every preset can put in a plan, across kinds and frame shapes.

    The whole library, not one preset: the card fields (`card_scale`, `card_zoom`,
    `card_tilt`, `card_shadow`) still sit on `MotionPreset`, so a preset is exactly the
    thing that could quietly reintroduce a card element if a builder started reading
    them again.
    """
    for preset in LIBRARY.values():
        for kind in KINDS:
            for width, height in ((1280, 720), (1080, 1920)):
                plan = plan_from(
                    preset, kind, ["A headline", "and its subhead"],
                    seconds=6.0, width=width, height=height,
                )
                yield preset, kind, plan


# ----------------------------------------------------------------- the plan itself


def test_no_preset_and_no_kind_can_put_a_card_in_a_plan():
    seen = set()
    for preset, kind, plan in _every_reachable_element():
        assert plan.elements, f"{preset.name}/{kind} produced an empty plan"
        for element in plan.elements:
            assert element.kind in ELEMENT_KINDS, (
                f"{preset.name}/{kind} emitted a {element.kind!r} element"
            )
            seen.add(element.kind)
    # Both survivors are actually reachable, so this file is testing a live contract
    # rather than asserting an empty set.
    assert seen == ELEMENT_KINDS


def test_the_serialised_payload_carries_no_card_either():
    """The backends ship JSON, not dataclasses, so the check has to survive `asdict`.

    Scanned over the elements rather than the whole payload, because `presetName` is
    legitimately `card_reveal` — the preset that names the removed element is still the
    library default, and it is the reason this needs asserting on shape not substring.
    """
    for _, _, plan in _every_reachable_element():
        payload = json.loads(plan.to_props())["plan"]
        for element in payload["elements"]:
            assert element["kind"] in ELEMENT_KINDS
            assert "src" not in element, "only a card ever carried a source path"
        assert "card" not in json.dumps(payload["elements"]).lower()


def test_a_background_image_stays_the_bed_and_is_not_inset_as_a_card(tmp_path):
    """The scene's picture fills the frame. That is the decision the card contradicted.

    A card would have shown this plate at ~56% of frame width on a flat field, which
    hides whatever `render.cutting` cut underneath it.
    """
    plate = tmp_path / "shot_000.png"
    plate.write_bytes(b"")
    plan = plan_from(LIBRARY["card_reveal"], "title", ["Hello"], seconds=4.0,
                     width=1280, height=720, background=plate)

    assert plan.background.kind == "image"
    assert plan.background.src == "shot_000.png"
    assert [element.kind for element in plan.elements] == ["band", "text"]


def test_scene_plan_declares_only_the_two_element_dataclasses():
    """A third `*Item` dataclass is how the card got here, so name the two that stay."""
    from forgecast.render import scene_plan

    declared = {
        name for name in vars(scene_plan)
        if name.endswith("Item") and isinstance(vars(scene_plan)[name], type)
    }
    assert declared == {"TextItem", "BandItem"}
    assert not hasattr(scene_plan, "card_item")


def test_an_unknown_kind_is_an_empty_plan_rather_than_a_guess():
    """Kept from the card's removal: `plan_from` must not invent an element for a kind
    it does not know, which is what a `card` branch falling through would have done."""
    plan = plan_from(LIBRARY["card_reveal"], "card", ["Hello"], seconds=4.0,
                     width=1280, height=720)
    assert plan.elements == []


# --------------------------------------------------------- planner and builder in step


def test_every_kind_the_planner_emits_is_a_kind_the_builder_draws():
    """The inverse of the bug this file records, and the more expensive direction.

    A builder with no emitter ships a visual no run can produce — that was the card. An
    emitter with no builder is worse: `motion_layer.plan` marks the scene active,
    `assemble_video` pays for an extra encode per scene, and the engine composites
    nothing over it. Neither side is authoritative on its own, so the two are compared.
    """
    from forgecast.render.ffmpeg import Scene as RenderScene
    from forgecast.render.motion_layer import plan as plan_motion

    preset = LIBRARY["kinetic_type"]           # intensity 0.9, so kinetic is reachable
    scenes = [
        RenderScene(index=index, seconds=9.0,
                    narration="Two facts. One cable. Nobody noticed it go.")
        for index in range(4)
    ]
    scenes.append(RenderScene(index=4, seconds=0.5, narration="too short"))

    plans = plan_motion(scenes, preset=preset, headline="Why the cables keep breaking")
    emitted = {item.kind for item in plans}
    assert {"title", "lower_third", "kinetic", "none"} <= emitted

    for item in plans:
        built = plan_from(preset, item.kind, list(item.lines), seconds=9.0,
                          width=1280, height=720)
        if item.active:
            assert built.elements, f"{item.kind!r} is planned but draws nothing"
            for element in built.elements:
                assert element.kind in ELEMENT_KINDS
        else:
            # `none` never reaches a builder — the backends return the clip untouched.
            assert not item.lines


# ------------------------------------------------------- the two sides of the contract


def test_nothing_in_the_tree_still_asks_for_a_card_element():
    """`scene_plan.py` is the source of truth; no Python may name the removed symbols."""
    offenders = []
    for path in REPO.glob("forgecast/**/*.py"):
        body = path.read_text(encoding="utf-8")
        # Docstrings record *why* it went, which is the one mention that should survive.
        code = re.sub(r'"""[\s\S]*?"""', "", body)
        for symbol in ("CardItem", "card_item"):
            if symbol in code:
                offenders.append(f"{path.relative_to(REPO)}: {symbol}")
    assert offenders == []


def test_the_typescript_contract_declares_the_same_elements_as_python():
    """types.ts mirrors `scene_plan.py` field for field, so its union has to match.

    Read as text rather than compiled: the suite must not need a Node toolchain, and a
    test that only runs where `npm install` was run is a test people learn to ignore.
    """
    types = (REMOTION / "types.ts").read_text(encoding="utf-8")
    union = re.search(r"export type SceneElement\s*=\s*([^;]+);", types)
    assert union, "types.ts no longer declares a SceneElement union"

    declared = {
        part.strip().removesuffix("Element").lower()
        for part in union.group(1).split("|")
    }
    assert declared == ELEMENT_KINDS
    assert "CardElement" not in types


def test_no_remotion_component_draws_an_element_the_plan_cannot_contain():
    """The React renderer is the half that was drawing a card nothing emitted."""
    for name in ("elements.tsx", "MotionScene.tsx"):
        source = (REMOTION / name).read_text(encoding="utf-8")
        code = re.sub(r"/\*[\s\S]*?\*/", "", source)      # keep the historical note
        assert "Card" not in code, f"{name} still references a Card component"


# ------------------------------------------------------------- the removed dead helper


def test_the_second_route_into_the_renderer_is_gone():
    """`apply.render_kwargs` packed settings the renderer never took under those names."""
    assert not hasattr(vision_apply, "render_kwargs")


def test_the_render_spec_is_the_route_those_settings_actually_take():
    """What `render_kwargs` claimed to do, done by the path that has a caller.

    `style.editing.to_render_spec` writes the profile the render node reads, and
    `render.cutting.spec_for` reads it back — the single path `to_render_spec`'s own
    docstring insists on, on the grounds that a second one means two places deciding
    how a video is cut.
    """
    style = EditingStyle(
        name="Ref", target_shot_seconds=2.5, transition="dissolve",
        ken_burns=False, zoom_rate=0.09, captions=True, caption_position="top_third",
        brightness=0.04, contrast=1.2, saturation=0.9,
    )
    spec = cutting.spec_for({"render_spec": style.to_render_spec()})

    assert spec.transition == "dissolve"
    assert spec.ken_burns is False
    assert spec.zoom_rate == pytest.approx(0.09)
    assert spec.captions is True
    assert spec.caption_position == "top_third"
    assert spec.grade_filter.startswith("eq=")
    # The rhythm too, since that is what the render node spends the spec on.
    assert spec.target_shot_seconds == pytest.approx(2.5)


def test_the_settings_reach_a_shot_plan_without_the_helper():
    """`build_plan` is what consumes the spec, and it carries them onto the plan."""
    style = EditingStyle(name="Ref", target_shot_seconds=2.0, transition="dissolve",
                         ken_burns=False, zoom_rate=0.09, caption_position="centre")
    spec = cutting.spec_for({"render_spec": style.to_render_spec()})
    plan = vision_apply.build_plan([8.0], spec)

    assert plan.transition == "dissolve"
    assert plan.ken_burns is False
    assert plan.zoom_rate == pytest.approx(0.09)
    assert plan.caption_position == "centre"
    assert plan.dissolve_seconds > 0
    assert len(plan.shots) > 1


def test_the_plan_a_default_channel_gets_is_unchanged_by_the_removal():
    """A channel with nothing measured still cuts at the shipped rhythm."""
    spec = cutting.spec_for(None)
    assert spec.target_shot_seconds == pytest.approx(cutting.DEFAULT_SHOT_SECONDS)
    assert asdict(ScenePlan(duration=2.0))["elements"] == []
