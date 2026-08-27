#!/usr/bin/env python3
"""Takes masquerading as samples, strictly: two attacks that each reach 55% of
peak, >=150 ms apart, with a real trough (<25% of the lower peak) between them.

The loose version (any envelope crossing of 30% of peak) counted the ripple
inside one decaying hit and flagged 108 of 240 files, including six sword-palette
whooshes that the previous job had already validated. A slow-blooming whoosh has
a long anchor and one attack; that is not the same shape as a four-blow take.
"""
import json, numpy as np, soundfile as sf, sys
BEDS = {"amb","march","vox_yell","crowd","fire","wind","lake","river","boil","foot"}
SWORD = {"amb","armor","boom","clatter","draw","fall","falx","forge","impact","march",
         "pop","stab","swish","vox_cry","vox_yell","whoosh","body","shield","vox_effort",
         "cut","chop","slash","gun","crowd"}   # prepared and vetted by the sword job
pal = json.load(open("pal/palette_manifest.json"))
anch = pal["_anchors"]

def attacks(path):
    y, sr = sf.read(path, always_2d=True)
    y = np.abs(y.mean(axis=1))
    w = max(1, int(sr * 0.004))
    env = np.convolve(y, np.ones(w)/w, mode="same")
    pk = env.max()
    if pk <= 0: return 0, 0.0
    idx = [i for i in range(1, len(env)-1)
           if env[i] >= 0.55*pk and env[i] >= env[i-1] and env[i] > env[i+1]]
    keep = []
    for i in idx:
        if not keep: keep.append(i); continue
        j = keep[-1]
        if i - j < int(sr*0.150): 
            if env[i] > env[j]: keep[-1] = i
            continue
        trough = env[j:i].min()
        if trough < 0.25*min(env[i], env[j]): keep.append(i)
        elif env[i] > env[j]: keep[-1] = i
    return len(keep), len(y)/sr

rows, flagged = [], []
for cat, names in pal.items():
    if cat.startswith("_") or cat in BEDS: continue
    for n in names:
        h, d = attacks(f"pal/{n}.wav")
        a = anch.get(n, 0.0)
        rows.append((cat, n, h, a, d))
        if h > 1 and a > 0.10 and cat not in SWORD:
            flagged.append((n, cat, h, a, d))
flagged.sort(key=lambda r: -r[2])
print(f"{'file':14s} {'cat':10s} {'hits':>4} {'anchor':>7} {'dur':>6}")
for n, c, h, a, d in flagged: print(f"{n:14s} {c:10s} {h:4d} {a:7.3f} {d:6.2f}")
sw_multi = [(n,c,h,a) for c,n,h,a,d in rows if h>1 and a>0.10 and c in SWORD]
print(f"\n{len(flagged)} castle files to split out of {len(rows)} hit files")
print(f"({len(sw_multi)} sword-palette files also read as multi-hit; left alone — "
      f"already vetted by the sword job)")
json.dump([f[0] for f in flagged], open("to_split.json","w"))
