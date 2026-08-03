# The method

Every rule here was added because a render was measurably wrong, and the
measurement said why. They are in the order they cost time to learn, which is
also roughly the order they matter.

The reference project throughout is one 13-minute animated explainer with dense
narration (93% voiced, no pause longer than 0.40 s), ~600 cues, mastered to
−14 LUFS.

---

## 1. Diagnose by measuring, never by ear

Sync was "fixed" twice in the wrong direction by guessing before
`sync_check.py --by-tier` existed. Two rules follow:

- **Read the per-tier breakdown, not the headline.** The overall number only ever
  says "scattered". The per-tier view says *which* tier and by how much, and the
  error turned out to track each category's rise time almost exactly.
- **Measure levels on the stems, not the master.** See §5.

## 2. Density and variety — what "sounds cheap" actually means

A first pass placed 474 cues drawn from **seven files**. One tick played **240
times**; a whoosh 148. Thirteen minutes is long enough for the ear to learn a
sample and then hear the seam instead of the picture.

```python
collections.Counter(os.path.basename(c["asset"]) for c in cues["sfx_cues"]).most_common(5)
```

Rule of thumb: **no file more than ~10 times in 13 minutes, and never twice
inside 30 seconds.** That needs a real palette (~80–110 files across categories),
not a keyword search per cue.

Density has a measurable ceiling too. That same render produced **723 onsets for
474 cues, and 148 cues never matched an onset at all** — more onsets than cues
means tails are overlapping into false attacks; unmatched cues mean hits are
burying each other. One cue per 1.5 s was too many; **~2.2 s with a per-tier
guard** kept everything meaningful and audible.

Resolve collisions **by priority, not by strength** — a caption tick must never
elbow a strike. Hand-timed beats are exempt from the guard *against each other*,
because a title card is deliberately a whoosh leading into a boom 0.4 s later.

## 3. Effects sit ABOVE the bed

That render's effects bus peaked at **−23.7 dB** against a −13 dB music bed, so
everything sat under the music and whole minutes read as having *no* effects. The
bed is the thing that gets out of the way. See `house.py` for the tier table.

**Normalise the palette before placing anything.** Across 81 library files the
peak spread was **15 dB** (+12.3 to −2.8 dB of correction). Without that pass the
tier table means nothing.

## 4. Anchoring — place the *perceived* moment, not the first sample

The single biggest sync lesson, and it took five renders because each fix exposed
the next. Per-tier error tracked rise time almost exactly:

| tier | rise to 15% of energy | measured sync error |
|---|---|---|
| pop | 2 ms | +3.0 ms |
| impact | 28 ms | −10.2 ms |
| swish | 93 ms | +39 ms |
| whoosh | 411 ms | +28 ms |

The rule that works, in order:

1. **Trim leading silence once, at palette prep.** Never *also* run a per-render
   transient search — doing both compensates twice and threw whooshes 300 ms early.
2. **Store a per-file anchor**: where the first 15% of the file's energy has
   accumulated. Per *file*, not per category — the spread inside a category is
   what makes the p90.
3. **Zero the anchor for anything front-loaded** (≥40% of peak level in the first
   30 ms). If it starts with a bang, the bang *is* the moment. This finally fixed
   title-card booms, which sat 59 ms early through two earlier rounds because a
   boom is a transient followed by a long sub tail.
4. **Subtract a one-frame deadband** from the rest. Only rise beyond a frame is
   real ramp.
5. **Cast beats that must hit a mark with front-loaded files.** A swell cannot land
   on a frame. Two of six boom files were swells; using them on cards was a
   casting error, not a timing one.

**Metrics that measure worse — don't repeat them:**

- *Time to 60% of peak* breaks on any multi-hit file. Across five blacksmith files
  it locked onto the loudest **late** hammer strike: median 749 ms where energy
  accumulation finds the first strike at 127 ms.
- *Steepest envelope rise* finds later swells: 203 ms for pops (vs 17) and 492 ms
  for multi-hit files (vs 127).

**Do not chase the whoosh number.** A 400 ms ramp has no well-defined onset:
measured against the cue its p90 is 212 ms, and measured against the file's own
start it is *worse* at 265 ms, while its median is −8 ms. Overall
"within one frame" settling near 75% is the expected result, not a defect.

## 5. Calibrate the bed on stems, on the music stem specifically

This landed wrong four times. The causes, in order:

- A blind trim: `−10 dB` produced a bed 21.6 dB under the voice, because library
  tracks arrive at their own levels.
- An integrated-LUFS ratio: not the same quantity at all — it folds the ducking
  and the voice's own gaps together, and put the bed 5.5 dB under instead of 13.
