#!/usr/bin/env python3
"""verify.py — assert the invariants that matter, on the fixture render.

Usage:  python3 test/verify.py <fixture dir>

Checks the things that are supposed to be true of EVERY mix, not fixture
trivia, so the same script is a sanity check on a real job:

  1. the voice comes out at the level it went in  (the master is anchored to
     the voice, so any drift here means a programme target crept back in)
  2. true peak is at or under the -1.0 dBTP ceiling
  3. the muxed video stream was COPIED, not re-encoded
  4. all three stems exist and run the full length
  5. the music bed sits below the voice under speech
"""
import json, os, re, subprocess, sys

F = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "fixture")
FAILED = []


def ff(args):
    return subprocess.run(["ffmpeg", "-hide_banner", *args],
                          capture_output=True, text=True).stderr


def lufs(path):
    out = ff(["-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"])
    i = re.findall(r"I:\s+(-?\d+\.?\d*)\s+LUFS", out)
    p = re.findall(r"Peak:\s+(-?\d+\.?\d*)\s+dBFS", out)
    return (float(i[-1]) if i else None), (float(p[-1]) if p else None)


def probe(path, stream, fields):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", stream,
                        "-show_entries", f"stream={fields}",
                        "-of", "default=noprint_wrappers=1:nokey=1", path],
                       capture_output=True, text=True)
    return r.stdout.split()


def check(name, ok, detail):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    if not ok:
        FAILED.append(name)


print(f"verifying {F}\n")

# 1. the voice is unchanged ------------------------------------------------
vo_in, _ = lufs(f"{F}/vo.wav")
vo_out, _ = lufs(f"{F}/stems/vo.wav")
check("voice unchanged", abs(vo_in - vo_out) <= 0.2,
      f"{vo_in:+.1f} LUFS in -> {vo_out:+.1f} LUFS out (tolerance 0.2)")

# 2. true peak under the ceiling -------------------------------------------
mix = f"{F}/fixture (mixed).mp4"
prog, peak = lufs(mix)
check("true peak <= -1.0 dBTP", peak is not None and peak <= -1.0 + 0.05,
      f"{peak:+.1f} dBFS")
print(f"         (programme loudness {prog:+.1f} LUFS -- an output, not a target)")

# 3. the video was copied, not re-encoded ----------------------------------
src = probe(f"{F}/video.mp4", "v:0", "codec_name,width,height,nb_frames")
out = probe(mix, "v:0", "codec_name,width,height,nb_frames")
check("video stream copied", src == out, f"{src} -> {out}")
acodec = probe(mix, "a:0", "codec_name,sample_rate,channels")
check("muxed audio is aac 48k stereo", acodec[:3] == ["aac", "48000", "2"],
      " ".join(acodec))

# 4. stems ------------------------------------------------------------------
for s in ("music", "sfx", "vo"):
    p = f"{F}/stems/{s}.wav"
    d = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", p],
                       capture_output=True, text=True).stdout.strip()
    check(f"stem {s}", os.path.exists(p) and abs(float(d) - 20.0) < 0.2,
          f"{float(d):.2f} s")

# 5. the bed sits under the voice ------------------------------------------
try:
    import numpy as np, soundfile as sf

    def env(p, hop=0.05):
        x, sr = sf.read(p, always_2d=True)
        x = x.mean(axis=1)
        n = int(hop * sr)
        k = len(x) // n
        return 20 * np.log10(np.sqrt((x[:k * n].reshape(k, n) ** 2).mean(axis=1)) + 1e-9)

    m, v = env(f"{F}/stems/music.wav"), env(f"{F}/stems/vo.wav")
    k = min(len(m), len(v))
    sp = v[:k] > -45
    under = float(np.median(m[:k][sp]) - np.median(v[:k][sp]))
    check("bed under speech", under < -6.0, f"{under:.1f} dB")
except ImportError:
    print("  [SKIP] bed under speech: numpy/soundfile not installed")

print()
if FAILED:
    print(f"FAILED: {', '.join(FAILED)}")
    sys.exit(1)
print("all checks passed")
