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
from ..providers import ProviderError
from ..render import ffmpeg as ff
from ._common import ask_json, dimensions, request_payload

THUMBNAIL_INSTRUCTIONS = """Design thumbnail concepts for this video.

Return JSON: {"concepts": [{"prompt", "text_overlay", "rationale"}]}

  prompt        the image generation prompt. One clear focal subject, strong
                contrast, deliberate negative space for the overlay text. Never
                request readable text inside the image — text is composited later.
                Never depict a real identifiable person.
  text_overlay  2-5 words, upper case, that survive being shrunk to 168px wide.
  rationale     one sentence on why this earns the click honestly."""

BROLL_INSTRUCTIONS = """Plan the visual for every scene in the script.

Return JSON: {"shots": [{"scene_index", "prompt", "kind", "motion"}]}

  scene_index  integer matching the script scene
  prompt       generation prompt: subject, setting, lens, lighting, composition.
               No text, no logos, no real people, no watermarks.
  kind         "video" only when motion carries meaning, else "image".
               Budget at most one third of shots as "video".
  motion       intended camera move, e.g. "slow push in", "static", "pan left"."""


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


@node_handler("voice")
async def voice_node(ctx: NodeContext) -> NodeResult:
    script = ctx.output("script")
    scenes = script.get("scenes") or []
    if not scenes:
        raise ProviderError("cannot narrate a script with no scenes")

    voice = ctx.registry.voice()
    # Casting wins over the channel default: the operator picked it at the gate for
    # this run, having actually heard the auditions.
    casting = ctx.upstream_outputs.get("voice_casting") or {}
    voice_id = (
        str(casting.get("selected_voice_id") or "")
        or ctx.channel.voice_id
        or str(ctx.params.get("voice_id") or "")
    )
    if casting.get("selected"):
        ctx.log(f"narrating with the cast voice: {casting['selected']}")
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
        instructions=BROLL_INSTRUCTIONS,
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

    # Every scene must end up with a shot, planned or inferred.
    shots: list[dict] = []
    video_budget = max(1, len(scenes) // 3)
    videos = 0
    for scene in scenes:
        planned = by_index.get(scene["index"], {})
        kind = str(planned.get("kind") or scene.get("visual_kind") or "image")
        if kind == "video" and videos >= video_budget:
            kind = "image"  # protect the budget from an over-eager plan
        if kind == "video":
            videos += 1
        shots.append(
            {
                "scene_index": scene["index"],
                "prompt": str(planned.get("prompt") or scene.get("visual_prompt") or "").strip()
                or f"cinematic b-roll: {scene['narration'][:120]}",
                "kind": "video" if kind == "video" else "image",
                "motion": str(planned.get("motion") or "slow push in"),
                "seconds": scene["seconds"],
            }
        )

    path = ctx.path_for("shot_list.json")
    path.write_text(json.dumps({"shots": shots}, indent=2, ensure_ascii=False), encoding="utf-8")
    ctx.emit_artifact("json", path, "application/json", shots=len(shots))
    ctx.log(f"planned {len(shots)} shots ({videos} animated)")

    return NodeResult(
        output={"shots": shots, "video_shots": videos}, credits=credits, provider=provider
    )


# --------------------------------------------------------------------------- shots


@node_handler("shots")
async def shots_node(ctx: NodeContext) -> NodeResult:
    plan = ctx.output("broll_plan")
    shots = plan.get("shots") or []
    if not shots:
        raise ProviderError("shot list is empty")

    width, height = dimensions(ctx)
    image_provider = ctx.registry.image()

    video_provider = None
    if any(s["kind"] == "video" for s in shots):
        try:
            video_provider = ctx.registry.video()
        except ProviderError as exc:
            # No video vendor configured. The loop below already falls back to the
            # still for any shot whose animation fails, so resolving eagerly and
            # letting this propagate would fail a run that could have finished —
            # and stills plus a Ken Burns push is a perfectly good B-roll bed.
            ctx.log(
                f"no video provider available, rendering every shot as a still: {exc}",
                level="warning",
            )

    credits = 0
    provider = ""
    produced: list[dict] = []
    degraded = 0

    for shot in shots:
        index = int(shot["scene_index"])
        prompt = shot["prompt"]
        seconds = float(shot.get("seconds") or 5.0)
        plate: Path | None = None

        # Always make the still first: it is the cheap fallback and the
        # conditioning frame that image-to-video models need.
        try:
            still = await image_provider.generate(
                prompt, out_path=ctx.path_for(f"shot_{index:03d}_plate"),
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
                "image", plate, still.mime, scene_index=index, role="plate",
                prompt=prompt[:300], relevance=relevance,
                licence=still.meta.get("licence"),
                attribution=still.meta.get("attribution"),
            )
        except ProviderError as exc:
            ctx.log(f"shot {index} still failed: {exc}", level="warning")

        final_path = plate
        kind = "image"
        if shot["kind"] == "video" and video_provider is not None:
            try:
                clip = await video_provider.generate_clip(
                    f"{prompt}. Camera: {shot.get('motion', 'slow push in')}.",
                    out_path=ctx.path_for(f"shot_{index:03d}_clip"),
                    seconds=seconds,
                    width=width,
                    height=height,
                    image_path=plate,
                )
                credits += clip.credits
                provider = clip.provider or provider
                final_path = clip.path
                kind = "video"
                ctx.emit_artifact(
                    "video", clip.path, clip.mime, scene_index=index, role="shot",
                    prompt=prompt[:300], seconds=clip.duration_seconds,
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
            produced.append({"scene_index": index, "path": None, "kind": "missing"})
            continue

        produced.append({"scene_index": index, "path": str(final_path), "kind": kind,
                         "seconds": seconds})

    usable = [s for s in produced if s["path"]]
    if not usable:
        raise ProviderError("no shot produced a usable visual", retryable=True)

    ctx.log(
        f"generated {len(usable)}/{len(shots)} shots"
        + (f", {degraded} degraded" if degraded else "")
    )
    return NodeResult(
        output={"shots": produced, "degraded": degraded}, credits=credits, provider=provider
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
