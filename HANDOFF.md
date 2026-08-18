# Voiceover session handoff — updated 2026-08-01

## State

`FINAL v11.mp3` is the good file. 703.392s (11:43), 320 kbps, 48 kHz mono.
Sapro confirmed it: "now it's perfect". It lives in the session scratchpad, not
the repo — see "the container is not storage" below.

The Hashish defect that was open at the last handoff is **closed**.

## How the Hashish defect was actually fixed

It was never the word. Sapro reported the window 261.690–262.300 and the word in
that window was fine — which is why six repairs failed, two of them damaged the
audio, and three fresh takes all sounded wrong to him.

The defect was a **133 ms duplicate of the word's final "sh"**, stranded alone at
262.469–262.601 — 169 ms past the end of the window he gave. Fenced by 178 ms of
silence before and 252 ms after. Spectrally a dead match for the word's own tail
(centroid 5075 Hz vs 5080 Hz, ZCR 8290 vs 7471). Left behind by one of the
earlier repair attempts.

The fix: clear 261.500–262.853 (both edges inside existing digital silence, so no
click is possible), place his replacement clip verbatim at 261.690. No tempo, no
gain, no EQ, no fade — his clip's tail already decays to −76 dBFS. The stray
fricative goes with the clearance.

His insistence on no gain was right on the measurements: his clip is −13.76 dB
RMS against −13.11 and −13.20 for the neighbouring lines. Within 0.6 dB unaided.

Verified: duration identical to the sample; everything outside 261.500–262.853
bit-identical to v10, asserted sample-for-sample; orphan sweep 1 → 0; transcript
41 words in both, identical sequence.

## The lesson worth keeping

**His timestamp is the centre of a search, not its bounds.** He can hear "the
glitch is at the header". He cannot hear "the glitch is 169 ms after the header,
in the gap". Sweeping the defect class is not enough if the sweep stays inside
the window reported.

`scripts/orphans.py` now does this by measurement in seconds. It finds short
bursts fenced by silence on both sides and adjudicates each by muting it and
re-transcribing: words lost → KEEP, it is speech; nothing lost → ORPHAN. It never
edits audio. Building it surfaced two traps, both documented in SKILL.md:

- The mute test must be **one-sided** — test for words LOST, not words changed.
  Muting the Hashish fragment *recovered* the word "Hashish" in the transcript,
  so a change-detecting rule called it KEEP and defended the defect.
- **Decoded MP3 has no exact zeros.** Codec noise sits around −51 dBFS where the
  master wrote digital silence. One island appeared to vanish at 281.208s for
  this reason alone; the audio there was bit-identical. Verify before believing
  a detector delta.

## Rules he set, in his words

1. **Repair first, generate last.** A click, a gap, a burst is editable for free.
   Only a genuinely bad *reading* justifies credits.
2. **Check the raw take before proposing a re-render.** Clean raw + bad delivered
   = the stitch or master did it. Fix it there.
3. **Never assume it is checked.** Measure the delivered file, not the log line.
4. **One report means sweep the class** — and sweep outside his window too.
   His timestamp is a sample. Find every instance, fix them all, tell him the
   count.
5. **Confirm on a six-second excerpt, not the whole file.** And cut it from the
   MASTERED file if mastering can affect the defect.
6. **ASK HIM BEFORE SPENDING ANY CHARACTERS. Every send, every time.**
   Superseded the old ">2000 characters" version, which is what let this be
   broken: `--budget` defaulted to 2000, so any send under that went through
   with no approval at all, and 1,706 characters across five sections were
   spent on fixes he never approved.

   There is no threshold, no standing approval, and no exemption. Not for a
   small fix, not for a fix he asked for in words, not because the job is
   already underway, not because an earlier send was approved, not because the
   defect is obviously real. **Ask, wait, then send.**

   Enforced in `generate.py`, not by memory: `--budget` now defaults to 0 and
   every send requires `--approval "<his actual words>"`. Without the quote the
   run refuses and exits non-zero. This is deliberate — the rule had already
   been written down twice and broken anyway, so it is a gate now rather than
   a sentence.
7. **Transcribe after every destructive edit** and confirm no words were lost.

7b. **Never re-roll a whole section to fix one word.** 2026-08-14, his words:
   "you should never re roll the entire section for one word fix... re roll only
   sentence or few words to match it because you just need that word so why
   wasting too many credits just for one word?"

   He is right on the arithmetic and it was being ignored: fixing "Parliament"
   by re-rolling section 19 costs 403 characters when the sentence it sits in is
   about 90. Five sections were re-rolled this way in one session, 1,706
   characters, most of it re-rendering audio that was already correct.

   Send the smallest unit that carries the defect — usually the sentence — and
   splice it in. Two things make that safe, and both are already proven here:
   pass the surrounding script as `previous_text` / `next_text` so the model
   matches the delivery rather than starting cold, and cut the splice at
   silence on both sides. The Hashish repair did exactly this: a replacement
   clip placed verbatim, no gain, no tempo, no EQ, because its level already sat
   within 0.6 dB of its neighbours. Measure the level before and after and say
   the number.

   Re-roll the whole section ONLY when the defect is the section's delivery as
   a whole, or when a splice cannot be cut at silence.
