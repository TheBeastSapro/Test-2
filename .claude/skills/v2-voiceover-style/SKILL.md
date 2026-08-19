---
name: v2-voiceover-style
description: The measured delivery and writing target for ExplainTory's V2 voiceover — the "sounds human, not TTS" style taken from two reference narration channels. Use when writing or pacing a script for voiceover, when a take sounds flat, robotic or evenly-paced, when deciding where pauses and gaps go, or when scoring a rendered take against the reference. TRIGGER on "V2", "V2 style", "make it sound more human", "the voiceover sounds like AI", "where should the pauses go", "pacing", "score this take". Use explaintory-voiceover to actually render, and explaintory-vo-master to master.
---

# V2 voiceover style

What separates the reference narrators from a TTS read is not voice quality. It
is **where they stop, and how much their sentence lengths move.** Both are
measurable, both were measured, and neither of them costs credits to fix.

Two channels were analysed end to end, from ASR word onsets rather than by ear:

| | Serious History (`sNMDXA8Qcts`) | Agent Flappy (`3GKC4kC3iQ0`) |
|---|---|---|
| runtime / words | 22:01 / 4,152 | 31:15 / 4,292 |
| speech rate | 189 wpm | 137 wpm |
| character | fast, even, silence saved and spent in lumps | slower, short sentences, silence spent constantly |

They are two different ways of sounding human. **Aim a script at one of them,
never at the average** — the midpoint between a 189-wpm anthology and a 137-wpm
chaptered explainer is a voice neither of them has.

## The four findings that matter

**1. They stop where the punctuation doesn't.** Both rest at ~11% of all
unpunctuated word boundaries — one mid-phrase pause every ten words, median
0.13–0.14s. This is the single loudest difference from TTS, which rests only
where the typesetting tells it to. It is also the one a script cannot express
and a voice cannot be blamed for.

**2. A full stop rests about twice as long as a comma.** 0.50s vs 0.21s, and
0.53s vs 0.29s. A flat TTS read collapses that ratio toward 1:1, which is what
"reads like it's reciting" actually sounds like. Roughly a fifth of the runtime
is silence in both (19.5% / 21.3%).

**3. Tempo is flat, and jittery.** Both hold one mean rate for the whole video —
trend r = −0.09 and +0.09, i.e. none — while swinging about ±10% from one
30-second stretch to the next. **There is no fast-hook-then-slow-body arc.** A
first pass of qualitative analysis claimed one; the timings refuted it. Do
pacing with sentence length and section length, not with the speed dial.

**4. Variance is the device, not brevity.** Adjacent sentences differ by ~8.4
words on average in *both* channels, despite medians of 17 and 11. The
long-then-short "punch" pattern that gets taught is, in these two videos,
statistically indistinguishable from chance (observed/expected 0.82 and 0.97).
What reads as rhythm is the raw spread.

## Where a mid-phrase rest goes

Derived as lift against chance, and only kept where both narrators agree in
direction. Encoded in `scripts/v2_profile.py` and applied by `scripts/v2_prep.py`.

**Rest here** — before *and* / *but* (lift 1.8 / 3.6), between a noun and the
verb it governs (1.5 / 2.2), after a proper noun (1.3 / 2.7), after an adverb or
a noun, before an auxiliary, before a date.

**Never rest here** — between a determiner and its noun, after a preposition,
inside an infinitive, between a pronoun and its verb, across a degree modifier
("too | heavy"). Both narrators steer around these positions well below chance,
and a break dropped into one is precisely what makes inserted pauses sound
mechanical rather than thoughtful. The veto list is load-bearing; it outranks
every preference above it.

**Before a numeral** is Agent Flappy's strongest single move (lift 4.31, the
largest effect measured anywhere in either channel) and Serious History does not
do it at all. It is therefore opt-in: `--emphasise-numbers`. Use it on a script
whose weight sits in figures, dates and casualty totals — and pair it with the
qualitative finding that both narrators take numbers **lower and slower**, never
louder.

## Do not buy silence

A `<break time="…" />` tag is billed like any other character. At the measured
rate of one rest every ten words, break-tag markup adds **36–43%** to a script's
character count — roughly 9,000 characters on a 4,500-word video, spent entirely
to describe silence.

The same silence costs nothing after the render. `scripts/v2_rest.py` opens the
gaps in the delivered audio: it aligns the audio, finds each planned boundary,
slides the cut to the local energy minimum so the splice lands between words,
and fills the gap with room tone sampled from the file's own quietest passage.
Digital silence would be wrong — the surrounding material has a noise floor, and
a gap that drops below it is heard as a dropout rather than a pause.

This is the standing rule anyway: repair first, generate last. Credits are for
the voice.

