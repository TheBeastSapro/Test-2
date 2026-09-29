---
name: explaintory-vo-master
description: Run the full ExplainTory voiceover QC and mastering pipeline on a raw AI voiceover, and deliver the finished audio. TRIGGER IMMEDIATELY on "QC vo", "QC voiceover", "QC the vo", "humanize the voiceover", or any submission of an AI/TTS voiceover file with its script. Also use for questions about VO pauses, commas, gaps, speaking rate, clipping, splice glitches, or mastering for the ExplainTory YouTube channel.
---

# ExplainTory VO Master

**When Sapro says "QC vo" or "QC voiceover" and attaches a voiceover, do the whole job
without asking follow-up questions, and deliver the finished MP3.** He supplies the audio
and the script; everything else is already decided and lives below.

Deliver: the mastered MP3 named `<Video Title> (final).mp3`. Nothing else unless asked.
Report the QC findings, the runtime, and the wpm/silence figures against the human
reference. Do not ask which settings to use -- the defaults are the approved sound.


# ExplainTory VO Master

Turns a raw TTS voiceover into a paced, studio-mastered file matching the ExplainTory
human-read profile. Inputs: **the AI voiceover audio + the script text.** Nothing else.

All settings here were derived by force-aligning the channel's real human VO stem
(*Weirdest Weapons*, 12:17.6, pre-music) and validated by ear over several rounds.

## Locked settings

Target **true silence** — not the aligner's word gap. See "The measurement trap" below.

| Boundary | Target |
|---|---|
| Comma / post-date / clause break | 0.16 s |
| Sentence end | 0.21 s |
| Paragraph break | 0.25 s |
| Section / era card | leave alone (already ~0.45 s) |
| Within a sentence | never touch |
| Tail after final line | 1.00 s |

Global tempo **+4%** (`atempo=1.04`). **No punchline time-stretching** — the human
accelerates into punchlines, so slowing them is wrong.

## Runbook

`scripts/humanize.py` does the whole job in one call. Do not rebuild the pipeline by hand.

1. `pip install numpy scipy --break-system-packages` and
   `pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu --break-system-packages`
   (ffmpeg must be on PATH; first run downloads the MMS_FA model, ~1 GB, then cached)
2. Write the script to a text file, **one paragraph per line**.
3. **Read the script for missing-comma clause breaks** and write them to a curated file,
   one `wordA|wordB` pair per line. Script-specific, needed every time. Dates are already
   automatic. spaCy can generate candidates but is wrong about a third of the time — it
   wants a pause inside "growing on a deck ‖ that also mounted a catapult". Generate with
   it, decide by reading.
4. ```
   python3 scripts/humanize.py --audio vo.mp3 --script script.txt \
       --out final.mp3 --report pauses.csv --curated breaks.txt
   ```
5. Deliver the MP3.

Takes 2–3x realtime, dominated by alignment. Run it in the background; log lines are
prefixed `[humanize]`.

**Defaults are the approved sound — do not change them without the user listening.**
`--exciter local` exists and is technically cleaner in quiet passages, but it is a
different top end and has not been signed off. Classic is the default for a reason.

The tool aborts with a non-zero exit if the script does not match the recording
(implied wpm outside 90–260, or alignment confidence under 0.55). A healthy run
reports something like `186 wpm | mean confidence 0.90 | 5% weak`.

It also removes **splice fragments** automatically: TTS rendered per segment and
butt-joined leaves detached scraps of an already-spoken phoneme next to the join —
a 35 ms second copy of the /s/ in "Ages" that reads as a tick. Only fragments both
isolated by silence AND within 50 ms of a hard digital splice are cut; ordinary short
fricatives mid-sentence are left alone. `--keep-glitches` disables it.

**Expect one round of ear-checking on pause values.** The user's ear has repeatedly
caught problems the measurements called fine.

## The measurement trap

**A gap is not silence.** Forced alignment ends words early, so the gap between aligned
words is only ~65% silent, and the fraction varies wildly — after "BC," a 0.26 s gap held
**0.04 s** of real silence and the comma vanished. Inserted padding is 100% silence.
So: target true silence, measured **per boundary**, in the last 0.35 s before the next
word onset — not across the whole gap, which would span unaligned digits.

Cut points go at the minimum-energy frame within 0.30 s **before the next word onset**,
never mid-gap. A mid-gap cut lands inside spoken numbers — it put silence inside "K22"
and "K14" in an early pass. Use 4 ms fades at splices.

## Boundary detection — three rules

1. **Script punctuation**, read from the script text, *not* the aligned token list.
   Pure-digit tokens drop out of alignment and take their punctuation with them, which
   hid three real sentence ends ("France fell in 1940.", "…in the water in 1873.").
2. **Post-date**: a number or BC/AD followed by a new phrase with no comma —
   "In 255 BC ‖ a returning fleet", "…around 240 BC ‖ for Hiero".
3. **Curated clause breaks** the script forgot — "At Angolpo ‖ the Japanese lost…",
   "Below the garden ‖ sat a temple" (that one had 0.00 s).

## Human reference (measured)

Overall 181 wpm · articulation 197 wpm · silence 7.8% · **longest pause anywhere 0.43 s**
(none above 0.45) · LRA 1.6 LU · median sentence 200 wpm.
Fastest sentences are the punchlines: 290 wpm "A weapon this strange should have been a
footnote", 283 "A cart full of fireworks had done the work of an army".

## Do not repeat these mistakes

Every one came from an audio model *describing* the video instead of measurement.
**Never treat listening-model timing as data.**

- "Human pauses are 0.8–1.0 s" — real max 0.43 s
- "Human silence is 10–12%" — real 7.8%
- "Add 60–80 s of silence" — real answer ~30 s
- "AI is flat at LRA 1.8 vs the human" — the human is 1.6, flatter
- "Slow it from 177 to 155–165 wpm" — the human runs 181/197; the AI was too slow
- "The AI accelerates into punchlines where the human decelerates" — the human accelerates too
- "The published video has a music bed" — it does not, uploads are clean VO

## Channel context

Best-retaining videos are shorter: Military Units ~11:11 (41.9% AVD), Napoleon ~11:59
(39.1%), vs Weirdest Weapons 12:21 (30.4%). To get back into that band, cut script — not
tempo. The read is already at the channel's natural rate.

The user's own master clips at +1.2 dBFS; recommend a −1 dBTP limiter on their export chain.
