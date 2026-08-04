"""The Sample Gate: prove the look on one clip before paying for eighty.

## Why this node exists

Image-to-video is about 90% of the cost of a long-form video — `ARCHITECTURE.md` works
the arithmetic and it is not close. Eighty shots at a few seconds each, at a per-second
rate, is the whole budget; everything else in the pipeline is noise beside it.

So the thing that must never happen is a full batch rendered on a look nobody has seen.
A grade that came back wrong, a camera move that melts faces, a register that is not the
one the channel uses — each of those is a defect in every clip at once, discovered after
all of them are paid for.

`skills/gates.py` has had the whole of this as pure functions since it was written:
coverage as style AND motion, waivers as operator input rather than a conclusion, two
charges never rolled into one. It carried a note that "the pipeline can be wired to this
later without either side growing a dependency on the other". It never was. Three shipped
skill documents told the agent the gate was mandatory — `image-to-video.md` calls it the
one rule that outranks all others, `storyboard.md` calls it the most expensive gate to
skip — for a gate the application could not run. This node is that wiring.

## Why it is a gate and not a check

The app's own argument, from `ARCHITECTURE.md`: a gate belongs on the stage that
*determines* the spend, not the stage that incurs it. This node spends a little — one
short clip per distinct setup — and authorises a great deal. That is exactly the shape
`final_review` already has before publishing, for the same reason.

## Why one sample per *setup*, not per shot

A sample per shot would cost as much as the render and gate nothing. A single sample for
the whole run would approve a batch containing camera moves nobody looked at, which is
the failure `gates.covers` exists to catch: two clips can share a grade and differ in
motion, and motion is where the melting happens.

So shots are grouped by `ShotSetup.setup_id` — model, style and motion together — and one
sample is generated per distinct group. On a normal video that is two or three samples
covering eighty shots.

## Why the model comes from the shot and not from the provider

`setup_id` has always hashed the model in, and this node used to overwrite every shot's
model with the single resolved provider's before grouping — so the facet that `gates.py`
calls "the largest single difference there is" was constant by construction and could
never split a group. Now that a plan routes its hero beats to one endpoint and the rest to
another, that would have shown the operator one sample and rendered the batch across two
models, one of which nobody looked at, at six times the rate of the one they approved.

Reading each shot's own model produces one sample per tier, which is not an extra cost so
much as the cost the gate was always supposed to surface: the hero sample is the only
evidence anybody has about the model doing the expensive work.

## What this node does not do

It does not render the batch and it does not decide whether the samples are good. It
generates them, prices what proceeding costs, and stops. `gates.surface()` assembles the
payload precisely so that a caller cannot show three of the four things an operator needs
and still call it a gate.
"""

from __future__ import annotations

import json

from ..graph.engine import NodeContext, NodeResult, node_handler
from ..providers import ProviderError, VideoProvider
from ..providers.media import STANDARD_TIER, model_for_tier, video_model
from ..skills import gates, prompt_check
from ._common import dimensions, tier_models

# What a shot with no stated camera is assumed to be doing. Matches the planner's own
# default in `prompts/moves.py`, so a shot that never named a move groups with the others
# that did not rather than forming a setup of its own.
DEFAULT_CAMERA = "push_in"

# A run with more distinct setups than this is not a style, it is a shot list nobody
# constrained — and sampling each one costs more than the batch it is protecting. The
# gate reports it rather than sampling them all, because the fix is to reduce the
# variation, not to buy thirty samples.
MAX_SETUPS = 6


def _setup_for(shot: dict, channel, aspect: str) -> gates.ShotSetup:
    """The style-and-motion key for one planned shot.

    Style comes from the channel rather than from the shot, because register, grade and
    lighting are channel-level decisions that every shot inherits — two shots differing
    only in subject are the same setup, and treating them as different is what makes a
    gate fire on every shot and get turned off.
    """
    profile = getattr(channel, "style_profile", None) or {}
    return gates.ShotSetup(
        model=str(shot.get("model") or ""),
        style=gates.StyleKey(
            register=str(profile.get("register") or ""),
            grade=str(profile.get("grade") or ""),
            lighting=str(profile.get("lighting") or ""),
            aspect_ratio=aspect,
        ),
        motion=gates.MotionKey(
            intensity=str(shot.get("intensity") or ""),
            focal_verb=str(shot.get("focal_verb") or ""),
            camera=str(shot.get("motion") or DEFAULT_CAMERA),
        ),
        seconds=float(shot.get("seconds") or 0.0),
        shot_id=str(shot.get("scene_index", "")),
    )