Break tags are still worth their cost in one case: when the **voice** needs to
change around the gap rather than only the timing. The model reads the tag, so
it can shape delivery either side of it; a post-production cut cannot. Note that
break tags work on `eleven_multilingual_v2` (the locked model) and the Flash
models, but **not on v3** — and moving to v3 to get audio tags would also give
up request stitching, `speed`, `similarity_boost` and `use_speaker_boost`.

## Workflow

```bash
S=.claude/skills/explaintory-voiceover/scripts

# 1. plan the rests and see the cost of both routes
python3 $S/v2_style.py script.txt --review

# 2. emit the plan for the free route
python3 $S/v2_style.py script.txt --emit-plan plan.json

# 3. render with the normal pipeline (approval gate unchanged)

# 4. open the gaps in the rendered audio — 0 credits
python3 $S/v2_rest.py take.mp3 --plan plan.json --out take_v2.wav --report rest.json

# 5. score the result against the reference
python3 $S/styleprint.py take_v2.wav --md take.md
```

`v2_rest.py` proves its own edit sample-for-sample: deleting the inserted spans
back out must reproduce the input exactly, apart from the 3 ms splice fades. It
does **not** re-transcribe to check for lost words — that was tried and failed on
provably intact audio, because ASR re-segments unstable material differently
between passes and reported words gained. A word cannot vanish from audio that
is still, sample for sample, the original.

Rests it cannot confidently locate are reported and skipped, never guessed.

## Writing to the target

The delivery layer above cannot rescue a script written in even-length
sentences. The checkable targets:

| | A-mode (fast anthology) | B-mode (chaptered explainer) |
|---|---|---|
| target rate | ~188 wpm | ~136 wpm |
| median sentence | 17 words | 10–11 words |
| mean adjacent-length difference | ~8.5 words | ~8.3 words |
| sentences ≤5 words | ~2%, titles and gags only | 17–19% |
| sentences ≥20 words | ~36% | ~17% |
| fragments | <4% | ~15% |
| And/But/So openers | ~14% | ~26% |
| names+numbers per 100 words | ~9 | ~13.5 |
| section length | 300–400s | 45–60s, σ≈30s |

Shared by both, and the safe default:

- Vary adjacent sentence lengths by ~8 words on average. This is the strongest
  measured signal in the writing and it survives both opposite styles.
- Put a name, number or date in every 8–11 words. Below that the writing goes
  abstract, and abstraction is what makes narration sound generic.
- Keep ~84% of non-name words inside the 2,000 commonest English words. The
  specificity comes from the *things*, not from the vocabulary.
- Open a scene in present tense with a date and a person doing something
  physical, before any background.
- Hold contractions near 20%. Over-contracting is a written writer's imitation
  of speech, and neither narrator does it.
- Rhetorical questions: at most ~1 per 1,000 words. Second person: under 0.5 per
  100 words, concentrated in the hook and the CTA.
- Cash every image planted in the hook. If it never returns, cut it.
- End a section on the concrete object or the verdict, never on a summary.

## What is measured, and what is not

Everything above about **timing, rate and sentence structure** is measured from
ASR word onsets across both full videos, and the site preferences are reported
as lift against chance with both channels agreeing in direction.

Two honest limits:

- **Pause lengths are inferred, not observed.** YouTube blocked audio download
  from this environment, so the analysis ran on caption word onsets, and pause
  length is the inter-onset interval minus a fitted word-duration model. A
  parameter sweep showed the *ratios* between pause types and the mid-phrase
  rate are stable across the whole sweep; the *absolute* medians move by about
  ±0.05s. Read the ratios as solid and the absolutes as close. Re-run
  `styleprint.py` on real audio if it ever becomes reachable — the audio path is
  already built and takes the same schema.
- **The prosody description is a model's listening, not a measurement.**
  Register shifts, breath placement, pitch resets, the volume trailing off
  before a big hold — those came from a multimodal pass over sampled segments,
  which contradicted itself on breath between two passes of the same video and
  produced tempo figures the timings refuted. Treat that layer as direction,
  not as data. The claims worth acting on, because they reproduced across both
  videos: pause-*before* is the reveal device rather than loudness; numbers and
  grim material go lower and slower; breath earns its place at the top of a
  paragraph and routine sentences start dry; big holds are co-designed with the
  SFX, so the hold budget belongs to the edit, not the read.

Whether the reference narrators are human or cloned was **not** settled. That
ambiguity is good news: it means the gap is in the pause-authoring layer, which
is buildable, rather than in raw voice quality, which is not.

## Constraints this layer must never break

- `send_text` only. Never touch `text` — the read-check and the mastering
  alignment work against the script's real spelling.
- If `send_text` changes, `chars` changes with it. Break tags are billed, and
  the approval gate must never under-report what a run costs.
- Ask before spending any characters, every send, every time. Nothing in this
  skill creates an exemption; the free route exists precisely so that pacing
  never needs one.
