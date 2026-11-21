#!/usr/bin/env python3
"""Catch the words Sapro would otherwise catch by ear.

He reported six defects in one delivery — "would", "measure", "mud",
"Parliament", "Roxburgh", "331 BC" — one at a time, describing them as "echoing",
"robotic", and "sounding like a separate word in the sentence". Then he stopped 5
minutes into a 12:30 file, which means the back half was never checked at all.

WHY NOTHING CAUGHT THEM. The read-check compares audio to the SCRIPT, so it can
only ever find wrong words. Every one of these was a correctly-read word that
sounds wrong. Two detectors were built for it and both failed: envelope
autocorrelation flagged 2133 of 2371 words (it was finding pitch periodicity),
and tail-template matching caught 2 of 3 (it was looking for a repeat, when the
defect is timbre).

WHAT ACTUALLY MEASURES. "Parliament" gave it away. Word by word:

    informed 308 Hz   [Parliament] 111 Hz   that 208 Hz

A 17.6-semitone drop below its neighbour and back up again — a word spoken in a
different register from the sentence around it. That is exactly what "a separate
word" means, and what "robotic" means when the pitch also stops moving: the
original take of that word had a pitch spread of 0.14 semitones, the 0th
percentile of its section, i.e. a flat tone.

So two measures, both per-word, both judged against the read's own distribution
rather than an invented threshold:

  DETACHED  median f0 far from the median f0 of the words either side.
  FLAT      pitch spread near zero when the surrounding words are moving.

Neither number means anything alone, which is the lesson from choosing between
four takes of the "Maginot" header: a distance without a baseline is not
evidence. Here the baseline is the section's own distribution of the same
statistic.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SR = 16000
MIN_DUR = 0.14
# CALIBRATION, and its weakness. These are set from ONE confirmed example —
# "Parliament", the only word Sapro has both complained about and had measured.
# In that section it scored 13.6 st against a next-worst of 9.4 and a spread of
# 6.2-9.4 for ordinary words, so 10.0 isolates it cleanly. At 6.0 the gate flagged
# 21 of 72 words, a 29% rate that nobody would read.
#
# n=1 is not a calibration, it is a starting point. Widen or tighten it as more
# confirmed examples arrive, and never report a clean run from this gate as proof
# the file is clean.
DETACH_ST = 10.0     # semitones from the local median before a word reads as detached
FLAT_ABS = 0.25      # pitch spread below this is a flat tone in absolute terms
FLAT_PCT = 3.0       # ...and it must also sit in the bottom N% of its section


def f0_stats(y, s, e, np, librosa):
    seg = y[int(s * SR):int(e * SR)]
    if len(seg) < int(0.05 * SR):
        return None
    f0, _, _ = librosa.pyin(seg, fmin=55, fmax=350, sr=SR, frame_length=1024)
    f = f0[~np.isnan(f0)]
    if len(f) < 4:
        return None
    med = float(np.median(f))
    spread = float(np.std(12 * np.log2(f / med)))
    return med, spread


def scan_section(path, model, np, librosa):
    y, _ = librosa.load(path, sr=SR, mono=True)
    segs, _ = model.transcribe(path, language="en", beam_size=5,
                               condition_on_previous_text=False, word_timestamps=True)
    rows = []
    for s_ in segs:
        for w in (s_.words or []):
            a, b = float(w.start), float(w.end)
            if b - a < MIN_DUR:
                continue
            st = f0_stats(y, a, b, np, librosa)
            if st:
                rows.append(dict(word=w.word.strip(), at=round(a, 2),
                                 f0=st[0], spread=st[1]))
    return rows


def judge(rows, np):
    """-> flagged rows. Each word is judged against its own neighbourhood."""
    if len(rows) < 6:
        return []
    spreads = np.array([r["spread"] for r in rows])
    flat_cut = float(np.percentile(spreads, FLAT_PCT))
    out = []
    for i, r in enumerate(rows):
        near = [rows[j]["f0"] for j in range(max(0, i - 3), min(len(rows), i + 4))
                if j != i]
        if len(near) < 2:
            continue
        local = float(np.median(near))
        drop = abs(12 * np.log2(r["f0"] / local))
        why = []
        if drop >= DETACH_ST:
            why.append(f"detached {drop:.1f} st from its neighbours "
                       f"({r['f0']:.0f} Hz vs {local:.0f} Hz)")
        # Function words ("that", "the", "every") are naturally flat, so the
        # percentile alone flagged them. Require an absolute floor as well: the
        # original "Parliament" sat at 0.14 st, a genuinely toneless reading.
        if r["spread"] <= flat_cut and r["spread"] < FLAT_ABS:
            why.append(f"flat, spread {r['spread']:.2f} st "
                       f"(section floor {flat_cut:.2f})")
        if why:
            out.append(dict(r, why="; ".join(why), drop=round(drop, 1)))
    return out


def main():
    ap = argparse.ArgumentParser(
        description="Flag words that are detached or flat relative to the read.")
    ap.add_argument("--parts-dir", required=True)
    ap.add_argument("--sections-json", required=True)
    ap.add_argument("--only", help="comma-separated 1-based section numbers")
    ap.add_argument("--json-out")
    a = ap.parse_args()

    import numpy as np
    import librosa
    import readcheck as rc

    sections = json.load(open(a.sections_json, encoding="utf-8"))["sections"]
    if a.only:
        want = {int(x) for x in a.only.split(",")}
        sections = [s for s in sections if s["index"] + 1 in want]
    model = rc.load_asr()

    hits = []
    for k, sec in enumerate(sections, 1):
        p = os.path.join(a.parts_dir, f"sec_{sec['index']:03d}.mp3")
        if not os.path.isfile(p):
            continue
        rows = scan_section(p, model, np, librosa)
        flagged = judge(rows, np)
        for f in flagged:
            f["section"] = sec["index"] + 1
        hits += flagged
        print(f"[prosody] {k}/{len(sections)} — section {sec['index']+1}, "
              f"{len(rows)} words, {len(flagged)} flagged", flush=True)

    print()
    if not hits:
        print("[prosody] nothing detached or flat.")
    else:
        for h in sorted(hits, key=lambda x: -x["drop"]):
            print(f"[prosody] section {h['section']:<3} {h['at']:6.2f}s  "
                  f"“{h['word']}”  — {h['why']}")
        secs = sorted({h["section"] for h in hits})
        print(f"\n[prosody] {len(hits)} word(s) in {len(secs)} section(s): "
              f"{','.join(map(str, secs))}")
        print("Fix with regen_span.py on the SENTENCE containing each — not the "
              "section (rule 7b).")
    if a.json_out:
        json.dump({"hits": hits}, open(a.json_out, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
