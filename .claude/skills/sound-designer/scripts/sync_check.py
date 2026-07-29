#!/usr/bin/env python3
"""sync_check.py — prove the SFX land on the picture, in numbers.

Every sync complaint so far was diagnosed by ear and fixed by guesswork, twice
in the wrong direction. This closes that loop: detect the actual onsets in the
rendered SFX stem, match each to the visual event it was cued to, and report
the error distribution against the frame duration.

A hit is "on" if it lands within half a frame of its event. At 24 fps that is
21 ms, which is roughly the threshold where audio and picture read as
simultaneous.

Usage:
  sync_check.py --sfx stems/sfx.wav --cues cues.json [--fps 24]
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sfx", required=True, help="the rendered sfx stem")
    ap.add_argument("--cues", required=True)
    ap.add_argument("--fps", type=float, default=24.0)
    args = ap.parse_args()

    cues = json.load(open(args.cues))
    want = np.array(sorted(c["at"] for c in cues.get("sfx_cues", [])))
    got = detect_onsets(args.sfx)
    if got.size == 0:
        raise SystemExit("[sync] no onsets detected in the sfx stem")

    frame = 1.0 / args.fps
    errs, matched = [], 0
    for t in want:
        d = got - t
        i = int(np.argmin(np.abs(d)))
        if abs(d[i]) <= 0.25:                 # within a quarter second = same hit
            errs.append(float(d[i]))
            matched += 1
    e = np.array(errs)
    if e.size == 0:
        raise SystemExit("[sync] could not match any cue to an onset")

    within_half = float(np.mean(np.abs(e) <= frame / 2) * 100)
    within_one = float(np.mean(np.abs(e) <= frame) * 100)
    print(f"[sync] {len(want)} cues, {got.size} onsets detected, {matched} matched")
    print(f"[sync] frame = {frame*1000:.1f} ms at {args.fps:g} fps")
    print(f"[sync] error   median {np.median(e)*1000:+7.1f} ms")
    print(f"[sync]         mean   {e.mean()*1000:+7.1f} ms   (a consistent sign here "
          f"means a systematic offset, not jitter)")
    print(f"[sync]         p90    {np.percentile(np.abs(e),90)*1000:7.1f} ms")
    print(f"[sync] within half a frame: {within_half:5.1f}%")
    print(f"[sync] within one frame:    {within_one:5.1f}%")
    if abs(np.median(e)) > frame / 2:
        print(f"[sync] VERDICT: systematic offset of {np.median(e)*1000:+.0f} ms — "
              f"shift every cue by {-np.median(e)*1000:+.0f} ms")
    elif within_one < 80:
        print("[sync] VERDICT: no systematic offset, but placement is scattered — "
              "the cue times themselves disagree with the picture")
    else:
        print("[sync] VERDICT: locked to picture")


if __name__ == "__main__":
    main()
