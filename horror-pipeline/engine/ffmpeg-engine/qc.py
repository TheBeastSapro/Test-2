#!/usr/bin/env python3
"""
Video QC pass for horror-explainer sections.

Usage:  python3 qc.py <video.mp4> [--workdir DIR] [--keep]

Measures motion energy, dead zones, loudness (incl. LRA), cut/SFX sync,
luminance, container specs, on-screen text (OCR), and the final 5 seconds.
Prints a verdict table plus a defect list.
"""

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np

try:
    import cv2
except ImportError:
    sys.exit("qc.py requires opencv-python (cv2)")

# ----------------------------------------------------------------------------
# Thresholds / benchmarks (client QC standard)
# ----------------------------------------------------------------------------
MOTION_PIXEL_DELTA = 12 / 255.0   # a pixel "changed" if it moves > 12/255
MOTION_SAMPLE_FPS = 2.0           # one sample per 0.5 s
BENCH_MOTION_GOOD = 22.0          # editor Vu, first cut
BENCH_MOTION_BEST = 25.1          # editor Vu, best cut to date
BENCH_MOTION_FAIL = 12.1          # editor Abel, a failing cut

DEADZONE_PCT = 4.0                # a 0.5 s sample below this is "low"
DEADZONE_MIN_S = 4.0              # flag runs at or above this
DEADZONE_BAD_S = 8.0              # hard fail on one asset

LUFS_LO, LUFS_HI = -16.0, -14.0
TRUE_PEAK_MAX = -1.0
LRA_MIN = 3.0                     # over-limited below this

CUT_DELTA_PCT = 60.0              # hard visual cut
SYNC_WINDOW_S = 0.6
SYNC_TARGET_PCT = 70.0

DARK_MEAN = 30                    # frame mean luminance below this = dark
DARK_P95_OK = 90                  # ...but a bright p95 anchor rescues it

BITRATE_FAIL_MBPS = 1.0
BITRATE_GOOD_MBPS = 10.0

OCR_FPS = 2                       # 1 fps under-samples ~2 s pops
CONTACT_COLS, CONTACT_ROWS = 5, 4
CONTACT_EVERY_S = 3
TAIL_S = 5.0

# The pops this cut is SUPPOSED to contain, read from the sheet that produced
# it via --sheet. The default below is the Sewer Alligator section and it used
# to be the only list this file had, so every other section was OCR-checked
# against another creature's captions and reported nine missing pops no matter
# what it actually rendered. A check that cannot pass is not a check.
INTENDED_POPS = [
    "Not alligators", "Spiders", "Former city worker", "4 legs", "3 joints",
    "Body never seen", "Name: fan-coined", "Plural", "No open manholes",
]


def load_intended(sheet_path):
    """Pop texts from a sheet, so QC checks THIS cut against THIS plan."""
    with open(sheet_path) as f:
        d = json.load(f)
    return [p["text"] for p in d.get("pops", []) if p.get("text")]


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def ts(t):
    return f"{int(t) // 60:d}:{t % 60:05.2f}"


# ----------------------------------------------------------------------------
# 6. Specs
# ----------------------------------------------------------------------------
def probe(path):
    r = sh(["ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", path])
    d = json.loads(r.stdout)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    fps_n, fps_d = (v.get("avg_frame_rate") or "0/1").split("/")
    fps = float(fps_n) / float(fps_d) if float(fps_d) else 0.0
    vbr = float(v.get("bit_rate") or 0) / 1e6
    if not vbr:  # fall back to container total minus audio
        tot = float(d["format"].get("bit_rate") or 0)
        abr_ = float(a.get("bit_rate") or 0) if a else 0
        vbr = max(tot - abr_, 0) / 1e6
    return {
        "duration": float(d["format"]["duration"]),
        "width": v["width"], "height": v["height"], "fps": fps,
        "vcodec": v["codec_name"], "profile": v.get("profile", ""),
        "pix_fmt": v.get("pix_fmt", ""),
        "vbitrate_mbps": vbr,
        "acodec": a["codec_name"] if a else None,
        "abitrate_kbps": (float(a.get("bit_rate") or 0) / 1e3) if a else 0.0,
        "sample_rate": a.get("sample_rate") if a else None,
        "channels": a.get("channels") if a else None,
        "size_mb": float(d["format"]["size"]) / 1e6,
    }


