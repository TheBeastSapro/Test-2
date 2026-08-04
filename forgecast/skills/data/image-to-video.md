# Image-to-Video Prompting

> **Model reference — cost/strength notes, NOT a closed list.**
>
> A starting reference of i2v models known to work for these jobs, with per-second costs.
> It is **not the full set**: fal hosts more. There *is* a blessed default in this app —
> `DEFAULT_VIDEO_MODEL` — and it is the only one a render can currently use; see the note
> under the table. If a model is named that isn't here, or something else suits the shot
> better, **discover what's actually available and
> use it** — list fal's video models or fetch the provider docs. **Never say a model is
> unavailable just because it's absent from this table — verify first.**
>
> The authoritative list is `VIDEO_MODELS` in `forgecast/providers/media.py`, which
> carries a `PRICES_CHECKED` date. This table is a copy of it and copies go stale: it was
> once out by more than 3x in both directions, and the agent quoted those figures to the
> operator as fact. If the two disagree, the code is right.
>
> | Strengths | Model id | Cost / notes |
> |---|---|---|
> | B-roll, atmospheric, dialogue close-ups | `fal-ai/kling-video/v2.6/pro/image-to-video` | ~$0.07/sec. The default, and the reliable workhorse. |
> | The same at lower latency | `fal-ai/kling-video/v2.5-turbo/pro/image-to-video` | ~$0.07/sec. |
> | Dramatic camera moves, action, faces in motion | `fal-ai/kling-video/v3/pro/image-to-video` | ~$0.112/sec. |
> | High volume, budget (OS, Apache 2.0) | `fal-ai/wan/v2.2-a14b/image-to-video` | ~$0.08/sec. Cheaper per clip than per second suggests — it is not the cheapest option. |
> | Cheap fast commercial | `fal-ai/minimax/hailuo-2.3-fast/standard/image-to-video` | ~$0.032/sec. The cheapest here. |
> | Cheap, quick | `fal-ai/ltx-2.3/image-to-video` / `…/image-to-video/fast` | ~$0.06 and ~$0.04/sec. |
> | Audio gen / long-form coherence | `fal-ai/veo3/image-to-video` (~$0.20/sec, audio), `fal-ai/veo3/fast/image-to-video` (~$0.10/sec), `fal-ai/sora-2/image-to-video` (~$0.10/sec, coherence) | Premium edge cases. |
>
> **Which one a render actually uses.** Today: always the default, on every shot. The
> registry builds each provider as `cls(api_key)` (`providers/registry.py`), so
> `FalVideoProvider` takes its `DEFAULT_VIDEO_MODEL` and there is no per-shot, per-run or
> per-channel path to any other slug. Advice to "pick a model per shot" is therefore not
> actionable from this app yet — say so rather than promising it, and treat the table
> above as what a render would cost if the choice existed.
>
> **How to choose:** match the model to the shot — general B-roll, hero/dramatic,
> high-volume/cheap, or premium audio/coherence — weighing fidelity against per-second
> cost. Pick per shot, not per project, then lock to one or two models per project for
> visual consistency. Prices drift; re-check when it matters.

Image-to-video is the most expensive single operation in the pipeline — roughly $0.01 to
$0.50 per second of output. Getting it right in one or two tries is the difference between
profitable production and burning the wallet.

One rule outranks all others: **never run a full render without first surfacing one
complete sample — generated at the chosen model's shortest supported sample duration,
targeting about five seconds — and getting approval on the look and motion.**

## 1. The job of i2v

1. **Animate a still** with motion that fits the script and the storyboard's intent.
2. **Bridge keyframes into watchable footage** — music video, what-if shorts, news-hijack
   B-roll, history reenactments, ambient loops.
3. **Stay inside the locked visual style** — every clip must feel like the same channel.

A weak prompt produces stiff motion, melted faces, six fingers. A strong one produces
clean, contained motion that reads as cinematography rather than artifact.

## 2. Prompt structure

```
[SUBJECT] + [ACTION] + [CAMERA] + [LIGHTING] + [MOOD/STYLE] + [TECHNICAL]
```

