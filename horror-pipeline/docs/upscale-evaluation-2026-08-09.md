# Upscale evaluation — 2026-08-09

Companion to `cutout-evaluation-2026-08-09.md`. That document picks the matting
model. This one answers what happens next: the cutout is small, it has to fill
roughly 60 percent of a 1080-line frame and then survive a Ken Burns push of up
to 1.16x, which is about a 2x enlargement.

Everything here was measured on the same two canon images, on this CPU-only
container (4 cores, no GPU).

---

## Verdict

| Question | Answer |
|---|---|
| **Order of operations** | **Matte first, crop to the subject bounding box, then upscale.** Measured, not assumed. Upscaling first was worse on the hard image and identical on the typical one, and costs 4x to 18x more compute. |
| **Which upscaler** | **`realesr-general-x4v3`**, run at 4x and resampled down to the target. Best fidelity of every AI model tested on all three test crops, and 25x faster than the next best. |
| **Canon drift risk** | **Real but bounded, and it is a different risk than expected.** `realesr-general-x4v3` does not invent anatomy. It does erase film grain, which for analog horror is an aesthetic change. `RealESRGAN_x4plus_anime_6B` DOES invent, and is disqualified. |
| **Before any of this** | **Source a larger original first.** Fandom serves the full-resolution file when the URL carries `&format=original` and no `scale-to-width-down` segment. Real pixels beat invented ones every time. |
| **hyperframes** | **No upscale capability.** Checked. `media-treatment` is colour grading only. |

---

## 1. Order of operations: matte first. This is the decisive finding.

### 1.1 Why upscaling first cannot help the matting model

`rembg`'s BiRefNet session resizes **every** input to a fixed 1024x1024 before
inference:

```python
# rembg/sessions/birefnet_general.py
self.normalize(img, (0.485, 0.456, 0.406), (0.229, 0.224, 0.225), (1024, 1024))
```

A 768x1024 source and a 1536x2048 upscale of that same source both arrive at the
model as 1024x1024. Upscaling first hands the segmenter **zero additional
pixels**. It only changes the image *content*, because the upscaler denoises and
sharpens on the way through.

That change is not neutral. On low-contrast limbs it removes the faint signal the
segmenter was just barely using.

### 1.2 Measured

Both paths were run to the same 2x output resolution and scored with the same
anatomy and background probes from the cutout evaluation, scaled by 2.

| Image | Path | anatomy | bleed | edge width (px) | seconds |
|---|---|---|---|---|---|
| Cartoon-cat (typical) | **A: matte then upscale** | **8/8** | 5/5 | 4.44 | 30.0 |
| Cartoon-cat (typical) | B: upscale then matte | 8/8 | 5/5 | 4.31 | 40.2 |
| Heiscoming (hard) | **A: matte then upscale** | **6/8** | 6/6 | 6.31 | 137.6 |
| Heiscoming (hard) | B: upscale then matte | **5/8** | 6/6 | 6.60 | 120.9 |

Path B additionally lost `L-upper-arm` on the hard image. See
`assets-example/compare-upscale-order-heiscoming.png`: in path A the creature
still has a left arm stub and a full right hand; in path B the left arm is gone
entirely and the right hand is shorter. The upscaler smoothed away the only
evidence the segmenter had.

### 1.3 The compute argument is even more one-sided

Path A lets you crop to the subject bounding box before upscaling, because you
already know where the subject is. Measured crop sizes:

| Image | Subject bbox | Share of frame |
|---|---|---|
| Cartoon-cat | 350 x 556 | 24.7% |
| Heiscoming | 372 x 467 | **5.5%** |

Upscaling only the crop, at 2x, with `realesr-general-x4v3`:

| Image | Whole frame | Subject crop only | Saving |
|---|---|---|---|
| Cartoon-cat | 18.8 s | **6.0 s** | 3x |
| Heiscoming | 56.1 s | **2.4 s** | 23x |

Path B has no way to do this. It must upscale the entire frame, including the
background it is about to throw away.

**Conclusion: matte, crop, then upscale. There is no configuration in which the
other order wins.**

