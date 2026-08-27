#!/usr/bin/env python3
"""Which cues keep sounding after the picture has moved on?

The general form of the fire note. For each primary cue, find the next scene cut
and compare it with how long the file actually stays audible (to -30 dB below its
own peak, not its full length — a file can be 7 s and inaudible after 1).
"""
import json, os, numpy as np, soundfile as sf
c = json.load(open("cues.json")); T = json.load(open("sfx_titles.json"))
cuts = sorted(e["t"] for e in json.load(open("redraw.json"))["events"] if e["kind"] == "cut")
cache = {}
def audible(p, floor=-30.0):
    if p in cache: return cache[p]
    y, sr = sf.read(p, always_2d=True); y = np.abs(y.mean(axis=1))
    w = max(1, int(sr*0.02)); e = np.convolve(y, np.ones(w)/w, mode="same")
    thr = e.max() * 10**(floor/20)
    idx = np.flatnonzero(e > thr)
    cache[p] = (idx[-1]/sr if len(idx) else 0.0)
    return cache[p]
rows = []
for s in c["sfx_cues"]:
    if s.get("layer"): continue
    nxt = next((t for t in cuts if t > s["at"] + 0.15), None)
    if nxt is None: continue
    shot = nxt - s["at"]
    tail = audible(s["asset"])
    cap = s.get("max_len")
    if cap: tail = min(tail, cap)      # the cue is trimmed at render, so measure that
    over = tail - shot
    if over > 1.5 and tail > 2.0:
        rows.append((s["at"], over, shot, tail, s["tier"], s["gain_db"],
                     os.path.basename(s["asset"])[:-4], s["kind"]))
rows.sort(key=lambda r: -r[1])
print(f"{'at':>9} {'over':>6} {'shot':>6} {'tail':>6} {'tier':9s} {'dB':>5}  file — beat")
for at,ov,sh,tl,t,g,n,k in rows:
    print(f"{at:9.2f} {ov:5.1f}s {sh:5.1f}s {tl:5.1f}s {t:9s} {g:+5.0f}  {n} — {k[:40]}")
print(f"\n{len(rows)} primary cue(s) still audible more than 1.5 s after the picture cut")
