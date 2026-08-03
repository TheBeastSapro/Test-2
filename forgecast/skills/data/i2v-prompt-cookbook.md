# i2v Prompt Cookbook

Runtime companion to the Image-to-Video skill, which covers model selection, the
SUBJECT+ACTION+CAMERA+LIGHTING+MOOD+TECHNICAL skeleton, and motion-verb principles. This
one carries the shot-type templates, the per-model fingerprints, the full verb bank, and
the anti-pattern diagnoses.

Most i2v prompts collapse for one reason: every shot gets treated as a generic "subject
doing thing in a place". Real video work has 8-10 recurring shot types, and each has a
prompt shape that produces clean output. Identify the shot type FIRST, load the template,
then customise. A locked template cuts prompt iteration by 60-70%, reduces style variance
within a video, and makes the Sample Gate cheaper because failures cluster around
predictable modes.

## Shot types

### 1 — Establishing exterior
Opens a scene, sets location and tone. Slow push-in or truck-right, 4-5s.

> [Exterior location, season, time of day]; [environmental detail in motion — flag, leaves,
> traffic, smoke]; slow [push-in / truck-right] over 5 seconds; [lighting matched to mood];
> [mood phrase]; 16:9, 5 seconds, moderate camera motion, no cuts.

**Example.** A small one-story brick house on a quiet residential street in suburban
Cincinnati, late autumn, fallen leaves drifting across the front lawn in a slow breeze, an
American flag on the porch swaying gently; slow push-in over 5 seconds; warm
late-afternoon golden hour from frame-right, long shadows; mood is quiet domestic
vulnerability; 16:9, 5 seconds, moderate camera motion, no cuts.

**Failure mode.** Models hallucinate weather changes mid-clip. Lock the weather in the
lighting field — if you say "overcast", do not also say "shafts of sun".

### 2 — Hook close-up (face-centric)
The beat-1 hook. Carries most of the click pay-off. Static; micro-expressions are the
motion. 4-6s.

> [Subject with age, attire, micro-detail]; [single action: looks up / sets down / opens /
> reads]; [secondary micro-expression: eyes widening, jaw tightening]; static medium
> close-up at eye level; [specific lighting]; [intimate / weighted / urgent mood]; 16:9, 5
> seconds, minimal camera motion, no cuts.

**Example.** A 47-year-old woman in a soft cream sweater in a study with bookshelves
blurred behind; slowly closes a manila folder, pauses, looks just past the camera; static
medium close-up at eye level; weighted soft warm key from camera-left, deep shadow on the
right side of the face; mood is reluctant witness gravity; 16:9, 6 seconds, minimal camera
motion, no cuts.

**Failure mode.** Adding a camera move to a hook close-up is the single most common error.
The face is the motion. Lock the camera.

### 3 — Mechanism diagram / explainer
Makes the abstract concrete. Slow orbit or static reveal, 5-8s.

> [Physical metaphor — book opening, lock turning, folder filling, water through pipes,
> dominoes falling]; [orbit / push-in / top-down]; [studio clean or single dramatic key];
> [methodical, inevitable, mechanical]; 16:9, [duration] seconds, smooth camera motion.

**Example.** A photoreal close-up of an old wooden file cabinet drawer slowly sliding open,
revealing rows of beige folders with handwritten date tabs, a single hand pulling out one
labelled "1997" and laying it flat; slow push-in following the folder, settling on the open
file; warm desk-lamp key, deep shadow in the cabinet; mood is methodical, inevitable; 16:9,
6 seconds, smooth camera motion, no cuts.

**Failure mode.** On-screen text warps. Use icons or colour-coding, add text in post.

### 4 — Composite case / patient story
The named case visualised. Slight push-in or observational handheld, 5-8s.

> [Named composite subject with age, profession-suggesting attire, location-suggesting
> backdrop]; [domestic action that visualises their situation — making tea, sorting mail,
> looking out a window]; [push-in OR observational handheld]; [warm intimate or cool
> detached]; [mood matched to their point in the arc]; 16:9, [duration] seconds.

**Failure mode.** Do not over-specify physical features — height, weight, exact eye colour
confuse the model. Give an age range, attire, and one defining detail.

