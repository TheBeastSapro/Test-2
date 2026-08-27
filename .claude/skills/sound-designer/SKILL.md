---
name: sound-designer
description: Act as Sapro's sound designer for ExplainTory videos — watch a video, produce a timestamped sound-design cue sheet (music sections + SFX hits + ducking), fetch tracks and SFX from the Epidemic Sound MCP, and auto-mix them under the voiceover into a mastered file. TRIGGER on "sound design this", "score this video", "add music and sfx", "make the sound design", "mix music under the VO", or any request to add music/sound effects to a video. Also use for questions about music placement, SFX timing, ducking, or the Epidemic Sound integration.
---

# Sound Designer

**When Sapro says "sound design this" or "score this video" and gives a video (+ usually the
mastered VO), do the whole job: analyze → fetch assets from Epidemic → mix → deliver the
mastered file.** This is the layer that runs *after* `explaintory-vo-master` has produced a
clean VO. The music and SFX sit under that VO; they never fight it.

Deliver: `<Video Title> (mixed).mp3` (or `(final).mp4` if muxing) with the **VO at
exactly the level it arrived**, plus the cue sheet. Report what was placed, the VO
level, and the programme level.

**ANCHOR THE MASTER TO THE VOICE, NEVER TO A PROGRAMME TARGET.** The VO arrives
already mastered by `explaintory-vo-master`. A programme-loudness target — any
programme-loudness target — silently moves it, because the voice *is* most of the
programme. Asked to "match the StickTory loudness" I mastered to −21.5 LUFS, which
applied a flat −7.6 dB to everything and landed the delivered voice **7.6 dB below
the file Sapro had sent me**. His note: *"you actually reduced the voice as well."*

So: sum music + SFX + VO at unity, limit for safety, and ship. Do not normalise the
sum. Programme loudness is then an *output*, not an input — it lands a fraction above
the VO's own level (measured: VO −14.5 LUFS, programme −14.4) and that difference is
exactly how much music and SFX are present. Report both numbers.

If a specific programme loudness is ever genuinely wanted, it is a decision about the
voice and has to be said that way — "master the voice to X" — because that is what it
does. Matching a reference channel's *programme* number means matching how loud their
narrator is, which is not usually what is being asked for.

```
ffmpeg -i music.wav -i sfx.wav -i vo.wav -filter_complex \
  "[0][1][2]amix=inputs=3:normalize=0[x];[x]alimiter=limit=0.891:level=disabled[a]" \
  -map "[a]" out.mp3          # the VO comes out exactly as it went in
```

In a cue sheet that is `"loudness_target_lufs": null`, and until the castle job that
setting **could not actually be rendered**: `final_master` interpolated the value
straight into the filter string, handed ffmpeg `loudnorm=I=None`, and died at the last
stage of a nine-minute render. Fixed — a null target now skips loudnorm entirely. If
you are reading this because a render just failed there, the fix is already in
`assemble.py`; the lesson is that the documented setting and the code path that
implements it are two different things, so render a 30-second `--preview` before
committing to a full pass.

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

## Intake for a new video — follow this order, it removes the back-and-forth

The first video took many rounds because the tooling was being built. It should not
happen again.

**A four-line brief is COMPLETE INPUT. Start work; do not ask for more.**

```
Sound design this ExplainTory video, StickTory style.

Video: <drive link>
Voiceover: <drive link>          <- mastered VO as a SEPARATE file, always
Title: <title>
Script: <doc link>
```

That is everything Sapro should ever have to type. The VO must be separate because both
the ducking and the bed level are calibrated against the VO stem — a mix-down cannot be
used. Links are Drive because YouTube downloads are blocked from the container.

**If only the video arrives, check its audio before asking for anything.** An
ExplainTory cut carries the mastered VO and nothing else, and it measures like one:
−14.5 LUFS, LRA 1.6–1.7, zero silences ≥0.6 s. `ffmpeg -i in.mp4 -vn -ac 1 -ar 48000
vo.wav` then gives a usable VO stem, so the separate file is not needed — it is needed
when the supplied cut already has music on it, which those numbers will tell you.

**And if the script is missing, transcribe it rather than asking.**
`pip install faster-whisper`, `base.en`, a couple of minutes on CPU, and the whole
script is available. Proper nouns come out mangled — Krak des Chevaliers as "Crackday
Chevelier", portcullis as "Port Colus", Château Gaillard as "Guy Lard" — but every
story beat and its timing is there, which is all the casting needs, and the picture
decides the casting anyway. Ask only if that fails; everything else below is your job
to do unasked.

Then, in this order — **all of it is default behaviour, not something to be told:**

1. **`visual_redraw.py video.mp4 -o redraw.json`** — the beats. Do not use optical flow
   for animation. Do not skip this and guess times from the script.
2. **Rebuild the palette** rather than re-choosing sounds:
   `examples/deadliest-sword/rebuild_palette.py --scripts scripts/`. It reproduces 107
   prepared files from a 3.7 KB id list in ~2 min. Fetch only what the new video needs
   on top, with `epidemic_api.py` (not the MCP connector).
3. **Build the music sections from the script's chapters**, one cue per topic — measured
   at a change every ~47 s on this channel. `examples/deadliest-sword/build_beats.py` is
   the working pattern.
