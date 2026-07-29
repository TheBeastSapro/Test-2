---
name: sound-designer
description: Act as Sapro's sound designer for ExplainTory videos — watch a video, produce a timestamped sound-design cue sheet (music sections + SFX hits + ducking), fetch tracks and SFX from the Epidemic Sound MCP, and auto-mix them under the voiceover into a mastered file. TRIGGER on "sound design this", "score this video", "add music and sfx", "make the sound design", "mix music under the VO", or any request to add music/sound effects to a video. Also use for questions about music placement, SFX timing, ducking, or the Epidemic Sound integration.
---

# Sound Designer

**When Sapro says "sound design this" or "score this video" and gives a video (+ usually the
mastered VO), do the whole job: analyze → fetch assets from Epidemic → mix → deliver the
mastered file.** This is the layer that runs *after* `explaintory-vo-master` has produced a
clean VO. The music and SFX sit under that VO; they never fight it.

Deliver: `<Video Title> (mixed).mp3` (or `(final).mp4` if muxing) at **−14 LUFS / −1 dBTP**,
plus the cue sheet. Report what was placed and the measured loudness.

## The two halves

1. **Brain** (`analyze.py`) — no API needed. Watches the video (scene cuts) and listens
   (silence/voice map + RMS energy) and emits a **cue sheet**: music sections with in/out,
   energy, mood/BPM *seed*, and per-section ducking; SFX hits mapped to scene cuts, reveals,
   and the intro riser. Every cue carries an Epidemic search seed.
2. **Hands** (`fetch.py` + `assemble.py`) — turns cues into a mix. `fetch.py` pulls the tracks
   the Epidemic MCP returns into `assets/<cue id>.wav`; `assemble.py` fits each track to its
   slot, places the SFX, **sidechain-ducks the music under the VO** (~measured live), and
   masters to target.

Timing/structure is **measured**. Mood/BPM are **seeds**, not truth — Epidemic Soundmatch and
your ear refine them. (Same discipline as the VO skill: never treat a listening model's
description as data. This tool trusts ffmpeg measurements only.)

## Runbook

```bash
cd .claude/skills/sound-designer/scripts

# 1. BRAIN — video (+ optional separate VO) -> cue sheet
python3 analyze.py --video in.mp4 --vo "Title (final).mp3" \
    --out cues.json --report cues.md
#   read cues.md; adjust seeds/energy/sections by hand if you disagree.

# 2. FETCH — fill each cue with a real Epidemic asset (see "Epidemic MCP" below).
#    Build manifest.json { "m1": "<url>", "s1": "<url>", ... } from MCP results, then:
python3 fetch.py --manifest manifest.json --assets ./assets --cues cues.json

# 3. HANDS — render the ducked, mastered mix
python3 assemble.py --cues cues.json --vo "Title (final).mp3" \
    --assets ./assets --out "Title (mixed).mp3" --stems ./stems
#    add --mux-into in.mp4 --out "Title (final).mp4" to burn it back onto the picture.
```

`analyze.py` flags: `--scene-threshold 0.4` (lower = more cuts), `--silence-db -30`,
`--silence-min 0.5`, `--sections auto|N`, `--lufs -14`.
`assemble.py` flags: `--music-db`/`--sfx-db` (global trims), `--no-duck`, `--stems DIR`,
`--mux-into VIDEO`.

## Epidemic MCP — the asset layer

Sapro's Creator plan has the **Epidemic Sound MCP** (`https://www.epidemicsound.com/a/mcp-service/mcp`).
Connect it once in claude.ai → Settings → Connectors → *Add custom connector* (URL above,
OAuth or the 30-day API key from the Epidemic dashboard). Once connected + enabled in chat, its
tools appear in the tool list. **If it is not connected, fall back to the manual-drop workflow**
(hand Sapro `cues.md` with the search seeds; he downloads from epidemicsound.com and drops files
named `m1.mp3`, `s1.mp3`… into `assets/`, then run step 3).

When the MCP is connected, for each cue drive it like a sound designer:

- **Music sections** → prefer **Soundmatch**: pass the section's video slice (start→end) so it
  recommends music that fits the *picture*. If Soundmatch isn't applicable, use **semantic
  search** with `cue.epidemic.search`. Then call **track-versions** with
  `target_duration_s` so the track is cut to the slot with its musical structure intact (this
  is better than looping — looping is only the fallback for manually-dropped short tracks).
- **SFX hits** → **semantic search** with `cue.epidemic.search` ("cinematic whoosh transition",
  "deep impact hit", "riser uplifter"). Pick the shortest clean match.
- Collect the returned download/preview URLs into `manifest.json` keyed by cue id and run
  `fetch.py`. Respect the license — only pull assets from Sapro's own Epidemic account.

## Sticktory reference (inspiration, not measurement)

To borrow the Sticktory feel, watch a Sticktory video with the multimodal watch tool and build a
**style profile**: where music enters/exits relative to the VO, SFX density, energy arc, how hard
the bed ducks. Use it to bias the seeds and section energy in `cues.json` *before* fetching. Do
**not** try to identify exact Sticktory tracks from audio, and do **not** take the watch tool's
timings as numbers — it informs taste, `ffmpeg` sets the clock.

## Defaults are the approved starting point

Ducking is a −30 dB-threshold, 6:1 sidechain (musical, VO always on top). Master is
`loudnorm I=−14:TP=−1:LRA=11`. SFX sit −6 to −9 dB under the bed; music beds duck to −9 dB
under voice, −3 dB in gaps. Expect one round of ear-checking on bed level and duck depth —
Sapro's ear catches what the meters call fine.
