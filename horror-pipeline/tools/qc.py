#!/usr/bin/env python3
"""
Stage 6: measured self-QC for horror-explainer cuts.

Usage:
    python3 tools/qc.py <video.mp4> [--workdir DIR] [--keep]
                        [--sheet sheet.json] [--sections auto|none|a,b,c|file.json]
                        [--pops-file pops.txt] [--jobs N] [--no-ocr] [--json report.json]

Port of engine/ffmpeg-engine/qc.py, extended to the full BUILD-PACKET section 8.1
pass/fail table. Prints a verdict table plus a defect list. Summaries, never dumps.

Two measurement subtleties carried over verbatim from the reference implementation,
because both have already produced a wrong verdict on a real cut:

  1. Dead zones are NEVER merged across a high-motion sample. A run ends at the
     first sample above threshold. Merging produced a bogus 13 s hold report.
  2. Luminance is measured inside the CONTENT BOX, not over the whole frame. A
     white canvas around a dark plate makes a pitch-black night shot read ~160
     mean. And a dark frame is only a defect if its p95 is also low: mean 16 with
     p95 101 has bright anchors and is correct.

And the two OCR traps:

  3. TWO tesseract passes per frame. Tesseract binarises the page globally, so
     white-on-dark pop text inside a dark box falls on the wrong side of the
     threshold and vanishes -- that produced a false "3 pops missing" report.
  4. OCR runs at 2 fps, not 1. Pops are on screen ~2 s and animate in over the
     first 0.2 s; at 1 fps you catch one mid-animation, read half a word and log
     a spelling error that does not exist. A pop is only misspelled if it never
     renders correctly on ANY frame.

ffmpeg is always called with -nostdin. Everything that does not need to be parsed
runs at -loglevel error. The two measurement calls (volumedetect, loudnorm) print
their statistics at info level, so those use -hide_banner -nostats -loglevel info:
-nostats is what suppresses the frame=... progress flood that the house rule is
actually about.
"""

import argparse
import concurrent.futures as futures
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np

try:
    import cv2
except ImportError:
    sys.exit("qc.py requires opencv-python (cv2)")

# ----------------------------------------------------------------------------
# Thresholds / benchmarks (BUILD-PACKET 8.1, client QC standard)
# ----------------------------------------------------------------------------
MOTION_PIXEL_DELTA = 12 / 255.0   # a pixel "changed" if it moves > 12/255
MOTION_SAMPLE_FPS = 2.0           # one sample per 0.5 s
BENCH_MOTION_GOOD = 22.0          # editor Vu, first cut
BENCH_MOTION_BEST = 25.1          # editor Vu, best cut to date
BENCH_MOTION_FAIL = 12.1          # editor Abel, a failing cut

DEADZONE_PCT = 4.0                # a 0.5 s sample below this is "low"
DEADZONE_MIN_S = 4.0              # flag runs at or above this
DEADZONE_BAD_S = 8.0              # hard fail on one asset

SHOT_MAX_S = 8.0                  # never > 8 s on one asset
SHOT_HOUSE_S = 6.5                # house headroom (style.MAX_SHOT_LEN)

LUFS_LO, LUFS_HI = -16.0, -14.0
TRUE_PEAK_MAX = -1.0
LRA_MIN = 3.0                     # over-limited below this (a cut failed at 1.9)

CUT_DELTA_PCT = 60.0              # hard visual cut
SYNC_WINDOW_S = 0.6
SYNC_TARGET_PCT = 70.0

DARK_MEAN = 30                    # content-box mean luminance below this = dark
DARK_P95_OK = 90                  # ...but a bright p95 anchor rescues it

BITRATE_FAIL_MBPS = 1.0           # outright fail
BITRATE_TARGET_MBPS = 4.0         # target floor
BITRATE_GOOD_MBPS = 10.0          # the benchmark
ABITRATE_MIN_KBPS = 128.0

OCR_FPS = 2                       # 1 fps under-samples ~2 s pops
POP_FLOOR_PER_SECTION = 2         # keyword pops per section, minimum
POP_TAPER_RATIO = 0.8             # last section >= 0.8 x median
POP_MIN_SAMPLES = 2               # a discovered pop must hold >= 2 OCR samples
POP_FUZZ = 0.80                   # fuzzy grouping of OCR reads of the same pop
POP_MATCH = 0.75                  # difflib score that counts as "this pop rendered"

CONTACT_COLS, CONTACT_ROWS = 5, 4
CONTACT_EVERY_S = 3
TAIL_S = 5.0
TAIL_BLACK_MEAN = 10              # black frame
TAIL_WHITE_MEAN = 245             # blank white card
TAIL_FLAT_STD = 3.0               # no content
AV_DELTA_MAX = 0.10
TRAILING_SILENCE_MAX = 0.15

# Default intended pop list. Real runs should pass --sheet / --pops-file; this is
# only the fallback for the engine's own sewer_spider demo section.
INTENDED_POPS_DEFAULT = [
    "Not alligators", "Spiders", "Former city worker", "4 legs", "3 joints",
    "Body never seen", "Name: fan-coined", "Plural", "No open manholes",
]

FF_QUIET = ["ffmpeg", "-nostdin", "-loglevel", "error"]
FF_MEASURE = ["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-loglevel", "info"]


def sh(cmd, timeout=None):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def ts(t):
    return f"{int(t) // 60:d}:{t % 60:05.2f}"


def log(msg):
    print(msg, file=sys.stderr, flush=True)