4. **Hand-cast the first 2–3 minutes beat by beat**, off contact sheets. This is where
   the audience decides, and pool-casting is not good enough there. Extract contact
   sheets at 4 fps and *look* — check what each blade is touching.
5. `place.py` → `assemble.py --stems`.
6. **Verify before showing anything:** `sync_check.py --by-tier`, and measure the bed on
   the stems. Report the numbers.
7. **Send 3–4 short clips WITH PICTURE at the specific action beats** — not the whole
   mix. Every correction on the first video came from watching a specific moment, and
   sending clips early is what turns five rounds into one.
8. Only after those are approved, deliver the full mix.

**Expect exactly one round of notes, and expect it to be about casting** — whether each
sound is the right *object* for what is on screen. That is the one thing measurement
cannot settle and Sapro's eyes can. Anything else taking a second round means a rule
belongs in this file; write it here rather than fixing it silently.

**If the topic is not history or warfare**, say so up front: 60 of the palette's files
(pop, swish, whoosh, impact, boom, ambience) carry over to anything, and ~47 (stab,
shield, armour, marching, forge, draws, falls, clatter) only apply to combat. Budget
20 minutes to fetch a topical set with `epidemic_api.py` and say that at the start
rather than discovering it mid-mix. `place.py`'s HERO_CAT maps script words to
categories and its vocabulary is weapon-flavoured — extend it for the new subject.

**CORRECTION from the warships job: three categories get REPLACED, not supplemented,
and `impact` is one of them.** The list above says impact and ambience carry over.
They do not, because they name *objects*. `impact` is eleven metal-on-metal blade
clashes, `body` is four flesh punches, and `amb` is medieval battle and village tone —
so on a naval video every generic strike is a sword hitting a ship and every scene sits
in a field. Those three are what the generic pool draws from (`impact` for strikes,
`body` as the default weight layer under them, `amb` for beds), so getting them wrong
is not a detail at the edges; it is most of what the viewer hears. Delete them from
`pal/` and rebuild them for the subject. What genuinely carries is the vocabulary of
air and transients — pop, swish, whoosh, boom, clatter, fall — plus the vocals.

For reference, the naval set that replaced them was 169 files across 33 categories
(sea/harbour/underwater/engine-room beds, hull creak, oars, sail canvas, cannon, steam,
gears, winch, sonar, ship horn, dive alarm, torpedo, underwater explosion, chain, ship
bell, bubbles, wood break, ram crash, hatch, plane, and so on), fetched in about 25
minutes with four batched `SearchSoundEffects` rounds read by title. That is the real
budget for a new subject: closer to half an hour than twenty minutes, and worth saying
so at the start.

**Fresh containers are missing three Python packages** the scripts need, and the
failure lands late: `rebuild_palette.py` downloads all 113 files and *then* dies with
`ModuleNotFoundError: No module named 'soundfile'` at the oneshot step. Install first:

```
pip install opencv-python-headless numpy soundfile librosa
```
(`cv2` for `visual_redraw.py`, `soundfile` for `oneshot.py`/`palette.py`, `librosa` for
`sync_check.py`.)

**Downloading a Drive video works** — a 1 GB mp4 in about 40 seconds, no auth needed
for a link-shared file:
```
curl -sL "https://drive.usercontent.google.com/download?id=<FILE_ID>&export=download&confirm=t" -o video.mp4
```

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

## A stem trim is not a bus trim — the room tone is inside the SFX stem

Recombining `stems/` at different gains is the right way to A/B a level question
in seconds instead of re-rendering for ten minutes. It has one trap, and it was
walked into: `assemble.py` merges the ambience beds **into the SFX bus** after the
polish stage, so the written `sfx.wav` stem contains hits *and* room tone. Trimming
that stem cuts both.

A real render does not do that. `--sfx-db` is added inside `render_sfx_short`, so it
reaches the hits only; every bed keeps its own per-bed `gain_db`, solved from that
file's measured rms. That distinction is the whole point of the bed system — a bed
at -42 dBFS "is never consciously heard and its absence is" — and a stem trim
quietly undoes it. Two rounds of level notes were answered with A/B renders that
were also 6 dB down on the room tone, i.e. answering a "too loud" note by making
the mix dry.

**Use stem recombination to find the number, then re-render to ship it.** And when
reporting, do not quote the SFX bus average as if it described the hits: with beds
merged in, the average is dominated by continuous room tone, not by transients. On
the warships mix, dropping every hit by 2.5 dB moved the bus average by **0.5 dB**.
Quote the trim you applied to the hits, and the bed's level, separately.

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

**`vocals: false` is not airtight — check the tags.** Measured live, **12 of 60** results
returned under that filter still carried a **`vocal presence`** tag. The filter means "not a
lead-vocal song", not "no human voice", so choir and chant pads come straight through it.
Under a narration track a choir is as bad as a singer. Trust the tags, not the filter —
`epidemic_api.py` now flags every leaked result in its search output.

**CORRECTION — this was NOT what caused "unnecessary vocals in the background" at 9:14.**
That was diagnosed from this leak without measuring, and the measurement says otherwise: the
Renaissance track is *The Vice*, tagged `action, dark, electronic rock, no vocals, suspense`,
with no vocal tag at all. The voices were an **ambience bed** — `amb_07`, whose Epidemic title
is literally *"Crowds, Battle, Medieval, Village Battle Ambience, **Voices, Yells**"* — running
under the whole 44.8 s section at -16 dB. See "Room tone must not contain a second voice"
below. The filter leak is real and worth guarding; it just wasn't this bug.

