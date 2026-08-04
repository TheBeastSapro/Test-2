---
name: sound-designer
description: Score a video with music and effects placed by measurement rather than by ear — read the beats from the picture and the narration, choose a bed, place accents above it, duck the music under the voice, master to the platform target, and check the timing in numbers. TRIGGER on "sound design this", "score this video", "add music and sfx", "add sound effects", "mix music under the voiceover", or any request to sound-design a video. Also use for questions about SFX timing, music placement, ducking, loudness targets, or why a mix sounds repetitive or badly synced.
---

# Sound designer

This is the method. Forgecast's `sound` node is the implementation, and it runs on
every render — this file exists so that you can read what it is doing, judge the
result, and change the parts a channel wants changed.

An earlier version of this file told you to run a suite of scripts from a `scripts/`
directory. That directory has never existed in this application; the scripts belonged
to a different tool. Every instruction below names something in this codebase, and
`tests/test_skills_shipped.py` is what keeps it that way.

## Where the work happens

| The step | Where it is |
| --- | --- |
| What this video's sound should be | `style.sound.brief_from` (from a measured reference) or `style.sound.recommend` (from the niche) |
| Where cues go and in what layer | `style.sound.design` → a `SoundPlan` of `SoundCue`s |
| Choosing the bed and fetching it | `nodes.sound.choose_track`, `fetch_palette` |
| Laying the bed and the accents | `nodes.sound._lay_bed`, `_lay_accents` |
| The final master | `render.assemble_video`, after the picture is muxed |

The stage runs after `voice` and before `render`, and it depends on `voice` rather
than on `script` because both numbers it needs — how long the bed must run and how
loud it must be — come from the narration that exists, not the script's estimate of it.

## What a channel has to have

**A music vendor.** `providers.registry` ships no default one, on purpose: nothing
should start spending on music because a connector happened to be configured. A
channel with no music vendor named gets a finished video with no bed, and says so.

**A separate voice stem.** Ducking and bed level are both calibrated against the
narration on its own, so a mixed-down programme cannot be used. In a normal run this
is free — `voice` writes the stem and `sound` reads it.

## Order of work

1. **Beats from the picture and the narration**, not from the script's timings. The
   script says a scene is six seconds; the voiceover says it is 7.4, and the second
   number is the one the cue lands on.

2. **A brief before a bed.** `brief_from` measures a reference the operator already
   likes — bed-to-programme ratio, loudness, dynamic range, cue-change rate. Failing
   that, `recommend(niche)` gives a starting point. **Measure; do not inherit.** The
   shipped defaults are one measured example, not a target.

3. **Music sections from the script's chapters**, one cue per topic. With no chapters,
   section by measured energy instead.

4. **Cast the opening by looking at it.** The first two or three minutes and every
   named beat are where the audience decides, and pooled casting is not good enough
   there. Check what each sound is actually touching.

5. **Place, then measure.** Report the numbers before showing anything.

6. **Show three or four short clips with picture, at the specific action beats** —
   not the whole mix. Every correction worth having comes from watching one moment;
   showing those early is what turns five rounds of notes into one.

## Non-negotiables

Each of these is a mistake that was made once and measured. `sound-designer-method.md`
carries the numbers behind them; read it before changing any.

- **Diagnose by measuring, never by ear.** Sync has been "fixed" twice in the wrong
  direction by guessing. A per-tier breakdown is where the diagnosis lives; the
  headline number only ever says "scattered".
- **Effects sit ABOVE the music bed.** Placing them under it is why whole minutes read
  as having no sound design at all.
- **Count distinct files.** No file more than about ten times in thirteen minutes,
  never twice inside thirty seconds. One tick played 240 times is what "sounds cheap"
  actually means.
- **Never compensate for the attack twice.** The palette trims to the attack and stores
  a per-file anchor; do not also search for the transient at mix time.
- **Split multi-hit takes** before placing them, or one cue fires three times.
- **Level beds from measured RMS**, never a flat trim. A constant trim put every bed at
  −55 to −65 dBFS, which is silence.
- **Calibrate the bed on the music stem**, not on the finished master. Loud effects in
  the voice's gaps inflate the reading, and the loop then pulls the music down.
- **A bed never ducks**, so a bed with human voices in it becomes a second narrator.
  Crowd recordings are placed by hand, only where a crowd is on screen.
- **A missing palette category is reported, not skipped.** Silently skipping one cost
  every strike its weight layer for a whole render.
- **Cast by OBJECT, not by keyword.** Measurement can prove a sound is on the frame; it
  cannot know the blade hit a shield rather than a body. That is the one class of error
  measurement never catches, and it needs eyes on the picture.

## What this stage will not do

**It will not fail the run.** Every failure degrades to what survived plus the named
reason for what did not: a finished video with no bed is a smaller loss than no video.
Degrading is still reported as degrading — a video with accents and no bed says so
rather than reporting itself complete.

**It will not fetch twice.** The node does not retry around the spend, because on
Epidemic a download is not merely a cost: exporting a track into published content is a
reportable event, and a retried fetch is a second export of a video that ships once.

**It will not place ambience.** `design` puts room tone under everything, on the sound
grounds that a cut into digital silence reads as a mistake even when the edit is clean.
Choosing a room-tone source by keyword is exactly the casting-by-keyword error above, so
where a music bed runs the bed is the floor, and where one does not the ambience cue
stands as an unmet recommendation rather than something quietly satisfied.

## Expectations to set

Expect **one round of notes, and expect it to be about casting** — whether each sound
is the right object for what is on screen. Anything else needing a second round means a
rule is missing from the method file; write it there rather than fixing it silently.
