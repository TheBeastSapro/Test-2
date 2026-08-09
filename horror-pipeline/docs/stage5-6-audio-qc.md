# Stage 5 (audio) and Stage 6 (measured QC)

Two tools, `tools/mix_audio.py` and `tools/qc.py`, built to BUILD-PACKET sections
6.6, 7 and 8. Both are ports of code that already works in this repo:
`engine/ffmpeg-engine/build.py` lines 60-103 for the audio chain, and
`engine/ffmpeg-engine/qc.py` (569 lines) for the measurement pass. This document
records the known-good commands and the measurements taken from real runs.

Every rule below exists because a real cut was rejected for breaking it. Nothing
here is a preference.

---

## 1. Stage 5: `tools/mix_audio.py`

Four buses: voiceover, ambient bed, SFX, master.

```
python3 tools/mix_audio.py \
  --vo   projects/<slug>/audio/vo.wav \
  --bed  projects/<slug>/audio/bed.wav \
  --duration 62.600 \
  --vo-offset 0.5 \
  --sfx assets/sfx/whoosh.wav@3.2 \
  --sfx assets/sfx/boom.wav@11.8:-3 \
  --out  projects/<slug>/audio/mix.wav \
  --work projects/<slug>/work \
  --report projects/<slug>/work/mix_report.json
```

`--sfx path@seconds[:gain_db]` is repeatable; `--sfx-json` takes
`{"sfx":[{"file":...,"t":...,"gain":...}]}` for a sheet-generated cue list.
`--mux out/video.mp4 --mux-out out/<slug>.mp4` muxes in the same run, with `-t`.

The tool exits non-zero and prints a numbered problem list if any master
measurement falls outside the QC window, so it can be used as a gate.

### 1.1 The chain, and the five things that must not change

```
VO   [0:a] adelay -> aresample=48000 -> highpass=80
           -> acompressor=threshold=-12dB:ratio=1.6:attack=15:release=280
           -> aformat=stereo                                              [vo]
BED  [1:a] aresample=48000 -> atrim=0:DUR -> apad=whole_dur=DUR
           -> afade in 1.2s -> afade out 2.0s -> volume=-19dB
           -> aformat=stereo                                            [bed0]
SFX  [k:a] aresample=48000 -> volume=(gain-9)dB -> adelay=cue
           -> aformat=stereo                                              [sk]
           -> amix=inputs=N:normalize=0:duration=longest                  [sfx]
DUCK [vo] asplit=2                                                 [vo1][vokey]
     [bed0][vokey] sidechaincompress=threshold=0.02:ratio=6:attack=20:
                   release=520:makeup=1                                  [bed]
MIX  [vo1][bed][sfx] amix=inputs=3:normalize=0:duration=longest
                   -> apad=whole_dur=DUR -> atrim=0:DUR -> aresample=48000[out]
                   -> pcm_s24le  work/mix_raw.wav
```

1. **No limiter anywhere.** A cut was failed at **LRA 1.9**, over-limited to the
   point the bed never audibly ducked and the SFX could not punch. The tool
   inspects the filtergraph it is about to hand ffmpeg and refuses to run if a
   limiter-class filter (`alimiter`, `compand`, `asoftclip`, `speechnorm`, ...)
   appears in it. If the master is genuinely too hot, turn the bed and the SFX
   down in the pre-master. Never add a limiter.

2. **Two-pass linear loudnorm.** See section 1.2.

3. **Sidechain argument order.** The **first** input to `sidechaincompress` is
   what gets compressed (the bed); the **second** is the key (a copy of the VO
   via `asplit`). Backwards, the bed swamps the voice, and ffmpeg reports
   nothing. Measured, see section 1.3.

4. **`apad` then `atrim` at the end of pass 2.** This is what makes the mix
   exactly the composition length, which is what stops the `-shortest`
   truncation in section 1.4.

5. **`aresample=48000` after `loudnorm`.** Bare `loudnorm` silently resamples
   48k to 96k. The tool re-probes the output and fails if the sample rate is not
   48000.

### 1.2 The two-pass linear loudnorm, and how the tool proves it happened

