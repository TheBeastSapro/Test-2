#!/usr/bin/env python3
"""Pick the header take that matches how the body already says the word.

The body sections say these names correctly — the read-check passed every one —
so they are a reference in the same voice, same session, same settings. A bare
two-word header is where ASR invents ("Maginot Line" -> "Imagine a line"), so
its SPELLING proves nothing. The acoustics do.

The distance number alone means nothing either, which is why this measures a
BASELINE first: the same word, spoken correctly, in two different body
sections. That is the noise floor for "same pronunciation, different context".
A candidate inside that floor is indistinguishable from correct; one well
outside it is really saying something else.
"""
import sys, numpy as np, librosa
sys.path.insert(0, "/home/user/Test-2/.claude/skills/explaintory-voiceover/scripts")
from readcheck import load_asr

P = ".vo_Every_Failed_Weapon_in_History_Explained/parts"
SR = 16000
model = load_asr()


def load(path, a=None, b=None):
    y, _ = librosa.load(path, sr=SR, mono=True)
    return y if a is None else y[int(a * SR):int(b * SR)]


def cut_word(path, stems):
    """Cut the first word matching any stem, with a little air either side."""
    segs, _ = model.transcribe(path, language="en", beam_size=5,
                               condition_on_previous_text=False, word_timestamps=True)
    for s in segs:
        for w in (s.words or []):
            t = w.word.strip().lower().strip(".,'\"-")
            if any(t.startswith(st) for st in stems):
                return load(path, max(0, w.start - 0.05), w.end + 0.05), w.word.strip()
    return None, None


def dist(a, b):
    def mf(y):
        m = librosa.feature.mfcc(y=y, sr=SR, n_mfcc=13)
        return (m - m.mean(axis=1, keepdims=True)) / (m.std(axis=1, keepdims=True) + 1e-9)
    D, _ = librosa.sequence.dtw(X=mf(a), Y=mf(b), metric="cosine")
    return float(D[-1, -1] / (len(a) / SR + len(b) / SR))


JOBS = [
    ("Maginot", ["magi", "magg", "imag", "mazh"], [25, 30],
     {"original (plain spelling)": f"{P}/sec_022.mp3.pre-regen",
      "MA-zhee-noh":              f"{P}/sec_022.cand-MAzheenoh.mp3",
      "Mazheeno":                 f"{P}/sec_022.cand-lex_maginot.mp3",
      "mah-ZHEE-noh":             f"{P}/sec_022.cand-lex_maginot2.mp3"}),
    ("scythed", ["scyth", "syth", "seith", "sithe"], [8, 10],
     {"original (plain spelling)": f"{P}/sec_006.mp3.pre-regen",
      "sythed":                    f"{P}/sec_006.cand-sythed.mp3"}),
]

for word, stems, ref_secs, cands in JOBS:
    print(f"\n=== {word} ===")
    refs = []
    for n in ref_secs:
        y, txt = cut_word(f"{P}/sec_{n-1:03d}.mp3", stems)
        if y is not None:
            refs.append((n, y, txt))
            print(f"  reference  body sec {n}: ASR wrote {txt!r}")
    if len(refs) < 2:
        print("  SKIP — need two body references to compute a baseline")
        continue

    floor = dist(refs[0][1], refs[1][1])
    print(f"  BASELINE (body sec {refs[0][0]} vs body sec {refs[1][0]}): {floor:.2f}")
    print("  -> anything at or below this is indistinguishable from the body\n")

    scored = []
    for name, path in cands.items():
        y, txt = cut_word(path, stems)
        if y is None:
            y, txt = load(path), "(no match — whole take)"
        d = float(np.mean([dist(y, r) for _, r, _ in refs]))
        scored.append((d, name, txt))
    for d, name, txt in sorted(scored):
        verdict = "WITHIN baseline" if d <= floor else f"{d/floor:.2f}x baseline"
        print(f"  {d:7.2f}  {name:<26} ASR {txt!r:<14} {verdict}")
    print(f"\n  WINNER: {sorted(scored)[0][1]}")
