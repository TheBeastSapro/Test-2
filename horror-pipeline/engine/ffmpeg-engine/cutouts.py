"""Procedural ANIMATIC CUTOUTS — PNGs with real alpha, for the layered-cutout
scene language (M Simplified / Ficknime reference: one background, a creature
cutout that rises from behind a foreground element, props stacking in).

These stand in for approved canon art exactly like plates.py does. Each cutout
is tagged with a slot number the same way plates are: cutNN_<name>.png, and the
slot number is surfaced in the on-screen animatic SlotTag line.

House look for a placeholder cutout: DARK, slightly noisy, soft-edged. It must
read as a silhouette that a real painted asset will later replace — never as
finished art.
"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# slot registry — index = slot number. Kept here so export_cutouts.py and the
# TS side agree on names without a second source of truth.
SLOTS = [
    ("creature_tall",  (1180, 1500)),   # cut01 — the sewer spider, tall/irregular
    ("creature_small", (980, 620)),     # cut02 — smaller crawler (the "alligator")
    ("car",            (1280, 560)),    # cut03 — car, side profile
    ("treeline",       (1920, 460)),    # cut04 — treeline strip, foreground slot
    ("manhole_rim",    (1500, 480)),    # cut05 — manhole rim, foreground slot
    ("figure",         (400, 940)),     # cut06 — stick figure, human scale ref
]


def _noise(w, h, seed, octaves=(3, 9, 24, 60)):
    rng = np.random.default_rng(seed)
    acc = np.zeros((h, w), np.float32)
    amp = 1.0
    for o in octaves:
        small = rng.random((max(2, h // o), max(2, w // o))).astype(np.float32)
        up = np.array(Image.fromarray((small * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC),
                      np.float32) / 255.0
        acc += up * amp
        amp *= 0.55
    acc -= acc.min()
    acc /= max(acc.max(), 1e-6)
    return acc


def _seg_leg(d, x0, y0, joints, width, jitter, rng):
    """A leg with THREE bends (the script's 'three separate joints'), tapering."""
    pts = [(x0, y0)]
    x, y = x0, y0
    for i, (dx, dy) in enumerate(joints):
        x += dx + rng.normal(0, jitter)
        y += dy + rng.normal(0, jitter)
        pts.append((x, y))
    for i in range(len(pts) - 1):
        w = max(3, int(width * (1.0 - 0.62 * i / max(1, len(pts) - 2))))
        d.line([pts[i], pts[i + 1]], fill=255, width=w)
        d.ellipse([pts[i + 1][0] - w / 2, pts[i + 1][1] - w / 2,
                   pts[i + 1][0] + w / 2, pts[i + 1][1] + w / 2], fill=255)
    return pts[-1]


def _mask_creature_tall(w, h, seed):
    rng = np.random.default_rng(seed)
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    cx, cy = w * 0.5, h * 0.62
    # eight long legs FIRST (they sit under the body), three bends each, splayed
    # wide and asymmetric so the silhouette is irregular rather than symmetrical.
    for i in range(8):
        side = -1 if i % 2 == 0 else 1
        k = i // 2
        reach = (0.16 + 0.13 * k) * w * side
        up = -h * (0.30 + 0.07 * k)
        joints = [(reach * 0.70, up),                       # shoulder -> high knee
                  (reach * 0.62, h * (0.16 + 0.04 * k)),    # knee -> mid joint
                  (reach * 0.34, h * (0.30 - 0.02 * k))]    # mid -> foot
        _seg_leg(d, cx + side * w * 0.06, cy - h * 0.02, joints,
                 width=int(h * 0.052), jitter=h * 0.016, rng=rng)
    # bulbous body + head, drawn over the leg roots
    bw, bh = w * 0.24, h * 0.15
    d.ellipse([cx - bw, cy - bh, cx + bw, cy + bh * 1.5], fill=255)
    d.ellipse([cx - bw * 0.62, cy - bh * 1.85, cx + bw * 0.62, cy + bh * 0.15], fill=255)
    d.ellipse([cx - bw * 0.34, cy - bh * 2.35, cx + bw * 0.34, cy - bh * 1.1], fill=255)
    return m


def _mask_creature_small(w, h, seed):
    rng = np.random.default_rng(seed)
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    # low, long body — reads as something half-submerged
    d.ellipse([w * 0.10, h * 0.42, w * 0.86, h * 0.86], fill=255)
    d.polygon([(w * 0.80, h * 0.52), (w * 0.99, h * 0.62), (w * 0.80, h * 0.76)], fill=255)
    d.ellipse([w * 0.04, h * 0.50, w * 0.30, h * 0.80], fill=255)
    for i in range(6):
        side = -1 if i % 2 == 0 else 1
        x = w * (0.24 + 0.16 * (i // 2))
        joints = [(side * w * 0.07, -h * 0.16), (side * w * 0.06, h * 0.10), (side * w * 0.04, h * 0.22)]
        _seg_leg(d, x, h * 0.60, joints, width=int(h * 0.045), jitter=h * 0.014, rng=rng)
    return m


def _mask_car(w, h, seed):
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([w * 0.03, h * 0.44, w * 0.97, h * 0.80], radius=h * 0.10, fill=255)
    d.polygon([(w * 0.24, h * 0.46), (w * 0.36, h * 0.16), (w * 0.66, h * 0.16),
               (w * 0.78, h * 0.46)], fill=255)
    for cx in (w * 0.24, w * 0.76):
        d.ellipse([cx - h * 0.17, h * 0.62, cx + h * 0.17, h * 0.96], fill=255)
    return m


def _mask_treeline(w, h, seed):
    rng = np.random.default_rng(seed)
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    d.rectangle([0, h * 0.50, w, h], fill=255)
    x = -120
    while x < w + 120:
        tw = int(rng.integers(140, 300))
        th = int(rng.integers(int(h * 0.45), int(h * 1.0)))
        base = h * 0.62
        d.polygon([(x, base), (x + tw * 0.5, base - th), (x + tw, base)], fill=255)
        d.ellipse([x + tw * 0.08, base - th * 0.72, x + tw * 0.92, base - th * 0.02], fill=255)
        d.rectangle([x + tw * 0.42, base - th * 0.3, x + tw * 0.58, h], fill=255)
        x += int(tw * rng.uniform(0.40, 0.70))
    return m


def _mask_manhole_rim(w, h, seed):
    """FOREGROUND occluder. Solid from the near lip of the hole down to the
    bottom of the box, so a creature rising out of the hole is cut off by the
    rim exactly like the reference 'rises from behind the peaks' move."""
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    d.rectangle([0, h * 0.46, w, h], fill=255)          # street plane
    d.ellipse([w * 0.02, h * 0.02, w * 0.98, h * 0.86], fill=255)   # rim disc
    d.ellipse([w * 0.09, h * 0.13, w * 0.91, h * 0.72], fill=0)     # the hole
    d.rectangle([0, 0, w, h * 0.42], fill=0)            # far lip removed
    return m


def _mask_figure(w, h, seed):
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    lw = int(w * 0.11)
    cx = w * 0.5
    d.ellipse([cx - w * 0.19, h * 0.03, cx + w * 0.19, h * 0.03 + w * 0.38], fill=255)
    d.line([cx, h * 0.20, cx, h * 0.58], fill=255, width=lw)
    d.line([cx - w * 0.34, h * 0.40, cx + w * 0.34, h * 0.34], fill=255, width=lw)
    d.line([cx, h * 0.58, cx - w * 0.26, h * 0.97], fill=255, width=lw)
    d.line([cx, h * 0.58, cx + w * 0.24, h * 0.97], fill=255, width=lw)
    return m


BUILDERS = {
    "creature_tall": _mask_creature_tall,
    "creature_small": _mask_creature_small,
    "car": _mask_car,
    "treeline": _mask_treeline,
    "manhole_rim": _mask_manhole_rim,
    "figure": _mask_figure,
}


def make_cutout(slot, name, size, seed=None):
    """Dark, slightly noisy, soft-edged silhouette with real alpha."""
    w, h = size
    seed = seed if seed is not None else slot * 1409 + 77
    mask = BUILDERS[name](w, h, seed)

    # soft edge: blur the alpha, then re-gamma so the core stays solid and only
    # the rim feathers. A hard-cut alpha is what makes a cutout read "pasted on".
    soft = max(2.0, min(w, h) * 0.012)
    a = np.array(mask.filter(ImageFilter.GaussianBlur(soft)), np.float32) / 255.0
    a = np.clip((a - 0.24) / 0.52, 0, 1) ** 0.85
    # nibble the alpha with noise so the silhouette edge is not a clean vector
    n = _noise(w, h, seed + 5, octaves=(6, 18, 44))
    a = np.clip(a * (0.86 + 0.30 * n), 0, 1)
    a[a < 0.02] = 0.0

    # body value: dark, with a faint interior structure + a top rim light so it
    # is not a flat black hole when composited over a dark plate.
    tex = _noise(w, h, seed + 11, octaves=(4, 12, 30, 72))
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None] * np.ones((1, w), np.float32)
    rim = np.clip(1.0 - yy * 2.4, 0, 1) ** 2
    lum = 0.045 + 0.085 * tex + 0.075 * rim
    lum = np.clip(lum, 0, 1)
    rgb = np.stack([lum * 1.00, lum * 1.04, lum * 1.16], -1)   # same cold cast as plates

    out = np.concatenate([np.clip(rgb, 0, 1) * 255, a[..., None] * 255], -1).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def export_all(outdir):
    os.makedirs(outdir, exist_ok=True)
    paths = []
    for i, (name, size) in enumerate(SLOTS, start=1):
        im = make_cutout(i, name, size)
        p = os.path.join(outdir, f"cut{i:02d}_{name}.png")
        im.save(p, "PNG")
        paths.append((i, name, p, im.size))
    return paths


if __name__ == "__main__":
    import sys
    _default = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "remotion-engine", "public", "cutouts")
    d = sys.argv[1] if len(sys.argv) > 1 else _default
    for slot, name, p, size in export_all(d):
        print(f"cut{slot:02d} {name:15s} {size}  {p}")