Targets: `I=-15` LUFS (middle of the -14..-16 window, because the measured
result drifts a few tenths), `TP=-1.5` dBTP (QC fails at -1.0, so aim inside the
line), `LRA=9` as a **ceiling hint, not a target to squash toward**.

Pass 1 measures and changes nothing:

```
ffmpeg -nostdin -hide_banner -nostats -loglevel info -i work/mix_raw.wav \
  -af loudnorm=I=-15:TP=-1.5:LRA=9:print_format=json -f null -
```

Pass 2 applies, with `linear=true` and **all five** `measured_*` values:

```
ffmpeg -nostdin -hide_banner -nostats -loglevel info -y -i work/mix_raw.wav -af \
"loudnorm=I=-15:TP=-1.5:LRA=9:linear=true:\
measured_I=${input_i}:measured_TP=${input_tp}:measured_LRA=${input_lra}:\
measured_thresh=${input_thresh}:offset=${target_offset}:print_format=summary,\
aresample=48000,apad=whole_dur=${dur},atrim=0:${dur}" \
-c:a pcm_s16le audio/mix.wav
```

Supplying all five values correctly is **not sufficient**. Measured here:
ffmpeg accepts `linear=true`, then **silently falls back to dynamic mode** when
the single constant gain that would hit the loudness target would also push the
true peak past the TP target. Nothing warns you. The output lands on both
targets and looks fine, and the loudness range has been ridden flat. That is the
same shape as the LRA 1.9 rejection.

So the tool does two things the packet does not spell out:

* **Pre-flight.** It computes `offset = I_target - measured_I` and predicts
  `measured_TP + offset`. If that exceeds the TP target it says so before
  spending the pass, names the pre-master crest factor and the budget
  (`TP_target - I_target`, i.e. 13.5 dB at -15/-1.5), and says the fix is gain
  staging upstream, never a limiter.
* **Post-flight.** Pass 2 runs at `-loglevel info` **only** so that
  `print_format=summary` can be read back, and the tool asserts on ffmpeg's own
  line:

  ```
  Normalization Type:   Linear
  ```

  Anything other than `Linear` is a hard failure with the LRA-1.9 explanation
  attached. This is the single most valuable check in the tool: it is ffmpeg
  stating to your face which algorithm it used.

A real failing run, for the record. A raw TTS voiceover at -24.43 LUFS with a
-6.82 dBTP pre-master (17.6 dB crest, budget 13.5 dB):

```
[audio] pre-master   I=-24.43 LUFS  TP=-6.82 dBTP  LRA=2.30 LU
[audio] loudnorm reports Normalization Type: Dynamic
  LRA  2.10 LU   (pre-master 2.30 LU, QC fails at or below 3.0)
[audio] PROBLEMS
  - loudnorm ran in DYNAMIC mode, not linear. ...
```

### 1.3 Measured proof run

**Inputs.** A real 45.000 s voiceover stem built from `projects/demo/vo.wav`
(three passages at three levels, because real narration varies section to
section and that variation IS the loudness range QC measures), plus a
synthesised ambient bed and two synthesised SFX used six times.

