# ExplainTory Voiceover — Standard Operating Procedure

Script text in, mastered `<Title> (final).mp3` out. This file describes what the
exported code **actually does**. Every number below was read from the code in
`skills/`, not from the skill prose, and the places where the prose disagrees
with the code are listed in section 10.

**Tags (item 7).** Every setting is tagged:

- **GENERAL**: would apply to any channel (loudness standard, file format, safety
  gates, engineering repairs).
- **CHANNEL TASTE**: chosen for ExplainTory (voice, pacing, gaps, EQ, tempo).
  Anything uncertain is tagged CHANNEL TASTE.

---

## 0. What is in this folder

| Path | What it is |
|---|---|
| `config/voice-calibration.json` | **The locked voice profile.** Voice ID, model and all five voice settings. Copied unchanged. Contains no key. |
| `config/profile.example.json` | Template for the profile shape. Its values are placeholders, **not** the channel's. Copied unchanged. |
| `config/lexicon.example.json` | Template for the pronunciation lexicon. **Not used by default.** Copied unchanged. |
| `skills/explaintory-voiceover/scripts/` | Generation, read-check, repair tools. `voiceover.py` is the entry point. |
| `skills/explaintory-vo-master/scripts/humanize.py` | Pause insertion, cleanup, EQ, de-ess, loudness. This is the mastering stage. |
| `skills/*/SKILL.md` | The two original skill files, for background. Where they disagree with this SOP, the code (and this SOP) wins. |
| `reference/HANDOFF.md` | The owner's rules in his own words (spend approval, repair-first, and so on). |
| `test/test_script.txt` | The test script used in RUN.md. |

**Where the rules live.** Only the voice settings are stored as JSON. There is **no
JSON file for gap lengths or read-aloud rules.** Those are constants in the code:

- gaps at the stitch: `PAUSE_PRESETS` in `script_prep.py`
- gaps in the master: `DEFAULTS` and `RUNTHROUGH` in `humanize.py`
- read-aloud rules: `_classify()` / `detect_structure()` in `script_prep.py`

To change a gap you edit the code, or for the master's gaps you pass a flag
(`--comma`, `--sentence`, `--paragraph`, `--tail` on humanize.py). `voiceover.py`
does not pass those flags through.

---

## 1. ElevenLabs voice

Source: `config/voice-calibration.json`, loaded by `generate.load_profile()`.

| Setting | Value | Tag |
|---|---|---|
| Voice ID | `dUHbvtIZto0ZEBkhYiyk` | CHANNEL TASTE |
| Model | `eleven_multilingual_v2` | CHANNEL TASTE |
| stability | **0.48** | CHANNEL TASTE |
| similarity_boost | **0.80** | CHANNEL TASTE |
| style | **0.05** | CHANNEL TASTE |
| use_speaker_boost | **true** | CHANNEL TASTE |
| speed | **1.07** | CHANNEL TASTE |
| Request output format | `mp3_44100_128` (44.1 kHz, 128 kbps MP3 per section) | GENERAL |
| Request timeout | 180 s | GENERAL |
| Retries | 4 attempts on 429/500/502/503/504, backoff 2 s, 4 s, 8 s | GENERAL |
| `pronOn` | false: pronunciation respelling is **off** | CHANNEL TASTE |

