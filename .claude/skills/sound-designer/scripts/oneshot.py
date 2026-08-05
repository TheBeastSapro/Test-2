#!/usr/bin/env python3
"""oneshot.py — split a multi-hit library recording into single hits.

Library recordings are often takes, not samples. "Weapons, Armor, Medieval
Shield, Impact, Hit, Block, Sword Attack" is 3.23 s containing four separate
sword blows on a shield. Dropped whole onto a one-frame beat it reads as a slam
rather than a clash, and because its energy accumulates across four hits the
measured anchor lands 695 ms in, so the whole cluster is placed early too. That
is exactly what got reported as "not good" and then as "not an actual sfx" when
the replacement was a generic metal ring instead of a shield.

Splitting the take gives what was wanted in the first place: real sword-on-shield
clashes, one per file, each landing on its frame -- and four variants of it, which
the rotation needs anyway.

Usage:
  oneshot.py pal/impact_11.wav --out pal --name shield
  oneshot.py pal/forge_01.wav  --out pal --name anvil --max 3
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import soundfile as sf


def find_hits(x: np.ndarray, sr: int, rel: float = 0.30, gap: float = 0.10):
    """Attack positions: local rises above `rel` of peak, at least `gap` apart."""
    w = max(1, int(sr * 0.005))
    env = np.sqrt(np.convolve(x ** 2, np.ones(w) / w, mode="same"))
    peak = float(env.max())
    if peak <= 0:
        return [], env
    thresh = rel * peak
    hits, last = [], -10 ** 9
    above = env >= thresh
    for i in range(len(env)):
        if above[i] and i - last > int(sr * gap):
            # walk back to where this attack actually begins, so the slice does
            # not clip the front off the transient
            j = i
            floor = 0.06 * peak
            while j > 0 and env[j] > floor and i - j < int(sr * 0.05):
                j -= 1
            hits.append(j)
            last = i
    return hits, env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", required=True, help="output prefix, e.g. shield")
    ap.add_argument("--max", type=int, default=8)
    ap.add_argument("--tail-db", type=float, default=-38.0,
                    help="end a slice when it decays this far below its own peak")
    ap.add_argument("--peak", type=float, default=-3.0,
                    help="normalise each slice to this peak dBFS, matching palette.py")
    args = ap.parse_args()

    y, sr = sf.read(args.src, dtype="float32", always_2d=True)
    mono = y.mean(axis=1)
    hits, env = find_hits(mono, sr)
    if not hits:
        raise SystemExit(f"[oneshot] no hits found in {args.src}")
    os.makedirs(args.out, exist_ok=True)

    n = 0
    for k, start in enumerate(hits[:args.max]):
        nxt = hits[k + 1] if k + 1 < len(hits) else len(mono)
        seg_env = env[start:nxt]
        peak = float(seg_env.max()) if seg_env.size else 0.0
        if peak <= 0:
            continue
        # end where it has decayed, or at the next hit, whichever comes first
        floor = peak * (10 ** (args.tail_db / 20))
        below = np.where(seg_env < floor)[0]
        end = start + (int(below[0]) if below.size else len(seg_env))
        end = min(max(end, start + int(sr * 0.08)), nxt, len(mono))
        seg = y[start:end].copy()

        fade = min(int(sr * 0.030), len(seg) // 4)
        if fade > 0:
            seg[-fade:] *= np.linspace(1.0, 0.0, fade)[:, None]
        p = float(np.abs(seg).max())
        if p > 0:
            seg *= (10 ** (args.peak / 20)) / p
        n += 1
        dst = os.path.join(args.out, f"{args.name}_{n:02d}.wav")
        sf.write(dst, seg, sr, subtype="PCM_16")
        print(f"  {os.path.basename(dst):<16} {start/sr:6.3f}s -> {end/sr:6.3f}s "
              f"({(end-start)/sr:.3f}s)")
    print(f"[oneshot] {n} single hits from {os.path.basename(args.src)}")


if __name__ == "__main__":
    main()