And treat vocals as **disqualifying, not a penalty**. `score_music` docked them 6 points,
which a track matching bpm, energy and three moods banks back easily, so the *best-fitting*
vocal track beat a plainer instrumental. It is a hard reject now, and a cue whose whole
candidate pool is rejected fails loudly rather than picking the least-bad choir.

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

**"Floaty" is a casting error, not a level problem.** The Golden Age of the East section was
reported as "float music, bit annoying". The reflex is to pull the bed down, but a drifting
ambient track at -16 dB is still a drifting ambient track — it just annoys more quietly, and
it drops the section below the channel's measured bed level to buy that. The brief above is
the fix: this channel's music is *rhythmic with a driving pulse*, never ambient wash. Replace
the cue, and only then check the level. Reach for a per-section `gain_db` (it stacks with
`--music-db`) when a correctly-cast cue is merely a touch hot — not to sedate a wrong one.

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

## Anchoring: place the sound's *perceived* moment on the beat, not its first sample

The single biggest sync lesson from the sword video, and it took five renders to get right
because each fix exposed the next one. Run `sync_check.py --by-tier` — the **per-tier**
breakdown is where the diagnosis lives; the headline number only ever said "scattered".

The rule that works, in order:

1. **Trim leading silence once, at palette prep.** Never also run a per-render transient
   search — doing both compensates twice and threw slow-blooming whooshes 300 ms early.
2. **Store a per-file anchor**: where the first 15% of the file's energy has accumulated.
   Per *file*, not per category — the spread inside a category is what makes the p90.
3. **Zero the anchor for anything front-loaded** (≥40% of peak level inside the first 30 ms).
   If it starts with a bang, the bang *is* the moment. This is what finally fixed era-card
   booms, which sat 59 ms early through two earlier rounds because a boom is a transient
   followed by a long sub tail.
4. **Subtract a one-frame deadband** from the rest. Only rise time beyond a frame is real ramp.
5. **Cast beats that must hit a mark with front-loaded files.** A swell cannot land on a frame.
   Two of six boom files were swells; using them on era cards was a casting error, not a
   timing one.

Metrics that were tried and are *worse*, so don't repeat them:
- *Time to 60% of peak* — breaks on any multi-hit file. Across five blacksmith files it locked
  onto the loudest **late** hammer strike: median 749 ms where energy accumulation finds the
  first strike at 127 ms.
- *Steepest envelope rise* — finds later swells. 203 ms for pops (vs 17) and 492 ms for forge
  files (vs 127).

Where that landed on a 13-minute video, 314 events, 438 cues:

| tier | median | p90 | within one frame |
|---|---|---|---|
| hand-timed beats | −3.8 ms | 12.8 ms | **100%** |
| impact | +2.1 ms | 104.7 ms | 87.9% |
| era-card boom | −1.1 ms | 39.0 ms | 86.7% |
| swish | +16.6 ms | 46.7 ms | 85.9% |
| pop | −17.3 ms | 61.6 ms | 75.4% |
| whoosh | −8.3 ms | 213.5 ms | 40.4% |
| **overall** | **−0.6 ms** | **74.5 ms** | 75.2% |

**Do not chase the whoosh number.** A 400 ms ramp has no well-defined onset, so the metric
cannot pin it: measured against the cue the p90 is 212 ms, and measured against the file's own
start it is *worse* at 265 ms. The median (−8 ms) says the placement is centred correctly.
Overall "within one frame" will sit around 75% for this reason, and that is fine.

**Master ceiling:** `loudnorm`'s true-peak limiter is not tight in single-pass mode and the mp3
encoder overshoots after it — a master asked for −1.0 dBTP came out at −0.2 once the SFX were
levelled as foreground. `final_master` appends an explicit `alimiter`, which brings it to −0.7.

## Fetching assets without the MCP connector (do this — it stops the dropouts)

The claude.ai MCP connector for Epidemic dropped in and out repeatedly across one
session, taking search and download with it each time. It is not the only way in.

Epidemic's MCP endpoint also accepts a plain bearer token, so `epidemic_api.py`
reaches the same catalogue over an ordinary HTTPS request from inside the container.
Nothing outside the container can disconnect it.

```
epidemic_api.py sfx "sword hits wooden shield" -n 12 --min-ms 200 --max-ms 4000
epidemic_api.py pull <id> <id> --out pal_raw --name clink
```

Setup, once:
1. Generate a key at **https://www.epidemicsound.com/account/api-keys**. It is tied to
   the user's own Epidemic account — **no partnership agreement needed**. (The separate
   Partner Content API at `partner-content-api.epidemicsound.com` *does* require one.
   This does not.)
2. Store it as `EPIDEMIC_SOUND_API_KEY` in the cloud environment's environment
   variables. **Never in chat** — chat is stored, environments are not.
3. Keys last **30 days**. A 401 means regenerate, and the script says so.

Prefer this over the connector for any real job. Use the MCP tools only for
exploration when they happen to be up.

**`query`, `filter` and `options` are objects, not JSON strings.** Passing them
stringified — which `epidemic_api.py` did — fails every search with:

