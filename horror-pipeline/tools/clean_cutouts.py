#!/usr/bin/env python3
"""Strip stray islands out of a matte before the cutout is ever composited.

A background remover returns whatever it thought was foreground, and on
painted or photographed creature art that includes small disconnected blobs:
a scrap of background wall, a highlight, a piece of a frame. Composited, each
one becomes a little pale rectangle floating beside the creature. One of them
sat in the top third of nearly every frame of a finished render and read as a
rendering bug, which is exactly what it was.

Measured on this project's five cutouts: zigzag carried an 8,936 pixel second
blob, branches a 43,672 pixel one, and stipple two fragments totalling 17.7%
of its alpha.

THE RULE IS NOT "KEEP THE LARGEST". That is how limbs get amputated, and this
build has already shipped a matte with both arms cut off because a global
statistic looked fine. A creature can legitimately be split into pieces by
something crossing in front of it, and those pieces belong to the same figure.
So a component is kept when it overlaps the main body's bounding box, and
dropped only when it sits somewhere else entirely.

  clean_cutouts.py <files...> [--out DIR] [--report]
"""
import argparse, os, sys

import numpy as np
from PIL import Image
from scipy import ndimage


def clean(path, out_path, pad=0.06, min_frac=0.0004):
    im = Image.open(path).convert("RGBA")
    a = np.asarray(im)[:, :, 3]
    m = a > 30
    if not m.any():
        return None
    lab, n = ndimage.label(m)
    if n <= 1:
        im.save(out_path)
        f = float((a > 30).mean())
        return {"blobs": n, "dropped": 0, "dropped_px": 0, "kept_frac": 1.0,
                "fill": round(f, 3), "failed_matte": f > 0.65}

    sizes = ndimage.sum(m, lab, range(1, n + 1))
    main = int(np.argmax(sizes)) + 1
    ys, xs = np.where(lab == main)
    H, W = m.shape
    py, px = int(H * pad), int(W * pad)
    y0, y1 = ys.min() - py, ys.max() + py
    x0, x1 = xs.min() - px, xs.max() + px

    keep = np.zeros(n + 1, bool)
    keep[main] = True
    main_px = float(sizes[main - 1])
    dropped, dropped_px = 0, 0
    for i in range(1, n + 1):
        if i == main:
            continue
        frac = sizes[i - 1] / main_px
        # SIZE decides, not position. The first version of this kept anything
        # overlapping the body's bounding box, which is most of the frame on a
        # creature with a long neck, so the 8,936 pixel scrap that had been
        # floating in every rendered frame survived the clean. A body part that
        # something is standing in front of is a substantial piece of the
        # figure; a matte artefact is a scrap. Below a twentieth of the body it
        # is a scrap.
        if frac >= 0.05 and sizes[i - 1] >= min_frac * m.size:
            cy, cx = np.where(lab == i)
            if cy.max() >= y0 and cy.min() <= y1 and cx.max() >= x0 and cx.min() <= x1:
                keep[i] = True
                continue
        dropped += 1
        dropped_px += int(sizes[i - 1])

    mask = keep[lab]
    arr = np.asarray(im).copy()
    arr[:, :, 3] = np.where(mask, arr[:, :, 3], 0)

    # crop to what is left so the cutout's own box is its subject, which is
    # what the compositor's scale and position are relative to
    ys, xs = np.where(arr[:, :, 3] > 10)
    arr = arr[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    Image.fromarray(arr).save(out_path)
    # FILL is how much of the cutout's own bounding box is opaque. A creature
    # is a thin irregular shape and fills a third to a half of its box. A matte
    # that failed and kept the artwork's dark painted background fills three
    # quarters of it, and composites as a rectangle with a creature inside -
    # which is precisely what two of this project's five original cutouts were
    # doing on screen before anyone looked at them at full size.
    fill = float((arr[:, :, 3] > 30).mean())
    return {"blobs": n, "dropped": dropped, "dropped_px": dropped_px,
            "fill": round(fill, 3), "failed_matte": fill > 0.65,
            "kept_frac": round(float(mask.sum()) / float(m.sum()), 4)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", default=None, help="default: overwrite in place")
    a = ap.parse_args()
    if a.out:
        os.makedirs(a.out, exist_ok=True)
    for f in a.files:
        dst = os.path.join(a.out, os.path.basename(f)) if a.out else f
        r = clean(f, dst)
        if not r:
            print(f"  {os.path.basename(f):28s} EMPTY MATTE")
            continue
        flag = "  MATTE FAILED, kept its background" if r["failed_matte"] else ""
        print(f"  {os.path.basename(f):28s} {r['blobs']:3d} blobs, dropped "
              f"{r['dropped']:2d} ({r.get('dropped_px',0):6d}px), "
              f"fill {r['fill']:.2f}{flag}")


if __name__ == "__main__":
    main()
