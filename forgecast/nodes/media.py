"""Media stages: thumbnail, narration, B-roll planning, shot generation, avatar.

This is where nearly all the money goes, so each stage degrades rather than dies:
a shot that fails to generate falls back to its still plate, and a still that fails
falls back to a captioned colour card. A run should not lose ten minutes of paid
render because one vendor request timed out.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..graph.engine import NodeContext, NodeResult, node_handler
from ..prompts import moves as camera_moves
from ..providers import ProviderError, VideoProvider
from ..providers.media import (
    HERO_TIER,
    STANDARD_TIER,
    model_for_tier,
    video_tier,
    video_usd,
)
from ..render import ffmpeg as ff
from ..render.cutting import plates_for, shot_estimate, spec_for
from ._common import ask_json, dimensions, request_payload

THUMBNAIL_INSTRUCTIONS = """Design thumbnail concepts for this video.

Return JSON: {"concepts": [{"prompt", "text_overlay", "rationale"}]}

  prompt        the image generation prompt. One clear focal subject, strong
                contrast, deliberate negative space for the overlay text. Never
                request readable text inside the image — text is composited later.
                Never depict a real identifiable person.
  text_overlay  2-5 words, upper case, that survive being shrunk to 168px wide.
  rationale     one sentence on why this earns the click honestly."""

MAX_MAP_MARKERS = 4


def known_places(value) -> list[str]:
    """Keep only the place names the gazetteer can actually resolve.

    Dropping the unknown ones, rather than failing the plan, is the right trade: a
    model asked for places will occasionally name a region, a country, or a port that
    does not exist, and losing one marker costs far less than losing the scene. The
    caller checks whether anything survived and falls back to a still if not.
    """
    from ..motion.geo import PLACES

    found: list[str] = []
    for item in value or []:
        key = " ".join(str(item).lower().split())
        if key in PLACES and key not in found:
            found.append(key)
    return found[:MAX_MAP_MARKERS]


BROLL_INSTRUCTIONS = """Plan the visual for every scene in the script.

