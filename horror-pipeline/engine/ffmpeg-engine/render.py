import json, math, os, sys, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import style as S, plates as P

def ease(u): u = max(0.0, min(1.0, u)); return u*u*(3-2*u)
def easeout(u): u = max(0.0, min(1.0, u)); return 1-(1-u)**3

_F = {}
def font(path, size):
    k = (path, size)
    if k not in _F: _F[k] = ImageFont.truetype(path, size)
    return _F[k]

def tracked_text(d, xy, txt, f, fill, track=0, anchor_center=False, stroke=0, stroke_fill=None):
    widths = [d.textlength(c, font=f) for c in txt]
    total = sum(widths) + track*(len(txt)-1)
    x, y = xy
    if anchor_center: x -= total/2
    for c, w in zip(txt, widths):
        d.text((x, y), c, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
        x += w + track
    return total

def rounded_mask(size, r):
    m = Image.new("L", size, 0); ImageDraw.Draw(m).rounded_rectangle([0,0,size[0]-1,size[1]-1], r, fill=255); return m

# ---------------------------------------------------------------- icons
def draw_icon(base, kind, cx, cy, size, prog, alpha):
    lay = Image.new("RGBA", base.size, (0,0,0,0)); d = ImageDraw.Draw(lay)
    s = size * (0.86 + 0.14*easeout(prog)); a = int(255*alpha)
    if kind == "redx":
        w = max(6, int(s*0.14))
        d.line([cx-s/2, cy-s/2, cx+s/2, cy+s/2], fill=S.RED+(a,), width=w)
        d.line([cx-s/2, cy+s/2, cx+s/2, cy-s/2], fill=S.RED+(a,), width=w)
    elif kind == "arrow":
        w = max(5, int(s*0.10))
        d.line([cx-s/2, cy, cx+s/3, cy], fill=S.RED+(a,), width=w)
        d.polygon([(cx+s/2, cy), (cx+s/6, cy-s/4), (cx+s/6, cy+s/4)], fill=S.RED+(a,))
    elif kind == "person":     # stick figure, black
        w = max(5, int(s*0.09)); col = S.BLACK+(a,)
        hr = s*0.16
        d.ellipse([cx-hr, cy-s/2, cx+hr, cy-s/2+2*hr], outline=col, width=w)
        d.line([cx, cy-s/2+2*hr, cx, cy+s*0.10], fill=col, width=w)
        d.line([cx-s*0.28, cy-s*0.10, cx+s*0.28, cy-s*0.10], fill=col, width=w)
        d.line([cx, cy+s*0.10, cx-s*0.22, cy+s/2], fill=col, width=w)
        d.line([cx, cy+s*0.10, cx+s*0.22, cy+s/2], fill=col, width=w)
    elif kind == "warn":
        col = S.RED+(a,); w = max(5,int(s*0.10))
        d.polygon([(cx, cy-s/2), (cx+s/2, cy+s/2), (cx-s/2, cy+s/2)], outline=col, width=w)
        d.line([cx, cy-s*0.16, cx, cy+s*0.18], fill=col, width=w)
        d.ellipse([cx-w*0.7, cy+s*0.28, cx+w*0.7, cy+s*0.28+w*1.4], fill=col)
    base.alpha_composite(lay)

# ---------------------------------------------------------------- shot
class Shot:
    def __init__(self, sp, idx):
        self.t0, self.t1 = sp["t0"], sp["t1"]
        self.desc = sp["desc"]; self.idx = idx
        self.kb = sp.get("kb", "in")
        self.seed = sp.get("seed", idx*977+13)
        self.plate = None
    def load(self):
        if self.plate is None:
            self.plate = P.make_plate(self.idx+1, self.desc, self.seed,
                                      key_light=0.45+0.12*((self.idx*7)%5)/4)
        return self.plate

    def frame(self, t):
        im = self.load()
        u = ease((t-self.t0)/max(1e-6, self.t1-self.t0))
        box_ar = S.BOX_W/S.BOX_H
        ch = min(P.PH, P.PW/box_ar); cw = ch*box_ar
        if   self.kb == "in":    s0, s1 = 1.02, 1.02+S.KB_DRIFT
        elif self.kb == "out":   s0, s1 = 1.02+S.KB_DRIFT, 1.02
        else:                    s0, s1 = 1.14, 1.14+S.KB_DRIFT*0.35
        sc = s0 + (s1-s0)*u
        # cut punch: a fast scale overshoot on the first beats of every shot, so a
        # cut reads as a CUT and not a dissolve (motion metric + perceived pace)
        cp = (t-self.t0)/0.30
        if cp < 1.0: sc *= 1.0 + 0.055*(1-easeout(max(0.0, cp)))
        vw, vh = cw/sc, ch/sc
        rng = np.random.default_rng(self.seed)
        ax, ay = rng.uniform(0.25,0.75), rng.uniform(0.3,0.7)
        bx, by = rng.uniform(0.25,0.75), rng.uniform(0.3,0.7)
        if self.kb == "pan": bx = ax + (0.62 if ax < 0.5 else -0.62)
        else: bx = ax + (bx-ax)*0.55 + (0.14 if ax < 0.5 else -0.14)
        px = ax + (bx-ax)*u; py = ay + (by-ay)*u
        cx = (P.PW-vw)*px + vw/2; cy = (P.PH-vh)*py + vh/2
        crop = im.crop((int(cx-vw/2), int(cy-vh/2), int(cx+vw/2), int(cy+vh/2)))
        return crop.resize((S.BOX_W, S.BOX_H), Image.BILINEAR)

# ---------------------------------------------------------------- renderer
class Renderer:
    def __init__(self, sheet):
        self.sheet = sheet
        self.title = sheet["title"].upper()
        self.shots = [Shot(s, i) for i, s in enumerate(sheet["shots"])]
        self.pops  = sheet["pops"]; self.icons = sheet.get("icons", [])
        self.shakes= sheet.get("shakes", []); self.glitches = sheet.get("glitches", [])
        self.cards = sheet.get("cards", [])
        self.dur   = sheet["duration"]
        self.mask  = rounded_mask((S.BOX_W, S.BOX_H), S.BOX_RADIUS)

    def shot_at(self, t):
        for sh in self.shots:
            if sh.t0 <= t < sh.t1: return sh
        return self.shots[-1]

    def render(self, t):
        cv = Image.new("RGBA", (S.W, S.H), S.CANVAS+(255,))
        d  = ImageDraw.Draw(cv, "RGBA")
        x0 = S.BOX_CX-S.BOX_W//2; y0 = S.BOX_CY-S.BOX_H//2
        # --- card takeover (roster / creature card punch-in)
        card = next((c for c in self.cards if c["t0"] <= t < c["t1"]), None)
        if card:
            self._card(cv, d, card, t); return cv
        sh = self.shot_at(t)
        img = sh.frame(t).convert("RGBA")
        d.rounded_rectangle([x0-S.BOX_BORDER, y0-S.BOX_BORDER, x0+S.BOX_W+S.BOX_BORDER, y0+S.BOX_H+S.BOX_BORDER],
                            S.BOX_RADIUS+4, fill=S.BLACK+(255,))
        cv.paste(img, (x0, y0), self.mask)
        # --- persistent title, top-center
        f = font(S.TITLE_FONT, S.TITLE_SIZE)
        tin = easeout(min(1.0, t/0.55))
        ty = S.TITLE_Y + (1-tin)*-26
        tw = tracked_text(d, (S.W/2, ty), self.title, f, S.BLACK+(int(255*tin),), S.TITLE_TRACK, True)
        ub = ty + f.getbbox(self.title)[3] + 14
        d.rectangle([S.W/2-(tw*0.32)*tin, ub, S.W/2+(tw*0.32)*tin, ub+7], fill=S.RED+(int(255*tin),))
        # animatic slot tag (production build drops this line)
        fs = font(S.BODY_FONT, 22)
        d.text((34, S.H-42), f"ASSET SLOT {sh.idx+1:02d} \u00b7 PLACEHOLDER \u00b7 {sh.desc.upper()}", font=fs, fill=(150,150,150,255))
        # --- icons
        for ic in self.icons:
            if ic["t0"] <= t < ic["t1"]:
                p = (t-ic["t0"])/max(1e-6, min(0.28, ic["t1"]-ic["t0"]))
                a = min(1.0, (ic["t1"]-t)/0.18)
                draw_icon(cv, ic["kind"], ic["x"], ic["y"], ic["size"], p, max(0.0, min(1.0, a)))
        # --- keyword pops
        for pp in self.pops:
            if pp["t0"] <= t < pp["t1"]: self._pop(cv, d, pp, t, x0, y0)
        # --- shake / glitch
        for sk in self.shakes:
            if sk["t0"] <= t < sk["t0"]+sk.get("dur", 0.34):
                k = (t-sk["t0"])/sk.get("dur", 0.34); amp = sk.get("amp", 16)*(1-k)**2
                dx = int(amp*math.sin(t*92)); dy = int(amp*math.cos(t*77))
                cv = cv.transform(cv.size, Image.AFFINE, (1,0,dx,0,1,dy), fillcolor=S.CANVAS+(255,))
        for g in self.glitches:
            if g["t0"] <= t < g["t0"]+g.get("dur", 0.22): cv = self._glitch(cv, t, g)
        return cv

    def _card(self, cv, d, card, t):
        u = ease((t-card["t0"])/max(1e-6, card["t1"]-card["t0"]))
        sc = 1.0 + 0.30*u
        cw, chh = int(980*sc), int(620*sc)
        pl = P.make_plate(99, card.get("desc", "creature card"), 4242, key_light=0.62)
        ar = cw/chh; sh_ = min(P.PH, P.PW/ar); sw = sh_*ar
        crop = pl.crop((int((P.PW-sw)/2), int((P.PH-sh_)/2), int((P.PW+sw)/2), int((P.PH+sh_)/2))).resize((cw, chh), Image.BILINEAR)
        x, y = S.W//2-cw//2, S.H//2-chh//2-30
        d.rounded_rectangle([x-8, y-8, x+cw+8, y+chh+8], 26, fill=S.BLACK+(255,))
        cv.paste(crop.convert("RGBA"), (x, y), rounded_mask((cw, chh), 22))
        f = font(S.CARD_FONT, int(96))
        a = int(255*easeout(min(1, (t-card["t0"])/0.4)))
        tracked_text(d, (S.W/2, y+chh+24), self.title, f, S.WHITE+(a,), 2, True, stroke=7, stroke_fill=S.BLACK+(a,))

    def _pop(self, cv, d, pp, t, bx, by):
        txt = pp["text"].upper()
        size = pp.get("size", S.POP_SIZE)
        f = font(S.POP_FONT, size)
        tin  = easeout(min(1.0, (t-pp["t0"])/S.POP_IN_DUR))
        tout = min(1.0, max(0.0, (pp["t1"]-t)/S.POP_OUT_DUR))
        a = int(255*min(tin, tout))
        dy = (1-tin)*26
        col = S.RED if pp.get("accent") else S.BLACK
        if pp.get("where", "band") == "band":
            y = S.BOX_CY+S.BOX_H//2+34+dy
            x = S.W/2 if pp.get("align","c")=="c" else (bx+40)
            tracked_text(d, (x, y), txt, f, col+(a,), 2, pp.get("align","c")=="c")
        else:  # on-image: white fill + black stroke, kept INSIDE the box
            y = by+S.BOX_H-size-58+dy
            x = bx+52
            w = d.textlength(txt, font=f)
            d.text((x, y), txt, font=f, fill=S.WHITE+(a,), stroke_width=7, stroke_fill=S.BLACK+(a,))
            if pp.get("accent"):
                yb = y+f.getbbox(txt)[3]+12
                d.rectangle([x, yb, x+w*tin, yb+9], fill=S.RED+(a,))

    def _glitch(self, cv, t, g):
        arr = np.array(cv.convert("RGB"), np.uint8)
        k = int(g.get("amp", 16)*(1-(t-g["t0"])/g.get("dur",0.22)))
        if k > 0:
            arr[:, :, 0] = np.roll(arr[:, :, 0], k, axis=1)
            arr[:, :, 2] = np.roll(arr[:, :, 2], -k, axis=1)
            rows = np.arange(S.H); band = (rows % 6) < 2
            arr[band] = (arr[band]*0.82).astype(np.uint8)
        return Image.fromarray(arr).convert("RGBA")
