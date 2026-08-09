#!/usr/bin/env python3
"""Pull frames from a competitor video and measure them.

Two sources, same output, so analysis code never cares which one you had:

  LOCAL   a downloaded .mp4      -> ffmpeg, full resolution, any interval
  REMOTE  YouTube storyboards    -> sprite sheets, 320x180, ~5s interval

The storyboard path exists because YouTube's media CDN signs its URLs against
the requesting IP, and this machine egresses from a rotating pool, so media
download is architecturally impossible here (docs/youtube-access-2026-08-09.md).
Storyboards are a separate, unsigned, unmetered asset that nothing blocks. They
gave 99-100% runtime coverage on both reference channels.

What each source can answer:

  structure, layout, palette, canvas logic, proportions   BOTH
  shot pacing, Ken Burns amount, animation timing, audio  LOCAL ONLY

A ~5s sampling interval cannot see anything faster than 5s. The tool refuses to
emit those metrics from storyboards rather than emitting a wrong number.

Usage
  competitor_frames.py fetch  <video-id> [--out DIR]
  competitor_frames.py fetch  <file.mp4> [--out DIR] [--fps 2]
  competitor_frames.py measure <DIR>
  competitor_frames.py sheet   <DIR> [--cols 6] [--rows 5]

Typical:
  competitor_frames.py fetch lrY0ErBfytQ --out research/m-simplified
  competitor_frames.py measure research/m-simplified
  competitor_frames.py sheet   research/m-simplified     # then read the PNGs
"""
import argparse, json, os, subprocess, sys
from collections import Counter

import numpy as np
from PIL import Image

UA = {"User-Agent": "horror-engine/1.0 (competitor style analysis)"}

# There can be more than one yt-dlp on a machine and they do NOT behave alike.
# Here, /usr/local/bin/yt-dlp loads the PO-token plugin and that plugin makes a
# plain `-J` extraction fail with "Requested format is not available", while the
# PATH binary (same version) succeeds. Storyboards need no plugin, so probe and
# take the first binary that actually returns usable JSON rather than hardcoding
# either one.
import shutil

def _ytdlp_candidates():
    seen, out = set(), []
    for c in (shutil.which("yt-dlp"), "/root/.local/bin/yt-dlp", "/usr/local/bin/yt-dlp"):
        if c and os.path.exists(c) and c not in seen:
            seen.add(c); out.append(c)
    return out or ["yt-dlp"]

# Storyboard resolution is CLIENT DEPENDENT and the difference is 4x pixel area:
# mweb exposes 320x180 (storyboard3_L3); android_vr, tv_embedded and
# web_embedded all cap at 160x90. Always sweep, never assume.
STORYBOARD_CLIENTS = ["mweb", "web", "tv_embedded", "android_vr"]


# ---------------------------------------------------------------- fetch

def _probe_storyboards(video_id):
    """Return the highest-resolution storyboard format across several clients."""
    best = None
    for client in STORYBOARD_CLIENTS:
        info = None
        for binpath in _ytdlp_candidates():
            try:
                out = subprocess.run(
                    [binpath, "-J", "--no-warnings", "--skip-download",
                     "--extractor-args", f"youtube:player_client={client}",
                     f"https://www.youtube.com/watch?v={video_id}"],
                    capture_output=True, text=True, timeout=120)
                if out.returncode == 0 and out.stdout.strip().startswith("{"):
                    info = json.loads(out.stdout)
                    break
            except Exception:
                continue
        if info is None:
            print(f"  {client:14s} extraction failed on all yt-dlp binaries"); continue

        for f in info.get("formats", []):
            if f.get("format_note") != "storyboard" and not str(f.get("format_id", "")).startswith("sb"):
                continue
            w, h = f.get("width") or 0, f.get("height") or 0
            if best is None or w * h > best["w"] * best["h"]:
                best = {"client": client, "id": f.get("format_id"), "w": w, "h": h,
                        "rows": f.get("rows"), "columns": f.get("columns"),
                        "fragments": f.get("fragments") or [],
                        "duration": info.get("duration"), "title": info.get("title")}
        if best:
            print(f"  {client:14s} {best['id']} {best['w']}x{best['h']} "
                  f"{best['columns']}x{best['rows']} per sheet, "
                  f"{len(best['fragments'])} sheets")
    return best


