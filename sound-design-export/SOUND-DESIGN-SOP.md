# SOUND-DESIGN-SOP.md

The ExplainTory sound-design pipeline, as it actually runs. Every number here was
read out of the scripts in `scripts/`, not recalled — where a value is a script
default, the flag and the file are named so you can check it.

Each setting is tagged:

- **[GENERAL]** — would apply to any channel. Loudness targets, export format,
  how cues are timed against the picture, how a bed is levelled from a measurement.
- **[TASTE]** — chosen for ExplainTory. Music style, effect density, section
  length, tier gains, the bed level. Anything I was unsure about is tagged
  **[TASTE]**, because a wrong GENERAL tag would spread a personal preference
  into somebody else's channel.

A full one-line-per-setting table is in **SETTINGS.md**.

---

## 1. Inputs

| input | format | required | notes |
|---|---|---|---|
| Video | `.mp4`, H.264 | yes | 1920×1080. Frame rate is read from the file — **do not assume 24 or 30**; `sync_check.py --fps` must be told the real one or every "within one frame" figure is wrong. |
| Voiceover | `.wav` 48 kHz preferred, `.mp3` accepted | yes | Already mastered by the separate `explaintory-vo-master` pipeline. Must be a **separate stem**, not a mix-down — the ducking key and the bed calibration are both measured against it. |
| Script | plain text or a doc link | no | Used for casting language and for naming beats. If missing, transcribe locally (see §2). |
| Timings | none supplied by hand | — | All timings are **measured from the video**, never taken from a script or an animator note. |
| Cue list | `cues_beats.json` | produced, not supplied | Written by a per-job `build_cues.py`. See §4. |

