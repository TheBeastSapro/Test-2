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


def dimensions(ctx: NodeContext) -> tuple[int, int]:
    width = int(ctx.params.get("width") or 0)
    height = int(ctx.params.get("height") or 0)
    if width and height:
        return width, height
    if ctx.channel.aspect_ratio == "9:16":
        return 1080, 1920
    if ctx.channel.aspect_ratio == "1:1":
        return 1080, 1080
    return 1280, 720
