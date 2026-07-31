"""Text stages: production brief and full script.

Both sit behind approval gates because they are the cheapest place to change the
video. Rewriting a brief costs a few credits; rewriting after the shots are
generated costs hundreds.
"""

from __future__ import annotations

import json

from ..graph.engine import NodeContext, NodeResult, node_handler
from ..providers import ProviderError
from ._common import ask_json, request_payload, target_seconds

WORDS_PER_SECOND = 2.6

BRIEF_INSTRUCTIONS = """Produce a production brief for one video.

Return JSON with exactly these keys:
  working_title   string, under 70 characters, no clickbait the video cannot deliver
  angle           string, the specific claim or lens that makes this video worth making
  audience        string, who this is for
  hook            string, the first spoken sentence of the video
  promise         string, what the viewer will know by the end
  target_duration_seconds  integer, echo the requested duration
  beats           array of 4-12 objects: {name, purpose, summary}
  keywords        array of 4-8 search terms

Beats must be a real outline: each one advances the argument. Do not write
"introduction / body / conclusion"."""

SCRIPT_INSTRUCTIONS = """Write the complete narration script from the approved brief.

Return JSON with exactly these keys:
  title        string, final video title, max 100 characters
  description  string, YouTube description, max 4000 characters
  tags         array of up to 15 lowercase tags
  scenes       array of objects: {index, narration, visual_prompt, visual_kind, seconds,
               on_screen_text}

Rules for scenes:
  - `narration` is what the voice actually says. Plain spoken prose. No stage
    directions, no "[pause]", no speaker labels, no markdown.
  - `visual_prompt` describes the shot for an image/video generator: subject,
    composition, lighting, camera move. It must never contain readable text,
    logos, watermarks, or a recognisable real person's face.
  - `visual_kind` is "video" for shots that need motion, "image" otherwise. Prefer
    "image" — it is roughly ten times cheaper.
  - `seconds` is the narration length at 2.6 words per second, rounded to 0.1.
  - Total narration must land within 10% of target_duration_seconds.
  - Cover every beat from the brief, in order."""


@node_handler("brief")
async def brief_node(ctx: NodeContext) -> NodeResult:
    seconds = target_seconds(ctx)
    payload = request_payload(ctx, target_duration_seconds=seconds)
    data, credits, provider = await ask_json(
        ctx,
        role="Write a production brief that makes the video specific instead of generic.",
        schema_name="brief",
        payload=payload,
        instructions=BRIEF_INSTRUCTIONS,
        max_tokens=2048,
    )

    beats = data.get("beats") or []
    if not isinstance(beats, list) or len(beats) < 2:
        raise ProviderError("brief came back without a usable beat outline")
    data.setdefault("target_duration_seconds", seconds)

    path = ctx.path_for("brief.json")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    ctx.emit_artifact("json", path, "application/json", beats=len(beats))
    ctx.log(f"brief ready: {data.get('working_title', 'untitled')!r}", beats=len(beats))

    return NodeResult(output=data, credits=credits, provider=provider)


@node_handler("script")
async def script_node(ctx: NodeContext) -> NodeResult:
    brief = ctx.output("brief")
    seconds = int(brief.get("target_duration_seconds") or target_seconds(ctx))
    payload = request_payload(ctx, target_duration_seconds=seconds, brief=brief)

    # Research, when the pipeline ran it, is appended as a hard constraint rather than
    # background reading: it names exactly which facts are available and forbids the
    # rest. Without it the house rule against inventing statistics has nothing to
    # stand on, because a documentary script with no sources will manufacture them.
    instructions = SCRIPT_INSTRUCTIONS
    research = ctx.upstream_outputs.get("research") or {}
    if research.get("prompt_block"):
        instructions = f"{SCRIPT_INSTRUCTIONS}\n\n{research['prompt_block']}"

    data, credits, provider = await ask_json(
        ctx,
        role="Write the full narration script.",
        schema_name="script",
        payload=payload,
        instructions=instructions,
        max_tokens=16384,
        temperature=0.8,
    )

    scenes = _normalise_scenes(data.get("scenes"))
    data["scenes"] = scenes
    data["word_count"] = sum(len(scene["narration"].split()) for scene in scenes)
    data["estimated_seconds"] = round(sum(scene["seconds"] for scene in scenes), 1)
    data.setdefault("title", brief.get("working_title", ctx.topic)[:100])

    script_path = ctx.path_for("script.json")
    script_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    ctx.emit_artifact("json", script_path, "application/json", scenes=len(scenes))

    readable = ctx.path_for("script.md")
    readable.write_text(_as_markdown(data), encoding="utf-8")
    ctx.emit_artifact(
        "script", readable, "text/markdown",
        words=data["word_count"], scenes=len(scenes),
    )

    drift = abs(data["estimated_seconds"] - seconds) / max(seconds, 1)
    if drift > 0.2:
        ctx.log(
            f"script is {data['estimated_seconds']:.0f}s against a {seconds}s target "
            f"({drift:.0%} off)",
            level="warning",
        )
    if research:
        claims = (research.get("counts") or {}).get("claims_verified", 0)
        data["research_claims_available"] = claims
        if claims == 0:
            ctx.log(
                "written without sourced facts — research found nothing verifiable",
                level="warning",
            )

    ctx.log(
        f"script ready: {len(scenes)} scenes, {data['word_count']} words, "
        f"~{data['estimated_seconds']:.0f}s"
    )
    return NodeResult(output=data, credits=credits, provider=provider)


def _normalise_scenes(raw) -> list[dict]:
    if not isinstance(raw, list) or not raw:
        raise ProviderError("script came back with no scenes")

    scenes: list[dict] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        narration = str(item.get("narration") or "").strip()
        if not narration:
            continue
        words = len(narration.split())
        seconds = item.get("seconds")
        try:
            seconds = float(seconds)
        except (TypeError, ValueError):
            seconds = 0.0
        # Trust the word count over the model's arithmetic.
        computed = words / WORDS_PER_SECOND
        if seconds <= 0.5 or abs(seconds - computed) > max(2.0, computed * 0.5):
            seconds = computed
        scenes.append(
            {
                "index": index,
                "narration": narration,
                "visual_prompt": str(item.get("visual_prompt") or "").strip()
                or f"cinematic b-roll for: {narration[:120]}",
                "visual_kind": "video" if str(item.get("visual_kind")) == "video" else "image",
                "seconds": round(max(seconds, 0.8), 2),
                "on_screen_text": str(item.get("on_screen_text") or "")[:60],
            }
        )
    if not scenes:
        raise ProviderError("script scenes were all empty after validation")
    return scenes


def _as_markdown(script: dict) -> str:
    lines = [f"# {script.get('title', 'Untitled')}", ""]
    total = script.get("estimated_seconds", 0)
    lines.append(f"_{script.get('word_count', 0)} words · ~{total:.0f}s · "
                 f"{len(script['scenes'])} scenes_")
    lines.append("")
    for scene in script["scenes"]:
        lines += [
            f"## Scene {scene['index'] + 1} · {scene['seconds']:.1f}s",
            "",
            scene["narration"],
            "",
            f"> **Visual ({scene['visual_kind']}):** {scene['visual_prompt']}",
            "",
        ]
    if script.get("description"):
        lines += ["---", "", "### Description", "", script["description"], ""]
    return "\n".join(lines)