### 5 — Authority intro / expert reveal
Host or expert on screen. Static or very subtle push-in, 3-5s.

> [Authority subject with profession-suggesting attire]; [neutral confident action: settles
> into chair, opens a folder, looks at camera]; static or very slow push-in; [three-point or
> window-key]; [calm authoritative mood]; 16:9, 4 seconds, minimal motion.

**Failure mode.** Animated background graphics pull focus. Keep backgrounds blurred and
physical.

### 6 — Static B-roll cutaway
Supports the narration at a retention valley. Very slight or no motion, 3-4s.

> [Single object or scene supporting the current narration]; [very subtle motion: leaves
> rustling, water dripping, paper turning, smoke rising]; [static or imperceptible
> push-in]; [lighting matched to scene]; [atmospheric, supportive]; 16:9, 3 seconds.

**Failure mode.** A B-roll prompt that introduces a person becomes a hero shot. Keep the
subject a single object and the motion microscopic.

### 7 — Transition / passage of time
Visual punctuation between beats. Sweep, whip-pan, or environmental change, 2-3s.

> [Environmental element representing time passing — sun across a wall, clock hands,
> calendar pages, sky shifting]; [sweep / time-lapse / whip pan]; [lighting shifting across
> the duration]; [time passing, forward momentum]; 16:9, [duration] seconds, fast camera
> motion acceptable.

**Failure mode.** Whip-pans across people melt faces. Pan across architecture,
environments or static objects.

### 8 — Action / dramatic moment
The "and then it happened" visual. Dynamic camera, 4-6s.

> [Subject in motion or about to break stillness]; [ONE dramatic action verb: collapses /
> surges / shatters / opens]; [matched camera motion]; [low-key, single key, hard shadow];
> [urgent mood]; 16:9, [duration] seconds.

**Failure mode.** Multiple action verbs melt. "Reaches for the phone, picks it up, dials"
melts; "picks up the phone" works.

### 9 — Number / dollar / data reveal
Beat-7 list visualisation, usually paired with a text overlay added in code. Static, 3-4s.

> [Physical metaphor for the number — stack of bills, calendar pages, folders, pills, days
> marked off]; [subtle motion: bill flipping, page turning]; static or imperceptible
> push-in; [bright clean lighting]; [factual, weighted]; 16:9, 3 seconds.

**Failure mode.** Rendering the actual digits produces garbled numbers. Reveal the
metaphor; add the number in code.

### 10 — Beat-locked music video shot
Duration is exactly the bar length (often 3.5-4s at 130-145 BPM).

> [Stylized scene with locked aesthetic]; [single beat-locked action]; [locked
> composition]; [genre-specific dramatic lighting]; [aggressive / defiant / triumphant];
> [aspect]; [exact bar duration].

**Failure mode.** Beat-locking needs precise duration. A 3.7s clip against a 3.5s bar feels
off. Generate at exact bar duration.

## Per-model fingerprints

| Model | Fingerprint | Excels at | Breaks on |
|---|---|---|---|
| Kling Standard | Cinematic generalist, smooth camera | Establishing, dialogue close-ups, slow moves | Fast action, multi-subject, frame-filling text |
| Kling Pro | Premium face fidelity | Hook close-ups, named-character shots | Complex environments behind faces, >8s |
| Kling Master | Highest in family | Trailers, recaps, hero shots | Cost — use sparingly |
| Hailuo | Cheap stylized workhorse | B-roll, atmospheric, music video at scale | Photoreal humans (slightly waxy), tight motion control |
| Veo | Realism specialist, strong physics | Water, smoke, fire, realistic camera, science viz | Stylized aesthetics (realism gravity), <4s |
| Sora | Cinematic premium | Long durations, complex multi-subject, dramatic establishing | Cost, queue times, restrictive policy |
| LTX | Volume workhorse, pass-through compute | 50+ clip music videos, stylized, high-volume B-roll | Photoreal humans, self-hosting complexity |

**Tuning notes.** Spend on Kling Pro only when a face is dominant — downgrade B-roll to
Hailuo or LTX. Do not fight Veo's realism gravity with stylized prompts. Don't put faces
in the centre of a Hailuo frame; lean into its texture.

