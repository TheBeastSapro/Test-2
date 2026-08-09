"""The shipped pipelines.

`faceless_longform` is the flagship: an 8–12 minute narrated documentary-style
video with generated B-roll, optional talking-head insert, burned captions and a
scheduled upload. `faceless_shorts` is the same spine compressed to a vertical clip.

Gates are placed where a human veto is cheapest. Approving a brief costs nothing;
approving a finished render costs whatever the shots already burned. So the
expensive stages sit *behind* gates on the cheap stages that determine them.
"""

from __future__ import annotations

from ..credits import PER_UNIT_COSTS
from ..providers.media import HERO_TIER, STANDARD_TIER, model_for_tier, video_reserve_credits
from ..render.cutting import estimate_plates, max_scenes, plates_for, spec_for
from ..skills.gates import MAX_SETUPS
from ..style.editing import HOOK_SECONDS, WORDS_PER_SECOND, writing_budget
from ..style.sourcing import budgets as style_budgets
from .spec import NodeSpec, PipelineSpec

# Both of these were literals here, and the hook window was a literal here *and* in
# `nodes/hook.py` with a test holding the two together — the trick `models.py` uses for
# `HOUSE_SLUG`, adopted because importing from `nodes.hook` would close a cycle
# (`nodes/__init__` imports `hook`, `hook` imports `graph.engine`, `graph.engine` imports
# this module).
#
# There is no cycle through `style.editing`, so the copies are gone. They live beside the
# measurement that overrides them, because a shipped default kept somewhere else from its
# override is the one that goes stale without anybody finding out. `writing_budget` is the
# single function that chooses between the two, and it is the same one `nodes.content`
# writes the script with and `nodes.hook` cuts the opening to — a reserve priced off one
# rate while the script is written at another is a hold that does not cover its own run.
#
# Both names are re-exported rather than merely imported: `pipelines.WORDS_PER_SECOND` is
# what the pricing tests read, and the shipped rate is a fact about this module's estimates
# whichever file now holds the literal.
__all__ = [
    "HOOK_SECONDS",
    "PIPELINES",
    "PIPELINE_META",
    "WORDS_PER_SECOND",
    "animation_reserve",
    "faceless_longform",
    "faceless_shorts",
    "get_pipeline",
]

# What one generated plate costs, from the row that prices the same vendor call for the
# thumbnail node. Read rather than restated so a change to the image rate moves both.
STILL_CREDITS = PER_UNIT_COSTS["thumbnail"][1]


def animation_reserve(
    target_seconds: float, *, standard: str = "", hero: str = "",
    sourcing: dict | None = None, render_spec: dict | None = None,
) -> tuple[int, int]:
    """Credits to hold for `sample` and `shots` on this channel's chosen models.

    Why this is not a row in `PER_UNIT_COSTS`. That table holds one figure per node type,
    and both of these nodes are priced almost entirely by *which model the channel picked*
    — the selectable endpoints run from $0.03 a second to $0.20, so any single figure is
    right for one channel and wrong by up to seven times for the rest. It was wrong in the
    direction that costs money: the `shots` row held a blended 22 credits a plate against
    a worst case near 70, and `sample` held one setup's worth of the default model against
    a gate that will buy four on the premium one.

    A reserve is released when the node settles, so holding too much costs a user nothing
    but the wait; holding too little means a run whose later nodes spend past the hold,
    which the ledger has no way to refuse once the run is under way. So this takes the
    worst legal shape rather than the likely one, exactly as `estimate_plates` does.

    Worst legal shape means: over every scene count a script may plausibly have, the split
    that costs the most. Scene count moves three things in opposite directions — a denser
    script buys more animated beats but shorter ones, and more scenes each buying at least
    one plate — so which split is dearest is not something to reason about in a comment.
    Enumerate them and take the maximum. The ceiling comes from `max_scenes`, i.e. from the
    scripting cadence that tells the model how many beats to write.

    `render_spec` is the channel's cutting rhythm and it is here because a measured
    channel now buys plates per shot rather than per second — so how fast it cuts is part
    of what it spends, and a reserve priced at the default 3.5s rhythm would be short by
    the ratio on any channel that cuts faster than that. It travels beside `sourcing`
    because both are read off the same learned style and neither means much without the
    other: variety says how often the picture changes, the rhythm says how often there is
    a cut for it to change on.
    """
    total = max(0.0, float(target_seconds or 0.0))
    hero_slug = model_for_tier(HERO_TIER, standard=standard, hero=hero)
    batch_slug = model_for_tier(STANDARD_TIER, standard=standard, hero=hero)
    spec = spec_for({"render_spec": render_spec} if render_spec else None)

    worst_shots = 0
    worst_setups = 0
    for scenes in range(1, max_scenes(total) + 1):
        seconds = total / scenes
        # The same call `broll_plan_node` makes, so the hold and the spend read one
        # measurement. A channel modelled on a cinematic reference animates most of its
        # beats and must be held for most of its beats.
        clips, heroes = style_budgets(sourcing, scenes)
        # An animated beat buys one plate and one clip; every other beat buys stills, and
        # a still is the cheap half of this. Maps buy one plate and no clip, so counting
        # every non-animated beat as stills is the dearer reading and the right one here.
        plates = clips + (scenes - clips) * plates_for(seconds, spec, sourcing=sourcing)
        worst_shots = max(worst_shots, plates * STILL_CREDITS
                          + heroes * video_reserve_credits(hero_slug, seconds)
                          + (clips - heroes) * video_reserve_credits(batch_slug, seconds))
        worst_setups = max(worst_setups, min(MAX_SETUPS, clips))

    # A sample is one short clip per distinct setup, and a setup cannot exist without an
    # animated shot to belong to — so the gate's own ceiling is not the binding one here,
    # the animation budget is. Priced on the dearer of the two models because nothing at
    # plan time says which setups will be hero beats.
    dearest_sample = max(video_reserve_credits(hero_slug, 0, samples=1),
                         video_reserve_credits(batch_slug, 0, samples=1))
    return worst_setups * dearest_sample, worst_shots