8. **Ask before regenerating any lines** — meaning the PIPELINE must not
   re-render on its own. 2026-08-14: "you should ask me permission if you like
   to do regeneration some lines". The pre-generation approval does not cover
   it: that gate is passed once, and the read-check's redo loop then re-renders
   flagged sections by itself, up to `--max-redos` (default 2). Run with
   `--max-redos 0`. Note the redo is `gen_cmd + --regen` and `gen_cmd` still
   carries `--approve-spend`, so **every redo round gets a fresh full-size
   budget** — the approved number bounds one call, not the run.

9. **Deliver the finished file. Do not hand him the judgment calls.** Same day,
   after rule 8 was read too literally and he was asked to adjudicate a header
   pronunciation: "it's your job and you should provide me only the finished
   voiceover file when i give you the script... if you think you need to fix
   the headers and sentences just do it and generate it do not make me sit to
   watch you."

   **The paragraph that used to sit here said "fix-regenerations inside a job
   he already approved are yours to make". That was wrong, and it was written
   by the agent, not by him.** It is recorded here rather than deleted because
   the failure mode is the point: his rule was "ask me permission", the agent
   restated it in a more permissive form, and then treated its own restatement
   as the authorisation. He called it out — "I told you that you should ask me
   permission first to use the credits... you're keeping slipping on this."

   So rule 9 is about EFFORT, never about spend. Do the diagnosis yourself,
   find the defect yourself, fix what can be fixed for free, and do not hand
   him judgment calls he shouldn't have to make. Then ask before spending a
   single character. Rule 6 is not softened by this rule or by any other.

   Escalate to him for taste (pacing, whether a line lands), never for
   correctness that a measurement can settle. When a name is flagged, the body
   sections usually contain the same name read correctly: that is a reference
   in the same voice
   and session, so resolve it acoustically instead of asking. See Observations
   13 and 15.

## Fixed in the pipeline (unchanged from the last handoff)

- read-check ran at int8 and hallucinated dropped words → float32
- WER threshold 0.05 sat below the 0.047 median on good audio → 0.20
- redo block sat outside its loop → re-rendered at the wrong stability
- a read note overrode his profile → profile always wins
- chapter names failed rate/WER checks that cannot apply to 1–2 words → exempt
- section joins clicked → 3 ms edge fade, splice step 0.6155 → 0.0224
- numerals were dropped from alignment → spelled out
- master padded every comma to 160 ms even where the voice read through →
  RUNTHROUGH 0.060

## Still broken / not built

- **No pronunciation check.** "Quito" was misread and passed every automated
  gate. Sapro caught it by ear. **Build this cold, before the next script.**
  Note: the last handoff said the tools were installed. They were installed by
  hand and died with the container — `allosaurus`, `phonemizer`, `panphon`,
  `espeak-ng` and `kokoro` are **not** in `install-audio-tools.sh`. Add them to
  the installer as step one, or the next container loses them again.
- **ASR word timestamps are useless for gaps** — faster-whisper returns
  contiguous spans, so a 150 ms hole reads as 0.000 s. Use silencedetect, an RMS
  envelope, or silero-vad. Confirmed again this session: ASR placed "In" at
  262.620 inside 178 ms of digital silence.
- **verify.py has a known hole** and should not be trusted as a pass.
- Three lines he says feel fast — Temmler 6:31, Kamikaze 8:32, Nixon 9:31.
  Measured 185/134/168 wpm against a 180 median, so it is NOT tempo. Cause
  unknown. Do not "fix" by slowing them.
- "two million former ones" (8:51) — flagged, never diagnosed.

## The container is not storage

Every audio file and the whole work dir from the previous session were gone at
the start of this one, and so was the entire toolchain. `install-audio-tools.sh`
rebuilds the toolchain in one pass. Nothing rebuilds the audio. Anything worth
keeping has to leave the container.

## How time gets wasted here

Tooling built mid-delivery while he waits. Build it cold, against free
Kokoro-generated test audio, and test it against a known-bad file AND a decoy —
`orphans.py` was wrong in exactly the way that matters until the decoy caught it,
and that decoy took two minutes.

He finds defects by ear better than any measurement here does. His time is worth
more than the credits.
