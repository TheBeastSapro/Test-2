# The Weirdest Warships from Every Era — job data

The second full job, and the first on a subject the sword palette did not cover.
Everything needed to reproduce it without re-deciding anything. The prepared
palette (309 wav) is derived from `job_ids.json`, so it is not carried here.

| file | what it is |
|---|---|
| `cues.json` | the finished sheet — 330 events, 662 cues with layers, 24 beds |
| `cues_beats.json` | the source sheet: 17 music sections + 91 hand-timed beats + 9 mute windows |
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
| Voice | **-14.5 LUFS** — exactly as supplied | anchor the master to this |
| Programme | **-14.4 LUFS** · LRA 1.6 | an output, not a target |
| Bed under the VO | **-20.0 dB** integrated · **-25.9 dB** under speech | -13.1 dB, but see below |
| SFX bus vs the bed | **+3.5 dB** | SFX sit above the bed |
| Cue changes | 17 -> one per **42.2 s** | one per 47-48 s |
| Density | 330 events -> one per **2.18 s** | ~2.2 s target |
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


## The bed number was never comparable

The -13.1 dB StickTory figure is the bed measured **in the gaps between VO lines**,
with the duck released — the only way to get it out of a published mix. The
calibration was setting a different quantity: the **integrated** level of an
already-ducked music bus against the integrated VO. Matching one to the other is
not like-for-like and the error runs toward "too loud", which is what got
reported.

The gap method cannot be applied to our own mixes at all. Measured on this VO at
four silence floors, there are **zero gaps of 0.6 s or more in 11:58** — speech
occupies 90-93% of the runtime. On this mix the two figures differ by **5.9 dB**:
the calibration was told -20 dB and the bed actually sits at **-25.9 dB** under
speech.

So `--bed-target-db` is an internal control, not a StickTory comparison. -20 was
arrived at by ear across three rounds, and it is also exactly the 10% that was
the standing instruction to human sound designers before any of this was
measured. Report both numbers on handover; only the second describes what is
heard.

## Anchor the master to the voice

Asked to match StickTory's programme loudness, mastering to -21.5 LUFS applied a
flat -7.6 dB to everything and put the delivered voice **7.6 dB below the file
that was supplied** — "you actually reduced the voice as well". The voice *is*
most of the programme, so any programme target moves it.

Sum music + SFX + VO at unity, limit, ship. Programme loudness becomes an output
(-14.4 LUFS against a -14.5 LUFS VO), and the gap between the two is exactly how
much music and SFX are present.

## A long tonal tail is a bed, not a hit

The renaming to *Alexandria* got a ship's bell at hero tier. Reported as
annoying, and the sheet says why twice: the file is **7.00 s** long, and the
event under it is an `element` of strength 0.011 — a caption tick the detector
had classified correctly before a hand-written beat overruled it with a hero
cue. A bell rings at a definite pitch for seconds, so under continuous narration
it is a second sustained voice, the same failure as a crowd ambience arriving as
a hit. Removed; the caption takes a pop like every other caption.
