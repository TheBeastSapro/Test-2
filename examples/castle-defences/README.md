# Castle Defences — job data

The third full job, and the first where the subject genuinely overlaps a palette
we already had. Eight castle features, each with one siege story: Murder Holes
(Krak des Chevaliers, 1271), Moat (Kenilworth, 1266), Portcullis, Arrow Loops
(Carcassonne, 1240), Round Towers (Rochester, 1215), Drawbridge, Gatehouse
(Dover, 1216), Concentric Walls (Château Gaillard, 1203).

| file | what it is |
|---|---|
| `cues.json` | the finished sheet — 372 events, 771 cues with layers, 26 beds |
| `cues_beats.json` | the source sheet: 19 music sections + 193 hand-timed beats + 11 mute windows |
| `build_cues.py` | writes `cues_beats.json`; every time in it was read off a contact sheet |
| `redraw.json` | `visual_redraw.py` output — 141 cuts, 217 actions, 165 elements |
| `palette_manifest.json` | 337 files across 67 categories, with per-file anchors |
| `castle_ids.txt` / `swish_ids.txt` / `air_ids.txt` | the 171 Epidemic SFX ids fetched on top of the sword palette |
| `music_pick.json` / `mus_measured.json` | the 19 tracks, and the drive measurement that chose them |
| `sfx_titles.json` | every internal filename mapped to its real Epidemic title |
| `mus_probe.py` / `mus_measure.py` | collect music candidates, then measure them for rhythmic drive |
| `multihit.py` | finds takes masquerading as samples |
| `preflight.py` | flags hero cues cast from a file that sustains instead of decaying |
| `fire.py` | scores drawn flame area per frame, so a fire bed can be cut to the shot |
| `onscreen.py` | scores water and figures per frame, to audit every bed against its shot |
| `overrun.py` | finds cues still sounding after the picture has cut |
| `scan.py` | one decode pass: era-card score, banner-strip fingerprint, ink centroid |
| `shots.py` / `sheets4.py` / `fine.py` | contact sheets at the cuts, then at 0.5–1.8 s over eight action windows |
| `titles.py` | replays the searches to recover every file's Epidemic title |
| `transcript.json` | the VO, transcribed locally — no script was supplied |
| `cue_sheet.md` | the human-readable cue sheet |

## Measured result

| | this mix | reference |
|---|---|---|
| Voice | **−14.5 LUFS** in, **−14.5 LUFS** out | anchor the master to this |
| Programme | **−14.4 LUFS** · LRA 1.6 · TP −0.7 | an output, not a target |
| Bed under speech | **−25.9 dB** | warships: −25.9 dB |
| Bed under the VO, integrated | **−24.1 dB** | `--bed-target-db -20` |
| SFX transients above the bed | **+19.9 dB** | hits sit above the bed |
| Cue changes | 19 → one per **38.9 s** | warships 42.2, StickTory 47–48 |
| Density | 372 events → one per **1.99 s** | ~2.2 s target |
| Distinct files | 206, busiest ×9 | no file more than ×10 |
| Sync (24 fps) | median **−2.9 ms**, p90 147 ms, 72.9% inside a frame | sword −0.6/74.5/75.2%, warships −0.2/154/70.9% |

## Rebuilding

```bash
python3 <skill>/examples/deadliest-sword/rebuild_palette.py --scripts <skill>/scripts
#   ... then pull castle_ids.txt + swish_ids.txt + air_ids.txt with the Epidemic
#   API, prepare with palette.py, split the multi-take recordings with
#   oneshot.py (see build_cues.py's header), and merge into pal/.
python3 build_cues.py
python3 <skill>/scripts/place.py --cues cues_beats.json --events redraw.json \
        --palette pal --out cues.json --no-beds
python3 <skill>/scripts/assemble.py --cues cues.json --vo vo.wav \
        --assets ./assets --out "mix.mp3" --stems stems
```

`--no-beds` again: all 26 beds are hand-assigned, because a bed never ducks.

## What this job added to SKILL.md

### A sustaining file is a bed, and a bed is cut to the shot

*Reported after the first pass:* "unnecessary fire sfx, it's keep continuing and
not stopping where necessary." Both halves of that were true and both were
measurable.

The fire bed under Rochester's mine ran the whole music section — **31.9 s at
−37 dBFS**, a *featured texture* level — while `fire.py` measures drawn flame on
screen for **2.92 s** (400.000–402.917). Torch crackle therefore played for 13.6 s
before anything was alight and 15.4 s after the corner had already come down, over
a diagram of a square tower. Retimed to 399.3–404.2 at −40 dBFS with 0.9 s fades;
`amb_08` now spans the section underneath.

The second half was the hero cue on top: the ignition at 400.000 was cast from
*Fire, Torch, Circular Swooshes* — 6.17 s, and it does not decay. `preflight.py`
measures the median level over a file's second half relative to its peak, which
separates the two cases that length alone cannot: a 6.19 s debris fall sits at
−38.4 dB (a hit that rings out) and a 3.03 s roaring flame sits at −9.5 dB (a
bed). Four of six `firewh` files and one of six `treb` files were beds in a hit's
clothes — and the sustaining catapult was the **flame ball** recording, cast onto
a trebuchet at 144.33 with no flame anywhere near it.

Fixed: `ignite` = the one short decaying file, the sustaining four parked in
`firetail` where nothing auto-casts them, the doubled flare at 402.583 dropped.
Measured after: the 3–8 kHz crackle band is at the noise floor from 391–396 s and
from 410 s on, where it used to run continuously.

### The full sweep: audit every bed and every tail, not just the reported one

*Then:* "check full and don't make unnecessary sfx like that." The same two
measurements over the whole 12:19 found worse than the fire.

