#!/usr/bin/env python3
"""analyze.py — the Sound Designer "brain".

Watches a video (scene cuts + audio) and emits a structured, timestamped
SOUND DESIGN CUE SHEET: music sections, SFX hits, ducking points, and an
Epidemic Sound search seed for every cue.

The timing/structure here is measured (scene cuts, silence map, RMS energy).
The creative descriptors (mood, bpm) are labelled *hints/seeds* — they are
starting points for Epidemic Soundmatch/semantic-search to refine at fetch
time, never treated as ground truth. (See the ExplainTory rule: never treat a
listening model's description as data. This tool only trusts measurements.)

Usage:
  analyze.py --video in.mp4 [--vo vo.mp3] --out cues.json --report cues.md
             [--scene-threshold 0.4] [--silence-db -30] [--silence-min 0.5]
             [--sections auto|N] [--lufs -14]
"""
from __future__ import annotations

import argparse
import json
import re

import numpy as np

from common import FFMPEG, run, media_info, decode_mono_pcm, fmt_ts


# ---------------------------------------------------------------- measurement

def detect_scene_cuts(video: str, threshold: float) -> list[float]:
    """Return sorted scene-change timestamps (s) via ffmpeg scene score."""
    res = run([
        FFMPEG, "-hide_banner", "-i", video,
        "-filter:v", f"select='gt(scene,{threshold})',showinfo",
        "-an", "-f", "null", "-",
    ])
    times = []
    for line in res.stderr.splitlines():
        if "showinfo" in line and "pts_time:" in line:
            m = re.search(r"pts_time:([0-9.]+)", line)
            if m:
                times.append(float(m.group(1)))
    return sorted(set(round(t, 3) for t in times))


def detect_silence(path: str, noise_db: float, min_d: float) -> list[tuple[float, float]]:
    """Return list of (start,end) silence intervals via silencedetect."""
    res = run([
        FFMPEG, "-hide_banner", "-i", path,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_d}",
        "-f", "null", "-",
    ])
    starts, spans = [], []
    for line in res.stderr.splitlines():
        s = re.search(r"silence_start:\s*(-?[0-9.]+)", line)
        e = re.search(r"silence_end:\s*(-?[0-9.]+)", line)
        if s:
            starts.append(float(s.group(1)))
        if e:
            end = float(e.group(1))
            if starts:
                spans.append((max(0.0, starts.pop()), end))
    return spans


def speech_intervals(duration: float, silence: list[tuple[float, float]],
                     pad: float = 0.0) -> list[list[float]]:
    """Complement of silence over [0,duration] = voiced/content regions."""
    voiced, cursor = [], 0.0
    for s, e in sorted(silence):
        if s - cursor > 0.15:
            voiced.append([round(cursor, 3), round(s, 3)])
        cursor = max(cursor, e)
    if duration - cursor > 0.15:
        voiced.append([round(cursor, 3), round(duration, 3)])
    return voiced


def energy_envelope(samples: np.ndarray, sr: int, hop: float = 0.25,
                    win: float = 0.5):
    """Windowed RMS -> (times, energy0to1). Robust-normalized."""
    if samples.size == 0:
        return np.array([0.0]), np.array([0.0])
    hop_n = max(1, int(hop * sr))
    win_n = max(hop_n, int(win * sr))
    times, rms = [], []
    for start in range(0, len(samples), hop_n):
        seg = samples[start:start + win_n]
        if seg.size == 0:
            break
        rms.append(float(np.sqrt(np.mean(seg.astype(np.float64) ** 2)) + 1e-9))
        times.append(start / sr)
    rms = np.asarray(rms)
    db = 20 * np.log10(rms)
    lo, hi = np.percentile(db, 5), np.percentile(db, 95)
    energy = np.clip((db - lo) / (hi - lo + 1e-9), 0, 1) if hi > lo else np.zeros_like(db)
    return np.asarray(times), energy


def overlaps_voice(a: float, b: float, voiced: list[list[float]]) -> bool:
    return any(not (b <= v0 or a >= v1) for v0, v1 in voiced)


# --------------------------------------------------------------- creative map

