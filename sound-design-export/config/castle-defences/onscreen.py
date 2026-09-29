#!/usr/bin/env python3
"""Score, per frame, whether the thing a bed names is actually on screen.

The fire bed ran 31.9 s over 2.9 s of drawn flame. That is measurable, so measure
it for every bed whose object is an EVENT rather than room tone. Weather, air and
stone-room tone are genuinely continuous and belong to the section; water,
flame, crowds and machinery start and stop on camera.

  water  — large flat blue/cyan region in the LOWER frame (sky is the same hue,
           so the upper frame is excluded outright)
  figures— dark ink strokes clustered mid-frame, the stick-figure signature
"""
import cv2, numpy as np
cap = cv2.VideoCapture("video.mp4"); fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
water, figs = [], []
while True:
    ok, fr = cap.read()
    if not ok: break
    s = cv2.resize(fr, (320, 180), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(s, cv2.COLOR_BGR2HSV)
    h, sat, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    blue = (h > 85) & (h < 115) & (sat > 45) & (v > 90)
    water.append(float(blue[80:].mean()))          # lower 55% only: sky excluded
    g = cv2.cvtColor(s, cv2.COLOR_BGR2GRAY)
    figs.append(float((g[40:160] < 90).mean()))
cap.release()
np.savez("onscreen.npz", water=np.array(water), figs=np.array(figs), fps=fps)
print("frames", len(water), "fps", fps)