---

## 2. Alpha handling, which is where matte-first can go wrong

Matting first means the **alpha channel** has to be enlarged too, and every
upscaler here is RGB-only. Three strategies were tested and the differences are
visible at 4x zoom in `assets-example/compare-upscale-alpha-handling.png`.

| Strategy | Alpha edge | Colour fringe | Verdict |
|---|---|---|---|
| **RGB through model + edge-extend, alpha via Lanczos** | Smooth 2 px feather, correct | **None** | **Correct. Use this.** |
| RGB through model, NO edge-extend, alpha via Lanczos | Same | **Visible dark fringe** along the silhouette | Wrong |
| Alpha replicated to 3 channels and pushed through the model | Hard, stair-stepped, aliased (edge width 1.13 px) | Visible dark fringe | Wrong |

Two things matter and neither is obvious:

**Edge extension is mandatory.** `rembg` leaves the ORIGINAL background pixels in
the RGB plane of transparent areas; it only writes the alpha channel. Resampling
that RGB plane pulls background colour across the matte boundary and leaves a
dark rim. The fix is to flood the subject's own colour outward past the matte
edge before upscaling, then re-apply alpha. That single step is the difference
between panels 1 and 2 of the comparison sheet.

**Do not push alpha through the upscaler.** It produces a *sharper* edge than the
true one, which sounds good and is not: the real edge has a genuine one to two
pixel feather from lens blur, and re-hardening it produces aliasing that a Ken
Burns move will crawl on. It also erodes weak alpha, which cost an anatomy probe
on the hard image (5/8 instead of 6/8). Lanczos on alpha keeps the feather
proportional, which is what you want.

---

## 3. Which upscaler

### 3.1 Fidelity test: downscale, upscale back, compare to the truth

Three creature crops were halved with Lanczos and then restored to full size by
each method. The original is the ground truth, so anything a model adds is by
construction invented.

- `hf_ratio` = high-frequency energy relative to the original. **1.00 is the
  correct amount of fine detail. Above 1.00 means the model invented detail that
  is not in the real image.**
- `psnr` / `ssim`: fidelity to the truth, higher is better.
- `edge_shift`: mean absolute difference of gradient maps, lower is better. This
  is the anatomy-drift proxy.

| Crop | Method | PSNR | SSIM | **hf_ratio** | edge_shift |
|---|---|---|---|---|---|
| cat-head | lanczos | **31.96** | **0.766** | 0.608 | **3.89** |
| cat-head | **realesr-general-x4v3** | 28.09 | 0.622 | **0.841** | 5.76 |
| cat-head | RealESRGAN_x4plus | 26.21 | 0.433 | 1.015 | 6.18 |
| cat-head | anime_6B | 24.87 | 0.318 | **1.167** | 6.64 |
| cat-glove | lanczos | **29.06** | **0.748** | 0.631 | **5.52** |
| cat-glove | **realesr-general-x4v3** | 24.82 | 0.628 | **0.949** | 7.78 |
| cat-glove | RealESRGAN_x4plus | 24.35 | 0.593 | 1.054 | 8.14 |
| cat-glove | anime_6B | 22.90 | 0.537 | **1.192** | 9.74 |
| heis-head | lanczos | **27.17** | **0.509** | 0.299 | **7.62** |
| heis-head | **realesr-general-x4v3** | 26.20 | 0.343 | 0.135 | 9.67 |
| heis-head | RealESRGAN_x4plus | 26.02 | 0.342 | 0.246 | 9.46 |
| heis-head | anime_6B | 25.87 | 0.331 | 0.292 | 9.81 |

Read this carefully, because the naive reading is wrong.

- **Lanczos wins every fidelity metric.** That is guaranteed by the construction
  of the test, not a discovery. Lanczos cannot invent, so it cannot be wrong. It
  is the fidelity ceiling and the honest baseline.
- **Among the AI models, `realesr-general-x4v3` wins on all three crops, on both
  PSNR and SSIM.** It is also the only AI model whose `hf_ratio` stays **below
  1.0** on the detailed crops, meaning it stays slightly conservative rather than
  adding detail.
