# Cutout (background removal) evaluation — 2026-08-09

Supersedes section 2 of `toolchain-status-2026-08-09.md`, which marked cutout
extraction PARTIAL. This document ranks 19 configurations across 11 models on
two real canon creature images, using a per-region test rather than global alpha
statistics.

Companion document: `upscale-evaluation-2026-08-09.md` covers what happens to the
cutout afterwards (upscaling for compositing). Read both before wiring the
source-image-to-production-cutout chain.

**Verdict: SOLVED for typical creature art. NOT solved for degraded
found-footage-style photographs, and that class of image should not be cut out
at all.**

Winner: **rembg `birefnet-general`**. On the representative test image it passes
every anatomy probe and every background probe with a clean edge. The runner-up
methods and the two previously-tried methods all fail measurably.

---

## 1. Test corpus, and which image is which

The single most important framing point in this document: **the two test images
are not equivalent, and pooling them produces a misleading ranking.**

| Image | Size | Class | Why |
|---|---|---|---|
| `public/Cartoon-cat.jpeg` | 768x1024 | **TYPICAL** | Creature is large in frame, reads as a distinct dark silhouette with white gloved hands, background is a wall and ground at a different depth. This is what most canon creature art looks like. |
| `public/Heiscoming.jpg` | 1536x2048 | **PATHOLOGICAL** | Very dark, heavily motion-blurred night photograph. The creature occupies about 1.1 percent of the frame. Its left arm is a thin dark limb crossing a blown-out streetlight, at roughly the same luminance as the glare behind it. |

`Heiscoming.jpg` is a worst case and is labelled as such throughout. It is used
to find failure modes, not to pick the winner. Ranking on it alone would have
selected a method that is visibly worse on real work (see SAM, section 5).

**`Heiscoming.jpg` should probably never be cut out at all.** See section 8.

---

## 2. Why the previous ranking was wrong

The earlier evaluation ranked on global alpha percentages: share of fully
transparent, fully opaque and soft-edge pixels. That earlier doc already noted
this was insufficient. It is worse than insufficient, it is actively inverted:

- **Amputation** (losing a limb) raises the transparent percentage and tightens
  the alpha bounding box. Both read as "clean".
- **Bleed** (fusing background onto the subject) lowers the transparent
  percentage. That reads as "dirty".

So the method that deletes the subject scores best. That is exactly what
happened: `u2net_human_seg` posted the best global numbers (97.84 percent
transparent) while having removed both arms.

A global metric also cannot see an **enclosed** background region. The gap
between the creature's legs on `Heiscoming.jpg` is 22 pixels wide and fully
surrounded by subject. `u2net_human_seg` fills 52.9 percent of it and rembg
`u2net` fills 100 percent of it. Neither shows up in any aggregate number.

---

## 3. How quality was actually judged

### 3.1 Anatomy and background probes

Small boxes were placed on each source image, each one read off a gridded,
contrast-stretched crop and **confirmed by eye before any model was run**. The
probe overlays are saved so the placement can be re-checked:

- 8 anatomy probes and 6 background probes on `Heiscoming.jpg`
- 8 anatomy probes and 5 background probes on `Cartoon-cat.jpeg`

Anatomy probes sit on: ears, head, torso, each upper arm, each extremity, each
lower leg. Background probes sit on: sky, lit building, trees, road, and
critically **the enclosed gap between the legs** plus a lit road region directly
beside the subject.

- **Anatomy PASS** = at least 20 percent of the tightly-drawn box has alpha > 25
  **and** the box contains at least one pixel with alpha >= 128.
- **Bleed PASS** = under 2 percent of the box has alpha > 25.

### 3.2 Edge quality

`edge tight` = the share of genuinely partial-alpha pixels lying within 3 pixels
of the hard silhouette boundary. High means a crisp, correctly feathered edge.
Low means a diffuse halo or ghost spread across the frame.

### 3.3 Islands

Connected-component count. Anything not attached to the largest component is
debris that will composite as floating specks. This metric was added
specifically because SAM passed every region test while producing two stray
fragments.

### 3.4 Eyes on the image

Every candidate was composited onto magenta and looked at. This changed the
outcome. SAM scores best of all methods on the pathological image by the numbers
(7/8 anatomy, 6/6 bleed) and is visibly unusable.

---

## 4. Ranked results

Anatomy and bleed are shown as passes/total. "edge tight" and "stray" are from
the typical image.