```
{'errors': [{'message': 'Unexpected error occurred',
             'path': ['variable', 'query'],
             'extensions': {'code': 'GRAPHQL_VALIDATION_FAILED'}}]}
```

Nothing in that says "wrong type", and `tools` still connects fine, so it reads
like an expired key or a server fault and sends you to regenerate a key that was
never the problem. The authority is the tool's own `inputSchema`, which types
`query` as `$ref: SoundEffectsQuery` (an object). Dump it when a call is
rejected and the answer is usually right there:

```python
c = Client(api_key()); c.initialize()
[t["inputSchema"] for t in c.list_tools() if t["name"] == "SearchSoundEffects"]
```

## Panning: a static sound under a moving picture reads as stuck

Reported on a shot of a legion advancing right-to-left: "I'm hearing the sfx only on
the left". Measured, the bed was dead centre — balance +0.7 dB, and the source files
were within 0.5 dB of centred. Nothing was wrong with the balance; the problem was that
nothing *moved*. The ear localises a static source once, and then the picture's motion
contradicts it.

`render_music_seg(..., pan=)` takes a position in [-1, +1], or a `[from, to]` pair to
travel between them over the segment. It is constant power, so the level holds across
the sweep instead of dipping through the middle — verified on a 6 s sweep: balance went
-8.8 dB to +11.4 dB while total level stayed within 1 dB.

Two things worth knowing:
- **Check the direction before committing.** Measure the ink centroid across the shot
  rather than trusting a glance. On the legion shot the framing does not translate at
  all — the column *faces* left, so the implied advance is right-to-left, and the pan
  carries what the framing does not.
- **Don't sweep hard on a wide shot.** ±0.85 reads as movement; ±1.0 draws attention to
  the technique. A tighter shot wants less, not more (±0.6).

## Library files are takes, not samples — split them before placing

Run `oneshot.py` on anything whose measured hit count is greater than one. This was
diagnosed twice from the same underlying fault, both times reported as bad sound design:

*"Weapons, Armor, Medieval Shield, Impact, Hit, Block, Sword Attack"* is exactly the
sword-on-shield clash a sword video wants. It is also a **3.23 s take containing four
separate blows**. Dropped whole on a one-frame beat it reads as a slam, and because the
energy anchor accumulates across all four hits it measured **695 ms**, so the whole
cluster landed early as well. It got rejected as "not good" — and the replacement, a
generic *Metal, Impact, Ring Out*, got correctly rejected as not being a shield at all.
The right sound had been in the palette the whole time, in the wrong shape.

```
oneshot.py pal/impact_11.wav --out pal --name shield     # -> 3 clashes, 0.23 s each
```

Each slice is cut from its own attack, ended where it decays 38 dB below its peak or at
the next hit, faded 30 ms, and peak-normalised to match `palette.py`. Front-loaded with
anchors of 0–15 ms, so they land on the frame.

**How to spot the problem** — count attacks per file (local rises above 30% of peak,
80 ms apart) and cross-check the anchor. A file with more than one hit *and* a large
anchor is a take being mistaken for a sample. In this palette the forge and armour
recordings have the same shape, so anything cast from them was landing as a cluster too.

**Also: my internal filenames are not sound names.** `impact_06` is a slot in a rotation,
not a description. When discussing a choice, quote the real Epidemic title — otherwise a
"clink" gets attributed to a recording that is nothing of the kind.

**Split what the TITLE says is several takes, not what an envelope test flags.** A
strict multi-attack test — two peaks each reaching 55% of the file's own peak, ≥150 ms
apart, with a real trough between them — still flags 65 of 240 files, and most of those
are one continuous gesture: a catapult creaking then releasing, a door latching then
thudding, a pour, a thunder roll. Splitting those destroys them. The reliable signal is
the Epidemic title: `x2`, `Variations`, `Impacts` (plural). On the castle video that
picked out 8 files and turned them into 54 front-loaded one-shots with 0–15 ms anchors.
The *loose* version of the test (any crossing of 30% of peak) flagged **108** files
including six sword-palette whooshes the previous job had already validated — a
slow-blooming whoosh has a long anchor and one attack, which is not the shape of a
four-blow take.

## Casting: the category is not the question, the OBJECT is

Getting the timing right and the tier right still produces a wrong mix if the sound
is of the wrong object. Every item below was reported by the channel owner watching a
render where the timing was already correct.

**Look at what the impact star is ON.** In the Bronze Age fight the first two strikes
put the comic starburst on the defender's *wooden shield*, with the blade against it —
he only takes X-eyes at 35.58, after a hook drags the shield away. Cast as flesh stabs
they were wrong twice over: wrong object, and they spent the flesh sound before the beat
that earns it. Blade-on-shield is wood plus metal; blade-in-body is flesh. Zoom into the
frame and check what the blade is touching before choosing.

**Read the whole shot, not the shot list.** A wide of an army on a field can be an
advance or an aftermath. One shot in the Iron Age section is corpses strewn over grass
with survivors standing among them; it got a marching bed, and marching over dead bodies
was reported as "not matching the scene". Aftermath wants wind, not feet.

**A diagram is not a strike, but its labels still name things.** A wound chart appearing
was cast as a metal impact by redraw tiering (it is a big redraw) and its two labels as
caption ticks. Right answer: the panel gets a soft element, and each label gets the sound
of the wound it names, 6 dB down from a real hit.

