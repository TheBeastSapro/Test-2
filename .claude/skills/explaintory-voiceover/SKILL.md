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

## One command

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