Return JSON: {"shots": [{"scene_index", "prompt", "kind", "tier", "motion", "places"}]}

  scene_index  integer matching the script scene
  prompt       generation prompt: subject, setting, lens, lighting, composition.
               No text, no logos, no real people, no watermarks.
  kind         "image", "video", or "map".
               "video" only when motion carries meaning — at most one third of shots.
               "map" when the scene is about *where*: a route, a distance, a spread
               between places, a location the viewer needs situated. A map is the
               right answer far less often than it is tempting; one or two per video.
  tier         "hero" or "standard" — how much this beat is worth spending on.
               "hero" for the shots the video is judged on: the opening hook, the one
               reveal it is built around, the payoff, and the closing shot. Everything
               else is "standard", including shots that are merely good.
               At most a quarter of the scenes, and fewer is better. Name the tier and
               never a model: the app decides which endpoint each tier renders on, the
               hero one can cost six times the standard one, and a plan that marks half
               the scenes hero has simply chosen the expensive model for the whole video.
  motion       the camera move, chosen from the vocabulary appended below. Free text
               still works — it is matched onto the nearest known move — but picking a
               key is what gets the shot the fragment that has been found to work.
  places       required when kind is "map": 1-4 place names in the order the scene
               mentions them, e.g. ["Rotterdam", "Suez Canal", "Singapore"]. Use
               well-known cities, ports, straits or canals — not countries or
               regions, which have no single point to mark."""


# ----------------------------------------------------------------------- thumbnail


@node_handler("thumbnail")
async def thumbnail_node(ctx: NodeContext) -> NodeResult:
    script = ctx.output("script")
    width, height = dimensions(ctx)
    wanted = max(1, int(ctx.params.get("concepts") or 2))

    data, credits, provider = await ask_json(
        ctx,
        role="Design thumbnails that earn the click without lying about the video.",
        schema_name="thumbnail",
        payload=request_payload(
            ctx, title=script.get("title"), hook=ctx.output("brief").get("hook", "")
        ),
        instructions=THUMBNAIL_INSTRUCTIONS,
        max_tokens=1500,
    )

    concepts = [c for c in (data.get("concepts") or []) if isinstance(c, dict)][:wanted]
    if not concepts:
        raise ProviderError("no thumbnail concepts returned")

    image_provider = ctx.registry.image()
    rendered: list[dict] = []
    for index, concept in enumerate(concepts):
        prompt = str(concept.get("prompt") or "").strip() or f"thumbnail for {ctx.topic}"
        overlay = str(concept.get("text_overlay") or "")[:40]
        try:
            result = await image_provider.generate(
                prompt, out_path=ctx.path_for(f"thumb_{index + 1}_plate"),
                width=width, height=height,
            )
            credits += result.credits
            provider = result.provider or provider
            final = ctx.path_for(f"thumb_{index + 1}.png")
            await asyncio.to_thread(_composite_overlay, result.path, overlay, final)
        except ProviderError as exc:
            ctx.log(f"thumbnail {index + 1} generation failed: {exc}", level="warning")
            continue

        ctx.emit_artifact(
            "image", final, "image/png",
            concept_index=index, text_overlay=overlay, prompt=prompt[:300],
            selected=index == 0,
        )
        rendered.append({"index": index, "path": str(final), "text_overlay": overlay,
                         "prompt": prompt, "rationale": concept.get("rationale", "")})

    if not rendered:
        raise ProviderError("every thumbnail concept failed to render", retryable=True)

    ctx.log(f"{len(rendered)} thumbnail concept(s) rendered")
    return NodeResult(
        output={"concepts": rendered, "selected_index": 0}, credits=credits, provider=provider
    )


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ):
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _composite_overlay(plate: Path, text: str, out_path: Path) -> Path:
    """Text is composited, never generated — image models still cannot spell."""
    image = Image.open(plate).convert("RGB")
    if not text:
        image.save(out_path, "PNG")
        return out_path

    draw = ImageDraw.Draw(image)
    width, height = image.size
    size = max(28, int(height * 0.13))
    font = _font(size)

    # Shrink until it fits with a comfortable margin.
    for _ in range(14):
        box = draw.textbbox((0, 0), text, font=font, stroke_width=max(2, size // 12))
        if box[2] - box[0] <= width * 0.88:
            break
        size = int(size * 0.9)
        font = _font(size)

    box = draw.textbbox((0, 0), text, font=font, stroke_width=max(2, size // 12))
    x = (width - (box[2] - box[0])) / 2
    y = height - (box[3] - box[1]) - height * 0.11

    band = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(band).rectangle(
        [0, y - size * 0.28, width, y + (box[3] - box[1]) + size * 0.3], fill=(0, 0, 0, 130)
    )
    image = Image.alpha_composite(image.convert("RGBA"), band).convert("RGB")

    draw = ImageDraw.Draw(image)
    draw.text(
        (x, y), text, font=font, fill=(255, 255, 255),
        stroke_width=max(2, size // 12), stroke_fill=(0, 0, 0),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, "PNG")
    return out_path


# --------------------------------------------------------------------------- voice


def resolve_voice_id(
    casting: dict, *, channel_voice_id: str = "", param_voice_id: str = ""
) -> tuple[str, str]:
    """Decide which voice narrates, and say why. Returns (voice_id, note).

    The order matters and is not obvious. The operator's pick at the gate wins — they
    heard the auditions. But the gate can be *approved without a pick*: the CLI's
    auto-approve does exactly that, and a human can too. When that happens the
    shortlist's top entry is the right fallback, because casting measured it against
    the live account moments earlier.

    The channel default comes after both. Preferring it is how a run reached
    ElevenLabs with `voice_id="demo-voice"` — a placeholder left over from whenever
    the channel was created, which the API rejected as an invalid ID after the run had
    already paid for research, a script and a thumbnail.
    """
    chosen = str(casting.get("selected_voice_id") or "")
    if chosen:
        name = casting.get("selected") or chosen
        return chosen, f"narrating with the cast voice: {name}"

    candidates = casting.get("candidates") or []
    top = next((c for c in candidates if c.get("voice_id")), None)
    if top is not None:
        return (
            str(top["voice_id"]),
            "no voice was chosen at the gate — using the top audition: "
            f"{top.get('name') or top['voice_id']}",
        )

    fallback = channel_voice_id or param_voice_id
    if fallback:
        return fallback, f"no audition available — using the channel voice {fallback}"

    raise ProviderError(
        "no voice to narrate with: the casting gate selected none, the shortlist is "
        "empty, and the channel has no voice_id",
        provider="voice",
    )


@node_handler("voice")
async def voice_node(ctx: NodeContext) -> NodeResult:
    script = ctx.output("script")
    scenes = script.get("scenes") or []
    if not scenes:
        raise ProviderError("cannot narrate a script with no scenes")

    voice = ctx.registry.voice()
    casting = ctx.upstream_outputs.get("voice_casting") or {}
    voice_id, note = resolve_voice_id(
        casting,
        channel_voice_id=ctx.channel.voice_id,
        param_voice_id=str(ctx.params.get("voice_id") or ""),
    )
    ctx.log(note)
    speed = float(ctx.options.get("voice_speed") or 1.0)

    credits = 0
    provider = ""
    segments: list[dict] = []
    clips: list[Path] = []

    # Per-scene synthesis, not one long take: it lets the renderer cut the visual
    # to the exact length of its own narration instead of guessing.
    for scene in scenes:
        narration = scene["narration"]
        result = await voice.synthesize(
            narration,
            voice_id=voice_id,
            out_path=ctx.path_for(f"scene_{scene['index']:03d}"),
            speed=speed,
        )
        credits += result.credits
        provider = result.provider or provider
        clips.append(result.path)
        segments.append(
            {
                "scene_index": scene["index"],
                "path": str(result.path),
                "seconds": round(result.duration_seconds, 3),
                "characters": len(narration),
            }
        )
        ctx.emit_artifact(
            "audio", result.path, result.mime,
            scene_index=scene["index"], seconds=result.duration_seconds,
        )

    full = ctx.path_for("narration.m4a")
    await asyncio.to_thread(_concat_audio, clips, full)
    total = await asyncio.to_thread(ff.ffprobe_duration, full)
    ctx.emit_artifact("audio", full, "audio/mp4", role="narration", seconds=total)

    ctx.log(
        f"narrated {len(segments)} scenes, {total:.1f}s total",
        characters=sum(s["characters"] for s in segments),
    )
    return NodeResult(
        output={
            "narration_path": str(full),
            "total_seconds": round(total, 2),
            "segments": segments,
            "voice_id": voice_id,
        },
        credits=credits,
        provider=provider,
    )


def _concat_audio(clips: list[Path], out_path: Path) -> Path:
    if not clips:
        raise ProviderError("no audio to join")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    listing = out_path.with_suffix(".txt")
    listing.write_text(
        "\n".join(f"file '{clip.resolve().as_posix()}'" for clip in clips) + "\n",
        encoding="utf-8",
    )
    # Re-encode rather than stream-copy: sources may differ in codec between vendors.
    ff.run_ffmpeg(
        ["-f", "concat", "-safe", "0", "-i", str(listing), *ff.ACODEC, str(out_path)],
        label="concat_audio",
    )
    listing.unlink(missing_ok=True)
    return out_path


# ---------------------------------------------------------------------- broll plan

# What share of a script's beats the app will grant the hero tier, however many the
# planner asks for.
#
# A cap rather than an allocation, and it exists because of how a language model satisfies
# "mark the important shots": the cheapest way to be safe is to mark most of them, and a
# plan with half its scenes hero has not routed anything — it has chosen the expensive
# model for the whole video, at a settings page that promised a fifth of the cost. The
# roles that earn an upgrade are a fixed, short list — hook, reveal, payoff, close — so a
# quarter is generous at the twelve-scene ceiling `render.cutting` plans against.
HERO_SHARE = 0.25


def tier_models(ctx: NodeContext) -> tuple[str, str]:
    """The two slugs this run's tiers render on, as (standard, hero).

    The standard one is read off the registry rather than off the channel because that is
    where a per-run override has already landed: the engine folds `provider_models` and
    the channel's standing choice together before a node sees either, and re-reading the
    channel here would quietly ignore "render this one on the cheap model".

    The hero one is read off the channel, which is the asymmetry it looks like. There is
    no per-run hero override today and this is not the file to invent one — a second
    precedence chain that only one caller uses is how the two settings come to disagree
    about which run they applied to.
    """
    standard = str(ctx.registry.models.get("video", "") or ctx.channel.video_model or "")
    return standard, str(ctx.channel.video_model_hero or "")


@node_handler("broll_plan")
async def broll_plan_node(ctx: NodeContext) -> NodeResult:
    script = ctx.output("script")
    scenes = script.get("scenes") or []
    payload = request_payload(
        ctx,
        scenes=[
            {"index": s["index"], "narration": s["narration"][:300],
             "visual_prompt": s.get("visual_prompt", ""), "seconds": s["seconds"]}
            for s in scenes
        ],
    )
    data, credits, provider = await ask_json(
        ctx,
        role="Turn the script into a shot list a generation model can execute.",
        schema_name="broll_plan",
        payload=payload,
        # The camera vocabulary is appended rather than written into the constant, so
        # a move added to the catalogue reaches the planner without anyone remembering
        # to update a second copy of the list.
        instructions=(f"{BROLL_INSTRUCTIONS}\n\nCAMERA MOVES\n"
                      f"{camera_moves.planner_vocabulary()}"),
        max_tokens=8192,
    )

    by_index = {}
    for shot in data.get("shots") or []:
        if not isinstance(shot, dict):
            continue
        try:
            index = int(shot.get("scene_index"))
        except (TypeError, ValueError):
            continue
        by_index[index] = shot

    # How fast this channel cuts. The rate decides how many plates a scene has to buy,
    # so it is resolved here — where the spend is planned — and again at render time from
    # the measured voiceover, which is the only place the shot *lengths* can be right.
    spec = spec_for(ctx.channel.style_profile)

    standard_model, hero_model = tier_models(ctx)

    # Every scene must end up with at least one plate, planned or inferred.
    shots: list[dict] = []
    video_budget = max(1, len(scenes) // 3)
    hero_budget = max(1, round(len(scenes) * HERO_SHARE))
    videos = 0
    heroes = 0
    planned_shots = 0
    animation_usd = 0.0
    for position, scene in enumerate(scenes):
        planned = by_index.get(scene["index"], {})
        kind = str(planned.get("kind") or scene.get("visual_kind") or "image")

        places = known_places(planned.get("places"))
        if kind == "map" and not places:
            # A map with nothing to mark is an empty map. Fall back rather than
            # rendering an establishing shot of the whole planet with no point to it.
            kind = "image"
        if kind == "video" and videos >= video_budget:
            kind = "image"  # protect the budget from an over-eager plan
        if kind == "video":
            videos += 1
        kind = kind if kind in {"video", "map"} else "image"

        seconds = float(scene["seconds"])
        shot_count = shot_estimate(seconds, spec)
        planned_shots += shot_count
        # An animated clip and a map are bought once and sliced; only a still is cheap
        # enough that a second one is worth buying to break up a long beat.
        plates = plates_for(seconds, spec, reusable=kind == "image")

        # The opening beat is hero whether or not the planner marked it. Position settles
        # that one on its own: it is the shot retention is won or lost on, and it is the
        # only shot in the video every viewer sees.
        tier = HERO_TIER if position == 0 else video_tier(planned.get("tier"))
        model = ""
        if kind == "video":
            # The budget is spent here and only here, because a tier is only money where
            # it is a different endpoint: a still marked hero costs exactly what a still
            # costs, so charging it against the cap would deny the upgrade to an animated
            # beat that would actually have used it.
            if tier == HERO_TIER and heroes >= hero_budget:
                tier = STANDARD_TIER
            if tier == HERO_TIER:
                heroes += 1
            model = model_for_tier(tier, standard=standard_model, hero=hero_model)
            animation_usd += video_usd(model, seconds)

        prompt = str(planned.get("prompt") or scene.get("visual_prompt") or "").strip() \
            or f"cinematic b-roll: {scene['narration'][:120]}"
        for plate_index in range(plates):
            shots.append(
                {
                    "scene_index": scene["index"],
                    "plate_index": plate_index,
                    "plates": plates,
                    "planned_shots": shot_count,
                    # Later plates re-enter the same scene, so they need a prompt that
                    # differs enough to be worth the money. Asking the model for two
                    # prompts per scene would double the planning tokens for a variation
                    # a suffix already gets: the same subject, seen another way.
                    "prompt": prompt if plate_index == 0
                    else f"{prompt}. Alternative angle {plate_index + 1} on the same subject.",
                    "kind": kind,
                    # What this beat is worth spending on, and the endpoint that follows
                    # from it. The slug is written down rather than re-derived downstream
                    # so the shot the Sample Gate approved and the shot the batch renders
                    # cannot be on two different models — and it is empty on a still,
                    # because a still is not generated on a video endpoint and carrying a
                    # slug there would read as though it had been.
                    "tier": tier,
                    "model": model,
                    "motion": str(planned.get("motion") or "slow push in"),
                    "places": places,
                    "seconds": seconds,
                }
            )

    path = ctx.path_for("shot_list.json")
    path.write_text(json.dumps({"shots": shots}, indent=2, ensure_ascii=False), encoding="utf-8")
    ctx.emit_artifact("json", path, "application/json", shots=len(shots))
    ctx.log(
        f"planned {planned_shots} visual shots across {len(scenes)} scenes from "
        f"{len(shots)} plates ({videos} animated), cutting every "
        f"{spec.target_shot_seconds:.1f}s"
    )

    hero_slug = model_for_tier(HERO_TIER, standard=standard_model, hero=hero_model)
    batch_slug = model_for_tier(STANDARD_TIER, standard=standard_model, hero=hero_model)
    if videos:
        # The plan is the stage that decides this spend, so it is the stage that has to
        # say what it decided. Reported per model rather than as one figure at one rate,
        # because a blended plan quoted at either model's rate is wrong in whichever
        # direction that model sits — and the low direction is a reserve that runs out
        # in the middle of a batch.
        ctx.log(
            f"{heroes} hero shot(s) on {hero_slug} and {videos - heroes} on {batch_slug}"
            f" — about ${animation_usd:.2f} of animation",
            hero_model=hero_slug, standard_model=batch_slug,
            video_usd=round(animation_usd, 2),
        )

    return NodeResult(
        output={
            "shots": shots,
            "video_shots": videos,
            "hero_shots": heroes,
            "plates": len(shots),
            "planned_shots": planned_shots,
            "target_shot_seconds": round(spec.target_shot_seconds, 3),
            # What the animated shots in this plan cost, each priced on the model it will
            # actually run on and on the duration that endpoint will actually bill. It is
            # here rather than in `credits.py` because that table holds one figure per node
            # type and this run has two rates in it; see the note beside `PER_UNIT_COSTS`
            # for the reserve this number is the honest version of.
            "video_usd": round(animation_usd, 2),
            "video_models": {"hero": hero_slug, "standard": batch_slug},
        },
        credits=credits,
        provider=provider,
    )


# --------------------------------------------------------------------------- shots


def _render_map(ctx, shot: dict, index: int, seconds: float,
                width: int, height: int) -> Path:
    """Draw a map scene locally. Blocking, so callers run it off the event loop."""
    from ..motion.worldmap import MAP_LIBRARY, render_clip, spec_from

    style = str(
        (ctx.channel.style_profile or {}).get("map_style")
        or ctx.options.get("map_style")
        or "documentary_dark"
    )
    if style not in MAP_LIBRARY:
        ctx.log(f"unknown map style {style!r}; using documentary_dark", level="warning")
        style = "documentary_dark"

    spec = spec_from(
        [name.title() for name in shot["places"]],
        seconds=max(2.0, seconds), width=width, height=height, style=style,
    )
    out = ctx.path_for(f"shot_{index:03d}_map.mp4")
    ctx.log(f"scene {index}: map of {', '.join(shot['places'])} ({style})")
    return render_clip(spec, out)


@node_handler("shots")
async def shots_node(ctx: NodeContext) -> NodeResult:
    plan = ctx.output("broll_plan")
    shots = plan.get("shots") or []
    if not shots:
        raise ProviderError("shot list is empty")

    width, height = dimensions(ctx)
    image_provider = ctx.registry.image()

    # One provider per model the plan routed to, rather than one for the run. The plan
    # sends its hero beats to one endpoint and the rest to another, and a single provider
    # would render every shot on whichever slug happened to resolve — at that model's
    # price, with nothing on the clip to say the tier had been ignored.
    #
    # Resolved before the loop so a missing video vendor is one warning rather than
    # eighty. The registry caches on vendor *and* model, so this is one adapter per
    # distinct model and a cache hit for every shot after the first.
    video_providers: dict[str, VideoProvider] = {}
    for slug in sorted({str(shot.get("model") or "")
                        for shot in shots if shot["kind"] == "video"}):
        try:
            video_providers[slug] = ctx.registry.video(slug)
        except ProviderError as exc:
            # No video vendor configured. The loop below already falls back to the
            # still for any shot whose animation fails, so resolving eagerly and
            # letting this propagate would fail a run that could have finished —
            # and stills plus a Ken Burns push is a perfectly good B-roll bed.
            ctx.log(
                f"no video provider for {slug or 'the run default model'}, so those "
                f"shots render as stills: {exc}",
                level="warning",
            )

    credits = 0
    provider = ""
    produced: list[dict] = []
    degraded = 0
    # What the animation actually came to, per model. The plan quoted this before the
    # gate; this is the same arithmetic against the shots that survived, so a run whose
    # animations mostly failed over to stills does not report the estimate as a cost.
    animation_usd = 0.0
    clips_by_model: dict[str, int] = {}

    for shot in shots:
        index = int(shot["scene_index"])
        # A scene can own several plates now, so the slug — and therefore every file this
        # loop writes — has to carry both numbers. Keyed on the scene alone, plate 2 would
        # overwrite plate 1 on disk and the render would cut between one image and itself.
        plate_index = int(shot.get("plate_index") or 0)
        slug = f"shot_{index:03d}" + (f"_{plate_index}" if plate_index else "")
        prompt = shot["prompt"]
        seconds = float(shot.get("seconds") or 5.0)
        plate: Path | None = None

        # Always make the still first: it is the cheap fallback and the
        # conditioning frame that image-to-video models need.
        try:
            still = await image_provider.generate(
                prompt, out_path=ctx.path_for(f"{slug}_plate"),
                width=width, height=height,
            )
            credits += still.credits
            provider = still.provider or provider
            plate = still.path
            relevance = still.meta.get("relevance")
            if relevance == "weak":
                # Stock search always returns something; when the query had to be
                # gutted to find it, the picture often does not depict the subject.
                degraded += 1
                ctx.log(
                    f"scene {index}: weak stock match "
                    f"({still.meta.get('title', '?')!r}) — may not depict the subject",
                    level="warning",
                )
            ctx.emit_artifact(
                "image", plate, still.mime, scene_index=index, plate_index=plate_index,
                role="plate", prompt=prompt[:300], relevance=relevance,
                licence=still.meta.get("licence"),
                attribution=still.meta.get("attribution"),
            )
        except ProviderError as exc:
            ctx.log(f"shot {index} still failed: {exc}", level="warning")

        final_path = plate
        kind = "image"

        if shot["kind"] == "map" and shot.get("places"):
            # Rendered here rather than bought from a provider: the map is drawn from
            # data that ships with the package, so a map scene costs nothing and works
            # with no keys configured at all.
            try:
                map_path = await asyncio.to_thread(
                    _render_map, ctx, shot, index, seconds, width, height
                )
                final_path = map_path
                kind = "map"
                ctx.emit_artifact(
                    "video", map_path, "video/mp4", scene_index=index,
                    plate_index=plate_index, role="map", seconds=seconds,
                    places=shot["places"],
                )
                produced.append({"scene_index": index, "plate_index": plate_index,
                                 "path": str(final_path), "kind": kind,
                                 "seconds": seconds})
                continue
            except Exception as exc:
                degraded += 1
                ctx.log(f"shot {index} map failed, falling back to the still: {exc}",
                        level="warning")

        model = str(shot.get("model") or "")
        video_provider = video_providers.get(model) if shot["kind"] == "video" else None
        if video_provider is not None:
            try:
                # The vocabulary's fragment, not the planner's words. `motion` used to
                # be appended verbatim, so "dramatic sweeping movement" reached the
                # model exactly like that and it did whatever it liked. `fragment_for`
                # matches it onto a known move and contributes the phrasing that
                # actually produces one — and downgrades a move the shot is too short
                # to contain, which renders as a jump rather than as a slower version
                # of itself.
                move, camera = camera_moves.fragment_for(
                    shot.get("motion", ""), seconds=seconds)
                clip = await video_provider.generate_clip(
                    f"{prompt}. {camera}.",
                    out_path=ctx.path_for(f"{slug}_clip"),
                    seconds=seconds,
                    width=width,
                    height=height,
                    image_path=plate,
                )
                credits += clip.credits
                provider = clip.provider or provider
                final_path = clip.path
                kind = "video"
                animation_usd += video_usd(model, seconds)
                clips_by_model[model or "(run default)"] = (
                    clips_by_model.get(model or "(run default)", 0) + 1)
                ctx.emit_artifact(
                    "video", clip.path, clip.mime, scene_index=index,
                    plate_index=plate_index, role="shot", prompt=prompt[:300],
                    seconds=clip.duration_seconds,
                    # Which endpoint this clip came off, and the tier that chose it. On
                    # the artifact rather than only in the log because this is the row an
                    # audit reads back: two clips in one video can be from two models now,
                    # and a charge nobody can attribute to a model cannot be checked
                    # against the plan that authorised it.
                    model=model, tier=str(shot.get("tier") or ""),
                    # The move that actually ran, which is not always the one asked
                    # for: a shot too short to contain its move is downgraded, and
                    # without this the artifact records a camera the video does not
                    # have. It is also what a later pass would compare a reference
                    # against.
                    camera=move.key,
                )
            except ProviderError as exc:
                degraded += 1
                ctx.log(
                    f"shot {index} animation failed, falling back to the still: {exc}",
                    level="warning",
                )

        if final_path is None:
            # Nothing usable — the renderer will draw a captioned card here.
            degraded += 1
            produced.append({"scene_index": index, "plate_index": plate_index,
                             "path": None, "kind": "missing"})
            continue

        produced.append({"scene_index": index, "plate_index": plate_index,
                         "path": str(final_path), "kind": kind, "seconds": seconds})

    usable = [s for s in produced if s["path"]]
    if not usable:
        raise ProviderError("no shot produced a usable visual", retryable=True)

    scenes_covered = len({s["scene_index"] for s in usable})
    ctx.log(
        f"generated {len(usable)}/{len(shots)} plates across {scenes_covered} scenes"
        + (f", {degraded} degraded" if degraded else "")
    )
    if clips_by_model:
        ctx.log(
            "animated " + ", ".join(f"{count} on {name}"
                                    for name, count in sorted(clips_by_model.items()))
            + f" — about ${animation_usd:.2f}",
            video_usd=round(animation_usd, 2), clips_by_model=clips_by_model,
        )
    return NodeResult(
        output={"shots": produced, "degraded": degraded, "plates": len(usable),
                # The same arithmetic the plan quoted, against the clips that actually
                # rendered. Reported here because `credits.py` prices this node at one
                # blended per-clip figure for one model, and a run that routed across two
                # has no single rate that figure could be — see the report in the node
                # output rather than trusting the reserve to describe the spend.
                "video_usd": round(animation_usd, 2),
                "clips_by_model": clips_by_model},
        credits=credits,
        provider=provider,
    )


# -------------------------------------------------------------------------- avatar


@node_handler("avatar")
async def avatar_node(ctx: NodeContext) -> NodeResult:
    voice_output = ctx.output("voice")
    narration = Path(voice_output["narration_path"])
    if not narration.exists():
        raise ProviderError(f"narration missing at {narration}")

    avatar_id = ctx.channel.avatar_id or str(ctx.params.get("avatar_id") or "")
    if not avatar_id:
        ctx.log("no avatar configured on the channel — skipping the talking-head pass")
        return NodeResult(output={"skipped": True})

    width, height = dimensions(ctx)
    provider = ctx.registry.avatar()
    result = await provider.generate(
        audio_path=narration,
        avatar_id=avatar_id,
        out_path=ctx.path_for("avatar"),
        width=width,
        height=height,
    )
    ctx.emit_artifact(
        "video", result.path, result.mime, role="avatar", seconds=result.duration_seconds
    )
    ctx.log(f"avatar pass rendered: {result.duration_seconds:.1f}s")
    return NodeResult(
        output={"avatar_path": str(result.path), "seconds": result.duration_seconds},
        credits=result.credits,
        provider=result.provider,
    )