| Rank | Method | TYPICAL anat | TYPICAL bleed | edge tight | stray | HARD anat | HARD bleed | Verdict |
|---|---|---|---|---|---|---|---|---|
| **1** | **`birefnet-general`** | **8/8** | **5/5** | **98.9%** | **0** | 6/8 | **6/6** | **Production ready** |
| 2 | `birefnet-general` + 2-pass crop | 8/8 | 5/5 | 99.9% | 0 | 5/8 | 6/6 | Marginally crisper on typical, worse on hard |
| 3 | `bria-rmbg` | 8/8 | 5/5 | 98.5% | 0 | 4/8 | 6/6 | Equal on typical, worst limb retention on hard. Licence check needed |
| 4 | `birefnet-dis` | 8/8 | 4/5 | 99.6% | 0 | 5/8 | 6/6 | Bleeds onto the right building |
| 5 | `birefnet-general-lite` | 7/8 | 5/5 | 99.7% | 0 | 5/8 | 6/6 | Loses a limb tip on the typical image |
| 6 | `birefnet-massive` | 8/8 | 4/5 | 79.7% | 0 | 5/8 | 6/6 | Bleeds, softer edge. Bigger is not better |
| 7 | `birefnet-general` + alpha matting | 8/8 | 5/5 | 76.0% | 0 | 5/8 | 6/6 | Alpha matting actively degrades a good matte |
| 8 | `sam` with box + point prompts | 8/8 | 4/5 | 0.0% | 2 | **7/8** | 6/6 | **Numerically best on hard, visually unusable** |
| 9 | `isnet-general-use` | 8/8 | 4/5 | 29.4% | 9 | 6/8 | 4/6 | Ghost matte, 9 stray islands |
| 10 | `u2net` (plain) | 8/8 | 3/5 | 14.9% | 0 | 8/8 | 3/6 | Keeps everything including the building |
| 11 | `silueta` | 8/8 | 3/5 | 17.6% | 0 | 8/8 | 3/6 | Same failure as `u2net` |
| 12 | `u2netp` | 8/8 | 3/5 | 15.0% | 2 | 5/8 | 3/6 | Worse on both axes |
| 13 | `cv2.grabCut` (box seeded) | 5/8 | 5/5 | 0.0% | 5 | 6/8 | 3/6 | Drops the head and torso. Unusable |
| 14 | `isnet-anime` | 0/8 | 5/5 | 22.2% | n/a | 0/8 | 6/6 | Total failure, empty mask |

### Previously-tried methods, re-measured with the same probes

| Method | TYPICAL anat | TYPICAL bleed | edge tight | HARD anat | HARD bleed |
|---|---|---|---|---|---|
| HyperFrames `remove-background` (`u2net_human_seg`, locked) | 6/8 | 5/5 | 25.8% | 4/8 | 5/6 |
| rembg `u2net` + alpha matting 240/20/erode 8 | 8/8 | 4/5 | 32.0% | 7/8 | 3/6 |

**The important new finding about the previously-recommended tool:**
`u2net_human_seg` amputates on the TYPICAL image too, not only the hard one. It
loses the right hand and the right limb of the cartoon cat entirely, and
everything on that side of the creature dissolves into a translucent smear. The
earlier conclusion that it produces "the cleanest matte" was an artefact of
global statistics. It should not be the default.

### Exact limb extents on the hard image (pixels, full resolution)

Source ground truth measured from a high-pass darkness map of the original.

| | left arm reaches | right arm reaches | legs reach down to |
|---|---|---|---|
| **Source** | x = 490 | x ~ 950 | y = 1053 |
| `birefnet-general` | x = 605 (about 30% of the arm) | x = 945 (full) | y = 946 |
| `u2net_human_seg` | x = 638 (about 10%) | x = 762 (amputated at shoulder) | y = 1090 |
| rembg `u2net` + AM | x = 438 (overshoots into background) | x = 828 (hand lost) | y = 1067 |

---

## 5. What the pictures show

Saved comparison sheets, all in `assets-example/`:

| File | Shows |
|---|---|
| `compare-cartooncat-all-models.png` | 6 methods on the typical image |
| `compare-cartooncat-vs-prior-methods.png` | winner against the two previously-tried methods |
| `compare-heiscoming-all-models.png` | 8 methods on the pathological image |
| `compare-heiscoming-winner-vs-sam.png` | why SAM's good numbers are wrong |

