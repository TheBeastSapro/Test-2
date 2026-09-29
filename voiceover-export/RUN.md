# RUN — script text file → final voiceover

Run every command from inside this `voiceover-export/` folder.

## One-time setup

```bash
# ffmpeg must be on PATH. Then:
bash skills/explaintory-voiceover/scripts/setup.sh
```

This installs elevenlabs, faster-whisper, jiwer, whisper-normalizer, spaCy +
en_core_web_sm, numpy, scipy, and CPU torch/torchaudio. The first real run downloads two
models: distil-large-v3 (**1.5 GB**) for the read-check and MMS_FA (**1.18 GB**) for
alignment. Both are cached after that. The sandbox needs network access to
huggingface.co and download.pytorch.org.

## Environment (every session)

```bash
export ELEVENLABS_API_KEY=...          # set it in the environment; never put it in a file
unset ELEVENLABS_VOICE_ID ELEVENLABS_MODEL   # these would silently override the locked voice
```

Nothing in this folder contains a key, and `generate.py` refuses a profile that has one.

## The commands

Set these once:

```bash
S=skills/explaintory-voiceover/scripts
H=skills/explaintory-vo-master/scripts/humanize.py
P=config/voice-calibration.json
SCRIPT=script.txt          # your script
OUT=out
```

**Step 1: plan (free, sends nothing).** Show the output to the owner and have them
confirm the chapter list and the character cost.

```bash
python3 $S/voiceover.py --script "$SCRIPT" --profile $P --humanize $H --out-dir $OUT --plan
```

**Step 2: clause breaks (free).** Print candidates, then **keep only the real ones by
reading them** (about a third are wrong). `cut -f1` is required: the raw output has
the sentence after a tab, and `humanize.py` would then match nothing, with no error.

```bash
python3 $S/voiceover.py --script "$SCRIPT" --profile $P --suggest-breaks | cut -f1 > breaks.txt
# edit breaks.txt by hand: delete wrong pairs, add missing ones (one wordA|wordB per line)
```

**Step 3: the full run (spends credits).** `--approval` must quote the owner's own
words approving *this* send. `--approve-spend` is the character count from step 1.

```bash
python3 $S/voiceover.py --script "$SCRIPT" --profile $P --humanize $H \
    --curated breaks.txt --out-dir $OUT \
    --approval "<owner's exact words>" --approve-spend <chars from plan> \
    > run.log 2>&1
echo "exit $?"            # trust the exit code; 0 = the final MP3 exists and is real audio
grep -v "MB/s]" run.log   # filter when READING, never on the pipe
```

Result: `$OUT/<Title> (final).mp3`, 48 kHz mono, 256 kbps. The working files are in
`$OUT/.vo_<Title>/`.

**Step 4: delivery gates (free, not run automatically, run them yourself):**

```bash
W="$OUT/.vo_<Title_with_underscores>"
python3 $S/orphans.py --audio "$OUT/<Title> (final).mp3"          # exit 1 = stranded fragments found
python3 $S/verify.py  --audio "$OUT/<Title> (final).mp3" --script "$W/script_lines.txt" \
                      --curated breaks.txt --sections "$W/sections.json"   # exit 1 = do not deliver
```

### Optional variants

- **Heading levelling off.** The last approved delivery ran this way, and `voiceover.py`
  has no flag for it. Re-stitch without levelling (free), then resume:
  ```bash
  python3 $S/generate.py --script "$W/narration_source.txt" --out "$W/raw_stitched.wav" \
      --parts-dir "$W/parts" --sections-json "$W/sections.json" --max-chunk 450 \
      --profile $P --stitch-only --no-level-headings
  python3 $S/voiceover.py --script "$SCRIPT" --profile $P --humanize $H \
      --curated breaks.txt --out-dir $OUT --from check > run2.log 2>&1
  ```
- **Fix one misread word:** re-render only its sentence (needs a new approval):
  `python3 $S/regen_span.py --parts-dir "$W/parts" --sections-json "$W/sections.json" --section N --sentence "<exact sentence>" --profile $P --approval "<owner's words>"`,
  then `--from check`.