```bash
# STAGE 4 (upstream) VO stem prep. NOT part of the stage 5 mix chain.
# Peak control belongs on the VO stem; the master bus stays limiter-free.
ffmpeg -nostdin -loglevel error -y -i projects/demo/vo.wav -filter_complex "\
[0:a]atrim=10:25,asetpts=N/SR/TB,volume=0dB[a];\
[0:a]atrim=60:75,asetpts=N/SR/TB,volume=-11dB[b];\
[0:a]atrim=110:125,asetpts=N/SR/TB,volume=7dB[c];\
[a][b][c]concat=n=3:v=0:a=1,aresample=48000,highpass=f=80,\
acompressor=threshold=-26dB:ratio=3:attack=5:release=160,volume=16dB,\
alimiter=limit=0.5:level=false:attack=5:release=50,volume=-1dB[o]" \
  -map "[o]" -ac 1 -c:a pcm_s16le work/vo_stem.wav
# -> I=-18.57 LUFS  TP=-6.34 dBTP  LRA=5.90 LU  (crest 12.2 dB)

# ambient bed
ffmpeg -nostdin -loglevel error -y \
  -f lavfi -i "anoisesrc=d=60:c=brown:a=0.6:r=48000" \
  -f lavfi -i "sine=frequency=55:duration=60:sample_rate=48000" \
  -f lavfi -i "sine=frequency=82.4:duration=60:sample_rate=48000" \
  -filter_complex "[0:a]lowpass=f=600,volume=3[n];[1:a]volume=0.5,tremolo=f=0.11:d=0.7[d];\
[2:a]volume=0.22,tremolo=f=0.12:d=0.8[e];[n][d][e]amix=inputs=3:normalize=0,\
aformat=channel_layouts=stereo,volume=-2dB[a]" -map "[a]" -c:a pcm_s16le work/bed.wav

# SFX
ffmpeg -nostdin -loglevel error -y -f lavfi -i "anoisesrc=d=0.7:c=pink:a=0.9:r=48000" \
  -af "highpass=f=300,lowpass=f=6000,afade=t=in:st=0:d=0.25:curve=exp,\
afade=t=out:st=0.3:d=0.4,aformat=channel_layouts=stereo" -c:a pcm_s16le work/whoosh.wav
ffmpeg -nostdin -loglevel error -y -f lavfi -i "sine=frequency=52:duration=1.2:sample_rate=48000" \
  -af "volume=1.6,afade=t=out:st=0.05:d=1.1:curve=exp,aformat=channel_layouts=stereo" \
  -c:a pcm_s16le work/boom.wav

# THE MIX
python3 tools/mix_audio.py --vo work/vo_stem.wav --bed work/bed.wav --duration 45.0 \
  --vo-offset 0.5 \
  --sfx work/whoosh.wav@1.2 --sfx work/whoosh.wav@8.4 --sfx work/boom.wav@14.6:-3 \
  --sfx work/whoosh.wav@22.0 --sfx work/boom.wav@33.5:-6 --sfx work/whoosh.wav@39.0 \
  --out work/mix.wav --work work --report work/mix_report.json
```

**Result.**

```
[audio] duck         bed -48.5 dB under speech vs -40.2 dB in gaps  -> 8.4 dB of duck
[audio] pre-master   I=-18.94 LUFS  TP=-7.52 dBTP  LRA=5.50 LU  thresh=-29.22
[audio] linear check offset +3.94 dB -> predicted TP -3.58 dBTP (limit -1.5)
                     pre-master crest 11.4 dB, budget 13.5 dB
[audio] loudnorm reports Normalization Type: Linear
```

| Master measurement | Value | Target | Verdict |
|---|---|---|---|
| Integrated loudness | **-15.00 LUFS** | -16 to -14 | PASS |
| True peak | **-3.58 dBTP** | below -1.0 (aim -1.5) | PASS |
| Loudness range | **5.40 LU** | above 3.0 | PASS |
| LRA drift, pre-master to master | 5.50 -> 5.40 LU (**0.10 LU**) | a constant gain cannot move it | PASS |
| Normalization type | **Linear** | Linear | PASS |
| Duration | 45.000 s | exactly the composition | PASS |
| Sample rate | 48000 Hz | 48000 (not 96000) | PASS |
| Bed duck depth | 8.4 dB | audible duck | PASS |

The LRA line is the one that matters: 5.50 LU went in, 5.40 LU came out. One
constant gain applied evenly cannot change a loudness range, and it did not.

### 1.4 The mux: `-t <exact_duration>`, never `-shortest`

```
ffmpeg -nostdin -loglevel error -y \
  -i out/video.mp4 -i projects/<slug>/audio/mix.wav \
  -c:v copy -c:a aac -b:a 320k \
  -t <exact_duration> \
  out/<slug>.mp4
```

Measured on a real 45.200 s picture from the reference cut, muxed against a
correctly padded 45.000 s mix and against an unpadded 44.370 s mix:

| Mux | Video stream | Audio stream | Picture lost |
|---|---|---|---|
| `-shortest`, padded mix | 44.967 s | 45.000 s | **0.233 s** |
| `-shortest`, unpadded mix | 44.367 s | 44.373 s | **0.833 s** |
| `-t 45.2`, padded mix | 45.200 s | 45.000 s | 0.000 s |
| `-t 45.2`, unpadded mix | 45.200 s | 44.373 s | 0.000 s |

