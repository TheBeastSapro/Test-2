# The Weirdest Warships from Every Era — job data

The second full job, and the first on a subject the sword palette did not cover.
Everything needed to reproduce it without re-deciding anything. The prepared
palette (309 wav) is derived from `job_ids.json`, so it is not carried here.

| file | what it is |
|---|---|
| `cues.json` | the finished sheet — 329 events, 661 cues with layers, 24 beds |
| `cues_beats.json` | the source sheet: 17 music sections + 92 hand-timed beats + 9 mute windows |
| `build_cues.py` | writes `cues_beats.json`; every time in it was read off a contact sheet |
| `redraw.json` | `visual_redraw.py` output — 88 cuts, 293 actions, 140 elements |
| `palette_manifest.json` | 309 files across 62 categories, with per-file anchors |
| `job_ids.json` | Epidemic ids: 196 naval SFX + 18 music tracks |
| `cue_sheet.md` | the human-readable cue sheet handed to Sapro |
| `cards.py` | finds the era title cards (white frame + red progress bar) |
| `fire.py` | finds the frames where the animation draws a fireball |
| `preview.html` | the cue sheet as a self-contained interactive timeline |
| `mkdata.py` | cue sheet -> the timeline's inlined data |
| `banner.py` | finds era-banner changes — kept as the thing that got it *wrong*, see below |
| `sheet.py` | contact sheets at arbitrary times, timestamps burned in |
| `report.py` | cue sheet -> markdown |

## Measured result

| | this mix | StickTory refs |
|---|---|---|
| Programme | **-14.0 LUFS** · LRA 1.7 · TP -0.7 dBFS | -21.5 / -23.1 LUFS, LRA 2.3-2.6 |
| Music bus under VO | **-13.0 dB** (calibrated) | -13.1 dB measured on their VO stem |
| SFX bus vs music bus | **+1.3 dB** (mean -27.8 vs -29.1) | SFX sit above the bed |
| Cue changes | 17 -> one per **42.2 s** | one per 47-48 s |
| Density | 329 events -> one per **2.18 s** | ~2.2 s target |
| Distinct files | 110, busiest ×9 | no file more than ×10 |
| Sync (30 fps) | median **-0.2 ms**, p90 154 ms, 70.9% inside a frame | sword final: -0.6 ms, 74.5 ms, 75.2% |

## Rebuilding

```bash
python3 <skill>/examples/deadliest-sword/rebuild_palette.py --scripts <skill>/scripts
#   ... then pull job_ids.json's naval set, prepare with palette.py, and drop the
#   sword palette's amb / impact / body before merging (see below).
python3 build_cues.py
python3 <skill>/scripts/place.py --cues cues_beats.json --events redraw.json \
        --palette pal --out cues.json --no-beds
python3 <skill>/scripts/assemble.py --cues cues.json --vo vo.mp3 \
        --assets ./assets --out "mix.mp3" --stems stems
```

`--no-beds` is deliberate: all 24 ambience beds are hand-assigned in
`build_cues.py`, because a bed never ducks and rotation cannot know that an
engine room does not belong under a Bronze Age deck.

## What this job added to SKILL.md

- Detect the era **card**, not the banner. `banner.py` is here as the negative
  result: it finds a change but fires on either the old text leaving or the new
  text arriving, and on this video those are up to 1.8 s apart.
- Coarse contact sheets find the *scene*; only a ~1 s sheet finds the *frame*.
  Three payoff beats were 1.1-7.1 s wrong when read at 6 s spacing.
- A non-combat topic replaces `amb`, `impact` and `body` wholesale. Those three
  name objects; the rest of the palette names air and transients and carries.
- **A hand-timed beat is never dropped.** `place.py` said so in prose and did
  not do it: the guard that thins the generic pool was being applied to
  designed cues too, and deleted **31 of 106** on this video — including all
  seven era-card whooshes, on every render, silently. Fixed in the script; the
  placer now also names any two hand beats inside 300 ms so a doubled hit is
  caught by count rather than by ear.

## Score the picture, not the brief

The animator note for this video says of the K-class collision sequence: *"No
explosions, no heroics."* That is an instruction to the animator about what to
draw. The animator drew fourteen fireballs anyway, and the first mix followed
the note instead of the frames — no explosion cues at all across 19.5 s of
burning ships, the loudest moment in the video scored as its quietest, and the
music deliberately held flat under it.

An accuracy note constrains the drawing. What reaches the sound is whatever
ended up on screen, so measure that: `fire.py` scores orange burst area per
frame and its local maxima are where the explosions go. It also caught a plain
error the eye had missed — Bushnell's mine detonates at 369.20 and the cue was
sitting at 371.67, on the scene cut *after* it.

## And then stop

The first attempt at that correction also swapped the music under the collision
column for a driving cue, split the section, added twelve water cues, and let
the placer fix restore two dozen other beats — and the channel owner's verdict
was *"you actually added too much... previous mix was better, I just said that
screenshot part and the explosion."* He was right.

A note says what is wrong; it does not authorise a re-score. The fix that
shipped is the approved sheet plus **nine new cues and seven layers**: fire on
the beats that already existed, four bursts that had nothing on them, and water
on four hulls that are visibly turning. Music untouched.

Measure the delta before sending it. Where a beat already exists, the new
element belongs on it as a layer rather than as a second cue — one moment, two
elements, no change to the density the owner already signed off.