def fetch_storyboards(video_id, outdir):
    import requests
    os.makedirs(f"{outdir}/frames", exist_ok=True)
    print(f"probing storyboard tracks for {video_id}")
    sb = _probe_storyboards(video_id)
    if not sb:
        sys.exit("no storyboard track found on any client")

    print(f"\nusing {sb['client']} {sb['id']} at {sb['w']}x{sb['h']}")
    # TILE size is authoritative, the grid is NOT. The final sprite sheet is
    # partial: on this video 12 sheets arrive at 960x540 (3x3 of 320x180) and
    # the last at 640x180, which is 2 tiles on one row. Splitting that by the
    # reported 3x3 carves it into nine 213x60 slivers. So derive the grid from
    # each sheet's own dimensions against the fixed tile size.
    tw, th = sb["w"], sb["h"]
    n = 0
    for frag in sb["fragments"]:
        r = requests.get(frag["url"], headers=UA, timeout=60)
        r.raise_for_status()
        import io
        sheet = Image.open(io.BytesIO(r.content)).convert("RGB")
        cols_i, rows_i = max(1, sheet.width // tw), max(1, sheet.height // th)
        for ry in range(rows_i):
            for rx in range(cols_i):
                tile = sheet.crop((rx * tw, ry * th, (rx + 1) * tw, (ry + 1) * th))
                if tile.size != (tw, th):
                    continue                      # ragged edge, not a real frame
                if np.asarray(tile).std() < 1.0:
                    continue                      # blank padding tile
                tile.save(f"{outdir}/frames/f_{n:05d}.png")
                n += 1

    dur = sb["duration"] or 0
    interval = dur / n if n else 0
    meta = {"source": "storyboard", "video_id": video_id, "title": sb["title"],
            "duration_s": dur, "frame_count": n, "interval_s": round(interval, 4),
            "frame_w": tw, "frame_h": th, "client": sb["client"],
            "coverage_pct": round(100.0 * (n * interval) / dur, 1) if dur else None,
            "blind_to": ["shot pacing", "ken burns amount", "icon/caption animation timing",
                         "screen shake", "glitch effects", "cuts per minute", "all audio"],
            "_blind_note": f"sampling interval is {interval:.2f}s; nothing faster than that is observable"}
    json.dump(meta, open(f"{outdir}/meta.json", "w"), indent=2)
    print(f"\n{n} frames at {interval:.2f}s, {tw}x{th}, covering {meta['coverage_pct']}% of {dur}s")
    return meta


def fetch_local(path, outdir, fps):
    os.makedirs(f"{outdir}/frames", exist_ok=True)
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip())
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", path,
                    "-vf", f"fps={fps}", f"{outdir}/frames/f_%05d.png"], check=True)
    n = len(os.listdir(f"{outdir}/frames"))
    im = Image.open(f"{outdir}/frames/f_00001.png")
    meta = {"source": "local", "path": os.path.abspath(path), "duration_s": dur,
            "frame_count": n, "interval_s": round(1.0 / fps, 4),
            "frame_w": im.width, "frame_h": im.height, "coverage_pct": 100.0,
            "blind_to": [], "_blind_note": "full resolution, everything observable"}
    json.dump(meta, open(f"{outdir}/meta.json", "w"), indent=2)
    print(f"{n} frames at {1/fps:.2f}s, {im.width}x{im.height}, {dur:.1f}s")
    return meta


# ---------------------------------------------------------------- measure

def _hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(*(int(c) for c in rgb))