# ----------------------------------------------------------------------------
# Specs
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
# Frame extraction (ONE 2 fps extraction, shared by motion and OCR)
# ----------------------------------------------------------------------------
def extract_samples(path, work):
    """Lossless PNG at MOTION_SAMPLE_FPS. JPEG noise would inflate motion, and
    cv2.imread(...,IMREAD_GRAYSCALE) on a PNG is the exact luma path the
    reference implementation's benchmarks (22% / 25.1%) were measured with."""
    d2 = os.path.join(work, "f2")
    if os.path.isdir(d2) and os.listdir(d2):
        return d2, sorted(os.listdir(d2))
    os.makedirs(d2, exist_ok=True)
    sh(FF_QUIET + ["-i", path, "-vf", f"fps={MOTION_SAMPLE_FPS}",
                   os.path.join(d2, "%05d.png"), "-y"])
    return d2, sorted(os.listdir(d2))


# ----------------------------------------------------------------------------
# Motion / dead zones
# ----------------------------------------------------------------------------
def motion_series(d2, files):
    deltas, prev = [], None
    for fn in files:
        g = cv2.imread(os.path.join(d2, fn), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        g = g.astype(np.float32) / 255.0
        if prev is not None:
            deltas.append(100.0 * float((np.abs(g - prev) > MOTION_PIXEL_DELTA).mean()))
        prev = g
    deltas = np.array(deltas, dtype=np.float64)
    times = np.arange(len(deltas)) / MOTION_SAMPLE_FPS
    return deltas, times


def dead_zones(deltas, times):
    """Maximal runs of consecutive sub-threshold samples.

    Runs are NEVER merged across a high-motion sample. Treating
    'low, low, spike, low, low' as one run previously produced a bogus 13 s
    reading on a cut that did not have one. A run ends at the first sample above
    threshold. Full stop."""
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
            out.append({"start": float(times[a]), "end": float(times[b] + dt),
                        "dur": dur, "peak": float(deltas[a:b + 1].max()),
                        "mean": float(deltas[a:b + 1].mean())})
    return out


# ----------------------------------------------------------------------------
# Content box + full-rate walk (cuts, luminance)
# ----------------------------------------------------------------------------
def _plate_bounds(im):
    """Locate the dark image box inside the white canvas (house boxed layout).

    Degrades correctly on a full-bleed cinematic cut: every column/row is dark,
    so the box becomes the whole frame, which is the right ROI for that layout."""
    dark = (im < 120).astype(np.uint8)
    xs = np.where(dark.mean(0) > 0.3)[0]
    ys = np.where(dark.mean(1) > 0.3)[0]
    if len(xs) < 20 or len(ys) < 20:
        return None
    return int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())