**Beds.** `onscreen.py` scores water (a flat blue region in the *lower* frame —
sky is the same hue) and figures per frame. It found `Water, Turbulent, River,
Fast Flow` running **57.7 s** under Château Gaillard with water on screen **15%**
of it: a map, a plan on white, a castle under lightning, a target diagram, arrows
on white. Replaced with neutral air. A second fast river ran 35 s under the
drawbridge's ditch — the water is genuinely there (86.5%) but a moat is standing
water, so it became gentle lapping. Both were the fire fault, one of them bigger.

Two beds were left alone on purpose. The Kenilworth lake laps sit at 39% and 28%
presence, but a gentle lap under a section whose premise is a castle in a lake is
*location*, not an event. And the figure proxy is not calibrated — it reports 29%
on a 7 s crowd bed whose frames plainly show men pouring through a breach, so
those were checked on a contact sheet and kept.

**Tails.** `overrun.py` compares each cue's audible tail (to −30 dB below its own
peak, not its full length) with the time to the next scene cut. 17 cues were
still sounding more than 1.5 s after the picture moved on. **Ten of them were
right** — four section-card booms, the corner collapse, the gate thrown open —
because a card boom is *supposed* to ring across its transition. So the fix is
per-cue, never global: a beat now takes an optional `max_len` (8th field in the
tuple), `place.py` carries it through and `assemble.py` trims there with a short
fade. Seven caps applied, plus one 4.6 s stone scrape droning at hero level under
a diagram.

Both scripts belong in the pre-render checklist. Between them they catch the two
halves of a sound that will not stop: a file that never decays, and a file that
decays fine but is longer than its shot.

### The section transition is not always a card

This channel runs a **grid of all eight features** as its section transition —
the whole menu on screen, scrolling to the next item — plus a persistent banner
naming the current feature. There is no white-frame-plus-red-progress-bar card,
so `cards.py` finds nothing here and the failure mode `banner.py` was kept to
document does not arise. What works: the banner-strip fingerprint diff in
`scan.py` (8 changes, one per feature), cross-checked against the grid on a
contact sheet. Two *red* full-screen cards exist and matter — "Murder Holes" at
45.17 and "This is the moment Dover should have fallen" at 581.38 — and a
red-field detector finds both.

### `body` names an object, so the default weight layer is per-video

`place.py` hardcoded `["body"]` — four flesh punches — as the weight under every
generic strike. On a video about stone, timber and iron that is the wrong object,
and with only four files they played **31 times each**, three times over the
reuse rule, in a mix whose next-busiest file was ×9. It is now
`cue["default_weight_cats"]`, defaulting to `["body"]`. Here it is a 24-file pool
of masonry, rock, ram timber and the flesh punches, which took the busiest weight
file to ×5.

### `loudness_target_lufs: null` could not actually be rendered

The rule is "anchor the master to the voice" and the cue-sheet setting for it is
a null loudness target. `final_master` interpolated that straight into the filter
string, so ffmpeg was handed `loudnorm=I=None` and refused it — the documented
setting failed at the last stage of a nine-minute render. It now skips loudnorm
entirely when the target is null: sum at unity, limit, ship.

### Measure a track's drive; do not read its title

`mus_measure.py` scores onset density, pulse-regularity (autocorrelation peak of
the onset envelope) and percussive fraction over 45 s of each candidate. Cast on
title alone, *Arrival at Caelmere Keep* and *The King's Return* are obvious
picks for a castle video; measured, they score 2.25 and 2.10 against 3.4–3.8 for
what shipped, i.e. they are the ambient wash that gets reported as "float music,
bit annoying". 116 candidates measured, 19 cast.

### Test an unnamed bed for voices instead of trusting the filename

Six ambiences carried over from the sword palette and their Epidemic titles are
not recoverable — that job stored CDN ULIDs, a different id space from what
search returns. The one thing that must not be in a bed is a second voice, so
measure it: `pyin` over the harmonic component, counting frames with a confident
pitch in the human F0 range (85–350 Hz), calibrated against the two files known
to be "Voices, Yells". Those score **0.14 and 0.25** mean confidence; every other
bed scores **≤0.04** — except `amb_05` at **0.16**, which was dropped. Band-energy
and modulation-depth tests do not separate them: water and wind score as high as
crowds on both.

### Cold air is an object too

All four wind recordings the obvious searches return are "Polar" or "Heavy
Storm, Cold". Under a Crusader castle in Syria, a hilltop in Languedoc and an
English keep in November that is the same class of error as marching over
corpses — the beds were re-cast to neutral and dry-grass air, and the polar ones
kept only where there is snow and tents on screen.

### A script is not required

None was supplied. The VO was transcribed locally with `faster-whisper` (base.en,
229 segments, a couple of minutes on CPU), which is enough to cast from: proper
nouns come out mangled — Krak des Chevaliers as "Crackday Chevelier", portcullis
as "Port Colus", Château Gaillard as "Guy Lard" — but every story beat and its
timing is there, and the picture decides the casting anyway.

### Split only what the title says is several takes

The strict multi-attack test (two peaks each reaching 55% of the file's own peak,
≥150 ms apart, with a real trough between) still flags 65 of 240 files, most of
them one continuous gesture: a catapult creaking then releasing, a door latching
then thudding, a pour. Splitting those destroys them. The reliable signal is the
Epidemic title — `x2`, `Variations`, `Impacts` plural — which picked out 8 files
and turned them into 54 front-loaded one-shots with 0–15 ms anchors. The loose
version of the test (any crossing of 30% of peak) flagged **108** files including
six sword-palette whooshes the previous job had already validated.