- Measuring the finished master: once effects are levelled as foreground, their
  energy inside the voice's gaps **inflates** the reading and the loop compensates
  by pulling the *music* down. It misread a bed as −5.6 dB and trimmed music
  7.4 dB when the true error was about 3.

What works: measure the **music stem** inside the voice's gaps against the **voice
stem** during speech, and iterate before mastering. Converges in one pass.

Also: **calibrate after ducking, not before.** With narration this dense the
compressor pulls the bed below whatever you just set and never lets it back up.

## 6. Beds are levelled from measurement, never trimmed by a constant

Bed sources are deliberately *not* peak-normalised, so their levels run **12 dB
apart** (−27 to −40 dBFS). A flat `−28 dB` bed gain applied to those put every bed
at **−55 to −65 dBFS** — inaudible. Every bed in the mix was silent for several
renders and nobody noticed, because silence is exactly what "no ambience" sounds
like.

Measure each bed's rms at prep time and derive the gain from a target. Ambience
near −42 dBFS; a featured texture (marching, rain, a crowd) near −37. Above about
−31 it competes with narration.

**A bed never ducks.** So a bed containing human voices becomes a second narrator
for as long as it runs. Keep crowd recordings in a category nothing auto-assigns
and call them by hand only where a crowd is on screen.

## 7. Library files are takes, not samples

One "sword on shield" recording was **3.23 s holding four blows**. Placed whole it
read as a slam, and because its energy accumulates across all four its anchor
landed 695 ms in, so the whole cluster was early too. `oneshot.py` splits takes
into single hits. The same applies to forge and armour recordings.

## 8. Casting — the category is not the question, the OBJECT is

Timing right and tier right still gives a wrong mix if the sound is of the wrong
object. This is the class of error measurement never caught:

- **Look at what the impact marker is ON.** Two strikes put the comic starburst on
  the defender's *wooden shield*, blade against it; he only takes X-eyes later,
  after a hook drags the shield away. Cast as flesh they were wrong twice — wrong
  object, and they spent the flesh sound before the beat that earned it.
- **Read the whole shot.** A wide of an army can be an advance or an aftermath. One
  shot was corpses with survivors standing among them; it got a marching bed.
- **A diagram is not a strike, but its labels still name things.** A wound chart
  was cast as a metal impact (it *is* a big redraw) and its two labels as caption
  ticks. Right answer: soft element for the panel, the named wound for each label,
  6 dB down.
- **Punctuate arrivals, not exits.** A title card already on screen at t=0 that
  cross-dissolves *out* has no frame to hit; the redraw mid-dissolve looks like a
  card and isn't.
- **Vocals sparingly** — the blow that lands and the crowd that shouts, not every
  beat. And never put an anticipation swish in front of a voice.

## 9. Stacks

One sound is a sample; two is a designed hit. A strike gets a short swish **130 ms
before** contact (anticipation) and a weight layer **35 ms after** (the body reacts
after the blade arrives). Metal alone is thin.

`sync_check.py` scores stack layers separately, because those offsets *are* the
design and scoring them as independent sync targets punishes doing it right.

## 10. Panning — a static sound under a moving picture reads as stuck

A bed under a column advancing right-to-left measured **dead centre** (+0.7 dB
balance, sources within 0.5 dB of centred) and was still described as sitting on
one side. Nothing was wrong with the balance; nothing *moved*. The ear localises a
static source once, and the picture's motion then contradicts it.

Use a constant-power sweep so level holds across it (verified: balance travelled
−8.8 dB to +11.4 dB while total level stayed within 1 dB). **Check the direction by
measuring** — on that shot the framing does not translate at all; it is the column
*facing* left that implies the advance. And don't sweep hard on a wide shot: ±0.85
reads as movement, ±1.0 draws attention to the technique.

## 11. Operational

- **A missing palette category must warn, not skip.** Rebuilding a palette once
  dropped a category and every strike silently lost its weight layer for a whole
  render — 7 survived where 114 should have.
- **Clean the work directory even on failure.** It holds a file per cue plus a
  full-length wav per batch: 2–4 GB per run. Ten leaked runs filled a 252 GB disk
  and the next render died mid-mix on "No space left on device".
- **`loudnorm` does not hold its own ceiling** in single-pass mode, and the mp3
  encoder overshoots after it: a master asked for −1.0 dBTP came out at −0.2 once
  effects were levelled as foreground. Append an explicit limiter.
- **Fetch signed CDN urls with curl, not ffmpeg.** ffmpeg re-encodes the `%`
  escapes and the signature stops matching — a 403 that looks like an auth
  problem.
- **Keep the cue sheet and the beat script in sync.** A committed sheet that was
  never regenerated after the script changed is a silent lie about what shipped.