def burns_captions(render_spec: dict | None) -> bool:
    """Whether this channel burns the narration onto the picture.

    Read off the learned style rather than configured, like every other decision that
    can be measured. `EditingStyle` has carried `captions` since it was first learned —
    it is a majority vote over what the reference's own frames do — and
    `to_render_spec` has always emitted it. Nothing read it. Both pipelines pinned
    `params={"subtitles": True}`, so a reference measured as caption-free still got
    captions burned over it, and the measurement was recorded and overruled in the same
    run.

    That is not a small stylistic default. On the format this was found against, the
    screen carries the subject's name, its dimensions, and speech-bubble jokes, and the
    voice carries the prose; burning a narration track across the lower third covers all
    three. A channel measured as caption-free is telling you where its screen budget
    goes.

    Absent a learned style there is no measurement to honour, and captions stay on —
    that is the safer default for an unmeasured channel and it is what every existing
    run did.
    """
    if not render_spec:
        return True
    return bool(render_spec.get("captions", True))


def faceless_longform(
    *, target_seconds: int = 480, use_avatar: bool = False, publish: bool = True,
    standard_model: str = "", hero_model: str = "", sourcing: dict | None = None,
    render_spec: dict | None = None, narrative: dict | None = None,
) -> PipelineSpec:
    # How fast this channel talks and how long its opening beat runs, from the same
    # learned style `sourcing` comes from. Absent on a channel with no reference, which
    # `writing_budget` reads as "use the shipped rate and the shipped window" — so an
    # unmeasured channel reserves exactly what it reserved before this existed.
    budget = writing_budget(narrative)
    words = budget.words_for(target_seconds)
    # The shots node buys *plates*, not shots: one image carries several shots at
    # different crops. This used to reserve `target_seconds / 6` units — about 80 for an
    # 8-minute video against the eight the node then spent, wrong by an order of
    # magnitude in the safe direction. Deriving it from the same constants the node uses
    # means the reserve now tracks the spend instead of guessing at it.
    shots = estimate_plates(target_seconds, sourcing=sourcing,
                            spec=spec_for({"render_spec": render_spec} if render_spec else None))
    sample_credits, shots_credits = animation_reserve(
        target_seconds, standard=standard_model, hero=hero_model, sourcing=sourcing,
        render_spec=render_spec)

    nodes: list[NodeSpec] = [
        NodeSpec(
            key="brief",
            type="brief",
            title="Create production brief",
            requires_approval=True,
            params={"target_duration_seconds": target_seconds},
        ),
        NodeSpec(
            key="research",
            type="research",
            title="Research & verify sources",
            depends_on=("brief",),
            params={"max_queries": 5, "max_pages": 8},
        ),
        NodeSpec(
            key="script",
            type="script",
            title="Write full script",
            # Research first: a documentary script with no sources invents its
            # statistics, and the citation rule needs real claims to point at.
            depends_on=("brief", "research"),
            requires_approval=True,
            estimated_units=words,
            params={"target_duration_seconds": target_seconds},
        ),
        NodeSpec(
            key="thumbnail",
            type="thumbnail",
            title="Generate thumbnail",
            depends_on=("script",),
            requires_approval=True,
            estimated_units=2,
            params={"concepts": 2},
        ),
        NodeSpec(
            key="voice_casting",
            type="voice_casting",
            title="Cast the voice",
            depends_on=("script",),
            # Gated: the voice is the most audible decision in the video, so the
            # system auditions candidates and a human picks.
            requires_approval=True,
            estimated_units=3,
            params={"shortlist": 3},
        ),
        NodeSpec(
            key="hook",
            type="hook",
            title="Cut and approve the opening",
            # The same argument as the Sample Gate, applied to a different failure. That
            # one asks whether the *look* works before eighty clips are bought; this asks
            # whether the *opening* works before the full narration and the whole batch
            # are. Fifteen seconds is where a viewer decides, and a video whose first
            # fifteen seconds fail does not get watched however good minute four is.
            depends_on=("script", "voice_casting"),
            requires_approval=True,
            # The window this channel's gate actually cuts, at the rate this channel
            # actually writes. Stills are the node's own cost and are small beside it —
            # see `nodes/hook.py` on why this gate uses stills and not generated video.
            # Both terms come off `budget` rather than off the constants, because the node
            # cuts to `budget.hook_seconds` too: a hold priced on fifteen seconds for a
            # gate that cuts three is a hold nobody can reconcile against the bill.
            estimated_units=budget.hook_seconds * budget.words_per_second * 5.5,
        ),
        NodeSpec(
            key="voice",
            type="voice",
            title="Narrate script",
            # On the hook, so that rejecting the opening saves the whole voiceover. A
            # gate placed after this one would already have bought the narration for a
            # script that is about to be rewritten.
            depends_on=("script", "voice_casting", "hook"),
            estimated_units=words * 5.5,  # ≈ characters
        ),
        NodeSpec(
            key="sound",
            type="sound",
            title="Score the sound",
            # After the narration, because the bed's length and its level are both derived
            # from the voiceover that actually exists rather than from the script's
            # estimate of it. No `estimated_units`: the bed comes out of a flat
            # subscription rather than a per-unit price, so there is no quantity to
            # multiply and the node's base estimate is the whole reserve.
            depends_on=("script", "voice"),
        ),
        NodeSpec(
            key="broll_plan",
            type="broll_plan",
            title="Plan B-roll shots",
            depends_on=("script",),
        ),
        NodeSpec(
            key="sample",
            type="sample",
            title="Sample the look",
            # The gate this file's own preamble describes: the expensive stage sits
            # behind an approval on the cheap stage that determines it. One short clip
            # per distinct style-and-motion setup — two or three on a normal video —
            # costs about a fiftieth of the batch it authorises, and the failure it
            # catches is not one bad clip but the same defect in all eighty at once.
            #
            # On the hook as well, so nothing that spends starts before the opening is
            # approved. `broll_plan` deliberately still runs on the script alone —
            # planning is free, costs nothing to throw away, and having the shot list in
            # hand makes a rejected hook cheaper to act on rather than more expensive.
            depends_on=("broll_plan", "hook"),
            requires_approval=True,
            # Every setup the animation budget can produce, on the dearer of the two
            # models. The run's real setup count is not known until `broll_plan` has
            # produced its shots, and the old reserve answered that by holding one — which
            # was not a conservative reading of an unknown, it was the smallest one.
            estimated_credits=sample_credits,
        ),
        NodeSpec(
            key="shots",
            type="shots",
            title="Generate B-roll",
            # Both, deliberately. `broll_plan` because that is where the shot list comes
            # from, and `sample` because the approval is the whole reason this stage is
            # allowed to spend — an edge only on the plan would let the batch render
            # while the sample was still being looked at.
            depends_on=("broll_plan", "sample"),
            # Both, and only one of them is money. `estimated_credits` is what the ledger
            # holds. `estimated_units` is the plate budget — how many images this stage is
            # expected to buy — which is a different question from what they cost and is
            # the one `render.cutting` answers. Nothing but the estimate reads it today;
            # it is on the node so the count is visible next to the price rather than
            # derivable only by re-running `estimate_plates` by hand.
            estimated_units=shots,
            estimated_credits=shots_credits,
        ),
    ]

    # `sound` is a dependency of the render rather than a sibling of it. Both depend on
    # `voice`, so without this edge the two are in the same wave and the render can mux
    # the dry narration while the bed is still being fetched — a video with no music and a
    # node output claiming one, which is the one failure worse than having no music.
    render_deps = ["shots", "voice", "sound"]
    if use_avatar:
        nodes.append(
            NodeSpec(
                key="avatar",
                type="avatar",
                title="Render avatar pass",
                depends_on=("voice",),
                estimated_units=target_seconds,
            )
        )
        render_deps.append("avatar")

    nodes.append(
        NodeSpec(
            key="render",
            type="render",
            title="Render final video",
            depends_on=tuple(render_deps),
            params={"subtitles": burns_captions(render_spec)},
            max_attempts=2,
        )
    )
    nodes.append(
        NodeSpec(
            key="compliance",
            type="compliance",
            title="Compliance & policy check",
            depends_on=("render", "thumbnail"),
        )
    )
    if publish:
        nodes.append(
            NodeSpec(
                key="final_review",
                type="final_review",
                title="Preview & approve upload",
                depends_on=("compliance", "thumbnail"),
                requires_approval=True,
            )
        )
        nodes.append(
            NodeSpec(
                key="publish",
                type="publish",
                title="Publish to YouTube",
                depends_on=("final_review",),
                params={"privacy_status": "private"},
                max_attempts=2,
            )
        )

    spec = PipelineSpec(
        name="faceless_longform",
        title="Faceless long-form video",
        description="Narrated 8–12 minute video with generated B-roll and captions.",
        nodes=tuple(nodes),
    )
    spec.validate()
    return spec