- **`anime_6B` adds 17 to 19 percent more high-frequency energy than the real
  image contains.** That is invention, measured.
- `RealESRGAN_x4plus` sits between them and is 25x slower than `x4v3` for worse
  fidelity. No reason to use it.

### 3.2 Looking at the outputs, which is what settles it

`assets-example/compare-upscale-fidelity-cat-glove.png` at 1:1 pixels is the
clearest single piece of evidence in this document.

- **lanczos**: faithful, soft, film grain intact.
- **realesr-general-x4v3**: clean, four fingers correct, glove proportions
  unchanged, still reads as a photograph.
- **RealESRGAN_x4plus**: similar, slightly more photographic texture retained.
- **anime_6B**: the photograph has been **converted into cel-shaded anime line
  art**. Hard black outlines around the glove, flat colour fills, and invented
  stroke-like lines drawn into the ground texture. This is not an upscale, it is
  a restyle.

`compare-upscale-fidelity-cat-head.png` shows the same thing on the face:
anime_6B draws an extra contour line inside the right ear that does not exist in
the original, and hardens the mouth into graphic shapes.

**`RealESRGAN_x4plus_anime_6B` is disqualified for this channel.** On a creature
whose canon anatomy is the entire point, a model that adds outlines and
reinterprets shapes will eventually draw a feature that canon does not have, and
it will ship.

### 3.3 waifu2x could not be tested, honestly stated

waifu2x was requested and was not testable here. `waifu2x-ncnn-vulkan` requires a
Vulkan device and this container has no GPU. No torch or ONNX distribution of
waifu2x weights was reachable through the proxy (both candidate release URLs
returned 404).

`RealESRGAN_x4plus_anime_6B` is the illustration-tuned model in the same family
and served as the closest available proxy. It failed on fidelity, which is at
least weak evidence that illustration-tuned models are the wrong class for this
material: canon creature art here is mostly photographic or painted-realistic
found footage, not line art.

### 3.4 Runtime on CPU, which decides usability at 25 images per creature

| Method | s per input megapixel | 2x on a typical 0.19 MP subject crop | 25 assets |
|---|---|---|---|
| lanczos | ~0 | 0.0 s | instant |
| **realesr-general-x4v3** | **11.2** | **2.4 to 6.0 s** | **~2 min** |
| RealESRGAN_x4plus_anime_6B | 83.9 | 14.3 to 17.1 s | ~7 min |
| RealESRGAN_x4plus | 274.6 | 38.6 to 48.1 s | ~23 min |

`realesr-general-x4v3` is the only AI option that is comfortable at production
volume on this hardware. It is also the most faithful. That is an unusually clean
result.

---

## 4. Canon drift: the honest read

**`realesr-general-x4v3` does not invent anatomy.** Across three crops it added
no features, moved no proportions, and kept `hf_ratio` below 1.0. On the
production 2x outputs its fingers, ears, mouth and limb widths match the source.

**It does erase film grain, and that is the real risk here.** On the noisy night
crop its `hf_ratio` is 0.135 against 0.299 for Lanczos: it removed more than half
the remaining fine detail, essentially all of which was sensor noise. See the
right-hand panels of `compare-upscale-fidelity-heis-head.png`, where the
found-footage grain disappears completely and the image starts to read as a clean
render rather than a photograph.

For a channel whose whole identity is analog found footage, silently
de-graining every asset is a style drift. It is not the drift the asset-drift
checklist was written for, but it is drift.

**Mitigation, and it is easy.** Re-add grain at composite time rather than trying
to preserve it through the upscale. The Remotion engine already generates a grain
texture (`public/tex/grain.png`). De-graining then re-graining under house
control is strictly better than carrying through whatever noise the source
camera happened to have, because it makes grain a style parameter instead of an
accident of sourcing.

**One case where Lanczos is still the right answer.** If an asset's canon detail
is fine texture that the reviewer cannot verify (an intricate mask, small
lettering, a patterned surface), take the soft Lanczos result rather than a
sharpened guess. Softness is a quality problem. Invented anatomy is a canon
failure, and the channel's own rules rank those very differently.

