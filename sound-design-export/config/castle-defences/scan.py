#!/usr/bin/env python3
"""One decode pass: era-card score, banner-strip fingerprint, ink centroid."""
import cv2, numpy as np, json

cap = cv2.VideoCapture("video.mp4")
fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
card, banner, cx, ink = [], [], [], []
while True:
    ok, fr = cap.read()
    if not ok: break
    s = cv2.resize(fr, (320, 180), interpolation=cv2.INTER_AREA).astype(np.int16)
    b, g, r = s[:, :, 0], s[:, :, 1], s[:, :, 2]
    red   = ((r > 150) & (g < 110) & (b < 110)).mean()
    white = ((r > 235) & (g > 235) & (b > 235)).mean()
    card.append(red * 100 if white > 0.55 else 0.0)
    # banner strip: top 12% of the frame, downsampled signature
    strip = cv2.cvtColor(s[:22, :, :].astype(np.uint8), cv2.COLOR_BGR2GRAY)
    banner.append(cv2.resize(strip, (40, 6), interpolation=cv2.INTER_AREA).astype(np.int16))
    # ink centroid over the body of the frame (dark pixels), for pan decisions
    body = cv2.cvtColor(s[22:, :, :].astype(np.uint8), cv2.COLOR_BGR2GRAY)
    dark = body < 110
    n = dark.sum()
    cx.append(float(np.argwhere(dark)[:, 1].mean() / 320.0) if n > 40 else np.nan)
    ink.append(float(n) / dark.size)
cap.release()

banner = np.array(banner, dtype=np.int16)
bdiff = np.concatenate([[0.0], np.abs(np.diff(banner, axis=0)).mean(axis=(1, 2)) / 255.0])
np.savez("scan.npz", card=np.array(card), bdiff=bdiff,
         cx=np.array(cx), ink=np.array(ink), fps=fps)
print("frames", len(card), "fps", fps)
