# RUN.md

## Requirements

```bash
# system
ffmpeg, ffprobe          # 6.x or 7.x; every stage shells out to these
python3                  # 3.11+

# python
pip install numpy soundfile librosa opencv-python-headless
# optional, only to transcribe a VO when no script was supplied
pip install faster-whisper
```

`librosa` is needed by `sync_check.py` and the music-drive measurement,
`opencv-python-headless` by `visual_redraw.py` and the picture detectors,
`soundfile` by `palette.py` / `oneshot.py`. A fresh container has none of them,
and the failure lands late — `rebuild_palette.py` downloads all 113 files and
*then* dies on `ModuleNotFoundError: No module named 'soundfile'`. Install first.

## Credentials

```bash
export EPIDEMIC_SOUND_API_KEY="..."     # from epidemicsound.com/account/api-keys
```

Read from the environment only. **No key is stored in any file in this export**
(`scripts/epidemic_api.py` reads `EPIDEMIC_SOUND_API_KEY` or `EPIDEMIC_API_KEY`;
`scripts/epidemic.py` reads `EPIDEMIC_API_KEY`). Keys expire after 30 days — a
401 means regenerate. The key is tied to a normal Epidemic account; no
partnership agreement is needed for this endpoint.

Downloads return signed URLs on `audiocdn.epidemicsound.com`, so that host has to
be reachable. If it is blocked you will see `curl: (56) CONNECT tunnel failed,
response 403` — search works without it, downloads do not.

---

## The one command

Given a cue sheet, a voiceover and the source video, this is the whole render:

```bash
python3 scripts/assemble.py \
  --cues cues.json \
  --vo   "Title (final).wav" \
  --assets ./assets \
  --out  "Title (final).mp4" \
  --mux-into in.mp4 \
  --stems ./stems
```

That writes the mixed video (video stream **copied**, audio AAC 320k) plus
`stems/music.wav`, `stems/sfx.wav`, `stems/vo.wav`.

Defaults already carry the house settings — `--bed-target-db -20`, `--sfx-db -6`,
ducking on, SFX polish on. You should not need to pass them.

For an audio-only master instead, change the extension and drop `--mux-into`:

```bash
python3 scripts/assemble.py --cues cues.json --vo vo.wav --assets ./assets \
  --out "Title (mixed).wav" --stems ./stems
```

### Getting to `cues.json` from a bare video

`assemble.py` is the last step. The full path from a video plus a voiceover:

```bash
# 0. VO stem — if the video already carries it and nothing else
ffmpeg -i in.mp4 -vn -ac 1 -ar 48000 vo.wav
ffmpeg -i vo.wav -af ebur128 -f null -        # expect ~-14.5 LUFS, LRA ~1.6

# 1. beats from the picture (~4 min for 12 minutes of 1080p)
python3 scripts/visual_redraw.py in.mp4 -o redraw.json

# 2. base cue structure
python3 scripts/analyze.py --video in.mp4 --vo vo.wav \
        --out cues_auto.json --report cues_auto.md

# 3. palette: fetch from Epidemic, then prepare ONCE
python3 scripts/epidemic_api.py sfx "sword clash metal impact" -n 12 --max-ms 4000
#   ... pull the chosen ids, then:
python3 scripts/palette.py --raw pal_raw --out pal --bed-prefix amb,wind,fire,crowd
python3 scripts/oneshot.py pal/impact_11.wav --out pal --name shield   # multi-take files

# 4. the hand-authored sheet. Copy a build_cues.py from config/ and rewrite
#    SECTIONS / BEDS / B / MUTES for this video, reading times off contact sheets.
python3 build_cues.py                          # -> cues_beats.json

# 5. CHECKS — before rendering, every time
python3 config/castle-defences/preflight.py    # files that sustain, cast as hits
python3 config/castle-defences/overrun.py      # cues longer than their shot
python3 config/castle-defences/onscreen.py     # beds vs what is on screen

# 6. place generic cues against the hand-written ones
python3 scripts/place.py --cues cues_beats.json --events redraw.json \
        --palette pal --out cues.json --no-beds

# 7. render (the one command above)

# 8. verify
python3 scripts/sync_check.py --sfx stems/sfx.wav --cues cues.json \
        --fps 24 --by-tier          # <- pass the video's REAL frame rate
```

