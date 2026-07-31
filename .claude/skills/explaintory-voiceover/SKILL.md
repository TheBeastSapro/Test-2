---
name: explaintory-voiceover
description: Take an ExplainTory script all the way to a finished, mastered voiceover file — generate it on ElevenLabs with Sapro's locked-in voice, read-check every section against the script with ASR, re-render anything misread, then master it through the explaintory-vo-master pipeline and deliver "<Title> (final).mp3". TRIGGER on "voiceover", "make the voiceover", "VO this script", or any script submitted with an instruction to voice it. Use explaintory-vo-master instead when Sapro supplies audio he already generated himself.
---

# ExplainTory Voiceover

**When Sapro gives a script and says "voiceover", do the whole job and deliver the
mastered MP3.** He supplies the script and the title. Nothing else is a question —
the voice, its settings, the pacing targets and the mastering chain are all locked.

Deliver: `<Video Title> (final).mp3`. Report the runtime, the read-check result
(which sections were redone and why), and the wpm/silence figures against the human
reference. Do not ask which settings to use.

## What this exists to remove

Generating a voiceover meant listening to twelve minutes of audio, catching the two
places the model misread a word, going back to the tool, regenerating those sections,
re-stitching, then sending it for QC. That listen-and-report loop is the cost, and
it is the part a machine can do: a misread is a measurable difference between what
the script said and what the audio says.

So the listening pass here is **ASR, not a listening model**. `explaintory-vo-master`
has a standing rule — never treat a listening model's description of audio as data —
and this obeys it. Every section is transcribed and diffed against its own script
text. A section only gets re-rendered on evidence.

## Confirm the structure first — always

Generation is the one irreversible step. The read-check and the master can be re-run
for free; characters sent are characters billed. So show the plan and let Sapro
confirm before spending anything, exactly as the studio's structure panel does:

```bash
python3 scripts/voiceover.py --script script.txt --profile voiceover_profile.json --plan
```

```
  “The Weirdest Warships Ever Built”
  detected 8 headings · 1 divider — headings read aloud as chapter intros
  chapters: The Weirdest Warships Ever Built · The Ancient World · The Middle Ages · …
  pronunciation guide: 31 names held out of the narration

  41 sections (8 of them chapter announcements) · 12,174 chars · ~14:29 audio
  voice dUHbvtIZto0ZEBkhYiyk · eleven_multilingual_v2 · stability 0.48 · style 0.05 · speed 1.07
  COST: ~12,174 credits of 82,852 remaining
```

Report the chapter list back and wait. A wrong heading count means the script is
structured differently than assumed, and it is far cheaper to find that here than in
a finished render — a missed heading is a chapter that never gets announced, and a
spurious one is a sentence read as a chapter title.

## Then run it

```bash
python3 scripts/voiceover.py --script script.txt --title "The Weirdest Weapons Ever Built" \
    --profile ~/voiceover_profile.json --out-dir ./out
```

Stages, all resumable with `--from generate|check|master`:

| Stage | What it does |
|---|---|
| generate | splits the script the way Voiceover Studio does, renders one ElevenLabs request per section, stitches with exact silence |
| check | transcribes every section, diffs against the script, re-renders what failed (up to `--max-redos`, default 2) |
| master | hands the stitch to `explaintory-vo-master`'s `humanize.py` with its approved settings |

Everything lands in `<out-dir>/.vo_<title>/`: the section takes, the raw stitch, the
read-check JSON, the pause report and the alignment cache. A second run reuses all of
it, so fixing one section costs one section's credits.

## Setup — two things, once

1. **`ELEVENLABS_API_KEY`** in the environment. Never in a file; never in the repo.
2. **The profile**, `--profile path/to/voiceover_profile.json`. This is the file
   Voiceover Studio already writes next to `voiceover_studio.py` when "remember" is
   ticked — copy it across unchanged, minus the key. See `profile.example.json`.
   Without it the voice id is missing and generation stops with that message.

Dependencies: `bash scripts/setup.sh` once. ffmpeg must be on PATH. First run of the
read-check downloads distil-large-v3 (~750 MB) and first run of the master downloads
MMS_FA (~1.2 GB); both are cached after that.

## The read-check

Per section, all measured:

