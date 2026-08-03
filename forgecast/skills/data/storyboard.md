# Storyboard / Scene Breakdown

Two rules outrank the rest.

**Storyboard only when called upon.** Talking-head channels do not need one. Documentary
explainers need a light one. Music videos, what-if shorts, ambient channels and
visual-narrative pipelines need a full one.

**Never start generating images or clips without locking the style with the operator.**
Generating twenty keyframes they hate is a failure prevented by sample-then-confirm at every
commit gate.

## What a storyboard does

Translates the script into visual shot intent that image and i2v models can execute · locks
visual continuity so the channel's brand stays coherent · surfaces decisions while they are
cheap (text and references) rather than expensive (full renders) · gives the editor the map
for cut timing, music sync and beat-locked pacing.

A weak storyboard is "show a guy in a suit". A strong one is a shot record: subject, action,
camera framing, lighting, grade, duration, transition, audio note.

## When to storyboard, when to skip

**Skip** for: a talking-head channel with a locked host (the shot *is* the host; cuts are
transitions between motion graphics) · documentary with stock B-roll needing no shot-level
direction · reaction / commentary / vlog · long-form unscripted · ambient loops with one
sustained scene.

**Storyboard** for: music video / propaganda / drill (every bar gets a visual decision) ·
what-if shorts and scene cascades · B-roll-heavy news-hijack documentary · history and
explainer with visual reenactment · ad or sponsor read with visual treatment · channel
trailers · anything where the visuals are the product rather than a wrapper for narration.

**Decision flow.** Read the script → determine the dominant visual mode (locked-host,
narration + B-roll, scene-cascade, music-video, ambient) → locked-host: no storyboard, go to
motion graphics · narration + B-roll: light storyboard, B-roll list only · scene-cascade or
music video: full storyboard · ambient: no storyboard, one scene description.

Surface the decision first: *"This reads as a music-video format. I'd recommend a full
shot-by-shot storyboard before we generate any visuals, so you can approve the look before we
spend on renders. Want me to produce it?"*

## The four depths — default is medium

**Light (~5 min).** A B-roll list, one line per visual moment.
```
[00:30] B-roll — historical photograph of pre-1929 stock exchange
[01:15] B-roll — modern bank vault, shallow focus
```

**Medium (~15 min) — DEFAULT.** A structured shot list, text only, no keyframes yet.
```
Shot 03 — 0:24 to 0:31 (7 seconds)
Subject: aerial drone shot of empty Manhattan skyline at dawn
Action: camera slowly pushes forward, slight downward tilt
Framing: wide establishing shot
Lighting: golden hour, low sun from frame-right
Mood: melancholy, pre-storm
Transition out: slow cross-fade
Audio note: ambient wind, no music yet
```

**Deep (~45 min).** Medium plus a reference keyframe per scene, reviewed before any video
generation.

**Production (2-4 h).** Deep plus full style locking and a sample i2v render approved before
production. One sample approval clears only the shots sharing its approved style **and**
motion; each different motion or camera setup is sampled, or explicitly waived, on its own.

## The four commit gates

**Gate 1 — Style lock, before storyboarding.** Confirm or propose the visual style profile
before writing a single shot. Pull from the channel profile if one exists, otherwise ask.

**Gate 2 — Storyboard text approval, before any keyframe.** *"Here are 18 shots planned. Read
through, tell me anything that feels off. Once locked, I'll generate keyframes."*

**Gate 3 — Sample keyframe approval, before all keyframes.** Even after the storyboard is
approved, generate ONE keyframe — Shot 1 or the most visually defining shot. *"Here's the
look. Approve to generate the remaining 17, or tell me what to change."*

**Gate 4 — Sample i2v approval, before all i2v renders.** Render ONE complete sample of the
most motion-defining shot at the model's shortest supported duration and surface the whole
clip. Approval clears only shots sharing that sample's approved style **and** motion. Surface
the aggregate sample budget across the distinct setups before starting the batch. This is the
most expensive gate to skip.

Any gate producing a no means regenerate and re-surface. Never proceed without explicit
approval. Cost protection and quality protection in one.

## Style locking — the prerequisite

**Path A.** A channel profile already exists (3+ videos shipped). Load its visual style DNA.

**Path B.** A reference channel is named. Ingest it, pull the style DNA, apply anchor
differentiation, surface the proposal, lock on approval.

**Path C.** No profile, no reference. Infer from niche convention, surface 2-3 proposals with
sample references, let the operator pick.