- **Subject** (1-2 phrases). Concrete nouns. Not "a man" — "a 70-year-old grandmother in a
  beige cardigan, reading glasses on a chain".
- **Action** (1-2 phrases). Verbs are load-bearing. Not "doing something" — "slowly looks
  up from a letter, eyes widening, mouth tightening".
- **Camera** (1 phrase, technical). "static medium close-up", "slow push-in over 5
  seconds", "handheld tracking shot following subject left to right".
- **Lighting** (1 phrase). "warm golden hour from frame-right, soft fill from above",
  "low-key cinematic, single key light, dramatic falloff".
- **Mood/style** (1 phrase). "ominous calm before storm", "intimate, melancholy,
  lived-in", "frenetic urban energy".
- **Technical** (1-2 phrases). "16:9, 5 seconds, moderate camera motion, no cuts".

### Worked example

> A 70-year-old grandmother in a beige cardigan and reading glasses sits at a kitchen
> table reading a letter from the Social Security Administration, her face slowly shifting
> from confusion to alarm; static medium close-up at eye level; warm golden-hour light from
> frame-right window, soft fill, slight shadow under eyes; mood is intimate concern with
> hint of dread; 16:9, 5 seconds, minimal camera motion, no cuts.

Specific prompts hit the brand on the first try around 85% of the time. Vague ones, ~30%.

## 3. Motion language

### Verbs that work

Slowly + movement verb; subtle + adjective change; begins + movement; looks at / toward /
away; lifts / lowers / tilts; push in / pull out / pan / tilt.

### Verbs that fail

Runs, jumps, throws, fights (fast multi-limb action). Speaks/talks (lip sync unreliable —
use lip-closed shots and overlay audio). Disappears, vanishes, transforms. Multiplies,
splits, replicates. Generic "dance" ("ballet pirouette" works better).

### The motion intensity dial

- **Static** — barely moves. Most reliable, most cinematic for emotional shots.
- **Subtle** — small expression shifts, slow camera. Reliable.
- **Moderate** — full body movement, walking, turning. Mixed.
- **High** — running, fighting. Sparingly; expect re-renders.
- **Extreme** — flying, transforming. Unpredictable; better on stylized models than
  photoreal.

Always bias toward LOWER intensity than the storyboard implies. Static is the friend.
Cinema is mostly stillness.

## 4. The Sample Gate

The load-bearing safety rule. Never generate a full-cost render without first surfacing one
complete sample at the chosen model's shortest supported sample duration.

1. Storyboard approved.
2. Keyframe approved.
3. Prepare the i2v prompt for the chosen model.
4. Generate one complete sample at production resolution, at the model's shortest
   supported sample duration (~5s; 6s where that is the minimum). Generate at that
   duration directly — never render longer, surface a trimmed preview, then deliver the
   unreviewed remainder.
5. Surface the entire sample with the prompt visible: *"Here's the sample (the full 5-sec
   clip). Cost so far: $0.42. Render the full 8-second shot at $0.67 — a separate charge?
   Or revise the prompt?"*
6. Approve or revise.
7. Render full-length ONLY after explicit approval — a separate submission billed on its
   own `request_id`.

### What the sample tests

Does the motion match storyboard intent? Does the style match the channel profile? Obvious
artifacts (six fingers, melted faces, warped text)? Does the camera move read as
cinematic or jerky?

### Visual QA means viewing frames, not reading metadata

`ffprobe` reports container metadata — duration, codec, fps. It is NOT visual QA and never
satisfies sample review or clears a clip for assembly. Before describing any clip or
cutting it in:

1. **Map the clip to an approved narration or storyboard beat.** Write the beat next to the
   clip id. Atmospheric/transition beats are valid when the storyboard calls for them. A
   clip serving no approved beat is filler — cut or regenerate; never pad the timeline.
2. **Extract and view representative frames** (first / middle / last):
   ```bash
   ffmpeg -y -i clip.mp4 -frames:v 1 qa_first.png
   ffmpeg -y -ss 2.5 -i clip.mp4 -frames:v 1 qa_mid.png
   ffmpeg -y -sseof -0.2 -i clip.mp4 -frames:v 1 qa_last.png
   ```
   Then actually look at them.