`--no-beds` at step 6 is deliberate: every ambience bed is hand-assigned, because
a bed never ducks and rotation cannot know that an engine room does not belong
under a medieval deck.

### Useful extras

```bash
# a 30 s excerpt of the real master, for a fast ear-check
python3 scripts/assemble.py ... --preview 6:35-6:54

# measure somebody else's finished video (works there; not on our own mixes)
python3 scripts/measure_ref.py reference.wav
```

---

## Test

A self-contained test that needs no video, no voiceover and no API key. It builds
a 20-second synthetic job and renders it through the real `assemble.py`.

```bash
cd sound-design-export
python3 test/make_fixture.py /tmp/fixture

python3 scripts/assemble.py \
  --cues /tmp/fixture/cues.json \
  --vo   /tmp/fixture/vo.wav \
  --out  "/tmp/fixture/fixture (mixed).wav" \
  --stems /tmp/fixture/stems \
  --mux-into /tmp/fixture/video.mp4

python3 test/verify.py /tmp/fixture
```

### Expected output

`make_fixture.py`:

```
fixture ready in /tmp/fixture
  video.mp4  20 s, 24 fps, cuts at 4/8/12/16 s
  vo.wav     20 s, mastered to ~-14.5 LUFS
  cues.json  2 music sections, 6 sfx cues, 1 bed
```

`assemble.py` ends with (paths will differ):

```
[assemble] stem -> /tmp/fixture/stems/music.wav
[assemble] stem -> /tmp/fixture/stems/sfx.wav
[assemble] stem -> /tmp/fixture/stems/vo.wav
[assemble] --mux-into writes a video; using /tmp/fixture/fixture (mixed).mp4
[assemble] muxed into video -> /tmp/fixture/fixture (mixed).mp4
[assemble] wrote /tmp/fixture/fixture (mixed).mp4
   I:         -15.2 LUFS
   LRA:         0.3 LU
   Peak:       -4.2 dBFS
```

`verify.py` — the actual recorded output of the run, not an illustration. The
fixture's noise sources are seeded, so these figures reproduce exactly:

```
verifying /tmp/fixture

  [PASS] voice unchanged: -15.1 LUFS in -> -15.1 LUFS out (tolerance 0.2)
  [PASS] true peak <= -1.0 dBTP: -4.2 dBFS
         (programme loudness -15.2 LUFS -- an output, not a target)
  [PASS] video stream copied: ['h264', '320', '180', '480'] -> ['h264', '320', '180', '480']
  [PASS] muxed audio is aac 48k stereo: aac 48000 2
  [PASS] stem music: 20.00 s
  [PASS] stem sfx: 20.00 s
  [PASS] stem vo: 20.00 s
  [PASS] bed under speech: -20.1 dB

all checks passed
```

Exit code 0 on success, 1 with a `FAILED:` line naming each broken check.

### What the test is actually asserting

Not fixture trivia — the invariants that must hold on every real job, which is
why `verify.py` can be pointed at a real render too:

1. **The voice comes out at the level it went in.** The single most important
   rule. Any drift means a programme-loudness target has crept back in, which
   moves the voice because the voice *is* most of the programme.
2. **True peak at or under −1.0 dBTP.**
3. **The video stream was copied, not re-encoded** — codec, dimensions and frame
   count identical between source and output.
4. **All three stems exist and run full length.**
5. **The bed sits under the voice during speech.**

Two numbers in that output are fixture-specific and will not match a real job:
programme loudness (−15.2) and true peak (−4.2). The fixture's synthetic voice
lands near −15.1 LUFS rather than −14.5, and with only six sine clicks there is
nothing near the ceiling. On a real ExplainTory mix expect **voice −14.5 LUFS in
and out, programme −14.4, LRA ~1.6, true peak −1.0, bed −25.9 dB under speech**.

### If the test fails

| symptom | cause |
|---|---|
| `No module named 'soundfile'` | install the python deps above; check 5 skips without them, the rest still run |
| `command failed (234)` from `common.py` | ffmpeg rejected a filter — the real error is in the `tail` it prints |
| `WAVE files have exactly one stream` | you are on a build from before the `--mux-into` extension fix; see MANUAL-STEPS.md §"Known fixed bugs" |
| voice-unchanged FAIL | `loudness_target_lufs` is not `null` in the cue sheet |
