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

## The StickTory sound — what the channel actually does

Observed by watching (structure and vocabulary only; every number in this file is measured
separately). This is the brief. Match it.

**The signature, in one line:** *tight synchronisation between rhythmic tension music and
literal, exaggerated foley — every visual action punctuated by a specific, high-fidelity sound
that sits **prominently above** the music.*

Four things that follow, and each one is a mistake this tool made first:

1. **SFX sit ABOVE the bed, not under it.** They are the foreground. Placing hits at
   -15…-22 dB buries them and reads as "no SFX". The bed is the thing that gets out of the way.
2. **Literal foley, not abstract transitions.** Cloth rustle on a hood going up, leather
   footsteps on dirt, a metallic unsheathe, a wet thud when a body lands, non-verbal
   vocalisations (gasps, grunts, an "hmm"). A generic whoosh where a cloth rustle belongs is
   the difference between "dense" and "designed".
3. **Layered stacks on the big actions.** A fall is *whoosh + scream + wet thud*, not one hit.
   Single-sample cues are for small moves.
4. **There is almost always an ambient bed** — wind, outdoor air, room tone. Scenes are rarely
   dry. This tool shipped completely dry mixes.

**Music:** hybrid tension beds — cinematic percussion (taiko, deep kicks), staccato strings,
low synth pulses. **Highly rhythmic with a driving pulse**, not ambient wash. It *acts*:
menacing, playful, triumphant as the story turns.

**Do not score each era with its own regional instruments.** The palette stays **consistent** —
cinematic/historical tension throughout — and cues change within that family. Swapping to taiko
for Japan and oud for Persia is off-brand for this channel; it reads as a compilation, not a
score. (This tool did exactly that on its first pass at the sword video.)

**Era/title cards:** heavy cinematic boom plus a deep whoosh.

## Density, variety and level — the three numbers behind "this sounds cheap"

Measured on the first full sword-video render, not guessed. When a mix is described as
"placed by a cheap guy", "irritating", or "repetitive", it is almost always one of these,
and all three are countable before anyone listens:

**1. How many distinct files are you actually using?** That render had 474 cues drawn from
**seven** files — one tick played **240 times**, a whoosh 148. Thirteen minutes is long enough
for the ear to learn a sample and then hear the seam instead of the picture. Count it:

```python
collections.Counter(os.path.basename(c["asset"]) for c in cues["sfx_cues"]).most_common(5)
```

Rule of thumb: **no file more than ~10 times in a 13-minute video, and never twice inside
30 seconds.** Getting there means a real palette (~80 sounds across categories), not a
keyword search per cue. `pal/` + `rebuild_cues.py` in the job dir is the working example.

**2. Are the hits masking each other?** `sync_check.py` reports onsets detected vs cues placed.
That render: **723 onsets for 474 cues, and 148 cues never matched an onset at all.** More
onsets than cues means tails are overlapping into false attacks; unmatched cues mean hits are
being buried by their neighbours. Both say the same thing — too dense. One cue per 1.5 s is
too many; **~2.2 s with a per-tier guard** kept everything meaningful and audible.

Guard by tier, and resolve collisions by **priority, not by strength** — a caption tick must
never elbow a sword strike. Hand-timed beats are exempt from the guard *against each other*:
an era card is deliberately a whoosh leading into a boom 0.4 s later.

**3. Are the SFX above the bed?** That render's SFX bus peaked at **-23.7 dB**. The music bed
sits at -13 dB. Everything was under the music, which is why whole minutes read as having no
SFX. Levels that work, relative to the voice:

| tier | gain | guard |
|---|---|---|
| hero boom (era card, stated turn) | -5 dB | 2.2 s |
| hero hit (hand-timed beat) | -7 dB | 1.3 s |
| impact (strong on-screen action) | -8 dB | 1.1 s |
| whoosh (shot change) | -12 dB | 1.0 s |
| swish (element moves) | -15 dB | 0.85 s |
| pop (caption, small element) | -19 dB | 0.8 s |

**Normalise the palette before placing anything.** Across 81 library files the peak spread was
**15 dB** (+12.3 to -2.8). Without a normalise pass the table above means nothing. Trim leading
silence at the same time — several files start 100-300 ms before the attack, which puts the hit
late by exactly that much and leaves the mixer's transient search to guess.

**Two cheap wins that cost nothing:**
- *Anticipation layers.* A strike gets a short swish 0.13 s before contact. One sound is a
  sample; two is a designed hit.
- *Ambience beds.* The answer to "this area has no SFX" is room tone, not more hits. A wind or
  battlefield bed at **-28 to -30 dB** under each section is never consciously heard, and its
  absence is. Do not run beds through the SFX room impulse — a room tone already is a room.

`polish_sfx()` in assemble.py handles what separates "satisfying" from "irritating" on the bus
itself: a dip at 2.4/3.6 kHz so effects stop masking consonants, -3 dB above 9 kHz so repeated
hits don't fatigue over thirteen minutes, a low shelf for body, and a short convolved tail so
hits sound placed rather than pasted. The chain costs 2.8 dB — the makeup is built in.

## LOOK AT THE FRAMES. Never place a hit you have not seen.

This is the single most important rule here, and it was learned by getting it wrong on a real
video. Placing SFX at "a fraction through the section, snapped to a nearby cut" produced:

| Beat | Guessed | Actually on screen | Error |
|---|---|---|---|
| the counterfeit ULFBERHT shatters | 4:29.8 | 4:48.4 | **19 s** |
| katana clay-quench | 8:11.7 | **not in that section at all** | invented |
| the smith at the anvil | never placed | 6:39.5, in the *shamshir* entry | missed |
| Renaissance era change | 8:46.5 | 8:42.1 (the title card) | 4.4 s |

The katana one is the lesson: that section is entirely the "paperwork disagrees" argument --
cutting demo, wound registers, Suzuki, the wound-cause chart -- and contains no forging
whatsoever. A steam sizzle would have played over a bar chart.

**Method.** Build contact sheets and read them:

```python
# 9 frames across a section, tiled 3x3, sampled at the detected scene cuts
ffmpeg -ss <t> -i video.mp4 -frames:v 1 -vf scale=440:-1 f_<i>.jpg    # per frame
ffmpeg -i f_0 .. -i f_8 -filter_complex \
  "[0][1][2]hstack=3[r1];[3][4][5]hstack=3[r2];[6][7][8]hstack=3[r3];[r1][r2][r3]vstack=3[o]" \
  -map "[o]" sheet.jpg
```
Then `Read` the sheet, note which panel holds the beat, and use that panel's timestamp. Six
sheets of 9 frames cover a 13-minute video at ~15 s granularity -- enough to find every era
card and every payoff shot. Refine with a tighter sheet where a beat needs sub-second placing,
then snap to the nearest scene cut within ~1.5 s so it lands on the picture change.

**Two things the frames give you for free:**
- **Era title cards are on screen** (BRONZE AGE, IRON AGE, ...). Snap the music section
  boundaries to the frame the card appears on, not to a scaled estimate from the script.
- **The retention peak is visible.** On the sword video it is the wound-cause chart reading
  "Sword -- Very Low". That gets the riser and the impact; nothing else in the video needs
  them more.

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
