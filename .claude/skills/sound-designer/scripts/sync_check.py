#!/usr/bin/env python3
"""sync_check.py — prove the SFX land on the picture, in numbers.

Every sync complaint was once diagnosed by ear and fixed by guesswork, twice in
the wrong direction. This closes that loop: detect the actual onsets in the
rendered SFX stem, match each cue to one, and report the error against frame
duration.

Two things it deliberately does NOT do, both learned the hard way:

  * It does not let two cues claim the same onset. Nearest-onset matching with
    reuse cross-assigns neighbours in a dense mix and reports scatter that is
    really just bookkeeping.
  * It does not score the companion layers of a stack against the cue grid as
    if they were independent events. A strike is a swish 130 ms early plus a
    body thud 35 ms late; those offsets ARE the design. They are reported
    separately, marked as layers.

A hit is "on" if it lands within half a frame of its event -- 21 ms at 24 fps,
roughly the threshold where audio and picture read as simultaneous.

Usage:
  sync_check.py --sfx stems/sfx.wav --cues cues.json [--fps 24] [--by-tier]
"""
from __future__ import annotations

import argparse
import json

import numpy as np


def detect_onsets(path: str, sr: int = 22050) -> np.ndarray:
    import librosa
    y, _ = librosa.load(path, sr=sr, mono=True)
    return librosa.onset.onset_detect(y=y, sr=sr, units="time", backtrack=True,
                                      pre_max=3, post_max=3, pre_avg=5,
                                      post_avg=5, delta=0.05, wait=2)


def match(cues: list[dict], onsets: np.ndarray, window: float = 0.25) -> dict[int, float]:
    """One-to-one nearest matching: closest pairs win, no onset used twice.

    Letting cues share an onset is what made the last report look scattered --
    in a mix with a hit every two seconds, two neighbouring cues would both
    claim the louder of their two onsets and one of them would post a 200 ms
    error it did not have.
    """
    pairs = []
    for i, c in enumerate(cues):
        d = onsets - c["at"]
        for j in np.where(np.abs(d) <= window)[0]:
            pairs.append((abs(float(d[j])), float(d[j]), i, int(j)))
    pairs.sort(key=lambda p: p[0])
    used_c: set[int] = set()
    used_o: set[int] = set()
    out: dict[int, float] = {}
    for _, err, i, j in pairs:
        if i in used_c or j in used_o:
            continue
        used_c.add(i)
        used_o.add(j)
        out[i] = err
    return out


def report(name: str, errs: np.ndarray, frame: float, indent: str = ""):
    if errs.size == 0:
        print(f"{indent}{name:<11} no matches")
        return
    half = float(np.mean(np.abs(errs) <= frame / 2) * 100)
    one = float(np.mean(np.abs(errs) <= frame) * 100)
    print(f"{indent}{name:<11} n={errs.size:<4} median {np.median(errs)*1000:+7.1f} ms   "
          f"p90 {np.percentile(np.abs(errs), 90)*1000:6.1f} ms   "
          f"<half {half:5.1f}%   <one {one:5.1f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sfx", required=True, help="the rendered sfx stem")
    ap.add_argument("--cues", required=True)
    ap.add_argument("--fps", type=float, default=24.0)
    ap.add_argument("--by-tier", action="store_true",
                    help="break the numbers down per cue tier")
    args = ap.parse_args()

    cues = sorted(json.load(open(args.cues)).get("sfx_cues", []),
                  key=lambda c: c["at"])
    if not cues:
        raise SystemExit("[sync] no sfx cues in the sheet")
    got = detect_onsets(args.sfx)
    if got.size == 0:
        raise SystemExit("[sync] no onsets detected in the sfx stem")

    frame = 1.0 / args.fps
    m = match(cues, got)
    prim = [i for i in m if not cues[i].get("layer")]
    lay = [i for i in m if cues[i].get("layer")]
    n_prim = sum(1 for c in cues if not c.get("layer"))

    print(f"[sync] {len(cues)} cues ({n_prim} primary, {len(cues) - n_prim} stack "
          f"layers), {got.size} onsets detected, {len(m)} matched one-to-one")
    print(f"[sync] frame = {frame*1000:.1f} ms at {args.fps:g} fps")
    if not prim:
        raise SystemExit("[sync] could not match any primary cue")
    e = np.array([m[i] for i in prim])
    report("primary", e, frame, "[sync] ")
    if lay:
        report("layers", np.array([m[i] for i in lay]), frame, "[sync] ")

    if args.by_tier:
        print("[sync] by tier:")
        for t in ("hero_boom", "hero_hit", "impact", "whoosh", "swish", "pop"):
            idx = [i for i in prim if cues[i].get("tier") == t]
            if idx:
                report(t, np.array([m[i] for i in idx]), frame, "[sync]   ")

    med = float(np.median(e))
    within_one = float(np.mean(np.abs(e) <= frame) * 100)
    print(f"[sync] coverage: {len(prim) / n_prim * 100:.0f}% of primary cues "
          f"produced a detectable onset within 250 ms")
    if abs(med) > frame / 2:
        print(f"[sync] VERDICT: systematic offset of {med*1000:+.0f} ms — "
              f"shift every cue by {-med*1000:+.0f} ms")
    elif within_one < 80:
        print("[sync] VERDICT: no systematic offset, but placement is scattered — "
              "the cue times themselves disagree with the picture")
    else:
        print("[sync] VERDICT: locked to picture")


if __name__ == "__main__":
    main()