def _canvas_family(a):
    """Classify the frame's ground by sampling the border ring.

    The centre is the subject; the border is the canvas. Sampling the ring
    rather than the whole frame is what stops a big dark creature from being
    read as a black canvas.
    """
    h, w, _ = a.shape
    m = max(2, min(h, w) // 24)
    ring = np.concatenate([a[:m].reshape(-1, 3), a[-m:].reshape(-1, 3),
                           a[:, :m].reshape(-1, 3), a[:, -m:].reshape(-1, 3)])
    med = np.median(ring, axis=0)
    luma = 0.2126 * med[0] + 0.7152 * med[1] + 0.0722 * med[2]
    spread = float(np.median(np.abs(ring - med)))
    # A busy border means a bled photographic scene, not a flat canvas.
    if spread > 18:
        fam = "scene"
    elif luma >= 200:
        fam = "white"
    elif luma <= 55:
        fam = "black"
    else:
        fam = "grey"
    return fam, _hex(med), round(float(luma), 1), round(spread, 1)


def _subject(a, canvas_rgb):
    """Bounding box and median luma of whatever differs from the canvas."""
    diff = np.abs(a.astype(np.int16) - np.array(canvas_rgb, dtype=np.int16)).sum(2)
    mask = diff > 60
    if mask.sum() < a.shape[0] * a.shape[1] * 0.002:
        return None
    ys, xs = np.where(mask)
    h, w, _ = a.shape
    px = a[mask]
    luma = 0.2126 * px[:, 0] + 0.7152 * px[:, 1] + 0.0722 * px[:, 2]
    return {"x0": round(float(xs.min() / w), 4), "x1": round(float(xs.max() / w), 4),
            "y0": round(float(ys.min() / h), 4), "y1": round(float(ys.max() / h), 4),
            "cx": round(float(xs.mean() / w), 4),
            "area_pct": round(100.0 * mask.mean(), 2),
            "median_luma": round(float(np.median(luma)), 1)}


def measure(outdir):
    meta = json.load(open(f"{outdir}/meta.json"))
    files = sorted(os.listdir(f"{outdir}/frames"))
    rows, prev = [], None
    for i, fn in enumerate(files):
        a = np.asarray(Image.open(f"{outdir}/frames/{fn}").convert("RGB"))
        fam, chex, cluma, spread = _canvas_family(a)
        canvas_rgb = tuple(int(chex[j:j + 2], 16) for j in (1, 3, 5))
        subj = _subject(a, canvas_rgb)
        rec = {"i": i, "t": round(i * meta["interval_s"], 2), "canvas": fam,
               "canvas_hex": chex, "canvas_luma": cluma, "border_spread": spread,
               "subject": subj}
        # Frame-to-frame change is only meaningful at a small interval. Emitting
        # it from ~5s storyboards would look like a motion metric and be noise.
        if meta["interval_s"] <= 1.0 and prev is not None:
            g = np.asarray(Image.open(f"{outdir}/frames/{fn}").convert("L"), dtype=np.float32)
            rec["change_pct"] = round(float((np.abs(g - prev) > 12).mean() * 100), 2)
        if meta["interval_s"] <= 1.0:
            prev = np.asarray(Image.open(f"{outdir}/frames/{fn}").convert("L"), dtype=np.float32)
        rows.append(rec)

    fams = Counter(r["canvas"] for r in rows)
    total = len(rows)
    summary = {"frames": total, "interval_s": meta["interval_s"],
               "canvas_pct": {k: round(100.0 * v / total, 1) for k, v in fams.most_common()},
               "canvas_hex_mode": {k: Counter(r["canvas_hex"] for r in rows if r["canvas"] == k)
                                   .most_common(1)[0][0] for k in fams},
               "blind_to": meta["blind_to"]}

    # The luminance rule: on which canvas does a dark subject land, and a bright one?
    lum = [(r["canvas"], r["subject"]["median_luma"]) for r in rows
           if r["subject"] and r["canvas"] in ("white", "black")]
    if lum:
        summary["subject_luma_by_canvas"] = {
            fam: {"n": sum(1 for f, _ in lum if f == fam),
                  "median": round(float(np.median([l for f, l in lum if f == fam])), 1),
                  "range": [round(float(min(l for f, l in lum if f == fam)), 1),
                            round(float(max(l for f, l in lum if f == fam)), 1)]}
            for fam in ("white", "black") if any(f == fam for f, _ in lum)}

    json.dump({"summary": summary, "frames": rows},
              open(f"{outdir}/metrics.json", "w"), indent=1)
    print(json.dumps(summary, indent=2))
    if meta["blind_to"]:
        print("\nNOT MEASURABLE from this source:")
        for b in meta["blind_to"]:
            print(f"  - {b}")
    return summary


# ---------------------------------------------------------------- sheet

def sheet(outdir, cols, rows_per):
    """Contact sheets with a timestamp burned into each cell, for reading."""
    from PIL import ImageDraw
    meta = json.load(open(f"{outdir}/meta.json"))
    files = sorted(os.listdir(f"{outdir}/frames"))
    os.makedirs(f"{outdir}/sheets", exist_ok=True)
    per, cw, ch, pad = cols * rows_per, 320, 180, 18
    made = []
    for s in range(0, len(files), per):
        chunk = files[s:s + per]
        sh = Image.new("RGB", (cols * cw, rows_per * (ch + pad)), (24, 24, 24))
        d = ImageDraw.Draw(sh)
        for k, fn in enumerate(chunk):
            im = Image.open(f"{outdir}/frames/{fn}").convert("RGB").resize((cw, ch))
            x, y = (k % cols) * cw, (k // cols) * (ch + pad)
            sh.paste(im, (x, y + pad))
            t = (s + k) * meta["interval_s"]
            d.text((x + 4, y + 4), f"{int(t//60)}:{t%60:05.2f}", fill=(255, 255, 255))
        p = f"{outdir}/sheets/sheet_{s//per:02d}.png"
        sh.save(p); made.append(p)
    print(f"{len(made)} contact sheets -> {outdir}/sheets/")
    for p in made:
        print(" ", p)
    return made


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch"); f.add_argument("target"); f.add_argument("--out", required=True)
    f.add_argument("--fps", type=float, default=2.0)
    m = sub.add_parser("measure"); m.add_argument("dir")
    s = sub.add_parser("sheet"); s.add_argument("dir")
    s.add_argument("--cols", type=int, default=6); s.add_argument("--rows", type=int, default=5)
    a = ap.parse_args()

    if a.cmd == "fetch":
        if os.path.exists(a.target):
            fetch_local(a.target, a.out, a.fps)
        else:
            fetch_storyboards(a.target, a.out)
    elif a.cmd == "measure":
        measure(a.dir)
    else:
        sheet(a.dir, a.cols, a.rows)


if __name__ == "__main__":
    main()
