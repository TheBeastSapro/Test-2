import json, os, subprocess, sys, math
ts = json.load(open("shot_times.json"))
os.makedirs("sheets", exist_ok=True)
W, COLS, ROWS = 420, 4, 4
per = COLS*ROWS
n = math.ceil(len(ts)/per)
for s in range(n):
    chunk = ts[s*per:(s+1)*per]
    tmp = f"/tmp/sh{s}"; os.makedirs(tmp, exist_ok=True)
    fs = []
    for i, t in enumerate(chunk):
        f = f"{tmp}/f{i:02d}.jpg"
        subprocess.run(["ffmpeg","-nostdin","-v","error","-ss",f"{t:.3f}","-i","video.mp4",
            "-frames:v","1","-vf",
            f"scale={W}:-1,drawtext=text='{t:.2f}':x=6:y=6:fontsize=24:fontcolor=yellow:"
            f"box=1:boxcolor=black@0.75:boxborderw=4",
            "-y",f], check=True)
        fs.append(f)
    while len(fs) < per: fs.append(fs[-1])
    args=[]; 
    for f in fs: args += ["-i", f]
    fc=[]
    for r in range(ROWS):
        fc.append("".join(f"[{r*COLS+c}]" for c in range(COLS)) + f"hstack={COLS}[r{r}]")
    fc.append("".join(f"[r{r}]" for r in range(ROWS)) + f"vstack={ROWS}[o]")
    out=f"sheets/s{s:02d}.jpg"
    subprocess.run(["ffmpeg","-nostdin","-v","error",*args,"-filter_complex",";".join(fc),
                    "-map","[o]","-q:v","4","-y",out], check=True)
    print(out, f"{chunk[0]:.1f}-{chunk[-1]:.1f}s")
