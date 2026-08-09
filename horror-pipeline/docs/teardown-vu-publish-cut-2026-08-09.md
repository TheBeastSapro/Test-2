# Teardown: Vu's publish cut

*Measured 2026-08-09 directly from `research/vu/vu-final.mp4`, the finished
publish cut of "Trevor Henderson's Most Aggressive Creatures Explained".
742 MB, 581.74s, 1920x1080 30fps, H.264 9.88 Mbps video, AAC 320k.
Obtained from the Drive link in the chat transcript PDF.*

**Method validation.** Before trusting anything here: re-measuring with the
house method (1 fps, >15 grey levels) returns **26.4% mean change** against the
**26%** recorded in the chat log for this exact video, and **zero** static runs
of 4s or more under 1% change, also matching. The measurement pipeline
reproduces a known-good historical result, so the numbers below are comparable
to this channel's QC history.

---

## 1. The finding that matters most: target the DISTRIBUTION, not the mean

| percentile | change per second |
|---|---|
| p10 | 0.0% |
| p25 | 3.0% |
| **p50 median** | **15.3%** |
| p75 | 42.8% |
| p90 | 74.1% |
| p99 | 97.2% |

mean **26.4%** · median **15.3%** · std dev **28.1%**
**30.8%** of seconds are under 5% change. **26.7%** are over 40%.

Vu's cut is not a video that changes 26% every second. It **holds still about a
third of the time and then changes decisively.** The 26% average is an artefact
of that alternation.

Three consequences for the renderer:

1. **A generator that targets 26% motion is wrong.** It would produce constant
   mid-level drift, hit the average exactly, and look nothing like Vu. That is
   the "edited by an AI" texture the owner rejected on sight.
2. **"Nothing is ever fully static" does not mean "always moving."** The
   reference editor is under 5% change for nearly a third of his runtime. The
   rule is *no frozen shot running past 4 seconds*, not perpetual Ken Burns.
   This resolves the standing conflict between house rule 1 and the motion
   doctrine's ban on idle wobble, with data rather than argument.
3. **The build target is a shape**: ~30% of seconds near-still, ~27%
   high-change, median well below mean. A validator should check the
   distribution, not a single average.

## 2. Audio: the reference cut FAILS the house spec

Measured two independent ways, because this repo's history contains two cases
of an audio fault being asserted without verification.

| metric | Vu's publish cut | house bar | verdict |
|---|---|---|---|
| integrated loudness | **-13.57 LUFS** | -14 to -16 | FAIL, too hot |
| true peak | **-0.17 dBTP** | below -1.0 | FAIL |
| loudness range | **1.70 LU** | above 3.0 | FAIL, worse than the 1.9 that got a cut rejected |

`volumedetect` independently confirms: max volume -0.2 dB, **6 samples pinned
at full scale**, 14 within 1 dB, 268 within 2 dB.

**Why this was never caught.** The same command reports `mean_volume: -16.1 dB`,
and the chat log records this video as "audio is clean at -16 dB". **Mean volume
is not LUFS.** Against a spec written as "-14 to -16", a mean volume of -16.1
reads as perfect while the integrated loudness is -13.57 and the mix is
over-limited. Any historical "audio clean at -16" reading on this channel should
be re-checked, because it may have been measuring the wrong quantity.

**Consequence for the clone brief.** Clone Vu's PICTURE craft, not his audio.
His audio is the one place where the written house spec is right and the best
editor is wrong. Two-pass linear loudnorm at I=-15, TP=-1.5, no limiter beats
his shipped cut on the exact numbers the QC measures.

## 3. Typography: settled by pixel comparison, not taste

**Comic Sans MS Bold.** Candidates rendered against crops of his own title band
at native resolution and rejected: Comic Neue 700 (too light), Patrick Hand,
Kalam, Bangers (condensed all-caps), Baloo 2 800 (right weight, too geometric),
Fredoka 600, Chewy 400 (closest free match). The extracted face matches
letterform for letterform.

Title Case, never uppercase. Fill is **contextual**:

| ground | treatment |
|---|---|
| white canvas | black fill, no stroke |
| scene / plate | white fill, dark stroke, plus an outer white highlight stroke |

The outer highlight was flagged by the owner and confirmed by zooming the title
band 7x on both grounds. `-webkit-text-stroke` draws only one stroke, so the
highlight has to be a stacked layer behind the letterform.

## 4. Known measurement limits

- **Pixel-delta cut detection does not work on white-canvas layouts.** Most
  pixels are identical white across a cut, so shot boundaries are invisible to
  a frame-difference test. BUILD-PACKET 8.1 specifies "hard cuts (frame delta
  > 60%)", which will silently under-report on this channel's content. Cut
  timing must come from the edit sheet, with an explicit caveat printed when no
  sheet is available.
- Shot-length distribution, Ken Burns travel per shot, layer construction, the
  OCR text inventory and SFX sync were NOT measured in this pass. The agent
  assigned to them was terminated by a session limit. They are all measurable
  from the file on disk and remain the highest-value outstanding work.