**`birefnet-general` on the typical image.** Complete creature: both ears with
the hollow inner ear resolved, open mouth, all four spindly limbs, both white
gloves with individual fingers, and the small rear limb. Edge is crisp with a
one-pixel feather. No background anywhere.

**`u2net_human_seg` on the typical image.** The left half is fine. The right half
of the creature fades into a translucent purple smear; the right glove is gone
and the right limb is a ghost. This is an amputation, not a soft edge.

**rembg `u2net` + alpha matting on the typical image.** All anatomy present, but
a slab of building wall and grass is fused to the subject and the silhouette
edge is chewed and moth-eaten from the erode step.

**SAM on the pathological image.** Recovers a left "arm" that is a thick lumpy
wedge of lit background rather than a thin limb, fuses a bright white streetlight
sliver into the torso, leaves two floating fragments in mid-air, and produces a
completely binary mask (0 soft pixels) that will alias visibly when composited
and scaled. It passes 7/8 anatomy probes. **This is the case that proves the
numeric test cannot be the last word.**

**grabCut.** Its colour model treats the dark creature as background. It keeps
the lit building and drops the head and torso.

---

## 6. The winner: exact known-good commands

Environment: `rembg 2.0.78`, `onnxruntime 1.28.0`, Python 3.11, CPU only.
Model `birefnet-general` is BiRefNet trained for general dichotomous image
segmentation.

### One-time setup

```bash
pip3 install "rembg[cpu]"
# the rembg CLI ships with unlisted imports; without these `rembg` will not start
pip3 install filetype watchdog asyncer aiohttp gradio
```

First run downloads `BiRefNet-general-epoch_244.onnx` (972,666,916 bytes, 927 MiB)
from GitHub releases to `/root/.u2net/birefnet-general.onnx`. The download
succeeds through the agent proxy. No TLS or proxy change is needed.

### The command

```bash
rembg i -m birefnet-general INPUT.jpg OUTPUT.png
```

That is the whole thing. No alpha matting, no post-processing, no flags.

Verified: the CLI output is **bit-identical** to the Python API path below
(`np.array_equal` is True), so either form is safe.

### Python form, for batching

```python
from PIL import Image
from rembg import remove, new_session

sess = new_session("birefnet-general")          # build ONCE, reuse for the batch
src = Image.open("INPUT.jpg").convert("RGB")
out = remove(src, session=sess).convert("RGBA")  # no alpha_matting, no post_process
out.save("OUTPUT.png", "PNG")
```

### Measured cost on this container (4 cores, no GPU)

| Step | Cost |
|---|---|
| `import rembg` (warm module cache) | 1.5 s |
| `new_session("birefnet-general")`, model cached on disk | 11.7 s (pay once per batch) |
| Inference, 768x1024 | 17.8 to 19.1 s |
| Inference, 1536x2048 | 32.7 to 58.9 s |
| CLI end to end, single 768x1024 image, cold process | 49.5 s |
| One-time model download | 973 MB, about 40 s |

**Always reuse the session across a batch.** Per-image CLI invocation pays the
11.7 s session build plus process start every time. For 25 images that is roughly
7 minutes of pure overhead.

---

## 7. The winner's remaining failure modes

Stated plainly. None of these are fixable by configuration; all were tested.

1. **Thin, low-contrast extremities against a bright background are lost.** On
   `Heiscoming.jpg` the left arm is recovered to only about 30 percent of its
   length. The arm crosses a blown-out streetlight and sits at nearly the same
   luminance as the glare.

2. **Silhouette extremities that fade into darkness get truncated early.** The
   legs stop at y=946 where the source has them to y=1053, an 11 percent
   shortfall on leg length, and the cut is abrupt rather than tapered.

3. **Near-opaque, not fully opaque.** BiRefNet sessions in rembg min-max
   normalise the prediction, so the subject interior lands at alpha 254 rather
   than 255. Harmless for compositing, but any acceptance check written as
   `alpha == 255` will report 0.02 percent opaque and look like a failure. Test
   `alpha >= 250`.

4. **Slowest of the tested models**, roughly 20x `u2netp`. Acceptable at 25
   images per creature, not acceptable for video frames.

5. **Not deterministic across model variants.** `birefnet-massive` and
   `birefnet-dis` are *worse* despite being larger or newer. Do not swap the
   model without re-running the probe test.

### Things that were tried and did NOT help

Recorded so they are not tried again.

