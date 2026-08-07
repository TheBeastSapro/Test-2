"""Final stages: render, compliance, the pre-publish gate, and the upload itself.

Note the shape of the gate here. Every earlier gate reviews a node's *own* output
after it ran — cheap to redo, so running first and asking after is correct. Publishing
is different: you cannot un-upload. So the approval lives in its own `final_review`
node that spends nothing, and `publish` runs unattended once that gate passes.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from ..config import get_settings
from ..graph.engine import NodeContext, NodeResult, node_handler
from ..providers import ProviderError
from ..providers.youtube import publisher_for
from ..render import Scene, assemble_video
from ..render.cutting import SceneBeat, plan_cuts, shots_per_minute, spec_for
from ._common import ask_json, dimensions, request_payload

COMPLIANCE_INSTRUCTIONS = """Review this video for platform-policy and honesty risk
before it is published.

Return JSON: {"verdict", "issues", "checks"}
  verdict  "pass" | "warn" | "fail"
  issues   array of {severity: "low"|"medium"|"high", area, detail, fix}
  checks   object noting what you examined

Fail only for things that would get the video removed, demonetised, or that mislead
the viewer: unsupported medical/financial claims, impersonation, hate or harassment,
graphic content, copyright-infringing material, a title the video does not deliver,
or missing disclosure of AI-generated or sponsored content where it is required.
Style disagreements are not failures."""


# -------------------------------------------------------------------------- render


@node_handler("render")
async def render_node(ctx: NodeContext) -> NodeResult:
    script = ctx.output("script")
    plates = _plates_by_scene(ctx.output("shots").get("shots", []))
    voice_output = ctx.output("voice")
    segments = {int(s["scene_index"]): s for s in voice_output.get("segments", [])}

    width, height = dimensions(ctx)
    scenes: list[Scene] = []
    beats: list[SceneBeat] = []
    for entry in script.get("scenes") or []:
        index = int(entry["index"])
        # The narration decides the cut length — visuals stretch to fit, never the reverse.
        seconds = round(float(segments.get(index, {}).get("seconds") or entry["seconds"]), 3)
        found = plates.get(index) or []
        usable = [Path(item["path"]) for item in found if item.get("path")]
        usable = [path for path in usable if path.exists()]
        if found and not usable:
            ctx.log(f"scene {index}: visual missing on disk, using a card", level="warning")
        scenes.append(
            Scene(
                index=index,
                seconds=seconds,
                visual_path=usable[0] if usable else None,
                narration=entry["narration"],
                meta={"on_screen_text": entry.get("on_screen_text", "")},
                plates=usable,
            )
        )
        beats.append(
            SceneBeat(
                index=index,
                seconds=seconds,
                plates=max(1, len(usable)),
                # Two reasons not to cut a scene up. A map animates itself along a route,
                # and punching in mid-route reads as a mistake rather than an edit. And a
                # scene with no visual at all falls back to a colour card, so subdividing
                # it would spend a dozen encodes cutting between identical cards.
                hold=not usable or any(item.get("kind") == "map" for item in found),
            )
        )

    if not scenes:
        raise ProviderError("nothing to render")

    # Subdivision. Without it a scene is one visual held for its entire voiceover, which
    # on an 8-minute video is roughly eight pictures at a minute each. The narration
    # lengths used here are the measured ones from the voice node, not the script's
    # estimates, because these are the numbers the audio track actually has — and
    # `plan_cuts` raises rather than letting the two disagree by a millisecond.
    spec = spec_for(ctx.channel.style_profile)
    # The same learned block `spec` is built from, kept whole: the renderer needs
    # two fields off it that `RenderSpec` does not carry.
    learned = (ctx.channel.style_profile or {}).get("render_spec") or {}
    cuts = plan_cuts(beats, spec)
    rate = shots_per_minute(cuts)

    narration = Path(voice_output["narration_path"])
    # The scored mix when the sound stage produced one — narration with the bed ducked
    # under it and the accents on top. Checked on disk as well as in the output because a
    # node that reported a path and a file that exists are two different claims, and
    # silently rendering the dry narration under an output that names a track is the one
    # way this stage can lie about what shipped.
    scored = Path(str((ctx.upstream_outputs.get("sound") or {}).get("mixed_path") or ""))
    audio_source = "voice"
    if scored.name and scored.exists():
        narration = scored
        audio_source = "sound"

    avatar_output = ctx.upstream_outputs.get("avatar") or {}
    avatar_path = (
        Path(avatar_output["avatar_path"])
        if avatar_output.get("avatar_path") and not avatar_output.get("skipped")
        else None
    )

    out_path = ctx.path_for("final.mp4")
    workdir = ctx.path_for("work")
    ctx.log(
        f"rendering {len(scenes)} scenes as {len(cuts)} shots at {width}x{height} — "
        f"{rate:.1f} shots/min from {sum(len(s.plates) for s in scenes)} plates "
        f"(target {spec.target_shot_seconds:.1f}s per shot)"
    )

    preset, plans = _motion_for(ctx, scenes, script)
    backend_name = str(ctx.options.get("motion_backend")
                       or (ctx.channel.style_profile or {}).get("motion_backend")
                       or "ffmpeg")
    if preset is not None:
        from ..render.backends import backend_for

        # Resolve now so the log names the engine that will actually run, not the one
        # that was asked for — an unavailable backend silently downgrades to ffmpeg.
        backend_name = backend_for(backend_name).name
        animated = [item for item in plans if item.active]
        ctx.log(
            f"motion preset '{preset.name}' (intensity {preset.intensity:.2f}, "
            f"{preset.provenance.get('origin', 'built_in')}) via {backend_name}: "
            f"{len(animated)} of {len(scenes)} scenes animated"
        )

    # ffmpeg is blocking and CPU-bound; keep it off the event loop.
    await asyncio.to_thread(
        assemble_video,
        scenes,
        out_path,
        workdir=workdir,
        narration_path=narration if narration.exists() else None,
        width=width,
        height=height,
        # The channel's rate, not the encoder's constant. It has to reach every piece of
        # the render: `concat_clips` stream-copies, so pieces at mixed rates produce a
        # file whose timestamps drift against its audio.
        fps=int(ctx.params.get("fps") or getattr(ctx.channel, "video_fps", 0) or 0) or None,
        # The machine's encoder, not the channel's. A GPU belongs to the computer, and
        # `Channel` is what the cloud backup copies — a channel restored onto a second
        # machine must not arrive asking for hardware that machine does not have.
        # An unavailable choice downgrades to the CPU rather than failing a render that
        # has already paid for a script, a voiceover and eighty shots.
        encoder=str(ctx.params.get("encoder") or get_settings().video_encoder or ""),
        avatar_path=avatar_path,
        subtitles=bool(ctx.params.get("subtitles", True)),
        # How this channel joins its shots, off the same learned spec the cutting
        # rhythm comes from. `render/transitions.py` shipped complete and unreachable,
        # so every video this app made was hard-cut regardless of what its reference
        # did — which looked correct on a reference that hard-cuts and silently wrong
        # on one that does not.
        transition=str(learned.get("transition") or ""),
        dissolve_share=float(learned.get("dissolve_share") or 0.0),
        motion_preset=preset,
        motion_plans=plans,
        motion_backend=backend_name,
        shot_cuts=cuts,
    )

    from ..render import ffprobe_duration

    duration = await asyncio.to_thread(ffprobe_duration, out_path)
    ctx.emit_artifact(
        "video", out_path, "video/mp4", role="final", seconds=duration,
        width=width, height=height,
    )
    captions = workdir / "captions.srt"
    if captions.exists():
        ctx.emit_artifact("text", captions, "application/x-subrip", role="captions")

    credits = _write_attribution(ctx, workdir)
    if credits is not None:
        ctx.emit_artifact("text", credits, "text/markdown", role="attribution")

    ctx.log(f"rendered {duration:.1f}s ({out_path.stat().st_size / 1_048_576:.1f} MB)")
    return NodeResult(
        output={
            "video_path": str(out_path),
            "duration_seconds": round(duration, 2),
            "width": width,
            "height": height,
            "size_bytes": out_path.stat().st_size,
            # Which audio track went into the file: the scored mix, or the dry narration.
            # Recorded rather than inferred, because "the sound node bought a bed" and
            # "the video contains it" are two claims, and the gap between them is silent.
            "audio_source": audio_source,
            "cutting": {
                "shots": len(cuts),
                "scenes": len(scenes),
                "plates": sum(len(scene.plates) for scene in scenes),
                "shots_per_minute": round(rate, 2),
                "target_shot_seconds": round(spec.target_shot_seconds, 3),
                "style": "measured" if (ctx.channel.style_profile or {}).get("render_spec")
                         else "default",
            },
            "motion": {
                "preset": preset.name if preset else None,
                "backend": backend_name if preset else None,
                "intensity": preset.intensity if preset else None,
                "origin": preset.provenance.get("origin") if preset else None,
                "scenes": [item.as_dict() for item in plans],
            },
        },
        credits=0,
        provider="local-ffmpeg",
    )


def _write_attribution(ctx: NodeContext, workdir) -> Path | None:
    """The credit file the licences require, beside the video they belong to.

    This is written because it was not. `stock.attribution_markdown` has been able to
    produce this block since stock imagery was added and nothing has ever called it — so
    every `by`-licensed photograph this app has ever used shipped without the credit its
    licence obliges, which that module's own docstring calls out as not a technicality.
    The code was there, the rule was written down, and the two were never connected.

    Emitted as an artifact rather than left in the workdir, because a credit file that
    does not travel with the video is the same failure one step later: the operator
    uploads the render and the attribution stays on a machine.

    Returns `None` when there is genuinely nothing to credit — a run made entirely of
    generated plates owes no one a line, and writing an empty file would train an
    operator to ignore the one that matters.
    """
    from ..providers.footage import FootageClip, attribution_markdown

    clips: list[FootageClip] = []
    for kind in ("image", "video"):
        for ref in ctx.artifacts("shots", kind):
            meta = ref.meta or {}
            licence = str(meta.get("licence") or "")
            attribution = str(meta.get("attribution") or "")
            if not licence and not attribution:
                continue  # a generated plate: nothing was licensed, nothing is owed
            clips.append(FootageClip(
                url=str(getattr(ref, "path", "") or ""),
                title=str(meta.get("title") or meta.get("prompt") or "")[:120],
                creator=str(meta.get("creator") or ""),
                licence=licence,
                source=str(meta.get("source") or "stock"),
                landing_url=str(meta.get("landing_url") or ""),
                attribution=attribution,
                operator_directed=bool(meta.get("operator_directed")),
                flag_reason=str(meta.get("flag_reason") or ""),
            ))

    body = attribution_markdown(clips)
    if not body.strip():
        return None

    path = Path(workdir) / "attribution.md"
    path.write_text(
        f"# Credits for this video\n\n{body}\n", encoding="utf-8",
    )
    directed = sum(1 for clip in clips if clip.operator_directed)
    ctx.log(
        f"wrote credits for {len(clips)} sourced asset(s)"
        + (f", {directed} operator-directed" if directed else "")
    )
    return path


def _plates_by_scene(produced: list) -> dict[int, list[dict]]:
    """Group the shots node's output by scene, in plate order.

    Sorted on `plate_index` rather than trusting the emission order: the node degrades
    per plate, so a scene whose second plate failed and was retried can hand these back
    out of sequence, and plate 0 is the establishing framing every scene opens on.
    """
    grouped: dict[int, list[dict]] = {}
    for item in produced or []:
        if not isinstance(item, dict) or item.get("scene_index") is None:
            continue
        grouped.setdefault(int(item["scene_index"]), []).append(item)
    for entries in grouped.values():
        entries.sort(key=lambda item: int(item.get("plate_index") or 0))
    return grouped


def _motion_for(ctx: NodeContext, scenes: list[Scene], script: dict):
    """Resolve the run's motion preset and plan, or (None, []) when motion is off.

    Motion is opt-out rather than opt-in: a faceless video with no graphics at all
    reads as a slideshow, which is the failure mode this whole module exists to avoid.
    Setting `motion: false` on the run turns it off entirely.
    """
    from ..render.motion_layer import plan as plan_motion
    from ..render.motion_layer import resolve_preset

    style = ctx.channel.style_profile or {}
    # Three sources, most specific first: what this run asked for, what the pipeline
    # sets by default, and what the channel always uses.
    if False in (ctx.options.get("motion"), ctx.params.get("motion"),
                 style.get("motion")):
        return None, []

    name = str(ctx.options.get("motion_preset") or ctx.params.get("motion_preset")
               or style.get("motion_preset") or "")
    # An analysed reference leaves its measurements on the channel, so a run that has
    # never been given a reference still gets motion sized to the intended pacing.
    measured = style.get("render_spec") or {}
    intensity = measured.get("motion_intensity")
    preset = resolve_preset(
        name,
        intensity=float(intensity) if isinstance(intensity, (int, float)) else None,
        directory=ctx.options.get("motion_preset_dir") or "./storage/motion_presets",
    )
    headline = str(script.get("title") or ctx.topic or "")
    return preset, plan_motion(scenes, preset=preset, headline=headline)


# ---------------------------------------------------------------------- compliance


@node_handler("compliance")
async def compliance_node(ctx: NodeContext) -> NodeResult:
    script = ctx.output("script")
    render = ctx.output("render")

    hard_failures = _mechanical_checks(ctx, script, render)

    data, credits, provider = await ask_json(
        ctx,
        role="Act as the channel's policy reviewer.",
        schema_name="compliance",
        payload=request_payload(
            ctx,
            title=script.get("title"),
            description=(script.get("description") or "")[:2000],
            tags=script.get("tags"),
            narration="\n".join(s["narration"] for s in script.get("scenes", []))[:12000],
            duration_seconds=render.get("duration_seconds"),
        ),
        instructions=COMPLIANCE_INSTRUCTIONS,
        max_tokens=2048,
        temperature=0.2,
    )

    verdict = str(data.get("verdict") or "warn").lower()
    issues = [i for i in (data.get("issues") or []) if isinstance(i, dict)]
    if hard_failures:
        verdict = "fail"
        issues = [
            {"severity": "high", "area": "mechanical", "detail": detail, "fix": fix}
            for detail, fix in hard_failures
        ] + issues

    output = {
        "verdict": verdict,
        "issues": issues,
        "checks": data.get("checks") or {},
        "mechanical_failures": [d for d, _ in hard_failures],
    }
    path = ctx.path_for("compliance.json")
    path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    ctx.emit_artifact("json", path, "application/json", verdict=verdict)

    if verdict == "fail":
        detail = "; ".join(
            str(i.get("detail")) for i in issues[:4] if i.get("detail")
        ) or "policy review failed"
        # Deliberately not retryable: re-asking will not fix the content.
        raise ProviderError(f"compliance check failed — {detail}")

    ctx.log(f"compliance {verdict} with {len(issues)} issue(s)",
            level="warning" if issues else "info")
    return NodeResult(output=output, credits=credits, provider=provider)


def _mechanical_checks(ctx: NodeContext, script: dict, render: dict) -> list[tuple[str, str]]:
    """Deterministic checks no model should be trusted with."""
    failures: list[tuple[str, str]] = []

    title = str(script.get("title") or "")
    if not title.strip():
        failures.append(("title is empty", "regenerate the script metadata"))
    if len(title) > 100:
        failures.append((f"title is {len(title)} characters (limit 100)", "shorten the title"))
    if len(str(script.get("description") or "")) > 5000:
        failures.append(("description exceeds 5000 characters", "trim the description"))

    duration = float(render.get("duration_seconds") or 0)
    if duration < 3:
        failures.append((f"rendered file is only {duration:.1f}s", "check the render node"))

    video = Path(str(render.get("video_path") or ""))
    if not video.exists() or video.stat().st_size < 10_000:
        failures.append(("rendered file is missing or truncated", "re-run the render node"))

    thumbnails = ctx.artifacts("thumbnail", "image")
    if thumbnails:
        chosen = thumbnails[0].path
        if chosen.exists() and chosen.stat().st_size > 2 * 1024 * 1024:
            failures.append(
                ("thumbnail is over YouTube's 2MB limit", "re-encode the thumbnail")
            )
    return failures


# -------------------------------------------------------------------- final review


@node_handler("final_review")
async def final_review_node(ctx: NodeContext) -> NodeResult:
    """Assembles the publish payload for the operator. Spends nothing.

    This node exists purely to hold the gate: it gathers the finished video, the
    chosen thumbnail and the metadata into one object the UI can preview, and the
    operator can patch any field when approving.
    """
    script = ctx.output("script")
    render = ctx.output("render")
    compliance = ctx.output("compliance")

    thumbnails = ctx.artifacts("thumbnail", "image")
    selected = ctx.upstream_outputs.get("thumbnail", {}).get("selected_index", 0)
    thumbnail = thumbnails[selected].path if selected < len(thumbnails) else (
        thumbnails[0].path if thumbnails else None
    )

    metadata = {
        "title": str(script.get("title") or ctx.topic)[:100],
        "description": str(script.get("description") or "")[:5000],
        "tags": [str(t)[:30] for t in (script.get("tags") or [])][:15],
        "category_id": str(ctx.params.get("category_id") or "27"),
        "privacy_status": str(ctx.options.get("privacy_status") or "private"),
        "publish_at": ctx.options.get("publish_at") or None,
        "made_for_kids": bool(ctx.options.get("made_for_kids", False)),
    }

    output = {
        "metadata": metadata,
        "video_path": render.get("video_path"),
        "thumbnail_path": str(thumbnail) if thumbnail else None,
        "duration_seconds": render.get("duration_seconds"),
        "size_bytes": render.get("size_bytes"),
        "compliance_verdict": compliance.get("verdict"),
        "compliance_issues": compliance.get("issues", []),
    }
    ctx.log("ready to publish — awaiting final approval")
    return NodeResult(output=output, credits=0, provider="local")


# ------------------------------------------------------------------------- publish


@node_handler("publish")
async def publish_node(ctx: NodeContext) -> NodeResult:
    review = ctx.output("final_review")
    metadata = dict(review.get("metadata") or {})

    video_path = Path(str(review.get("video_path") or ""))
    if not video_path.exists():
        raise ProviderError(f"no rendered video at {video_path}")

    refresh_token = ctx.channel.youtube_refresh_token
    publisher = publisher_for()
    if publisher.name != "mock-youtube" and not refresh_token:
        raise ProviderError(
            "this channel is not connected to YouTube — authorise it under "
            "Channel → Connect YouTube, or run in mock mode"
        )

    thumbnail = review.get("thumbnail_path")
    result = await publisher.upload(
        video_path=video_path,
        refresh_token=refresh_token,
        title=metadata.get("title", ctx.topic)[:100],
        description=metadata.get("description", ""),
        tags=list(metadata.get("tags") or []),
        category_id=str(metadata.get("category_id") or "27"),
        privacy_status=str(metadata.get("privacy_status") or "private"),
        publish_at=metadata.get("publish_at"),
        thumbnail_path=Path(thumbnail) if thumbnail else None,
        made_for_kids=bool(metadata.get("made_for_kids", False)),
    )

    ctx.log(f"published as {result.video_id} ({result.privacy_status})", url=result.url)
    return NodeResult(
        output={
            "video_id": result.video_id,
            "url": result.url,
            "privacy_status": result.privacy_status,
            "published_metadata": metadata,
        },
        credits=2,
        provider=result.provider,
    )