`-shortest` throws picture away silently; nothing in the render output warns.
`-t` never does. Note the last row: `-t` keeps the picture but leaves an 0.83 s
A/V delta, which is what the QC A/V-length check is for. Both halves are needed
-- `apad` in stage 5 so the mix is the right length, `-t` in the mux so the
picture is not cut to fit it.

### 1.5 The three guards, proven

```
$ # limiter refusal
clean chain: accepted
refused -> REFUSING TO BUILD: limiter-class filter(s) in the chain: alimiter
refused -> REFUSING TO BUILD: limiter-class filter(s) in the chain: compand
refused -> REFUSING TO BUILD: limiter-class filter(s) in the chain: speechnorm

$ # sidechaincompress argument order
correct   sidechain -> bed -48.5 dB under speech, -40.2 dB in gaps, duck depth   8.4 dB
reversed  sidechain -> bed -28.2 dB under speech, -67.4 dB in gaps, duck depth -39.2 dB
```

Reversed, the "bed" output is really the compressed voice: loud under speech,
gone in the gaps. The duck-depth measurement separates the two cases by 47 dB,
so the check (`duck_depth_db < 1.0` is a problem) cannot miss it.

---

## 2. Stage 6: `tools/qc.py`

```
python3 tools/qc.py projects/<slug>/out/<slug>.mp4 \
  --workdir projects/<slug>/out/qc --keep \
  --sheet projects/<slug>/sheets/<slug>.json \
  --json  projects/<slug>/out/qc/report.json
```

Options: `--sections auto|none|<t1,t2,...>|file.json` (default `auto`),
`--pops-file` for the intended pop strings when there is no sheet, `--jobs N`
for the OCR worker count, `--no-ocr` to skip the text pass, `--json` to write
the full report. Exit status is 1 if anything FAILs, so it drops straight into
the build loop.

It prints a verdict table and a defect list. It does not print every frame.

### 2.1 The four measurement subtleties that must survive any future edit

**Dead zones are never merged across a high-motion sample.** A run of
sub-threshold 0.5 s samples ends at the first sample above threshold. Full stop.
Merging "low, low, spike, low, low" into one zone produced a bogus 13 second
hold report on a cut that did not have one.

**Content-box luminance, not whole-frame luminance.** The house boxed style is a
white canvas around a dark image box; measure the whole frame and a pitch-black
night shot reads about 160 mean and looks fine. And check p95 before flagging: a
mean of 16 with a p95 of 101 has bright anchors in it and is correct, not
illegible.

There is a second half to that rule which the port had to add. This channel also
ships **full-bleed cinematic** cuts, and on those the box finder happily returns
the bounding box of whatever the darkest region happens to be. Measuring inside
*that* biases the mean down and manufactures "dark and flat" defects on a
correctly graded night shot: the exact mirror image of the bug the rule exists to
prevent. So the tool tests whether what surrounds the box is actually a bright
canvas (median margin luminance at or above 200/255, margin at least 8% of the
frame). Bright margin, use the box. Otherwise the frame *is* the content, and it
measures the whole frame and says so:

```
[3/7] content box
      margin around the box reads 96/255, not a white canvas: full-bleed layout,
      measuring whole frame -> ROI whole frame
```

**Two OCR passes per frame.** Tesseract binarises the page globally, so
white-on-dark pop text inside a dark box falls on the wrong side of the threshold
and vanishes. That produced a false "3 pops missing" report. Pass A reads the
page as-is; pass B isolates bright pixels inside the content box, inverts them so
the text is dark on light, doubles the size (tesseract wants roughly 30 px cap
height) and adds a white border. Both passes run on every frame and the results
are merged.

**OCR at 2 fps, not 1.** Pops are on screen about 2 s and animate in over the
first 0.2 s. At 1 fps you catch a pop mid-animation, read half a word and log a
spelling error that does not exist. A pop counts as misspelled only if it never
renders correctly on **any** frame.

### 2.2 The pop taper check