ENERGY_WORDS = [
    (0.20, "calm", "ambient", 68),
    (0.40, "gentle", "warm underscore", 82),
    (0.60, "building", "driving underscore", 100),
    (0.80, "driving", "propulsive cinematic", 116),
    (1.01, "intense", "tense cinematic climax", 128),
]


def energy_label(e: float):
    for thr, word, mood, bpm in ENERGY_WORDS:
        if e < thr:
            return word, mood, bpm
    return ENERGY_WORDS[-1][1], ENERGY_WORDS[-1][2], ENERGY_WORDS[-1][3]


def snap(t: float, cuts: list[float], tol: float = 1.5) -> float:
    """Snap a time to the nearest scene cut within tol, for musical edits."""
    if not cuts:
        return round(t, 3)
    nearest = min(cuts, key=lambda c: abs(c - t))
    return round(nearest if abs(nearest - t) <= tol else t, 3)


def build_music_sections(duration, cuts, times, energy, voiced, n_sections):
    if n_sections == "auto":
        k = int(np.clip(round(duration / 90.0), 1, 6))
    else:
        k = max(1, int(n_sections))
    bounds = [duration * i / k for i in range(k + 1)]
    bounds = [snap(b, cuts) for b in bounds]
    bounds[0], bounds[-1] = 0.0, round(duration, 3)
    bounds = sorted(set(bounds))

    sections = []
    for i in range(len(bounds) - 1):
        a, b = bounds[i], bounds[i + 1]
        if b - a < 3:
            continue
        mask = (times >= a) & (times < b)
        e = float(np.mean(energy[mask])) if mask.any() else 0.3
        word, mood, bpm = energy_label(e)
        has_vo = overlaps_voice(a, b, voiced)
        role = "intro" if i == 0 else ("outro" if i == len(bounds) - 2 else "bed")
        seed = f"{mood} instrumental underscore for explainer video, {word} energy, no vocals"
        sections.append({
            "id": f"m{i + 1}", "role": role,
            "start": round(a, 3), "end": round(b, 3), "dur": round(b - a, 3),
            "energy": round(e, 3), "energy_label": word,
            "mood_hint": mood, "bpm_hint": bpm,
            "under_voiceover": has_vo,
            "duck_db": -9 if has_vo else -3,
            "fade_in": 1.5 if role == "intro" else 0.8,
            "fade_out": 2.5 if role == "outro" else 1.0,
            "epidemic": {
                "tool": "soundmatch|semantic_search",
                "search": seed,
                "target_bpm_hint": bpm,
                "target_duration_s": round(b - a, 3),
                "note": "Feed this section's video slice to Soundmatch; use "
                        "track-versions to fit the returned track to target_duration_s.",
            },
            "asset": None,   # <- filled by the Epidemic MCP fetch, or by you
            "gain_db": 0.0,
        })
    return sections


def build_sfx(cuts, voiced, silence, duration):
    sfx, seen = [], set()

    def add(at, kind, seed, gain=-8.0):
        key = (round(at, 1), kind)
        if key in seen or at < 0 or at > duration:
            return
        seen.add(key)
        sfx.append({
            "id": f"s{len(sfx) + 1}", "at": round(at, 3), "kind": kind,
            "gain_db": gain,
            "epidemic": {"tool": "semantic_search", "search": seed},
            "asset": None,
        })

    # transition whooshes on scene cuts (thinned so they don't machine-gun)
    last = -10.0
    for c in cuts:
        if c - last >= 2.5:
            add(c, "transition whoosh", "cinematic whoosh transition swipe", -9.0)
            last = c
    # reveal impact on the first cut after a long silence (a beat lands)
    for s, e in silence:
        if e - s >= 1.0:
            after = next((c for c in cuts if c >= e - 0.1), None)
            if after is not None:
                add(after, "reveal impact", "deep cinematic impact hit boom", -6.0)
    # opening riser into the first content
    if voiced:
        add(max(0.0, voiced[0][0] - 1.2), "intro riser", "cinematic riser uplifter build tension", -7.0)
    return sorted(sfx, key=lambda x: x["at"])


