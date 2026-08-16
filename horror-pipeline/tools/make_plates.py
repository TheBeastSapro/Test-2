#!/usr/bin/env python3
"""Turn canon photographs into CREATURE-FREE environment plates.

The gap this closes: a creature's wiki gallery contains, by definition, images
of the creature. Stage 1 sources SUBJECTS. But the reference grammar (measured
from M Simplified) composites a creature cutout onto a plate the editor OWNS,
and holds that plate while the creature layer performs. Using a canon
photograph as the plate puts a second creature in frame, so the reveal reveals
nothing and the section shows two of the same monster. That shipped once and it
is what made the first Long Horse render read as amateur.

The canon photographs are still the right source: they carry the real settings
(a half-built suburban street, a disused basement, an institutional corridor, a
flash-lit wood). So: matte the creature, dilate the mask, inpaint it out, and
keep the environment.

  make_plates.py <materials.json> --out DIR [--min-clear 0.86]

Only images the owner APPROVED and marked cutout_suitable=false are used, since
those are the ones already judged to be environments rather than subjects.

Every plate records how much of the frame had to be reconstructed. A plate that
needed a large inpaint is reported and skipped by default, because inpainting a
third of the frame invents scenery, and invented scenery is a canon risk of
exactly the kind this pipeline exists to prevent.
"""
import argparse, json, os, subprocess, sys

import numpy as np
from PIL import Image, ImageFilter


def creature_mask(src, tmp):
    """Alpha from birefnet-general = where the creature is."""
    out = os.path.join(tmp, "m.png")
    r = subprocess.run(["rembg", "i", "-m", "birefnet-general", src, out],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out):
        return None
    a = np.asarray(Image.open(out).convert("RGBA").split()[-1])
    return a


def build_plate(src, dst, min_clear=0.86, feather=9, dilate=14):
    im = Image.open(src).convert("RGB")
    tmp = os.path.dirname(dst)
    a = creature_mask(src, tmp)
    if a is None:
        return None

    covered = float((a > 40).mean())
    # Dilate so the matte's soft edge and any contact shadow go too; a tight
    # mask leaves a halo of creature-coloured pixels that reads as a smear.
    m = Image.fromarray((a > 40).astype(np.uint8) * 255)
    m = m.filter(ImageFilter.MaxFilter(dilate * 2 + 1)).filter(ImageFilter.GaussianBlur(feather))
    mask = (np.asarray(m) > 60).astype(np.uint8) * 255

    # CROP, do not inpaint. Inpainting reconstructs plausible-looking texture and
    # on structured backgrounds it smears into obvious blobs - the first pass
    # produced plates that passed a clear-fraction gate numerically and were
    # visibly unusable. Real pixels beat invented ones, so find the largest
    # 16:9 rectangle that contains NO creature and crop that.
    H, W = mask.shape
    occ = (mask > 0).astype(np.int64)   # int64: uint32 overflows on a large integral image
    ii = occ.cumsum(0).cumsum(1)
    ii = np.pad(ii, ((1, 0), (1, 0)))

    def occupied(x0, y0, x1, y1):
        return int(ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0])

    best = None
    for cw in range(min(W, int(H * 16 / 9)), 240, -40):
        chh = int(round(cw * 9 / 16))
        if chh > H:
            continue
        step = max(20, cw // 12)
        for y0 in range(0, H - chh + 1, step):
            for x0 in range(0, W - cw + 1, step):
                if occupied(x0, y0, x0 + cw, y0 + chh) == 0:
                    best = (x0, y0, cw, chh)
                    break
            if best: break
        if best: break

    if best is None:
        return {"covered": round(covered, 4), "clear": round(1 - covered, 4),
                "usable": False, "why": "no creature-free 16:9 region exists"}

    x0, y0, cw, chh = best
    out = im.crop((x0, y0, x0 + cw, y0 + chh)).resize((1920, 1080), Image.LANCZOS)
    out.save(dst, quality=93)
    frac = (cw * chh) / float(W * H)
    return {"covered": round(covered, 4), "clear": round(1 - covered, 4),
            "crop_frac": round(frac, 3),
            "usable": frac >= 0.16 and cw >= 560,
            "why": f"clean crop {cw}x{chh} = {100*frac:.0f}% of source"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("materials")
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-clear", type=float, default=0.86)
    a = ap.parse_args()

    d = json.load(open(a.materials))
    root = os.path.dirname(os.path.dirname(os.path.abspath(a.materials)))
    os.makedirs(a.out, exist_ok=True)

    made, skipped = [], []
    for i in d["images"]:
        if not i.get("approved") or i.get("cutout_suitable") is not False:
            continue
        src = os.path.join(root, i["file"])
        if not os.path.exists(src):
            continue
        name = os.path.splitext(os.path.basename(i["file"]))[0]
        dst = os.path.join(a.out, f"plate-{name}.jpg")
        r = build_plate(src, dst, a.min_clear)
        if r is None:
            skipped.append((name, "matte failed")); continue
        label = os.path.basename(i.get("wiki_page") or "").replace("File:", "")[:40]
        if not r["usable"]:
            if os.path.exists(dst):
                os.remove(dst)
            skipped.append((label, r.get("why", "unusable")))
            continue
        made.append({"plate": os.path.basename(dst), "from": label,
                     "crop_frac": r.get("crop_frac"),
                     "setting": i.get("setting", ""), "time_of_day": i.get("time_of_day", "")})
        print(f"  OK   {label:42s} {100*r['clear']:5.1f}% clear -> {os.path.basename(dst)}")

    for n, why in skipped:
        print(f"  skip {n:42s} {why}")

    json.dump({"plates": made, "skipped": [{"from": n, "why": w} for n, w in skipped]},
              open(os.path.join(a.out, "plates.json"), "w"), indent=2)
    print(f"\n{len(made)} plates, {len(skipped)} skipped -> {a.out}/plates.json")


if __name__ == "__main__":
    main()
