import json, subprocess, os, sys
d = json.load(open("redraw.json"))
cuts = sorted(e["t"] for e in d["events"] if e["kind"] == "cut")
dur = d["duration"]
ts, bounds = [], cuts + [dur]
for i, c in enumerate(bounds[:-1]):
    ts.append(c + 0.45)
    gap = bounds[i+1] - c
    if gap > 9.0:                       # long shot: sample inside it too
        n = int(gap // 7.0)
        ts += [c + gap*(k+1)/(n+1) for k in range(n)]
ts = [t for t in sorted(ts) if t < dur - 0.3]
json.dump([round(t,3) for t in ts], open("shot_times.json","w"))
print(len(ts), "sample times;", (len(ts)+8)//9, "sheets of 9")