**An era card does not stop the scene.** The title-card guard silences everything within
0.45 s of a card boom, which is right for caption ticks and wrong for designed action. A
hand-timed beat sets `"solo_ok": true` (7th field in the sword video's `BEATS` tuples) to
survive the guard. The guard's log now names every silenced cue and flags the hand-timed
ones, because a bare count made a missing designed beat look identical to a healthy render.

**CORRECTION — the card guard was NOT what silenced the shield beat.** That was a guess made
before reading the cue sheet, and the sheet disagrees. The beat is the **Dacian falx** (not the
falcata) hooking over the Roman shield at **200.000**, and the nearest card is IRON AGE at
99.583 — a hundred seconds away, so the guard never touched it. What actually happened: the
redraw event at 200.000 lost its collision to a generic `movement` swish at **199.292**, 0.71 s
earlier, inside the swish tier's 0.85 s guard. A nothing-cue deleted a named beat. The general
lesson stands and is worth more than the specific one: **a generic cue can silently outrank a
designed moment purely by arriving first**, so any beat the script names belongs in the
hand-timed sheet, where tier priority protects it — not left to the detector to rediscover.

**A portrait is not an event — mute it, don't re-tier it.** A museum photograph of
Tutankhamun's mask sliding in with its caption, and a sepia portrait plate, both drew sword
hits. To the redraw detector they are indistinguishable from a blade entering a shield: a
large mid-band redraw. But nothing is being struck, so there is no quieter or softer sound
that is *right* — the beat should be silent. `place.py` takes `mute_windows` in the cue
sheet ( `[start, end, "why"]`, seconds) which drop **generic** cues only; hand-timed beats
pass through, so a designed beat inside a window still sounds. Sweep the figure shots off
contact sheets and window them all at once — these arrive one screenshot at a time
otherwise, and each round costs a render.

**Room tone must not contain a second voice.** `place.py` lays one `amb` bed under every music
section by rotation, and two of the eight ambience recordings are crowds with people in them —
`amb_06` *"Crowds, Battle, Medieval, Savages Battle Ambience, Voices, Yells"* and `amb_07`
*"...Village Battle Ambience, Voices, Yells"*. Rotation put one of them under **five** of the
seventeen sections; the Renaissance one was reported as "unnecessary vocals in the background".
A bed never ducks (beds mix onto the SFX bus, only the music bus is sidechained), so a crowd
bed is a second voice competing with the narrator for 45 seconds at a time.

Keep them in the palette as a `crowd` category, which nothing auto-assigns, so a hand-written
bed can still call one where a crowd is actually on screen. And **check the titles of every
file in the auto-assigned pool** — the internal names say `amb_06`, which tells you nothing;
the Epidemic titles say "Voices, Yells", which tells you everything.

**A long tonal tail is a bed, not a hit — treat it like one.** The Syracusia
being renamed *Alexandria* got a ship's bell, hero tier, -8 dB. It was reported
as "annoying", and the cue sheet says why twice over: the file is **7.00 s**
long, and the thing it was placed on is an `element` of strength 0.011 — a
caption tick, which the detector had classified correctly before a hand-written
beat overrode it with a hero cue.

Two rules fall out, and they are cheap to check before rendering:

- **Check the length of anything tonal.** A bell, chime, gong or singing bowl
  rings for seconds at a definite pitch, so under continuous narration it is a
  second sustained voice in the same band — the same failure as a crowd
  ambience, arriving as a "hit" instead of a bed. Non-tonal hits decay into
  noise and get out of the way; tonal ones do not. Either cast something short
  and struck, or accept it is a bed and level it like one (-32 dBFS or below).
- **A caption is a caption even when the words are important.** "Renamed
  ALEXANDRIA" is a story beat in the script and a small text element on screen.
  The tier belongs to what is drawn, not to what the sentence means. When a
  hand-written beat lands on an event the detector called an `element`, that is
  a signal to check the casting, not to overrule it.

`grep` the sheet for hand beats sitting on small elements before rendering:

```python
ev = {round(e["t"], 2): e for e in json.load(open("redraw.json"))["events"]}
for s in cue["sfx_cues"]:
    e = ev.get(round(s["at"], 2))
    if e and e["kind"] == "element" and s["tier"].startswith("hero"):
        print(f'{s["at"]:8.2f}  hero cue on a caption tick: {s["kind"]}')
```

**Levels for sustained beds, measured against the voice.** The VO sits near -18 dBFS rms
and the music bed lands near -28. A featured texture like marching at -31 fights the
narration and was reported as overlapping it; **-37 dBFS** sits under the music and reads
as present without competing. Ambience beds belong near -42.

**Vocals: sparingly, and only where a person would make one.** Non-verbal vocalisation
(an effort grunt on a heavy swing, a short cry on the killing blow, a crowd's yell on a
charge) is part of this channel's sound. It is also the fastest thing to overdo — one per
fight beat is a cartoon. Reserve it for the blow that lands and the ranks that shout.

What that came to on the sword video — three vocals in thirteen minutes, and the search
terms and levels that got there:

| beat | recording | placement |
|---|---|---|
| the swing that costs effort | *Voices, Efforts, Male, Attack, Grunt, Breath, Short, Multiple 02* | on the swing, **-11 dB** |
| the killing blow | *Voices, Male, Sudden Death, Combat, Pain 04* | **+80 ms** after the blade, **-7 dB** |
| the ranks in formation | *Crowds, Battle, Medium, Yell, Short* | bed, **-32 dBFS** rms |

Three things that are easy to get wrong here:

- **The grunt take was three grunts.** 3.56 s, measured at three hits — the "takes, not
  samples" rule again, and dropped whole it plays all three down one swing. Split it
  (`oneshot.py`) into 0.16–0.26 s one-shots with 4–17 ms anchors.
- **The cry goes after the blade, not on it.** A man cries out *because* he was hit; on the
  same frame it just thickens the stab. 80 ms reads as reaction.
- **A crowd yell is the one bed that can climb over the narration.** Beds mix onto the SFX
  bus, and *only the music bus is sidechained* — a bed never ducks. A yell is mid-band,
  exactly where the voice is, so it is the most dangerous thing in the sheet. Keep it a few
  dB under the -28 music bed (-32) and pull the shot's ambience back to make room rather
  than raising the yell.
- **Cast the crowd for what the shot is doing.** Ranks holding formation want *Yell* or
  *Shout*; the *Battle Cry, Screams, Charge* recordings are men running, and putting those
  under a standing formation is the same error as marching over corpses.

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

**A coarse sheet finds the SCENE. Only a ~1 s sheet finds the FRAME.** Sampling at 6 s
was enough to locate every one of the warships video's beats and wrong about *when*
three of them happen, by 1.1 to 7.1 s:

| beat | read at 6 s | actually | how far out |
|---|---|---|---|
| Bushnell's drill will not bite | 359.0 | **351.9** (the bit turns red, the pod rocks) | 7.1 s |
| K22 hits K14 | 563.0 | **561.0** (first frame with an impact star) | 2.0 s |
| Fearless cuts K17 open | 575.0 | **573.9** | 1.1 s |

The drill one is the lesson: 357.8 is a *different* beat — the pilot's face goes red,
which is the man failing, not the auger — so the 6 s sheet had merged two beats into
one and named it after the wrong thing. Work in two passes: coarse to find the scene,
then re-sample that scene at ~0.7-1.3 s and read which panel first shows the change.
Snapping to a detected event does not rescue a time that is seconds out; it only
polishes one that is already within a frame or two.

**Detect the era CARD, not the banner.** This channel runs a persistent era name in a
top banner *and* a full-screen title card at each change, and the two do not coincide.
Diffing the banner strip finds a change but cannot say which one it found: it fires
either when the old text leaves or when the new text arrives, and on the warships video
those are as much as 1.8 s apart (the card was fully on screen at 167.7 while the banner
did not swap until 169.5). Detect the card itself — on this channel a near-white frame
carrying a red progress bar — and take the onset of the run:

```python
red   = ((r > 150) & (g < 110) & (b < 110)).mean()      # the progress bar
white = ((r > 235) & (g > 235) & (b > 235)).mean()      # the card ground
score = red * 100 if white > 0.55 else 0.0             # runs > 0.9, >= 0.4 s
```
`examples/weirdest-warships/cards.py` is that scan; `banner.py` beside it is the
version that got it wrong, kept on purpose. Expect a couple of false positives on
white-background shots that happen to contain red (a ship's red hull, a flag) —
check them on a contact sheet rather than widening the threshold.

**The white presenter shot is a free transition marker.** Every era card on this
channel is preceded by a ~2 s shot of the narrator character on plain white. If the
card scan misses one, the presenter shot is a second way in.

**But the transition device is per-video, so find it before scanning for it.** The
castle video has no white-and-red card at all: its sections are marked by a **grid
of all eight topics** that scrolls to the next one, plus a persistent banner naming
the current topic. `cards.py` returns nothing but false positives on grey stone, and
the grey-card variant of it finds castle walls. What works there is the **banner-strip
fingerprint** — downsample the top 12% of the frame, diff consecutive frames, and the
8 section changes fall out — cross-checked against the grid on a contact sheet.
`banner.py`'s documented failure (firing on the old text leaving *or* the new text
arriving) is real but harmless when the grid card gives you the true boundary.
Full-screen **red** cards can still exist and still be the biggest beats in the
section: two on that video, found with `red = ((r>110)&(r-g>45)&(r-b>45)).mean() > 0.55`.
Spend two minutes reading a coarse contact sheet for what the transition actually
looks like before running any detector.

## The default weight layer names an object, so set it per video

`place.py` puts a layer under every generic strike 35 ms late, because metal alone is
thin. That layer defaulted to `["body"]` — four flesh punches — which is right for a
video about men hitting each other and wrong for one about stone, timber and iron.
It is also only four files: on a 12-minute castle video with 125 generic strikes they
played **31 times each**, three times over the reuse rule, in a mix whose next-busiest
file was ×9. Nothing warned, because the reuse check people run looks at the primary
cues and these are layers.

Set `"default_weight_cats"` in the cue sheet to say what a strike in *this* video
weighs; `["body"]` stays the fallback. On the castle video it was a 24-file pool of
masonry, rock, ram timber and the flesh punches (men do still get hit), which took the
busiest weight file to ×5. **Count the layers, not just the events**, when checking
reuse:

```python
collections.Counter(os.path.basename(s["asset"]) for s in cues["sfx_cues"])
```

## Measure a track's drive; never read its title

"Floaty is a casting error" is only actionable if you can tell before rendering. You
can: score onset density, pulse regularity (the autocorrelation peak of the onset
envelope) and percussive fraction over ~45 s from the middle of each candidate.
`examples/castle-defences/mus_measure.py` is that scan, and the `lqmp3Url` in every
search result means candidates cost one small download each rather than a WAV pull.

On a castle video, *Arrival at Caelmere Keep* and *The King's Return* are the obvious
picks by name. Measured, they score **2.25** and **2.10** against 3.4–3.8 for what
shipped — they are exactly the ambient wash that gets reported as "float music, bit
annoying". 116 candidates measured, 19 cast, no floaty note came back.

## Test an unnamed bed for voices; do not trust the filename

`amb_05` says nothing about what is in `amb_05`, and the sword palette's Epidemic
titles are not recoverable — that job stored CDN ULIDs, which are a different id space
from what `SearchSoundEffects` returns, so there is nothing to look them up by. The one
thing that must not be in a bed is a second voice. So measure it: `pyin` over the
harmonic component, counting frames carrying a confident pitch in the human F0 range
(85–350 Hz), calibrated against the two files known to be "Voices, Yells".

| | mean pitch confidence |
|---|---|
| the two known crowd recordings | **0.14, 0.25** |
| every other bed | **≤ 0.04** |
| `amb_05` | **0.16** — dropped |

Band-energy and modulation-depth tests do **not** work: water and wind land in
300–3400 Hz and modulate at 2–8 Hz just as hard as people do, so both flagged lake,
river and wind files alongside the real crowds. Pitch confidence separates them
cleanly. Also resolve the titles of anything you fetched yourself — replaying the
searches that chose the files maps every internal name back to its real title
(`examples/castle-defences/titles.py`), and the cue sheet should quote those.

## A file that SUSTAINS is a bed, whatever its pitch — and a bed is cut to the shot

The tonal-tail rule ("a bell rings for seconds, so it is a bed, not a hit") is a
special case. The general one is about the **envelope**, not the pitch: a file whose
level does not decay after its attack keeps sounding after the beat, and that reads as
a sound that will not stop. Measure it — median level over the second half of the file,
relative to its peak:

| | length | sustain | verdict |
|---|---|---|---|
| *Rocks, Crash & Debris, Heavy, Big Hit, Stone Debris* | 6.19 s | **−38.4 dB** | fine as a hit — long, but it decays |
| *Rocks, Impact, Single Rock, Ground, Heavy Thud* | 4.62 s | **−36.5 dB** | fine |
| *Fire, Ignite, Fast Flame Up, Large Flame* | 1.27 s | **−21.8 dB** | fine |
| *Weapons, Siege, Catapult, Fire, Flame Ball* | 5.58 s | **−20.7 dB** | a bed |
| *Fire, Torch, Circular Swooshes, Some Crackling* | 6.17 s | **−22.9 dB** | a bed |
| *Fire, Burst, Cinematic, Large Roaring Flame* | 3.03 s | **−9.5 dB** | a bed |

So **length alone does not condemn a hit** — a 7 s debris fall is right on a collapse
and a 3 s roaring flame is wrong on anything. `examples/castle-defences/preflight.py`
runs this over a finished sheet and names every hero cue cast from a sustaining file;
run it before rendering. On the castle video four of the six candidates in `firewh` and
one of six in `treb` were beds in a hit's clothes, and the one sustaining catapult was
the *flame ball* recording — cast onto a trebuchet with no flame anywhere near it.

**Then cut every bed to the shot, not to the section.** This was the note that came
back: *"unnecessary fire sfx, it's keep continuing and not stopping where necessary."*
The fire bed under Rochester's mine ran the whole music section — **31.9 s at −37 dBFS**,
a *featured texture* level — while `fire.py` measures drawn flame on screen for
**2.92 s**. So torch crackle played for 13.6 s before anything was alight and 15.4 s
after the corner had already fallen, over a diagram of a square tower. Retimed to
399.3–404.2 at −40 dBFS with 0.9 s fades.

Weather, water and room tone are genuinely continuous and belong to the section. **Fire,
machinery, crowds and anything else that is an *event with a duration* belong to the
shot**, and their window is measurable: score the thing on screen (`fire.py` for flame
area, the same trick as the warships job) and set the bed to what it finds, plus a
beat either side. A bed at section length is the default and the default is wrong for
anything that starts and stops on camera.

**Audit every bed the same way, not just the one that got reported.** Asked to check the
whole mix after the fire note, the same measurement found worse:
`Water, Turbulent, River, Fast Flow` running for **57.7 s** under the Château Gaillard
section with water on screen **15%** of that — a map, a plan on white, a castle under
lightning, a target diagram, arrows on white. And a second fast-flowing river under a
drawbridge's **standing** ditch, where the object is wrong even though the water is
genuinely there. `examples/castle-defences/onscreen.py` scores water (a flat blue region
in the *lower* frame — sky is the same hue) and figures per frame; run it against the
bed list and anything under ~45% presence is either mis-timed or mis-cast.

Two cautions on that audit. **Room tone is exempt**: a gentle lake lap under a section
whose whole premise is a castle sitting in a lake is location, not an event, and 39%
presence is fine for it. And **the figure proxy is unreliable** — ink density flags
7-second crowd beds on light-grey wall shots at 29% when the frames plainly show men in
a breach. Check those on a contact sheet before cutting them; do not cut a bed on a
proxy you have not calibrated.

## A cue may not outlast its shot: `max_len`

The general form of the same note, for cues rather than beds. `examples/castle-defences/overrun.py`
compares each cue's *audible* tail (to −30 dB below its own peak, not its full length)
against the time to the next scene cut. On this video 17 cues were still sounding more
than 1.5 s after the picture had moved on — a 6.9 s door creak that spanned two cuts,
a 4.5 s thunder roll over a 1.3 s lightning shot, a 5.8 s creak over a 3.2 s climb.

Ten of the seventeen were **right**, and that is the point: a section-card boom is
*supposed* to ring across its transition, and a collapse's debris is supposed to ring
out over the next shot. So this is never a global cap. A cue sheet beat now takes an
optional `max_len` (an 8th field in the `BEATS` tuple), `place.py` carries it through,
and `assemble.py` trims the cue there with a short fade. Seven caps fixed this video;
the ten that remain are all cues that earn their tail.

Run `overrun.py` and `preflight.py` on every finished sheet before rendering. Between
them they catch both halves of "unnecessary sfx that keeps continuing": a file that
never decays, and a file that decays fine but is longer than the shot it is in.

And a short bed needs a short fade: `BEDS` entries carry their own `fade` now, because
the 2.5 s default cannot fit inside a 5 s bed.

## Cold air is an object too

Every obvious search for a wind bed returns "Polar" and "Heavy Storm, Cold" — that is
what the library has most of. Running one under a Crusader castle in Syria, a hilltop
in Languedoc and an English keep in November is the same class of error as marching
over corpses: the bed contradicts the picture for a minute at a time and never ducks.
Search `vegetation grass wheat in wind` and `wind designed constant` for neutral and
dry air, and keep the polar ones for the shots that actually have snow in them.

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

## The bed number was measuring the wrong thing — read this before setting a level

The −13 dB bed target below is **correct for StickTory's mixes and wrong for ours**,
and the reason is not taste. The two numbers are not the same quantity:

- **Theirs** was measured *in the gaps between VO lines* — the bed alone, with the
  duck released. That is the only way to get it from a published mix.
- **Ours** was set as the *integrated LUFS of the ducked music bus against the
  integrated LUFS of the VO* — an average that includes every ducked moment.

Calibrating our average to their gap measurement is not like-for-like, and the error
runs in the direction of "too loud". Worse, the gap method cannot be applied to our
own mixes at all: measured on the warships VO at four different silence floors,
**there are zero gaps of 0.6 s or more in 11:58**, and speech occupies 90–93% of the
runtime. There is nothing to measure the bed alone in.

On that mix the two figures differ by **5.9 dB**: the calibration was told −20 dB
and what the bed actually does under speech is **−25.9 dB**. So a `--bed-target-db`
value is roughly 6 dB hotter than what a viewer hears under the narration.

**What to do:**
- Treat `--bed-target-db` as an internal control, not as a StickTory comparison.
  **−20 is the chosen value**, and it was arrived at by ear over three rounds:
  −13 (their gap figure) was reported loud, and −20 is also exactly Sapro's original
  standing instruction to human sound designers, which was 10%.
- Report both numbers when handing over — the target you set *and* the measured
  under-speech figure — because only the second one describes what is heard.
- `--sfx-db -6` alongside it, which keeps hits **+3.5 dB above the bed**. Hits must
  stay above the bed at any bed level; that part of the reference holds.

```python
# what the bed is really doing, on any mix, gaps or no gaps
sp = vo_env_db > -45
under_speech = np.median(music_env_db[sp]) - np.median(vo_env_db[sp])
```

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

**But `measure_ref.py`'s bed ratio does not work on our OWN mixes — only on a
published reference with gaps.** It reads the p10 of the loudness envelope as
"music alone", which is true of a mix that has silences between VO lines and false
of ours: the ExplainTory VO is continuous, so p10 is just the quietest speech.
On the warships mix it reported the bed **-2.7 dB under programme (73%)** for a
music bus that `assemble.py` had measured and calibrated to exactly **-13.0 dB
under the VO**. Reading the tool literally would say the mix is 10 dB too hot and
send you to pull a correct bed down into inaudibility.

Verify our own renders two other ways, both of which agree:
- the calibration line `assemble.py` prints — `music -26.9 LUFS, vo -14.5 LUFS
  (-12.4 dB) -> target -13 dB needs -0.6 dB` — this is the number that matters;
- `volumedetect` on the stems: on the warships mix music mean **-29.1 dB**, VO mean
  **-17.2 dB**, i.e. -11.9 dB, and SFX mean **-27.8 dB**, so the hits sit **1.3 dB
  above the bed** as they should.

Use `measure_ref.py` for what it was built for: measuring somebody else's finished
video, where the gaps are real. Its programme LUFS, LRA and true-peak readings are
fine on anything.

**`sync_check.py` assumes 24 fps.** These videos are 30. Pass `--fps 30` or every
"within one frame" figure is quoted against a frame 8.4 ms too long.

**`oneshot.py` overwrites silently when `--name` repeats.** Splitting three different
takes with the same prefix leaves only the last one's slices on disk, and nothing
says so. Give each source its own name.