3. **Reject and regenerate on sight of:** cartoonish rendering when the style is photoreal;
   loop-like motion (last frame ≈ first, no progress) unless a seamless loop was asked for;
   generic motion unrelated to the beat; a grade that breaks the locked style.

Describing a clip you have not visually inspected as "cohesive" or "cinematic" is a
contract violation, not optimism.

### When to skip the sample (rare)

Only when the shot is under 3 seconds, or style and motion are identical to a
previously-approved shot in the same project, or a no-sample mode was explicitly enabled
for the batch. **Never decide to skip on your own.** Calling a batch a "pilot", "proof
cut" or "sample reel" does not make it the sample — a multi-clip assembly is production
output. A general go-ahead to produce is NOT a waiver. The gate is one clip, surfaced
alone, approved on look and motion.

### Sample and full render bill separately

Each provider submission is separate billable work — on fal each has its own billed
`request_id`. The sample is not credited against the full render. Quote **sample + full
render** as two charges. A verified continuation endpoint may replace the full re-render
with a priced extension — then quote **sample + extension**, still two charges. Never
describe either as "rolled in" or "included in" the other.

When a batch has several distinct style/motion setups each needing their own sample,
surface the aggregate sample budget before starting.

## 5. Reference image use

The reference is at least as important as the prompt, often more.

- **Match the aspect ratio** of the target output.
- **Above 1024×576** for cinematic; 1080×1920 for vertical.
- **Single dominant subject** — multi-subject references confuse motion intent.
- **No text overlays** — the model will try to animate text and fail. Add text in post.
- **Match the lighting/grade** to the style lock.

The prompt instructs what to ANIMATE in the reference. So the reference shows the subject
at the START of the motion, and the prompt describes what happens NEXT. A reference already
showing the destination ("a man running through a doorway" + "the man runs through the
doorway") produces incoherent motion.

## 6. Seed locking

- **Lock** for: the same character across shots; re-rendering after a revision (so only
  the prompt change is tested); bulk generation with subtle variation.
- **Vary** for: the first sample of a new shot; when a locked seed produces artifacts (try
  3-4 and pick).

Protocol: first sample random; if approved, lock it for the full render; if revised, try
2-3 seeds before rewriting the prompt — random variation is often the cheap fix.

## 7. Aspect ratio

| Aspect | Use case |
|---|---|
| 16:9 | YouTube long-form |
| 9:16 | Vertical Shorts |
| 1:1 | Instagram crossposting |
| 4:3 | Retro / archival |
| 21:9 | Premium hero shots |

Long-form: always 16:9. Shorts: 9:16. Multi-platform: generate 16:9 and crop in post.

## 8. Anti-patterns

**Visual.** Six-finger/extra-limb (Sample Gate catches). Melted faces on fast motion —
lower intensity or upgrade the model. Warped text — never put text in the reference.
Background drift — lock seed, simpler backgrounds, shorter clips. Limb morphing on extreme
action — lower intensity or recut around it.

**Prompt.** Generic prompts. Conflicting instructions ("static shot, fast camera
movement"). Too many subjects. Pop-culture style references (often produce parody). Brand
names (content policy).

**Workflow.** Skipping the Sample Gate — the biggest budget burner. Mass-rendering before
testing one. Mixing models within a project. Re-prompting endlessly without changing seed.

## 9. Runtime checklist

**Before each submission:** storyboard shot exists with subject, action, camera, lighting,
mood, duration · style locked · keyframe approved · model selected per shot · reference
meets aspect/resolution/composition · prompt follows the skeleton · motion intensity biased
low · aspect matches platform · Sample Gate run with explicit approval before a full render
· cost surfaced pre-render · seed locked if repeating a shot type · each clip mapped to an
approved beat.

**After each result, before presenting or assembling:** representative frames extracted and
visually inspected — ffprobe alone is not QA · clip rejected/regenerated if cartoonish vs
locked style, loop-like, generic, or grade-mismatched.

If any check fails, regenerate or surface. Never bulk-render without sample approval.
