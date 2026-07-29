# Sound Designer studio

An internal sound-design tool for the ExplainTory channel. It watches a video, decides where
music and sound effects go, pulls the assets from **Epidemic Sound** (via their MCP), and
auto-mixes them **under your voiceover** into a YouTube-mastered file — sidechain-ducked so the
voice is always on top.

It's built as a Claude skill: say *"sound design this video"* with the video (and usually the
mastered VO), and Claude runs the whole pipeline. See [`SKILL.md`](./SKILL.md) for how Claude
drives it; this file is the human quickstart.

## Pipeline

```
video ──▶ analyze.py ──▶ cues.json + cues.md         (music sections, SFX hits, ducking, search seeds)
                              │
        Epidemic MCP  ──▶ fetch.py ──▶ assets/         (Soundmatch / semantic search / track-versions)
                              │
   VO + assets + cues ─▶ assemble.py ──▶ Title (mixed).mp3   (ducked + mastered, −14 LUFS / −1 dBTP)
                                          Title (final).mp4   (optional: muxed back onto picture)
                                          stems/              (optional: music / sfx / vo)
```

The **brain** (`analyze.py`) needs no API. The **hands** (`fetch.py` + `assemble.py`) turn cues
into the mix. Only asset *acquisition* needs Epidemic — and if the MCP isn't connected, you drop
files into `assets/` by hand and skip `fetch.py`.

## Requirements

- `ffmpeg` + `ffprobe` on PATH (`apt-get install -y ffmpeg`)
- `yt-dlp` (only if pulling a source video from YouTube: `pip install yt-dlp`)
- `python3` + `numpy` (`pip install numpy`)

## Connect Epidemic Sound (one time)

Your **Creator plan** includes the Epidemic Sound MCP.

1. In the Epidemic dashboard, open the developer / MCP section and generate an **API key**
   (valid 30 days — regenerate when it expires), or use the OAuth flow.
2. In **claude.ai → Settings → Connectors → Add custom connector**, add
   `https://www.epidemicsound.com/a/mcp-service/mcp` and authenticate.
3. Enable it for the chat. Its tools (Soundmatch, semantic search, track-versions, SFX, voices)
   then appear to Claude, and `fetch.py` can pull what it returns.

No Epidemic connection yet? The tool still produces the full cue sheet with exact search terms —
download those from epidemicsound.com, drop them in `assets/` as `m1.mp3`, `s1.mp3`, … (named by
cue id), and run `assemble.py`.

## Quickstart

```bash
cd .claude/skills/sound-designer/scripts

# (optional) grab a source video
yt-dlp -f "bestvideo+bestaudio" -o in.mp4 "<youtube url>"

python3 analyze.py  --video in.mp4 --vo "Title (final).mp3" --out cues.json --report cues.md
#   → open cues.md, sanity-check the plan

python3 fetch.py    --manifest manifest.json --assets ./assets --cues cues.json   # if MCP connected
python3 assemble.py --cues cues.json --vo "Title (final).mp3" --assets ./assets \
                    --out "Title (mixed).mp3" --stems ./stems
```

## Preview Studio (browser)

`studio.html` is a self-contained preview console — open it in any browser, no server. Load the
cue sheet, the video, the VO and the assets, and it plays the whole thing back **with live Web
Audio ducking**, so you can judge balance and timing without rendering. Faders (bed / duck depth
/ SFX) are live; when it sounds right, **Export cues.json** and pass it to `assemble.py`.

Files are read locally via the file picker — nothing is uploaded. It opens on a demo cue sheet
with synthesized tones so you can hear the ducking before loading anything.

It is a *monitor*, not the master: the browser approximates with scheduled gain automation, while
`assemble.py` renders the real sidechain compressor and the −14 LUFS / −1 dBTP master.

## Rendering previews from the CLI

Don't re-render 12 minutes to check one transition. `--preview` cuts an excerpt out of the
finished master (real loudness, 50 ms fades so it doesn't click):

```bash
python3 assemble.py --cues cues.json --vo "Title (final).mp3" --assets ./assets \
                    --out "Title (mixed).mp3" --preview 0:30-1:00
#   → "Title (mixed) (preview 0:30-1:00).mp3"
```

| Question you're asking | What to render |
|---|---|
| Is the balance right? | audio `--preview` around the busiest passage |
| Does the whoosh land on the cut? | `--mux-into` + `--preview` (preview with picture) |
| Something sits wrong, can't tell what | `--stems` — listen to the bed alone |
| Is the ducking too much/too little? | two renders, one with `--no-duck` or a different `--music-db`, A/B them |

When Claude runs this in a session it sends the rendered files straight into the chat so you can
play them inline — you never need to open a file on the remote machine.

## Notes on honesty

- **Timing is measured** (scene cuts, silence, RMS energy). **Mood/BPM are seeds** for Epidemic
  Soundmatch and your ear to refine — never treated as ground truth.
- The **Sticktory** reference is used for *style* (where music enters, SFX density, energy arc),
  not to identify or copy specific tracks, and its watched timings are never used as numbers.
- Everything stays inside your licensed Epidemic account. No scraping, no ripping.

## Files

| File | Role |
|------|------|
| `scripts/analyze.py`  | video → cue sheet (the brain) |
| `scripts/fetch.py`    | Epidemic MCP results → `assets/` + writes paths back into the cue sheet |
| `scripts/assemble.py` | cue sheet + VO + assets → ducked, mastered mix (the hands) |
| `scripts/common.py`   | shared ffmpeg/ffprobe helpers |
| `studio.html`         | browser preview console (live ducking, faders, export) |
| `SKILL.md`            | how Claude runs the studio end-to-end |
