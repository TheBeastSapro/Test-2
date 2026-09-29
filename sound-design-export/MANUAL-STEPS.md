# MANUAL-STEPS.md

What the pipeline does **not** do for you. Read this before assuming a clean run
means a finished mix.

The scripts automate measurement, placement and mixing. They do not automate
**judgement about what a sound is of**, and that is where every round of notes
on every job has landed.

---

## Done entirely by hand

### 1. The hand-timed cue sheet — the largest manual step by far

`build_cues.py` is written from scratch for each video. Nothing generates it.
For the castle job it holds **193 hand-timed beats, 19 music sections, 26 beds
and 11 mute windows**, and every time in it was read off a contact sheet by eye.

Per beat you choose: the time, the label, the palette category, the tier, the
gain, any stacked layers, whether to snap to the nearest picture change, and
optionally a `max_len`. The placer fills in the generic cues around them, but the
beats that matter are all yours.

Budget: this is most of the work on a new video.

### 2. Reading the contact sheets

The pipeline extracts frames and tiles them. A person looks at them and decides
what is happening. There is no automated shot description.

Specifically manual:
- which panel holds the beat
- what object is being struck (blade on shield is wood+metal; blade in body is
  flesh — the detector cannot tell)
- whether a wide shot is an advance or an aftermath
- which shots are photographs, paintings or maps and therefore need a mute window

### 3. Identifying the section-transition device

Different on every channel and it has already changed once mid-channel (title
card → scrolling grid). Somebody has to look at a coarse sheet and see what the
transition *is* before choosing or writing a detector.

### 4. Choosing the music search terms

The eight mood strings in the SOP were written by hand from the story. The drive
*measurement* is automated; deciding that the Kenilworth section wants "the king
tries everything: trebuchets into water" and that this means marching-and-tragedy
is not.

### 5. Mapping story beats to sound categories

"He packs the tunnel props with forty pigs and sets it alight" → `ignite` +
`pig`. No automation. `place.py` has a `HERO_CAT` word map but its vocabulary is
weapon-flavoured and has to be extended per subject.

### 6. Calibrating the picture detectors for a new subject

`fire.py` and `onscreen.py` carry colour thresholds tuned to this channel's flat
palette. A different art style needs the thresholds re-picked against real
frames. **The figure detector is explicitly not calibrated** — it reports 29 % on
a crowd bed whose frames plainly show men in a breach. Never cut a bed on it
without checking a sheet.

### 7. Deciding which flagged items are real

`preflight.py` and `overrun.py` produce lists, not verdicts. On the castle job
`overrun.py` flagged 17 cues and **10 were correct** — a card boom is supposed to
ring across its transition. A person decides which is which every time.

Same for `multihit.py`: a strict envelope test flags 65 of 240 files, most of
them one continuous gesture. The usable signal is the Epidemic *title*, read by a
human.

### 8. Deciding a note's scope

When a note arrives, deciding what it does and does not authorise. A previous job
answered one note by re-scoring a whole section and the verdict was *"you
actually added too much... previous mix was better"*. A note says what is wrong;
it does not authorise a re-score.

---

## Checked by ear

These have no measurement that settles them.

| what | why measurement doesn't settle it |
|---|---|
| **Casting — is this the right object?** | Timing, tier and level can all be right and the sound still be of the wrong thing. This is where every round of notes has landed. |
| **Bed level** | `--bed-target-db -20` was arrived at across three rounds of listening. −13 (the reference figure) was reported as too loud. The meters called both fine. |
| **Duck depth and speed** | The 6:1 / 5 ms / 300 ms numbers are an ear judgement. |
| **Whether a section is "floaty"** | The drive score catches the obvious cases. A track can score 3.4 and still feel wrong under a particular story beat. |
| **Whether a hit is satisfying** | `sync_check` says it is inside a frame; it cannot say it lands well. |
| **Whether the density feels right** | The target is ~2.2 s and the castle job shipped 1.99 s. Whether that reads as dense or busy is ear-only. |
| **Vocal placement** | The cry at +80 ms after the blade, the grunt on the swing. Reserved for the blow that lands. |

---

## Semi-automated — script assists, person decides

| step | automated | manual |
|---|---|---|
| Section boundaries | a change is detected | *where* the story turns, and which detected change is the real one |
| Music casting | drive score, vocal-tag reject, duration filter | which of the surviving candidates fits the beat |
| Palette | normalise, trim, measure anchors | which sounds to fetch, and their search terms |
| Splitting takes | attack counting | reading the title to decide if it really is several takes |
| Beds | level solved from measured rms | which bed, where it starts and stops |
| `max_len` caps | the overrun list | which overruns are wrong |

---

## Known limitations

**Cold opens are untested.** See SOP §6. `analyze.py` places an intro riser and
marks sections `under_voiceover`, but `assemble.py` never reads that flag, the
duck is applied to the whole music bus at once, and the bed calibration compares
whole-file integrated loudness — so a long silent opening drags the VO figure
down and biases the trim. All three delivered videos start on the voice almost
immediately, so none of this has been exercised. Treat it as unverified.

**`measure_ref.py`'s bed ratio is wrong on our own mixes.** It reads the p10 of
the loudness envelope as "music alone", which is true of a mix with gaps between
VO lines and false of a continuous narration — p10 is just the quietest speech.
It reported −2.7 dB (73 %) for a bus calibrated to exactly −13.0 dB. Use it on
other people's finished videos. Its programme LUFS, LRA and true-peak readings
are fine on anything.

**`sync_check.py` defaults to 24 fps.** Pass `--fps` with the file's real rate or
every "within one frame" figure is quoted against the wrong frame length.

**`oneshot.py` overwrites silently** when `--name` repeats. Give every source its
own prefix.

**The whoosh sync figure cannot be improved.** A 400 ms ramp has no well-defined
onset, so the metric cannot pin it — measured against the cue the p90 is 212 ms,
and measured against the file's own start it is *worse* at 265 ms. Overall
"within one frame" sits around 70–75 % for this reason. Do not chase it.

**YouTube audio cannot be downloaded** from a cloud container — the API responds
but every media fetch returns 403, on the IP range rather than the video. To
measure a reference video, get the file attached directly.

---

## Known fixed bugs

Both were found by running the pipeline, and both are fixed in this export.
Listed because a stale copy elsewhere will still have them.

1. **`loudness_target_lufs: null` could not be rendered.** The cue-sheet setting
   for "anchor the master to the voice" was interpolated into the filter string
   as the literal `None`, so ffmpeg got `loudnorm=I=None` and refused it — at the
   last stage of a nine-minute render. `final_master()` now skips `loudnorm`
   entirely when the target is null.

2. **`--out *.wav` with `--mux-into` died.** The mux handed ffmpeg a video stream
   and an audio stream to write into a WAV container, which holds exactly one
   stream: `WAVE files have exactly one stream`, after the whole render had
   completed. It now corrects the extension to `.mp4` and says so. *(Found by the
   test fixture in this export, not on a real job.)*