- **misread / skipped / repeated words** — ASR transcript vs script text. Word
  boundary differences ("temple sat" heard as "temples at") are the same sounds
  segmented differently, so they are dropped before the WER is computed. A dropped
  or duplicated run is always a defect. A *single* substituted word is the ambiguous
  case and is settled by how confidently the transcriber heard it — "chain" rendered
  as a confident "crane" changes the meaning of the sentence and would otherwise hide
  under the WER floor in a long section.
- **slurred delivery** — a run of 3+ words the transcriber heard at under 0.45
  confidence.
- **speaking rate** outside 120–240 wpm — text was dropped or repeated.
- **dead air** of 0.7 s+ *inside* a section — the model hesitating mid-thought.
  Edge silence is normal and the mastering pass retimes it, so it is not counted.
- **clipping** — peak at or above −0.1 dBFS.

The tools matter here. `distil-large-v3` is the default because small Whisper models
invent errors — `base.en` heard "bow" as "mow" and "training" as "trading" on a
clean take — and every invented error costs a real regeneration. Normalisation is
OpenAI's `EnglishTextNormalizer`, which settles British vs American spelling
(harbour/harbor, programme/program) and spoken numbers ("nineteen forty three" →
1943) — most of the apparent-mismatch noise, handled by a tool that is already right
rather than by local guesswork.

First redo round is a plain re-roll, which is what fixes a one-off misread. Later
rounds raise stability by 0.05 — the studio's own lever for false mid-sentence
pauses, which a re-roll would only repeat.

A word that comes out the same way on two separate takes stops being re-rendered.
The render is consistent, so a third will not differ: either it is a name the
transcriber spells its own way ("Angolpo", "Hiero") or the voice really does say it
wrong every time, which needs the script fixed rather than more credits. Those are
listed as *consistent across takes, worth a listen*.

Sections still flagged after the last round are named in the output. **Listen to
those before publishing** and say so in the delivery message; do not report a clean
run when the check did not come back clean.

## Generation matches the studio exactly

A section rendered here is interchangeable with one rendered in the browser tool, so
the two can be mixed on the same project:

- one request per section, ~450 chars (`chunkSize` from the profile)
- `previous_text` / `next_text` conditioning, 300 chars each way
- `previous_request_ids` from the last 3 sections
- conditioning **dropped** right after a chapter announcement, so the narration
  starts fresh instead of continuing the heading's sentence
- exact digital silence around chapter announcements and CTAs, `natural` preset:
  ~0.45 s before the chapter name and ~0.50 s after it, measured off Sapro's own edits

Two deliberate differences: the stitch is a 48 kHz WAV, not a re-encoded MP3, so
mastering runs on un-degraded audio and only the delivered file is encoded once; and
the script's H1 is treated as the video's title, not its first chapter, so the
voiceover does not open by reading its own title aloud.

### The first chapter announcement reads fast

It is the section with the least conditioning behind it — no `previous_text`, no
`previous_request_ids` — so the model starts cold and rushes it, while later headings
inherit up to three prior request ids and settle into pace. Sapro hears this in the
browser tool, where it is most obvious because the H1 is read as section 0 with no
context at all.

The cause is structural, so re-rolling it does not reliably help. Retiming does, and
costs nothing: at stitch time every heading's rate is measured **over its spoken span
only** (a 3-word announcement is mostly edge silence, so dividing by file length would
make every short heading look slow), and any heading more than 12% off the median of
the others is stretched to match. Needs 3+ headings — with fewer there is no majority
to level against. Corrections are clamped to ±15%, past which the stretch is audible
itself; when the clamp binds it says so and asks for an ear. `--no-level-headings`
turns it off.

## When a read is fast — retime, do not re-render

Speed is a timing problem, and timing is fixed exactly by processing. Re-rendering
is for missing or wrong *words*. Three distinct cases, three different answers:

| Symptom | Cause | Fix |
|---|---|---|
| A whole section off-rate **and** the transcript disagrees | the render lost or repeated text | re-render |
| A whole section off-rate, transcript matches | it is merely fast | timing — never re-rendered |
| The first chapter announcement rushes | no conditioning behind it | retimed at stitch, automatic |
| An individual sentence unusually fast | one sentence, not the read | `--max-wpm` in the master |

The read-check makes that distinction itself: an odd rate only forces a re-render when
it arrives *with* a transcript mismatch. A section where every word is present is
reported as pace and left for the master.

### Choosing --max-wpm

`humanize.py` levels per sentence off the alignment, skips the first 25 s so the hook
stays fast, and never stretches past 13%. Default is **0, off** — the un-levelled read
is the one that was approved.

