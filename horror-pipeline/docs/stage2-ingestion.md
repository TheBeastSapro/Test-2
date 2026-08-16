# Stage 2: script and voiceover ingestion — 2026-08-09

Implements BUILD-PACKET section 4 (4.1 parsing, 4.2 word timings, 4.3 the RMS
arbiter, 4.4 the anchor resolver), plus `align_sections.py`, which the packet
requires but does not specify. See section 6 for why.

Everything below was run for real on 2026-08-09 against a generated demo VO in
`projects/demo/`. Every number is measured. Companion document:
`stage1-asset-sourcing.md` (the images the sheet will point at).

**Why this stage exists.** The whole edit hangs off one file, `work/words.json`,
which says when every spoken word happens. Sheets never carry hardcoded seconds.
They carry "the word THIRTY, second occurrence in section 4, offset -0.05", and
this stage is what turns that into a number. Re-record the voiceover, re-run
these five commands, and the entire cut re-syncs itself.

---

## 1. The known-good command sequence

Run from anywhere. Every tool takes absolute paths and refuses relative ones,
because the shell working directory is not stable between calls.

```bash
P=/home/user/Test-2/horror-pipeline
D=$P/projects/demo

# 1. Script to sections. --vo-text also writes the narration alone, which is
#    exactly the text to hand to the voice.
python3 $P/tools/parse_script.py $D/script.md $D/work/sections.json \
        --vo-text $D/work/vo.txt

# 2. RMS first. It is the arbiter, and it costs two seconds.
python3 $P/tools/rms.py $D/vo.wav $D/work/rms.json

# 3. Word timings off the DRY voiceover, never a mix.
python3 $P/tools/transcribe.py $D/vo.wav $D/work/words.json

# 4. Section time ranges, with every suspected gap put to the arbiter.
#    Exits 2 if the VO is genuinely missing script.
python3 $P/tools/align_sections.py $D/work/sections.json $D/work/words.json \
        $D/work/rms.json

# 5. Resolve anchors. Always inside a section.
python3 $P/tools/anchors.py $D/work/words.json thirty \
        --occurrence 2 --offset -0.05 --sections $D/work/sections.json --section 1

# Re-check a suspect window with the bigger model. Timestamps come back
# absolute to the source file, so the output drops straight into a comparison.
python3 $P/tools/transcribe.py $D/vo.wav $D/work/win.json \
        --model small.en --start 52 --end 70
```

Total wall time on this container for the full chain: about 40 seconds, of which
35 to 39 is `base.en` on 150 seconds of audio. The sequence above was re-run
from an empty `work/` directory and reproduced every number in section 2.

---

## 2. Measured output

### The demo fixture

`projects/demo/script.md` is a 3 creature cut written in the voice of
`script-trevor-cannot-survive-v4.md`: Cartoon Cat, The Sewer Spider, a mid CTA,
Siren Head, an outro CTA. Two lines carry the dry joke marker. The word THIRTY
appears twice in section 1 and once in section 4 on purpose, so the section
restriction has something to get wrong.

`projects/demo/vo.wav` is Kokoro `am_michael` at speed 1.0 through
`npx hyperframes@latest tts`. 150.83 s, 24 kHz mono PCM, 7.2 MB.

### parse_script.py

```
sections : 5  (creature 3, cta 2)
  idx kind     creature/title                         lines  words  jokes
    1 creature Cartoon Cat                            17-25    112  25
    2 creature Sewer Spider                           29-37    119  -
    3 cta      MID CTA                                41-41     37  -
    4 creature Siren Head                             45-53    118  53
    5 cta      OUTRO CTA                              57-57     51  -
words    : 437 total, est 154s at 170 wpm
jokes    : 2 marked line(s) -> [25, 53]
```

Also run against the real 7 creature script as a robustness check: 9 sections
(7 creature, 2 CTA), 1551 narration words, per-section counts within 6 words of
the counts the script annotates itself with.

### transcribe.py, rms.py

```
words  : 439        span 0.00s -> 150.42s (150.4s), audio 150.8s
rate   : 175 wpm spoken          (house target is 160 to 180)
conf   : mean p 0.954, 8 word(s) below 0.5
repeats: none (no 5-gram occurs 3+ times)

windows : 301 at 0.5s hop (150.8s of audio)
level   : median -25.2 dBFS, loudest window -18.3, quietest -75.6
below -50 dBFS: 8 window(s) in 8 run(s)
          8.5-9.0s, 13.5-14.0s, 31.5-32.0s, 77.0-77.5s, 81.0-81.5s,
          101.0-101.5s, 107.0-107.5s, 124.5-125.0s
```

Every quiet run in a clean read is a single 0.5 s window. That is a breath, and
it is why `align_sections.py` needs 1.0 s of continuous floored audio before it
will call something a hole.

