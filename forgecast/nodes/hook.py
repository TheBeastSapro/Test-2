"""The Hook Gate: watch the opening before buying the other eight minutes.

## Why this node exists

A run's order of spending is upside down relative to its order of risk. The script is
approved as *text*, and then the app buys a full voiceover and eighty generated clips —
and only at the end, watching the finished file, does anybody find out that the opening
does not land. By then the whole video is paid for.

Fifteen seconds is not an arbitrary window. It is where a viewer decides, and a video
whose first fifteen seconds fail does not get watched however good minute four is. So it
is the one part of a video worth seeing before the rest is commissioned.

## Why fifteen seconds is now only the *default* window

It was fifteen for every channel, and fifteen is where a viewer decides on a channel
nobody has measured. `vision.semantic` reads where a learned reference's opening beat
actually stops — the instant the narrator first pauses for longer than they pause inside
a beat — and a channel whose references stop at 3.2s was having its opening judged on five
times the video it opens with. That judged the setup as part of the hook, which is the one
thing this gate must not do: the failure it exists to catch is a slow open, and a window
that swallows the setup cannot tell a slow open from a normal one.

So the window is `style.editing.writing_budget`'s, which is the same function `nodes/content`
writes the script with and `graph/pipelines` reserves against. An unmeasured channel gets
fifteen seconds, exactly as before, and the gate says so.

## What the gate holds it against

The opening was previously judged against nothing at all — cut, surfaced, and approved on
a feeling. It now carries what the references do: how long their opening beat runs, how
fast it is read, and whether that is faster than the rest of their video. Those are
comparisons and never a verdict, because a verdict needs to know whether the promise
landed and nothing in a timing carries that. What the measurement declines to claim
travels with it, so "no hook type" reads as a refusal rather than as a finding.

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
from ..graph.pipelines import burns_captions
from ..providers import ProviderError
from ..render import ffmpeg as ff
from ..style.editing import HOOK_SECONDS, WritingBudget, writing_budget
from ._common import dimensions

# `HOOK_SECONDS` is imported rather than declared here: it is now the fallback half of a
# decision `writing_budget` makes, and a shipped default kept away from its override is the
# one that goes stale without anybody noticing. It is still the name this module's window
# is spelled with, so `hook.HOOK_SECONDS` reads as it always did.

# However short the opening scenes are, more than this is not a hook any more, it is the
# first act. The gate exists to be cheap; a "hook" running to forty seconds because the
# script opens with five short scenes is a gate that costs what it is guarding.
MAX_HOOK_SCENES = 4

# How far the written opening has to sit from the references' before the difference is
# worth a sentence at the gate. An opening length is a choice a creator makes within a
# range and not to a stopwatch, so their own references disagree by a third without
# meaning anything by it — and a gate that remarks on every run is one the operator stops
# reading, which costs more than a gate that says nothing.
NOTABLE_DRIFT = 0.35


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


def measured_against(budget: WritingBudget, *, seconds: float, words: int) -> dict:
    """What the opening the app just wrote looks like beside the ones it learned from.

    Comparisons, never a verdict. Whether a hook *works* is whether it made a promise the
    viewer wants kept, and nothing in a duration or a word rate carries that — which is
    why this returns sentences an operator can check against the clip in front of them
    rather than a score. The gate is still theirs; this is what they were previously
    asked to decide without.

    A channel with nothing learned gets one finding saying exactly that, rather than an
    empty block. An absent comparison that looks like a passed comparison is how a
    measurement stops being read.
    """
    rate = round(words / seconds, 2) if seconds > 0 else 0.0
    wrote = {"seconds": round(float(seconds), 2), "words": int(words),
             "words_per_second": rate}
    findings: list[str] = []
    learned = dict(budget.hook)

    if not budget.hook_measured:
        findings.append(
            f"nothing is measured about how this channel opens, so this is judged on the "
            f"shipped {budget.hook_seconds:.0f}s window with nothing to hold it against — "
            f"{budget.note}")
        return {"window_seconds": round(budget.hook_seconds, 2), "measured": False,
                "learned": learned, "wrote": wrote, "findings": findings,
                "note": budget.note}

    reference = float(learned.get("seconds") or 0.0)
    drift = (wrote["seconds"] - reference) / reference if reference > 0 else 0.0
    if drift > NOTABLE_DRIFT:
        findings.append(
            f"this opening runs {wrote['seconds']:.1f}s against references that stop "
            f"their opening beat at {reference:.1f}s — {drift:.0%} longer, which is the "
            f"slow open this gate exists to catch")
    elif drift < -NOTABLE_DRIFT:
        findings.append(
            f"this opening runs {wrote['seconds']:.1f}s against references that stop "
            f"their opening beat at {reference:.1f}s — {abs(drift):.0%} shorter, so it "
            f"has less room to make a promise than the references take")
    else:
        findings.append(
            f"this opening runs {wrote['seconds']:.1f}s, about the {reference:.1f}s the "
            f"references stop their opening beat at")

    reference_rate = float(learned.get("words_per_second") or 0.0)
    if reference_rate > 0 and rate > 0:
        change = (rate - reference_rate) / reference_rate
        if abs(change) > NOTABLE_DRIFT:
            findings.append(
                f"read at {rate:.1f} words a second against the references' "
                f"{reference_rate:.1f} — {'denser' if change > 0 else 'sparser'} than "
                f"this channel opens, and the voice cannot fix a word count")
    findings.append(learned.get("sentence", ""))

    return {"window_seconds": round(budget.hook_seconds, 2), "measured": True,
            "learned": learned, "wrote": wrote,
            "findings": [line for line in findings if line], "note": budget.note}


@node_handler("hook")
async def hook_node(ctx: NodeContext) -> NodeResult:
    """Narrate and cut the opening, then stop for approval."""
    script = ctx.output("script")
    scenes = script.get("scenes") or []
    if not scenes:
        raise ProviderError("cannot cut a hook from a script with no scenes")

    # How this channel opens, if anybody has measured it. The same call `script_node`
    # writes to and `graph.pipelines` reserves against, so the window this gate cuts is
    # the window the ledger paid for — see `style.editing.writing_budget`.
    budget = writing_budget((ctx.channel.style_profile or {}).get("narrative"))
    ctx.log(budget.note)

    opening = hook_scenes(scenes, seconds=budget.hook_seconds)
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
        mock=ctx.registry.mode == "mock",
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
        # Captioned exactly as the finished video will be, because the captions are part
        # of what is being judged: a hook that reads well and captions badly is a hook
        # that fails on the platform where most of it is watched muted.
        #
        # It was pinned on, which made the argument backwards on a channel measured as
        # caption-free. The operator approved an opening with a caption track, and the
        # render then produced one without — so the one frame they were shown to judge
        # was the one frame guaranteed not to match. A gate that previews something the
        # run will not make is worse than no preview.
        subtitles=burns_captions((ctx.channel.style_profile or {}).get("render_spec")),
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
        # What the opening was cut to, and what it looks like beside the references it was
        # supposed to be modelled on. Before this the gate surfaced a clip and a cost and
        # asked for a decision with nothing on the other side of the scales.
        "measured_against": measured_against(budget, seconds=length, words=words),
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
        f"cut a {length:.1f}s hook from {len(built)} scene(s), {words} words, against a "
        f"{budget.hook_seconds:.1f}s window — approving commits the remaining "
        f"{output['commits']['remaining_scenes']} scenes "
        f"({output['commits']['remaining_seconds']:.0f}s)"
    )
    for finding in output["measured_against"]["findings"]:
        # On the run log as well as in the output, because the output is read at the gate
        # and the log is where somebody looks afterwards to find out why a video opened
        # the way it did.
        ctx.log(finding)
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