**Code fallbacks when a field is missing from the profile** (tagged GENERAL, since
these are the ElevenLabs defaults and not the channel's values): stability 0.50,
similarity_boost 0.75, style 0.0, speed 1.0, speaker boost true. `voiceover.py --plan`
marks every value as `(profile)` or `(default)`. **Anything marked `(default)` was
not chosen by anyone.** Today exactly one is: `readTitle` (true).

**Environment overrides. Check these before every run.** `ELEVENLABS_VOICE_ID`
and `ELEVENLABS_MODEL` in the environment **override the profile** without any
warning in the log. Unset them unless you mean to change the voice.

**Conditioning (how sections sound continuous)**, all GENERAL mechanics mirrored from
the owner's Voiceover Studio:
- `previous_text`: the last 300 characters of the previous section
- `next_text`: the first 300 characters of the next section
- `previous_request_ids`: request IDs of the last 3 sections
- For the section right after a chapter heading, `previous_text` and
  `previous_request_ids` are **dropped**, so the narration starts fresh instead of
  continuing the heading's sentence. `next_text` is still sent. CHANNEL TASTE.

**Re-render stability nudge.** This happens only with `--auto-redo`, which is off by
default. Redo round 1 is a plain re-roll. Each later round raises stability by
+0.05 per round, capped at 1.0. CHANNEL TASTE.

---

## 2. How script text is prepared before sending

The short version: **almost nothing is rewritten.** The text goes to ElevenLabs as
written, apart from structural cleanup. `eleven_multilingual_v2` decides how to say
numbers, dates and abbreviations.

| Item | What happens | Tag |
|---|---|---|
| **Numbers** | **Not converted.** Digits are sent as digits and the model voices them. (The master spells digits out *only* for alignment, e.g. `1547 → "fifteenfortyseven"`. That never changes the audio.) | CHANNEL TASTE |
| **Years / dates** | **Not converted.** Sent as written. They affect *pauses* only (see §4, post-date beat). | CHANNEL TASTE |
| **Abbreviations** (BC, AD, U.S., M16) | **Not expanded.** Sent as written. `BC/AD/BCE/CE` count as a "date" for the post-date pause. A single capital + period (`A.`) is not treated as a sentence end by the master. | CHANNEL TASTE |
| **Foreign names** | **Sent as written** (`pronOn: false`, the owner chose raw over respelled). Respelling happens only if you pass `--lexicon file.json`: whole-word, applied to the sent text only, never IPA (the model ignores phoneme tags). No lexicon is used by default. `lexicon.example.json` is an example, not a live list. | CHANNEL TASTE |
| **Pronunciation guide** at the end of the script | A heading that says *pronunciation / pronounce / how to say / say it*, followed by `Name — RES-pel-ing` lines. It is **removed from the narration** and saved to `<work>/pronunciation_guide.json` as a *reference for checking*, not for substitution. | CHANNEL TASTE |
| **Pre-flight check** (free, before spending) | Warns when a guide headword is missing from the narration, and when there is an orphaned decimal such as `British. 303` (a Google Docs export artifact that makes the voice read a sentence break and "three hundred and three"). **Fixing it is manual.** | GENERAL |
| **Markdown emphasis** | `**bold**`, `_em_`, `*italic*` are stripped. | GENERAL |
| **Title (H1)** | The first `# Title` or `Title:` line within the first 12 lines is the video title. Suffixes like "— Voiceover Script", "— Draft", "— v2" are stripped. It is **read aloud as section 1** (`readTitle` true, inherited default). It names the output file. | CHANNEL TASTE |
| **Section headings** | Read aloud as chapter announcements, each in **its own TTS request**, with a period added (`## Coca` → "Coca."). `skipHeadings: false`. | CHANNEL TASTE |
| — what counts as a heading | Any `#`–`######` line; `Section/Part/Chapter/Act/Scene/Segment N: Name` (only "Name" is spoken; a bare "Section 3" is silent); `3. Name` (≤60 chars, ≤8 words, no end punctuation); ALL-CAPS line ≤60 chars without end punctuation; a line ending in `:` (≤60 chars, ≤8 words, colon removed); a Title-Case line (≤60 chars, ≤8 words, no end punctuation) after a blank line, a sentence end, or another heading/direction. | GENERAL (structure parser) |
| — silent labels | `Intro, Outro, Hook, Conclusion, Opening, Closing, CTA, Title, The End, Script, Voiceover Script, VO Script, Body, Full Script`, as a heading or a bare line: **never spoken**, but they force a new TTS request. | GENERAL |
| **Stage directions** | `[SFX: …]` and `*pause*` lines (≤80 chars) are **dropped**. | GENERAL |
| **Dividers** | `---`, `***`, `===`, `~~~`, `——` are **dropped**. | GENERAL |
| **CTA lines** | Lines matching subscribe / like / bell / comment phrases start their own request, with a pause before (§4). | CHANNEL TASTE |
| **Read note** | A block near the top titled READ NOTE / Note to narrator / Delivery note, and so on (within the first 40 lines, running to the next divider or heading) is **removed**. A note asking for "no pause" after chapter names is logged but **not obeyed**. The profile wins unless you pass `--chapter-style run-on`. | CHANNEL TASTE |
| **Appendices** | Everything from a heading starting *animator / animation / art / visual / thumbnail / production / reference / source / research / accuracy* onward is **removed**. | GENERAL |

---

## 3. Chunking and joining

**Chunking** (`script_prep.split_script`). The tag is CHANNEL TASTE, because 450 is
the studio's chosen sweet spot.
1. Split on blank lines into paragraphs.
2. A paragraph over **450 characters** (`chunkSize`) is split at sentence ends. A
   single sentence over 450 is split at the last space before 450.
3. Units are merged greedily back up to 450 characters, joined with a blank line.
   **Never split mid-sentence** unless one sentence exceeds 450.
4. A chapter heading always starts a new request **and** is sent alone. The next
   narration starts a new request. CTAs and silent labels also force a new request.

**Joining** (`generate.stitch`):

| Step | Value | Tag |
|---|---|---|
| Decode each section MP3 | 48 kHz, mono, 16-bit | GENERAL |
| Edge fade on every section, both ends | **3 ms** linear (prevents join clicks) | GENERAL |
| Silence between sections | exact digital zeros, lengths in §4 | CHANNEL TASTE |
| Heading rate levelling | **ON** when run through `voiceover.py`. Measures every chapter announcement in syllables/second over its spoken span. A heading more than **12%** off the median of the *other* headings is time-stretched toward it, clamped to **×0.85–×1.18**. Needs ≥3 headings. | CHANNEL TASTE |
| Output | `<work>/raw_stitched.wav`, 48 kHz mono 16-bit PCM | GENERAL |
| Truncation check | the stitch file's duration must be ≥90% of the expected end time (sections plus inserted silence), or the run stops | GENERAL |

---

## 4. Every gap length

Gaps are set in **two separate stages**, and both add silence. The first stage
inserts silence at section joins. The master then tops up silence at punctuation.
Neither stage ever **shortens or removes** a pause.

### 4a. Stitch stage: silence inserted between TTS sections (`PAUSE_PRESETS`, preset `natural`)

This silence is added **on top of** the ~0.2 s the model renders at each section edge.

| Where | Inserted | Tag |
|---|---|---|
| **Before the first line** | **0.00 s**. Nothing is inserted. Only whatever lead silence ElevenLabs rendered is there (about 0.2 s, not controlled or measured). The master adds none. | CHANNEL TASTE |
| Before a chapter heading | **0.22 s** | CHANNEL TASTE |
| After a chapter heading (before its first line) | **0.30 s** | CHANNEL TASTE |
| Before a CTA section | **0.30 s** | CHANNEL TASTE |
| Between ordinary body sections | **0.00 s** (the model's own edge silence only) | CHANNEL TASTE |
| Other presets (not used) | `tight` 0.10 / 0.18 / CTA 0.20; `wide` 0.40 / 0.55 / CTA 0.55 | CHANNEL TASTE |

Measured on a delivered master, `natural` finishes at about **0.33–0.41 s before** a
chapter name and **0.39–0.57 s after** it (code comment in `script_prep.py`).

### 4b. Master stage: true-silence targets at punctuation (`humanize.py DEFAULTS`)

Each target is a **minimum amount of true silence** (10 ms frames under −45 dB). The
silence is measured from `max(previous word end, next onset − 0.35 s) − 0.05 s` to
`next onset + 0.05 s`. Inserted =
`max(0, target − measured)`.

| Boundary | Target | Tag |
|---|---|---|
| **Comma**, `;` or `:` | **0.16 s** | CHANNEL TASTE |
| "Run-through" rule | if the voice left **< 0.060 s**, **nothing is added**. Applies to every 0.16 s beat (comma, post-date **and** curated), because the code treats all three as "comma". Not applied to sentence or paragraph. | CHANNEL TASTE |
| **Post-date beat** (a number or BC/AD followed by a non-number, e.g. "In 1547 ‖ the viceroy") | **0.16 s**. Skipped inside a date range ("between 1547 and 1550"). | CHANNEL TASTE |
| **Curated clause break** (`--curated` file, `wordA|wordB`) | **0.16 s** | CHANNEL TASTE |
| **Sentence** end (`. ! ?`, not `A.`) | **0.21 s**. The run-through rule does not apply. | CHANNEL TASTE |
| **Paragraph** (new script line) | **0.25 s**. Skipped where either line is a "card" (≤5 words, no end punctuation). In this pipeline headings get a period added, so they are *not* cards and get the 0.25 target. They already carry ≥0.33 s from 4a, so in practice nothing is added. | CHANNEL TASTE |
| **Section heading** | no separate value. It gets 4a's inserted silence plus the paragraph target above. | CHANNEL TASTE |
| Within a sentence (no punctuation) | **never touched** | CHANNEL TASTE |
| **Tail** after the final line | **1.00 s** appended | CHANNEL TASTE |
| Cut placement | at the minimum-energy point within the 0.30 s before the next word onset (never mid-gap), with **4 ms** fades on every cut chunk | GENERAL |

The human reference these came from: longest pause anywhere 0.43 s, silence 7.8%,
181 wpm overall.

---

## 5. Post-processing (mastering), in order

All in `humanize.py`, called by `voiceover.py` with its defaults plus `--curated`.
`--max-wpm` is off.

| # | Step | Exact settings | Tag |
|---|---|---|---|
| 1 | Decode | 48 kHz mono float32; 16 kHz copy for alignment | GENERAL |
| 2 | QC report (log only) | flags clip at sample peak ≥ 0.999 (≈ −0.009 dBFS), hot > −1 dBFS, DC > 0.001, noise range < 35 dB, sub-60 Hz rumble, sibilance ratio > 1.2 | GENERAL |
| 3 | **Declip** | runs with \|x\| ≥ 0.95 rebuilt by cubic fit over 8 samples either side | GENERAL |
| 4 | **Splice-fragment cleanup** | removes bursts ≤ 0.25 s, above −50 dB, ≥15 dB over silence on both sides, within 50 ms of a digital-silence edge; 2 ms fades. `--keep-glitches` disables it. | GENERAL |
| 5 | Forced alignment | torchaudio MMS_FA, 40 s chunks, 2 s overlap. **Aborts** if the implied rate is outside 90–260 wpm, or mean confidence < 0.55, or > 25% of words < 0.4 | GENERAL |
| 6 | **Tempo** | adaptive: each sentence (≥5 words) sped up by **×1.04**, but never past **250 wpm**. Shorter sentences and the final chunk are not stretched. `--uniform-tempo` = one global 1.04. | CHANNEL TASTE |
| 6b | Sentence rate levelling | **off** (`--max-wpm 0`). If requested: never within the first 25 s, max slowdown ×0.87, start at 290, not 250. | CHANNEL TASTE |
| 7 | **Pause insertion** | §4b | CHANNEL TASTE |
| 8 | **EQ** | 2047-tap linear-phase FIR matched to the channel's human stem. Curve points (Hz, dB): 40 0 · 63 +1.3 · 80 +3.4 · 101 +4.8 · 143 +1.5 · 254 −0.8 · 285 −2.0 · 403 +1.7 · 570 −2.4 · 806 0 · 1613 +0.8 · 2560 +1.9 · 3620 +5.0 · 5747 +6.0 · 7241 +5.7 · 9123 +4.1 · 11494 +6.0 · 12902 +6.0 · 14482 +4.6 · 16255 0 (full 54-point table in `humanize.py` `EQ_CURVE`) | CHANNEL TASTE |
| 9 | Exciter ("air") | **off** (`air 0.00`, approved 2026-07-29). The `classic` mode is selected but inactive at 0. | CHANNEL TASTE |
| 10 | **High-pass** | 3rd-order Butterworth, **55 Hz** | CHANNEL TASTE |
| 11 | **De-esser** | band 5.2–9.5 kHz; ratio threshold 0.42, gain law (0.42/ratio)^0.55; sibilant env 1 ms attack / 40 ms release, full-band env 5 / 150 ms; max reduction to ×0.45 (≈ −6.9 dB); gain smoothed at 120 Hz | CHANNEL TASTE |
| 12 | Write intermediate | 16-bit WAV, hard clip at ±1 | GENERAL |
| 13 | **Loudness** | ffmpeg `loudnorm=I=-14:TP=-1.5:LRA=7:linear=true` → **−14 LUFS integrated, −1.5 dBTP true-peak ceiling** | GENERAL |
| 14 | Final QC | same as step 2, run on the delivered file (log only) | GENERAL |

There is **no separate limiter**. The −1.5 dBTP ceiling comes from `loudnorm`'s
true-peak control only.

---

## 6. Output

| Item | Value | Tag |
|---|---|---|
| File name | `<Title> (final).mp3` in `--out-dir`. Title = `--title`, else the H1, else the file name. Characters matching `[^\w\-. ]` are removed (so letters, including Unicode letters, digits, `_`, `-`, `.` and space are kept), runs of whitespace become one space, and the name is capped at 80 chars | CHANNEL TASTE |
| Codec | MP3 (libmp3lame), **256 kbps** CBR | GENERAL |
| Sample rate / channels | **48 kHz, mono** | GENERAL |
| Working folder | `<out-dir>/.vo_<Title_with_underscores>/`, holding `parts/sec_NNN.mp3` (each TTS take), `parts/request_ids.json`, `raw_stitched.wav`, `sections.json`, `script_lines.txt`, `narration_source.txt`, `readcheck.json`, `align.json`, `pauses.csv`, `spend.json`, `pronunciation_guide.json` | GENERAL |
| Resume | `--from generate / check / master`. Takes already on disk are reused and not re-billed. | GENERAL |

---

## 7. Word timings

**The pipeline does not produce word timings for the final MP3.** What exists:

| File | Content | Timeline | Usable as final timings? |
|---|---|---|---|
| `align.json` | `{"key", "words": [{"line", "w", "s", "e", "score"}]}`: MMS_FA forced alignment, one entry per script word, seconds, 3 decimals | the **raw stitch**, before tempo and pause insertion | **No.** It drifts from the final by the tempo change plus every inserted pause, often seconds by the end. |
| `sections.json` → `marks` | `{index, start, end, retimed}` per TTS section | raw stitch | No |
| `pauses.csv` | `time, kind, silence_before, target, inserted, context` per inserted pause | raw time × 1.04 (approximate) | No. It ignores earlier inserted pauses. |
| `readcheck.json` | per-section WER, wpm, problems, `heard` text. Word times are used internally but **not saved** | per section | No |

ElevenLabs' `/with-timestamps` endpoint is not used. If captions or edit timings are
needed, re-align the **final MP3** against `script_lines.txt` as a separate step. No
such step exists in the code today.

---

## 8. Read-check (after generation, before mastering)

All GENERAL (measurement gates), with thresholds tuned on this channel's audio:
faster-whisper `distil-large-v3` at **float32** (int8 invents errors), OpenAI
English normalizer, jiwer WER. Flags a section on: WER > **0.20**; a dropped or
duplicated run; a confident single-word substitution; ≥3 consecutive words at
confidence < 0.45 (slurred); rate outside **120–240 wpm** *with* a transcript
mismatch; ≥ **0.7 s** dead air inside a section; peak ≥ −0.1 dBFS. Sections of ≤3
words (headings) are exempt from WER/rate. A word that reads the same wrong way on
two takes is "settled": not re-rendered again, listed as *worth a listen*.

**Flagged sections are reported, not re-rendered** (`--max-redos 0`). Re-rendering
needs new approval (see RUN.md).

## 9. Spend gate (GENERAL safety, owner's hard rule)

`generate.py` refuses to send **any** characters without `--approval "<the owner's
actual words>"`. An earlier approval does not carry over. Above **1,000** characters
it also needs `--approve-spend N`. `N` is a ceiling for the **whole run**, including
redo rounds, tracked in `<work>/spend.json`. Without approval, the tool prints the
exact sections and character count it would send, then stops.

## 10. Where the docs and the code disagree (the code is what runs)

1. **Two `humanize.py` copies existed.** The export uses the repo copy
   (`.claude/skills/explaintory-vo-master/scripts/`), which is **newer** than the one
   shipped with the synced vo-master skill. It adds digit spelling for alignment, the
   60 ms comma run-through rule, and no post-date beat inside date ranges. When run
   from the repo, `voiceover.py` resolves to this copy first.
2. vo-master SKILL.md says "global tempo +4% (atempo=1.04)". The code default is
   **per-sentence** 1.04 capped at 250 wpm.
3. vo-master SKILL.md says "4 ms fades at splices". True for master cuts; **section
   joins use 3 ms**.
4. HANDOFF says the approved `FINAL v11.mp3` was **320 kbps**. The code writes
   **256 kbps**. v11 was hand-edited after the pipeline.
5. voiceover SKILL.md says the last delivery ran with `--no-level-headings`, but
   `voiceover.py` **has no such flag**, so heading levelling is **on** in the
   one-command run. RUN.md shows how to turn it off.
6. `voiceover.py --approve-spend` help text says "default ceiling is 2000". The
   actual default in `generate.py` is **1000**.
7. voiceover SKILL.md quotes chapter gaps as "~0.45 s before / ~0.50 s after". Those
   are finished figures from an old version. The **inserted** values are
   0.22 / 0.30 (§4a).
8. `vo-studio/` (a separate Windows app using the local Chatterbox TTS) is **not
   included**. It has never run end-to-end, and its ElevenLabs fallback settings
   (0.55 / 0.85 / 0.10) are **not** the locked profile.

## 11. Changes made for this export

Exactly one code change: `generate.py` now reads the API key **only** from
`ELEVENLABS_API_KEY`. The original also accepted an `api_key` field in the profile
JSON. That fallback is removed, and a profile containing `api_key` is now refused.
Every other file is a byte-for-byte copy.