| Attempt | Result |
|---|---|
| Alpha matting (`-a`, 240/10/erode 10) | Made it **worse**. Edge tightness fell from 98.9% to 76.0% and it introduced a visible fuzzy fringe. Alpha matting fixes the u2net "fused slab" problem by eroding it, but on an already-clean BiRefNet matte there is nothing to erode and it only adds halo. |
| Two-pass crop refinement (run once, crop to the found bbox at native resolution, run again) | Helped slightly on the typical image (edge 98.9% to 99.9%). **Hurt on the hard image**: the crop is seeded from pass 1's own bounding box, so a pass that already amputated a limb crops the limb out of pass 2 entirely. Structural flaw in the technique. |
| Two-pass crop with a 35 percent pad, so an amputated pass 1 still contains the limbs | Still lost the left arm. Confirms the loss is a model limitation, not a resolution limitation. |
| Gamma lift (0.5) on the pixels fed to the model, original RGB preserved on output | No improvement on either image. |
| SAM with box + 4 positive point prompts | Best anatomy numbers on the hard image, visually unusable: binary mask, no soft edge, fused background wedge, stray islands. |
| `cv2.grabCut` seeded with a bounding box | Fails on dark subjects. Drops head and torso. |
| `isnet-anime` on cartoon-style creature art | Total failure, produced an effectively empty mask on both images. |

### Licence note

`bria-rmbg` matched the winner on the typical image. BRIA RMBG weights are
distributed under a licence that restricts commercial use without an agreement.
This channel is monetised. **Confirm the licence before using `bria-rmbg` in
production.** BiRefNet is MIT licensed, which is why it is the recommendation
even where the two are tied.

---

## 8. Production recommendation

### 8.1 Not every canon image is a cutout candidate

This is the most useful finding in the evaluation and it is not about tooling.

`Heiscoming.jpg` cannot be cleanly separated from its scene by any method
tested, including a human-prompted one, because the creature's left arm is
genuinely not distinguishable from the streetlight glare behind it. No model
choice will fix that. The image is still excellent material, it just wants to be
used **boxed or full-bleed as an atmospheric found-footage plate**, not cut out.

**Decision rule, judgeable in a few seconds per image.** An image is a cutout
candidate only if all four hold:

1. **Subject-to-background separation.** The creature reads as a distinct shape
   against its background at a glance, at thumbnail size. If you have to look for
   the edge, the model will not find it either.
2. **No heavy motion blur on the silhouette.** Blur inside the body is fine.
   Blur that smears the outline into the background is disqualifying.
3. **Extremities are not crossing a bright or busy region.** Thin limbs over
   lens flare, streetlights, foliage or lit windows are where every model fails.
   Thin limbs over flat sky or flat dark are fine.
4. **The creature is not occluded.** Anything passing in front of it produces a
   matte with a bite out of it that reads as damage rather than occlusion.

A practical proxy for rule 1 that can be computed without a model: the creature
occupying under about 2 percent of the frame is a strong warning sign.
`Heiscoming.jpg` is 1.1 percent; `Cartoon-cat.jpeg` is 9.0 percent.

### 8.2 Yes, record `cutout_suitable` in the materials JSON

Agreed, and it should be set during the **same human approval pass that approves
the image**, not later. It is a property of the source image, the reviewer is
already looking at the image, and deciding it later means re-opening every asset.

Suggested shape:

```json
{
  "file": "Cartoon-cat.jpeg",
  "approved": true,
  "cutout_suitable": true,
  "cutout_note": "",
  "cutout_status": "pending"
}
```

```json
{
  "file": "Heiscoming.jpeg",
  "approved": true,
  "cutout_suitable": false,
  "cutout_note": "left arm not separable from streetlight glare; use boxed or bled",
  "cutout_status": "n/a"
}
```

`cutout_suitable` is the reviewer's up-front judgement on the source.
`cutout_status` is the outcome of the actual matte (`pending` / `passed` /
`failed`). Keeping them separate matters, because "we never tried" and "we tried
and it failed" call for different actions.

**What the reviewer needs to see to set `cutout_suitable` in about a second:**
the source image with a **1-bit silhouette preview beside it**. Threshold the
image and show the resulting blob. If the blob looks like the creature, it is a
candidate; if the blob is a smear that includes the building, it is not. That
takes no model and is instant to compute. The reviewer is answering "is this
shape findable", not "is this shape correct".

### 8.3 Cutouts must pass a human approval gate. Yes.

