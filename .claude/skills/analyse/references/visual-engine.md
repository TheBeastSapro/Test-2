# The local visual engine

`forgecast.vision` measures editing style from the pixels — deterministic ffmpeg and
numpy, no API key, no vendor, nothing to rate-limit. Use it whenever the question is
about *how the video is cut and graded* rather than what is said in it.

Why it matters for this skill: a vision model asked "describe the editing style"
returns adjectives. This returns numbers, and numbers can be applied. `render_spec`
is the same shape the render pipeline already accepts, so "adapt this creator's
style" becomes a parameter hand-off instead of a prose instruction.

## Running it

```bash
# a local file
python3 -m forgecast.vision.cli analyse clip.mp4

# save the machine-readable profile too
python3 -m forgecast.vision.cli analyse clip.mp4 --json profile.json --no-shots

# a platform URL (yt-dlp handles acquisition), first 2 minutes only
python3 -m forgecast.vision.cli analyse "https://youtube.com/watch?v=..." --max-seconds 120

# how close is my edit to the reference?
python3 -m forgecast.vision.cli compare reference.json mine.json
```

From Python:

```python
from forgecast.vision import analyse_file
profile = analyse_file("clip.mp4")
profile.edit_signature        # human-readable fingerprint
profile.render_spec.as_dict() # applicable parameters
```

## What it measures, and what each number is for

| Signal | Field | Why it matters |
|---|---|---|
| Shot boundaries | `shot_rhythm.shots` | The spine — every other per-shot number hangs off it |
| Cuts per minute | `shot_rhythm.cuts_per_minute` | The headline pace number |
| Median shot length | `shot_rhythm.shot_length.median` | What you actually set when replicating |
| Regularity | `shot_rhythm.regularity` | 1.0 metronomic, 0 wildly varied. Two edits with identical cuts/min feel completely different at 0.9 versus 0.3 |
| Pacing trend | `shot_rhythm.pacing_trend` | Accelerating edits are a retention technique; decelerating means the payoff is late |
| Transition mix | `shot_rhythm.transition_mix` | Hard cuts versus dissolves, as a ratio |
| Grade | `colour.grade_label`, `palette` | The look, plus an applicable ffmpeg `eq` string |
| Motion | `motion.dominant`, `dominant_camera_move` | Static, subtle, moderate, high; zoom versus pan |
| Caption zone | `overlay.caption_zone` | Where burned text sits and how persistently |
| Loudness / silence | `audio.silence_ratio` | "No dead air" is a measurable, copyable choice |
| Tempo | `audio.tempo_bpm` | Music bed speed |
| **Cut-to-beat** | `beat_alignment.verdict` | Whether cuts land on audio onsets |

**Cut-to-beat is the signal nothing else can give you.** It is invisible in a
transcript and invisible in a still frame, and it is the difference between an edit
that feels intentional and one that feels arbitrary. Two videos with the same
cuts-per-minute, one beat-locked and one not, are not the same style.

## Reading the output honestly

The engine reports its own limits; carry them into your report rather than dropping
them.

**Shot detection is luma-based.** `scdet` scores brightness change, so a cut between
two similarly-lit shots is faint however different the colours are. Measured on flat
fields: an 8-level luma step scores ~2.7 and is missed, 21 levels scores ~7 and is
caught. If a shot count looks low, check `shot_rhythm.detection.threshold` — it is
reported precisely so a surprising number can be audited.

**Text position, not text contents.** There is no OCR, so the engine finds *where*
persistent text sits and how much of the runtime it covers. Reading the words needs
the semantic layer.

**`semantic` is null.** Shot subjects, graphic style vocabulary, motion-graphic
description and the actual words on screen are not measured. That requires a
multimodal model, which requires a key. When `confidence.semantic` is `absent`, say
so — do not fill the gap with plausible-sounding guesses about what is in frame.

**Motion is a heuristic, not optical flow.** Zoom versus pan is inferred from whether
frame-edge change outruns frame-centre change. It reports `unclear` rather than
picking when the evidence is thin, and `confidence.motion` is `medium` by design.

**Low shot counts are weak evidence.** Under about 8 shots, rhythm statistics
describe an anecdote. `confidence.shot_detection` drops to `low` and says so.

## Where acquisition can fail

Local files and direct media URLs are tested and work. Platform URLs go through
yt-dlp, which is written and correct but **could not be verified end to end here**:
YouTube returns HTTP 403 for media to datacentre IP ranges across every player
client. That is a platform-side block, not a code fault. Run acquisition from a host
with residential egress, or supply cookies.

Practical consequence for the website: acquisition belongs on a worker with suitable
egress, and it is the piece to expect breakage in. Analysis, once the file is local,
has no external dependency at all.

## Combining with the semantic layer

The two halves answer different questions and neither replaces the other:

- **Local engine** — how it is cut, paced, graded, and whether cuts hit the beat.
  Exact, free, reproducible.
- **Vision model** (`watch_*` tools, or your own key) — what is in the shot, what the
  on-screen text says, what the graphic style is, how the hook reads.

For a full style teardown, run the engine for the measurements and a vision pass for
the semantics, then put the engine's numbers in `visual_layout` on the per-video JSON
and attach the whole profile under a `style_profile` key. The engine's numbers should
win on anything countable — cuts, durations, colours — because they are measured
rather than estimated. A vision model asked to count cuts will guess.
