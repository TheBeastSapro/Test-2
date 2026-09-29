#!/usr/bin/env python3
"""measure_ref.py — measure a finished reference mix.

Answers, from the audio itself and never from a listening model:
  * programme loudness (LUFS / LRA / true peak)
  * the loudness envelope's shape — where the music-only floor sits versus the
    voice-over-music body, i.e. the real bed-to-voice ratio
  * hard dropouts (deliberate dead air)
  * how often the bed level changes materially — a proxy for cue changes

Separating bed from voice in a *finished mix* is inference, not fact: the
quietest sustained non-silent passages are taken to be music-only. That holds
for a ducked explainer, where the bed plays alone between lines. Given a
separate VO stem the same script measures the bed directly instead — pass
--vo and it reports the true figure.

Usage:
  measure_ref.py --audio ref.wav [--vo vo.wav] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

import numpy as np

from common import FFMPEG, run, decode_mono_pcm, media_info, fmt_ts


def db(x):
    return 20 * np.log10(np.maximum(x, 1e-9))


def envelope(path, win=0.40, hop=0.10):
    """Windowed RMS in dBFS -> (times, dB)."""
    x, sr = decode_mono_pcm(path, 16000)
    if x.size == 0:
        sys.exit(f"[measure] no audio in {path}")
    w, h = int(win * sr), int(hop * sr)
    n = 1 + max(0, (len(x) - w) // h)
    t = np.arange(n) * hop
    e = np.empty(n)
    for i in range(n):
        seg = x[i * h: i * h + w]
        e[i] = np.sqrt(np.mean(seg.astype(np.float64) ** 2)) if seg.size else 0.0
    return t, db(e), sr


def loudness(path):
    res = run([FFMPEG, "-hide_banner", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"])
    tail = res.stderr[-2500:]
    def grab(label):
        m = re.search(rf"{label}:\s*(-?[0-9.]+)", tail)
        return float(m.group(1)) if m else None
    return {"integrated_lufs": grab("I"), "lra_lu": grab("LRA"), "true_peak_dbfs": grab("Peak")}


def dropouts(path, thresh=-50.0, min_d=0.35):
    res = run([FFMPEG, "-hide_banner", "-i", path,
               "-af", f"silencedetect=noise={thresh}dB:d={min_d}", "-f", "null", "-"])
    starts, spans = [], []
    for line in res.stderr.splitlines():
        s = re.search(r"silence_start:\s*(-?[0-9.]+)", line)
        e = re.search(r"silence_end:\s*(-?[0-9.]+)", line)
        if s:
            starts.append(float(s.group(1)))
        if e and starts:
            spans.append((round(max(0.0, starts.pop()), 2), round(float(e.group(1)), 2)))
    return spans


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True, help="the finished mix")
    ap.add_argument("--vo", help="separate VO stem — makes the bed figure exact")
    ap.add_argument("--json")
    args = ap.parse_args()

    info = media_info(args.audio)
    print(f"[measure] {args.audio} · {fmt_ts(info['duration'])}")

    loud = loudness(args.audio)
    print(f"[measure] programme: {loud['integrated_lufs']} LUFS · LRA {loud['lra_lu']} LU · "
          f"true peak {loud['true_peak_dbfs']} dBFS")

    t, e, sr = envelope(args.audio)
    live = e[e > -55]                       # ignore hard silence
    p = {q: float(np.percentile(live, q)) for q in (5, 10, 25, 50, 75, 90, 95)}
    print("[measure] loudness envelope (dBFS, silence excluded):")
    for q in (5, 10, 25, 50, 75, 90, 95):
        print(f"            p{q:<2} {p[q]:7.1f}")

    # music-only floor vs the voice+music body
    floor, body = p[10], p[50]
    bed_ratio = floor - body
    print(f"[measure] music-only floor  p10 = {floor:.1f} dBFS")
    print(f"[measure] voice+music body  p50 = {body:.1f} dBFS")
    print(f"[measure] => bed sits {bed_ratio:.1f} dB under the programme "
          f"({100 * 10 ** (bed_ratio / 20):.1f}% in linear terms)")

    dr = dropouts(args.audio)
    total_dr = sum(b - a for a, b in dr)
    print(f"[measure] hard dropouts (< -50 dBFS, >0.35 s): {len(dr)} "
          f"totalling {total_dr:.1f}s ({100*total_dr/max(info['duration'],1):.1f}% of runtime)")
    for a, b in dr[:12]:
        print(f"            {fmt_ts(a)} – {fmt_ts(b)}  ({b-a:.2f}s)")
    if len(dr) > 12:
        print(f"            … and {len(dr)-12} more")

    # bed-level changes: how often the quiet floor shifts materially
    win = int(15 / 0.10)                    # 15 s blocks
    blocks = [e[i:i + win] for i in range(0, len(e), win)]
    floors = [float(np.percentile(b[b > -55], 10)) for b in blocks if (b > -55).any()]
    shifts = sum(1 for i in range(1, len(floors)) if abs(floors[i] - floors[i - 1]) >= 3.0)
    print(f"[measure] bed-floor shifts >=3 dB across 15 s blocks: {shifts} "
          f"(rough proxy for cue changes over {fmt_ts(info['duration'])})")

    out = {
        "file": args.audio, "duration": info["duration"], "loudness": loud,
        "envelope_percentiles_dbfs": p,
        "music_floor_dbfs": floor, "programme_body_dbfs": body,
        "bed_under_programme_db": bed_ratio,
        "bed_percent_linear": 100 * 10 ** (bed_ratio / 20),
        "dropouts": dr, "dropout_seconds": total_dr,
        "bed_floor_shifts_15s": shifts,
        "method": "full-mix inference: p10 of the loudness envelope is taken as "
                  "music-only, p50 as voice-over-music",
    }

    if args.vo:
        tv, ev, _ = envelope(args.vo)
        vlive = ev[ev > -55]
        vo_body = float(np.percentile(vlive, 50))
        out["vo_body_dbfs"] = vo_body
        out["bed_under_vo_db"] = floor - vo_body
        out["method"] = "measured against a separate VO stem"
        print(f"[measure] VO stem body p50 = {vo_body:.1f} dBFS -> "
              f"bed sits {floor - vo_body:.1f} dB under the voice")

    if args.json:
        json.dump(out, open(args.json, "w"), indent=2)
        print(f"[measure] wrote {args.json}")


if __name__ == "__main__":
    main()