Measured on a test read containing both of the reference stem's named punchlines:

- **`--max-wpm 290`** — touched nothing (x1.000). 290 is faster than the human
  reference ever goes, so it only ever catches genuinely broken sentences. This is the
  safe setting if levelling is wanted at all.
- **`--max-wpm 250`** — slowed *"A cart full of fireworks had done the work of an army"*
  from 290 to 252 wpm, and *"A weapon this strange should have been a footnote"* to 250.
  Those are the two lines the vo-master skill records the **human** delivering at 290
  and 283. 250 is the human's p90, so it flattens real punchlines by construction.

So: the channel's fastest sentences are not a defect, they are the delivery. Do not
reach for 250 because a sentence "sounds fast" — check whether the human goes faster
there too. If Sapro asks for levelling, start at 290 and let him hear it.

## The pronunciation guide at the end of the script

Every ExplainTory script ends with one, in `Name — RES-pel-ing` form. It is a note
to the reader, and **left in place the video closes by reciting its own glossary**.
It is stripped from the narration automatically and saved to
`<work>/pronunciation_guide.json` as that video's answer key.

Detection needs the heading to actually say *pronunciation* (or "how to say"), and
most of what follows to look like entries — so a section legitimately titled "Names",
or a heading followed by prose, is left alone. Only the tail is examined, so a
mid-script line like "The corvus — a boarding bridge — decided the battle" is never
mistaken for an entry. One entry is enough to trigger it; a one-name guide read aloud
is exactly as wrong as a ten-name one.

**Extracted is not applied.** Sapro compared a raw take against a respelled one in his
own voice and chose the raw: `pronOn` is `false` in his profile, and respelling costs
pacing. The guide is the reference for *checking*, not an automatic substitution.

## Pronunciation — respell, never phonemes

ElevenLabs takes two kinds of pronunciation rule and only one of them works here.
From their docs:

> "Pronunciation dictionary phoneme tags only work with `eleven_flash_v2` and
> `eleven_v3` models. Other models skip dictionary phoneme tags and use the default
> pronunciation. For other models, use alias tags instead."

The channel runs `eleven_multilingual_v2` — picked for accuracy, and the one model
where a phoneme rule does nothing. It is not rejected, it is **skipped**: careful IPA
produces the same wrong reading with no error to tell you. `pronounce.py` warns when a
lexicon entry looks like IPA on a model that will ignore it.

So the fix is respelling. `lexicon.json`, passed with `--lexicon`:

```json
{ "words": { "Angolpo": "An-gol-poh", "Hiero": "Hee-air-oh" } }
```

Whole-word only — a `Hiero` entry cannot corrupt "hierarchy" — and applied **only to
the text sent to the API**. The read-check still diffs against the real spelling, and
`humanize.py` still aligns against the real script, so nothing downstream is fooled.
Respellings are longer than the words they replace, and that is billed.

The read-check feeds it. A word that comes out identically on two takes is exactly
what a lexicon is for, so those runs print:

```bash
python3 scripts/pronounce.py --from-check <work>/readcheck.json
```

which emits a ready-to-fill entry per consistently-misread word. **Decide which are
real** — most are the transcriber spelling a name its own way, which needs no fix.

## Before mastering — the curated clause breaks

`humanize.py` wants a file of clause breaks the script forgot to punctuate, one
`wordA|wordB` pair per line. This is script-specific and needed every time.

`--suggest-breaks` prints candidates, one `wordA|wordB` per line with the sentence
beside it. It parses with spaCy and takes the last token of a fronted modifier's
subtree, because knowing where the phrase *ends* is a parse, not a pattern — a regex
counting words lands on "lost forty ‖ ships" instead of "At Angolpo ‖ the Japanese".

**They are still candidates.** The vo-master skill is explicit that automatic guesses
are wrong about a third of the time — it wants a pause inside "growing on a deck ‖
that also mounted a catapult". Read them, keep the real ones, pass the file with
`--curated`. Post-date beats are automatic inside `humanize.py` and are filtered out
here so they are not doubled.

## Do not

- Do not re-tune the mastering settings. They were derived by force-aligning the
  channel's real human stem and signed off by ear. This skill drives that pipeline;
  it does not have opinions about it.
- Do not report a runtime, a pause figure or a wpm from listening. Read them out of
  `humanize.py`'s own output and the read-check JSON.
- Do not swap the ASR model down to save time. The read-check is only worth running
  if it is trustworthy.