Never storyboard from a vague style. *"Cinematic" is not a style. "Warm sepia, single key
light, rule-of-thirds composition, slow cuts" is a style.*

## Beat extraction — script to shots

Read the full script → identify natural beat boundaries (topic shifts, the sentence that
introduces a new idea, rhetorical pauses, "and then…" transitions) → estimate a timestamp per
beat at ~150 wpm → allocate one shot per beat, except that beats over 15s get 2-3 shots and
beats under 3s may share a shot → surface the beat-shot map before generating keyframes.

For lyrics: each bar is 4 beats; default one shot per 4-8 bars; hook lines get reusable shots;
drops get distinct visuals.

## Controlled vocabulary

**Framing.** XCU (eyes, object detail) · CU (face, hand and prop) · MCU (head and shoulders)
· MS (waist up) · WS (full body, room) · EWS (landscape, scale) · insert (document, prop) ·
aerial/drone · POV · OTS.

**Movement.** Static · pan · tilt · push in / pull out · dolly · tracking · crane · whip pan
· arc.

**Lighting.** High-key · low-key · three-point · available/natural · practical (visible
sources in frame) · silhouette · underlit · colour-keyed.

**Grade.** Warm sepia · cool cinematic · clinical bright · saturated pop · muted documentary
· desaturated grit · film noir · neon.

**Transitions.** Hard cut · match cut · cross-fade · whip pan · wipe · smash cut · dissolve.

Use these terms so the i2v model interprets the intent correctly.

## Duration maths

**Music video.** 4 beats = 1 bar. Bar seconds = 60 / BPM × 4. At 136 BPM a bar is 1.76s.
Standard shot 4-8 bars (7-14s); very fast cuts 1-2 bars (1.7-3.5s); sustained sections 8-16
bars (14-28s). A 3-minute drill track is typically 40-70 shots.

**Narration.** Standard B-roll cut 3-5s (one sentence) · cinematic establishing 7-10s · fast
punctuation 1-2s · avoid under 1s unless the fast-cut read is deliberate.

**i2v constraints.** Most models cap at 5-10s per generation. A shot over 10s needs two
generations stitched, or one sustained camera move, or a cut to a different shot type at the
10s mark. Factor the model's cap into the duration decision.

## Niche approaches

**Music video / drill / propaganda.** Beat-locked timing — at 136 BPM a beat lands every
441ms and shots span 4-8 beats. Hook return means visual return: every chorus reuses or echoes
the same treatment, which is how the track builds visual identity. Verse 2 escalates verse 1 —
same world, more action, faster cuts. The bridge is a visual reset, then back to the chorus
register. The outro is one sustained image or a slow zoom out.

**What-if shorts / vertical.** 9:16 mandatory. Each line of dialogue gets one visual decision.
Hook visual inside 0:00-0:03, before the scroll. Typically 8-15 shots for 60-90s.

**News-hijack documentary.** B-roll heavy, not a full storyboard — narration carries the
structure. Record where document and screenshot evidence appears. Full storyboard only for the
cinematic interludes at major reveals.

**History / explainer.** Mid-tier shot count. Narration spine, with key historical moments
getting full visualisation. Map and chart sequences scripted shot-by-shot. Photo restorations
get keyframes.

**Ambient / sleep / focus.** One sustained scene, style lock only. The "shot" is a concept:
"rainy library at night, candles, slow tilt over two hours."

## Anti-patterns

1. **Storyboarding talking-head content** — the shot is the host. Skip it.
2. **Skipping the style lock** — keyframes before style approval means regenerating them all.
3. **Generating all keyframes before a sample** — quality varies per keyframe even with the
   style locked.
4. **Vague shot descriptions** — always specify framing, lighting, mood, duration.
5. **Beat misalignment** — always maths-check against BPM.
6. **Forgetting the hook return** — don't generate fresh visuals every chorus.
7. **Over-cutting** — over ~30 cuts/min in non-music content reads frenetic; under 6 reads
   dull. Target the niche convention.
8. **Style drift mid-storyboard** — the lock applies to every shot unless a shift is
   structural (a bridge).
9. **Ignoring i2v duration limits** — don't storyboard 20s sustained shots against a 10s cap.
10. **Skipping the approval log** — without a record of each gate there is no clean rollback.

## Checklist

Storyboard need decided · style locked at Gate 1 with approval · shot list written at the
chosen depth · beat maths validated · shot list approved at Gate 2 · sample keyframe approved
at Gate 3 · sample i2v approved at Gate 4 (production depth) · all shots inside the model's
duration limits · transitions plan locked · approval log timestamped at every gate.