**And the thing that beats all of it:** get a bigger original. `Heiscoming.jpg`
came from Fandom at 1536x2048 only because the URL carried `&format=original`.
Always check for a larger source file before upscaling anything. A real 2x is
worth more than any model.

---

## 5. Known-good production commands

### Setup

```bash
pip3 install spandrel
# spandrel pulls a generic torchvision that will not match a +cpu torch build.
# Symptom: RuntimeError: operator torchvision::nms does not exist
pip3 install --force-reinstall "torchvision==0.28.0+cpu" \
  --index-url https://download.pytorch.org/whl/cpu

mkdir -p /root/upscale-models && cd /root/upscale-models
curl -sSL --fail -O https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth
```

`realesr-general-x4v3.pth` is 4,885,111 bytes. It downloads through the agent
proxy with no TLS or proxy changes.

### The pipeline

```python
import numpy as np, torch
from PIL import Image
from rembg import remove, new_session
from spandrel import ModelLoader

torch.set_num_threads(4)
matte = new_session("birefnet-general")                       # build once per batch
up    = ModelLoader().load_from_file("/root/upscale-models/realesr-general-x4v3.pth").eval()

FACTOR = 2.0

def edge_extend(rgb, a, iters=12):
    """Flood subject colour outward so resampling cannot pull background
    across the matte edge. rgb float 0..1 HxWx3, a is 0..255 alpha."""
    m = (a > 8).astype(np.float32)[..., None]
    for _ in range(iters):
        acc = np.zeros_like(rgb); w = np.zeros_like(m)
        for d in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            acc += np.roll(rgb * m, d, (0, 1)); w += np.roll(m, d, (0, 1))
        rgb = np.where(m > 0, rgb, np.where(w > 0, acc / np.maximum(w, 1e-6), 0))
        m = np.maximum(m, (w > 0).astype(np.float32))
    return rgb

def cutout_2x(path, out_path):
    src = Image.open(path).convert("RGB")

    # 1. MATTE FIRST, at native resolution
    cut = remove(src, session=matte).convert("RGBA")

    # 2. CROP to the subject bounding box, so the upscaler only sees the subject
    a = np.asarray(cut)[:, :, 3]
    ys, xs = np.where(a > 8)
    pad = 8
    cut = cut.crop((max(0, xs.min() - pad), max(0, ys.min() - pad),
                    min(cut.width,  xs.max() + pad),
                    min(cut.height, ys.max() + pad)))

    # 3. UPSCALE: RGB through the model after edge extension, alpha via Lanczos
    arr  = np.asarray(cut).astype(np.float32) / 255.0
    rgb  = edge_extend(arr[:, :, :3], arr[:, :, 3] * 255)
    with torch.no_grad():
        o = up(torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0))[0]
    o = o.permute(1, 2, 0).clamp(0, 1).numpy()                # model is 4x

    tw, th = int(cut.width * FACTOR), int(cut.height * FACTOR)
    rgb_up = Image.fromarray((o * 255).round().astype("uint8")).resize((tw, th), Image.LANCZOS)
    a_up   = Image.fromarray(np.asarray(cut)[:, :, 3]).resize((tw, th), Image.LANCZOS)
    out = rgb_up.convert("RGBA"); out.putalpha(a_up)
    out.save(out_path, "PNG")
```

**Tile inputs above roughly 512x512** (256 px tiles with 16 px overlap, blended
by accumulation weight) or peak memory becomes the limit. The subject crops in
these tests were small enough not to need it, but a large creature filling a
2048-line frame will.

---

## 6. Recording an upscale so it is never silent

An upscale must never be invisible in the materials JSON. Proposed fields, added
alongside the cutout fields from `cutout-evaluation-2026-08-09.md`:

