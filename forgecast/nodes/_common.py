"""Shared prompt plumbing for node handlers."""

from __future__ import annotations

import json

from ..graph.engine import NodeContext
from ..providers import ProviderError
from ..providers.llm import extract_json

HOUSE_STYLE = """You are the showrunner for a faceless video channel. You write for
the ear, not the page: short sentences, concrete nouns, no filler, no throat-clearing.
You never invent statistics, quotes, or citations. If a claim needs a source you do
not have, you rewrite the sentence so it does not need one. You do not write clickbait
that the video fails to deliver on."""


def system_prompt(ctx: NodeContext, role: str) -> str:
    parts = [HOUSE_STYLE, "", f"YOUR TASK RIGHT NOW: {role}", ""]
    parts.append(
        f"CHANNEL: {ctx.channel.name or 'unnamed'} — niche: {ctx.channel.niche or 'general'} "
        f"— language: {ctx.channel.language}"
    )
    if ctx.memory_block:
        parts += ["", ctx.memory_block]
    if ctx.revision_feedback:
        parts += [
            "",
            "THE OPERATOR REJECTED YOUR PREVIOUS ATTEMPT. Their instruction, which "
            f"overrides your own preferences: {ctx.revision_feedback}",
        ]
    return "\n".join(parts)


def request_payload(ctx: NodeContext, **extra) -> str:
    """The machine-readable half of the prompt. Keep every number the model needs here."""
    payload = {
        "topic": ctx.topic,
        "channel": {
            "name": ctx.channel.name,
            "niche": ctx.channel.niche,
            "language": ctx.channel.language,
            "aspect_ratio": ctx.channel.aspect_ratio,
        },
        "target_duration_seconds": int(
            ctx.params.get("target_duration_seconds")
            or ctx.options.get("target_seconds")
            or ctx.channel.target_duration_seconds
            or 480
        ),
    }
    payload.update(extra)
    return json.dumps(payload, indent=2, ensure_ascii=False)


async def ask_json(
    ctx: NodeContext, *, role: str, schema_name: str, payload: str, instructions: str,
    max_tokens: int = 8192, temperature: float = 0.7,
) -> tuple[dict, int, str]:
    """One structured LLM call. Returns (data, credits, provider)."""
    llm = ctx.registry.llm()
    prompt = f"{instructions}\n\nINPUT:\n{payload}"
    result = await llm.complete(
        prompt,
        system=system_prompt(ctx, role),
        json_object=True,
        schema_name=schema_name,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    data = extract_json(result.text)
    if not isinstance(data, dict):
        raise ProviderError(f"{schema_name} response was not a JSON object")
    return data, result.credits, result.provider


def target_seconds(ctx: NodeContext) -> int:
    return int(
        ctx.params.get("target_duration_seconds")
        or ctx.options.get("target_seconds")
        or ctx.channel.target_duration_seconds
        or 480
    )


#: Heights this pipeline will render at, shortest first.
#:
#: 720 is kept because it exists in stored runs and because it halves the encode time on
#: a slow machine. It is not the default any more: it was, for 16:9 only, while vertical
#: and square already rendered at 1080 — so the main format was the one format shipping at
#: the lower resolution, which is the opposite of the intent and was nobody's decision.
#:
#: 1440 is offered and not recommended. Most i2v vendors return 720p or 1080p, so a 1440
#: timeline upscales them; what it genuinely sharpens is type, captions and motion
#: graphics, which are drawn at whatever height they are given.
SUPPORTED_HEIGHTS: tuple[int, ...] = (720, 1080, 1440)
DEFAULT_HEIGHT = 1080

#: Width for one height, per aspect. Both even, because libx264 will not take an odd one.
_ASPECTS: dict[str, float] = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0,
                              "4:3": 4 / 3, "21:9": 21 / 9}


def resolve_height(height: int | None = None) -> int:
    """Snapped to a height this pipeline renders at, nearest wins."""
    wanted = int(height or DEFAULT_HEIGHT)
    if wanted in SUPPORTED_HEIGHTS:
        return wanted
    return min(SUPPORTED_HEIGHTS, key=lambda option: abs(option - wanted))


def frame_for(aspect_ratio: str, height: int | None = None) -> tuple[int, int]:
    """The frame one aspect gets at one height.

    Derived rather than tabulated, so adding a height does not mean adding a row per
    aspect — and so a channel set to 21:9 gets a 21:9 frame rather than falling through
    to 16:9, which the hardcoded table it replaces did silently.
    """
    named = resolve_height(height)
    ratio = _ASPECTS.get(str(aspect_ratio or ""), 16 / 9)

    # The named resolution is the *short* edge, whichever edge that is. "1080p" means
    # 1920x1080 landscape and 1080x1920 portrait — the number is 1080 in both, and it is
    # the height of one and the width of the other. Treating it as the height always gave
    # 9:16 a 608x1080 frame: correctly 9:16, and a third of the pixels anybody asking for
    # 1080p expected.
    if ratio < 1:
        wide, tall = named, round(named / ratio)
    else:
        wide, tall = round(named * ratio), named

    # Both even, because libx264 will not take an odd dimension and the failure lands at
    # encode time rather than here.
    return (wide // 2 * 2, tall // 2 * 2)


def dimensions(ctx: NodeContext) -> tuple[int, int]:
    """The frame this node renders at.

    Run params win, then the channel's standing choice, then the default — the same
    precedence every other per-run setting uses, because "render this one at 720 to see
    it quickly" has to beat the channel without changing it.
    """
    width = int(ctx.params.get("width") or 0)
    height = int(ctx.params.get("height") or 0)
    if width and height:
        return width, height
    return frame_for(getattr(ctx.channel, "aspect_ratio", "16:9"),
                     int(getattr(ctx.channel, "video_height", 0) or 0))
