#!/usr/bin/env python3
"""visual_redraw.py — find the beats by what the animation redraws.

This replaces optical-flow motion ranking for hand-drawn/animated footage, and
it exists because ranking by flow got the important beats wrong on a real video.

Explainer animation is drawn on held frames: nothing changes for a beat, then a
new pose appears. So the per-frame difference is almost exactly zero except at
redraws. Measured over 22 s of the sword video, only 15 of 528 frames are
non-zero and the median difference is 0.00000 -- the signal is effectively
binary, where a flow-based motion curve produced a continuous 391-event mush
that had to be percentile-thresholded and still misranked things.

It also classifies for free, because the size of the change says what changed:

    >= 0.15    the whole frame was redrawn        -> a shot change
    0.02-0.15  a figure took a new pose           -> an action beat
    0.004-0.02 a small element appeared           -> a caption or label

That mattered. A khopesh going into a chest is a *small* movement, so flow
ranked it below a camera pan and it was cast as a generic "movement" swish; the
hook catching a shield was cast as a caption tick. Both are unambiguous
mid-band redraws. Validated against twelve beats read off a contact sheet by
eye: eleven matched, ten of them inside 130 ms.

Output uses the same vocabulary as visual_events.py so the two are drop-in
comparable:
  {"fps","duration","events":[{"t","strength","kind":"cut"|"action"|"element"}]}

Usage:
  visual_redraw.py video.mp4 -o redraw.json [--cut 0.15] [--action 0.02]
"""
from __future__ import annotations

import argparse
import json

import cv2
import numpy as np


def redraw_curve(path: str, width: int = 320, height: int = 180):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    prev, out = None, []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(cv2.resize(frame, (width, height),
                                    interpolation=cv2.INTER_AREA),
                         cv2.COLOR_BGR2GRAY).astype(np.int16)
        out.append(0.0 if prev is None else
                   float(np.abs(g - prev).mean()) / 255.0)
        prev = g
    cap.release()
    return np.array(out), fps


def events(curve: np.ndarray, fps: float, floor: float,
           cut: float, action: float):
    """Cluster consecutive changed frames into one beat, at its peak frame.

    A redraw can smear over two or three frames when the encoder interpolates or
    the drawing cross-fades; taking the peak of each run puts the beat on the
    frame where most of the change happened rather than on its leading edge.
    """
    ev, i, n = [], 0, curve.size
    while i < n:
        if curve[i] >= floor:
            j = i
            while j + 1 < n and curve[j + 1] >= floor:
                j += 1
            k = i + int(np.argmax(curve[i:j + 1]))
            v = float(curve[k])
            kind = "cut" if v >= cut else ("action" if v >= action else "element")
            ev.append({"t": round(k / fps, 4), "strength": round(v, 5),
                       "kind": kind})
            i = j + 1
        else:
            i += 1
    return ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--floor", type=float, default=0.004,
                    help="ignore changes below this (default 0.004)")
    ap.add_argument("--cut", type=float, default=0.15,
                    help="at or above this the whole frame changed")
    ap.add_argument("--action", type=float, default=0.02,
                    help="at or above this a figure moved")
    args = ap.parse_args()

    curve, fps = redraw_curve(args.video)
    ev = events(curve, fps, args.floor, args.cut, args.action)
    dur = curve.size / fps
    by = {k: sum(1 for e in ev if e["kind"] == k)
          for k in ("cut", "action", "element")}
    print(f"[redraw] {curve.size} frames at {fps:.2f} fps ({dur:.0f}s); "
          f"{int((curve >= args.floor).sum())} changed")
    print(f"[redraw] {len(ev)} beats: {by['cut']} cuts, {by['action']} actions, "
          f"{by['element']} elements — one per {dur/max(1,len(ev)):.2f}s")
    with open(args.out, "w") as f:
        json.dump({"fps": fps, "duration": dur, "events": ev}, f, indent=1)
    print(f"[redraw] wrote {args.out}")


if __name__ == "__main__":
    main()
