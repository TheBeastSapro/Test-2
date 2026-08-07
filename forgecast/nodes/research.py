"""Research and voice-casting nodes.

Both sit early in the graph for the same reason the other gates do: they determine
what the expensive stages produce. Research shapes the script, and the voice decides
how every second of narration sounds — so both belong before anything is synthesised,
and the voice choice belongs to a human.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..graph.engine import NodeContext, NodeResult, node_handler
from ..providers.base import ProviderError
from ..providers.search import provider_for
from ..research import research_topic
from ..voice import casting_summary, render_samples, sample_line, shortlist, target_from_reference


@node_handler("research")
async def research_node(ctx: NodeContext) -> NodeResult:
    """Gather cited claims before the script is written.

    Placed before `script` deliberately. Asking a model for a documentary with no
    sources produces invented numbers, because the genre expects them — the fix is to
    give it real ones, and to record plainly what could not be sourced.
    """
    brief = ctx.upstream_outputs.get("brief") or {}
    angle = str(brief.get("angle") or "")
    search = provider_for(ctx.registry.user_keys)

    result = await research_topic(
        ctx.topic,
        llm=ctx.registry.llm(),
        search=search,
        angle=angle,
        max_queries=int(ctx.params.get("max_queries") or 5),
        max_pages=int(ctx.params.get("max_pages") or 8),
    )

    payload = result.as_dict()
    path = ctx.path_for("research.json")
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    ctx.emit_artifact(
        "json", path, "application/json",
        claims=len(result.verified_claims), sources=len(result.usable_sources),
    )

    readable = ctx.path_for("research.md")
    readable.write_text(_as_markdown(result), encoding="utf-8")
    ctx.emit_artifact("text", readable, "text/markdown", role="research")

    counts = payload["counts"]
    ctx.log(
        f"research: {counts['claims_verified']} verified claims from "
        f"{counts['sources_fetched']}/{counts['sources']} sources, "
        f"{counts['claims_rejected']} rejected for unmatched quotes"
    )
    if not result.verified_claims:
        # Not a failure. The script node reads this and writes without factual
        # claims, which is the correct behaviour when nothing could be sourced.
        ctx.log(
            "no verifiable claims found — the script will be written without factual "
            "assertions rather than with invented ones",
            level="warning",
        )

    # The prompt block travels in the output so the script node needs no re-derivation.
    payload["prompt_block"] = result.prompt_block()
    return NodeResult(output=payload, credits=result.credits, provider=search.name)


@node_handler("voice_casting")
async def voice_casting_node(ctx: NodeContext) -> NodeResult:
    """Shortlist voices from the reference and render auditions. Gated.

    This node never selects a voice. It proposes, with reasons and samples, and stops
    — the voice is the most audible decision in the video and the operator has the
    strongest opinion about it, so a silent default would be the wrong kind of
    automation.
    """
    style_profile = (ctx.options.get("style_profile") or {})
    script = ctx.upstream_outputs.get("script") or {}
    brief = ctx.upstream_outputs.get("brief") or {}

    words_per_minute = None
    if script.get("word_count") and script.get("estimated_seconds"):
        seconds = float(script["estimated_seconds"])
        if seconds > 0:
            words_per_minute = float(script["word_count"]) / (seconds / 60)

    target = target_from_reference(
        style_profile,
        words_per_minute=words_per_minute,
        register=str(ctx.channel.style_profile.get("register") or ctx.channel.niche or ""),
        accent=str(ctx.params.get("accent") or ctx.channel.style_profile.get("accent") or ""),
    )

    candidates = shortlist(target, limit=int(ctx.params.get("shortlist") or 3))
    line = sample_line(script, brief, ctx.topic)

    candidates, sample_meta = await render_samples(
        candidates, line, ctx.path_for("auditions"), registry=ctx.registry
    )

    for candidate in candidates:
        if candidate.sample_path:
            path = Path(candidate.sample_path)
            if path.exists():
                ctx.emit_artifact(
                    "audio", path, "audio/mp4",
                    role="audition", voice=candidate.name, score=candidate.score,
                )

    for line_out in casting_summary(target, candidates):
        ctx.log(line_out)
    if sample_meta.get("placeholder"):
        ctx.log(sample_meta.get("note", "samples are placeholders"), level="warning")

    # Stop here if approving this gate cannot produce a narrator.
    #
    # The built-in roster describes voices and does not own them — no entry carries a
    # vendor id until an account is connected and synced. With no vendor and no channel
    # voice, this node still shortlists four names and still raises a gate, the operator
    # still picks one, and the run dies at `hook` two stages later with the script and
    # the thumbnail already paid for.
    #
    # That is the failure ARCHITECTURE.md's "gates must sit on the cheap stages" exists
    # to prevent, arriving through a gate rather than around one: a decision point that
    # cannot change the outcome is worse than no decision point, because it reads as
    # progress. Fail here, name the fix, and leave the auditions on disk so the reasons
    # are still there to read.
    usable = [c for c in candidates if c.voice_id]
    if not usable and not (ctx.channel.voice_id or str(ctx.params.get("voice_id") or "")):
        raise ProviderError(
            f"nothing here can narrate: {len(candidates)} voices were shortlisted and "
            "none is owned by a connected account. The built-in roster is a description "
            "of voices, not a source of them. Connect ElevenLabs or MiniMax in Settings "
            "and sync, or set this channel's voice, then start the run again — stopping "
            "now so the render is not paid for a video that cannot be narrated.",
            provider="voice",
        )

    # `selected` stays null. The gate's approval carries the operator's choice as an
    # override, and the voice node reads it from here.
    return NodeResult(
        output={
            "target": target.as_dict(),
            "candidates": [candidate.as_dict() for candidate in candidates],
            "sample_line": line,
            "samples": sample_meta,
            "selected": None,
            "selected_voice_id": None,
            "instruction": (
                "Listen to the auditions, then approve with "
                '{"selected": "<voice name>"} to cast it.'
            ),
        },
        credits=sample_meta.get("credits", 0) or 0,
        provider="local" if sample_meta.get("placeholder") else "elevenlabs",
    )


def _as_markdown(result) -> str:
    lines = [f"# Research — {result.topic}", ""]
    counts = result.as_dict()["counts"]
    lines.append(
        f"_{counts['claims_verified']} verified claims · "
        f"{counts['sources_fetched']}/{counts['sources']} sources fetched · "
        f"{counts['claims_rejected']} rejected_"
    )
    lines += ["", "## Queries", ""]
    lines += [f"- `{query}`" for query in result.queries]

    lines += ["", "## Verified claims", ""]
    if result.verified_claims:
        for index, claim in enumerate(result.verified_claims, start=1):
            lines.append(f"**[{index}]** ({claim.kind}, {claim.confidence}) {claim.text}")
            lines.append(f"> {claim.quote}")
            lines.append(f"— {claim.source_url}")
            lines.append("")
    else:
        lines += ["_None. The script must avoid factual assertions._", ""]

    if result.rejected_claims:
        lines += ["## Rejected", "",
                  "Claims whose supporting quote could not be found in the source:", ""]
        for entry in result.rejected_claims[:20]:
            lines.append(f"- {entry['text']} — _{entry['reason']}_")
        lines.append("")

    if result.open_questions:
        lines += ["## Unresolved", ""]
        lines += [f"- {question}" for question in result.open_questions]
        lines.append("")

    lines += ["## Sources", ""]
    for source in result.sources:
        state = "ok" if source.fetched else f"failed: {source.error}"
        lines.append(f"- [{source.title}]({source.url}) — {source.trust} trust, {state}")
    return "\n".join(lines)
