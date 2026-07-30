#!/usr/bin/env python3
"""palette.py — turn a folder of downloaded SFX into hit files fit to place.

Placing library files straight out of the CDN is what makes a mix sound cheap,
for two reasons that are both measurable rather than matters of taste:

  * Peak level is inconsistent. Across an 81-file palette pulled for one video
    the spread was 15 dB (+12.3 to -2.8 dB of correction needed). Until that is
    flattened, a cue sheet that says "-8 dB" means nothing.
  * Many files start 100-300 ms before the attack. Placing such a file "at" a
    cue puts the sound late by exactly that much, and the mixer's transient
    search is then guessing at something that should have been trimmed.

Ambience beds are exempt from both: they have no attack to find, and peak
normalising a two-minute room tone just amplifies its loudest gust.

Input is a directory of audio named `<category>_<nn>.<ext>`, e.g. impact_03.mp3.
Output is `<category>_<nn>.wav`, plus palette_manifest.json listing each
category. Categories are yours to choose; the placer only needs them to agree
with its own mapping. The set used on the sword video was:

  pop swish whoosh impact boom forge draw armor amb

Usage:
  palette.py --raw pal_raw --out pal [--peak -3.0] [--bed-prefix amb]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess

SR = 48000


def run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def peak_db(path: str) -> float:
    p = subprocess.run(["ffmpeg", "-v", "info", "-i", path, "-af", "volumedetect",
                        "-f", "null", "-"], capture_output=True, text=True)
    for line in p.stderr.splitlines():
        if "max_volume:" in line:
            return float(line.split("max_volume:")[1].strip().split()[0])
    return 0.0


def anchor_offset(path: str, pct: float = 0.15, window: float = 1.0,
                  cap: float = 0.75, deadband: float = 0.04) -> float:
    """Seconds from the file's start to the moment it is *perceived* to happen.

    Trimming to the first audible sample is right for a pop and wrong for a
    whoosh. Measured across an 81-file palette, the sync error per tier on a
    real render tracked each category's rise time almost exactly: pops (2 ms
    rise) landed +3 ms, metal impacts (28 ms) landed -10 ms, swishes (93 ms)
    landed +39 ms and whooshes (411 ms) +28 ms. Gradual sounds were arriving
    late by roughly their own rise time.

    So each file carries its own anchor and is placed so that the anchor, not
    the file start, lands on the cue. Per file rather than per category on
    purpose: the spread *inside* a category is what produces the p90 outliers.

    The anchor is where the first `pct` of the file's energy has accumulated,
    not where it first reaches a fraction of its peak. The peak-relative
    version breaks on anything with more than one hit: on five blacksmith
    files it locked onto the loudest *late* hammer strike and reported a median
    rise of 749 ms, where energy accumulation correctly finds the first strike
    at 127 ms. Same story for sustained rustles with a late peak.

    `deadband` is subtracted before the value is used, because for an impulsive
    sound the attack IS the perceived moment: its 15%-energy figure is just the
    tail of the transient, and compensating for it moves the hit early. On the
    first anchored render that cost 28 ms on impacts and 36 ms on pops. Only
    rise time beyond one frame is real ramp worth compensating for.

    `cap` is 750 ms because a 500 ms cap silently truncated three long "airy"
    whooshes whose real rise is 598-759 ms, leaving them 100-260 ms late and
    contributing most of that tier's p90 error.
    """
    try:
        import numpy as np
        import soundfile as sf
    except ImportError:
        return 0.0
    y, sr = sf.read(path, dtype="float32", always_2d=True)
    if not len(y):
        return 0.0
    mono = y.mean(axis=1)
    n = max(1, int(sr * 0.005))                       # 5 ms rms window
    env = np.sqrt(np.convolve(mono ** 2, np.ones(n) / n, mode="same"))
    power = env[:int(sr * window)] ** 2
    cum = np.cumsum(power)
    if not cum.size or cum[-1] <= 0:
        return 0.0
    rise = float(int(np.argmax(cum >= pct * cum[-1])) / sr)
    return max(0.0, min(cap, rise - deadband))


def lead_silence(path: str, thresh_db: float = -45.0, cap: float = 1.0) -> float:
    """Seconds of silence before the first real sample. Capped, because a file
    that is quiet for more than a second is not a hit with a late attack -- it
    is a different kind of sound and should not be shifted."""
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-af",
         f"silencedetect=noise={thresh_db}dB:d=0.02", "-f", "null", "-"],
        capture_output=True, text=True)
    start = end = None
    for line in p.stderr.splitlines():
        if "silence_start:" in line:
            v = float(line.split("silence_start:")[1].strip().split()[0])
            if start is None and v < 0.01:
                start = v
        elif "silence_end:" in line and start is not None and end is None:
            end = float(line.split("silence_end:")[1].strip().split()[0])
    return max(0.0, min(end, cap)) if end is not None else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True, help="dir of downloaded sfx")
    ap.add_argument("--out", required=True, help="dir to write prepared wavs")
    ap.add_argument("--peak", type=float, default=-3.0,
                    help="normalise every hit to this peak dBFS (default -3)")
    ap.add_argument("--bed-prefix", default="amb",
                    help="category left untouched: no trim, no normalise")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    files = sorted(f for f in glob.glob(os.path.join(args.raw, "*"))
                   if os.path.splitext(f)[1].lower() in
                   (".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"))
    if not files:
        raise SystemExit(f"[palette] nothing to prepare in {args.raw}")

    manifest: dict[str, list[str]] = {}
    anchors: dict[str, float] = {}
    for src in files:
        name = os.path.splitext(os.path.basename(src))[0]
        cat = name.rsplit("_", 1)[0] if "_" in name else name
        dst = os.path.join(args.out, f"{name}.wav")

        if cat == args.bed_prefix:
            run(["ffmpeg", "-v", "error", "-y", "-i", src, "-ac", "2",
                 "-ar", str(SR), "-c:a", "pcm_s16le", dst])
            manifest.setdefault(cat, []).append(name)
            print(f"  {name:<12} bed, untouched")
            continue

        trim = lead_silence(src)
        gain = args.peak - peak_db(src)
        cmd = [FFMPEG := "ffmpeg", "-v", "error", "-y"]
        if trim > 0.005:
            cmd += ["-ss", f"{trim:.3f}"]
        cmd += ["-i", src, "-af", f"volume={gain:.2f}dB", "-ac", "2",
                "-ar", str(SR), "-c:a", "pcm_s16le", dst]
        run(cmd)
        manifest.setdefault(cat, []).append(name)
        anchors[name] = round(anchor_offset(dst), 4)
        note = f"trimmed {trim*1000:.0f} ms" if trim > 0.005 else ""
        print(f"  {name:<12} {gain:+6.1f} dB  anchor {anchors[name]*1000:4.0f} ms  {note}")

    for v in manifest.values():
        v.sort()
    with open(os.path.join(args.out, "palette_manifest.json"), "w") as f:
        json.dump({**manifest, "_anchors": anchors}, f, indent=1)

    total = sum(len(v) for v in manifest.values())
    print(f"[palette] {total} files ready across {len(manifest)} categories")
    for k, v in sorted(manifest.items()):
        print(f"  {k:<8} {len(v):>3}")


if __name__ == "__main__":
    main()
