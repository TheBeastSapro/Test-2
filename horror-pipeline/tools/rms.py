#!/usr/bin/env python3
"""RMS per 0.5s -> work/rms.json  (Stage 2, BUILD-PACKET section 4.3)

This is the ARBITER for "is this a real VO gap or a Whisper drop?".

Whisper silently drops words. A dropped stretch looks exactly like a gap in
the voiceover, and "the narrator never recorded the mid-roll CTA" is a
serious conclusion to get wrong. So before acting on any suspected gap,
measure the actual energy in the voiceover over that window:

  flat and normal RMS through the gap -> the VO is there, the transcript
                                          dropped it
  RMS genuinely floors out            -> the gap is real, it is a pickup

Measure the DRY voiceover. On a mixed track the music holds the RMS up
through a real gap and the arbiter tells you a comfortable lie.

Every ffmpeg call carries -nostdin -v error. Without them ffmpeg floods the
session with hundreds of `frame= 1042 fps=31` lines and burns the context.

Usage:
  rms.py /abs/vo.wav /abs/work/rms.json
  rms.py /abs/vo.wav /abs/work/rms.json --floor -45 --hop 0.25

Exit codes: 0 ok, 1 usage or ffmpeg error, 3 file decoded to no audio.
"""
import json
import os
import subprocess
import sys

import numpy as np

SR = 48000


def abs_arg(p, what):
    if not os.path.isabs(p):
        sys.exit(f"ERROR: {what} must be an absolute path (got {p!r}). "
                 "The shell working directory is not stable between calls.")
    return p


def runs_of(indices, hop):
    """Collapse window indices into contiguous [start, end] second ranges."""
    out = []
    for i in indices:
        if out and i == out[-1][1] + 1:
            out[-1][1] = i
        else:
            out.append([i, i])
    return [(round(a * hop, 2), round((b + 1) * hop, 2)) for a, b in out]


def measure(src, hop_s):
    r = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", src,
         "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
        capture_output=True)
    if r.returncode != 0:
        sys.exit(f"ERROR: ffmpeg decode failed: {r.stderr.decode()[:400]}")
    x = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    hop = int(SR * hop_s)
    n = len(x) // hop
    if n == 0:
        sys.exit(f"ERROR: {src} decoded to under {hop_s}s of audio")
    env = np.sqrt(np.maximum((x[:n * hop].reshape(n, hop) ** 2).mean(1), 1e-12))
    return 20 * np.log10(env), len(x) / SR


def main():
    argv, pos, floor, hop_s = sys.argv[1:], [], -50.0, 0.5
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            key, _, inline = a.partition("=")
            val = inline if inline else (argv[i + 1] if i + 1 < len(argv) else None)
            if not inline:
                i += 1
            if val is None:
                sys.exit(f"ERROR: {key} needs a value")
            if key == "--floor":
                floor = float(val)
            elif key == "--hop":
                hop_s = float(val)
            else:
                sys.exit(f"ERROR: unknown flag {key}")
        else:
            pos.append(a)
        i += 1
    if len(pos) != 2:
        sys.exit(__doc__)
    src = abs_arg(pos[0], "audio")
    out = abs_arg(pos[1], "rms.json")
    if not os.path.isfile(src):
        sys.exit(f"ERROR: no such audio file: {src}")

    db, dur = measure(src, hop_s)
    n = len(db)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    # Format is the packet's: a flat list of {"t","db"}. The hop is recoverable
    # from consecutive t values, so no header is needed and nothing downstream
    # has to learn a second schema.
    json.dump([{"t": round(i * hop_s, 2), "db": round(float(v), 2)}
               for i, v in enumerate(db)],
              open(out, "w", encoding="utf-8"))

    quiet_idx = [i for i, v in enumerate(db) if v < floor]
    quiet_runs = runs_of(quiet_idx, hop_s)
    long_runs = [(a, b) for a, b in quiet_runs if b - a >= 1.0]

    print("SUMMARY rms")
    print(f"  audio   : {src}")
    print(f"  windows : {n} at {hop_s}s hop ({dur:.1f}s of audio)")
    print(f"  level   : median {np.median(db):.1f} dBFS, "
          f"loudest window {db.max():.1f}, quietest {db.min():.1f}")
    print(f"  below {floor:g} dBFS: {len(quiet_idx)} window(s) in {len(quiet_runs)} run(s)")
    shown = quiet_runs[:40]
    if shown:
        print("            " + ", ".join(f"{a}-{b}s" for a, b in shown)
              + (f" ... +{len(quiet_runs) - len(shown)} more" if len(quiet_runs) > len(shown) else ""))
    if long_runs:
        print(f"  runs >= 1.0s: {len(long_runs)} -> "
              + ", ".join(f"{a}-{b}s" for a, b in long_runs[:12]))
        print("            these are the windows align_sections.py will call a real gap")
    print(f"  wrote   : {out}")

    if len(quiet_idx) == n:
        print("  WARNING : the whole file is below the floor, this is silence, "
              "not a voiceover", file=sys.stderr)


if __name__ == "__main__":
    main()