- **Only re-master** (free): add `--from master` to the step 3 command.

---

## Test example

`test/test_script.txt` has a title, 3 chapters, dates, a date range, a missing-comma
clause and a pronunciation guide.

### Step 1 (free). Run and verified in this export

```bash
env -u ELEVENLABS_API_KEY python3 $S/voiceover.py --script test/test_script.txt \
    --profile $P --humanize $H --out-dir test/out --plan
```

Expected output (exit 0). The `master:` path will show your own absolute path:

```
[voiceover] “The Tiny Test Video” · 8 sections · 372 chars
[voiceover] pronunciation guide: 2 names, held out of the narration (Angolpo, Syracuse)

  TITLE: “The Tiny Test Video”  (read aloud — readTitle is on)
  detected 3 chapters — chapter names read aloud as intros
    1. The First Voyage
    2. The Second Voyage
    3. The Third Voyage
  pronunciation guide: 2 names held out of the narration

  8 sections (3 chapter announcements + the title) · 372 chars · ~0:26 audio

  CALIBRATION — every value that will be sent, and who chose it:
  voice dUHbvtIZto0ZEBkhYiyk (profile)
  model eleven_multilingual_v2 (profile)
  stability 0.48 (profile) · similarity_boost 0.8 (profile)
  style 0.05 (profile) · speed 1.07 (profile)
  use_speaker_boost True (profile)
  chunkSize 450 (profile) · chapterPause natural (profile)
  collapseBreaks False (profile) · readTitle True (default)
  skipHeadings False (profile)
  ^ 1 value(s) nobody chose — inherited defaults, not settings: read_title

  COST: ~372 credits (first pass)
  redo rounds: off (--max-redos 0) — flagged sections are reported, not re-rendered
  WORST CASE this run: ~372 credits
  master: .../skills/explaintory-vo-master/scripts/humanize.py
```

With `ELEVENLABS_API_KEY` set, the COST line also shows `of N remaining` (a free, read-only call).

Expected section split and inserted silence (from `script_prep`):

```
 1 gap_before=0.00s heading=True    20ch  'The Tiny Test Video.'
 2 gap_before=0.30s heading=False   71ch  'In 1547 the viceroy sent three ships north, and none of them came back.'
 3 gap_before=0.22s heading=True    17ch  'The First Voyage.'
 4 gap_before=0.30s heading=False   92ch  'Between 1547 and 1550, the crews mapped the coast. At Angolpo the Japanese lost forty ships.'
 5 gap_before=0.22s heading=True    18ch  'The Second Voyage.'
 6 gap_before=0.30s heading=False   80ch  'By 255 BC a returning fleet had reached Syracuse. It was the largest ever built.'
 7 gap_before=0.22s heading=True    17ch  'The Third Voyage.'
 8 gap_before=0.30s heading=False   57ch  'Nobody knows what happened next. The records simply stop.'
```

Step 2 on the test prints exactly one candidate: `Angolpo|the` (a real break, so keep it).

### Step 3 on the test. NOT run for this export (it costs ~372 credits and needs the owner's approval)

Predicted output, **not measured**:
- `test/out/The Tiny Test Video (final).mp3`, mono, 48 kHz, 256 kbps, about 30 s
  (≈26 s of speech + chapter gaps + 1.0 s tail).
- The log ends with `[humanize] inserted … at N boundaries {…}` and `[voiceover]
  delivered test/out/The Tiny Test Video (final).mp3 (… MB, 0:3x)`, exit 0.
- Pauses the master should insert or top up: a post-date beat after "In 1547", **none**
  inside "1547 and 1550", a comma beat after "1550," (unless the voice left under
  60 ms), a curated beat at "Angolpo ‖ the", a post-date beat after "255 BC", and
  sentence beats at each period.
- Integrated loudness ≈ −14 LUFS, true peak ≤ −1.5 dBTP. Check with
  `ffmpeg -i "<file>" -af ebur128=peak=true -f null -`.

Without `--approval`, step 3 stops before sending and prints the 8 sections with
their character counts. That output is safe to use as a test of the gate.