### align_sections.py

```
match   : 436/437 script words found in transcript (99.8%)

  idx kind     creature/title                start      end     dur  script  match  status
    1 creature Cartoon Cat                    0.00    40.36   40.36     112  100%  ok
    2 creature Sewer Spider                  40.36    81.18   40.82     119  100%  ok
    3 cta      MID CTA                       81.18    91.66   10.48      37  100%  ok
    4 creature Siren Head                    91.66   133.04   41.38     118  100%  ok
    5 cta      OUTRO CTA                    133.04   150.50   17.46      51   98%  ok

gaps    : none. Every section resolved against the transcript.
```

### anchors.py

Five resolutions against the real transcript:

| what | restriction | resolves to |
|---|---|---|
| `thirty` occ 1 | whole file | 14.920 s |
| `thirty` occ 2, offset -0.05 | section 1, 0.00-40.36 s | 28.010 s |
| `thirty` occ 1 | section 4, 91.66-133.04 s | 114.020 s |
| `forty feet` occ 1, offset -0.05 | section 4 | 108.670 s |
| `it says spiders` occ 1 | section 2, 40.36-81.18 s | 71.020 s |

Rows 1 and 3 are the whole argument for `section=`. The same word, the same
occurrence number, 99 seconds apart. A pop for Siren Head that skipped the
restriction would have landed in Cartoon Cat.

Three failure paths, all exit 4 and resolve nothing:

```
anchor 'bridge worm' occurrence 1 not found in 0.0-1000000000.0s (found 0)
anchor 'spiders' occurrence 1 not found in 91.7-133.0s (found 0); 2 occurrence(s)
  exist OUTSIDE this range, so either the section restriction is doing its job or
  the range is wrong
anchor 'thirty' occurrence 9 not found (found 3); 3 occurrence(s) exist in the
  whole file, so the occurrence number is too high
```

`--batch` resolves a whole sheet's worth at once and fails the entire batch on
one miss. There is no partial resolve, on purpose.

---

## 3. The arbiter, proved both ways on real audio

Two variants of the demo VO were built with ffmpeg and put through the full
chain. `work/failure-tests/` holds both.

**Test B, the voiceover really is missing script.** 55 to 61 s silenced inside
section 2. `base.en` returned 420 words instead of 439; alignment fell to 95.0 %
and section 2 to 84 %.

```
!!! 1 SUSPECTED REAL GAP(S). THE VOICEOVER IS MISSING SCRIPT.
  section 2  script lines [35]  55.5-61.0s  (RMS floors out for 5.5s below
    -50 dBFS. RECORD THE PICKUP INTO THIS WINDOW)
    19 words missing: only known photo shows 4 glossy white legs rising out of
    an open manhole each 1 longer than a
```

Exit code 2.

**Test C, the packet's failure mode two.** A dense pink-noise bed over 52 to
70 s, transcribed by mistake instead of the dry VO. `base.en` returned 393
words; section 2 fell to 62 % matched. Arbitrated against the DRY `rms.json`:

```
1 gap(s) arbitrated as VO PRESENT (Whisper dropped it, or the read paraphrased).
Nothing to record:
  section 2 lines [35] 52.64-54.56s  median -29.7 dBFS, 0% below floor
```

Exit code 0. Same missing script lines, opposite verdict, and the verdict is
right both times. That is the entire point of section 4.3.

**Arbitrate on the dry voiceover.** In test C the mixed file's own RMS is high
through the window because the bed is loud. Feeding the mix to `rms.py` would
have produced the same reassuring answer even if the VO had been silent under
it. The arbiter is only valid on the file the narrator actually made.

---

## 4. What did not survive contact with reality

**1. Whisper writes spoken numbers as digits, so the packet's own example anchor
does not resolve.** The narrator says "thirty feet"; `base.en` emits `30 feet`.
The packet's worked example is `{"phrase": "thirty", "occurrence": 2}` and
against a raw transcript it finds nothing. Worse, the surface form is not stable
across models, so a sheet written against `base.en` can break under `small.en`,
which defeats the point of anchoring. Fixed by folding number words onto digits
inside `anchors.norm`, which `align_sections.py` imports so both sides of the
comparison agree. Script-to-transcript match went from 98.6 % to 99.8 % from
that change alone. Residual limit: a number Whisper collapses into one token
that the script spells across two ("one hundred" against `100`) still will not
match token for token. Anchor on a neighbouring word.

**2. A real gap does not appear as a gap in the transcript.** The intuition is
that missing audio leaves a hole in the word timings. It does not, because
Whisper does not timestamp what it never heard. In test B the words either side
of the 6 second silence came back at 55.02 s and 55.02 s, adjacent, so the window
bracketed by the surviving words was zero seconds wide and the tool first
reported the gap at `55.02-55.02s`, which is useless for recording a pickup.
`align_sections.py` now searches the RMS around the suspect point for a floored
run of at least 1.0 s and reports that window instead. Do not derive a gap's
timing from the transcript that is missing it.

