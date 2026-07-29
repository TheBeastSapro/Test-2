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
`--mux-into VIDEO`, `--preview START-END`.

## Preview Studio

`studio.html` (repo root of this skill) is a browser preview console: cue sheet + video + VO +
assets in, live playback with Web Audio ducking out, live bed/duck/SFX faders, and an
**Export cues.json** that carries the tuned values back to `assemble.py`. Point Sapro at it when
he wants to *tune* rather than *check*. It reads files locally; nothing uploads.

## Previewing (how Sapro actually hears it)

He is on a remote container — he cannot open files on this machine. **Send the rendered file
with `SendUserFile` (`display: "render"`) so it plays inline.** Always preview before declaring
the job done.

- **Excerpt, don't dump a 12-minute render.** `--preview 0:30-1:00` writes
  `<name> (preview 0:30-1:00).mp3` — the real master, just cut, with 50 ms fades. Pick the
  moments that matter: the intro riser, the first duck, a reveal impact, a section change.
- **A/B when a judgement call is in play** (bed level, duck depth, whether an SFX belongs):
  render both, send both, name them so the difference is obvious. Do not describe the
  difference in prose and ask him to imagine it.
- **Send `--mux-into` previews** when the question is *timing against picture* (does the whoosh
  land on the cut?); send audio-only when the question is *balance*.
- **Send `--stems`** when he says something sits wrong but can't place what — hearing the bed
  alone answers it fast.

## Epidemic MCP — the asset layer (VERIFIED LIVE)

Connected and tested. Real tool names and shapes:

| Tool | Use |
|---|---|
| `SearchRecordings` | music. Filter supports **`vocals: false`**, `bpm{min,max}`, `duration{min,max}` (ms), `moodSlugs`, `tagSlugs`, `musicalKeys`, `featuredInstrumentSlugs` |
| `SearchSoundEffects` | SFX. Same `duration` filter — cap it so you get hits, not beds |
| `SearchSimilarToRecording` / `...SoundEffect` | "more like this one" once a cue lands |
| `DownloadRecording` | `(id, options{fileType: MP3\|WAV, stemType: FULL\|INSTRUMENTS\|BASS\|DRUMS})` -> `assetUrl` |
| `DownloadSoundEffect` | same, for SFX |
| `EditRecording` + `PollEditRecordingJob` | fit a track to a target duration keeping musical structure — the right move for a section, better than looping |
| `GenerateVoiceover` / `ListVoices` | AI VO; not used, ExplainTory VO comes from the VO-master skill |

Push constraints into the **query**, don't just filter afterwards: set `vocals: false`,
`bpm` around the cue's `bpm_hint`, and `duration.min` >= the section length. Use
`stemType: INSTRUMENTS` when a track is right but its lead is too busy under the VO.

Response shape (results nest one level deep, duration is in **milliseconds**):

```
{"data":{"recordings":{"nodes":[{"recording":{"id","title","bpm",
   "audioFile":{"durationInMilliseconds","lqmp3Url","waveformUrl"},
   "tags":[{"displayName","slug"}]}}]}}}
```

`scripts/epidemic.py` normalizes exactly this, so raw MCP output can be dumped
straight to a file and piped in:

```
epidemic.py select --cues cues.json --candidates raw_mcp.json \
                   --out picks.json --manifest manifest.json
epidemic.py fetch  # or: fetch.py --manifest manifest.json --assets ./assets --cues cues.json
```

`select` scores every candidate against the cue (instrumental, bpm distance, energy,
tag overlap, duration fit, reuse penalty) and records **why** it picked each winner
plus the runners-up. That judgement is the skill's job — never hand Sapro a shopping list.

### Network requirement (hard blocker)

`DownloadRecording` returns a **signed URL on `audiocdn.epidemicsound.com`**. Downloading
it happens from *this container*, not Claude's backend, so that host must be allowlisted in
the environment's network policy. Verified failure mode when it is not:

```
curl: (56) CONNECT tunnel failed, response 403
```

Allowlist `audiocdn.epidemicsound.com` (plus `epidemicsound.com`). Search works without it;
downloads do not. If it is blocked, say so plainly and fall back to handing over the picks
with their titles — do not pretend the mix is done.

## Sticktory reference (inspiration, not measurement)

To borrow the Sticktory feel, watch a Sticktory video with the multimodal watch tool and build a
**style profile**: where music enters/exits relative to the VO, SFX density, energy arc, how hard
the bed ducks. Use it to bias the seeds and section energy in `cues.json` *before* fetching. Do
**not** try to identify exact Sticktory tracks from audio, and do **not** take the watch tool's
timings as numbers — it informs taste, `ffmpeg` sets the clock.

## Levels — Sapro's house rule

**Music and SFX sit at 10% — that is −20 dB** (20·log10(0.1)). This is what he tells a human
sound designer, so it is the starting point here too, not a suggestion:

```
assemble.py ... --music-db -20 --sfx-db -12
```
`--sfx-db -12` because the cue sheet already writes SFX at −6…−9 dB, so −12 more lands them
around −20 too. Verify by measuring the bed inside a VO gap — it should read roughly 20 dB
below an untrimmed render, not by trusting the flag.

Ducking still applies on top: the bed is at 10% *and* ducks under the voice. Master is
`loudnorm I=−14:TP=−1:LRA=11`.

## Calibrating from Sticktory — measure, never listen

To copy Sticktory's balance, do **not** ask an audio model how loud the music is. Measure the
published mix: in the **silences between VO lines the music bed is playing alone**, so
`silencedetect` finds those gaps and `volumedetect` over them gives the true bed level. Compare
that against the level during speech and the bed-to-voice ratio falls out as a number.

```
yt-dlp -x --audio-format wav -o ref.wav "<sticktory url>"
ffmpeg -i ref.wav -af silencedetect=noise=-30dB:d=0.4 -f null -   # find gaps
ffmpeg -i ref.wav -af "atrim=<gap>,volumedetect" -f null -        # bed alone
```
This is the same discipline as the VO skill: the aligner and the meters are data, a listening
model's description is not. Expect one round of ear-checking on bed level and duck depth —
Sapro's ear catches what the meters call fine.