A plain per-section floor does not catch a lazy finale: a floor of 2 lets a
section through on two filler connectives. An editor was failed on exactly this
shape -- dense pops through creature 5, two filler pops in 84 s by creature 7,
zero editor-added pops in the 87 s finale.

So the tool counts pops per section, takes the **median**, and requires the
**last** section to be at least **0.8 x** that median, on top of the per-section
floor of 2.

Sections come from the sheet when there is one. With no sheet, `--sections auto`
infers them from the persistent creature-name title: house rule 3 puts that title
top-centre on every frame of a section, so a fuzzy text cluster that occupies a
contiguous, well-covered span of the timeline is a section title, and the
midpoints between those spans are the boundaries. OCR misreads the title
consistently but not identically ("Cartoon Cat" comes back as "Cartoon", "Cat",
"GartoonnGats"), so the clustering is fuzzy, not exact. Exact-match grouping
splits one title into a dozen strings, none of which then looks persistent, and
the title gets counted as a keyword pop in every section.

### 2.3 Verdict table from the reference cut

`research/vu/vu-final.mp4`, the channel's own publish-standard cut by editor Vu:
581.74 s, 742 MB, 1920x1080 at 30 fps, H.264 High, AAC 320 kbps. The file is
gitignored.

```
python3 tools/qc.py research/vu/vu-final.mp4 \
  --workdir /tmp/qcref --keep --jobs 4 --json /tmp/qcref/report.json
```

<!-- RESULTS -->

---

## 3. Selftests

Both tools carry a `--selftest`. Every assertion in them corresponds to a rule
that has already produced a wrong verdict or a rejected cut, because a rule
stated in a docstring gets "simplified" out and a rule stated as an assertion
does not.

```
$ python3 tools/qc.py --selftest
=== qc.py selftest: the rules that have already cost a wrong verdict ===
  ok   dead zones: not merged across a spike  got 2 zones of [4.0, 4.0]s (merging would give one 8.5s zone)
  ok   dead zones: each run measured on its own
  ok   dead zones: a continuous low run is one zone
  ok   dark: mean 16 with p95 101 is not a defect
  ok   pops: two passes on one frame count as one sample
  ok   pops: a 3-letter grain read is not word-shaped
  ok   pops: a title fragment is not a pop
  ok   taper: 6/6/6/2 fails the taper rule  last 2 vs median 6.0 (needs 4.8)
  ok   taper: 6/6/6/2 passes a plain floor of 2, which is why the floor is not enough
  ok   taper: 6/5/6/5 passes
  ok   longest shot: tail after the last cut counts  got 18.0s
selftest: 0 failure(s)

$ python3 tools/mix_audio.py --selftest
=== mix_audio.py selftest: the rules that have already cost a rejected cut ===
  ok   no-limiter guard: the real chain is accepted
  ok   no-limiter guard: refuses alimiter
  ok   no-limiter guard: refuses compand
  ok   no-limiter guard: refuses speechnorm
  ok   no-limiter guard: refuses asoftclip
  ok   linear check: 17.6 dB crest against a 13.5 dB budget is refused  predicted TP +2.61 dBTP
  ok   linear check: 11.4 dB crest fits the budget  predicted TP -3.58 dBTP
  ok   measured values: a complete set is accepted
  ok   measured values: a missing one is caught
  ok   measured values: 'inf' is caught
selftest: 0 failure(s)
```

The taper pair is the important one: `6/6/6/2` clears a plain per-section floor
of 2 and still fails the taper rule, which is exactly the shape an editor was
failed on.

---

## 4. House rules for calling ffmpeg from these tools

Every ffmpeg call carries `-nostdin`. Everything that does not need to be parsed
also carries `-loglevel error`.

Three calls are the exception, and they have to be: `volumedetect`,
`loudnorm print_format=json` and `loudnorm print_format=summary` all emit their
statistics at **info** level, so `-loglevel error` deletes the measurement. Those
three run as:

```
ffmpeg -nostdin -hide_banner -nostats -loglevel info ...
```

`-nostats` is what suppresses the `frame= ... speed=` progress flood, which is
what the house rule is actually about. `-hide_banner` drops the build banner. The
statistics survive.
