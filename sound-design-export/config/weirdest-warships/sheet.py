#!/usr/bin/env python3
"""Build a 3x3 contact sheet of frames at given times (or evenly spaced)."""
import argparse, os, subprocess, sys

def grab(video, t, out, w=440):
    subprocess.run(["ffmpeg","-nostdin","-v","error","-ss",f"{t:.3f}","-i",video,
                    "-frames:v","1","-vf",
                    f"scale={w}:-1,drawtext=text='{t:.2f}s':x=6:y=6:fontsize=22:"
                    f"fontcolor=yellow:box=1:boxcolor=black@0.6:boxborderw=4",
                    "-y",out], check=True)

def sheet(video, times, out, w=440):
    tmp = out + ".frames"
    os.makedirs(tmp, exist_ok=True)
    fs = []
    for i, t in enumerate(times):
        f = os.path.join(tmp, f"f_{i:02d}.jpg")
        grab(video, t, f, w); fs.append(f)
    n = len(fs)
    cols = 3
    rows = (n + cols - 1)//cols
    while len(fs) < rows*cols:
        fs.append(fs[-1])
    args = []
    for f in fs: args += ["-i", f]
    fc = []
    for r in range(rows):
        fc.append("".join(f"[{r*cols+c}]" for c in range(cols)) + f"hstack={cols}[r{r}]")
    fc.append("".join(f"[r{r}]" for r in range(rows)) + f"vstack={rows}[o]")
    subprocess.run(["ffmpeg","-nostdin","-v","error", *args, "-filter_complex",
                    ";".join(fc), "-map","[o]","-q:v","4","-y", out], check=True)
    for f in set(fs): os.remove(f)
    os.rmdir(tmp)
    print(out, "->", ", ".join(f"{t:.2f}" for t in times))

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("video"); p.add_argument("-o", required=True)
    p.add_argument("--times", help="comma separated seconds")
    p.add_argument("--start", type=float); p.add_argument("--end", type=float)
    p.add_argument("-n", type=int, default=9)
    p.add_argument("-w", type=int, default=440)
    a = p.parse_args()
    if a.times:
        ts = [float(x) for x in a.times.split(",")]
    else:
        step = (a.end - a.start)/a.n
        ts = [a.start + step*(i+0.5) for i in range(a.n)]
    sheet(a.video, ts, a.o, a.w)
