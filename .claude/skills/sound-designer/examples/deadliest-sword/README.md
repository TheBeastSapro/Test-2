# The Deadliest Sword From Every Era — job data

Everything needed to reproduce this video's sound design without re-deciding any
of it. The prepared palette itself is 243 MB of wav and is deliberately *not*
here: it is fully derived from `ulids.txt` by `rebuild_palette.py`.

| file | what it is |
|---|---|
| `cues.json` | the finished cue sheet — 363 events, 495 cues with layers, 24 beds |
| `cues_prev.json` | the source sheet: 17 music sections + the hand-timed beats |
| `build_beats.py` | derives the hand-authored sheet from `cues_prev.json` + `redraw.json` |
| `redraw.json` | visual beats from `visual_redraw.py` — 107 cuts, 225 actions, 135 elements |
| `palette_manifest.json` | the 107-file palette: categories, per-file anchors, front-load ratios, bed rms |
| `ulids.txt` | Epidemic CDN ids for every palette file |
| `music_manifest.json` | the 17 chosen music tracks |

## Rebuilding from scratch

```bash
cd <a working dir>
cp <this dir>/{ulids.txt,cues_prev.json,redraw.json,build_beats.py} .
python3 <skill>/examples/deadliest-sword/rebuild_palette.py --scripts <skill>/scripts
python3 build_beats.py
python3 <skill>/scripts/place.py --cues cues_beats.json --events redraw.json \
        --palette pal --out cues.json
python3 <skill>/scripts/assemble.py --cues cues.json --vo vo.wav \
        --out "mix.mp3" --stems stems
```

`redraw.json` is included so the detection pass (~20 min of video decoding) can be
skipped. Regenerate it with `visual_redraw.py video.mp4 -o redraw.json` if the cut
of the video changes — every cue time is derived from it.

The voiceover and video are not here; supply `vo.wav` and `video.mp4` yourself.
