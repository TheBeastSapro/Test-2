#!/usr/bin/env python3
"""Score drawn flame area per frame, so a fire bed can be cut to the shots that
have fire in them. Same idea as the warships job's fire.py: the animation's
flame palette is saturated orange/red, which nothing else in this video's
palette is (the red cards are flat crimson with no yellow, and are excluded by
requiring both a hot-orange and a yellow band)."""
import cv2, numpy as np
cap = cv2.VideoCapture("video.mp4"); fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
score = []
while True:
    ok, fr = cap.read()
    if not ok: break
    s = cv2.resize(fr, (320, 180), interpolation=cv2.INTER_AREA).astype(np.int16)
    b, g, r = s[:, :, 0], s[:, :, 1], s[:, :, 2]
    orange = (r > 180) & (g > 60) & (g < 175) & (b < 90)      # flame body
    yellow = (r > 225) & (g > 175) & (b < 130)                 # flame core
    score.append(float((orange.mean() * 0.7 + yellow.mean() * 0.3)))
cap.release()
sc = np.array(score); np.save("fire.npy", sc)
thr = 0.030
on = sc > thr
runs, s0 = [], None
for k, m in enumerate(on):
    if m and s0 is None: s0 = k
    elif not m and s0 is not None:
        if (k - s0) / fps >= 0.4: runs.append((s0 / fps, k / fps, sc[s0:k].max()))
        s0 = None
if s0 is not None: runs.append((s0 / fps, len(on) / fps, sc[s0:].max()))
print(f"flame area > {thr}: {len(runs)} runs")
for a, b_, pk in runs:
    print(f"  {a:8.3f} -> {b_:8.3f}  ({b_-a:5.2f}s)  peak {pk:.3f}")
