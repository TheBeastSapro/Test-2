#!/usr/bin/env python3
"""Flag files that SUSTAIN cast as hits, and beds that outrun what they are under.

The tonal-tail rule ("a bell is a bed, not a hit") is a special case of a bigger
one: a file whose level does not decay after its attack is a bed whatever its
pitch. A 6.2 s torch crackle cast as a hero boom keeps crackling for seconds
after the beat, which reads exactly like a bed that will not stop. A 7 s debris
fall is fine at the same length because it decays.

sustain = median level over the last half of the file, relative to its peak.
Decaying hits land near -30 dB; loops and crackles land near -12.
"""
import json, os, numpy as np, soundfile as sf
c = json.load(open("cues.json")); T = json.load(open("sfx_titles.json"))
def sustain_db(p):
    y, sr = sf.read(p, always_2d=True); y = np.abs(y.mean(axis=1))
    if len(y) < sr * 0.2: return -99.0, len(y)/sr
    w = max(1, int(sr*0.02)); e = np.convolve(y, np.ones(w)/w, mode="same")
    pk = e.max() + 1e-12
    return 20*np.log10(np.median(e[len(e)//2:])/pk + 1e-12), len(y)/sr
cache, flagged = {}, []
for s in c["sfx_cues"]:
    if s.get("layer") or not s["tier"].startswith("hero"): continue
    a = s["asset"]
    if a not in cache: cache[a] = sustain_db(a)
    sus, dur = cache[a]
    if dur > 4.0 and sus > -22.0:
        flagged.append((s["at"], s["tier"], dur, sus, os.path.basename(a)[:-4], s["kind"]))
flagged.sort()
print(f"{'at':>9} {'tier':10s} {'dur':>5} {'sustain':>8}  file / beat")
for at, t, d, sus, n, k in flagged:
    print(f"{at:9.2f} {t:10s} {d:5.2f}s {sus:7.1f} dB  {n} — {k[:44]}")
print(f"\n{len(flagged)} hero cue(s) cast from a file that sustains")
print("\n=== for comparison, what a decaying hit measures ===")
for n in ("rubble_01","rubble_02","boom_01","firewh_04","fire_01","stone_01"):
    p = f"pal/{n}.wav"
    if os.path.exists(p):
        sus, d = sustain_db(p)
        print(f"  {n:10s} {d:5.2f}s  sustain {sus:6.1f} dB   {T.get(n,'')[:52]}")