**3. `small.en` on a suspect window does not recover the words, it invents
better ones.** The packet says to re-transcribe a suspect window with `small.en`
before believing it. On the mixed window, 52 to 70 s, where the truth is 54
words:

| | words returned | mean p |
|---|---|---|
| `base.en` | 8 | high |
| `small.en` | 47 | 0.525, 49 % of words below 0.5 |
| dry VO, `base.en` | 54 | 0.954 |

`base.en` dropped. `small.en` produced fluent, confident-looking English that
the narrator never said: "The only way to do this is to go across the body as
well as over the head." A word count that jumps back up is not recovery. The
tell is the confidence, so `transcribe.py` prints mean p and warns above 15 %
weak words. Treat `small.en` as a second opinion to compare, never as an
upgrade to trust.

**4. Failure mode one did not reproduce, and that is a result.** No 5-gram
repeated even three times in any of the four transcripts, including the one
taken from a loud mix. `condition_on_previous_text=False` is doing exactly what
the packet says it does. What replaced looping was invention inside a single
segment, which the repeat detector cannot see. Both checks are needed.

**5. `vad_filter=True` does not shift the timeline.** A reasonable fear, since
the filter removes audio before inference. Measured against the 6 second
silence: word starts after the cut differ from the dry transcript by at most
0.03 s at 70 s, 90 s, 110 s and 140 s. Timestamps stay absolute to the source.

**6. `hyperframes tts` needs its Python side installed first.** It fails with
"kokoro-onnx package is not installed". `pip install kokoro-onnx soundfile`,
then the first run downloads about 340 MB of model and 27 MB of voice data.
Synthesis of 437 words took roughly 4 minutes of CPU in one process with no
progress output, which looks like a hang and is not.

---

## 5. Decisions taken inside the tools

- **Section ranges tile the timeline.** `start`/`end` are cut at the midpoint
  between one section's last matched word and the next section's first, so
  there are no holes between sections. An anchor sitting in a hole would be
  unresolvable for no good reason. The honest matched extent is kept separately
  as `vo_start`/`vo_end`.
- **`index` is document order, counting CTA beats.** `number` keeps the number
  the script itself wrote in the heading. On the packet's own example these
  agree.
- **Line numbers become times.** `parse_script.py` keeps the raw 1-based line
  number of every narration line, and `align_sections.py` writes `line_times`
  back, so a marked joke line resolves to a time range with no guessing. In the
  demo, joke line 25 runs 32.06 to 39.98 s and joke line 53 runs 125.08 to
  133.04 s. That is what "keep the raw line numbers" is for.
- **Joke markers.** A line is a joke line if it carries `[JOKE]`, `[DRY JOKE]`,
  `[GAG]`, any of those in bold, or an HTML comment `<!-- joke -->`. The marker
  is stripped from the narration text. A marker found outside any section is a
  warning on stderr, not a silent drop.
- **Exit codes are the contract.** 0 clean, 1 usage or input error, 2 a
  suspected real gap or a gap that could not be arbitrated, 3 empty transcript
  or empty audio, 4 anchor not found. A build step can branch on these without
  parsing text.
- **Every ffmpeg call carries `-nostdin -v error`.** Both in `rms.py` and in
  `transcribe.py`'s window clipper.

---

## 6. Why align_sections.py exists

The packet lists four Stage 2 tools and specifies all four. It also states, in
the repo layout, that `work/sections.json` holds "script parsed into sections
with VO time ranges", and in 4.4 it requires `section=(sec.start, sec.end)` on
every anchor search and calls that restriction the thing that stops a pop for
creature 6 resolving into creature 2. But the sketch for `parse_script.py`
writes no time fields, and no other specified tool writes them either. The
field has two documented consumers and no producer. `align_sections.py` is that
producer, and the RMS arbitration described in 4.3 is folded into it, because
alignment is the step that discovers a missing stretch in the first place.

---

## 7. The gitignore contract

`*.wav` and `horror-pipeline/projects/*/work/` are both ignored, deliberately:
`work/` is rebuildable from `script.md` plus `vo.wav` in about 40 seconds, and
audio does not belong in a repo that has to stay clonable.

The one exception is `projects/demo/vo.wav`, force-added at 7.2 MB. It is the
Stage 2 test fixture. TTS output is not reproducible across model versions, so
without the committed file the measured numbers in this document could not be
re-derived. Regenerate it only if you also update the numbers here:

```bash
npx hyperframes@latest tts /abs/projects/demo/work/vo.txt \
    -o /abs/projects/demo/vo.wav --voice am_michael --speed 1.0
```
