"""Procedural ANIMATIC plates. These stand in for approved canon art.
In production this module is replaced by a loader that reads the locked
per-creature image shortlist from the editor-materials sheet."""
import numpy as np, hashlib
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import style as S

PW, PH = 1700, 1050   # oversized so Ken Burns never runs out of pixels

def _noise(w, h, seed, octaves=(3, 7, 16, 40, 96)):
    rng = np.random.default_rng(seed)
    acc = np.zeros((h, w), np.float32)
    amp = 1.0
    for o in octaves:
        small = rng.random((max(2, h // o), max(2, w // o))).astype(np.float32)
        up = np.array(Image.fromarray((small * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 255.0
        acc += up * amp; amp *= 0.55
    acc -= acc.min(); acc /= max(acc.max(), 1e-6)
    return acc

def make_plate(slot, description, seed=None, key_light=0.55):
    """Dark, grainy, cinematic-ish plate with 2-3 bright anchors (never illegible)."""
    seed = seed if seed is not None else int(hashlib.md5(description.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    n = _noise(PW, PH, seed)
    yy, xx = np.mgrid[0:PH, 0:PW]
    # key light pool -> the "bright anchor" the QC doc demands in night scenes
    cx, cy = rng.uniform(0.25, 0.75) * PW, rng.uniform(0.2, 0.6) * PH
    r = np.sqrt(((xx - cx) / (PW * 0.55)) ** 2 + ((yy - cy) / (PH * 0.75)) ** 2)
    pool = np.clip(1.0 - r, 0, 1) ** 2
    base = 0.035 + 0.10*rng.random()
    lum = base + (0.55+0.5*rng.random()) * pool * key_light + (0.16+0.16*rng.random()) * n * (0.35 + pool)
    lum = np.clip(lum, 0, 1)
    tint = np.stack([lum * 1.00, lum * 1.03, lum * 1.12], -1)   # cold cast
    img = Image.fromarray((np.clip(tint, 0, 1) * 255).astype(np.uint8))
    d = ImageDraw.Draw(img, "RGBA")
    # Hard graphic anchors so consecutive plates read as different shots AND so a
    # 'close' / 'insert' crop still has edges in it. The rebuild hard-cuts to
    # magnified crops of the same plate; with only soft low-frequency noise those
    # crops rendered as featureless fog.
    for _ in range(rng.integers(7, 14)):
        x0, y0 = rng.integers(0, PW - 300), rng.integers(0, PH - 300)
        w_, h_ = rng.integers(120, 900), rng.integers(120, 700)
        a = int(rng.integers(40, 130))
        col = (0, 0, 0, a) if rng.random() < 0.76 else (255, 255, 255, int(a * 0.36))
        if rng.random() < 0.5:
            d.rectangle([x0, y0, x0 + w_, y0 + h_], fill=col)
        else:
            d.ellipse([x0, y0, x0 + w_, y0 + h_], fill=col)
    # fine structure: struts / pipe runs / edges, so magnification finds detail
    for _ in range(rng.integers(10, 22)):
        x0, y0 = rng.integers(0, PW), rng.integers(0, PH)
        L = int(rng.integers(200, 1400))
        vert = rng.random() < 0.55
        wid = int(rng.integers(4, 26))
        a = int(rng.integers(35, 110))
        col = (0, 0, 0, a) if rng.random() < 0.7 else (255, 255, 255, int(a * 0.55))
        box = [x0, y0, x0 + (wid if vert else L), y0 + (L if vert else wid)]
        d.rectangle(box, fill=col)
    img = img.filter(ImageFilter.GaussianBlur(0.5))
    # contrast: the old plates sat in a narrow grey band and read as fog
    arr = np.array(img, np.float32) / 255.0
    arr = np.clip((arr - 0.46) * 1.30 + 0.40, 0, 1)
    img = Image.fromarray((arr * 255).astype(np.uint8))
    # vignette
    v = np.clip(1.15 - np.sqrt(((xx - PW / 2) / (PW / 2)) ** 2 + ((yy - PH / 2) / (PH / 2)) ** 2) * 0.75, 0, 1)
    img = Image.fromarray((np.array(img, np.float32) * v[..., None]).astype(np.uint8))
    return img
