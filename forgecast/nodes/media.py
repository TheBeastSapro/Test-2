"""Media stages: thumbnail, narration, B-roll planning, shot generation, avatar.

This is where nearly all the money goes, so each stage degrades rather than dies:
a shot that fails to generate falls back to its still plate, and a still that fails
falls back to a captioned colour card. A run should not lose ten minutes of paid
render because one vendor request timed out.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .. import operator_lane
from ..config import get_settings
from ..edit import segment as segment_planner
from ..graph.engine import NodeContext, NodeResult, node_handler
from ..motion import paper
from ..prompts import cast
from ..prompts import moves as camera_moves
from ..providers import ProviderError, VideoProvider, footage
from ..providers.media import (
    HERO_TIER,
    STANDARD_TIER,
    model_for_tier,
    video_tier,
    video_usd,
)
from ..providers.stock import to_query
from ..render import ffmpeg as ff
from ..render.cutting import plates_for, shot_estimate, spec_for
from ..style import sourcing
from ._common import ask_json, dimensions, request_payload, tier_models

THUMBNAIL_INSTRUCTIONS = """Design thumbnail concepts for this video.

Return JSON: {"concepts": [{"prompt", "text_overlay", "rationale"}]}

  prompt        the image generation prompt. One clear focal subject, strong
                contrast, deliberate negative space for the overlay text. Never
                request readable text inside the image — text is composited later.
                Never depict a real identifiable person.
  text_overlay  2-5 words, upper case, that survive being shrunk to 168px wide.
  rationale     one sentence on why this earns the click honestly."""

MAX_MAP_MARKERS = 4

#: The one visual style that replaces generated video rather than costing less than it.
#: Set on a channel's `style_profile.visual_style`.
PAPER_COLLAGE = "paper_collage"


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
    casting: dict, *, channel_voice_id: str = "", param_voice_id: str = "",
    mock: bool = False,
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

    # Say which of the two it is. The message here read "the shortlist is empty" for
    # both cases, and the common one is the other: the built-in catalogue describes
    # voices without vendor IDs on purpose — it is matched against a connected
    # account's real voices — so with no vendor connected the shortlist is *full* and
    # every entry is unusable. Reporting that as empty sends whoever reads it looking
    # for a missing shortlist that is sitting right there, and says nothing about the
    # fix, which is to connect a vendor or set a channel voice.
    # In mock mode there is nothing to refuse on behalf of. The stand-in narrator
    # ignores the id it is handed and no call is made, so both messages below would be
    # describing a cost that does not exist — and refusing here stopped a first-time
    # operator at exactly the stage the app promises they can walk past, leaving
    # everything from `hook` to `publish` unreachable until they connected a vendor.
    # The note says which voice this is not, so nobody reads a finished mock run as
    # evidence that casting worked.
    if mock:
        return "mock-voice", ("no real voice is connected — narrating with the offline "
                              "stand-in, which is not any of the auditions")

    if candidates:
        raise ProviderError(
            f"no voice to narrate with: {len(candidates)} auditions were shortlisted "
            f"({', '.join(str(c.get('name') or '?') for c in candidates[:4])}) but none "
            "carries a vendor voice id — the built-in roster describes voices and does "
            "not own them. Connect ElevenLabs or MiniMax in Settings, or set the "
            "channel's voice, then run again.",
            provider="voice",
        )
    raise ProviderError(
        "no voice to narrate with: the casting gate selected none, no voice was "
        "shortlisted, and the channel has no voice_id",
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
        mock=ctx.registry.mode == "mock",
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


def _fetch_canon(ctx: NodeContext, shot: dict, slug: str) -> Path | None:
    """Download one wiki asset. `None` if anything stops it.

    Plain HTTP because that is what these are: a canonical file URL the MediaWiki API
    handed back, on a host that serves it openly. No acquisition machinery, no
    subprocess, nothing to fail at three in the morning except the network.

    The file is written under the run and never cached across runs. A run's assets have
    to be inspectable and re-checkable afterwards — the whole reason the licence is
    unresolved is that a human may have to look — and a shared cache would leave the
    picture that got published sitting in a directory no run owns.
    """
    import httpx

    from ..research.fandom import USER_AGENT

    url = str(shot.get("asset_url") or "")
    if not url:
        return None

    suffix = Path(url.split("?")[0]).suffix.lower()
    out = ctx.path_for(f"{slug}_canon{suffix if suffix in ('.png', '.jpg', '.jpeg', '.webp') else '.png'}")
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True,
                          headers={"User-Agent": USER_AGENT}) as client:
            response = client.get(url)
            response.raise_for_status()
            out.write_bytes(response.content)
    except Exception as exc:
        ctx.log(f"{slug}: could not fetch {shot.get('asset') or url}: {exc}",
                level="warning")
        return None

    # An HTML error page saved under a .png name is a file that exists, opens as
    # nothing, and fails much later inside ffmpeg with a message about the codec.
    try:
        with Image.open(out) as image:
            image.verify()
    except Exception:
        ctx.log(f"{slug}: {shot.get('asset') or url} did not arrive as an image",
                level="warning")
        out.unlink(missing_ok=True)
        return None
    return out


async def _canon_plate(ctx: NodeContext, shot: dict, cache: dict, image_provider,
                       width: int, height: int) -> Path | None:
    """The background one composite stands on, bought once per segment.

    Keyed on `plate_group` — the entity — because the reference reuses its plate across
    a creature's whole segment and generating one a shot would be paying twenty times
    for a location the format only has one of. `None` is a real answer: the caller
    renders the cut-out as it arrived and says so.

    Generation first and the page's own wide second, which is the measured order rather
    than a preference. A wiki gallery's wides are gameplay screenshots — standing a
    subject on one puts a hotbar along the bottom of the shot and a player avatar in the
    corner, which is somebody's recording rather than a background. It stays as the free
    fallback because a HUD behind the subject is a poor shot and no shot is a hole.
    """
    if not shot.get("composite"):
        return None

    group = str(shot.get("plate_group") or "")
    if group in cache:
        return cache[group]

    plate: Path | None = None
    prompt = str(shot.get("plate_prompt") or "")
    if prompt:
        try:
            made = await image_provider.generate(
                prompt, out_path=ctx.path_for(f"canon_plate_{_slugify(group)}"),
                width=width, height=height,
            )
            plate = made.path
            ctx.log(f"plate for {group or 'the canon segment'} generated once and reused "
                    f"across its shots")
        except ProviderError as exc:
            ctx.log(f"plate for {group or 'the canon segment'} could not be generated "
                    f"({exc}) — falling back to the page's own wide", level="warning")

    if plate is None and shot.get("plate_url"):
        plate = await asyncio.to_thread(
            _fetch_canon, ctx, {"asset_url": shot["plate_url"],
                                "asset": shot.get("plate_asset")},
            f"canon_plate_{_slugify(group)}")

    if plate is None:
        ctx.log(f"nothing to stand {group or 'the canon subject'} on — its shots render "
                f"as the cut-outs they arrived as", level="warning")

    cache[group] = plate
    return plate


def _slugify(text: str) -> str:
    """A filename fragment from an entity title. Not reversible and not meant to be."""
    kept = "".join(char if char.isalnum() else "_" for char in str(text).lower())
    return kept.strip("_")[:48] or "plate"


def _stand_subject(ctx: NodeContext, shot: dict, slug: str, subject: Path,
                   plate_path: Path | None, width: int, height: int) -> Path:
    """Put a cut-out onto a plate. Returns the composite, or the subject unchanged.

    This is the shot model the format is actually made of and the reason
    `layers/shot.py` exists: the creature is the franchise's own artwork, the
    environment is a generated plate, and the shot is the first standing on the second.
    Without this step a canon shot renders as a 2250x2250 transparent PNG — which ffmpeg
    will happily letterbox onto black, producing a sticker floating in a void.

    Returns the subject untouched rather than raising when there is no plate or the
    composite fails. A cut-out on black is a poor shot and a missing shot is a hole; the
    poor shot is recoverable and says so in the log.
    """
    from ..layers.shot import place

    if not shot.get("composite") or plate_path is None:
        # Said out loud rather than performed quietly. A shot marked for motion that
        # cannot take it is how the ration came to plan two clips and render none for
        # every run: the planner marked, this returned the still, and neither end
        # reported a disagreement. The planner no longer marks these — this is the
        # backstop, and a backstop that degrades in silence is the defect it is
        # supposed to catch.
        if shot.get("animate"):
            ctx.log(f"{slug}: planned to move but there is "
                    + ("no cut-out in it" if not shot.get("composite")
                       else "no plate to move it against")
                    + " — holding it as a still", level="warning")
        return subject

    # The shots the planner rationed motion to. `animate` has been on the shot list
    # since the planner was written and nothing read it, so the ration decided nothing
    # — every canon shot was a still whatever the plan said.
    #
    # The subject moves and the plate does not, which is the reference's own
    # construction and the thing a whole-frame push cannot fake: push the frame and it
    # reads as a camera move, move the cut-out alone and it reads as the creature. The
    # phase is per shot so two cuts of one creature never start the same move together.
    if shot.get("animate"):
        from ..render.layered import drift_clip

        seconds = float(shot.get("seconds") or 3.0)
        try:
            return drift_clip(
                subject, plate_path, ctx.path_for(f"{slug}_drift.mp4"),
                seconds=seconds, width=width, height=height,
                phase=float(int(shot.get("plate_index") or 0)) * 1.7,
            )
        except Exception as exc:
            # Down to the still, never out. A shot that would have moved and is instead
            # held is a slightly duller video; a missing shot is a hole.
            ctx.log(f"{slug}: {shot.get('asset')} could not be animated ({exc}) — "
                    f"holding it as a still", level="warning")

    out = ctx.path_for(f"{slug}_composite.png")
    try:
        place(subject, plate_path, out, width=width, height=height)
    except Exception as exc:
        ctx.log(f"{slug}: could not stand {shot.get('asset')} on its plate: {exc}",
                level="warning")
        return subject
    return out


def _fetch_footage(ctx: NodeContext, shot: dict, slug: str, seconds: float):
    """Get the chosen clip onto disk, muted and trimmed. `None` if anything stops it.

    The licence is re-established from the clip rather than read from the shot list. The
    list is a JSON artifact an operator can open and edit, so trusting a stored
    `commercially_safe: true` would be this app vouching for a licence it never checked —
    the same quiet claim `FootageClip.commercially_safe` exists to refuse, one file
    removed.

    Acquisition goes through `vision.acquire`, which already handles local paths, direct
    media URLs and yt-dlp. A fetcher here would be a fourth copy of the same subprocess
    call with its own timeout and its own way of failing at three in the morning.

    Audio comes off at ingest, never at render. A clip that arrives muted cannot be
    un-muted by a later stage written by somebody who does not know where the file came
    from — and the sound design owns this video's audio.
    """
    from ..vision.acquire import AcquireError, acquire

    raw = shot.get("clip") or {}
    clip = footage.FootageClip(
        url=str(raw.get("url") or ""), title=str(raw.get("title") or ""),
        creator=str(raw.get("creator") or ""), licence=str(raw.get("licence") or ""),
        source=str(raw.get("source") or ""),
        landing_url=str(raw.get("landing_url") or ""),
        licence_url=str(raw.get("licence_url") or ""),
        attribution=str(raw.get("attribution") or ""),
        seconds=float(raw.get("seconds") or 0.0), width=int(raw.get("width") or 0),
        operator_directed=bool(raw.get("operator_directed")),
    )
    if not clip.commercially_safe or not clip.url:
        ctx.log(f"{slug}: the recorded clip is not usable in a monetised edit "
                f"({clip.licence or 'no licence'}) — generating instead", level="warning")
        return None

    workdir = ctx.path_for(f"{slug}_footage_src")
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        got = acquire(clip.fetch_reference(), workdir, max_seconds=seconds * 3)
    except (AcquireError, Exception) as exc:  # acquire raises its own and yt-dlp's
        ctx.log(f"{slug}: could not fetch {clip.source} footage: {exc}", level="warning")
        return None

    out = ctx.path_for(f"{slug}_footage.mp4")
    try:
        footage.strip_audio(got.path, out, seconds=seconds)
    except Exception as exc:
        ctx.log(f"{slug}: could not mute and trim the clip: {exc}", level="warning")
        return None
    if not out.exists() or out.stat().st_size == 0:
        return None
    return out, clip


#: How many footage searches run at once. Four sources per beat behind one connection
#: pool; more parallelism here buys latency the operator waits on for free and risks a
#: vendor's rate limit, which costs the lane for the whole run rather than one beat.
_FOOTAGE_CONCURRENCY = 4


async def _offer_free_footage(ctx: NodeContext, beats: list[dict]) -> None:
    """Replace generated clips with licensed footage wherever the free lane can serve.

    Only beats already planned to MOVE are offered. A still is never converted into
    footage, and that single restriction is what makes the change safe: a moving beat
    buys one plate whether the pixels come from Pexels or from Kling, so the free lane
    substitutes strictly inside a class the profile has already counted, and no
    measurement function has to know it exists.

    It runs at plan time, not at fetch time, and the reason is `nodes/sample`: the Sample
    Gate reads the plan, spends real money on one clip per distinct setup, and filters on
    `kind == "video"`. Choosing footage later would buy samples for setups that never
    render, and the plan's own `video_usd` would be a quote for work nobody does.

    Nothing here may fail the node. A free lane that can break a paid run is worse than
    no free lane, so every failure — a dead source, a timeout, no key, an exception —
    leaves the beat exactly as the planner wrote it.
    """
    movers = [beat for beat in beats if beat["kind"] == "video"]
    if not movers:
        return

    # Mock never touches the network and never spends money. The free lane spends
    # nothing but does reach the network, so it is skipped — which is also what keeps
    # every existing test harness offline.
    if getattr(ctx.registry, "mode", "") == "mock":
        return

    settings = get_settings()
    pexels = str(getattr(settings, "pexels_api_key", "") or "")
    pixabay = str(getattr(settings, "pixabay_api_key", "") or "")

    width, _height = dimensions(ctx)
    gate = asyncio.Semaphore(_FOOTAGE_CONCURRENCY)

    async def look(beat: dict) -> None:
        query = to_query(beat["prompt"])
        async with gate:
            try:
                clips = await footage.find(query, pexels_key=pexels, pixabay_key=pixabay)
            except Exception as exc:
                beat["why"] = f"footage search failed: {exc}"
                return
        chosen, why = footage.best_for(
            clips, query=query, seconds=beat["seconds"], width=width)
        beat["why"] = why
        if chosen is None:
            return

        # Archive hands back a download directory and NASA a manifest of assets, so a
        # chosen clip from either is not yet something that can be fetched. Resolved
        # here — once, for the one clip that won — rather than during the search, where
        # it would be eight manifest fetches to answer a question about one.
        async with gate:
            try:
                resolved = await footage.resolve_media_url(chosen)
            except Exception:
                resolved = ""
        if not resolved:
            beat["why"] = (f"{chosen.source} matched but no downloadable file could be "
                           f"resolved from it")
            return
        chosen.url = resolved
        beat["kind"] = "footage"
        beat["clip"] = chosen

    try:
        await asyncio.gather(*(look(beat) for beat in movers))
    except Exception as exc:
        ctx.log(f"the free footage lane did not run: {exc}", level="warning")
        return

    served = [beat for beat in movers if beat["kind"] == "footage"]
    if served:
        ctx.log(f"{len(served)} of {len(movers)} moving beats served by licensed "
                f"footage — those cost nothing to generate")
    else:
        # Why not, once, rather than per beat: on a run where nothing matched this would
        # otherwise be a paragraph of near-identical lines.
        reasons = {beat["why"] for beat in movers if beat["why"]}
        ctx.log("no moving beat could be served free — "
                + ("; ".join(sorted(reasons))[:220] if reasons else "no reason recorded"))


# ------------------------------------------------------------------------- the canon
#
# When research fetched the entities off a wiki, the shot list for their scenes is
# written rather than generated. That is not a saving so much as a correctness rule:
# these audiences know what the creature looks like and correct the video when it is
# wrong, so a generated depiction of a named entity is an error the comments find.
#
# `edit/segment.py` has written the shot list all along and nothing called it, which is
# this codebase's own named defect — a module measured, tested and never read. This is
# the call site.


def _scenes_for(entity: dict, scenes: list[dict]) -> tuple[list[dict], str]:
    """The scenes this entity is the subject of, and a warning when the match was loose.

    Matched on the entity's title appearing in the narration, which for this format is
    the join that exists: the script writes a segment per creature and says its name.
    `asked_for` is checked too, because the operator's spelling is what the beat outline
    and therefore the narration used, while `title` is what the wiki redirected to.

    Whole words, and the name's own capitalisation first. Substring matching put the
    wrong creature's artwork on screen on the first wiki this was pointed at: Doors has
    entities called **Rush** and **Halt**, so "do not rush the last door" and "a halt in
    the music" both claimed a segment. A creature is a proper noun and a script writes
    it as one, so the capital is real evidence and not a formality.

    The case-insensitive pass is the fallback rather than the rule, and it says so —
    a script that lower-cases its names should still produce a video, and an operator
    should be able to see why a scene was claimed.
    """
    names = [name for name in (str(entity.get("title") or ""),
                               str(entity.get("asked_for") or "")) if name]
    if not names:
        return [], ""

    def matches(scene: dict, flags: int) -> bool:
        text = str(scene.get("narration") or "")
        return any(re.search(rf"\b{re.escape(name)}\b", text, flags) for name in names)

    exact = [scene for scene in scenes if matches(scene, 0)]
    if exact:
        return exact, ""

    loose = [scene for scene in scenes if matches(scene, re.IGNORECASE)]
    if not loose:
        return [], ""
    return loose, (f"matched on {len(loose)} scene(s) only by ignoring case — check "
                   f"the narration is about it and not using the word")


#: How much of the script's own visual direction goes into a plate prompt. The scene's
#: `visual_prompt` is a whole-frame instruction and this is only asking for the back
#: half of one, so it is a phrase of guidance rather than a paragraph of it.
PLATE_PROMPT_CHARS = 180

#: What every plate prompt ends with, and the reason it is a constant. The subject is
#: composited on top, so a plate with its own creature in it renders two — and this is
#: the failure mode a generation model falls into hardest, because the scene text it is
#: given is entirely about a creature.
PLATE_CONSTRAINT = (
    "Empty environment only. No creature, no figure, no person, no animal, no character "
    "of any kind. No text, no logo, no interface. Deep focus background plate, room for "
    "a subject to stand in the lower centre foreground."
)


def _plate_prompt(entity: dict, scenes: list[dict]) -> str:
    """What to generate as the background for one entity's segment.

    Built from the script's own visual direction for the scenes the entity covers,
    because that is where the environment was already described and it is the half of
    the frame the plate is. The entity's name goes in only as the *place* it is
    associated with, never as a subject to draw — see `PLATE_CONSTRAINT`.
    """
    direction = next((str(scene.get("visual_prompt") or "").strip()
                      for scene in scenes if str(scene.get("visual_prompt") or "").strip()),
                     "")
    setting = direction[:PLATE_PROMPT_CHARS] or (
        f"the environment {entity.get('title', 'this creature')} is found in")
    return f"Background plate: {setting}. {PLATE_CONSTRAINT}"


def _canon_shots(ctx, scenes: list[dict]) -> tuple[dict, dict]:
    """Written shot lists for every scene an entity covers.

    Returns the shots keyed by scene index, and a report worth logging. A scene no
    entity claims is absent from the mapping and falls through to the generated path
    below — a partly-canon video is normal, and forcing the rest through this lane
    would mean inventing assets for it.
    """
    research = ctx.upstream_outputs.get("research") or {}
    found = (research.get("canon") or {}).get("entities") or []
    entities = [entity for entity in found if entity.get("usable")]
    if not entities or not scenes:
        return {}, {}

    by_scene: dict[int, list[dict]] = {}
    planned_segments: list[dict] = []
    warnings: list[str] = []

    for entity in entities:
        owned, loose = _scenes_for(entity, scenes)
        if loose:
            warnings.append(f"{entity['title']}: {loose}")
        if not owned:
            warnings.append(
                f"{entity['title']}: fetched but no scene names it, so its artwork is "
                f"not on the timeline")
            continue

        # One plan across the entity's whole run of scenes rather than one per scene.
        # A segment is the unit the reference cuts to — beats get a share of the
        # *segment*, and planning each scene alone would restart the story beat every
        # time the script broke a paragraph.
        span = sum(float(scene["seconds"]) for scene in owned)
        plan = segment_planner.plan(entity, seconds=span)
        planned_segments.append({"title": entity["title"],
                                 # The scene indexes, not just how many. This is the
                                 # only exact segment→time mapping the run ever has,
                                 # and it is what `final_review` writes the chapter
                                 # marks from: the audience of this format hand-writes
                                 # that index in the comments, and publishing it costs
                                 # nothing. Reconstructed later from narration it would
                                 # be a guess; recorded here it is the same join that
                                 # decided the shots.
                                 "scene_indexes": [int(scene["index"]) for scene in owned],
                                 "scenes": len(owned),
                                 "shots": plan.shot_count, "seconds": round(span, 1),
                                 "warnings": list(plan.warnings)})
        warnings += [f"{entity['title']}: {note}" for note in plan.warnings]

        gallery = {str(asset.get("name")): asset for asset in entity.get("gallery") or []}
        # Plates for the cut-outs. These assets arrive as transparent PNGs — the ones
        # this lane fetched off Doors are 2250x2250 RGBA with the creature in the middle
        # — so a composite shot needs a background to stand on.
        #
        # Generated, not fetched, which is the measured split and not a preference:
        # REFERENCE-MSIMPLIFIED records ~70% sourced creature art against ~10% generated
        # background plates, and the reason is visible the moment you render one. The
        # first version of this stood the cut-outs on the page's own wide images, and
        # those are gameplay screenshots — the composite came back with a hotbar along
        # the bottom and a player avatar in the corner. Chrome from somebody's recording
        # is not a background, it is evidence of one.
        #
        # A gallery wide stays as the free fallback for a run with no image provider: a
        # HUD behind the subject is a poor shot, and no shot at all is a hole.
        fallback_plates = [asset for asset in entity.get("gallery") or []
                           if not asset.get("portrait")]
        plate_at = 0
        # One plate per entity, reused across its composites. The reference reuses both
        # halves — the same creature image across every shot of that creature, only
        # scale and position changing — so a plate per shot would be paying for variety
        # the format does not have and the eye reads as a different location each cut.
        plate_prompt = _plate_prompt(entity, owned)
        # Each shot lands on whichever scene its start time falls in, so the shot list
        # keeps the (scene_index, plate_index) shape everything downstream already
        # reads. Boundaries are the scenes' own durations — the plan is laid over the
        # script's clock, not the other way round.
        bounds: list[tuple[float, dict]] = []
        clock = 0.0
        for scene in owned:
            clock += float(scene["seconds"])
            bounds.append((clock, scene))

        at = 0.0
        for shot in plan.shots:
            scene = next((scene for edge, scene in bounds if at < edge), owned[-1])
            asset = gallery.get(shot.asset) or {}
            index = int(scene["index"])
            plates = by_scene.setdefault(index, [])
            by_scene[index] = plates

            plate: dict = {}
            # A plate only where the shot is a cut-out that needs one, and never the
            # subject's own file: a wide standing behind itself is one picture at two
            # scales, which reads as a zoom nobody asked for.
            if shot.composite and fallback_plates:
                plate = fallback_plates[plate_at % len(fallback_plates)]
                plate_at += 1

            plates.append({
                "scene_index": index,
                "plate_index": len(plates),
                "kind": "canon",
                "seconds": round(shot.seconds, 2),
                "beat": shot.beat,
                # The prompt is not a generation instruction here — nothing is
                # generated. It is what the shot IS, so a human reading the shot list
                # can see it, and so a fallback further down has something to work from
                # if the fetch fails.
                "prompt": f"{entity['title']} — {shot.beat}",
                # Carried as fields rather than parsed back out of `prompt`. The name
                # card and the stat card are rendered from exactly these two, and
                # recovering them from a display string later is a parser nobody asked
                # for standing between the wiki and the screen.
                "entity": entity["title"],
                "stats": dict(entity.get("stats") or {}),
                "asset": shot.asset,
                "asset_url": str(asset.get("url") or ""),
                "asset_page": str(asset.get("page") or ""),
                "licence": asset.get("licence") or {},
                "attribution": str(entity.get("attribution") or ""),
                "source_page": str(entity.get("url") or ""),
                # `composite` says what the shot IS, and it stays true even with no
                # plate found — the renderer needs to know it is holding a cut-out
                # either way, and flipping it to false here would hide the missing
                # plate behind a shot that merely looks flat.
                "composite": bool(shot.composite),
                # Where the background comes from, in preference order. The group is
                # what makes it one purchase rather than one a shot: every composite in
                # this entity's segment names the same group, so the batch generates the
                # plate once and re-uses it.
                "plate_group": entity["title"] if shot.composite else "",
                "plate_prompt": plate_prompt if shot.composite else "",
                "plate_asset": str(plate.get("name") or ""),
                "plate_url": str(plate.get("url") or ""),
                "overlays": list(shot.overlays),
                "animate": bool(shot.animate),
                "tier": STANDARD_TIER,
                "model": "",
                "places": [],
            })
            at += shot.seconds

    # `plates` was written as the running length, which is what the position in the
    # list means; the total per scene is only known once the scene is finished.
    for plates in by_scene.values():
        for plate in plates:
            plate["plates"] = len(plates)
            plate["planned_shots"] = len(plates)

    return by_scene, {"segments": planned_segments, "warnings": warnings,
                      "entities": len(entities)}


@node_handler("broll_plan")
async def broll_plan_node(ctx: NodeContext) -> NodeResult:
    script = ctx.output("script")
    scenes = script.get("scenes") or []

    # Written first, because it decides what is left to plan. A scene whose artwork was
    # fetched needs no prompt, and asking a model to write one would be paying for a
    # description of a picture the run already has.
    canon_by_scene, canon_report = _canon_shots(ctx, scenes)
    to_plan = [scene for scene in scenes if int(scene["index"]) not in canon_by_scene]
    if canon_by_scene:
        ctx.log(
            f"{len(canon_by_scene)} of {len(scenes)} scenes are canon — "
            f"{sum(len(plates) for plates in canon_by_scene.values())} shots planned "
            f"from fetched artwork across {canon_report['entities']} entities, "
            f"nothing generated for them",
            canon_scenes=len(canon_by_scene),
        )
        for note in canon_report["warnings"]:
            ctx.log(f"canon: {note}", level="warning")

    payload = request_payload(
        ctx,
        scenes=[
            {"index": s["index"], "narration": s["narration"][:300],
             "visual_prompt": s.get("visual_prompt", ""), "seconds": s["seconds"]}
            for s in to_plan
        ],
    )
    # Who has to look the same in every shot they appear in. The script stage already
    # worked this out and wrote it to `script.cast` — and until now nothing downstream
    # read it. Forgecast computed the locked likenesses, logged "cast locked: N recurring
    # faces", saved them to disk, and then planned and generated every shot without them.
    # The one thing the module exists to prevent is a second, contradictory description
    # of a recurring character, and that is exactly what a planner with no cast writes.
    #
    # `script["cast"]` is the *built* cast, not the planner's raw answer: the script node
    # overwrites its own key with `company.as_dict()` at content.py:213. Handing that
    # straight back to `build` produces a cast of two characters called "characters" and
    # "walk_ons", which is what the first version of this did and what its test caught.
    # `Character.as_dict` emits name, description and scenes, so the character list is
    # already a shape `build` accepts — it is the wrapper around it that is not.
    stored = script.get("cast")
    raw = stored.get("characters") if isinstance(stored, dict) else stored
    company = cast.build(raw, scenes)
    block = cast.planner_block(company)

    # Nothing left to plan means nothing to ask. A wholly canon video would otherwise
    # pay planning tokens to describe pictures it already holds, and be handed back a
    # shot list for an empty scene list.
    if not to_plan:
        data, credits, provider = {"shots": []}, 0, "canon"
    else:
        data, credits, provider = await ask_json(
            ctx,
            role="Turn the script into a shot list a generation model can execute.",
            schema_name="broll_plan",
            payload=payload,
            # The camera vocabulary is appended rather than written into the constant, so
            # a move added to the catalogue reaches the planner without anyone remembering
            # to update a second copy of the list.
            #
            # The cast goes in the same way and for the same reason, and it goes to the
            # planner as well as onto the prompt afterwards. Stamping alone would leave the
            # planner free to write "an older woman looks up" for someone locked as a
            # seventy-year-old — the prompt then carries two descriptions of one person and
            # the model resolves the contradiction however it likes.
            instructions=(f"{BROLL_INSTRUCTIONS}\n\nCAMERA MOVES\n"
                          f"{camera_moves.planner_vocabulary()}"
                          + (f"\n\n{block}" if block else "")),
            max_tokens=8192,
        )
    if company:
        ctx.log(f"planning to {len(company.characters)} locked "
                f"{'likeness' if len(company.characters) == 1 else 'likenesses'}")

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
    # Measured off the channel's reference where there is one, and from `render.cutting`'s
    # defaults where there is not — `sourcing.budgets` decides which, on one rule, so the
    # ledger that reserves against these and this loop that spends them cannot disagree.
    #
    # This is what replaced "one beat in three may animate". A white-card explainer moves
    # almost nothing and a cinematic channel moves nearly everything, so a third was
    # wrong for both and every run paid for it.
    animated_allowed, heroes_allowed = sourcing.budgets(
        (ctx.channel.style_profile or {}).get("sourcing"), len(scenes))

    # Two counters where there was one, and conflating them is the easiest mistake in
    # this node to make and the hardest to see.
    #
    #   `moving`   — beats that MOVE. Enforces `animated_allowed`, which is the look the
    #                reference dictated: `animation_share` measures the share of shots
    #                that are moving footage rather than stills, and a beat moves whether
    #                the pixels were bought or generated.
    #   `animated` — beats that are GENERATED. Priced into `animation_usd` and reported
    #                as `video_shots`, which `nodes/sample` and the cost log already read
    #                as meaning generated.
    #
    # One counter doing both jobs either lets a channel move more than its reference
    # does, or reports a bill for clips nobody bought.
    moving = 0
    animated = 0
    heroes = 0
    planned_shots = 0
    animation_usd = 0.0

    # ---- pass A: everything that is not money -------------------------------------
    beats: list[dict] = []
    for position, scene in enumerate(scenes):
        # A canon scene's shots are already written, off pictures the run holds. It buys
        # nothing, so it takes no plate, no tier and no place in the animation budget —
        # and it must not reach the free-footage lane either, which would go looking for
        # stock of a creature whose canonical art is already on the timeline.
        if int(scene["index"]) in canon_by_scene:
            planned_shots += len(canon_by_scene[int(scene["index"])])
            continue

        planned = by_index.get(scene["index"], {})
        kind = str(planned.get("kind") or scene.get("visual_kind") or "image")

        places = known_places(planned.get("places"))
        if kind == "map" and not places:
            # A map with nothing to mark is an empty map. Fall back rather than
            # rendering an establishing shot of the whole planet with no point to it.
            kind = "image"
        if kind == "video" and moving >= animated_allowed:
            kind = "image"  # protect the budget from an over-eager plan
        if kind == "video":
            moving += 1
        kind = kind if kind in {"video", "map"} else "image"

        seconds = float(scene["seconds"])
        shot_count = shot_estimate(seconds, spec)
        planned_shots += shot_count

        prompt = str(planned.get("prompt") or scene.get("visual_prompt") or "").strip() \
            or f"cinematic b-roll: {scene['narration'][:120]}"
        # The locked likenesses for the people actually in this scene, appended to the
        # prompt the planner wrote. Only this scene's characters: every locked face costs
        # words in every prompt carrying it, and a prompt holding six descriptions has
        # pushed its own subject out of the model's attention.
        prompt = cast.stamp(prompt, company.in_scene(scene["index"]))

        beats.append({"position": position, "scene": scene, "planned": planned,
                      "kind": kind, "places": places, "seconds": seconds,
                      "shot_count": shot_count, "prompt": prompt,
                      "clip": None, "why": ""})

    # ---- pass B: the free lane, before a single dollar is committed ----------------
    saved_usd = 0.0
    await _offer_free_footage(ctx, beats)

    # ---- pass C: the money, and the shot list --------------------------------------
    for beat in beats:
        position, scene, planned = beat["position"], beat["scene"], beat["planned"]
        kind, places = beat["kind"], beat["places"]
        seconds, shot_count, prompt = beat["seconds"], beat["shot_count"], beat["prompt"]

        # An animated clip and a map are bought once and sliced; only a still is cheap
        # enough that a second one is worth buying to break up a long beat.
        #
        # How many stills a beat is worth is the channel's own measurement: a reference
        # that reframes one picture across four shots buys one plate here, and one that
        # changes picture on every cut buys a plate a shot. Same profile the reserve was
        # computed from, so the hold and the spend cannot disagree.
        #
        # `footage` is not `image`, so it buys one plate — exactly what the `video` beat
        # it replaced already bought. That is the whole reason no measurement function
        # changes: the free lane substitutes strictly *within* a beat class the profile
        # has already counted, so `plates_for`, `estimate_plates`, `budgets` and
        # `animation_reserve` all stay in step without being touched.
        plates = plates_for(seconds, spec, reusable=kind == "image",
                            sourcing=(ctx.channel.style_profile or {}).get("sourcing"))

        # The opening beat is hero whether or not the planner marked it. Position settles
        # that one on its own: it is the shot retention is won or lost on, and it is the
        # only shot in the video every viewer sees.
        tier = HERO_TIER if position == 0 else video_tier(planned.get("tier"))
        model = ""
        if kind == "footage":
            # Free, so it takes no hero slot and adds nothing to the bill. The tier is
            # flattened for the same reason the money block below flattens a still's:
            # a tier is only meaningful where it names a different endpoint, and this
            # beat has none. What it would have cost is recorded, because that number is
            # the whole point of the lane.
            tier = STANDARD_TIER
            saved_usd += video_usd(
                model_for_tier(HERO_TIER if position == 0 else video_tier(planned.get("tier")),
                               standard=standard_model, hero=hero_model),
                seconds)
        elif kind == "video":
            # The budget is spent here and only here, because a tier is only money where
            # it is a different endpoint: a still marked hero costs exactly what a still
            # costs, so charging it against the cap would deny the upgrade to an animated
            # beat that would actually have used it.
            if tier == HERO_TIER and heroes >= heroes_allowed:
                tier = STANDARD_TIER
            if tier == HERO_TIER:
                heroes += 1
            model = model_for_tier(tier, standard=standard_model, hero=hero_model)
            animation_usd += video_usd(model, seconds)
            animated += 1

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
                    # The clip a footage beat will fetch, recorded so the batch does not
                    # search again and get a different answer. `commercially_safe` is
                    # deliberately NOT trusted from here — the shot list is a JSON
                    # artifact an operator can edit, and believing a stored `true` would
                    # be this app vouching for a licence it did not establish, one file
                    # removed. `shots_node` re-asks the clip itself.
                    **({"clip": beat["clip"].as_dict()} if beat["clip"] else {}),
                }
            )

    # Merged in scene order rather than appended, so the shot list reads as the timeline
    # does. `shots_node` walks this in order and the render assembles in the order it is
    # handed, so a canon block sitting at the end would cut the whole video out of
    # sequence — the kind of defect that renders fine and is wrong.
    if canon_by_scene:
        shots = sorted(shots + [plate for plates in canon_by_scene.values()
                                for plate in plates],
                       key=lambda shot: (int(shot["scene_index"]),
                                         int(shot.get("plate_index") or 0)))

    path = ctx.path_for("shot_list.json")
    path.write_text(json.dumps({"shots": shots}, indent=2, ensure_ascii=False), encoding="utf-8")
    ctx.emit_artifact("json", path, "application/json", shots=len(shots))
    sourced = sum(1 for beat in beats if beat["kind"] == "footage")
    ctx.log(
        f"planned {planned_shots} visual shots across {len(scenes)} scenes from "
        f"{len(shots)} plates ({moving} moving: {animated} generated, {sourced} "
        f"sourced), cutting every {spec.target_shot_seconds:.1f}s"
    )
    if sourced:
        # Money not spent, never a refund. The reserve is still held against the whole
        # plan and still released at settle — a hold reduced for footage a search had not
        # run yet would be short whenever the search found nothing, and that is the one
        # direction the ledger cannot recover from mid-run.
        ctx.log(f"{sourced} beat(s) came from licensed footage — about "
                f"${saved_usd:.2f} of generation not bought",
                footage_shots=sourced, footage_usd_saved=round(saved_usd, 2))

    hero_slug = model_for_tier(HERO_TIER, standard=standard_model, hero=hero_model)
    batch_slug = model_for_tier(STANDARD_TIER, standard=standard_model, hero=hero_model)
    if animated:
        # The plan is the stage that decides this spend, so it is the stage that has to
        # say what it decided. Reported per model rather than as one figure at one rate,
        # because a blended plan quoted at either model's rate is wrong in whichever
        # direction that model sits — and the low direction is a reserve that runs out
        # in the middle of a batch.
        ctx.log(
            f"{heroes} hero shot(s) on {hero_slug} and {animated - heroes} on {batch_slug}"
            f" — about ${animation_usd:.2f} of animation",
            hero_model=hero_slug, standard_model=batch_slug,
            video_usd=round(animation_usd, 2),
        )

    return NodeResult(
        output={
            "shots": shots,
            # Generated, not moving. `nodes/sample` and the cost log both
            # read this as "clips somebody will pay for", so a sourced beat
            # must not appear in it — the gate would sample a setup that is
            # never generated.
            "video_shots": animated,
            "footage_shots": sourced,
            "footage_usd_saved": round(saved_usd, 2),
            "moving_shots": moving,
            "hero_shots": heroes,
            "plates": len(shots),
            "planned_shots": planned_shots,
            # Reported separately from `plates` because they are a different kind of
            # thing: a plate is something the run will pay a model for and a canon shot
            # is a file somebody else already made, which is why it carries an
            # attribution line and why `finalize` has to see it.
            "canon_shots": sum(len(plates) for plates in canon_by_scene.values()),
            "canon_scenes": len(canon_by_scene),
            "canon_segments": canon_report.get("segments") or [],
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

    # What a shot with no model recorded is priced and reported as. A plan made before
    # shots carried one — a run paused at the sample gate across this upgrade — reaches
    # here with an empty slug, which the registry resolves to exactly this endpoint. So
    # the render is right either way and only the report is at risk: priced as an empty
    # slug it lands on the unrecognised-model ceiling of $0.40 a second, and the log says
    # five times what the batch actually cost.
    standard_model, hero_model = tier_models(ctx)
    batch_model = model_for_tier(STANDARD_TIER, standard=standard_model, hero=hero_model)

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
    # A channel-level look, not a per-shot one. The style's whole argument is that every
    # cut-out in the video carries the identical halftone screen and sits on the same
    # paper — a collage that changes desk halfway through is a pile of images.
    paper_style = str((ctx.channel.style_profile or {}).get("visual_style") or "") \
        == PAPER_COLLAGE
    # What the animation actually came to, per model. The plan quoted this before the
    # gate; this is the same arithmetic against the shots that survived, so a run whose
    # animations mostly failed over to stills does not report the estimate as a cost.
    animation_usd = 0.0
    clips_by_model: dict[str, int] = {}
    # One plate per canon segment, held across the loop. A `None` entry is cached too —
    # a segment whose plate could not be made must not re-ask on every one of its
    # twenty shots and log the same warning twenty times.
    canon_plates: dict[str, Path | None] = {}

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

        # A clip the operator supplied for this scene, which beats everything below it.
        # They chose this shot; nothing here gets to prefer a generated impression of it
        # or a stock match to the thing they actually wanted.
        #
        # Checked on plate 0 only. Later plates are alternative angles on the same beat
        # and there is one supplied file, so re-using it would cut from one clip to
        # itself. Those fall through and are generated as usual.
        supplied = operator_lane.clip_for(ctx.run_id, index) if plate_index == 0 else None
        if supplied is not None:
            record = operator_lane.note_for(ctx.run_id, index)
            ctx.emit_artifact(
                "video", supplied, "video/mp4",
                scene_index=index, plate_index=plate_index, role="shot",
                seconds=seconds, operator_directed=True,
                # The position, in words, on the artifact — which is what `finalize`
                # reads to write the credits file and to list this in its own section
                # rather than beside clips whose licence the app actually established.
                licence=record.get("licence", "operator_supplied"),
                attribution=record.get("attribution", ""),
                creator=record.get("creator", ""),
                flag_reason=record.get("flag_reason", ""),
            )
            produced.append({"scene_index": index, "plate_index": plate_index,
                             "path": str(supplied), "kind": "operator",
                             "source": "operator", "seconds": seconds})
            ctx.log(f"scene {index}: using the clip you supplied "
                    f"({record.get('title') or supplied.name})")
            continue

        # A shot the plan wrote off fetched canon art. It generates nothing, so it comes
        # before the still: buying a plate here would spend on a picture the run already
        # has, and — the part that matters more than the money — replace the canonical
        # art with an impression of it. These audiences know what the creature looks
        # like and correct the video when it is wrong, so the generated version is not a
        # cheaper shot, it is a wrong one.
        #
        # It never falls through to generation. When the fetch fails the shot is dropped
        # and said so, because the honest failure for a canon shot is a missing shot the
        # operator can fix, not a plausible substitute they will not notice.
        if str(shot.get("kind")) == "canon":
            asset_path = await asyncio.to_thread(_fetch_canon, ctx, shot, slug)
            if asset_path is None:
                degraded += 1
                continue
            plate_path = await _canon_plate(ctx, shot, canon_plates, image_provider,
                                            width, height)
            asset_path = await asyncio.to_thread(
                _stand_subject, ctx, shot, slug, asset_path, plate_path, width, height)
            # Whatever it actually came out as. A shot the planner marked for motion is
            # a clip, and labelling it an image would send `finalize` looking for the
            # attribution on the wrong kind — the credits file collects a sourced
            # shot's line off the "video" artifact, which is where this asset's
            # unresolved licence has to appear.
            moved = asset_path.suffix.lower() == ".mp4"
            ctx.emit_artifact(
                "video" if moved else "image",
                asset_path, "video/mp4" if moved else "image/png",
                scene_index=index, plate_index=plate_index, role="shot",
                prompt=prompt[:300], seconds=seconds,
                # "not stated" travels rather than being dropped. These wikis return no
                # licence fields for most uploads and the file is frequently the
                # original artist's copyright hosted under fair use — so `finalize`
                # gets the file page and the unknown, never a verdict this cannot
                # support.
                licence=(shot.get("licence") or {}).get("LicenseShortName")
                or "not stated",
                attribution=shot.get("attribution", ""),
                creator=(shot.get("licence") or {}).get("Artist", ""),
                landing_url=shot.get("asset_page", ""),
                source="fandom", sourced=True,
            )
            produced.append({"scene_index": index, "plate_index": plate_index,
                             "path": str(asset_path), "kind": "canon",
                             "source": "fandom", "seconds": seconds,
                             "composite": bool(shot.get("composite")),
                             # The graphics this shot was planned to carry, and what
                             # they are drawn from. `render` promotes them to the
                             # scene's motion element — they exist on the shot list
                             # only because the planner works in shots.
                             "overlays": list(shot.get("overlays") or []),
                             "entity": shot.get("entity", ""),
                             "stats": dict(shot.get("stats") or {}),
                             "beat": shot.get("beat", "")})
            continue

        # A beat the plan served from licensed footage. Fetched before the still, which
        # inverts the rule three lines below and is the one place that is right: for a
        # footage shot the still is not a conditioning frame, only insurance, so buying
        # it up front would spend on every beat the free lane just saved.
        #
        # It never falls through to a paid clip. The plan quoted zero here and the Sample
        # Gate approved no setup for it, so generating would be a spend nobody authorised
        # on a model the gate never sampled. When the fetch fails the beat becomes a
        # still, which is the same degradation every other stage in this node performs.
        if str(shot.get("kind")) == "footage" and shot.get("clip"):
            got = await asyncio.to_thread(_fetch_footage, ctx, shot, slug, seconds)
            if got is not None:
                clip_path, clip = got
                ctx.emit_artifact(
                    "video", clip_path, "video/mp4",
                    scene_index=index, plate_index=plate_index, role="shot",
                    prompt=prompt[:300], seconds=seconds,
                    # The credit travels with the shot, which is what `finalize`
                    # collects to write `attribution.md`. The kind must be "video" for
                    # it to be picked up, and it is.
                    licence=clip.licence, attribution=clip.credit_line(),
                    creator=clip.creator, landing_url=clip.landing_url,
                    source=clip.source, sourced=True,
                )
                produced.append({"scene_index": index, "plate_index": plate_index,
                                 "path": str(clip_path), "kind": "footage",
                                 "source": clip.source, "seconds": seconds})
                continue
            degraded += 1
            ctx.log(f"scene {index}: licensed footage could not be fetched — "
                    f"falling back to a still", level="warning")

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

        # The paper-collage style, where generated video is the wrong tool rather than an
        # expensive one. Veo and Kling produce smooth motion, a drifting camera and
        # photoreal texture; this style removes all three, so paying for a clip here buys
        # output that then has to be fought. The still is screened, torn and laid on paper
        # built from the run's own seed — ffmpeg arithmetic, no vendor, no spend.
        if paper_style and plate is not None:
            try:
                beat = await asyncio.to_thread(
                    paper.compose_beat, plate, ctx.path_for(f"{slug}_paper"),
                    seconds=seconds, index=index,
                    text=str(shot.get("on_screen_text") or ""),
                    width=width, height=height,
                    workdir=ctx.path_for(f"{slug}_paperwork"),
                )
                ctx.emit_artifact("video", beat, "video/mp4", scene_index=index,
                                  plate_index=plate_index, role="shot", seconds=seconds,
                                  style="paper_collage")
                produced.append({"scene_index": index, "plate_index": plate_index,
                                 "path": str(beat), "kind": "paper", "seconds": seconds})
                continue
            except Exception as exc:
                degraded += 1
                ctx.log(f"shot {index}: the paper composite failed, using the still "
                        f"({exc})", level="warning")

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
                billed_on = model or batch_model
                animation_usd += video_usd(billed_on, seconds)
                clips_by_model[billed_on] = clips_by_model.get(billed_on, 0) + 1
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

    # Planned against produced, for the one treatment that can be planned and then
    # silently not happen. Two rules that each looked right marked motion onto the
    # shots that could not take it, so every run planned two clips and rendered none —
    # and the only way that was ever going to surface was somebody counting the files.
    # Counting it here means the run says so itself.
    asked_to_move = sum(1 for shot in shots if shot.get("animate"))
    moved = sum(1 for item in usable if str(item.get("path", "")).endswith("_drift.mp4"))
    if asked_to_move:
        ctx.log(f"{moved}/{asked_to_move} shot(s) planned for motion actually moved",
                planned_motion=asked_to_move, rendered_motion=moved,
                level="info" if moved == asked_to_move else "warning")
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
