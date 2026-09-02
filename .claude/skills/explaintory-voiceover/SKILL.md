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

## Read this before the next run — 2026-08-14

One delivery took eleven rounds because of the things below. None of them are
subtle in hindsight and all of them are now enforced somewhere; this list exists
so the next run starts where that one finished.

**Money.** `--approval "<his actual words>"` is required for EVERY send, at any
size. `--budget` defaults to 1000 and is a runaway backstop, not an allowance.
There is no threshold, no standing approval, and no carry-forward — and note how
this broke: the rule was written down, then restated more permissively by the
agent itself ("fixes inside an approved job are yours to make"), and the
restatement was used as the authorisation. A rule the agent can rewrite is a rule
the agent can repeal, which is why it lives in `generate.py` now.

**Repair granularity.** Never re-roll a section to fix a word. Use
`regen_span.py` on the sentence — 134 characters instead of 403, conditioned on
the surrounding script and spliced inside measured silence. It refuses when there
is no silence at an edge, and it verifies itself afterwards and auto-reverts if a
word went missing (it ate "personal insult" once, before that check was inline).
Re-rolling a section also re-rolls every correct word in it: a header re-roll
made two names *worse* than plain spelling.

**Defects the read-check cannot see.** Every complaint was a correctly-read word
that sounds wrong — "echoing", "robotic", "like a separate word". The read-check
compares audio to the SCRIPT, so it structurally cannot find these. Three
detectors were built and all three failed: envelope autocorrelation flagged 2133
of 2371 words, tail-template matching caught 2 of 3, and `prosody_gate.py` flags
"the" twelve times because `pyin` makes octave errors on short function words.
**Do not present a clean run from `prosody_gate.py` as evidence.** It needs
octave correction and a second confirmed example before it is worth anything.

**Verification.** The whole-file transcript invents dropped words — it did on all
four deliveries, including a 25-word run that was present verbatim. Always
confirm a candidate drop with a windowed re-transcription, and cross-check the
alignment JSON: a word the forced aligner placed at high confidence is there.

**Logs.** Never pipe a stage through `tail` or `head`. Write the full log to a
file and filter at read time — a filter on the pipe decides, before the output
exists, what will ever be knowable, and it lost a master's repair counts.

**Profile.** `voice-calibration.json` at the repo root, committed, key-free. The
container is not storage; it died three times today. `similarity_boost` is 0.80
and appears nowhere in this file's examples — read it from the calibration.

**Heading levelling.** `level_headings` compares syllables per second now, not
words per minute; the old metric slowed a 4-word heading 15% to match a median
set by 2-word ones. Even fixed, it still wanted to slow "James the Second's
Bombard", so the last delivery ran with `--no-level-headings`. Check what it
would do before enabling it.





## Read this before the next run — 2026-09-02

Three defects reached a delivered file and Sapro found all three by ear. Each one
had a check that was supposed to catch it, and each check reported nothing.

**A heuristic measurement is a silent decision.** `_syllables` had `y` inside
`[aeiouy]+`, so "bayonet" counted 2 syllables instead of 3. "The Bayonet." then
measured 3.59 syl/s when it reads at 4.79 — the fastest announcement in the file —
and 3.59 sits inside the 12% levelling tolerance. The one heading `level_headings`
exists to catch was the one it examined and passed. The undercount is
**one-directional**: it always makes a heading look slower, so it can only ever
suppress a correction, never trigger a wrong one. Same class of word: loyal, royal,
crayon, player, layer, mayonnaise. Fixed, but the lesson generalises — nothing
downstream can tell a wrong rate from a right one, so a heuristic that gates a
correction needs test cases on the inputs it is worst at.

**A detector that only knows one class looks identical to a clean sweep.**
`--suggest-breaks` scanned for fronted modifiers only. Reduced relatives were
invisible, and the tool's short candidate list read as "this script has few missing
breaks" rather than "half the classes were never checked". See the clause-break
section; the fix took the list from 4 candidates to 14.