**If only the video arrives.** An ExplainTory cut carries the mastered VO and
nothing else, and it measures like one: **−14.5 LUFS, LRA 1.6–1.7, zero silences
≥ 0.6 s** [TASTE — those are this channel's VO numbers]. Extract it and use it as
the stem:

```bash
ffmpeg -i in.mp4 -vn -ac 1 -ar 48000 vo.wav
ffmpeg -i vo.wav -af ebur128 -f null -     # confirm ≈ −14.5 LUFS, LRA ≈ 1.6
```

If those numbers come back different, the supplied cut already has music on it
and you need the separate VO stem.

**If the script is missing**, transcribe rather than ask:
`pip install faster-whisper`, model `base.en`, ~2 min on CPU for 12 minutes.
Proper nouns come out mangled (Krak des Chevaliers → "Crackday Chevelier";
portcullis → "Port Colus") but every story beat and its timing is there, which is
all the casting needs. [GENERAL]

---

## 2. Reading the picture

Nothing is placed that has not been looked at. [GENERAL]

**2.1 `visual_redraw.py video.mp4 -o redraw.json`** — the beat detector.
Explainer animation is drawn on held frames, so the per-frame difference is
almost binary, and its *size* classifies the beat for free: [GENERAL]

| frame difference | meaning | flag |
|---|---|---|
| ≥ 0.15 | whole frame redrawn → shot change | `--cut 0.15` |
| 0.02–0.15 | a figure took a new pose → action beat | `--action 0.02` |
| 0.004–0.02 | a small element appeared → caption or label | `--floor 0.004` |

Do **not** use optical flow (`visual_events.py`) on animation. It ranked a blade
entering a chest below a camera pan. `visual_events.py` is kept only for
live-action footage. [GENERAL]

**2.2 Contact sheets.** Sample one frame 0.45 s after every detected cut, tile
4×4 at 420 px, and read them. Then re-sample any payoff beat at 0.5–1.8 s.
A 6 s sheet finds the *scene*; only a ~1 s sheet finds the *frame* — three beats
were 1.1–7.1 s wrong when read at 6 s spacing. [GENERAL]
Scripts: `config/castle-defences/shots.py`, `sheets4.py`, `fine.py`.

**2.3 Section boundaries.** The transition device is per-channel, so find it
before scanning for it. [GENERAL] On ExplainTory it has been two different
things across three videos [TASTE]:

- a full-screen title card (white ground + red progress bar) — `cards.py`
- a **scrolling grid** of all topics plus a persistent top banner — detect via
  the banner-strip fingerprint diff in `scan.py`

`banner.py` is kept as the negative result: it fires either when the old text
leaves or when the new arrives, up to 1.8 s apart.

**2.4 Event detectors for beds.** Score the thing on screen so a bed can be cut
to its shot rather than its section: `fire.py` (drawn flame area), `onscreen.py`
(water as flat blue in the *lower* frame — sky is the same hue — and figures by
ink density). [GENERAL]

---

## 3. Music

**One track per section, never one track for the video.** [TASTE]

### 3.1 How many sections

`analyze.py` uses `SECTION_SECONDS = 47.0` and clips the count to 1–24. [TASTE]
Measured from two published reference mixes: a cue change every **47–48 s**.
Delivered jobs ran 42.2 s (warships) and 38.9 s (castle). Section boundaries are
placed on **story turns**, snapped to the transition card, not on a fixed grid.

### 3.2 How a track is chosen

**Search Epidemic by term, then reject by measurement.** [GENERAL method,
[TASTE] targets]

Search terms that have worked, one per mood the story needs:

```
dark cinematic tension building strings percussion medieval
medieval battle drums war marching relentless
driving cinematic percussion taiko action tension
playful sneaky mischief pizzicato comedic tension
somber slow strings mournful cinematic
suspense pulse ostinato strings ticking urgent
epic grand orchestral cinematic powerful
heroic triumphant orchestral brass rising
```

Query filters pushed into the API, not applied afterwards:

| filter | value | tag |
|---|---|---|
| `vocals` | `false` | [GENERAL] |
| `duration.min` | ≥ the longest section (90 000 ms typical) | [GENERAL] |
| `bpm` | around the cue's hint when one is set | [TASTE] |

**`vocals: false` is not airtight.** Measured live, **12 of 60** results under
that filter still carried a `vocal presence` tag — the filter means "not a
lead-vocal song", not "no human voice", so choir and chant pads pass straight
through. Trust the tags, not the filter. A vocal tag is a **hard reject**, not a
score penalty: scoring docked it 6 points and the best-fitting vocal track still
beat a plainer instrumental. [GENERAL]

**Then measure rhythmic drive.** [GENERAL method, [TASTE] threshold]
`config/castle-defences/mus_measure.py` loads 45 s from 20 s in and scores:

```
drive = min(onsets_per_sec / 2.2, 1.4)
      + 1.6 × pulse            (autocorrelation peak of the onset envelope)
      + 2.2 × percussive_frac  (HPSS percussive / total)
```

This channel's music is **rhythmic with a driving pulse, never ambient wash**
[TASTE]. Shipped tracks scored **3.3–3.8**. Two obvious-by-title medieval picks —
*Arrival at Caelmere Keep* (2.25) and *The King's Return* (2.10) — are ambient
wash by that measure and were rejected on it. "Floaty" is a casting error, not a
level problem: pulling a drifting track down just annoys more quietly.

Candidates cost one small download each — use `lqmp3Url` from the search result
rather than pulling WAVs to audition. [GENERAL]

**Do not score each era or region with its own instruments.** The palette stays
one family — cinematic/historical tension throughout — and cues change within it.
Swapping to taiko for Japan and oud for Persia reads as a compilation, not a
score. [TASTE]

### 3.3 Trimming and looping

`render_music_seg()` in `assemble.py`: [GENERAL]

- **Start offset**: `energy_onset()` finds where the track first reaches −12 dB
  below its own peak (searching the first 30 s) and starts 0.25 s before that.
  Library tracks open on long ambient swells; starting at sample 0 made five of
  seventeen cues inaudible for 8–17 s and the section change read as "the music
  never changed".
- **Trim**: `atrim=skip : skip+dur` — the section is cut from the track, not
  time-stretched.
- **Loop**: only if the asset is shorter than the section (`-stream_loop -1`).
  In practice never — tracks are filtered to ≥ 90 s and the longest section is
  ~58 s.
- **Fades**: `fade_in 0.4 s` on the first section, `1.2 s` on every other;
  `fade_out 1.2 s` on all. [TASTE]
- Epidemic's `EditRecording` / `PollEditRecordingJob` can fit a track to a target
  length keeping musical structure. Available, not used on these jobs.

---

## 4. Sound effects

### 4.1 What gets an effect

Two sources, merged: [GENERAL]

1. **Hand-timed beats** — every moment the script or the picture names. Written
   by hand into a per-job `build_cues.py` as
   `(time, label, category, tier, gain_db, stack, snap, max_len?)`.
   Castle job: **193** of these. A hand beat is **never dropped** by the placer.
2. **Generic events** from `redraw.json`, thinned and de-collided by `place.py`.

`place.py` merges them, resolves collisions **by tier priority, never by
strength** (a caption tick must not elbow a sword strike), and drops the weakest
fraction of in-shot action events (`--drop-weakest`, default 0.35).

### 4.2 Timing

**Place the sound's perceived moment on the beat, not its first sample.** [GENERAL]

1. Trim leading silence **once**, at palette prep (`palette.py`). Never also run
   a per-render transient search — doing both compensates twice and threw
   slow-blooming whooshes 300 ms early.
2. Store a **per-file anchor**: where the first 15 % of the file's energy has
   accumulated. Per file, not per category.
3. **Zero the anchor** for anything front-loaded (≥ 40 % of peak inside the first
   30 ms). If it starts with a bang, the bang *is* the moment.
4. Subtract a one-frame deadband from the rest.
5. Cast beats that must hit a mark with **front-loaded files**. A swell cannot
   land on a frame.

Metrics that were tried and are worse — do not reintroduce: time-to-60 %-of-peak
(locks onto the loudest *late* hit: 749 ms vs 127 ms across five forge files),
steepest envelope rise (finds later swells).

A hand beat is written at the time read off the sheet, then **snapped to the
nearest picture change within 1.2 s**.

### 4.3 Tiers — level and minimum spacing

`TIERS` in `place.py`. Gains are relative to the voice. [TASTE]

| tier | gain | guard | used for |
|---|---|---|---|
| `hero_boom` | −5 dB | 2.20 s | section card, stated turning point |
| `hero_hit` | −7 dB | 1.30 s | hand-timed story beat |
| `impact` | −8 dB | 1.10 s | strong on-screen action |
| `whoosh` | −12 dB | 1.00 s | shot change |
| `swish` | −15 dB | 0.85 s | element moves |
| `pop` | −19 dB | 0.80 s | caption, small element |

**SFX sit ABOVE the music bed, not under it.** [TASTE] They are the foreground;
the bed gets out of the way. A render with the bus at −23.7 dB under a −13 dB bed
read as having no SFX at all.

### 4.4 Layers

- **Anticipation**: a `swish` at **t − 0.13 s**, gain − 7 dB, on `impact` and
  `hero_hit` only. One sound is a sample; two is a designed hit. Suppressed in
  front of a voice cue — a grunt displaces no air. [TASTE]
- **Weight**: stacked categories at **t + 0.035 s** (+0.05 s each extra), gain
  − 5 dB. The default pool is per-video via `default_weight_cats` in the cue
  sheet [GENERAL that it is configurable; [TASTE] what is in it]. Four flesh
  punches under every strike is right for men fighting and wrong for stone,
  timber and iron — and with only four files they played **31 times each**.

### 4.5 Density and variety

Countable before anyone listens: [TASTE]

| metric | target | castle job |
|---|---|---|
| events per second | ~ one per **2.2 s** | one per 1.99 s |
| distinct files | no file more than **×10** in 13 min | 206 files, busiest ×9 |
| same file twice | never inside **30 s** | 20 of 771 cues, all quiet layers |

A render drawing 474 cues from **seven** files (one tick played 240 times) was
described as "placed by a cheap guy". Getting there needs a real palette of ~80+
sounds, not a keyword search per cue.

### 4.6 Where the sounds come from

**Epidemic Sound only.** No generated/synthesised audio anywhere in the
pipeline. [GENERAL for this pipeline]

- Reach the catalogue with `scripts/epidemic_api.py` (plain HTTPS bearer to
  Epidemic's MCP endpoint). Prefer it over the claude.ai MCP connector, which
  dropped in and out repeatedly and took search and download with it.
- `query` / `filter` / `options` are **objects, not JSON strings**. Stringifying
  them returns `GRAPHQL_VALIDATION_FAILED` on `['variable','query']` with no hint
  that the type is the problem, which sends you to regenerate a perfectly good key.
- Cap `duration` at 3–4 s on SFX searches so you get hits, not beds.
- Downloads come back as signed URLs on `audiocdn.epidemicsound.com`; that host
  must be reachable from wherever the scripts run.

**Palette preparation** (`palette.py`) — do this once per job, never per render:
[GENERAL]

- peak-normalise hits to **−3.0 dBFS** (measured spread across 81 library files
  was **15 dB**, +12.3 to −2.8; without this the tier table means nothing)
- trim leading silence
- measure and store per-file anchor, front-load ratio, and rms
- beds (`--bed-prefix`) are left un-normalised and un-trimmed; only their rms is
  measured, so they can be levelled to a target rather than trimmed by a constant

**Library files are takes, not samples.** Split anything whose Epidemic title
says it holds several — `x2`, `Variations`, `Impacts` (plural) — with
`oneshot.py`. A 3.23 s recording of four sword-on-shield blows dropped whole on a
one-frame beat reads as a slam, and its energy anchor lands 695 ms in so the
whole cluster is early. [GENERAL]

Do **not** split on an envelope test alone: a strict two-peak test still flags 65
of 240 files, most of them one continuous gesture (a catapult creaking then
releasing, a door latching then thudding). The loose version flagged 108
including six whooshes already validated. Give each source its own `--name` —
`oneshot.py` overwrites silently when a prefix repeats. [GENERAL]

### 4.7 Casting — the category is not the question, the OBJECT is

Every rule below came from a real wrong call. [GENERAL principle, examples [TASTE]]

- **Look at what the impact star is on.** A blade against a wooden shield is wood
  plus metal; a blade in a body is flesh. Cast as flesh stabs they were wrong
  twice: wrong object, and they spent the flesh sound before the beat that earns it.
- **Read the whole shot, not the shot list.** A wide of an army on a field can be
  an advance or an aftermath. Marching over corpses was reported as not matching.
- **A portrait is not an event — mute it, don't re-tier it.** A museum photograph
  sliding in is indistinguishable from a blade entering a shield to the redraw
  detector: a large mid-band redraw. Nothing is being struck, so no quieter sound
  is right. `mute_windows` in the cue sheet drops **generic** cues only; hand
  beats pass through.
- **A generic cue can silently outrank a designed moment by arriving first.** A
  nothing-swish 0.71 s earlier deleted a named beat inside the swish guard. Any
  beat the script names belongs in the hand-timed sheet.
- **Room tone must not contain a second voice.** A bed never ducks. Two of eight
  library ambiences were crowds with people in them and rotation put one under
  five of seventeen sections.
- **Vocals sparingly.** Non-verbal only — an effort grunt on a heavy swing, a
  short cry on the killing blow, a crowd's yell on a charge. Three in thirteen
  minutes. The cry goes **+80 ms after** the blade, not on it: a man cries out
  *because* he was hit. [TASTE]

### 4.8 A sound that will not stop

Two tests, both in `config/castle-defences/`. Run both before rendering. [GENERAL]

**`preflight.py` — does the file decay?** Median level over the second half
relative to peak. Length alone does not condemn a hit:

| | length | sustain | verdict |
|---|---|---|---|
| Stone debris | 6.19 s | −38.4 dB | fine — long, but it decays |
| Fire ignite | 1.27 s | −21.8 dB | fine |
| Roaring flame | 3.03 s | −9.5 dB | a bed |
| Torch crackle | 6.17 s | −22.9 dB | a bed |

**`overrun.py` — is it longer than its shot?** Audible tail (to −30 dB below its
own peak) vs time to the next cut. On the castle job 17 cues overran; **10 were
right**, because a card boom is *supposed* to ring across its transition and
debris should ring out. So the cap is **per cue, never global**: a beat takes an
optional `max_len`, `place.py` carries it through, `assemble.py` trims there with
a fade of `min(0.12 s, max_len/4)`.

---

## 5. Ambience beds

Hand-assigned, never rotated. A bed does **not** duck — only the music bus is
sidechained — so a wrong bed runs under the narration for a minute at a time.
Render with `place.py --no-beds` and write them all by hand. [GENERAL]

Levels, measured against a VO near −18 dBFS rms: [TASTE]

| kind | rms target |
|---|---|
| ambience / room tone | **−42 to −43 dBFS** |
| featured texture (fire, marching) | **−37 dBFS** |
| crowd / anything mid-band with people in it | **−38 dBFS** |

A bed at −42 dBFS is never consciously heard and its absence is. A featured
texture at −31 fights the narration.

**Weather, water and room tone belong to the section. Fire, machinery, crowds and
anything that is an event with a duration belong to the SHOT** — and the window
is measurable. [GENERAL] A fire bed ran **31.9 s at −37 dBFS** over **2.92 s** of
drawn flame; a turbulent river ran **57.7 s** with water on screen **15 %** of it.
Audit every bed with `onscreen.py`; under ~45 % presence it is mis-timed or
mis-cast.

Two cautions on that audit: room tone is exempt (a gentle lake lap under a
section about a castle in a lake is *location*, 39 % is fine), and the figure
detector is **not calibrated** — it reports 29 % on a crowd bed whose frames
plainly show men in a breach. Check those on a sheet; never cut a bed on an
uncalibrated proxy. [GENERAL]

A short bed needs a short fade: beds carry their own `fade` because the 2.5 s
default does not fit inside a 5 s bed. [GENERAL]

---

## 6. An animation-only opening before the voice

**Handled, but only weakly, and it has never been exercised on a real job — treat
this section as untested.** [GENERAL]

What the code does today:

- `analyze.py` builds a voice map with
  `silencedetect=noise=-30dB:d=0.5` [TASTE — thresholds] and takes the complement
  as voiced regions.
- If there is a gap before the first voiced region, it places one cue —
  **"intro riser"** at `first_voice − 1.2 s`, gain **−7 dB**, search term
  *"cinematic riser uplifter build tension"*.
- Each music section is marked `under_voiceover: true/false` by whether it
  overlaps a voiced region.

Three honest limitations:

1. **`under_voiceover` is metadata only.** `assemble.py` never reads it. The duck
   is applied to the **whole music bus** at once (`duck()` at line 623), so a
   pre-voice opening is ducked by the same sidechain as everything else — which
   does nothing while the voice is silent, so the music simply plays at full bed
   level. That is usually what you want, but it is not a decision the pipeline
   made.
2. **The bed calibration ignores it.** `calibrate_bed()` compares integrated
   music loudness against integrated VO loudness across the whole file. A long
   silent opening drags the VO's integrated figure down and makes the bed trim
   slightly too quiet. Not yet measured, because all three ExplainTory videos
   start on the voice almost immediately.
3. **Hand-written sheets bypass it entirely.** Every delivered job wrote its own
   `SECTIONS` with `under_voiceover: True` hardcoded, so the automatic path above
   never ran.

**If a video with a real cold open arrives:** give the opening its own music
section, let the bed sit at full level (no duck is doing anything anyway), and
either set `--no-bed-calibration` and trim by hand, or calibrate on a trimmed
copy of the VO that excludes the silence. Then check by ear.

---

## 7. Levels, ducking and fades

### 7.1 Ducking

`duck()` in `assemble.py` — one sidechain compressor over the whole music bus,
keyed by the VO: [TASTE for the numbers, [GENERAL] for the approach]

```
sidechaincompress=threshold=0.03:ratio=6:attack=5:release=300:makeup=1
```

- threshold **0.03** linear (≈ −30 dBFS)
- ratio **6:1**
- attack **5 ms**, release **300 ms**
- makeup **1** (none)

SFX and beds are **not** ducked — only music. That is why a crowd bed is the most
dangerous thing in a sheet: it is mid-band, it sits where the voice is, and
nothing pulls it down.

### 7.2 Bed level — the number that matters is the one under speech

Two different quantities, and confusing them runs the bed hot: [GENERAL]

- **Published-mix method**: measure the bed in the gaps between VO lines, with
  the duck released. The only way to get it from someone else's finished video.
  Two reference mixes gave **−13.1 dB (22 %)**.
- **Our calibration**: integrated LUFS of the *ducked* music bus against
  integrated LUFS of the VO. This includes every ducked moment, so it is **not**
  the same number.

Matching one to the other runs ~6 dB hot. On a real mix the calibration was told
−20 dB and the bed under speech measured **−25.9 dB**.

The gap method **cannot be used on our own mixes**: measured at four silence
floors, an ExplainTory VO has **zero gaps ≥ 0.6 s in 12 minutes** and speech
occupies 90–93 % of the runtime.

```
--bed-target-db  -20.0    # assemble.py default [TASTE]
--sfx-db          -6.0    # keeps hits above the bed [TASTE]
--music-db         0.0    # extra manual trim on top of calibration [TASTE]
```

`--bed-target-db` is an **internal control, not a reference comparison**. Report
both numbers on handover — the target you set and the measured under-speech
figure — because only the second describes what a viewer hears:

```python
sp = vo_env_db > -45
under_speech = np.median(music_env_db[sp]) - np.median(vo_env_db[sp])
```

**`measure_ref.py`'s bed ratio does not work on our own mixes.** It reads the p10
of the loudness envelope as "music alone", which is true of a mix with gaps and
false of ours — p10 is just the quietest speech. It reported −2.7 dB (73 %) for a
bus calibrated to exactly −13.0 dB. Use it for *other people's* finished videos,
where the gaps are real; its programme LUFS, LRA and true-peak readings are fine
on anything. [GENERAL]

### 7.3 SFX bus polish

`polish_sfx()`, applied to the SFX bus before summing. Costs 2.8 dB; the makeup
is built in. [TASTE]

```
equalizer f=2400 q w=1.1 g=-4      # out of the way of consonants
equalizer f=3600 q w=1.3 g=-3
highshelf f=9000 g=-3              # stop long-run fatigue
lowshelf  f=120  g=+2.5            # body under impacts
highpass  f=45                     # no inaudible rumble
convolved room tail, wet 0.16
volume +2.8 dB                     # makeup
```

Do **not** run ambience beds through the room impulse — a room tone already is a
room. [GENERAL]

### 7.4 Stems

`--stems DIR` writes `music.wav`, `sfx.wav`, `vo.wav` (all `pcm_s16le`).

**A stem trim is not a bus trim.** The ambience beds are merged into the **SFX
stem** after the polish stage, so that stem holds hits *and* room tone. A real
render adds `--sfx-db` inside `render_sfx_short()`, which reaches the hits only,
while every bed keeps its own solved gain. Recombining stems at different gains
is the right way to A/B a level question in seconds — but **re-render to ship
it**, or you answer a "too loud" note by also making the mix dry. On one mix,
dropping every hit by 2.5 dB moved the SFX bus average by **0.5 dB**. [GENERAL]

---

## 8. Final loudness and true peak

**Anchor the master to the voice. Never to a programme target.** [GENERAL]

The VO arrives already mastered. Any programme-loudness target silently moves it,
because the voice *is* most of the programme. Asked once to match a reference
channel's −21.5 LUFS, `loudnorm` applied a flat **−7.6 dB to everything** and
delivered the voice 7.6 dB below the file that was supplied.

So: **sum music + SFX + VO at unity, limit for safety, ship.** Do not normalise
the sum.

In the cue sheet that is:

```json
"loudness_target_lufs": null,
"true_peak_ceiling_dbtp": -1.0
```

`final_master()` then builds:

```
amix=inputs=3:normalize=0:dropout_transition=0
alimiter=limit=0.8913:attack=5:release=50:level=disabled
```

`0.8913` is `10^(-1.0/20)` — the −1.0 dBTP ceiling. When the target is **not**
null, `loudnorm=I=<target>:TP=<tp>:LRA=11` is inserted before the limiter;
`loudnorm`'s own true-peak limiter is not tight in single-pass mode and the mp3
encoder overshoots after it (a master asked for −1.0 came out at −0.2), which is
why the explicit `alimiter` is always appended.

**Programme loudness is an output, not an input.** It lands a fraction above the
VO's own level, and that difference is exactly how much music and SFX are present.
Report both:

| | measured |
|---|---|
| Voice in | −14.5 LUFS |
| Voice out | **−14.5 LUFS** (unchanged) |
| Programme | **−14.4 LUFS** |
| LRA | 1.6 LU |
| True peak | −1.0 dBFS |
| Bed under speech | −25.9 dB |
| SFX transients above bed | +19.8 dB |

Note this ships ~7–9 dB hotter than the reference channel's back catalogue
(−21.5 / −23.1 LUFS). That is deliberate and correct for YouTube. Mention it once
on the first handover, then stop. [TASTE]

---

## 9. Export

### 9.1 Audio

Chosen by the **output file extension** in `assemble.py`: [GENERAL]

| extension | codec | settings |
|---|---|---|
| `.mp3` | `libmp3lame` | `-q:a 2` → VBR, measured **183.7 kbps**, 48 kHz stereo |
| anything else | `pcm_s16le` | 48 kHz stereo WAV |

Everything internal runs at **48 kHz stereo** (`SR = 48000`, `CH = "stereo"`).

The mp3 lowpasses at **18.0 kHz** against the master's 23.9 kHz; loudness and
peak are identical. It is fine to listen to. **Do not use it as the upload
source** — YouTube re-encodes, and you do not want to stack generations.

A null test against an mp3 shows a large residual even when it is perceptually
transparent, because the codec shifts phase. Do not quote that SNR as a quality
figure. [GENERAL]

### 9.2 Video

```bash
--mux-into in.mp4 --out "Title (final).mp4"
```

→ `-c:v copy` — **the video is never re-encoded.** Audio becomes `aac -b:a 320k`.

**Mux from the WAV master, not from the mp3.** Muxing the mp3 makes the AAC
lossy-on-lossy before YouTube adds a third pass. Either pass `--out ....wav` and
mux that, or rebuild the master from stems:

```bash
ffmpeg -i stems/music.wav -i stems/sfx.wav -i stems/vo.wav -filter_complex \
  "[0:a][1:a][2:a]amix=inputs=3:normalize=0:dropout_transition=0[mx];\
[mx]alimiter=limit=0.8913:attack=5:release=50:level=disabled[o]" \
  -map "[o]" -c:a pcm_s24le -ar 48000 master.wav
```

### 9.3 Previews

`--preview START-END` writes `<name> (preview A-B).<ext>` — the real master, just
cut, with 50 ms fades. mp4 previews use `aac -b:a 256k`. [GENERAL]

Send **3–4 short clips with picture at the specific action beats**, not the whole
render. Every correction on every job came from watching a specific moment.
Audio-only when the question is balance; with picture when it is timing. [TASTE]

---

## 10. Order of operations

```
1.  extract / obtain the VO stem, confirm its LUFS and LRA
2.  visual_redraw.py          → redraw.json
3.  contact sheets            → read every shot
4.  scan.py / cards.py        → section boundaries
5.  transcribe if no script
6.  palette: fetch → palette.py → oneshot.py → merge manifests
7.  music: search → measure drive → pull chosen tracks to assets/<cue id>.wav
8.  build_cues.py             → cues_beats.json  (sections, beats, beds, mutes)
9.  preflight.py + overrun.py + onscreen.py   ← before rendering, every time
10. place.py --no-beds        → cues.json
11. assemble.py --stems       → mix + stems
12. verify: LUFS in/out, bed under speech, sync_check --by-tier --fps <real>
13. send 3–4 clips with picture
14. only then deliver the full mix
```