def faceless_shorts(*, target_seconds: int = 45, publish: bool = True,
                    standard_model: str = "", hero_model: str = "",
                    sourcing: dict | None = None, render_spec: dict | None = None,
                    narrative: dict | None = None, **_) -> PipelineSpec:
    # The format this matters most for. A shorts creator reads breathlessly and opens in
    # three seconds, and both of those were being priced — and written — at a documentary's
    # pace. See `faceless_longform` for why it is a parameter rather than a lookup.
    budget = writing_budget(narrative)
    words = budget.words_for(target_seconds)
    # A short is mostly floor rather than rate: its beats are too brief to want a second
    # plate, so the reserve is one per scene and the runtime term barely contributes.
    shots = estimate_plates(target_seconds, sourcing=sourcing,
                            spec=spec_for({"render_spec": render_spec} if render_spec else None))
    sample_credits, shots_credits = animation_reserve(
        target_seconds, standard=standard_model, hero=hero_model, sourcing=sourcing,
        render_spec=render_spec)

    nodes: list[NodeSpec] = [
        NodeSpec(
            key="brief",
            type="brief",
            title="Create short brief",
            requires_approval=True,
            params={"target_duration_seconds": target_seconds, "format": "shorts"},
        ),
        NodeSpec(
            key="research",
            type="research",
            title="Research & verify sources",
            depends_on=("brief",),
            params={"max_queries": 3, "max_pages": 4},
        ),
        NodeSpec(
            key="script",
            type="script",
            title="Write hook-first script",
            depends_on=("brief", "research"),
            requires_approval=True,
            estimated_units=words,
            params={"target_duration_seconds": target_seconds, "format": "shorts"},
        ),
        NodeSpec(
            key="voice_casting", type="voice_casting", title="Cast the voice",
            depends_on=("script",), requires_approval=True, estimated_units=3,
            params={"shortlist": 3},
        ),
        NodeSpec(
            key="hook", type="hook", title="Cut and approve the opening",
            # A short is mostly hook, so this covers a larger share of it than on
            # long-form — which cuts both ways. It gates less spend, and it is a
            # correspondingly better prediction of the finished thing, because on a
            # sixty-second video the first fifteen seconds are a quarter of the video
            # rather than a thirtieth.
            depends_on=("script", "voice_casting"), requires_approval=True,
            estimated_units=budget.hook_seconds * budget.words_per_second * 5.5,
        ),
        NodeSpec(
            key="voice", type="voice", title="Narrate script",
            depends_on=("script", "voice_casting", "hook"),
            estimated_units=words * 5.5,
        ),
        NodeSpec(
            key="sound", type="sound", title="Score the sound",
            depends_on=("script", "voice"),
        ),
        NodeSpec(
            key="broll_plan", type="broll_plan", title="Plan vertical shots",
            depends_on=("script",),
        ),
        NodeSpec(
            key="sample", type="sample", title="Sample the look",
            # On a short the ratio is nearer one to eight than one to fifty, so the gate
            # buys less. It is still here, because what it catches does not scale with
            # the batch: a camera move that melts faces is wrong in all eight clips of a
            # short exactly as it is wrong in all eighty of a long-form, and a short that
            # has to be regenerated has lost the whole render rather than a fraction.
            depends_on=("broll_plan", "hook"), requires_approval=True,
            estimated_credits=sample_credits,
        ),
        NodeSpec(
            key="shots", type="shots", title="Generate vertical B-roll",
            depends_on=("broll_plan", "sample"), estimated_units=shots,
            estimated_credits=shots_credits,
        ),
        NodeSpec(
            key="thumbnail", type="thumbnail", title="Generate cover frame",
            depends_on=("script",), estimated_units=1,
            params={"concepts": 1},
        ),
        NodeSpec(
            key="render", type="render", title="Render vertical video",
            depends_on=("shots", "voice", "sound"),
            params={"subtitles": burns_captions(render_spec)},
            max_attempts=2,
        ),
        NodeSpec(
            key="compliance", type="compliance", title="Compliance & policy check",
            depends_on=("render",),
        ),
    ]
    if publish:
        nodes.append(
            NodeSpec(
                key="final_review", type="final_review", title="Preview & approve upload",
                depends_on=("compliance", "thumbnail"), requires_approval=True,
            )
        )
        nodes.append(
            NodeSpec(
                key="publish", type="publish", title="Publish Short",
                depends_on=("final_review",),
                params={"privacy_status": "private"}, max_attempts=2,
            )
        )

    spec = PipelineSpec(
        name="faceless_shorts",
        title="Faceless short",
        description="Vertical hook-first clip under 60 seconds.",
        nodes=tuple(nodes),
    )
    spec.validate()
    return spec


