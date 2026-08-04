"""Text stages: production brief and full script.

Both sit behind approval gates because they are the cheapest place to change the
video. Rewriting a brief costs a few credits; rewriting after the shots are
generated costs hundreds.
"""

from __future__ import annotations

import json
from string import Template

from .. import scripting
from ..graph.engine import NodeContext, NodeResult, node_handler
from ..prompts import cast
from ..providers import ProviderError
from ..scripting.method import hook_shape
from ..style.editing import WORDS_PER_SECOND, writing_budget
from ._common import ask_json, request_payload, target_seconds

# `WORDS_PER_SECOND` is imported rather than declared: it is the rate a script is written
# at when nothing has been learned, and `style.editing.writing_budget` is what chooses
# between it and the channel's measured one. It stays a name in this module because
# `_normalise_scenes` needs a rate for a caller that has no channel in hand.

BRIEF_INSTRUCTIONS = """Produce a production brief for one video.

Return JSON with exactly these keys:
  working_title   string, under 70 characters, no clickbait the video cannot deliver
  angle           string, the specific claim or lens that makes this video worth making
  audience        string, who this is for
  hook            string, the first spoken sentence of the video
  promise         string, what the viewer will know by the end
  target_duration_seconds  integer, echo the requested duration
  beats           array of objects: {name, purpose, summary} — as many as the
                  cadence below asks for
  keywords        array of 4-8 search terms

Beats must be a real outline: each one advances the argument. Do not write
"introduction / body / conclusion"."""

# The rate is a `$placeholder` rather than a literal, and the reason is the one this
# file's own brief stage already learned the hard way. `2.6 words per second` was written
# into this paragraph while `_normalise_scenes` divided by a constant, and the moment a
# channel's measured rate reached one of them but not the other, the prompt would be two
# instructions that disagree — which `scripting.method` names precisely: the model resolves
# that by ignoring both. One rate, substituted into the sentence the writer reads and used
# by the arithmetic that checks them.
#
# `string.Template` rather than `str.format` because this text is full of braces — the JSON
# shapes it is describing — and a formatting pass over them raises at the top of a run.
SCRIPT_INSTRUCTIONS = Template("""Write the complete narration script from the approved brief.

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
  - `seconds` is the narration length at $rate words per second, rounded to 0.1.
  - Total narration must land within 10% of target_duration_seconds, which at that rate
    is about $words words of narration across the whole script.
  - Cover every beat from the brief, in order.""")


def scripting_block(ctx: NodeContext, seconds: int, *, only: tuple[str, ...] = ()) -> str:
    """The channel's scripting method, and a log line for anything wrong with it.

    Two things are reported here rather than swallowed, and both are the kind of failure
    that otherwise presents as "the writing got worse".

    A selection that no longer resolves — a renamed folder, a machine change — falls back
    to the house method inside `prompt_block`, so the run continues. Silently, though,
    the operator would see a run written to a method they did not choose with nothing
    anywhere saying so.

    And a style that loaded with warnings is the sixteen-documents-three-missing case: the
    style works, writes, and is quietly missing part of itself. The warnings belong in the
    run log because that is where somebody looks when a script came out wrong.
    """
    style = scripting.get(ctx.channel.scripting_style)
    if style is None:
        ctx.log(
            f"scripting style {ctx.channel.scripting_style!r} could not be loaded — "
            f"writing to the house method instead",
            level="warning",
        )
    else:
        for warning in style.warnings:
            ctx.log(f"scripting style {style.name}: {warning}", level="warning")
    return scripting.prompt_block(
        ctx.channel.scripting_style, target_seconds=seconds, only=only)


