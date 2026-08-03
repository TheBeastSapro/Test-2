---
name: sound-designer
description: Add music and sound effects to an animated explainer video, placed by measurement rather than by ear — find the beats in the picture, fetch a sound palette, place and level the cues, duck the music under the narration, master, and verify the timing in numbers. TRIGGER on "sound design this", "score this video", "add music and sfx", "add sound effects", "mix music under the voiceover", or any request to sound-design a video. Also use for questions about SFX timing, music placement, ducking, loudness targets, or why a mix sounds repetitive or badly synced.
---

# Sound designer

Do the whole job when given a video and a voiceover: find the beats, fetch and
prepare a palette, place the cues, mix, master, and **verify in numbers before
showing anything**.

Deliver a mastered file at the configured loudness target plus the cue sheet, and
report what was placed and what the measurements say.

## What you need from the user

A four-line brief is complete input. **Start work; do not ask for more.**

```
Video: <path or link>
Voiceover: <path or link>     <- MASTERED VO AS A SEPARATE FILE, always
Title: <title>
Script: <text, doc, or chapter list>       (optional but valuable)
```

The voiceover must be separate, because both the ducking and the bed level are
calibrated against the VO stem — a mix-down cannot be used. If the VO is missing,
ask only for that.

## Order of work

Run these from this skill's `scripts/` directory. All of it is default behaviour,
not something to be told.

1. **`visual_redraw.py video.mp4 -o redraw.json`** — the beats.
   Do not use optical flow on animation, and do not guess times from the script.
   For live action use `visual_events.py` instead and say so, because redraw
   detection has nothing to work with when every frame changes.

2. **Build a palette.** `build_palette.py --spec ../examples/palette.history.json
   --out pal` fetches against the user's own `EPIDEMIC_SOUND_API_KEY`. Copy the
   spec and swap its `topical` block for the video's subject; the six `generic`
   categories suit anything. If the subject is not the spec's, **say so up front**
   and budget the fetch, rather than discovering it mid-mix.

3. **Music sections from the script's chapters**, one cue per topic. If there is
   no script, section by measured energy instead.

4. **Hand-cast the first two or three minutes**, and every named beat, off contact
   sheets. This is where the audience decides and pooled casting is not good
   enough. `../examples/beats.example.py` is the pattern. Extract sheets at 4 fps
   with burned-in timestamps and *look at them* — check what each thing is
   actually touching.

5. **`place.py` → `assemble.py --stems`.**

6. **Verify before showing anything:** `sync_check.py --by-tier`, and measure the
   bed on the stems. Report the numbers.

7. **Send 3–4 short clips WITH PICTURE at the specific action beats** — not the
   whole mix. Every correction on the reference project came from watching a
   specific moment; showing those early is what turns five rounds into one.

8. Only once those are approved, render and deliver the full mix.

## Non-negotiables

Full reasoning and the measurements behind each of these is in `docs/METHOD.md`.
Read it before changing any of them.

- **Diagnose by measuring, never by ear.** Sync was "fixed" twice in the wrong
  direction by guessing. The **per-tier** breakdown is where the diagnosis lives;
  the headline number only ever says "scattered".
- **Effects sit ABOVE the music bed.** Placing them under it is why whole minutes
  read as having no sound design.
- **Count distinct files.** No file more than ~10 times in 13 minutes, never twice
  inside 30 s. One tick played 240 times is what "sounds cheap" actually means.
- **Never compensate for the attack twice.** `palette.py` trims to the attack and
  stores a per-file anchor; do not also run a transient search at mix time.
- **Split multi-hit library takes** with `oneshot.py` before placing them.
- **Level beds from measured rms**, never a flat trim — a constant trim put every
  bed at −55..−65 dBFS, i.e. silent.
- **Calibrate the bed on the music stem**, not the finished master. Loud effects
  in the voice's gaps inflate the reading and the loop then pulls the music down.
- **A bed never ducks**, so a bed with human voices in it becomes a second
  narrator. Call crowd recordings by hand only where a crowd is on screen.
- **Watch `place.py`'s warnings.** A missing palette category used to be skipped
  silently and every strike lost its weight layer for a whole render.
- **Cast by OBJECT, not by keyword.** The tool can prove a sound is on the frame;
  it cannot know the blade hit a shield rather than a body. That is the one class
  of error measurement never catches — it needs eyes on the picture.

## Configuring for a channel

The numbers that define a sound live in `scripts/house.py`. Write them out with
`python3 scripts/house.py my-house.json`, edit, and pass `--config`.

**Measure them; do not inherit them.** `measure_ref.py --mix reference.wav --vo
reference-vo.wav` reports the bed-to-programme ratio, loudness, dynamic range and
cue-change rate of a mix the user already likes. Use a reference they have the
rights to. The shipped defaults are one measured example, not a target.

## Expectations to set

Expect **one round of notes, and expect it to be about casting** — whether each
sound is the right object for what is on screen. Anything else needing a second
round means a rule is missing from `docs/METHOD.md`; write it there rather than
fixing it silently.

A 13-minute video with ~600 cues takes 20–30 minutes to render and a few GB of
scratch. Check free space before starting.

## Verify the install

`python3 selftest.py` builds a synthetic clip, voiceover and palette and runs the
whole pipeline. No API key needed. Run it first if anything behaves oddly.