@node_handler("sample")
async def sample_node(ctx: NodeContext) -> NodeResult:
    """Generate one sample per distinct setup and stop for approval."""
    plan = ctx.output("broll_plan")
    shots = [shot for shot in (plan.get("shots") or [])
             if str(shot.get("kind")) == "video"]

    # No generated video means nothing to gate. Passing through rather than refusing:
    # a run whose shots are all stills is the cheap case this gate exists to protect,
    # and stopping it for an approval of nothing would be a gate that only ever
    # inconveniences the runs it was not built for.
    if not shots:
        ctx.log("no generated-video shots in this plan, so there is nothing to sample")
        return NodeResult(output={"samples": [], "setups": 0, "skipped": "no video shots"})

    # A plan made before shots carried a model has none to read, and that is a live case
    # rather than a hypothetical: a run paused at this very gate across the upgrade comes
    # back to a stored shot list with no `model` key. Filled in with the run's standing
    # choice, which is the endpoint it would have rendered on anyway — left empty,
    # `video_model("")` prices it at the unrecognised-model ceiling of $0.40 a second, and
    # an approval recorded against no endpoint names nothing an audit could check.
    standard_model, hero_model = tier_models(ctx)
    batch_model = model_for_tier(STANDARD_TIER, standard=standard_model, hero=hero_model)
    shots = [shot if shot.get("model") else {**shot, "model": batch_model}
             for shot in shots]

    # One provider per model the plan routed to. Two tiers is two endpoints, and the
    # sample for each has to come off the endpoint that tier will actually render on —
    # a hero sample generated on the batch model approves a look nothing will produce.
    providers: dict[str, VideoProvider] = {}
    for slug in sorted({shot["model"] for shot in shots}):
        try:
            providers[slug] = ctx.registry.video(slug)
        except ProviderError as exc:
            ctx.log(f"no video provider for {slug}, so nothing will be generated at "
                    f"full cost on it either: {exc}", level="warning")
    if not providers:
        return NodeResult(output={"samples": [], "setups": 0,
                                  "skipped": "no video provider"})

    width, height = dimensions(ctx)
    aspect = str(getattr(ctx.channel, "aspect_ratio", "") or "")

    grouped: dict[str, list[dict]] = {}
    setups: dict[str, gates.ShotSetup] = {}
    for shot in shots:
        # The shot's own model, not the provider's. See the module docstring: overwriting
        # it here made the one facet that separates a $0.03 endpoint from a $0.20 one
        # constant across the whole run, so the group it was meant to split never split.
        setup = _setup_for(shot, ctx.channel, aspect)
        grouped.setdefault(setup.setup_id, []).append(shot)
        setups.setdefault(setup.setup_id, setup)

    if len(setups) > MAX_SETUPS:
        # Reported, not silently sampled. Buying thirty samples to protect a batch is
        # the gate costing more than the thing it guards.
        ctx.log(f"{len(setups)} distinct setups in one run — more variation than a "
                f"sample gate can cover economically. Sampling the {MAX_SETUPS} "
                f"covering the most shots; the rest will need their own approval.",
                level="warning")

    ordered = sorted(setups.items(), key=lambda item: len(grouped[item[0]]), reverse=True)

    quotes: dict[str, gates.Quote] = {}
    for setup_id, setup in ordered:
        covered = grouped[setup_id]
        full_seconds = sum(float(shot.get("seconds") or 0.0) for shot in covered)
        # Priced from the catalogue rather than off the provider object, which is a fix
        # as well as a necessity. The duration envelope used to be read as
        # `shortest_seconds` and `longest_seconds` — attribute names no adapter in this
        # tree has ever carried — so both came back 0.0 and every sample was quoted at
        # five seconds whatever the model was. That under-quotes Hailuo, whose shortest
        # generation is six, and names a duration Sora rejects outright, since Sora takes
        # 4, 8, 12, 16 and 20 and nothing between.
        priced = video_model(setup.model)
        quotes[setup_id] = gates.quote(
            model=setup.model, usd_per_second=priced.usd_per_second,
            full_seconds=full_seconds,
            shortest_supported=priced.sample_seconds,
            longest_supported=priced.max_seconds)

    budget = gates.batch_budget(quotes)
    surfaced: list[dict] = []
    credits = 0
    spent = 0.0

    for setup_id, setup in ordered[:MAX_SETUPS]:
        covered = grouped[setup_id]
        first = covered[0]
        prompt = str(first.get("prompt") or first.get("visual_prompt") or "").strip()
        seconds = quotes[setup_id].sample.seconds

        # Settled before the prompt is read, and that order is deliberate rather than
        # tidy: everything from here down is the gate deciding what to show a person
        # about a clip it is about to buy, and a branch in the middle of that which can
        # skip a setup reads as the checker below taking the decision. This one is not a
        # judgement about the prompt — the tier's endpoint would not resolve, so there is
        # nothing to sample on. It is surfaced as an unapproved setup rather than sampled
        # on the other tier's model, because a clip from the wrong endpoint is worse than
        # no clip: it is evidence about something the batch will not run.
        video_provider = providers.get(setup.model)
        if video_provider is None:
            surfaced.append({"setup_id": setup_id, "model": setup.model, "clip": "",
                             "error": "no provider for this model",
                             "shots": len(covered)})
            continue

        # Read before it is paid for. `skills/prompt_check` has been able to say which
        # prompts melt since it was written and nothing had ever called it — so a prompt
        # chaining four finite verbs, or whip-panning across a face, was submitted,
        # billed in full, and thrown away. It costs nothing to ask, and the answer is
        # carried to the operator rather than acted on: the gate's whole shape is that a
        # person decides, so a checker that silently skipped a setup would be taking the
        # decision this node exists to hand over.
        #
        # The setup's own model, not the run's: `review` gives realism-model-specific
        # advice, and on a plan routing two endpoints there is no single model it could
        # be given that would be right for both setups.
        verdict = prompt_check.review(prompt, model=setup.model)
        if verdict.findings:
            ctx.log(f"setup {setup_id}: {verdict.summary()}",
                    level="warning" if verdict.blocked else "info")

        try:
            clip = await video_provider.generate_clip(
                prompt,
                out_path=ctx.path_for(f"sample_{setup_id}"),
                seconds=seconds, width=width, height=height,
            )
        except ProviderError as exc:
            # One failed sample does not fail the gate. The operator still has to see
            # the others, and a setup with no sample is reported as unapproved rather
            # than quietly rendered — which is the state this gate exists to prevent.
            ctx.log(f"sample for setup {setup_id} failed: {exc}", level="warning")
            surfaced.append({"setup_id": setup_id, "model": setup.model, "clip": "",
                             "error": str(exc), "shots": len(covered)})
            continue

        credits += clip.credits
        spent += quotes[setup_id].sample.usd
        ctx.emit_artifact("video", clip.path, clip.mime, role="sample",
                          setup_id=setup_id, shots_covered=len(covered),
                          seconds=clip.duration_seconds,
                          # Which endpoint this sample is evidence about. One gate can
                          # now hold a hero sample and a batch sample, and an approval
                          # that cannot name its model approves neither.
                          model=setup.model, tier=str(first.get("tier") or ""))

        payload = gates.surface(setup=setup, prompt=prompt, clip_path=str(clip.path),
                                quote_=quotes[setup_id], usd_spent_so_far=spent,
                                batch=budget)
        payload["shots"] = len(covered)
        # Travels with the sample, so the operator looking at a clip that is subtly wrong
        # has the reason in front of them rather than having to name it themselves.
        payload["prompt_review"] = verdict.as_dict()
        payload["scene_indexes"] = [shot.get("scene_index") for shot in covered]
        surfaced.append(payload)

    output = {
        "samples": surfaced,
        "setups": len(setups),
        "sampled": len([item for item in surfaced if item.get("clip")]),
        "batch": budget.as_dict(),
        # Written down so `shots` can check coverage against what was actually approved
        # rather than against what was planned — those differ the moment an operator
        # rejects one setup and approves another.
        "setup_ids": [setup_id for setup_id, _ in ordered],
        # Every endpoint this batch will touch. A gate that named one model while
        # authorising two would be the same defect as the one this node was fixed for,
        # moved from the grouping into the summary.
        "models": sorted({setup.model for setup in setups.values()}),
    }

    readable = ctx.path_for("samples.json")
    readable.write_text(json.dumps(output, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    ctx.emit_artifact("json", readable, "application/json", setups=len(setups))

    ctx.log(f"sampled {output['sampled']} of {len(setups)} setups covering "
            f"{len(shots)} shots — {budget.sentence() if hasattr(budget, 'sentence') else ''}")
    # The vendor, which is one vendor even when it is serving two models: they are
    # different endpoints on the same key. The first resolved provider is therefore the
    # right name for the ledger row, and there is no second name it could be.
    return NodeResult(output=output, credits=credits,
                      provider=next(iter(providers.values())).name)