def content_box(d2, files, max_probe=120):
    """Median plate box over sampled frames.

    The reference took the box from the first frame only. Sampling and taking the
    median costs nothing and stops one atypical opening frame (a full-bleed title
    card, a fade-from-black) from fixing a wrong ROI for the entire measurement."""
    step = max(1, len(files) // max_probe)
    boxes = []
    for fn in files[::step]:
        g = cv2.imread(os.path.join(d2, fn), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        b = _plate_bounds(g)
        if b:
            boxes.append(b)
    if not boxes:
        return None, 0.0
    b = np.median(np.array(boxes), axis=0).astype(int)
    g = cv2.imread(os.path.join(d2, files[0]), cv2.IMREAD_GRAYSCALE)
    h, w = g.shape[:2]
    cover = ((b[1] - b[0]) * (b[3] - b[2])) / float(w * h)
    return (int(b[0]), int(b[1]), int(b[2]), int(b[3])), float(cover)


def _hist_stats(roi):
    """Exact mean and p95 from the 256-bin histogram. np.percentile on a 1080p
    ROI 17k times is minutes of wall clock; calcHist is milliseconds and, for
    uint8, the bins ARE the levels, so the result is exact, not approximate."""
    hist = cv2.calcHist([roi], [0], None, [256], [0, 256]).ravel()
    n = hist.sum()
    if n <= 0:
        return 0.0, 0.0
    lv = np.arange(256, dtype=np.float64)
    mean = float((hist * lv).sum() / n)
    c = np.cumsum(hist)
    p95 = float(np.searchsorted(c, 0.95 * n))
    return mean, p95


def full_rate_walk(path, fps, box, progress_every=3000):
    """Cut detection and per-frame luminance in one decode."""
    cap = cv2.VideoCapture(path)
    cuts, lum, prevf, idx = [], [], None, 0
    t0 = time.time()
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        roi = g[box[2]:box[3], box[0]:box[1]] if box else g
        if roi.size == 0:
            roi = g
        m, p95 = _hist_stats(roi)
        fm, _ = _hist_stats(g)
        lum.append((idx / fps, m, p95, fm))
        gf = g.astype(np.float32) / 255.0
        small = cv2.resize(gf, (320, 180), interpolation=cv2.INTER_AREA)
        if prevf is not None:
            pct = 100.0 * float((np.abs(small - prevf) > MOTION_PIXEL_DELTA).mean())
            if pct > CUT_DELTA_PCT:
                cuts.append(idx / fps)
        prevf = small
        idx += 1
        if progress_every and idx % progress_every == 0:
            log(f"  [walk] {idx} frames ({time.time() - t0:.0f}s)")
    cap.release()
    # de-bounce cuts within 3 frames
    ded = []
    for c in cuts:
        if not ded or c - ded[-1] > 3 / fps:
            ded.append(c)
    return ded, lum


def shot_lengths(cuts, duration):
    """Longest single shot = longest span with no hard cut, head and tail
    included. This is the 'one asset held' row of the table."""
    marks = [0.0] + list(cuts) + [duration]
    spans = [(a, b, b - a) for a, b in zip(marks, marks[1:]) if b > a]
    spans.sort(key=lambda s: -s[2])
    return spans


# ----------------------------------------------------------------------------
# Audio
# ----------------------------------------------------------------------------
def audio_stats(path):
    out = {}
    r = sh(FF_MEASURE + ["-i", path, "-af", "volumedetect", "-f", "null", "-"])
    for key in ("mean_volume", "max_volume"):
        m = re.search(rf"{key}:\s*(-?[\d.]+) dB", r.stderr)
        out[key] = float(m.group(1)) if m else None
    m = re.search(r"histogram_0db:\s*(\d+)", r.stderr)
    out["clipped_samples"] = int(m.group(1)) if m else 0

    r = sh(FF_MEASURE + ["-i", path, "-af", "loudnorm=print_format=json",
                         "-f", "null", "-"])
    m = re.search(r"\{[^{}]*input_i[^{}]*\}", r.stderr, re.S)
    j = json.loads(m.group(0)) if m else {}
    for k, src in (("lufs", "input_i"), ("tp", "input_tp"),
                   ("lra", "input_lra"), ("thresh", "input_thresh")):
        try:
            out[k] = float(j.get(src, "nan"))
        except (TypeError, ValueError):
            out[k] = float("nan")
    return out


def decode_mono(path, work):
    raw = os.path.join(work, "a.raw")
    if not os.path.exists(raw):
        sh(FF_QUIET + ["-i", path, "-ac", "1", "-ar", "48000", "-f", "s16le", raw, "-y"])
    return np.fromfile(raw, dtype=np.int16).astype(np.float32) / 32768.0


def envelope_db(x, hop=480):
    n = len(x) // hop
    if n < 2:
        return np.array([-120.0]), hop
    env = np.sqrt(np.maximum((x[:n * hop].reshape(n, hop) ** 2).mean(axis=1), 1e-12))
    return 20 * np.log10(env), hop


def audio_transients(x):
    sr, hop = 48000, 480                      # 10 ms hops
    logdb, hop = envelope_db(x, hop)
    flux = np.maximum(np.diff(logdb, prepend=logdb[0]), 0)
    thr = flux.mean() + 2.0 * flux.std()
    on, last = [], -1e9
    for i in range(1, len(flux) - 1):
        t = i * hop / sr
        if flux[i] > thr and flux[i] >= flux[i - 1] and flux[i] >= flux[i + 1] \
                and t - last > 0.10:
            on.append(t)
            last = t
    return on


def tail_audio(x):
    """Trailing digital silence and how abruptly the mix stops."""
    sr = 48000
    alen = len(x) / sr
    db, hop = envelope_db(x)
    k = 0
    while k < len(db) and db[len(db) - 1 - k] < -60:
        k += 1
    silence = k * hop / sr
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
# OCR -- two passes per frame, 2 fps, parallel over frames
# ----------------------------------------------------------------------------
# tesseract spawns an OpenMP pool per process; with a worker pool of our own that
# oversubscribes the box badly and every call slows down. One thread each.
TESS_ENV = dict(os.environ, OMP_THREAD_LIMIT="1")


def _tess(img, scratch, psm="11", timeout=180):
    cv2.imwrite(scratch, img)
    try:
        r = subprocess.run(["tesseract", scratch, "stdout", "--psm", psm],
                           capture_output=True, text=True, timeout=timeout,
                           env=TESS_ENV)
    except subprocess.TimeoutExpired:
        return []
    return [l.strip() for l in r.stdout.splitlines() if l.strip()]


def ocr_frame(path, scratch):
    """TWO passes, deliberately.

    Tesseract binarises the page globally, so white-on-dark keyword pops sitting
    inside a dark image box are silently dropped by the plain pass -- that
    produced a false "3 pops missing" reading on an earlier run. Pass B isolates
    the bright text inside the box, inverts it to dark-on-light, doubles the size
    (tesseract wants ~30 px cap height) and adds a white border (it dislikes text
    touching the edge)."""
    im = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if im is None:
        return []
    out = list(_tess(im, scratch))                     # pass A: the page as-is
    b = _plate_bounds(im)                              # find the dark image box
    if b:
        x0, x1, y0, y1 = b
        crop = im[y0:y1, x0:x1]
        bw = 255 - ((crop > 190).astype(np.uint8) * 255)   # bright mask, inverted
        bw = cv2.resize(bw, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        bw = cv2.copyMakeBorder(bw, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
        out += _tess(bw, scratch)                      # pass B: dark-on-light, 2x
    # strip leading pipes/bars the accent underline fakes into the OCR
    return [re.sub(r"^[|\s_]+", "", l).strip() for l in out
            if re.sub(r"^[|\s_]+", "", l).strip()]


def _ocr_job(args):
    i, path, tmpdir = args
    scratch = os.path.join(tmpdir, f"_ocr_{i}.png")
    try:
        lines = ocr_frame(path, scratch)
    finally:
        if os.path.exists(scratch):
            os.remove(scratch)
    return i, lines


def norm_txt(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def ocr_inventory(d2, files, work, jobs):
    """OCR at OCR_FPS. Runs to completion before anything is analysed --
    reading a partial job silently truncates the inventory and makes whole
    sections look textless."""
    if not shutil.which("tesseract"):
        return None
    tmpdir = os.path.join(work, "ocrtmp")
    os.makedirs(tmpdir, exist_ok=True)
    tasks = [(i, os.path.join(d2, fn), tmpdir) for i, fn in enumerate(files)]
    per_t, done, t0 = {}, 0, time.time()
    with futures.ProcessPoolExecutor(max_workers=jobs) as ex:
        for i, lines in ex.map(_ocr_job, tasks, chunksize=4):
            per_t[i / OCR_FPS] = lines
            done += 1
            if done % 200 == 0:
                log(f"  [ocr] {done}/{len(tasks)} frames ({time.time() - t0:.0f}s)")
    shutil.rmtree(tmpdir, ignore_errors=True)
    return per_t


# ----------------------------------------------------------------------------
# Sections, persistence, pop events
# ----------------------------------------------------------------------------
def wordlike(ns):
    """Is this normalised OCR read plausibly a rendered word, or plate grain?

    Only used to decide whether a DISCOVERED pop counts toward per-section
    density. Matching against a sheet's intended strings deliberately does not
    use it -- a half-read during the 0.2 s pop-in still proves the pop rendered."""
    if len(ns) < 3:
        return False
    body = ns.replace(" ", "")
    if not body:
        return False
    alnum = sum(c.isalnum() for c in body)
    if alnum < 0.75 * len(body):
        return False
    return bool(re.search(r"[aeiou]", ns)) or bool(re.search(r"\d", ns))


def _cluster(reps_in):
    """Fuzzy-cluster normalised OCR strings.

    OCR of the same on-screen title is misread CONSISTENTLY but not identically
    ('Cartoon Cat' -> 'Cartoon' / 'Cat' / 'GartoonnGats'), so exact-match
    grouping splits one section title into a dozen strings and then none of them
    looks persistent -- and the title then gets counted as a pop in every
    section. Only recurring strings become cluster representatives; one-off
    grain is left as its own singleton, which keeps this linear enough to run on
    a ten-minute file."""
    reps = []
    assign = {}
    for s in sorted(reps_in, key=lambda x: -len(x)):
        hit = difflib.get_close_matches(s, reps, n=1, cutoff=POP_FUZZ)
        if hit:
            assign[s] = hit[0]
        else:
            reps.append(s)
            assign[s] = s
    return reps, assign


def per_frame_clusters(per_t, min_len=3, rep_min_count=3):
    counts = {}
    for ls in per_t.values():
        for s in set(norm_txt(x) for x in ls):
            if len(s) >= min_len:
                counts[s] = counts.get(s, 0) + 1
    recurring = [s for s, n in counts.items() if n >= rep_min_count and len(s) >= 4]
    reps, assign = _cluster(recurring)
    log(f"      {len(counts)} distinct OCR strings, {len(recurring)} recurring, "
        f"{len(reps)} clusters")

    def cid(ns):
        if ns in assign:
            return assign[ns]
        hit = difflib.get_close_matches(ns, reps, n=1, cutoff=POP_FUZZ)
        assign[ns] = hit[0] if hit else ns
        return assign[ns]

    frames = {}
    for t, ls in per_t.items():
        c = set()
        for s in ls:
            ns = norm_txt(s)
            if len(ns) >= min_len:
                c.add(cid(ns))
        frames[t] = c
    return frames, assign, cid


def auto_sections(frames, duration, min_span_s=20.0, min_cover=0.30):
    """Infer section boundaries from the persistent creature-name title.

    House rule 3: a persistent creature name sits top-centre on EVERY frame of a
    section. So a cluster that occupies a contiguous, well-covered span of the
    timeline is a section title, and the midpoints between those spans are the
    section boundaries. Best effort -- pass --sections/--sheet when you have the
    edit sheet, which is authoritative."""
    times = sorted(frames)
    if not times:
        return []
    occ = {}
    for t in times:
        for c in frames[t]:
            occ.setdefault(c, []).append(t)
    cands = []
    for c, tsx in occ.items():
        if len(c) < 6 or len(tsx) < min_span_s * OCR_FPS * min_cover:
            continue
        a, b = min(tsx), max(tsx)
        span = b - a
        if span < min_span_s:
            continue
        cover = len(tsx) / max(span * OCR_FPS, 1)
        if cover < min_cover:
            continue
        cands.append({"title": c, "t0": a, "t1": b, "n": len(tsx), "cover": cover})
    if not cands:
        return []
    # keep the strongest non-overlapping spans
    cands.sort(key=lambda d: -(d["n"]))
    kept = []
    for c in cands:
        if all(min(c["t1"], k["t1"]) - max(c["t0"], k["t0"]) < 0.4 *
               min(c["t1"] - c["t0"], k["t1"] - k["t0"]) for k in kept):
            kept.append(c)
    kept.sort(key=lambda d: d["t0"])
    if len(kept) < 2:
        return []
    secs = []
    for i, c in enumerate(kept):
        t0 = 0.0 if i == 0 else (kept[i - 1]["t1"] + c["t0"]) / 2.0
        t1 = duration if i == len(kept) - 1 else (c["t1"] + kept[i + 1]["t0"]) / 2.0
        secs.append({"name": c["title"], "t0": float(t0), "t1": float(t1)})
    return secs


def persistent_sets(frames, sections):
    """A cluster on >=50% of the frames of a section (or of the whole file) is
    the persistent title / caption furniture, not a keyword pop."""
    times = sorted(frames)
    glob_count = {}
    for t in times:
        for c in frames[t]:
            glob_count[c] = glob_count.get(c, 0) + 1
    persistent = {c for c, n in glob_count.items() if n >= 0.5 * max(len(times), 1)}
    per_sec = []
    for s in sections:
        tt = [t for t in times if s["t0"] <= t < s["t1"]]
        cnt = {}
        for t in tt:
            for c in frames[t]:
                cnt[c] = cnt.get(c, 0) + 1
        per_sec.append({c for c, n in cnt.items() if n >= 0.5 * max(len(tt), 1)})
    return persistent, per_sec


def pop_events(per_t, cid, sections, persistent, per_sec_persistent):
    """Group transient OCR lines into pop events.

    Events keep the raw OCR text (so spelling can be checked) and are grouped
    across adjacent samples by fuzzy identity. The persistent furniture of the
    section -- the creature-name title, a standing caption -- is dropped here,
    not counted as a pop."""
    dt = 1.0 / OCR_FPS
    events = []
    for t in sorted(per_t):
        sec = section_of(sections, t)
        drop = persistent | (per_sec_persistent[sec] if sec is not None
                             and sec < len(per_sec_persistent) else set())
        for s in per_t[t]:
            ns = norm_txt(s)
            u = s.upper()
            if not ns or len(ns) < 2:
                continue
            if cid(ns) in drop:
                continue
            if "ASSET SLOT" in u or "PLACEHOLDER" in u:
                continue
            hit = None
            for ev in reversed(events[-8:]):
                if t - ev["end"] <= 1.5 * dt + 1e-6 and \
                        difflib.SequenceMatcher(None, ev["text_n"], ns).ratio() >= POP_FUZZ:
                    hit = ev
                    break
            if hit is not None:
                hit["end"] = t
                hit["n"] += 1
                hit["reads"].add(s)
            else:
                events.append({"start": t, "end": t, "n": 1, "text": s,
                               "text_n": ns, "reads": {s}, "section": sec})
    return events


def section_of(sections, t):
    for i, s in enumerate(sections):
        if s["t0"] <= t < s["t1"]:
            return i
    return len(sections) - 1 if sections else None


def match_pops(events, intended):
    """Match pop events to the sheet's intended pop strings.

    A pop is only MISSPELLED if it never renders correctly on ANY frame -- a
    partial read during the 0.2 s pop-in animation is not a defect."""
    used = {}
    for ev in events:
        best, score = None, 0.0
        for p in intended:
            s = difflib.SequenceMatcher(None, ev["text_n"], norm_txt(p)).ratio()
            if s > score:
                best, score = p, s
        ev["intended"], ev["score"] = best, score
        if score >= POP_MATCH:
            used.setdefault(best, []).append(ev)
    missing = [p for p in intended if p not in used]
    misspelled = []
    for p, evs in used.items():
        ok = any(norm_txt(r) == norm_txt(p) for e in evs for r in e["reads"])
        if not ok:
            misspelled.append((p, sorted({r for e in evs for r in e["reads"]})))
    return missing, misspelled, used


def pop_taper(events, sections):
    """Pop count per section, plus the taper rule.

    A plain per-section floor does not catch a lazy finale: a floor of 2 passes a
    section with two filler pops. So take the MEDIAN section count and require
    the LAST section to be at least POP_TAPER_RATIO x that median. An editor was
    failed on exactly this shape -- dense pops through creature 5, two filler
    pops in 84 s by creature 7, zero editor-added pops in the 87 s finale."""
    if not sections:
        return None
    counts = [0] * len(sections)
    for ev in events:
        # a single-sample read, or a read that is not word-shaped, is plate grain
        if ev["n"] < POP_MIN_SAMPLES or not wordlike(ev["text_n"]):
            continue
        i = ev["section"]
        if i is not None and 0 <= i < len(counts):
            counts[i] += 1
    med = float(np.median(counts))
    last = counts[-1]
    need = POP_TAPER_RATIO * med
    below_floor = [i for i, c in enumerate(counts) if c < POP_FLOOR_PER_SECTION]
    return {"counts": counts, "median": med, "last": last, "need": need,
            "taper_ok": last >= need, "below_floor": below_floor,
            "floor_ok": not below_floor}


# ----------------------------------------------------------------------------
# Tail frames + contact sheets
# ----------------------------------------------------------------------------
def tail_check(path, work, duration, fps):
    d = os.path.join(work, "tail")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    start = max(duration - TAIL_S, 0)
    sh(FF_QUIET + ["-ss", str(start), "-i", path, os.path.join(d, "%05d.png"), "-y"])
    rows = []
    for i, fn in enumerate(sorted(os.listdir(d))):
        g = cv2.imread(os.path.join(d, fn), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        m, p95 = _hist_stats(g)
        rows.append({"t": start + i / fps, "mean": m, "p95": p95,
                     "std": float(g.std()), "file": os.path.join(d, fn)})
    return rows


def contact_sheets(path, work):
    d = os.path.join(work, "sheets")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    sh(FF_QUIET + ["-i", path,
                   "-vf", f"fps=1/{CONTACT_EVERY_S},scale=384:-1,"
                          f"tile={CONTACT_COLS}x{CONTACT_ROWS}:padding=4:margin=4",
                   os.path.join(d, "sheet_%02d.png"), "-y"])
    return [os.path.join(d, f) for f in sorted(os.listdir(d))]


# ----------------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------------
def verdict_table(rows):
    w0 = max(len(r[0]) for r in rows)
    w1 = max(len(r[1]) for r in rows)
    w2 = max(len(r[2]) for r in rows)
    line = ("+" + "-" * (w0 + 2) + "+" + "-" * (w1 + 2) + "+" + "-" * (w2 + 2)
            + "+" + "-" * 9 + "+")
    out = [line,
           f"| {'METRIC'.ljust(w0)} | {'MEASURED'.ljust(w1)} | {'TARGET'.ljust(w2)} "
           f"| {'VERDICT'.ljust(7)} |", line]
    for name, val, tgt, v in rows:
        out.append(f"| {name.ljust(w0)} | {val.ljust(w1)} | {tgt.ljust(w2)} "
                   f"| {v.ljust(7)} |")
    out.append(line)
    return "\n".join(out)


def load_sheet(args, duration):
    """Returns (intended_pops, sections, source_note)."""
    intended, sections, notes = None, None, []
    if args.sheet:
        with open(args.sheet) as f:
            sd = json.load(f)
        if sd.get("pops"):
            intended = [p["text"] if isinstance(p, dict) else str(p) for p in sd["pops"]]
        if sd.get("sections"):
            sections = [{"name": s.get("name", f"S{i+1}"),
                         "t0": float(s["t0"]), "t1": float(s["t1"])}
                        for i, s in enumerate(sd["sections"])]
        notes.append(f"sheet={os.path.basename(args.sheet)}")
    if args.pops_file:
        with open(args.pops_file) as f:
            intended = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        notes.append(f"pops={os.path.basename(args.pops_file)}")
    if args.sections and args.sections not in ("auto", "none"):
        if os.path.exists(args.sections):
            with open(args.sections) as f:
                sd = json.load(f)
            sd = sd.get("sections", sd)
            sections = [{"name": s.get("name", f"S{i+1}"), "t0": float(s["t0"]),
                         "t1": float(s["t1"])} for i, s in enumerate(sd)]
        else:
            bounds = [float(x) for x in args.sections.split(",") if x.strip()]
            marks = [0.0] + bounds + [duration]
            sections = [{"name": f"S{i+1}", "t0": a, "t1": b}
                        for i, (a, b) in enumerate(zip(marks, marks[1:]))]
        notes.append("sections=explicit")
    return intended, sections, ", ".join(notes) if notes else "no sheet supplied"


def main():
    ap = argparse.ArgumentParser(description="Stage 6 measured QC")
    ap.add_argument("video")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--sheet", default=None, help="edit sheet JSON (pops + sections)")
    ap.add_argument("--sections", default="auto",
                    help="auto | none | comma-separated boundary times | file.json")
    ap.add_argument("--pops-file", default=None, help="intended pop strings, one per line")
    ap.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1))
    ap.add_argument("--no-ocr", action="store_true")
    ap.add_argument("--json", default=None, help="write the full report as JSON")
    args = ap.parse_args()

    path = os.path.abspath(args.video)
    if not os.path.exists(path):
        sys.exit(f"no such file: {path}")
    work = os.path.abspath(args.workdir) if args.workdir else tempfile.mkdtemp(prefix="qc_")
    os.makedirs(work, exist_ok=True)

    sp = probe(path)
    fps = sp["fps"] or 30.0
    intended, sections_in, sheet_note = load_sheet(args, sp["duration"])
    print(f"\n=== QC: {os.path.basename(path)} "
          f"({sp['duration']:.2f}s, {sp['size_mb']:.1f} MB) === [{sheet_note}]\n")

    log("[1/7] extracting 2 fps sample frames")
    d2, files = extract_samples(path, work)
    log(f"      {len(files)} frames")

    log("[2/7] motion + dead zones")
    deltas, times = motion_series(d2, files)
    dz = dead_zones(deltas, times)

    log("[3/7] content box")
    box, cover = content_box(d2, files)
    log(f"      box={box} cover={cover:.2f}"
        + ("  (full-bleed layout)" if cover > 0.85 else "  (boxed layout)"))

    log("[4/7] full-rate walk: cuts + content-box luminance")
    cuts, lum = full_rate_walk(path, fps, box)
    spans = shot_lengths(cuts, sp["duration"])

    log("[5/7] audio")
    au = audio_stats(path)
    x = decode_mono(path, work)
    onsets = audio_transients(x)
    ta = tail_audio(x)
    sync, missed = sync_score(cuts, onsets)

    per_t = None
    if not args.no_ocr:
        log(f"[6/7] OCR, two passes per frame at {OCR_FPS} fps, {args.jobs} workers")
        per_t = ocr_inventory(d2, files, work, args.jobs)

    sections, frames, persistent, per_sec_persistent = [], {}, set(), []
    events, missing, misspelled, used, taper = [], [], [], {}, None
    sec_source = "n/a"
    if per_t:
        frames, _assign, cid = per_frame_clusters(per_t)
        if sections_in:
            sections, sec_source = sections_in, "sheet/explicit"
        elif args.sections == "auto":
            sections = auto_sections(frames, sp["duration"])
            sec_source = "auto (persistent title)" if sections else "auto (failed)"
        persistent, per_sec_persistent = persistent_sets(frames, sections)
        events = pop_events(per_t, cid, sections, persistent, per_sec_persistent)
        if intended:
            missing, misspelled, used = match_pops(events, intended)
        taper = pop_taper(events, sections)

    log("[7/7] tail + contact sheets")
    tail = tail_check(path, work, sp["duration"], fps)
    sheets = contact_sheets(path, work)

    # ---------------- derived ----------------
    avg_motion = float(deltas.mean()) if deltas.size else 0.0
    dark = [r for r in lum if r[1] < DARK_MEAN]
    dark_flat = [r for r in dark if r[2] < DARK_P95_OK]
    worst_dz = max((z["dur"] for z in dz), default=0.0)
    longest_shot = spans[0][2] if spans else sp["duration"]
    tail_black = [r for r in tail if r["mean"] < TAIL_BLACK_MEAN and r["std"] < TAIL_FLAT_STD]
    tail_white = [r for r in tail if r["mean"] > TAIL_WHITE_MEAN and r["std"] < TAIL_FLAT_STD]
    tail_flat = [r for r in tail if r["std"] < TAIL_FLAT_STD]
    av_delta = abs(ta["audio_len"] - sp["duration"])
    pops_counted = [e for e in events
                    if e["n"] >= POP_MIN_SAMPLES and wordlike(e["text_n"])]

    def PF(ok, warn=False):
        return "WARN" if warn else ("PASS" if ok else "FAIL")

    R = []
    mv = ("PASS" if avg_motion >= BENCH_MOTION_GOOD else
          "FAIL" if avg_motion <= BENCH_MOTION_FAIL + 3 else "WARN")
    R.append(("Motion (avg %px changed / 0.5s)", f"{avg_motion:.1f}%",
              f">={BENCH_MOTION_GOOD} (best {BENCH_MOTION_BEST})", mv))
    R.append(("Motion floor / peak",
              f"{deltas.min():.1f}% / {deltas.max():.1f}%" if deltas.size else "n/a",
              "-", "INFO"))
    R.append((f"Dead zones >={DEADZONE_MIN_S:.0f}s (<{DEADZONE_PCT:.0f}%)",
              f"{len(dz)}", "0", PF(not dz)))
    R.append(("Longest dead zone", f"{worst_dz:.1f}s", f"<{DEADZONE_MIN_S:.0f}s",
              "PASS" if worst_dz < DEADZONE_MIN_S else
              "FAIL" if worst_dz > DEADZONE_BAD_S else "WARN"))
    R.append(("One asset held (longest shot)", f"{longest_shot:.1f}s",
              f"<={SHOT_MAX_S:.0f}s", "PASS" if longest_shot <= SHOT_MAX_S else "FAIL"))
    R.append(("Integrated loudness", f"{au['lufs']:.2f} LUFS", f"{LUFS_LO} to {LUFS_HI}",
              PF(LUFS_LO <= au["lufs"] <= LUFS_HI)))
    R.append(("True peak", f"{au['tp']:.2f} dBTP", f"<{TRUE_PEAK_MAX}",
              PF(au["tp"] < TRUE_PEAK_MAX)))
    R.append(("Loudness range (LRA)", f"{au['lra']:.2f} LU", f">{LRA_MIN} LU",
              PF(au["lra"] > LRA_MIN)))
    R.append(("Mean / max volume",
              f"{au['mean_volume']:.1f} / {au['max_volume']:.1f} dB", "max < 0 dB",
              PF(au["max_volume"] is not None and au["max_volume"] < 0)))
    R.append(("Clipped samples (0 dBFS)", f"{au['clipped_samples']}", "0",
              PF(au["clipped_samples"] == 0)))
    R.append(("Hard cuts detected", f"{len(cuts)}", "-", "INFO"))
    R.append(("Audio transients", f"{len(onsets)}", "-", "INFO"))
    R.append((f"Cuts w/ transient <={SYNC_WINDOW_S}s",
              "n/a" if sync is None else f"{sync:.0f}%", f">={SYNC_TARGET_PCT:.0f}%",
              "INFO" if sync is None else PF(sync >= SYNC_TARGET_PCT)))
    R.append(("Content-box luminance (mean)",
              f"{np.mean([r[1] for r in lum]):.1f} (frame {np.mean([r[3] for r in lum]):.0f})",
              "-", "INFO"))
    R.append((f"Dark frames (box mean<{DARK_MEAN})", f"{len(dark)} / {len(lum)}",
              "-", "INFO"))
    R.append(("...of those, flat (p95<%d)" % DARK_P95_OK, f"{len(dark_flat)}", "0",
              PF(not dark_flat)))
    R.append(("Resolution / fps", f"{sp['width']}x{sp['height']} @ {sp['fps']:.2f}",
              "1920x1080 @ 30",
              PF((sp["width"], sp["height"]) == (1920, 1080) and abs(sp["fps"] - 30) < 0.5)))
    R.append(("Video codec", f"{sp['vcodec']} {sp['profile']} {sp['pix_fmt']}",
              "h264 yuv420p", PF(sp["vcodec"] == "h264", warn=sp["vcodec"] != "h264")))
    vb = sp["vbitrate_mbps"]
    R.append(("Video bitrate", f"{vb:.2f} Mbps",
              f">{BITRATE_TARGET_MBPS} (bench {BITRATE_GOOD_MBPS})",
              "FAIL" if vb < BITRATE_TARGET_MBPS else
              "PASS" if vb >= BITRATE_GOOD_MBPS else "WARN"))
    R.append(("Audio codec / bitrate", f"{sp['acodec']} {sp['abitrate_kbps']:.0f} kbps",
              f">={ABITRATE_MIN_KBPS:.0f} kbps", PF(sp["abitrate_kbps"] >= ABITRATE_MIN_KBPS)))
    R.append(("Sections detected", f"{len(sections)} ({sec_source})", "-", "INFO"))
    if intended:
        R.append(("Keyword pops found (OCR)", f"{len(used)}",
                  f"{len(intended)} intended", PF(not missing)))
        R.append(("Missing pops", f"{len(missing)}", "0", PF(not missing)))
        R.append(("Misspelled pops", f"{len(misspelled)}", "0", PF(not misspelled)))
    else:
        R.append(("Keyword pops found (OCR)", f"{len(pops_counted)} discovered",
                  "needs sheet", "INFO"))
        R.append(("Pop spelling vs sheet", "no intended list", "--sheet/--pops-file", "SKIP"))
    if taper:
        R.append(("Pops per section",
                  " ".join(str(c) for c in taper["counts"]),
                  f">={POP_FLOOR_PER_SECTION} each", PF(taper["floor_ok"])))
        R.append(("Pop taper (last vs median)",
                  f"last {taper['last']} vs median {taper['median']:.1f}",
                  f"last >= {POP_TAPER_RATIO} x median (>= {taper['need']:.1f})",
                  PF(taper["taper_ok"])))
    else:
        R.append(("Pops per section", "no sections", "-", "SKIP"))
        R.append(("Pop taper (last vs median)", "no sections", "-", "SKIP"))
    R.append(("A/V stream length delta", f"{av_delta:.2f}s", f"<{AV_DELTA_MAX:.2f}s",
              PF(av_delta < AV_DELTA_MAX)))
    R.append(("Trailing digital silence", f"{ta['trailing_silence']:.2f}s",
              f"<{TRAILING_SILENCE_MAX:.2f}s",
              PF(ta["trailing_silence"] < TRAILING_SILENCE_MAX)))
    R.append(("Last 5s black frames", f"{len(tail_black)}", "0", PF(not tail_black)))
    R.append(("Last 5s blank white frames", f"{len(tail_white)}", "0", PF(not tail_white)))
    R.append(("Last 5s content present", f"{len(tail) - len(tail_flat)} / {len(tail)}",
              "all frames", PF(not tail_flat)))

    print(verdict_table(R))
    fails = [r[0] for r in R if r[3] == "FAIL"]
    warns = [r[0] for r in R if r[3] == "WARN"]
    print(f"\nVERDICT: {len(fails)} FAIL, {len(warns)} WARN, "
          f"{sum(1 for r in R if r[3] == 'PASS')} PASS")
    if fails:
        print("  FAIL: " + "; ".join(fails))
    if warns:
        print("  WARN: " + "; ".join(warns))

    print("\n--- DEAD ZONES (never merged across a high-motion sample) ---")
    if not dz:
        print(f"  none >= {DEADZONE_MIN_S:.0f}s")
    for z in dz[:20]:
        print(f"  {ts(z['start'])}-{ts(z['end'])}  {z['dur']:.1f}s  "
              f"mean {z['mean']:.1f}%  peak {z['peak']:.1f}%")
    if len(dz) > 20:
        print(f"  ... {len(dz) - 20} more")

    print("\n--- LONGEST HOLDS (no hard cut) ---")
    for a, b, d in spans[:8]:
        print(f"  {ts(a)}-{ts(b)}  {d:.1f}s" + ("   <-- over 8s" if d > SHOT_MAX_S else ""))

    print("\n--- CUTS WITHOUT A NEARBY TRANSIENT ---")
    if missed:
        print("  " + ", ".join(ts(m) for m in missed[:40])
              + (f"  ... (+{len(missed) - 40})" if len(missed) > 40 else ""))
    else:
        print("  none")

    print("\n--- DARK-AND-FLAT FRAMES (content box mean<%d and p95<%d) ---"
          % (DARK_MEAN, DARK_P95_OK))
    if not dark_flat:
        print("  none")
    else:
        runs = []
        for r in dark_flat:
            if runs and r[0] - runs[-1][1] < 0.5:
                runs[-1][1] = r[0]
            else:
                runs.append([r[0], r[0]])
        for a, b in runs[:15]:
            print(f"  {ts(a)}-{ts(b)}  {b - a:.1f}s")
        if len(runs) > 15:
            print(f"  ... {len(runs) - 15} more runs")

    if per_t is not None:
        print("\n--- ON-SCREEN TEXT ---")
        print(f"  OCR frames: {len(per_t)} at {OCR_FPS} fps, two passes each")
        print(f"  persistent furniture (filtered): "
              f"{sorted(persistent)[:6] if persistent else 'none'}")
        for i, s in enumerate(sections):
            n = taper["counts"][i] if taper else 0
            print(f"  section {i+1:>2}  {ts(s['t0'])}-{ts(s['t1'])}  "
                  f"{s['t1']-s['t0']:6.1f}s  pops {n:>3}  title~{s['name'][:44]!r}")
        if intended:
            if missing:
                print(f"  MISSING intended pops: {missing}")
            for p, got in misspelled:
                print(f"  SPELLING: intended {p!r} -> rendered {got!r}")
            for p, evs in sorted(used.items()):
                e = evs[0]
                print(f"  OK  {p!r} first at {ts(e['start'])} "
                      f"({len(evs)} event(s), best read {e['text']!r})")
        else:
            top = sorted(pops_counted, key=lambda e: e["start"])[:25]
            for e in top:
                print(f"  {ts(e['start'])}-{ts(e['end'])} x{e['n']}  {e['text']!r}")
            if len(pops_counted) > 25:
                print(f"  ... {len(pops_counted) - 25} more discovered pop events")

    print("\n--- AUDIO TAIL ---")
    print(f"  audio {ta['audio_len']:.3f}s vs container {sp['duration']:.3f}s | "
          f"trailing silence {ta['trailing_silence']:.2f}s | "
          f"final-second level drop {ta['tail_drop_db']:.1f} dB")

    print("\n--- LAST 5 SECONDS ---")
    for r in tail[::15]:
        print(f"  {ts(r['t'])}  mean {r['mean']:6.2f}  p95 {r['p95']:6.2f}  "
              f"std {r['std']:6.2f}")
    if tail:
        r = tail[-1]
        print(f"  FINAL {ts(r['t'])}  mean {r['mean']:6.2f}  p95 {r['p95']:6.2f}  "
              f"std {r['std']:6.2f}")

    print("\n--- CONTACT SHEETS (review these visually) ---")
    for s in sheets:
        print("  " + s)

    if args.json:
        rep = {
            "file": path, "specs": sp, "sheet": sheet_note,
            "motion_avg": avg_motion,
            "motion_min": float(deltas.min()) if deltas.size else None,
            "motion_max": float(deltas.max()) if deltas.size else None,
            "dead_zones": dz, "longest_shot": longest_shot,
            "longest_holds": [{"t0": a, "t1": b, "dur": d} for a, b, d in spans[:20]],
            "audio": au, "audio_tail": ta, "sync_pct": sync,
            "cuts": len(cuts), "onsets": len(onsets),
            "cuts_without_transient": missed,
            "dark_frames": len(dark), "dark_flat_frames": len(dark_flat),
            "content_box": box, "content_box_cover": cover,
            "sections": sections, "section_source": sec_source,
            "pops_discovered": len(pops_counted),
            "pop_taper": taper,
            "missing_pops": missing,
            "misspelled_pops": [{"intended": p, "rendered": g} for p, g in misspelled],
            "tail_black": len(tail_black), "tail_white": len(tail_white),
            "tail_flat": len(tail_flat),
            "verdict": {r[0]: {"measured": r[1], "target": r[2], "verdict": r[3]}
                        for r in R},
            "fails": fails, "warns": warns,
        }
        with open(args.json, "w") as f:
            json.dump(rep, f, indent=2, default=float)
        print(f"\nJSON report: {args.json}")

    print(f"\nWorkdir: {work}")
    if not args.keep:
        shutil.rmtree(os.path.join(work, "f2"), ignore_errors=True)
        for f in ("a.raw",):
            p = os.path.join(work, f)
            if os.path.exists(p):
                os.remove(p)
        print("(frames discarded; pass --keep to retain them)")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