# ---------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--vo", help="separate mastered VO file (preferred for the voice map)")
    ap.add_argument("--out", required=True, help="cue sheet JSON")
    ap.add_argument("--report", help="human-readable markdown cue sheet")
    ap.add_argument("--scene-threshold", type=float, default=0.4)
    ap.add_argument("--silence-db", type=float, default=-30.0)
    ap.add_argument("--silence-min", type=float, default=0.5)
    ap.add_argument("--sections", default="auto")
    ap.add_argument("--lufs", type=float, default=-14.0)
    args = ap.parse_args()

    vinfo = media_info(args.video)
    duration = vinfo["duration"]
    print(f"[analyze] {args.video} · {fmt_ts(duration)} · "
          f"{vinfo['width']}x{vinfo['height']}@{vinfo['fps']}fps · "
          f"audio={'yes' if vinfo['has_audio'] else 'no'}")

    cuts = detect_scene_cuts(args.video, args.scene_threshold) if vinfo["has_video"] else []
    print(f"[analyze] {len(cuts)} scene cuts")

    vo_source = args.vo if args.vo else (args.video if vinfo["has_audio"] else None)
    if vo_source:
        silence = detect_silence(vo_source, args.silence_db, args.silence_min)
        voiced = speech_intervals(duration, silence)
    else:
        silence, voiced = [], []
    voiced_dur = sum(b - a for a, b in voiced)
    print(f"[analyze] voice/content regions: {len(voiced)} "
          f"({voiced_dur:.1f}s, {100*voiced_dur/max(duration,1):.0f}% of runtime)")

    energy_src = args.video if vinfo["has_audio"] else (args.vo or args.video)
    samples, sr = decode_mono_pcm(energy_src)
    times, energy = energy_envelope(samples, sr)

    sections = build_music_sections(duration, cuts, times, energy, voiced, args.sections)
    sfx = build_sfx(cuts, voiced, silence, duration)
    print(f"[analyze] {len(sections)} music sections · {len(sfx)} SFX cues")

    cue = {
        "schema": "sound-designer/cue-sheet@1",
        "video": args.video,
        "vo": args.vo,
        "duration": round(duration, 3),
        "loudness_target_lufs": args.lufs,
        "true_peak_ceiling_dbtp": -1.0,
        "measured": {
            "scene_cuts": cuts,
            "voiced_regions": voiced,
            "silence": [[round(s, 3), round(e, 3)] for s, e in silence],
        },
        "music_sections": sections,
        "sfx_cues": sfx,
        "notes": [
            "Timing is measured; mood/bpm are seeds for Epidemic Soundmatch to refine.",
            "Fill each cue's 'asset' with a local file (from the Epidemic MCP or a "
            "manual download), then run assemble.py.",
        ],
    }
    with open(args.out, "w") as f:
        json.dump(cue, f, indent=2)
    print(f"[analyze] wrote {args.out}")

    if args.report:
        write_report(cue, args.report)
        print(f"[analyze] wrote {args.report}")


def write_report(cue: dict, path: str):
    L = []
    L.append(f"# Sound design cue sheet — {cue['video']}")
    L.append(f"\nRuntime **{fmt_ts(cue['duration'])}** · master target "
             f"**{cue['loudness_target_lufs']} LUFS / {cue['true_peak_ceiling_dbtp']} dBTP** · "
             f"{len(cue['measured']['scene_cuts'])} scene cuts\n")
    L.append("## Music")
    L.append("| # | in | out | role | energy | mood seed | duck | Epidemic search |")
    L.append("|---|----|-----|------|--------|-----------|------|-----------------|")
    for m in cue["music_sections"]:
        L.append(f"| {m['id']} | {fmt_ts(m['start'])} | {fmt_ts(m['end'])} | {m['role']} "
                 f"| {m['energy_label']} ({m['energy']}) | {m['mood_hint']} @~{m['bpm_hint']}bpm "
                 f"| {m['duck_db']}dB | {m['epidemic']['search']} |")
    L.append("\n## SFX hits")
    L.append("| # | at | kind | gain | Epidemic search |")
    L.append("|---|----|------|------|-----------------|")
    for s in cue["sfx_cues"]:
        L.append(f"| {s['id']} | {fmt_ts(s['at'])} | {s['kind']} | {s['gain_db']}dB "
                 f"| {s['epidemic']['search']} |")
    L.append("\n> Fill each `asset` field (Epidemic MCP fetch or manual download), "
             "then run `assemble.py` to render the mix.")
    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