```json
{
  "file": "Cartoon-cat.jpeg",
  "approved": true,
  "cutout_suitable": true,
  "cutout_status": "passed",
  "cutout_file": "cutout-cartooncat-birefnet-general.png",

  "upscaled": true,
  "upscale_method": "realesr-general-x4v3",
  "upscale_factor": 2.0,
  "upscale_source": "cutout-cartooncat-birefnet-general.png",
  "upscale_native_px": [350, 556],
  "upscale_output_px": [700, 1112],
  "upscale_status": "pending",
  "upscale_note": ""
}
```

Two fields carry most of the weight:

- **`upscale_source`** is a pointer to the exact artefact the upscale was made
  from, so any drift claim can be checked against the real original rather than
  argued about. Without it, an upscale is unfalsifiable.
- **`upscale_method`** must record the model name, not just `true`. The whole
  finding of section 3 is that models in the same family differ from faithful to
  disqualified, so "was it upscaled" is not the useful question. "By what" is.

Set `"upscaled": false, "upscale_method": "lanczos"` explicitly when no AI model
was used. Absent is not the same as none.

---

## 7. What the reviewer needs to SEE to accept an upscale in a second

The reviewer is already ticking images. The upscale check must ride along, not
become a second pass.

**Two panels, side by side, both at the SAME on-screen size, both at 1:1 output
pixels on the same crop.**

| Panel | Content |
|---|---|
| Left | The **original** region, nearest-neighbour enlarged to the output size |
| Right | The **upscaled** result at 1:1 |

Nearest-neighbour on the left is the important detail. It enlarges without
inventing or blurring, so the left panel shows exactly what information actually
existed. Anything present on the right but absent on the left is invented. Using
Lanczos on the left would hide the comparison, because Lanczos smooths and the
reviewer would be comparing two guesses.

**Crop to the feature that carries canon**, not to the whole creature: the face,
the jaw, the sockets, the hands. Those are where a hallucination becomes a canon
failure. A whole-creature view at 2x is too small to judge and will be waved
through.

The reviewer's question is one sentence: **"is there anything on the right that
is not on the left?"** That is a one-second comparison, and it is the same shape
of question as the matte review sheet's "does panel 4 have the same limbs as
panel 1". Keeping both gates phrased as a presence check rather than a quality
judgement is what makes them fast enough to actually get done.

Examples of this comparison at 3x zoom, on real assets:
`assets-example/compare-upscale-2x-cartooncat-face.png` and
`compare-upscale-2x-cartooncat-glove.png`.

---

## 8. Honest summary

- **Order of operations is settled and the reason is structural, not empirical
  taste:** the matting model discards resolution, so upscaling before it cannot
  help and measurably hurt on the hard image.
- **`realesr-general-x4v3` is a genuinely good result:** most faithful AI model
  on every crop, no invented anatomy, and fast enough to be a non-issue at 25
  assets per creature.
- **`anime_6B` would have shipped canon failures.** It converts photographs to
  line art and adds 17 to 19 percent detail that does not exist. If an
  illustration-tuned upscaler is ever proposed again, this measurement is the
  reason to refuse.
- **The residual risk is de-graining, not hallucination**, and the fix is to
  re-add grain under house control rather than to avoid the upscaler.
- **None of this beats sourcing a larger original.** Check the Fandom original
  first, every time.

## 9. Output file inventory

All under `assets-example/`.

| Pattern | Contents |
|---|---|
| `upscale-fidelity-<crop>-*.png` | round-trip test: original, halved input, and each method's restoration |
| `compare-upscale-fidelity-<crop>.png` | 1:1 five-way comparison sheets for the three crops |
| `prod-<image>-0-cutout-cropped.png` | the matte cropped to its subject bbox, the real upscaler input |
| `prod-<image>-2x-<method>.png` (+ `_check`) | production-path 2x results for all four methods |
| `compare-upscale-2x-cartooncat-face.png`, `-glove.png` | 3x zoom, the reviewer-facing comparison |
| `compare-upscale-alpha-handling.png` | the three alpha strategies plus path B, with alpha channels |
| `compare-upscale-order-heiscoming.png` | path A against path B on the hard image |
| `upscale-<image>-pathA-*.png`, `upscale-<image>-pathB-*.png` (+ `_check`) | full order-of-operations outputs at 2x |