**Pace is not the only way a read goes wrong.** Sapro said an announcement was "not
good"; the measurable outlier was pace, so pace got fixed — and the real defect was
the take dying away at the end (level −22.26 dB start-to-end against a −19.57..−5.39
band across the other seven, pitch falling 17 semitones). Retiming it 15% slower
made the dying tail *longer*. Before retiming a heading, measure its level and pitch
trajectory against the other headings, not just its rate. A take that trails off is a
bad take and wants a re-render; a take that rushes wants retiming. They are different
defects and the fix for one worsens the other.

**Render candidates, don't bet on one roll.** A chapter announcement is 10-20
characters. Three takes cost 36 and let the choice be made by measurement — the best
of three had a −10.67 dB drop against the delivered take's −22.26. Rolling once and
hoping is the expensive option.

### Prove a destructive edit did not eat a word

Any edit that silences or removes audio must be checked by TRANSCRIBING the
region afterwards and diffing against the script — before it is reported, and
before the file is sent.

A sweep for orphan fragments in the chapter gaps looked correct and was not. A
gap is 0.30 s, so the next sentence starts inside a 0.6 s search window, and
every "fragment" the sweep found after a chapter name was the opening of the
following line. It turned "Captagon was invented for children" into "Captagon
was in for children" — a word cut out of the middle of the read, delivered as a
fix. The transcript caught it; nothing else would have.

Silencing something that turns out to be speech is worse than the glitch it
replaced, because it is invisible to every level and waveform check and only
shows up as a missing word.


## Check the raw take before ever proposing a re-render

If the RAW take is clean and the DELIVERED file is not, the defect was created
downstream — by the stitch or by the master — and re-rendering cannot fix it. It
buys a different take of a line that was already right, and the same pipeline
damages the new one identically.

This is not hypothetical. The Hashish chapter announcement measured 16 ms of
fricative in the stitch and 186 ms after mastering; three surgical attempts
missed because they were aimed at the fricative, when the real defect was two
orphan fragments 106 ms and 66 ms after the word. The proposal on the table at
that point was to re-render the header. Sapro asked "but the raw was good
right?" and that question is the whole rule.

So, in order, every time:

  1. Measure the defect in the RAW section file.
  2. Clean there  -> the stitch or the master did it. Fix it there. Zero credits.
  3. Present there -> the take is genuinely bad. Only then consider a re-render,
     and only after saying what it will cost.

A re-render is the last option, not the first. Sapro has said so repeatedly and
he has been right every time.


## One report means sweep the class

When Sapro names a defect, the timestamp he gives is a sample, not the job. Find
every other instance of the same defect in the file before going back to him,
and tell him how many there were.

He had to report the forced-comma beat three times — 0:03, then 0:40, then
"road, spaced" — because each time it was fixed only where he pointed. It was
one bug in eight places. Later, one report of a tick at "continued strain"
turned out to be an orphan burst at the end of seven different sections.

So: identify the SIGNATURE, not the timestamp. A -16 dB burst in the last 2 ms
after 50 ms of silence is a signature; 16:29.9 is not. Then scan every section
for it, repair them all, and check the mirror case as well — a burst at the end
of a section means checking the start of one too.

Report it as "you heard one, there were seven". That is the difference between
him being the detector and him spot-checking the work.

### The timestamp he gives may not contain the defect

Sweeping the class is not enough if the search stays inside the window reported.
Sapro gave 261.690-262.300 for the Hashish header. The word in that window was
fine. The defect was a 133 ms copy of its final "sh" stranded at 262.469 — 169 ms
past the end of the window, in the silence. Six repairs and three fresh takes all
aimed inside the window and could not have worked.

He hears "the glitch is at the header". He cannot hear "the glitch is 169 ms
after the header, in the gap". Take his timestamp as the centre of a search, not
its bounds, and scan the whole file for the signature anyway:

    python3 scripts/orphans.py --audio "Title (final).mp3"

It finds short bursts fenced by silence on BOTH sides, then decides each one by
muting it and re-transcribing. Words lost -> KEEP, it is speech. Nothing lost ->
ORPHAN, safe to cut. It never edits the file.

Two things that sweep taught, both of which broke an earlier version:

- **A gained word is not a change to defend.** Muting the Hashish fragment made
  ASR *recover* "Hashish" — the fragment was corrupting the word badly enough to
  erase it from the transcript. A rule that flagged any transcript change called
  that KEEP and protected the exact defect it was built to find. Test for words
  LOST, one-sided, never for words different.
