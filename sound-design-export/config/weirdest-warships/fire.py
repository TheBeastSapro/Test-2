#!/usr/bin/env python3
"""Find the frames where the animation draws a fireball (orange/yellow burst)."""
import cv2, numpy as np
cap = cv2.VideoCapture("video.mp4")
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
score = []
while True:
    ok, fr = cap.read()
    if not ok: break
    s = cv2.resize(fr, (320, 180), interpolation=cv2.INTER_AREA).astype(np.int16)
    b, g, r = s[:,:,0], s[:,:,1], s[:,:,2]
    fire = ((r > 215) & (g > 95) & (g < 205) & (b < 95)).mean()
    score.append(float(fire))
cap.release()
sc = np.array(score)
np.save("fire.npy", sc)
on = sc > 0.004
runs, s0 = [], None
for k, m in enumerate(on):
    if m and s0 is None: s0 = k
    elif not m and s0 is not None:
        if (k - s0)/fps >= 0.15: runs.append((s0/fps, k/fps, sc[s0:k].max()))
        s0 = None
if s0 is not None: runs.append((s0/fps, len(on)/fps, sc[s0:].max()))
print(f"FIREBALLS ({len(runs)} runs):")
for a, b_, pk in runs:
    print(f"  {a:8.3f} -> {b_:8.3f}  ({b_-a:5.2f}s)  peak area {pk*100:.2f}%")
