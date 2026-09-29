# sound-design-export

The ExplainTory sound-design pipeline, packaged so another Claude can run it the
same way. Everything here was read out of working code, and the test at the end
of RUN.md was executed before it was written down.

## Read in this order

| file | what it is |
|---|---|
| **RUN.md** | requirements, the one command, and a self-contained test with its real expected output |
| **SOUND-DESIGN-SOP.md** | the full procedure — inputs, music, SFX, beds, levels, ducking, loudness, export |
| **SETTINGS.md** | every setting tagged **GENERAL** (portable) or **TASTE** (chosen for this channel) |
| **MANUAL-STEPS.md** | what is still done by hand or judged by ear, and the known limitations |
| **SKILL.md** | the original rules document, copied unchanged — the long-form reasoning behind the SOP, including how each rule was learned |

## What is here

```
scripts/        every script the pipeline uses (13 files)
config/         JSON and config from three completed jobs, unchanged
  castle-defences/     the most recent and most complete
  weirdest-warships/   a non-combat subject; shows how a palette gets replaced
  deadliest-sword/     the first job; the palette everything else builds on
test/           make_fixture.py + verify.py — runs with no video and no API key
studio.html     browser preview console: cue sheet + video + live faders
```

`config/*/cues.json` are the finished cue sheets — 372 events for the castle job.
`config/*/build_cues.py` are the hand-authored source sheets; copy the nearest one
and rewrite it for a new video. `config/*/palette_manifest.json` holds per-file
anchors, front-load ratios and measured rms for every sound used.

## The three rules that matter most

1. **Anchor the master to the voice, never to a programme target.** The VO
   arrives already mastered; any programme target moves it, because the voice is
   most of the programme. Sum at unity, limit, ship.
2. **Never place a hit you have not seen.** Times come from contact sheets, not
   from the script and not from an animator's note.
3. **The category is not the question, the object is.** A sound can be on the
   right frame at the right level and still be of the wrong thing. That is where
   every round of notes has landed, and it is the one thing measurement cannot
   settle.

## Credentials

No API key is in any file here. `scripts/epidemic_api.py` reads
`EPIDEMIC_SOUND_API_KEY` or `EPIDEMIC_API_KEY` from the environment;
`scripts/epidemic.py` reads `EPIDEMIC_API_KEY`. See RUN.md.

## Not included

Audio assets. The palettes are 240–340 WAV files per job and are fully derived
from the id lists in `config/*/` — `deadliest-sword/rebuild_palette.py`
reproduces 113 files from a 3.7 KB list in about two minutes. The source videos
and voiceovers are not here either.