- **Decoded MP3 has no digital silence.** A master writes exact zeros between
  sections; lame plus a decoder puts about -51 dBFS of noise in their place. An
  exact-zero fence finds nothing on an MP3, and a fence below the codec noise
  finds nothing either. The script auto-detects which case it is and prints it.
  Believe a floor figure only after reading that line.


## Confirm a fix on the excerpt, not the whole file

Sapro's rule, and it is faster for both sides: when a defect is fixed, send him
the SIX SECONDS around it — before and after, cut from the stitch so the fix is
the only difference — and wait for his yes. Master and deliver the full file
only after he confirms.

Mastering a twelve-minute file takes eight minutes and makes him listen to
twelve to check one edit. An excerpt is instant, and if the fix is wrong he
says so in seconds instead of after a full pass. Kick the master off in the
background while he listens, so a yes delivers immediately.

    ffmpeg -ss <chapter_start - 2.5> -t <len + 5> -i raw_stitched.wav clip.mp3

Applies to every fix — a trimmed fricative, a removed beat, a repaired click.
The one exception is a change that only exists after mastering, like loudness
or a pause the master itself inserts; those have to be judged on the master.


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

  PRE-FLIGHT — 2 thing(s) to look at before spending:
    ! guide entry “.303” does not appear in the narration — export artifact, …
    ! orphaned decimal point: “…it was fed British. 303 made to loosen…” — a Docs
      export splits ".303" into ". 303", so the voice reads a sentence boundary
      mid-clause and says the number in full. Fix the script.

  41 sections (8 of them chapter announcements) · 12,174 chars · ~14:29 audio

  CALIBRATION — every value that will be sent, and who chose it:
  voice dUHbvtIZto0ZEBkhYiyk (profile) · model eleven_multilingual_v2 (profile)
  stability 0.48 (profile) · similarity_boost 0.8 (profile) · style 0.05 (profile)
  speed 1.07 (profile) · use_speaker_boost True (profile)
  chunkSize 450 (profile) · chapterPause natural (profile)
  collapseBreaks False (profile) · readTitle True (default) · skipHeadings False (profile)
  ^ 1 value(s) nobody chose — inherited defaults, not settings: read_title

  COST: ~12,174 credits (first pass) of 82,852 remaining
  redo rounds: off (--max-redos 0) — flagged sections are reported, not re-rendered
  WORST CASE this run: ~12,174 credits
  master: /root/.claude/skills/synced/explaintory-vo-master/scripts/humanize.py
```

Report the chapter list back and wait. A wrong heading count means the script is
structured differently than assumed, and it is far cheaper to find that here than in
a finished render — a missed heading is a chapter that never gets announced, and a
spurious one is a sentence read as a chapter title.

**Read the provenance marks, not just the numbers.** The gate prints every value it
is about to commit and says where each came from, because the value that is wrong is
almost never one somebody typed. `similarity_boost` once fell back to the code
default of 0.75 when the locked-in number is 0.80, and the old plan output printed
four settings out of six — so the one setting that was wrong was the one the gate
could not show. Anything marked `(default)` is a decision nobody made. Check those
first.

The **PRE-FLIGHT** block cross-references the script against its own pronunciation
guide before a credit is spent. A guide headword that does not appear verbatim in the
narration is an export artifact, a spelling drift, or a stale guide entry. It matters
most for the artifact that leaves the text well-formed: Google Docs exports ".303" as
". 303", the voice then reads a sentence boundary mid-clause and says "three hundred
and three", and no downstream check can catch it — the read-check diffs the ASR
against the same corrupted script and finds agreement.

## Then run it

```bash
python3 scripts/voiceover.py --script script.txt --title "The Weirdest Weapons Ever Built" \
    --profile ~/voiceover_profile.json --out-dir ./out
