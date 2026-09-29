#!/usr/bin/env python3
"""Find (a) era-banner text changes in the top strip and (b) white presenter shots."""
import cv2, numpy as np, json, sys

cap = cv2.VideoCapture(sys.argv[1])
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
prev = None
diffs = []      # banner strip diff per frame
white = []      # full-frame whiteness
i = 0
while True:
    ok, fr = cap.read()
    if not ok: break
    small = cv2.resize(fr, (480, 270), interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.int16)
    band = g[0:14, 60:420]                       # the header text strip
    diffs.append(0.0 if prev is None else float(np.abs(band - prev).mean())/255.0)
    prev = band
    body = g[16:270, :]
    white.append((float(body.mean()), float(body.std())))
    i += 1
cap.release()
np.save("/home/user/work/warships/banner_diff.npy", np.array(diffs))
np.save("/home/user/work/warships/whiteness.npy", np.array(white))
d = np.array(diffs)
print(f"frames={len(d)} fps={fps} median={np.median(d):.5f} p99={np.percentile(d,99):.5f}")
# banner changes: local maxima above a hard floor, min 8 s apart
idx = np.argsort(-d)
picked = []
for j in idx:
    if d[j] < 0.010: break
    if all(abs(j - p) > fps*8 for p in picked):
        picked.append(int(j))
picked.sort()
print("BANNER CHANGES:")
for p in picked: print(f"  {p/fps:8.3f}s  strength {d[p]:.4f}")
# white shots: mean>245 and std<12 sustained >=0.7 s
w = np.array(white)
mask = (w[:,0] > 244) & (w[:,1] < 14)
runs, s = [], None
for k, m in enumerate(mask):
    if m and s is None: s = k
    elif not m and s is not None:
        if (k-s)/fps >= 0.6: runs.append((s/fps, k/fps))
        s = None
if s is not None and (len(mask)-s)/fps >= 0.6: runs.append((s/fps, len(mask)/fps))
print("WHITE PRESENTER SHOTS:")
for a,b in runs: print(f"  {a:8.3f} -> {b:8.3f}  ({b-a:.2f}s)")
