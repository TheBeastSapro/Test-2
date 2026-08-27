#!/usr/bin/env python3
"""Measure each candidate: is it RHYTHMIC WITH A DRIVING PULSE, or ambient wash?

Per SKILL.md: "floaty is a casting error, not a level problem" -- this channel's
music is rhythmic with a driving pulse, never ambient wash. So measure the pulse
rather than trusting the title or a mood tag.
"""
import json, numpy as np, librosa, warnings, sys
warnings.filterwarnings("ignore")

cands = {c["id"]: c for c in json.load(open("mus_candidates.json"))}
rows = []
for n, (cid, c) in enumerate(cands.items(), 1):
    if c["vocals"]: continue
    try:
        y, sr = librosa.load(f"mus_probe/{cid}.mp3", sr=22050, mono=True,
                             offset=20.0, duration=45.0)
    except Exception as e:
        print("skip", c["title"], e); continue
    if len(y) < sr * 10: continue
    onset = librosa.onset.onset_strength(y=y, sr=sr)
    tempo = float(librosa.beat.tempo(onset_envelope=onset, sr=sr)[0])
    peaks = librosa.util.peak_pick(onset, pre_max=3, post_max=3, pre_avg=3,
                                   post_avg=5, delta=0.4, wait=4)
    onsets_per_s = len(peaks) / (len(y) / sr)
    # pulse strength: how peaked the tempogram autocorrelation is
    ac = librosa.autocorrelate(onset - onset.mean(), max_size=len(onset)//2)
    ac = ac / (ac[0] + 1e-9)
    pulse = float(np.max(ac[8:200])) if len(ac) > 200 else 0.0
    # percussive fraction
    D = librosa.stft(y, n_fft=1024)
    H, P = librosa.decompose.hpss(D)
    perc = float(np.abs(P).sum() / (np.abs(H).sum() + np.abs(P).sum()))
    rms = librosa.feature.rms(y=y)[0]
    dyn = float(np.std(librosa.amplitude_to_db(rms + 1e-9)))
    cent = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    rows.append({"id": cid, "title": c["title"], "ms": c["ms"], "tags": c["tags"],
                 "bpm": round(tempo,1), "onsets_s": round(onsets_per_s,2),
                 "pulse": round(pulse,3), "perc": round(perc,3),
                 "dyn_db": round(dyn,2), "centroid": round(cent)})
    if n % 20 == 0: print(f"  ..{n}", file=sys.stderr)
json.dump(rows, open("mus_measured.json","w"), indent=1)
# drive score: rhythmic density + pulse regularity + percussive content
for r in rows:
    r["drive"] = round(min(r["onsets_s"]/2.2,1.4)*1.0 + r["pulse"]*1.6 + r["perc"]*2.2, 3)
rows.sort(key=lambda r: -r["drive"])
print(f"{'title':38s} {'bpm':>6} {'ons/s':>6} {'pulse':>6} {'perc':>6} {'dyn':>5} {'drive':>6}")
for r in rows:
    print(f"{r['title'][:38]:38s} {r['bpm']:6.1f} {r['onsets_s']:6.2f} {r['pulse']:6.3f} "
          f"{r['perc']:6.3f} {r['dyn_db']:5.1f} {r['drive']:6.2f}")