```

Stages, all resumable with `--from generate|check|master`:

| Stage | What it does |
|---|---|
| generate | splits the script the way Voiceover Studio does, renders one ElevenLabs request per section, stitches with exact silence |
| check | transcribes every section, diffs against the script, and **reports** what failed. It does not re-render unless `--auto-redo` is given (`--max-redos` defaults to 0) |
| master | hands the stitch to `explaintory-vo-master`'s `humanize.py` with its approved settings |

**Capture each stage's full output to a file and filter when you READ it — never on
the pipe.**

```bash
python3 scripts/voiceover.py … > stage.log 2>&1;  grep -v "MB/s]" stage.log
```

The instinct to filter a noisy job is right — a 1.5 GB download emits hundreds of
progress lines — but `| tail -12` applies the filter to the *pipe*, which decides
before the job has finished which of its output will ever be knowable. A mastering
pass was launched that way and succeeded; its own repair counts (how many over-
full-scale regions were declipped, how many splice fragments were removed and where)
scrolled past the window and were gone, and the only way to get them back was another
eight-minute run. The full log costs a few kilobytes; discarding it costs a re-run.
Download progress bars are the thing to filter at read time, not at write time.

Every stage exits non-zero if it produced no artifact, so the exit code can be
trusted. Do not read success out of the prose.

Everything lands in `<out-dir>/.vo_<title>/`: the section takes, the raw stitch, the
read-check JSON, the pause report, the alignment cache and `spend.json` — the run's
character ledger. A second run reuses all of it, so fixing one section costs one
section's credits.

## Setup — two things, once

1. **`ELEVENLABS_API_KEY`** in the environment. Never in a file; never in the repo.
2. **The profile**, `--profile path/to/voiceover_profile.json`. This is the file
   Voiceover Studio already writes next to `voiceover_studio.py` when "remember" is
   ticked — copy it across unchanged, minus the key. See `profile.example.json`.
   Without it the voice id is missing and generation stops with that message.

Dependencies: `bash scripts/setup.sh` once. ffmpeg must be on PATH. First run of the
read-check downloads **distil-large-v3 — 1.5 GB** on disk (1,516,480,902 bytes,
measured on a cold container; an earlier figure of ~750 MB here was half the real
size) and first run of the master downloads **MMS_FA — 1.18 GB** (1,262,047,414
bytes, measured against the upstream `content-length`). Both are cached after that.

Those caches are verified before use, not trusted. A truncated transfer produces a
file that looks present, is never re-fetched, and makes every later run fail
identically — the cache turns a transient network fault into a permanent one and the
error message ("your checkpoint file is corrupted") blames the server rather than the
transfer. So a damaged cache entry is **deleted** as part of the error path and the
message says so, which is what makes the obvious recovery — run it again — actually
work. If a download keeps arriving short, fetch it with resume:
`curl --retry 6 --retry-all-errors -C -`.

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

### Re-rendering is a second spend, so it has a second gate

**`--max-redos` defaults to 0 and nothing is re-rendered without `--auto-redo`.**
The check stage prints each flagged section with its ASR evidence and the character
cost of re-rendering it, then hands over the command that would do it. Sapro's rule:
*"you should ask me permission if you like to do regeneration some lines."*

The confirmation collected before generation is consent for one quantity of
characters, not for every later render the pipeline decides to do. And the ceiling is
now run-wide: every `generate.py` invocation in the work dir — the first pass and
every redo round — debits `<work>/spend.json`, so `--approve-spend` is a ceiling for
the whole run. It used to be enforced per invocation, and the redo was built as
`gen_cmd + ["--regen", …]` with `--approve-spend 12926` still attached, so each round
started with a fresh full-size budget and the true worst case was that number times
`(1 + max_redos)`. `--plan` now states that worst case, not just the first-pass cost.

With `--auto-redo`, the first redo round is a plain re-roll, which is what fixes a
one-off misread. Later rounds raise stability by 0.05 — the studio's own lever for
false mid-sentence pauses, which a re-roll would only repeat.

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
| A heading that **trails off** — "starts good, ends like murmuring" | the take dies away: level and pitch fall off the end | **re-render** — retiming makes it worse |

The read-check makes that distinction itself: an odd rate only forces a re-render when
it arrives *with* a transcript mismatch. A section where every word is present is
reported as pace and left for the master.

That last row is the trap, because it presents as "the announcement sounds wrong" —
the same words Sapro uses for a rushed one — and pace is the property that is easy to
measure, so pace is what gets found and fixed. Measure the trajectory before deciding:

```python
y = librosa.load(part)[0]                      # trimmed to the spoken span
r = librosa.feature.rms(y=y)[0]                # first third vs last third, in dB
f0 = librosa.pyin(y, fmin=60, fmax=300)[0]     # same, in semitones
```

Run it on **every** heading, not just the reported one — the other headings are the
only baseline that makes the number mean anything. A drop well outside their range is
a bad take. Trust the level figure over the pitch figure: RMS cannot make an octave
error and `pyin` can.

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
or a heading followed by prose, is left alone. A mid-script line like "The corvus —
a boarding bridge — decided the battle" is never mistaken for an entry, because the
heading has to match first. One entry is enough to trigger it; a one-name guide read
aloud is exactly as wrong as a ten-name one.

Two anchors, in order. **Tail** is the fast path: everything after the heading looks
like entries, which is the shape of a script that ends with its guide. **Section** is
the fallback, and it is the one production documents need — a real source doc is a
container for several documents (script, then guide, then a 1,400-word animator note
or a shot list), and with anything appended after it the guide is no longer the tail.
The tail test is then dragged under by material that was never part of the guide,
detection misses entirely, and the video closes by reciting its own glossary *and*
the art direction. So the block from the guide heading to the next H1 is tested on
its own, and everything from that heading onward is held out of the narration.

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
beside it. It parses with spaCy, because knowing where a phrase *ends* is a parse,
not a pattern — a regex counting words lands on "lost forty ‖ ships" instead of
"At Angolpo ‖ the Japanese". It looks for **two** classes:

1. **Fronted modifiers** — "At Angolpo ‖ the Japanese lost…", "For 25 hours ‖ the
   British pounded…". The last token of the modifier's subtree.
2. **Reduced relative clauses** — a noun followed straight by a clause with its own
   subject and verb, the "that" dropped: "each one a walking weakness ‖ the other
   had to babysit", "the tool ‖ the legions dug their latrines with", "a fort ‖ he
   could take with him". The writer hears the join and leaves the comma out; the
   voice then runs the noun into the subject and the listener has to re-parse the
   line mid-sentence.

Class 2 was added on 2026-09-02 because Sapro reported "weakness" by hand. Only
class 1 existed, and a reduced relative is not a fronted modifier, so **this entire
class was invisible no matter how many scripts went through** — the tool reported
its usual two or three candidates and looked like it had swept the script. On the
script that prompted this, adding class 2 took the candidate list from 4 to 14.

Idiomatic heads — "the second he got close", "the instant it did" — parse as
reduced relatives and must NOT get a beat; they are skipped by a stop list.
Infinitives ("a heartbeat to choose") are skipped by requiring a finite verb.

A boundary that is already punctuated on *either* side is skipped. When a fronted
modifier's subtree ends on its own comma the left token is `,`, which used to emit
pairs like `,|the` — noise in a list whose whole purpose is to be short enough to
read by hand, and a pair that cannot match anything downstream anyway.

**They are still candidates.** The vo-master skill is explicit that automatic guesses
are wrong about a third of the time — it wants a pause inside "growing on a deck ‖
that also mounted a catapult". Read them, keep the real ones, pass the file with
`--curated`. Post-date beats are automatic inside `humanize.py` and are filtered out
here so they are not doubled.

**Reject a class-2 candidate only for length or idiom, never because it "is not a
fronted modifier."** That reasoning dropped `fort|he` — "a fort ‖ he could take with
him" — from a delivered file, and it is the same construction as the "weakness" line
Sapro then had to report by hand. The classes are different shapes; both want a beat.

**A curated pair is a bigram, not a location.** `humanize.py` matches `wordA|wordB`
against every adjacent pair in the script, so a pair occurring twice fires at both.
Count occurrences before adding one: `men|it` wanted a beat in "The men ‖ it cut
down in the grass were never asked" but the same pair would have fired inside "Not
for the men it killed", a punchline that has to stay tight, so it could not be used
at all. Say so rather than adding it and hoping.

## Do not

- Do not re-tune the mastering settings. They were derived by force-aligning the
  channel's real human stem and signed off by ear. This skill drives that pipeline;
  it does not have opinions about it.
- Do not report a runtime, a pause figure or a wpm from listening. Read them out of
  `humanize.py`'s own output and the read-check JSON.
- Do not swap the ASR model down to save time. The read-check is only worth running
  if it is trustworthy.
