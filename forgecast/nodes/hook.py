"""The Hook Gate: watch the first fifteen seconds before buying the other eight minutes.

## Why this node exists

A run's order of spending is upside down relative to its order of risk. The script is
approved as *text*, and then the app buys a full voiceover and eighty generated clips —
and only at the end, watching the finished file, does anybody find out that the opening
does not land. By then the whole video is paid for.

Fifteen seconds is not an arbitrary window. It is where a viewer decides, and a video
whose first fifteen seconds fail does not get watched however good minute four is. So it
is the one part of a video worth seeing before the rest is commissioned.

## Why this is a separate gate from the Sample Gate, and not a duplicate of it

They ask different questions and neither answers the other's.

* **This gate asks whether the opening works** — the words, the voice, the pace, the
  first image. It is a question about the *script and the read*.
* **`nodes/sample.py` asks whether the look works** — grade, register, camera motion,
  whether faces melt. It is a question about the *generated video*.

A hook that reads badly is rewritten; a look that comes back wrong is re-prompted. Those
are different fixes made by different means, and a single gate mixing them would get
approved for one reason while the other went unexamined.

That division is also why this node uses **stills**, not image-to-video. Generated video
here would cost roughly ten times as much to answer a question stills already answer, and
it would answer the Sample Gate's question a second time — badly, on three shots.

## Why it sits where it does

Before `voice` and before `sample`, so that rejecting it saves both the full narration
and the whole batch. A hook gate placed after either is a gate that only ever saves the
cheaper half, which is most of the way to not having one.

`broll_plan` deliberately still runs on the script alone. Planning is free and costs
nothing to throw away, and having the shot list in hand makes the hook's rejection
cheaper to act on rather than more expensive.

## What it costs

About fifteen seconds of narration and two or three stills — on the order of a fiftieth
of what the run it gates will spend. The arithmetic is the same one that justifies the
Sample Gate, applied to a different failure.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from ..graph.engine import NodeContext, NodeResult, node_handler
from ..providers import ProviderError
from ..render import ffmpeg as ff
from ._common import dimensions

# The window a viewer decides in. Scenes are taken whole until this is covered rather
# than cut at exactly fifteen seconds — half a sentence tests nothing, and a hook judged
# on a truncated clause is judged on an artefact of the cut.
HOOK_SECONDS = 15.0

# However short the opening scenes are, more than this is not a hook any more, it is the
# first act. The gate exists to be cheap; a "hook" running to forty seconds because the
# script opens with five short scenes is a gate that costs what it is guarding.
MAX_HOOK_SCENES = 4


def hook_scenes(scenes: list[dict], *, seconds: float = HOOK_SECONDS) -> list[dict]:
    """The opening scenes that make up the hook, taken whole.

    At least one, always. A first scene longer than the window on its own *is* the hook —
    returning nothing there would skip the gate on exactly the script that most needs it,
    since a single opening scene running past fifteen seconds is a slow open and a slow
    open is the failure this gate is looking for.
    """
    taken: list[dict] = []
    running = 0.0
    for scene in scenes:
        taken.append(scene)
        running += float(scene.get("seconds") or 0.0)
        if running >= seconds or len(taken) >= MAX_HOOK_SCENES:
            break
    return taken


@node_handler("hook")
async def hook_node(ctx: NodeContext) -> NodeResult:
    """Narrate and cut the opening, then stop for approval."""
    script = ctx.output("script")
    scenes = script.get("scenes") or []
    if not scenes:
        raise ProviderError("cannot cut a hook from a script with no scenes")

    opening = hook_scenes(scenes)
    width, height = dimensions(ctx)
    fps = int(ctx.params.get("fps") or getattr(ctx.channel, "video_fps", 0) or 0) or None

    # The voice this channel actually cast, resolved the same way the full narration
    # resolves it. A hook read in a different voice from the video is a hook that
    # approves something nobody is going to hear.
    from .media import resolve_voice_id

    casting = ctx.upstream_outputs.get("voice_casting") or {}
    voice_id, note = resolve_voice_id(
        casting,
        channel_voice_id=ctx.channel.voice_id,
        param_voice_id=str(ctx.params.get("voice_id") or ""),
    )
    ctx.log(note)

    voice = ctx.registry.voice()
    speed = float(ctx.options.get("voice_speed") or 1.0)

    credits = 0
    provider = ""
    built: list[ff.Scene] = []
    audio_clips: list[Path] = []

    try:
        images = ctx.registry.image()
    except ProviderError as exc:
        # A hook with no picture still tests the words, the voice and the pace, which is
        # three of the four things this gate is for. Refusing outright would stop a run
        # that can still be judged on most of what matters.
        ctx.log(f"no image provider, so the hook will be cut over colour: {exc}",
                level="warning")
        images = None

    for scene in opening:
        index = int(scene.get("index", 0))
        narration = str(scene.get("narration") or "").strip()

        spoken = await voice.synthesize(
            narration,
            voice_id=voice_id,
            out_path=ctx.path_for(f"hook_{index:03d}"),
            speed=speed,
        )
        credits += spoken.credits
        provider = spoken.provider or provider
        audio_clips.append(spoken.path)

        still: Path | None = None
        if images is not None:
            prompt = str(scene.get("visual_prompt") or "").strip()
            try:
                made = await images.generate(
                    prompt or narration[:200],
                    out_path=ctx.path_for(f"hook_still_{index:03d}"),
                    width=width, height=height,
                )
                credits += made.credits
                still = made.path
                ctx.emit_artifact("image", made.path, made.mime, role="hook",
                                  scene_index=index)
            except ProviderError as exc:
                # One missing still is a colour card in one scene of a fifteen-second
                # clip. It is not worth failing a gate over, and the operator can see
                # for themselves which scene it was.
                ctx.log(f"hook still for scene {index} failed: {exc}", level="warning")

        built.append(ff.Scene(
            index=index,
            # The length the narration actually came out at, not the script's estimate.
            # A hook cut to the estimate has the picture change mid-word, which reads as
            # a fault in the edit rather than in the timing.
            seconds=round(float(spoken.duration_seconds), 3),
            visual_path=still,
            narration=narration,
            audio_path=spoken.path,
        ))

    workdir = ctx.path_for("cut").parent / "hook_build"
    workdir.mkdir(parents=True, exist_ok=True)

    narration_path = ctx.path_for("hook_narration.m4a")
    await asyncio.to_thread(_concat_audio, audio_clips, narration_path)

    out_path = ctx.path_for("hook.mp4")
    await asyncio.to_thread(
        ff.assemble_video,
        built,
        out_path,
        workdir=workdir,
        narration_path=narration_path,
        width=width, height=height, fps=fps,
        # Burned, because the captions are part of what is being judged: a hook that
        # reads well and captions badly is a hook that fails on the platform where most
        # of it is watched muted.
        subtitles=True,
    )
    length = await asyncio.to_thread(ff.ffprobe_duration, out_path)
    ctx.emit_artifact("video", out_path, "video/mp4", role="hook",
                      seconds=round(length, 2), scenes=len(built))

    words = sum(len(scene.narration.split()) for scene in built)
    output = {
        "hook_path": str(out_path),
        "seconds": round(length, 2),
        "scenes": [scene.index for scene in built],
        "words": words,
        # What proceeding commits to, so the approval is made against a number rather
        # than against a feeling. The same shape the Sample Gate surfaces, and for the
        # same reason: an approval with no cost beside it is a formality.
        "commits": {
            "remaining_scenes": max(0, len(scenes) - len(built)),
            "remaining_seconds": round(
                sum(float(s.get("seconds") or 0.0) for s in scenes[len(built):]), 1),
            "remaining_words": max(0, int(script.get("word_count") or 0) - words),
        },
        "title": script.get("title", ""),
    }

    readable = ctx.path_for("hook.json")
    readable.write_text(json.dumps(output, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    ctx.emit_artifact("json", readable, "application/json")

    ctx.log(
        f"cut a {length:.1f}s hook from {len(built)} scene(s), {words} words — "
        f"approving commits the remaining {output['commits']['remaining_scenes']} "
        f"scenes ({output['commits']['remaining_seconds']:.0f}s)"
    )
    return NodeResult(output=output, credits=credits, provider=provider)


def _concat_audio(clips: list[Path], out_path: Path) -> Path:
    """Join the hook's per-scene narration into one track.

    Its own copy rather than `media._concat_audio`, which is private to that module and
    belongs to a node this one runs before. Importing it would tie the cheap gate to the
    expensive stage it exists to precede, which is the coupling this file's placement in
    the graph is meant to avoid.
    """
    if not clips:
        raise ProviderError("no narration to join")
    if len(clips) == 1:
        return _single(clips[0], out_path)

    listing = out_path.with_suffix(".concat.txt")
    listing.write_text(
        "\n".join(f"file '{clip.resolve().as_posix()}'" for clip in clips),
        encoding="utf-8")
    ff.run_ffmpeg(
        ["-f", "concat", "-safe", "0", "-i", str(listing), *ff.ACODEC, str(out_path)],
        label="hook_concat_audio",
    )
    return out_path


def _single(clip: Path, out_path: Path) -> Path:
    """One scene's audio, re-encoded to the pipeline's settings.

    Re-encoded rather than copied because the rest of the render assumes one codec and
    one sample rate throughout, and a hook whose audio came straight from the vendor is
    the one file in the run that does not.
    """
    ff.run_ffmpeg(["-i", str(clip), *ff.ACODEC, str(out_path)], label="hook_audio")
    return out_path