### Selection matrix

| Shot type | Default | Why |
|---|---|---|
| Establishing exterior | Kling Standard | Cinematic, cost-efficient |
| Hook close-up | Kling Pro | Face fidelity is load-bearing |
| Mechanism diagram | Veo Fast | Physics realism |
| Composite case | Kling Pro | Named character needs a strong face |
| Authority intro | Kling Pro / Veo Fast | Subject is host or expert |
| Static B-roll | Hailuo | Cheap, motion is microscopic |
| Transition | Hailuo | Short, low-stakes |
| Action / dramatic | Kling Pro / Veo | Motion and face both matter |
| Number / data reveal | Kling Standard | Static physical metaphor |
| Music video shot | LTX | Volume plus stylized aesthetic |

## Motion verb bank

**Clean — reliable ~90%+ across models.** Looks up / down / at · slowly turns · sets down /
picks up · reads / writes / signs · walks slowly toward / away from · sits / stands · opens
/ closes · pours · nods / shakes head · furrows brow / raises eyebrow / closes eyes ·
drifts / floats / hovers · glances · pauses / hesitates · reaches for (stop there — "reaches
for and grabs" doubles the verb).

**Risky — single subject, single direction, clear duration only.** Runs (lock the
direction) · throws (single object) · drives (static car, motion-blur background) · falls
(single object, linear trajectory) · crashes (into stationary objects) · smiles (slight
only) · cries (single tear) · argues / yells (one person) · dances (slow) · flies (objects,
not people) · cooks (one steady action).

**Forbidden — almost always melt.** Fights · kisses · hugs · plays sports · performs
surgery · operates machinery · writes paragraphs · cuts hair / shaves · climbs · swims ·
jumps · complex choreography.

Note that "falls" works while "jumps" melts: gravity plus body is fine, push-off plus
gravity plus body is not.

**Stacking rules.** One verb per prompt — "walks to the door, opens it, steps outside" is
three actions; the model picks one and melts the rest. Chaining with "then" rarely helps;
split into two clips. Background verbs are free: "a man reads a letter while leaves drift
past the window" — "reads" is focal, "drift" is environmental motion handled separately.

**Camera verbs.** Push-in, pull-back, truck-left/right, tilt-up/down: clean.
Pan-left/right: clean for environments, risky for faces. Orbit/arc: single subjects only.
Whip-pan: architecture only, never people. Handheld: realism with slight distortion risk.
Locked/static: safest, and the default for face shots.

## Anti-pattern diagnoses

1. **Multi-action.** *"Walks to the door, opens it, steps outside, and waves."* Four verbs;
   the model picks one and melts the others. Split into 2-3 clips.
2. **Conflicting conditions.** *"Overcast January afternoon with shafts of bright sunlight."*
   Mutually exclusive, so the model alternates and the lighting flickers. Pick one.
3. **Frame-filling text.** *"…the words 'YOUR BENEFITS HAVE BEEN REDIRECTED' clearly
   visible."* Letters warp, kerning collapses. Generate a blank document; add text in code.
4. **Generic everything.** *"A man at a desk doing finance stuff in an office."* Every field
   generic, so the output feels like a stock image. Anchor every field.
5. **Camera move on a face shot.** *"Static close-up… camera does a slow orbit."* Orbiting a
   face distorts it. Lock the camera, or orbit the environment and end on the subject.
6. **Stylized prompt to a photoreal model.** Veo has realism gravity and pulls stylized
   prompts halfway, producing half-real confusion. Match model to register.

## Runtime workflow

1. Identify the shot type from the storyboard; match one of the ten above.
2. Pull that template.
3. Pick the model from the fingerprint table.
4. Customise SUBJECT and ACTION with topic specifics.
5. Verify the motion verb is in the clean tier.
6. Verify one focal verb — background motion is allowed.
7. Verify no contradicting environmental conditions.
8. Verify no on-screen text is requested.
9. Run the Sample Gate: one sample for this style-and-motion setup, surfaced alone,
   explicit approval on look and motion.
10. Generate only the shots sharing that approved style **and** motion. A different motion,
    grade, or framing needs its own sample. Style looking consistent is not enough — motion
    must match too.
