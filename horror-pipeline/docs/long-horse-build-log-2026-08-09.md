# Long Horse section: build log and QC

*Section 7 of "Trevor Henderson Monsters You CANNOT Survive", built end to end
from the v4 script. Four renders, each measured against Vu's publish cut.*

## Final QC

| metric | this cut | Vu's publish cut | house bar | verdict |
|---|---|---|---|---|
| motion mean | 28.8% | 26.4% | >= 22% | PASS |
| motion median | 16.7% | 15.3% | - | - |
| std dev | 31.1 | 28.1 | - | - |
| seconds under 5% | 23.0% | 30.8% | - | - |
| seconds over 40% | 24.6% | 26.7% | - | - |
| static runs >= 4s | 0 | 0 | 0 | PASS |
| integrated loudness | -15.22 | **-13.57** | -14 to -16 | PASS (Vu FAILS) |
| true peak | -1.47 | **-0.17** | below -1.0 | PASS (Vu FAILS) |
| loudness range | **2.80** | 1.70 | above 3.0 | FAIL (Vu worse) |
| video bitrate | 10.1 Mbps | 9.9 Mbps | 10-15 | PASS |

Five of six pass. On the two audio metrics the reference editor's own shipped
cut fails, this one passes.

## The one failure, diagnosed to physics rather than left as a number

LRA 2.80 against a bar of 3.0.

The raw mix measures I -24.72, TP -6.51, **crest factor 18.2 dB**. Reaching
-15 LUFS with a true peak under -1.5 therefore needs about 4.7 dB of peak
reduction, and that reduction costs roughly 0.8 LU of range. Raw LRA is 3.40;
mastered it lands at 2.80.

The crest factor is inherited from the voiceover, which measures **22.5 dB**
on its own. That is a property of this Kokoro TTS render, not of the mix. A
human-recorded VO or a better TTS render sits around 14-16 dB and clears all
three targets without any peak control at all.

Things that were tried and did not fix it, recorded so they are not retried:
- A broadband 1.6:1 VO compressor (the build packet's chain) makes it WORSE:
  pre-master LRA 2.90 with it, 4.10 without. Removing it is a straight win.
- Peak-shaping the VO trades directly against range: threshold -9 gives crest
  21.3 / LRA 3.50, threshold -15 gives crest 17.7 / LRA 2.30. Compressing
  toward the crest target destroys the range you are trying to protect.
- Targeting -16 instead of -15 changes nothing meaningful (2.70 vs 2.60).

**The fix is upstream: regenerate the voiceover.** No mastering chain recovers
range that the source never had.

## What each render taught

|  | mean | median | std | under 5% | over 40% | what was wrong |
|---|---|---|---|---|---|---|
| v1 | 13.0 | 8.4 | 17.3 | 31.1 | 4.9 | 4 shots. A slideshow |
| v2 | 31.1 | 18.6 | 27.9 | **1.6** | 24.6 | cuts added, stillness destroyed |
| v3 | 27.6 | 16.0 | 30.2 | 21.3 | 24.6 | held shots restored |
| v4 | 27.6 | 16.3 | 30.9 | 23.0 | 24.6 | art shots, subjects in the opening |
| v5 | - | - | - | - | - | icons added, but at ~10% frame height they read as specks |
| v6 | - | - | - | - | - | icons scaled 2.2-3.4x; label collisions cleared |
| v7 | 28.0 | 16.3 | 30.7 | 23.0 | 24.6 | red X moved to the beat it actually means |
| v8 | 28.8 | 16.7 | 31.1 | 23.0 | 24.6 | cold open rebuilt: creature on frame one |
| Vu | 26.4 | 15.3 | 28.1 | 30.8 | 26.7 | |

## The cold open

v7 still opened on 2.5 seconds of empty wood plate. House rule is first fact at
0:01, and the chat log is blunt that the hook IS the retention document: a 14
second static opening was measured at 0-3% frame change and modelled to cost
45-55% of viewers by 0:30.

v8 opens full-frame on the creature artwork, pushing out rather than in so it
reads as an arrival, then cuts to the red X crossing out the threat on "cannot
hurt you", a white-canvas beat on "not good news", the basement approach with a
stick figure that appears and then reacts, a deliberately held beat, and the
reveal at 15s with the figure carrying scale.

## Still open

- **seconds under 5%: 23.0 against Vu's 30.8.** More of the runtime should sit
  genuinely still. Adding held shots is the lever and it is cheap.
- **LRA 2.80.** Upstream VO problem, diagnosed above.
- **The sheet bakes resolved times.** Anchors were resolved once and the seconds
  written into the sheet, which is exactly what the build packet says never to
  do. A VO regen currently means re-authoring the sheet rather than re-running
  the resolver. This is the next structural fix and it is what makes the
  section survive a pickup.

v2 is the instructive one. Adding cuts alone hit the change target and
collapsed stillness to 1.6%, which is idle wobble arriving from the opposite
direction. The reference has BOTH a third of its runtime nearly still and a
quarter of it exploding, so the generator needs explicitly HELD shots where the
image does not move and only a pop animates over it.

## Faults found by looking, not by measuring

Every one of these passed the numeric checks:

1. **The plates contained the creature.** Canon photographs of Long Horse,
   darkened and used as backgrounds, so every scene had two of the same
   monster and every reveal revealed nothing.
2. **The design lock had two heads.** Its own recorded description says
   "TWO heads face each other across the centre of the frame". The cutout kept
   both. Chosen from a thumbnail; caught only at zoom.
3. **Inpainted plates smeared.** cv2 TELEA passed a clear-fraction gate and
   produced visible blobs. Replaced with largest-clean-crop: real pixels.
4. **A cutout kept a hard rectangular black edge.** Claimed it would read as
   shadow on a dark plate. It read as a sticker.
5. **Pops ran through the persistent title.**

Rule that came out of it: look at the contact sheet of your own output the way
you look at a competitor's, before shipping it, not after being told.

## Asset roles

Sourcing produces SUBJECTS. The reference grammar also needs PLATES, and those
cannot come from a creature's own wiki gallery by definition. `make_plates.py`
closes that gap. A third role emerged during the build: images whose subject is
genuinely fused to a near-black ground cannot be matted at all, and belong as
**full-frame art shots**, which is what the reference does with a finished
artwork anyway.