Agreed, and the evaluation supports it strongly rather than as a precaution.
Three independent findings force it:

- The best global statistics belonged to the worst matte.
- The best region-test score on the hard image belonged to a visibly unusable
  matte.
- The previously-recommended tool amputates on ordinary images, not just the
  hard one, and that went unnoticed through a full evaluation cycle.

An automated gate can catch gross failures. It cannot catch "the arm is 30
percent of its length" without knowing where the arm is, and that knowledge came
from a human looking at a gridded crop.

**What the reviewer needs to SEE.** Four panels, one row, judgeable in about a
second. Generated examples are saved as
`assets-example/review-sheet-cartooncat-birefnet-general.png` and
`assets-example/review-sheet-heiscoming-birefnet-general.png`.

| Panel | Content | Catches |
|---|---|---|
| 1 | Source, gamma lifted to 0.45 | What anatomy is actually there. Without this the reviewer cannot know a limb is missing. The lift is essential; on unlifted dark horror art the arms are invisible on a normal monitor. |
| 2 | Cutout on **magenta** | Amputation. Magenta appears nowhere in this material, so any hole reads instantly. |
| 3 | Cutout on a **white / black split field** | Halo and fringe. A light halo is invisible on white and obvious on black; a dark fringe is the reverse. One panel catches both. |
| 4 | The **alpha channel alone** | Stray islands, soft slop, and whether the silhouette is a creature or a blob. This is the panel that exposed SAM. |

The reviewer's question is not "does this look good", it is **"does panel 4's
silhouette have the same limbs as panel 1"**. That is a one-second comparison.

Run the automated probe check first and put its verdict on the sheet, so the
reviewer is confirming rather than searching. Machine screen, human decide.

### 8.4 A failed matte blocks the cutout treatment, not the image

Agreed with your instinct. The image and the matte are separate artefacts and a
bad matte says nothing about the image.

- `approved: true` + `cutout_suitable: false` is a completely normal, useful
  state. The image goes into the shot list as a boxed or bled plate.
- Only `approved: false` removes the image from the video.
- A failed matte sets `cutout_status: "failed"` and should also flip
  `cutout_suitable` to false with a note, so nothing retries it every run.

Given the competitor finding that the distinction that matters in this niche is
"boxed versus bled" rather than "standalone versus composited", losing the cutout
treatment on an image costs very little. Losing the image would cost a lot more.

### 8.5 Recommended pipeline

1. Human approves the image and sets `cutout_suitable` from the source plus the
   silhouette preview.
2. If suitable, run `rembg i -m birefnet-general`, batching with a reused
   session.
3. Run the automated probe check: subject area between 0.5 and 60 percent, zero
   stray components above 50 px, edge tightness above 60 percent, and no alpha in
   the frame's four corners.
4. Generate the 4-panel review sheet with the automated verdict stamped on it.
5. Human accepts or rejects. Rejection sets `cutout_status: "failed"` and
   `cutout_suitable: false` with a note; the image stays approved for boxed or
   bled use.
6. Feed the accepted cutout into the upscale step. See
   `upscale-evaluation-2026-08-09.md`.

**Do not run this unattended.** Not because the model is unreliable in general,
but because its one failure mode is silent limb loss, and silent limb loss on a
creature whose limbs are the whole point is exactly the class of defect the
channel's asset-drift checklist exists to catch.

---

## 9. Honest summary

- **Typical creature art: solved.** `birefnet-general` produced a
  production-quality matte on the representative image with 8/8 anatomy, 5/5
  background and a 98.9 percent tight edge, and it did so with a single flag on a
  single command. Nothing about the result needs an apology.
- **Degraded found-footage photographs: not solved, and not solvable.** The
  correct response is admission control, not a better model. That is a genuine
  negative result and it should be treated as a pipeline rule, not a to-do.
- **The previously-recommended default was wrong** and would have shipped
  amputated creatures on ordinary images. That is the most important correction
  in this document.

## 10. Output file inventory

All under `assets-example/`. Every cutout has a matching `_check.png` composited
on magenta.

- `cutout-cartooncat-*.png` and `cutout-heiscoming-*.png` for all 17 tested
  configurations plus the two prior methods
- `compare-*.png`, four comparison sheets
- `review-sheet-*.png`, two examples of the human approval sheet
- `cutout-hyperframes.png`, `cutout-rembg.png`, `cutout-test.png` retained from
  the earlier evaluation, now with `_check.png` composites added
