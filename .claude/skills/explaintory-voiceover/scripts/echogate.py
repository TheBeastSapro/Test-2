#!/usr/bin/env python3
"""Catch the doubled-tail artifact before Sapro has to hear it.

He reported it five times in one delivery — "would", "measure", "mud", and two
more — one word at a time, which is precisely the loop this pipeline exists to
remove. The read-check could not see it: the words are all correctly READ, so the
transcript matches the script and WER is clean. It is an acoustic defect in a
correct read, and nothing in the pipeline was looking for those.

SIGNATURE. Not periodicity — a copy. HANDOFF records the same artifact from the
Hashish defect: a short segment that is a spectral near-duplicate of the preceding
word's tail (centroid 5075 Hz vs 5080, ZCR 8290 vs 7471). An earlier attempt here
measured envelope autocorrelation instead and flagged 2133 of 2371 words, i.e.
nothing; the 56 ms peak it kept finding was pitch periodicity. So: take each
word's last 120 ms as a template, slide over the following 400 ms, and take the
best MFCC cosine similarity. A word decaying into a different phoneme scores low;
a word whose tail is reprinted after it scores high.

VALIDATION, and its limits. Against the three words Sapro named in the takes he
flagged: "mud" 0.741 (99.3rd percentile), "would" 0.585 (93.6th) — both fell after
a re-roll. "measure" scored 0.366, the 34th percentile: NOT caught. So this gate
finds two thirds of what he hears, and a clean run from it is not proof of a clean
file. It is a floor, not a ceiling, and it should be reported that way.

THRESHOLD. 0.585, the lower of the two confirmed true positives, so the weaker of
the two known defects still trips it. Deliberately not tuned tighter: the cost of
a false positive is one section re-rolled, and the cost of a false negative is
Sapro finding it.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SR = 16000
TAIL = 0.120
LOOK = 0.400
MINLAG = 0.040
THRESHOLD = 0.585


def _feats(y, librosa, np):
    m = librosa.feature.mfcc(y=y, sr=SR, n_mfcc=13, hop_length=128)
    return (m - m.mean(axis=1, keepdims=True)) / (m.std(axis=1, keepdims=True) + 1e-9)


def tail_echo(y, s, e, librosa, np):
    """-> (best cosine similarity to this word's tail in the next 400 ms, lag ms)."""
    a0, a1 = int(max(s, e - TAIL) * SR), int(e * SR)
    if a1 - a0 < int(0.05 * SR):
        return None, None
    tmpl = _feats(y[a0:a1], librosa, np)
    n = tmpl.shape[1]
    best, blag = -1.0, None
    for off in range(int(MINLAG * SR), int(LOOK * SR), int(0.008 * SR)):
        b0, b1 = a1 + off, a1 + off + (a1 - a0)
        if b1 > len(y):
            break
        seg = y[b0:b1]
        if float(np.sqrt((seg ** 2).mean())) < 1e-4:
            continue
        f = _feats(seg, librosa, np)
        if f.shape[1] != n:
            continue
        c = float((tmpl * f).sum()) / (float(np.linalg.norm(tmpl) * np.linalg.norm(f)) + 1e-12)
        if c > best:
            best, blag = c, 1000.0 * off / SR
    return (best if best > -1 else None), blag


def scan_sections(parts_dir, sections, threshold=THRESHOLD, asr=None):
    """-> [{index, word, score, lag, at}] for every word over the threshold."""
    import numpy as np
    import librosa
    import readcheck as rc

    model = asr or rc.load_asr()
    hits = []
    total = len(sections)
    for k, sec in enumerate(sections, 1):
        p = os.path.join(parts_dir, f"sec_{sec['index']:03d}.mp3")
        if not os.path.isfile(p):
            continue
        y, _ = librosa.load(p, sr=SR, mono=True)
        segs, _ = model.transcribe(p, language="en", beam_size=5,
                                   condition_on_previous_text=False,
                                   word_timestamps=True)
        worst = 0.0
        for s in segs:
            for w in (s.words or []):
                sc, lag = tail_echo(y, float(w.start), float(w.end), librosa, np)
                if sc is None:
                    continue
                worst = max(worst, sc)
                if sc >= threshold:
                    hits.append(dict(index=sec["index"], word=w.word.strip(),
                                     score=round(sc, 3), lag=round(lag or 0, 1),
                                     at=round(float(w.start), 2)))
        print(f"[echogate] {k}/{total} — section {sec['index']+1}, worst {worst:.3f}",
              flush=True)
    return hits


def main():
    ap = argparse.ArgumentParser(description="Flag doubled-tail artifacts in section takes.")
    ap.add_argument("--parts-dir", required=True)
    ap.add_argument("--sections-json", required=True)
    ap.add_argument("--threshold", type=float, default=THRESHOLD)
    ap.add_argument("--json-out")
    a = ap.parse_args()

    sections = json.load(open(a.sections_json, encoding="utf-8"))["sections"]
    hits = scan_sections(a.parts_dir, sections, a.threshold)

    secs = sorted({h["index"] + 1 for h in hits})
    print()
    if not hits:
        print("[echogate] no doubled-tail artifacts at or above "
              f"{a.threshold:.3f}. NOTE: this gate caught 2 of the 3 words Sapro "
              "reported, so clean here is a floor, not a guarantee.")
    else:
        for h in sorted(hits, key=lambda x: -x["score"]):
            print(f"[echogate] {h['score']:.3f}  lag {h['lag']:5.1f} ms  "
                  f"section {h['index']+1:<3} {h['word']}")
        print(f"\n[echogate] {len(hits)} hit(s) in {len(secs)} section(s): "
              f"{','.join(map(str, secs))}")
    if a.json_out:
        json.dump({"threshold": a.threshold, "hits": hits, "sections": secs},
                  open(a.json_out, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