PIPELINES = {
    "faceless_longform": faceless_longform,
    "faceless_shorts": faceless_shorts,
}

PIPELINE_META = [
    {
        "name": "faceless_longform",
        "title": "Faceless long-form video",
        "description": "Narrated 8–12 minute video with generated B-roll and captions.",
        "default_seconds": 480,
    },
    {
        "name": "faceless_shorts",
        "title": "Faceless short",
        "description": "Vertical hook-first clip under 60 seconds.",
        "default_seconds": 45,
    },
]


def get_pipeline(name: str, **options) -> PipelineSpec:
    builder = PIPELINES.get(name)
    if builder is None:
        raise KeyError(f"unknown pipeline '{name}'; have {sorted(PIPELINES)}")
    return builder(**options)


# ------------------------------------------------------------------- stage names
#
# Every node in this file already carries a `title` written for a person — "Cast the
# voice", "Write full script" — and until now only the run page used them. Analytics
# listed its stages by `node_type`, so a page whose whole argument is that it prints
# honest numbers labelled its rows `voice_casting`, `final_review` and `broll_plan`, and
# said things like "Died at voice_casting ×1".
#
# Derived from the pipelines rather than written out again: a second table of stage
# names is one that drifts the first time a node is renamed, and the page would then be
# confidently wrong rather than ugly.

_STAGE_TITLES: dict[str, str] | None = None


def stage_titles() -> dict[str, str]:
    """Every shipped node type mapped to the words its own pipeline gives it.

    Built once. A type that appears in two pipelines under two titles keeps the first,
    which is the long-form one — they agree today, and if they ever stop, the page
    showing one of them is a smaller problem than the page showing a slug.
    """
    global _STAGE_TITLES
    if _STAGE_TITLES is None:
        found: dict[str, str] = {}
        for builder in PIPELINES.values():
            try:
                spec = builder()
            except Exception:                                      # pragma: no cover
                # A builder that needs arguments is not a reason for a page to lose its
                # labels; the types it would have contributed fall back to their slugs.
                continue
            for node in spec.nodes:
                if node.type and node.title:
                    found.setdefault(node.type, node.title)
        _STAGE_TITLES = found
    return _STAGE_TITLES


def stage_title(node_type) -> str:
    """One stage's name for a page, falling back to the slug opened out."""
    slug = str(node_type or "").strip()
    return stage_titles().get(slug) or slug.replace("_", " ")
