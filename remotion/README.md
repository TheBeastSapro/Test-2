# Remotion renderer (optional backend)

A headless-browser renderer for Forgecast motion scenes. It is **opt-in**: ffmpeg
remains the default and this directory can be deleted without breaking anything.

```bash
cd remotion && npm install
forgecast run start --channel 1 --topic "..." --motion-preset my_look \
    --motion-backend remotion
```

If it isn't installed, the backend reports itself unavailable and the run silently
falls back to ffmpeg with a warning. A missing optional renderer should never kill a
run that has already paid for a script and a voiceover.

## ⚠️ Licence — read before you sell anything

**Remotion is not unconditionally free software.** From the
[Remotion licence FAQ](https://www.remotion.dev/docs/license/faq):

- Free for **individuals**, **non-profits**, and **for-profit companies with up to
  three employees** — commercial use included.
- Beyond three employees a paid **per-seat company licence** is required, and the
  obligation begins when you *decide to use it*, not when you ship.
- An Enterprise tier exists with a stated minimum spend.

Everything else in this repository is yours. This directory is the one place a
third-party commercial obligation enters the product, which is why it sits behind
`forgecast/render/backends.py` rather than in the core: if the licence stops suiting
the business, replacing it is one new `RenderBackend` implementation.

[Revideo](https://github.com/midrender/revideo) (MIT) is the drop-in alternative if
that day comes. Its API differs but the scene plan it would consume is the same.

## Why a browser at all

`forgecast/motion/compose.py` animates with ffmpeg expressions. It is fast, it needs
nothing, and it is genuinely limited: `drawtext` has no line breaking, so long copy
must be split by hand in Python; shadows are a displaced dark copy because blurring an
alpha matte is too slow; and every filter that touches frame size fights an animated
`scale`.

A browser brings a layout engine. Text wraps on word boundaries with real font
metrics, shadows are actually blurred, and a card scales and rotates in one transform.

## The contract

`remotion/src/types.ts` mirrors `forgecast/render/scene_plan.py` field for field.
Python owns the plan — it holds the motion presets *learned from reference videos* —
and this project only draws it. Two rules keep the two backends honest:

- **Times in seconds, positions as fractions.** A preset measured from a 24fps
  landscape reference has to drive a 30fps vertical render unchanged.
- **The easing curves in `src/easing.ts` duplicate the Python ones exactly.** Remotion
  has nicer springs. "Nicer" that differs between backends is a bug.

## Files

| | |
|---|---|
| `src/types.ts` | the plan contract, mirroring the Python dataclasses |
| `src/easing.ts` | the five curves, matching `motion/keyframe.py` |
| `src/elements.tsx` | Text, Band, Card — the same vocabulary as `motion/compose.py` |
| `src/MotionScene.tsx` | background bed plus timed elements |
| `src/Root.tsx` | the composition; size and duration come from the plan |

## Preview

```bash
cd remotion && npm run studio
```

Remotion Studio scrubs a composition interactively — the fastest way to see what a
learned preset actually looks like before spending a render on it.
