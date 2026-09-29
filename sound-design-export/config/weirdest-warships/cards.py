#!/usr/bin/env python3
"""Find the era title cards: near-white frame carrying a red progress bar."""
import cv2, numpy as np, sys
cap = cv2.VideoCapture("video.mp4")
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
score = []
i = 0
while True:
    ok, fr = cap.read()
    if not ok: break
    s = cv2.resize(fr, (320, 180), interpolation=cv2.INTER_AREA).astype(np.int16)
    b, g, r = s[:,:,0], s[:,:,1], s[:,:,2]
    red = ((r > 150) & (g < 110) & (b < 110)).mean()
    white = ((r > 235) & (g > 235) & (b > 235)).mean()
    score.append(red * 100 if white > 0.55 else 0.0)
    i += 1
cap.release()
sc = np.array(score)
on = sc > 0.9
runs, s0 = [], None
for k, m in enumerate(on):
    if m and s0 is None: s0 = k
    elif not m and s0 is not None:
        if (k - s0)/fps >= 0.4: runs.append((s0/fps, k/fps))
        s0 = None
if s0 is not None: runs.append((s0/fps, len(on)/fps))
print("ERA CARDS (white frame + red bar):")
for a, b in runs:
    print(f"  {a:8.3f} -> {b:8.3f}   ({b-a:.2f}s)")