@node_handler("brief")
async def brief_node(ctx: NodeContext) -> NodeResult:
    seconds = target_seconds(ctx)
    payload = request_payload(ctx, target_duration_seconds=seconds)

    # The structural half only. A brief is a beat outline and no prose, so the ladder,
    # the loops and the joins are exactly what it has to obey — and the banned-phrase
    # list would be spending tokens on every run policing writing this stage does not
    # produce. Appended as a constraint rather than as background, for the reason the
    # research block is: an instruction the model may treat as context is one it drops
    # the moment the output gets long.
    instructions = (
        # The beat count comes from the cadence rather than from a literal in
        # BRIEF_INSTRUCTIONS. The two used to disagree for every video over about five
        # minutes — the instructions asked for "4-12" and the block appended two lines
        # later said "about 19 of them", and 900s asked for 36. `method.py`'s own
        # docstring names that failure: two instructions that disagree are resolved by
        # ignoring both.
        f"{BRIEF_INSTRUCTIONS}\n\n"
        f"{scripting_block(ctx, seconds, only=scripting.STRUCTURE_IDS)}"
    )

    data, credits, provider = await ask_json(
        ctx,
        role="Write a production brief that makes the video specific instead of generic.",
        schema_name="brief",
        payload=payload,
        instructions=instructions,
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

    # How fast this channel's own references talk, and where their opening beat stops.
    # This is the number that turns "eight minutes" into a word count, and it was 2.6 for
    # every channel — a documentary's pace handed to a shorts creator who says four words
    # a second, which comes back a third short and gets padded by the model. The same call
    # `graph.pipelines` reserves against and `nodes.hook` cuts the opening to.
    budget = writing_budget((ctx.channel.style_profile or {}).get("narrative"))
    ctx.log(budget.note)

    # The channel's scripting method, in full: this is the stage that writes sentences,
    # so the banned constructions and the rotation banks apply here as well as the
    # structure. Appended as a hard constraint for the same reason the research block
    # below is — a method offered as background is a method the model agrees with and
    # then does not follow.
    instructions = (
        f"{SCRIPT_INSTRUCTIONS.safe_substitute(rate=f'{budget.words_per_second:.2f}', words=budget.words_for(seconds))}"
        f"\n\n{scripting_block(ctx, seconds)}"
    )

    # How this channel opens, when a reference has been measured — the length and the pace
    # of its first beat, which is the one thing about the script the Hook Gate downstream
    # then judges it on. Empty for an unmeasured channel rather than a paragraph of
    # hedging: an instruction that says there is no measurement spends tokens telling the
    # model to ignore it, and a model told to ignore one numbered rule reads the rest as
    # negotiable.
    opening = hook_shape(budget.hook)
    if opening:
        instructions = f"{instructions}\n\n{opening}"

    # The cast comes out of this call rather than a second one. The stage that wrote the
    # script has the whole script in front of it and knows who recurs; asking again later
    # is a second paid round trip to re-read what was just written, and it would be
    # re-reading a summary rather than the reasoning that produced it.
    instructions = f"{instructions}\n\n{cast.SCRIPT_INSTRUCTION}"

    # Research, when the pipeline ran it, is appended as a hard constraint rather than
    # background reading: it names exactly which facts are available and forbids the
    # rest. Without it the house rule against inventing statistics has nothing to
    # stand on, because a documentary script with no sources will manufacture them.
    research = ctx.upstream_outputs.get("research") or {}
    if research.get("prompt_block"):
        instructions = f"{instructions}\n\n{research['prompt_block']}"

    data, credits, provider = await ask_json(
        ctx,
        role="Write the full narration script.",
        schema_name="script",
        payload=payload,
        instructions=instructions,
        max_tokens=16384,
        temperature=0.8,
    )

    scenes = _normalise_scenes(data.get("scenes"), rate=budget.words_per_second)
    data["scenes"] = scenes

    # Who has to look the same in every shot they appear in. Built here rather than in
    # the shot planner because it is a fact about the script, and because the planner is
    # downstream of a gate: an operator revising a script must see the cast change with
    # it, not discover afterwards that the person they renamed is now two people.
    company = cast.build(data.get("cast"), scenes)
    data["cast"] = company.as_dict()
    for member in company.characters:
        thin = cast.thin_description(member.description)
        if thin:
            # Warned, never rewritten. A weak likeness is the planner's failure and the
            # operator's decision — silently padding it would invent a face nobody chose
            # and then lock every shot to it.
            ctx.log(f"{member.name} is locked on a weak description: {thin}",
                    level="warning")
    if company:
        ctx.log(f"cast locked: {len(company.characters)} recurring "
                f"{'face' if len(company.characters) == 1 else 'faces'} across "
                f"{sum(one.appearances for one in company.characters)} shots")
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


def _normalise_scenes(raw, *, rate: float = WORDS_PER_SECOND) -> list[dict]:
    """The scenes as the rest of the run reads them, timed at this channel's own rate.

    `rate` defaults to the shipped figure so a caller with no channel in hand — a test, a
    tool re-reading a stored script — gets the arithmetic the app has always done. It is a
    parameter and not a lookup because a scene length derived from a different rate than
    the prompt asked for is the disagreement the prompt's own `$rate` exists to prevent,
    one stage later and invisible.
    """
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
        computed = words / (rate or WORDS_PER_SECOND)
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

    # The cast, above the scenes, because this document is what the script gate shows and
    # a locked likeness is part of what is being approved. A description nobody read is a
    # face that turns up identical in eighty shots and wrong in all of them — and the
    # script gate is the last point where changing it costs nothing.
    company = (script.get("cast") or {}).get("characters") or []
    if company:
        lines += ["## Cast", "",
                  "_These people appear in more than one shot and are locked to one "
                  "description, used word for word in every prompt they are in._", ""]
        for member in company:
            where = ", ".join(str(index + 1) for index in member.get("scenes", []))
            lines.append(f"- **{member.get('name', '?')}** — {member.get('description', '')}")
            lines.append(f"  <br>_scenes {where}_")
        walk_ons = (script.get("cast") or {}).get("walk_ons") or []
        if walk_ons:
            lines += ["", f"_Appearing once, so not locked: {', '.join(walk_ons)}._"]
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
