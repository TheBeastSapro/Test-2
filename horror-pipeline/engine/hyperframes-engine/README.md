# HyperFrames engine — proven reference composition

A working, lint-clean, QC-passing two-shot section in the house style. This is
the smoke test that proves the HyperFrames chain end to end on this machine,
and it is the reference for how a generated section should be shaped.

## Why HyperFrames alongside Remotion

Same paradigm (HTML/CSS/JS composited in headless Chrome, captured per frame),
but it ships the things this pipeline was going to have to build by hand:

| Need | HyperFrames command |
|---|---|
| Cutout a creature to transparent PNG | `hyperframes remove-background` |
| Word-level VO timings | `hyperframes transcribe` |
| Preview with a scrubbable timeline | `hyperframes preview` |
| Validate before rendering | `hyperframes check` |
| Render | `hyperframes render -o out.mp4` |
| Beat / keyframe diagnostics | `hyperframes beats`, `hyperframes keyframes` |

Remotion stays. It is the reference implementation, it has no dependency on a
model-facing CLI, and `engine/ffmpeg-engine/style.py` remains the canonical
statement of the house style.

## Measured result of this composition

Rendered on 4 cores, 180 frames, 23.8s wall clock.

| Metric | Measured | Channel bar | Verdict |
|---|---|---|---|
| Resolution / fps / codec | 1920x1080, 30, h264 yuv420p | 1920x1080 at 30 | pass |
| Video bitrate | **12.48 Mbps** | 10 to 15 Mbps, fails under 1 | pass, untuned |
| Duplicate frames | **0 of 180** | any is a defect | pass |
| Motion, whole frame | 16.7% avg (11.0 min, 35.6 max) | see note | see note |
| Motion, inside content box | **40.5% avg** (26.4 min, 87.6 max) | 22% bar, 25.1% best cut | pass |
| Dead samples under 4% | **0 of 11** | zero runs >= 4s | pass |
| Text contrast | 8/8 checks | WCAG AA | pass |

**Motion note.** Whole-frame motion is not comparable across layouts. A boxed
white-canvas frame puts most of the picture under static white, so it caps low
by construction. Judge a boxed cut on in-box motion. Do not ever raise the
number by adding jitter or grain.

**Bitrate note.** 12.48 Mbps came out of the box with no bitrate flag set. The
ffmpeg engine at `-crf 17` produces 1.89 Mbps on this same content, and the
export that was rejected in QC history was 0.87 Mbps.

## Two traps this composition documents

**1. Vendor every render-time dependency.** The generated starter loads GSAP
from a CDN. `hyperframes check` failed with a 10s navigation timeout until GSAP
was vendored to `public/js/`. Same principle the build packet already applies to
fonts: nothing is fetched at render time, or the render is not deterministic.
`public/js/` is intentionally not committed here — each project vendors its own.

**2. One clip per track index at any instant.** Two clips overlapping in time on
the same `data-track-index` is a hard lint error. The persistent title and its
accent rule both span the whole section, so they need different track indices.

## Craft rules encoded in `index.html`

- Ken Burns is `transform` only, never width/height/left/top. Chrome snaps
  layout to whole device pixels, which emits duplicate frames that measure as
  dead air. The 0-of-180 duplicate count above is that rule proving out.
- Ken Burns runs **linear** (`ease: "none"`). Easing stalls the shot at both
  ends and puts a low-motion window at the head and tail of every shot.
- The image inside the box is oversized so a transform-only move always has
  travel available and never reveals an edge.
- Nothing appears by cutting to it. Title, rule and pops all animate in.
- Palette is white, near-black ink, one red accent. Nothing else.

## Run it

```bash
cd horror-pipeline/engine/hyperframes-engine
curl -sS -o public/js/gsap.min.js https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js
npx hyperframes check
npx hyperframes preview          # scrubbable timeline in a browser
npx hyperframes render -o out.mp4
```

First run on a new machine also needs `npx hyperframes browser ensure`
(downloads a 115 MB Chrome Headless Shell).

## Not yet done

Style is still hardcoded in this file's CSS. It has to read from
`spec/style-profiles.json` before this is more than a reference. That is the
same gap the Remotion engine has.
