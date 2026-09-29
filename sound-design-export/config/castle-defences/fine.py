import json, os, subprocess, math, sys
WINDOWS = [("A",42.0,50.0),("B",52.0,64.0),("C",186.0,200.0),("D",400.0,422.0),
           ("E",455.0,467.0),("F",572.0,600.0),("G",144.0,156.0),("H",700.0,712.0)]
W,COLS,ROWS = 420,4,4
for name,a,b in WINDOWS:
    per=COLS*ROWS; step=(b-a)/per
    ts=[a+step*(i+0.5) for i in range(per)]
    tmp=f"/tmp/fn{name}"; os.makedirs(tmp,exist_ok=True); fs=[]
    for i,t in enumerate(ts):
        f=f"{tmp}/f{i:02d}.jpg"
        subprocess.run(["ffmpeg","-nostdin","-v","error","-ss",f"{t:.3f}","-i","video.mp4",
          "-frames:v","1","-vf",f"scale={W}:-1,drawtext=text='{t:.2f}':x=6:y=6:fontsize=24:"
          f"fontcolor=yellow:box=1:boxcolor=black@0.75:boxborderw=4","-y",f],check=True)
        fs.append(f)
    args=[]
    for f in fs: args+=["-i",f]
    fc=[]
    for r in range(ROWS): fc.append("".join(f"[{r*COLS+c}]" for c in range(COLS))+f"hstack={COLS}[r{r}]")
    fc.append("".join(f"[r{r}]" for r in range(ROWS))+f"vstack={ROWS}[o]")
    out=f"sheets/fine_{name}.jpg"
    subprocess.run(["ffmpeg","-nostdin","-v","error",*args,"-filter_complex",";".join(fc),
                    "-map","[o]","-q:v","4","-y",out],check=True)
    print(out, f"{a}-{b}s step {step:.2f}s")
