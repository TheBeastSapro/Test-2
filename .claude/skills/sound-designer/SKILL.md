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

## StickTory reference — MEASURED

Two full mixes, measured with `scripts/measure_ref.py`. These numbers replace every earlier
estimate, including the ones a listening model gave.

| | Bounty Hunter | Roman Legion |
|---|---|---|
| Runtime | 10:17 | 11:01 |
| Programme | **-23.1 LUFS** · LRA 2.3 · TP -5.0 | **-21.5 LUFS** · LRA 2.6 · TP -2.6 |
| Bed floor (p10) | -31.2 dBFS | -34.1 dBFS |
| Programme body (p50) | -23.0 dBFS | -21.5 dBFS |
| **Bed under programme** | **-8.2 dB (39%)** | **-12.6 dB (23%)** |
| Cue changes (bed floor shifts >=3 dB) | 13 -> one per **48 s** | 14 -> one per **47 s** |
| Hard dropouts (< -50 dBFS) | 1 (1.0 s, the outro) | 3 (1.4 s total) |

### What this changes

0. **CORRECTED: the bed target is -13 dB, and it must be CALIBRATED, not trimmed.**
   A flat `--music-db` is not a relative level -- the VO is a hot mastered file while library
   tracks arrive at their own levels, so the same trim lands differently on every video. On a
   real job `--music-db -10` produced a bed **21.6 dB** under the voice (9%), not 30%.
   `assemble.py` now measures the music bus and the VO in LUFS and solves for the trim
   (`--bed-target-db`, default **-13**); `--no-bed-calibration` restores the old behaviour.

   The -13 figure is exact, not inferred: the StickTory *Bounty Hunter* VO stem was measured
   against that video's own full mix. Every window where the narrator is silent in the stem is
   music-alone in the mix, so the ratio falls straight out -- **-13.1 dB, 22% linear** (median
   of 5 true gaps; their VO has only 6 gaps >=0.6 s in 10 minutes, as dense as ExplainTory's).

1. **SUPERSEDED (kept for history): bed at -10 dB, master at -14 LUFS.** Sapro chose the measured level over his
   own 10% instruction after seeing the numbers. `--music-db` now defaults to **-10.0**, so
   this is the behaviour without any flag. Verified end to end: a render at the default
   measures a bed **-10.3 dB** under programme (references: -8.2 and -12.6) at **-13.9 LUFS**,
   LRA 2.5 (references: 2.3 and 2.6).

   He keeps **-14 LUFS** rather than matching the channel's -21.5/-23.1, so delivered mixes
   sit ~8 dB hotter than his back catalogue. That is deliberate and correct for YouTube --
   mention it once when handing over the first mix, then stop mentioning it.
2. **A cue change every ~47 s.** `SECTION_SECONDS = 47.0` in `analyze.py` comes straight from
   this; it reproduces 13 and 14 sections for these two runtimes. The old `duration/90` capped
   at 6 was less than half the real rate.
3. **There are essentially no music dropouts.** A listening model claimed frequent "comedic
   dead air"; measurement finds 1 and 3 hard dropouts totalling ~1 s, one of them the outro.
   Do not build a dropout feature on that claim.
4. **Both masters sit 7-9 dB below YouTube's -14 LUFS target**, with 2.6-5.0 dB of unused
   headroom. Worth raising with Sapro: on YouTube these play noticeably quieter than
   competing content. `assemble.py` targets -14 by default, so a delivered mix will sound
   louder than his back catalogue -- flag that rather than surprising him.
5. LRA 2.3-2.6 LU, consistent with the 1.6 LU measured on the ExplainTory human VO stem.
   The channel's dynamics are deliberately flat; don't "fix" that.

Structural notes still worth keeping from watching (placement, not levels): SFX land tightly on
cuts and text pop-ins, the duck is pronounced, and cue mood tracks the story beat rather than
escalating linearly.

## SFX must follow the scene, not the cut

Generic whooshes on scene cuts are the lazy version and it shows. StickTory syncs sound to
what is actually happening on screen -- "Mickey Mousing" -- so source **literally** and place
on the beat.

The script usually hands you the beats for free. ExplainTory scripts carry an animator
reference listing a SYNC note per entry; read it and turn each note into a sound:

| Script beat | Sound |
|---|---|
| "the fake failing with visible slag" | glass smash |
| "coated in clay, quenched so the edge froze glass-hard" | steam sizzle on hot metal |
| "three weapons in one: cut → half-sword thrust → pommel" | three separate hits, spaced |
| "thrown in short stabs that traveled inches" | metal clash on the shield line |
| "reached over and around Roman shields" | clash on the hook |

Useful Epidemic searches, all verified to return tight usable hits: `sword unsheathe metal
blade ring draw`, `sword clash metal impact hit blade`, `glass metal shatter break`,
`hot metal quench steam hiss forge`. Cap `duration` at 3-4 s so you get hits, not beds.

Place each beat at a sensible fraction through its section, then snap to the nearest scene cut
within ~3 s so it lands on picture. Era changes get a short blade draw; save the big impacts
for the rehook and the closer.

### YouTube audio cannot be downloaded from this container

Do not spend a session rediscovering this. With network access on **Full**, the proxy tunnel
opens and YouTube's *API* responds, but every **media** fetch returns `HTTP Error 403`.
Confirmed against an unrelated control video, so it is the IP range, not the video:

| Attempt | Result |
|---|---|
| `player_client=android` | API fine, media **403** |
| `player_client=ios/mweb/web/web_safari` | "Sign in to confirm you're not a bot" |
| `player_client=tv` | "This video is DRM protected" |
| `--impersonate chrome` (curl_cffi) | TLS reset — the agent proxy's MITM breaks fingerprinting |

**The fix is not a setting.** To measure a reference video, ask Sapro to attach the audio (or
the video file) to the chat and measure the local file. Everything downstream works normally —
this only blocks pulling from YouTube directly.

## Levels — Sapro's house rule

**SUPERSEDED by measurement — the bed sits at −10 dB, not 10%/−20 dB.** Sapro's original
instruction to human sound designers was 10%; measuring two of his own mixes showed the channel
actually ships 23–39%. He reviewed the numbers and chose the measured level. `--music-db`
defaults to −10.0, so no flag is needed:

```
assemble.py --cues cues.json --vo vo.mp3 --assets ./assets --out "Title (mixed).mp3"
```
SFX keep their per-cue gains (−6…−9 dB), which puts hits a few dB above the bed — right for
transients. Verify with `measure_ref.py` on the output, not by trusting the flag.

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
