#!/usr/bin/env python3
"""assemble.py — the Sound Designer "hands".

Takes a cue sheet (with assets resolved) + the mastered VO and renders the
final mix: music bed (fit + faded + placed), SFX hits, sidechain-ducked under
the voice, then mastered to the YouTube loudness target.

Asset resolution per cue, in order:
  1. cue["asset"]                      (explicit path, e.g. filled by the Epidemic MCP)
  2. <assets>/<cue id>.<ext>           (manual-drop convenience: m1.mp3, s3.wav, ...)
  3. skip (warn)

Usage:
  assemble.py --cues cues.json --vo vo.mp3 --out "Title (mixed).mp3"
              [--assets ./assets] [--stems ./stems] [--mux-into in.mp4]
              [--music-db 0] [--sfx-db 0] [--no-duck]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import tempfile

from common import FFMPEG, run, media_info, fmt_ts

SR = 48000
CH = "stereo"


def resolve_asset(cue: dict, assets_dir: str | None) -> str | None:
    if cue.get("asset") and os.path.exists(cue["asset"]):
        return cue["asset"]
    if assets_dir:
        hits = glob.glob(os.path.join(assets_dir, cue["id"] + ".*"))
        if hits:
            return sorted(hits)[0]
    return None


def dur_of(path: str) -> float:
    return media_info(path)["duration"]


def render_music_seg(asset, start, dur, fin, fout, gain_db, work, idx) -> str:
    """Fit an asset to `dur`, fade, gain, delay to `start`; write a wav."""
    out = os.path.join(work, f"m_{idx}.wav")
    loop = dur_of(asset) < dur - 0.1
    fout_st = max(0.0, dur - fout)
    delay_ms = int(round(start * 1000))
    af = (
        f"aformat=sample_rates={SR}:channel_layouts={CH},"
        f"atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d={fin:.3f},"
        f"afade=t=out:st={fout_st:.3f}:d={fout:.3f},"
        f"volume={gain_db:.2f}dB,"
        f"adelay={delay_ms}:all=1"
    )
    cmd = [FFMPEG, "-hide_banner", "-v", "error", "-y"]
    if loop:
        cmd += ["-stream_loop", "-1"]
    cmd += ["-i", asset, "-filter:a", af, "-ac", "2", "-ar", str(SR), out]
    run(cmd)
    return out


def render_sfx_seg(asset, at, gain_db, work, idx) -> str:
    out = os.path.join(work, f"s_{idx}.wav")
    delay_ms = int(round(at * 1000))
    af = (
        f"aformat=sample_rates={SR}:channel_layouts={CH},"
        f"afade=t=in:st=0:d=0.005,volume={gain_db:.2f}dB,"
        f"adelay={delay_ms}:all=1"
    )
    run([FFMPEG, "-hide_banner", "-v", "error", "-y", "-i", asset,
         "-filter:a", af, "-ac", "2", "-ar", str(SR), out])
    return out


def mix_bus(segments: list[str], out: str, total: float):
    """Sum segments (no auto-normalize) into one bus of length `total`."""
    if not segments:
        # silent bus
        run([FFMPEG, "-hide_banner", "-v", "error", "-y", "-f", "lavfi",
             "-i", f"anullsrc=r={SR}:cl={CH}", "-t", f"{total:.3f}", out])
        return
    if len(segments) == 1:
        inputs = ["-i", segments[0]]
        fc = f"[0:a]apad=whole_dur={total:.3f},atrim=0:{total:.3f}[o]"
    else:
        inputs = []
        for s in segments:
            inputs += ["-i", s]
        mixin = "".join(f"[{i}:a]" for i in range(len(segments)))
        fc = (f"{mixin}amix=inputs={len(segments)}:normalize=0:"
              f"dropout_transition=0[m];[m]apad=whole_dur={total:.3f},"
              f"atrim=0:{total:.3f}[o]")
    run([FFMPEG, "-hide_banner", "-v", "error", "-y", *inputs,
         "-filter_complex", fc, "-map", "[o]", "-ac", "2", "-ar", str(SR), out])


def to_wav(src: str, out: str, total: float | None = None):
    af = f"aformat=sample_rates={SR}:channel_layouts={CH}"
    cmd = [FFMPEG, "-hide_banner", "-v", "error", "-y", "-i", src,
           "-filter:a", af, "-ac", "2", "-ar", str(SR)]
    if total:
        cmd += ["-t", f"{total:.3f}"]
    run(cmd + [out])


def duck(music: str, vo: str, out: str):
    """Sidechain-compress the music bus, keyed by the voice."""
    fc = (
        "[1:a]aformat=sample_rates=%d:channel_layouts=%s[key];"
        "[0:a][key]sidechaincompress=threshold=0.03:ratio=6:attack=5:"
        "release=300:makeup=1[o]" % (SR, CH)
    )
    run([FFMPEG, "-hide_banner", "-v", "error", "-y", "-i", music, "-i", vo,
         "-filter_complex", fc, "-map", "[o]", "-ac", "2", "-ar", str(SR), out])


def final_master(music, sfx, vo, out, lufs, tp, is_mp3):
    inputs, idx, labels = [], 0, []
    for src in (music, sfx, vo):
        if src:
            inputs += ["-i", src]
            labels.append(f"[{idx}:a]")
            idx += 1
    mixin = "".join(labels)
    fc = (f"{mixin}amix=inputs={len(labels)}:normalize=0:dropout_transition=0[mx];"
          f"[mx]loudnorm=I={lufs}:TP={tp}:LRA=11[o]")
    cmd = [FFMPEG, "-hide_banner", "-v", "error", "-y", *inputs,
           "-filter_complex", fc, "-map", "[o]"]
    if is_mp3:
        cmd += ["-c:a", "libmp3lame", "-q:a", "2"]
    else:
        cmd += ["-c:a", "pcm_s16le"]
    run(cmd + [out])


def mux(video, audio, out):
    run([FFMPEG, "-hide_banner", "-v", "error", "-y", "-i", video, "-i", audio,
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "320k", "-shortest", out])


def parse_time(s: str) -> float:
    """'90', '1:30', '1:02:03.5' -> seconds."""
    parts = str(s).strip().split(":")
    try:
        vals = [float(p) for p in parts]
    except ValueError:
        raise SystemExit(f"[assemble] bad time value: {s!r}")
    sec = 0.0
    for v in vals:
        sec = sec * 60 + v
    return sec


def parse_window(spec: str, total: float) -> tuple[float, float]:
    """'0:30-1:00' -> (30.0, 60.0), clamped to the timeline."""
    if "-" not in spec:
        raise SystemExit("[assemble] --preview needs START-END, e.g. 0:30-1:00")
    a, b = spec.split("-", 1)
    start, end = parse_time(a), parse_time(b)
    start = max(0.0, min(start, total))
    end = max(start + 0.5, min(end, total))
    return start, end


def extract_preview(src: str, dst: str, start: float, end: float, is_video: bool):
    """Cut an excerpt out of the finished master, with short fades so it
    doesn't click. The audio is the real master -- only excerpted."""
    dur = end - start
    fade = min(0.05, dur / 10)
    af = f"afade=t=in:st=0:d={fade:.3f},afade=t=out:st={dur - fade:.3f}:d={fade:.3f}"
    cmd = [FFMPEG, "-hide_banner", "-v", "error", "-y",
           "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", src, "-af", af]
    if is_video:
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "256k"]
    elif dst.lower().endswith(".mp3"):
        cmd += ["-c:a", "libmp3lame", "-q:a", "2"]
    run(cmd + [dst])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cues", required=True)
    ap.add_argument("--vo", help="mastered voiceover (sidechain key + anchor)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--assets", help="dir with files named by cue id (m1.mp3, s2.wav)")
    ap.add_argument("--stems", help="dir to also write music/sfx/vo stems")
    ap.add_argument("--mux-into", help="video to remux the final mix into (-> mp4)")
    # -10 dB is measured, not guessed: across two StickTory full mixes the bed
    # floor sits 8.2 and 12.6 dB under programme level. See SKILL.md.
    ap.add_argument("--music-db", type=float, default=-10.0,
                    help="global music trim (default -10, the measured channel bed level)")
    ap.add_argument("--sfx-db", type=float, default=0.0,
                    help="global sfx trim on top of each cue's own gain (-6..-9)")
    ap.add_argument("--no-duck", action="store_true")
    ap.add_argument("--preview", metavar="START-END",
                    help="also write a short excerpt of the finished master, "
                         "e.g. --preview 0:30-1:00 (for fast ear-checking)")
    args = ap.parse_args()

    with open(args.cues) as f:
        cue = json.load(f)
    total = cue["duration"]
    lufs = cue.get("loudness_target_lufs", -14.0)
    tp = cue.get("true_peak_ceiling_dbtp", -1.0)

    work = tempfile.mkdtemp(prefix="sd_assemble_")
    music_segs, sfx_segs = [], []
    placed_m = placed_s = missing = 0

    for m in cue.get("music_sections", []):
        asset = resolve_asset(m, args.assets)
        if not asset:
            missing += 1
            print(f"[assemble]   music {m['id']} ({fmt_ts(m['start'])}) — NO ASSET, skipped")
            continue
        seg = render_music_seg(
            asset, m["start"], m["dur"], m.get("fade_in", 1.0),
            m.get("fade_out", 1.5), m.get("gain_db", 0.0) + args.music_db,
            work, m["id"])
        music_segs.append(seg)
        placed_m += 1
        print(f"[assemble]   music {m['id']} <- {os.path.basename(asset)} "
              f"@ {fmt_ts(m['start'])} for {m['dur']}s")

    for s in cue.get("sfx_cues", []):
        asset = resolve_asset(s, args.assets)
        if not asset:
            missing += 1
            continue
        seg = render_sfx_seg(asset, s["at"], s.get("gain_db", -8.0) + args.sfx_db,
                             work, s["id"])
        sfx_segs.append(seg)
        placed_s += 1
        print(f"[assemble]   sfx {s['id']} <- {os.path.basename(asset)} @ {fmt_ts(s['at'])}")

    print(f"[assemble] placed {placed_m} music + {placed_s} sfx · {missing} cues had no asset")

    vo_wav = None
    if args.vo:
        vo_wav = os.path.join(work, "vo.wav")
        to_wav(args.vo, vo_wav)

    if not music_segs and not sfx_segs and not vo_wav:
        raise SystemExit("[assemble] nothing to render: no assets and no VO.")

    music_bus = os.path.join(work, "music_bus.wav")
    sfx_bus = os.path.join(work, "sfx_bus.wav")
    mix_bus(music_segs, music_bus, total)
    mix_bus(sfx_segs, sfx_bus, total)

    ducked = music_bus
    if vo_wav and music_segs and not args.no_duck:
        ducked = os.path.join(work, "ducked.wav")
        duck(music_bus, vo_wav, ducked)
        print("[assemble] sidechain-ducked music under VO")

    is_mp3 = args.out.lower().endswith(".mp3")
    audio_out = args.out if not args.mux_into else os.path.join(work, "final.wav")
    final_master(ducked if music_segs else None,
                 sfx_bus if sfx_segs else None,
                 vo_wav, audio_out, lufs, tp, is_mp3 and not args.mux_into)

    if args.stems:
        os.makedirs(args.stems, exist_ok=True)
        for name, src in (("music", ducked if music_segs else None),
                          ("sfx", sfx_bus if sfx_segs else None),
                          ("vo", vo_wav)):
            if src:
                dst = os.path.join(args.stems, f"{name}.wav")
                to_wav(src, dst, total)
                print(f"[assemble] stem -> {dst}")

    if args.mux_into:
        mux(args.mux_into, audio_out, args.out)
        print(f"[assemble] muxed into video -> {args.out}")

    if args.preview:
        start, end = parse_window(args.preview, total)
        stem, ext = os.path.splitext(args.out)
        prev = f"{stem} (preview {fmt_ts(start)}-{fmt_ts(end)}){ext}"
        extract_preview(args.out, prev, start, end, bool(args.mux_into))
        print(f"[assemble] preview -> {prev}")

    # loudness verification
    res = run([FFMPEG, "-hide_banner", "-i", args.out,
               "-filter:a", "ebur128=peak=true", "-f", "null", "-"])
    tail = [l for l in res.stderr.splitlines() if "I:" in l or "Peak" in l or "LRA:" in l]
    print(f"[assemble] wrote {args.out}")
    for l in tail[-6:]:
        print("   " + l.strip())


if __name__ == "__main__":
    main()