# ----------------------------------------------------------------------------
# 1/2/4/5. Single decode pass -> motion, dead zones, cuts, luminance
# ----------------------------------------------------------------------------
def decode_pass(path, work, fps):
    """Extract 2 fps PNG frames (lossless: JPEG noise would inflate motion)
    and also walk every frame for cut detection + luminance."""
    d2 = os.path.join(work, "f2")
    os.makedirs(d2, exist_ok=True)
    sh(["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps={MOTION_SAMPLE_FPS}",
        os.path.join(d2, "%05d.png"), "-y"])
    files = sorted(os.listdir(d2))

    # --- motion at 2 fps ---
    deltas, prev = [], None
    for fn in files:
        g = cv2.imread(os.path.join(d2, fn), cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255.0
        if prev is not None:
            changed = np.abs(g - prev) > MOTION_PIXEL_DELTA
            deltas.append(100.0 * changed.mean())
        prev = g
    deltas = np.array(deltas)
    # sample i covers the window ending at (i+1)/MOTION_SAMPLE_FPS seconds
    dt = 1.0 / MOTION_SAMPLE_FPS
    times = np.arange(len(deltas)) * dt

    # --- full-rate walk: cuts + luminance ---
    cap = cv2.VideoCapture(path)
    cuts, lum, prevf, idx, box = [], [], None, 0, None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # measure the image box, not the whole page: a white canvas around a dark
        # plate makes whole-frame luminance meaningless (reads ~160 on a night shot)
        if box is None:
            box = _plate_bounds(g)
        roi = g[box[2]:box[3], box[0]:box[1]] if box else g
        lum.append((idx / fps, float(roi.mean()), float(np.percentile(roi, 95)),
                    float(g.mean())))
        gf = g.astype(np.float32) / 255.0
        small = cv2.resize(gf, (320, 180), interpolation=cv2.INTER_AREA)
        if prevf is not None:
            pct = 100.0 * (np.abs(small - prevf) > MOTION_PIXEL_DELTA).mean()
            if pct > CUT_DELTA_PCT:
                cuts.append(idx / fps)
        prevf = small
        idx += 1
    cap.release()
    # de-bounce cuts within 3 frames
    ded = []
    for c in cuts:
        if not ded or c - ded[-1] > 3 / fps:
            ded.append(c)
    return deltas, times, ded, lum


def dead_zones(deltas, times):
    """Maximal runs of consecutive sub-threshold samples.
    Runs are NEVER merged across a high-motion sample -- doing so previously
    produced a bogus 13 s reading."""
    dt = 1.0 / MOTION_SAMPLE_FPS
    zones, run = [], None
    for i, v in enumerate(deltas):
        if v < DEADZONE_PCT:
            if run is None:
                run = [i, i]
            else:
                run[1] = i
        else:
            if run is not None:
                zones.append(run)
            run = None          # hard break: no merging across the blip
    if run is not None:
        zones.append(run)
    out = []
    for a, b in zones:
        dur = (b - a + 1) * dt
        if dur >= DEADZONE_MIN_S:
            out.append({"start": times[a], "end": times[b] + dt, "dur": dur,
                        "peak": float(deltas[a:b + 1].max()),
                        "mean": float(deltas[a:b + 1].mean())})
    return out


# ----------------------------------------------------------------------------
# 3. Audio
# ----------------------------------------------------------------------------
def audio_stats(path):
    out = {}
    r = sh(["ffmpeg", "-v", "info", "-i", path, "-af", "volumedetect", "-f", "null", "-"])
    for key in ("mean_volume", "max_volume"):
        m = re.search(rf"{key}:\s*(-?[\d.]+) dB", r.stderr)
        out[key] = float(m.group(1)) if m else None
    m = re.search(r"histogram_0db:\s*(\d+)", r.stderr)
    out["clipped_samples"] = int(m.group(1)) if m else 0

    r = sh(["ffmpeg", "-v", "info", "-i", path, "-af",
            "loudnorm=print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*input_i[^{}]*\}", r.stderr, re.S)
    j = json.loads(m.group(0)) if m else {}
    out["lufs"] = float(j.get("input_i", "nan"))
    out["tp"] = float(j.get("input_tp", "nan"))
    out["lra"] = float(j.get("input_lra", "nan"))
    out["thresh"] = float(j.get("input_thresh", "nan"))
    return out


def audio_transients(path, work):
    wav = os.path.join(work, "a.raw")
    sh(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "48000",
        "-f", "s16le", wav, "-y"])
    x = np.fromfile(wav, dtype=np.int16).astype(np.float32) / 32768.0
    sr, hop = 48000, 480                      # 10 ms hops
    n = len(x) // hop
    env = np.sqrt(np.maximum((x[:n * hop].reshape(n, hop) ** 2).mean(axis=1), 1e-12))
    log = 20 * np.log10(env)
    flux = np.diff(log, prepend=log[0])
    flux = np.maximum(flux, 0)
    thr = flux.mean() + 2.0 * flux.std()
    on, last = [], -1e9
    for i in range(1, len(flux) - 1):
        t = i * hop / sr
        if flux[i] > thr and flux[i] >= flux[i - 1] and flux[i] >= flux[i + 1] and t - last > 0.10:
            on.append(t)
            last = t
    return on


def tail_audio(path, work, duration):
    """Trailing digital silence and how abruptly the mix stops."""
    raw = os.path.join(work, "tail.raw")
    sh(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "48000",
        "-f", "s16le", raw, "-y"])
    x = np.fromfile(raw, dtype=np.int16).astype(np.float32) / 32768.0
    sr = 48000
    alen = len(x) / sr
    # length of the trailing run below -60 dBFS
    hop = 480
    n = len(x) // hop
    env = np.sqrt(np.maximum((x[:n * hop].reshape(n, hop) ** 2).mean(1), 1e-12))
    db = 20 * np.log10(env)
    k = 0
    while k < len(db) and db[len(db) - 1 - k] < -60:
        k += 1
    silence = k * hop / sr
    # biggest level drop in the final second
    tailwin = db[max(0, len(db) - 100):]
    drop = float(tailwin[:len(tailwin) // 2].mean() - tailwin[len(tailwin) // 2:].mean()) \
        if len(tailwin) > 4 else 0.0
    return {"audio_len": alen, "trailing_silence": silence, "tail_drop_db": drop}


def sync_score(cuts, onsets):
    if not cuts:
        return None, []
    o = np.array(onsets) if onsets else np.array([])
    hit, miss = 0, []
    for c in cuts:
        if o.size and np.min(np.abs(o - c)) <= SYNC_WINDOW_S:
            hit += 1
        else:
            miss.append(c)
    return 100.0 * hit / len(cuts), miss


# ----------------------------------------------------------------------------
# 7. OCR
# ----------------------------------------------------------------------------
def _plate_bounds(im):
    """Locate the dark image box inside the white canvas (house boxed layout)."""
    dark = (im < 120).astype(np.uint8)
    xs = np.where(dark.mean(0) > 0.3)[0]
    ys = np.where(dark.mean(1) > 0.3)[0]
    if len(xs) < 20 or len(ys) < 20:
        return None
    return int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())


def _tess(img, work):
    p = os.path.join(work, "_ocr.png")
    cv2.imwrite(p, img)
    return [l.strip() for l in sh(["tesseract", p, "stdout", "--psm", "11"]).stdout.splitlines()
            if l.strip()]


def ocr_frame(path, work):
    """TWO passes, deliberately.

    Tesseract binarises the page globally, so white-on-dark keyword pops sitting
    inside a dark image box are silently dropped by the plain pass -- that
    produced a false "3 pops missing" reading on an earlier run. Pass B isolates
    the bright text inside the box and inverts it to dark-on-light."""
    im = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if im is None:
        return []
    out = list(_tess(im, work))
    b = _plate_bounds(im)
    if b:
        x0, x1, y0, y1 = b
        crop = im[y0:y1, x0:x1]
        bw = 255 - ((crop > 190).astype(np.uint8) * 255)
        bw = cv2.resize(bw, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        bw = cv2.copyMakeBorder(bw, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
        out += _tess(bw, work)
    # strip leading pipes/bars the accent underline fakes into the OCR
    return [re.sub(r"^[|\s_]+", "", l).strip() for l in out if re.sub(r"^[|\s_]+", "", l).strip()]


def norm_txt(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def ocr_inventory(path, work):
    """OCR at OCR_FPS. Runs to completion before anything is analysed --
    reading a partial job silently truncates the inventory."""
    d1 = os.path.join(work, "focr")
    os.makedirs(d1, exist_ok=True)
    sh(["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps={OCR_FPS}",
        os.path.join(d1, "%05d.png"), "-y"])
    files = sorted(os.listdir(d1))
    if not shutil.which("tesseract"):
        return None, None
    per_t = {}
    for fn in files:
        t = (int(fn.split(".")[0]) - 1) / OCR_FPS
        per_t[t] = ocr_frame(os.path.join(d1, fn), work)   # blocking, in order
    seen = {}
    for t, ls in per_t.items():
        for s in set(norm_txt(x) for x in ls):
            if len(s) >= 4:
                seen[s] = seen.get(s, 0) + 1
    persistent = {s for s, c in seen.items() if c >= 0.5 * max(len(per_t), 1)}
    return per_t, persistent


def match_pops(per_t, persistent):
    """Group transient OCR lines into pop events and match to the intended list."""
    events = []
    for t in sorted(per_t):
        for s in per_t[t]:
            ns = norm_txt(s)
            u = s.upper()
            if not ns or ns in persistent or len(ns) < 2:
                continue
            if "ASSET SLOT" in u or "PLACEHOLDER" in u:
                continue
            if events and events[-1]["text_n"] == ns and t - events[-1]["end"] <= 1.5 / OCR_FPS + 1e-6:
                events[-1]["end"] = t
            else:
                events.append({"start": t, "end": t, "text": s, "text_n": ns})
    matched, used = [], {}
    for ev in events:
        best, score = None, 0.0
        for p in INTENDED_POPS:
            s = difflib.SequenceMatcher(None, ev["text_n"], norm_txt(p)).ratio()
            if s > score:
                best, score = p, s
        ev.update(intended=best, score=score)
        matched.append(ev)
        if score >= 0.75:
            used.setdefault(best, []).append(ev)
    missing = [p for p in INTENDED_POPS if p not in used]
    # a pop is only "misspelled" if it NEVER renders correctly. Partial reads
    # during the 0.2 s pop-in animation are not spelling defects.
    misspelled = []
    for p, evs in used.items():
        if not any(norm_txt(e["text"]) == norm_txt(p) for e in evs):
            misspelled.append((p, sorted({e["text"] for e in evs})))
    return matched, missing, misspelled, used


# ----------------------------------------------------------------------------
# 8/9. Tail frames + contact sheets
# ----------------------------------------------------------------------------
def tail_check(path, work, duration, fps):
    d = os.path.join(work, "tail")
    os.makedirs(d, exist_ok=True)
    start = max(duration - TAIL_S, 0)
    sh(["ffmpeg", "-v", "error", "-ss", str(start), "-i", path,
        os.path.join(d, "%05d.png"), "-y"])
    files = sorted(os.listdir(d))
    rows = []
    for i, fn in enumerate(files):
        g = cv2.imread(os.path.join(d, fn), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        rows.append({"t": start + i / fps, "mean": float(g.mean()),
                     "p95": float(np.percentile(g, 95)),
                     "std": float(g.std()), "file": os.path.join(d, fn)})
    return rows


def contact_sheets(path, work, duration):
    d = os.path.join(work, "sheets")
    os.makedirs(d, exist_ok=True)
    per = CONTACT_COLS * CONTACT_ROWS
    sh(["ffmpeg", "-v", "error", "-i", path,
        "-vf", f"fps=1/{CONTACT_EVERY_S},scale=384:-1,"
               f"tile={CONTACT_COLS}x{CONTACT_ROWS}:padding=4:margin=4",
        os.path.join(d, "sheet_%02d.png"), "-y"])
    return [os.path.join(d, f) for f in sorted(os.listdir(d))], per


# ----------------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------------
def verdict_table(rows):
    w0 = max(len(r[0]) for r in rows)
    w1 = max(len(r[1]) for r in rows)
    w2 = max(len(r[2]) for r in rows)
    line = "+" + "-" * (w0 + 2) + "+" + "-" * (w1 + 2) + "+" + "-" * (w2 + 2) + "+" + "-" * 8 + "+"
    out = [line, f"| {'METRIC'.ljust(w0)} | {'MEASURED'.ljust(w1)} | {'TARGET'.ljust(w2)} | {'VERDICT'.ljust(6)} |", line]
    for name, val, tgt, v in rows:
        out.append(f"| {name.ljust(w0)} | {val.ljust(w1)} | {tgt.ljust(w2)} | {v.ljust(6)} |")
    out.append(line)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--sheet", default=None,
                    help="sheet JSON this cut was built from; its pops become "
                         "the intended list the OCR pass checks against")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    global INTENDED_POPS
    if args.sheet:
        INTENDED_POPS = load_intended(args.sheet)

    path = os.path.abspath(args.video)
    if not os.path.exists(path):
        sys.exit(f"no such file: {path}")
    work = args.workdir or tempfile.mkdtemp(prefix="qc_")
    os.makedirs(work, exist_ok=True)

    sp = probe(path)
    print(f"\n=== QC: {os.path.basename(path)} "
          f"({sp['duration']:.2f}s, {sp['size_mb']:.1f} MB) ===\n")

    deltas, times, cuts, lum = decode_pass(path, work, sp["fps"] or 30.0)
    dz = dead_zones(deltas, times)
    au = audio_stats(path)
    onsets = audio_transients(path, work)
    sync, missed = sync_score(cuts, onsets)
    per_sec, persistent = ocr_inventory(path, work)
    if per_sec:
        pops, missing, misspelled, used = match_pops(per_sec, persistent)
    else:
        pops, missing, misspelled, used = [], INTENDED_POPS, [], {}
    ta = tail_audio(path, work, sp["duration"])
    tail = tail_check(path, work, sp["duration"], sp["fps"] or 30.0)
    sheets, per = contact_sheets(path, work, sp["duration"])

    avg_motion = float(deltas.mean())
    dark = [r for r in lum if r[1] < DARK_MEAN]
    dark_flat = [r for r in dark if r[2] < DARK_P95_OK]
    worst_dz = max((z["dur"] for z in dz), default=0.0)
    tail_black = [r for r in tail if r["mean"] < 10 and r["std"] < 3]

    R = []
    mv = ("PASS" if avg_motion >= BENCH_MOTION_GOOD else
          "FAIL" if avg_motion <= BENCH_MOTION_FAIL + 3 else "WARN")
    R.append(("Motion (avg %px changed / 0.5s)", f"{avg_motion:.1f}%",
              f">={BENCH_MOTION_GOOD} (best {BENCH_MOTION_BEST})", mv))
    R.append(("Motion floor / peak", f"{deltas.min():.1f}% / {deltas.max():.1f}%", "-", "INFO"))
    R.append((f"Dead zones >={DEADZONE_MIN_S:.0f}s (<{DEADZONE_PCT:.0f}%)", f"{len(dz)}",
              "0", "PASS" if not dz else "FAIL"))
    R.append(("Longest dead zone", f"{worst_dz:.1f}s", f"<{DEADZONE_MIN_S:.0f}s",
              "PASS" if worst_dz < DEADZONE_MIN_S else
              "FAIL" if worst_dz > DEADZONE_BAD_S else "WARN"))
    R.append(("Integrated loudness", f"{au['lufs']:.2f} LUFS",
              f"{LUFS_LO} to {LUFS_HI}",
              "PASS" if LUFS_LO <= au["lufs"] <= LUFS_HI else "FAIL"))
    R.append(("True peak", f"{au['tp']:.2f} dBTP", f"<{TRUE_PEAK_MAX}",
              "PASS" if au["tp"] < TRUE_PEAK_MAX else "FAIL"))
    R.append(("Loudness range (LRA)", f"{au['lra']:.2f} LU", f">{LRA_MIN} LU",
              "PASS" if au["lra"] > LRA_MIN else "FAIL"))
    R.append(("Mean / max volume", f"{au['mean_volume']:.1f} / {au['max_volume']:.1f} dB",
              "max < 0 dB", "PASS" if au["max_volume"] < 0 else "FAIL"))
    R.append(("Clipped samples (0 dBFS)", f"{au['clipped_samples']}", "0",
              "PASS" if au["clipped_samples"] == 0 else "FAIL"))
    R.append(("Hard cuts detected", f"{len(cuts)}", "-", "INFO"))
    R.append(("Audio transients", f"{len(onsets)}", "-", "INFO"))
    R.append((f"Cuts w/ transient <={SYNC_WINDOW_S}s",
              "n/a" if sync is None else f"{sync:.0f}%", f">={SYNC_TARGET_PCT:.0f}%",
              "INFO" if sync is None else ("PASS" if sync >= SYNC_TARGET_PCT else "FAIL")))
    R.append(("Content-box luminance (mean)",
              f"{np.mean([r[1] for r in lum]):.1f} (frame {np.mean([r[3] for r in lum]):.0f})",
              "-", "INFO"))
    R.append((f"Dark frames (box mean<{DARK_MEAN})", f"{len(dark)} / {len(lum)}", "-", "INFO"))
    R.append(("...of those, flat (no bright p95)", f"{len(dark_flat)}", "0",
              "PASS" if not dark_flat else "FAIL"))
    R.append(("Resolution / fps", f"{sp['width']}x{sp['height']} @ {sp['fps']:.2f}",
              "1920x1080 @ 30", "PASS" if (sp["width"], sp["height"]) == (1920, 1080) else "FAIL"))
    R.append(("Video codec", f"{sp['vcodec']} {sp['profile']} {sp['pix_fmt']}", "h264 yuv420p",
              "PASS" if sp["vcodec"] == "h264" else "WARN"))
    R.append(("Video bitrate", f"{sp['vbitrate_mbps']:.2f} Mbps",
              f">{BITRATE_FAIL_MBPS} (good {BITRATE_GOOD_MBPS})",
              "FAIL" if sp["vbitrate_mbps"] < BITRATE_FAIL_MBPS else
              "PASS" if sp["vbitrate_mbps"] >= BITRATE_GOOD_MBPS else "WARN"))
    R.append(("Audio codec / bitrate", f"{sp['acodec']} {sp['abitrate_kbps']:.0f} kbps",
              ">=128 kbps", "PASS" if sp["abitrate_kbps"] >= 128 else "FAIL"))
    R.append(("Keyword pops found (OCR)", f"{len(used)}", f"{len(INTENDED_POPS)} intended",
              "PASS" if not missing else "FAIL"))
    R.append(("Missing pops", f"{len(missing)}", "0", "PASS" if not missing else "FAIL"))
    R.append(("Misspelled pops", f"{len(misspelled)}", "0",
              "PASS" if not misspelled else "FAIL"))
    R.append(("A/V stream length delta",
              f"{abs(ta['audio_len'] - sp['duration']):.2f}s", "<0.10s",
              "PASS" if abs(ta["audio_len"] - sp["duration"]) < 0.10 else "FAIL"))
    R.append(("Trailing digital silence", f"{ta['trailing_silence']:.2f}s", "<0.15s",
              "PASS" if ta["trailing_silence"] < 0.15 else "FAIL"))
    R.append(("Last 5s black frames", f"{len(tail_black)}", "0",
              "PASS" if not tail_black else "FAIL"))
    print(verdict_table(R))

    print("\n--- DEAD ZONES (no merging across high-motion samples) ---")
    if not dz:
        print("  none >= %.0fs" % DEADZONE_MIN_S)
    for z in dz:
        print(f"  {ts(z['start'])}-{ts(z['end'])}  {z['dur']:.1f}s  "
              f"mean {z['mean']:.1f}%  peak {z['peak']:.1f}%")

    print("\n--- MOTION PROFILE (per 0.5s) ---")
    for i in range(0, len(deltas), 10):
        chunk = deltas[i:i + 10]
        print(f"  {ts(times[i])}  " + " ".join(f"{v:5.1f}" for v in chunk))

    print("\n--- CUTS WITHOUT A NEARBY TRANSIENT ---")
    print("  " + (", ".join(ts(m) for m in missed) if missed else "none"))

    print("\n--- ON-SCREEN TEXT INVENTORY ---")
    print(f"  persistent (filtered): {sorted(persistent) if persistent else 'none'}")
    if misspelled:
        for p, got in misspelled:
            print(f"  SPELLING: intended {p!r} -> rendered {got!r}")
    shown = [p for p in pops if p["score"] >= 0.75 or len(p["text"]) >= 12]
    noise = len(pops) - len(shown)
    for p in shown:
        flag = "OK " if p["score"] >= 0.9 else ("~  " if p["score"] >= 0.75 else "?? ")
        span = f"{p['start']:6.2f}-{p['end']:<6.2f}s"
        print(f"  {flag}{span}  {p['text']!r}  -> {p['intended']!r} ({p['score']:.2f})")
    print(f"  ({noise} sub-threshold OCR fragments from plate grain suppressed)")
    if missing:
        print(f"  MISSING intended pops: {missing}")

    print("\n--- AUDIO TAIL ---")
    print(f"  audio {ta['audio_len']:.3f}s vs container {sp['duration']:.3f}s | "
          f"trailing silence {ta['trailing_silence']:.2f}s | "
          f"final-second level drop {ta['tail_drop_db']:.1f} dB")

    print("\n--- LAST 5 SECONDS ---")
    for r in tail[::5]:
        print(f"  {ts(r['t'])}  mean {r['mean']:6.2f}  p95 {r['p95']:6.2f}  std {r['std']:6.2f}")
    if tail:
        r = tail[-1]
        print(f"  FINAL {ts(r['t'])}  mean {r['mean']:6.2f}  p95 {r['p95']:6.2f}  std {r['std']:6.2f}")

    print("\n--- CONTACT SHEETS (review these visually) ---")
    for s in sheets:
        print("  " + s)
    print(f"\nWorkdir: {work}")
    if not args.keep and not args.workdir:
        print("(pass --keep or --workdir to retain frames)")


if __name__ == "__main__":
    main()
