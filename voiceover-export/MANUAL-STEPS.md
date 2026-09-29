# What is still done by hand or checked by ear

The code runs generate → read-check → master in one command. Everything below is
**not** automated. Each item is tagged by who has to do it.

## Decisions a person makes (the owner)

1. **Approving every spend.** `--approval` must quote the owner's actual words for
   *each* send, including re-renders and single-sentence fixes. There is no standing
   approval. `generate.py` enforces the presence of the quote but cannot check that it
   is genuine. That part is on the operator.
2. **Confirming the plan.** Checking the chapter list and the character cost from
   `--plan` before anything is spent.
3. **Taste calls.** Whether a line lands, overall pacing, whether a heading sounds
   right. Escalate taste, never correctness that can be measured.
4. **Confirming a fix on a ~6-second excerpt** (before/after, cut from the stitch or
   from the master if mastering affects the defect) before the full file is re-mastered.
5. **Video length.** Retention is better on shorter videos. That is fixed by cutting
   the script, never by changing tempo.

## Done by hand by the operator (Claude)

6. **Curated clause breaks.** `--suggest-breaks` gives candidates that are wrong about a
   third of the time. Each is kept or deleted by reading, and missing ones are added.
   Needed for every script.
7. **Script export artifacts.** The pre-flight *warns* about an orphaned decimal
   (`British. 303`) or a guide name missing from the narration. The script is fixed by
   hand.
8. **Pronunciation.** The lexicon is off by default. Whether a "consistent across takes"
   word is a real mispronunciation or just ASR spelling a name its own way is a
   judgement, settled by comparing against the same name read correctly elsewhere in the
   file (`pick_take.py` did this once; it has hard-coded paths and is a one-off
   example, not a tool). Only then is a lexicon entry written.
9. **Re-rendering flagged sections.** The read-check reports them and does not
   re-render. The operator diagnoses first: raw take clean + delivered file bad =
   stitch/master fault, which is fixed for free. If the take itself is bad, the
   operator re-renders only the **sentence** (`regen_span.py`) after a new approval.
10. **Running the delivery gates.** `orphans.py` and `verify.py` are not called by
    `voiceover.py` and must be run manually on the final MP3.
11. **Sweeping the defect class.** When the owner reports a glitch at a timestamp, every
    other instance of the same signature is found across the whole file, including
    outside the reported window, and the count is reported back.
12. **Transcribing after every destructive edit** (any cut or mute) to prove no word was
    lost. Nothing does this automatically except `regen_span.py`'s own self-check.
13. **Heading levelling on/off.** It is on in the one-command run. The last approved
    delivery had it off (see RUN.md). Check what it would change before accepting it.

## Checked by ear, because no reliable detector exists

14. **Correctly-read words that sound wrong:** echo, doubled tail, "robotic",
    "sounds like a separate word". The read-check compares audio to the script, so it
    structurally cannot see these. Helpers exist but do not settle it:
    `echogate.py` catches about 2 of 3 known cases; `prosody_gate.py` gives false flags
    on short words ("the") and **a clean run from it is not evidence**; `oddword.py` is
    unvalidated.
15. **Pause values after mastering.** The code's own doc says to expect one round of
    ear-checking. The owner's ear has repeatedly caught pauses the measurements called
    fine (forced beats at commas the voice read through, a beat inside a date range).
16. **Lead-in silence before the first word.** It is whatever ElevenLabs rendered. Nothing
    measures or sets it.
17. **The first chapter announcement rushing.** Levelling or re-timing reduces it, but
    whether it is fixed is judged by ear.
18. **Level of a spliced-in sentence** against its neighbours. `regen_span.py` prints the
    dB difference but never applies gain. Whether it matches is judged by ear.
19. **Any `--max-wpm` levelling or `--exciter local`.** Both are off. Neither is signed off,
    and either needs the owner to listen before use.

## Not produced at all

20. **Word timings for the final file** (see SOP §7). `align.json` is on the raw
    stitch's timeline and does not match the delivered MP3.
