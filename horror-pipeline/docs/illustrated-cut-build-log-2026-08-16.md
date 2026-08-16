# The illustrated cut: build log

*The section rebuilt around "what does this line literally show", after the
craft note of 2026-08-09 established that most of the reference's frames are
not creature images at all. Every number here is measured, not estimated.*

---

## What was wrong

Eleven lines of Long Horse, eleven creature pictures. The script names a girl,
a bed, a hallway, a door frame, stairs, music, apples and cinnamon, and none of
them had ever been on screen, because the pipeline could only source canon
creature art.

## The new stage

`tools/illustrate.py` turns a script into an image per named thing. A line
becomes queries through spaCy noun chunks and WordNet concreteness rather than
a keyword list, because a keyword list only matches the script it was written
for and a new script arrives every video.

Three routings run before the concreteness test, each guarding a rule that had
already cost a delivery:

| routing | rule it protects |
|---|---|
| creature nouns to approved canon art, never stock | rule 5, the image may not contradict the line. A stock horse skull has a lower jaw |
| `noun.person` becomes a drawn figure, never a photo | rule 6. A photo of a child has shipped and been pulled |
| "this list" becomes the roster, not a photo of paper | it refers to the video, not to the world |

### Search relevance was the real bottleneck

Ranked by caption text, the sources returned:

| query | what came back |
|---|---|
| crack | crack cocaine, a cracked iPhone screen |
| dark corridor interior | a wallpaper calendar, a museum |
| staircase interior dark | a mosque |
| empty bed dark bedroom night | nothing at all |

CLIP ranks on what the picture shows instead. Pooling three phrasings and
letting CLIP pick the winner turned the bedroom query from 0 usable images into
3, best score 0.374.

### Relevance is not fitness

The contact sheet settled this. A saturated green abstract scored **0.222** as
"crack"; a genuinely perfect dark industrial corridor scored **0.242**. The
higher number was the unusable picture.

So the look is measured on its own axis. Saturation separates stock graphics
from photographs (green abstract 0.968, yellow pictogram sign 0.724, darkest
usable bedroom 0.665). OCR catches calendars, posters and watermarks: on the
first batch it fired on exactly one image, a calendar's date strip, and on
nothing legitimate.

Even then, ten of twenty-seven images were editorially wrong and no automatic
gate could have known: a bright purple front door with a letterbox, a hospital
workshop full of bed frames, rocks in snow, a museum, a cinnamon bun. Those
were rejected by looking, and `illustrate.py approve` records the decision so
nothing downstream can place an unreviewed image.

### The stand-in table was itself a guess

`illustrate.py calibrate` runs every stand-in query and ranks them by what they
actually return. Four return nothing usable and need rewriting:

    corner    -> corridor corner interior    NOTHING FOUND
    danger    -> hazard warning sign         NOTHING FOUND
    news      -> newspaper headline          NOTHING FOUND
    disaster  -> tornado supercell storm     NOTHING FOUND

The best are `dream -> empty bed dark bedroom night` at 0.374 and
`follow -> footprints in snow` at 0.361.

## The assets were the constraint

Three of the five cutouts in use were failed mattes. `cut-head-frontal` had
kept its entire black rectangle; `cut-neck-zigzag` carried an 8,936 pixel scrap
that had been floating in the top third of nearly every rendered frame.

`tools/clean_cutouts.py` drops components below a twentieth of the body's size.
The rule is deliberately not "keep the largest" - that is how the earlier matte
lost both arms. It also reports FILL, the fraction of the cutout's own box that
is opaque: a real creature fills a third to a half, a failed matte fills three
quarters.

Nine images had been approved as cutout-suitable in Stage 1 and only five had
ever been cut. Matting all nine produced **two hero cutouts that were never
being used at all**.

## Scenes with events, not shots

| | reference | previous build | this build |
|---|---|---|---|
| hard cuts per minute | 15.2 | 18.4 | 12.5 |
| longest single hold | 23.1 s | 6.1 s | 12.8 s |
| seconds per on-screen event | - | 5.2 | 1.8 |

This resolves the apparent conflict between the house rule "maximum 4.0 seconds
on one unchanged frame" and a reference that holds a framing for 23 seconds.
The rule governs an unchanged FRAME, not an unchanged framing. Cutting to
satisfy it was the mistake.

A bug found by QC: an element that arrived in one part of a scene was deleted
by the next punch, so a box appeared and then silently vanished, leaving the
white canvas at 1.4% frame change for 4.5 seconds. Carried elements are now
re-declared without replaying their entrance.

## QC, first render to last

| metric | v9 | final | target |
|---|---|---|---|
| dead zones >=4s | 1 | **0** | 0 |
| longest dead zone | 4.5 s | **0.0 s** | <4 s |
| integrated loudness | -21.31 LUFS | **-15.90** | -16 to -14 |
| true peak | -1.80 dBTP | **-1.03** | <-1.0 |
| flat dark frames | 18 | **0** | 0 |
| last 5s black frames | 18 | **0** | 0 |
| motion per 0.5s | 13.9% | 15.4% | >=22% |
| LRA | 4.00 at -21 LUFS | 2.70 | >3.0 |
| keyword pops found | 0 of 9 | **5 of 5** | all |

`qc.py` had a hardcoded `INTENDED_POPS` list belonging to the Sewer Alligator
section, so every other section was OCR-checked against another creature's
captions and reported nine missing pops whatever it rendered. It now reads the
sheet via `--sheet`.

## The two things still failing, and why

**LRA 2.70 against a 3.0 floor.** This is a genuine wall for this voiceover,
not a setting left wrong. Measured frontier: pre-master crest runs about
LRA + 12.4 dB. Linear normalisation requires crest <= (target LUFS - target
true peak). Passing LRA therefore needs LUFS - TP >= 15.4, which at TP -1.0 dB
means -16.4 LUFS, outside the -16..-14 QC window.

Everything else was tried and measured:

- compressing the VO stem cut crest 18.7 -> 14.5 dB and cut pre-master LRA
  3.6 -> 1.6. One for one. Circular.
- trimming SFX by 6, 9 and 12 dB moved pre-master true peak not at all: the
  peaks are the VO's.
- raising the bed made it worse; the bed peaks too (TP 0.0 dBTP at +5 dB).
- trimming isolated plosives on the stem is the best lever, since only 0.10% of
  samples sit within 6 dB of peak. It reaches LRA 2.90 at -15.93 LUFS.

The fix is upstream: a voiceover with a lower crest at the same LRA. No limiter
belongs on the master, and none was added.

**Motion 15.4% against 22%.** Deliberately not chased. Reaching the reference's
26.4% by cutting more is exactly what produced the cut the owner called
machine-made, and he cuts LESS than we do. The honest gap is that his in-frame
events are larger than ours: a screen fills with static, an image multiplies.
Ours are boxes and cutouts arriving.

## Still weak, by looking

- The opening beat is a near-black plate with a small cutout on it and reads as
  nothing. Worst frame in the cut.
- The white canvas beats are empty around their box.
- The title clips the plate on two shots.
