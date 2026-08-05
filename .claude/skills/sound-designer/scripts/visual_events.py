#!/usr/bin/env python3
"""visual_events.py — find every frame worth putting a sound on.

Scene detection alone is the wrong tool for this job. It finds *shot changes*,
so it misses the thing an animated explainer is full of: motion inside a held
shot — a label sliding in, a sword coming down, a stick figure being struck.
Those are most of the sound design and a cut list contains none of them.

So two detectors, both frame-accurate:

  * PySceneDetect (ContentDetector) for real shot changes.
  * A per-frame motion curve from OpenCV for everything else. Peaks in the
    curve are elements arriving and actions happening; their prominence
    separates a big reveal from a caption fading up.

Every timestamp comes back on a frame boundary, because a hit placed between
frames is a hit that reads as late.

Usage:
  visual_events.py --video in.mp4 --out events.json [--fps-scale 240]
"""
from __future__ import annotations

import argparse
import json

import cv2
import numpy as np


def scene_cuts(path: str) -> list[float]:
    from scenedetect import open_video, SceneManager
    from scenedetect.detectors import ContentDetector
    video = open_video(path)
    sm = SceneManager()
    sm.add_detector(ContentDetector(threshold=27.0, min_scene_len=6))
    sm.detect_scenes(video, show_progress=False)
    return [s[0].get_seconds() for s in sm.get_scene_list()]


def motion_curve(path: str, width: int = 240):
    """Per-frame mean absolute difference, plus the frame times."""
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    prev, vals = None, []
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(cv2.resize(fr, (width, int(width * fr.shape[0] / fr.shape[1]))),
                         cv2.COLOR_BGR2GRAY).astype(np.float32)
        vals.append(0.0 if prev is None else float(np.abs(g - prev).mean()))
        prev = g
    cap.release()
    v = np.asarray(vals)
    return v, fps


def find_events(v: np.ndarray, fps: float, min_gap: float = 0.30):
    """Local maxima in the motion curve, with a prominence for each."""
    gap = max(1, int(min_gap * fps))
    floor = float(np.median(v)) + 0.6
    idx = []
    for i in range(1, len(v) - 1):
        if v[i] < floor or v[i] < v[i - 1] or v[i] < v[i + 1]:
            continue
        lo = max(0, i - gap)
        if v[i] < v[lo:i].max(initial=0.0):
            continue
        idx.append(i)
    # thin: keep the strongest inside any min_gap window
    kept = []
    for i in idx:
        if kept and i - kept[-1] < gap:
            if v[i] > v[kept[-1]]:
                kept[-1] = i
            continue
        kept.append(i)
    scale = float(v.max()) or 1.0
    return [(i / fps, float(v[i]) / scale) for i in kept]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fps-scale", type=int, default=240)
    args = ap.parse_args()

    cuts = scene_cuts(args.video)
    print(f"[visual] {len(cuts)} shot changes (PySceneDetect)")

    v, fps = motion_curve(args.video, args.fps_scale)
    ev = find_events(v, fps)
    print(f"[visual] {len(ev)} motion events across {len(v)/fps:.0f}s at {fps:.2f} fps")

    # tag each motion event: is it a shot change, or action inside a shot?
    out = []
    for t, s in ev:
        is_cut = any(abs(t - c) < 0.10 for c in cuts)
        out.append({"t": round(t, 4), "strength": round(s, 4),
                    "kind": "cut" if is_cut else "action"})
    for c in cuts:                       # cuts the motion curve may have merged
        if not any(abs(c - e["t"]) < 0.10 for e in out):
            out.append({"t": round(c, 4), "strength": 1.0, "kind": "cut"})
    out.sort(key=lambda e: e["t"])

    n_cut = sum(1 for e in out if e["kind"] == "cut")
    print(f"[visual] -> {n_cut} cuts + {len(out)-n_cut} in-shot actions = {len(out)} events, "
          f"one per {(len(v)/fps)/max(len(out),1):.1f}s")
    json.dump({"fps": fps, "duration": len(v) / fps, "events": out},
              open(args.out, "w"), indent=1)
    print(f"[visual] wrote {args.out}")


if __name__ == "__main__":
    main()
