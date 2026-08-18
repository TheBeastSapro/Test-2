#!/usr/bin/env python3
"""Find words the voice rendered unlike its own other renderings of that word.

The read-check compares audio to the SCRIPT, so it only sees wrong words. Sapro's
complaints are a different class: correctly-read words that sound wrong — an echo,
a doubled tail, a pitch break. Nothing was looking for those, so he found them by
ear, one at a time, and stopped 5 minutes into a 12:30 file.

METHOD, borrowed from the one that worked. Choosing between four takes of the
"Maginot" header was settled by measuring the word against the body sections that
say it correctly, and calibrating with a baseline: the same word in two DIFFERENT
correct places. That baseline is what made the distance readable.

Generalise it. A word occurring 3+ times gives its own baseline for free: the
median pairwise distance between its instances is how much this voice normally
varies on that word. An instance far outside its own peers is the anomaly — and
the comparison is airtight because it is the same word, same voice, same session,
same settings. No threshold has to be invented; each word brings its own.

Scores are reported as a ratio to the word's own median, so 2.0 means "twice as
unlike its peers as they are unlike each other".
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SR = 16000
MIN_OCCURRENCES = 3
MIN_DUR = 0.14          # below this a word is too short to characterise
PAD = 0.03


def _norm(w):
    return re.sub(r"[^a-z']", "", w.lower())


def collect(parts_dir, sections, model, librosa):
    """-> {word: [(section_index, audio), ...]} using ASR word timings per take."""
    bag = defaultdict(list)
    for k, sec in enumerate(sections, 1):
        p = os.path.join(parts_dir, f"sec_{sec['index']:03d}.mp3")
        if not os.path.isfile(p):
            continue
        y, _ = librosa.load(p, sr=SR, mono=True)
        segs, _ = model.transcribe(p, language="en", beam_size=5,
                                   condition_on_previous_text=False,
                                   word_timestamps=True)
        for s in segs:
            for w in (s.words or []):
                a, b = float(w.start), float(w.end)
                if b - a < MIN_DUR:
                    continue
                key = _norm(w.word)
                if len(key) < 3:
                    continue
                clip = y[int(max(0, a - PAD) * SR):int((b + PAD) * SR)]
                if len(clip) > int(0.05 * SR):
                    bag[key].append((sec["index"], clip, round(a, 2)))
        print(f"[oddword] collected {k}/{len(sections)}", flush=True)
    return bag


def dist(a, b, librosa, np):
    def mf(y):
        m = librosa.feature.mfcc(y=y, sr=SR, n_mfcc=13, hop_length=128)
        return (m - m.mean(axis=1, keepdims=True)) / (m.std(axis=1, keepdims=True) + 1e-9)
    D, _ = librosa.sequence.dtw(X=mf(a), Y=mf(b), metric="cosine")
    return float(D[-1, -1] / (len(a) / SR + len(b) / SR))


def analyse(bag, librosa, np, ratio=1.8):
    out = []
    for word, items in sorted(bag.items()):
        if len(items) < MIN_OCCURRENCES:
            continue
        n = len(items)
        M = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                d = dist(items[i][1], items[j][1], librosa, np)
                M[i, j] = M[j, i] = d
        med_to_peers = np.array([np.median([M[i, j] for j in range(n) if j != i])
                                 for i in range(n)])
        base = float(np.median(med_to_peers))
        if base <= 0:
            continue
        for i in range(n):
            r = float(med_to_peers[i] / base)
            if r >= ratio:
                out.append(dict(word=word, section=items[i][0] + 1, at=items[i][2],
                                ratio=round(r, 2), occurrences=n))
    return sorted(out, key=lambda x: -x["ratio"])


def main():
    ap = argparse.ArgumentParser(
        description="Flag words rendered unlike the voice's own other renderings.")
    ap.add_argument("--parts-dir", required=True)
    ap.add_argument("--sections-json", required=True)
    ap.add_argument("--ratio", type=float, default=1.8)
    ap.add_argument("--json-out")
    a = ap.parse_args()

    import numpy as np
    import librosa
    import readcheck as rc

    sections = json.load(open(a.sections_json, encoding="utf-8"))["sections"]
    bag = collect(a.parts_dir, sections, rc.load_asr(), librosa)
    usable = {w: v for w, v in bag.items() if len(v) >= MIN_OCCURRENCES}
    print(f"\n[oddword] {len(bag)} distinct words, {len(usable)} with "
          f"{MIN_OCCURRENCES}+ occurrences to compare against\n")

    hits = analyse(bag, librosa, np, a.ratio)
    if not hits:
        print(f"[oddword] nothing at or above {a.ratio}x its own baseline.")
    else:
        for h in hits:
            print(f"[oddword] {h['ratio']:5.2f}x  section {h['section']:<3} "
                  f"{h['at']:6.2f}s  “{h['word']}”  ({h['occurrences']} occurrences)")
        secs = sorted({h["section"] for h in hits})
        print(f"\n[oddword] {len(hits)} outlier(s) in {len(secs)} section(s): "
              f"{','.join(map(str, secs))}")
    if a.json_out:
        json.dump({"ratio": a.ratio, "hits": hits}, open(a.json_out, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
