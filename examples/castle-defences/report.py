#!/usr/bin/env python3
import json, collections, os
c = json.load(open("cues.json"))
T = json.load(open("sfx_titles.json"))
def name(n): return T.get(n, n)
def ts(t): return f"{int(t)//60}:{t%60:06.3f}"
L=[]; A=L.append
ev = [s for s in c["sfx_cues"] if not s.get("layer")]
A("# Castle Defences — sound design cue sheet\n")
A(f"Runtime 12:19.17 · {len(c['music_sections'])} music sections · {len(ev)} SFX events "
  f"({len(c['sfx_cues'])} cues with layers) · {len(c['amb_beds'])} ambience beds\n")
A("## Music\n")
A("Cast by measurement, not by title: `mus_measure.py` scores onset density, pulse "
  "regularity and percussive fraction over 45 s of each candidate, because *floaty is a "
  "casting error, not a level problem*. Two medieval-sounding tracks — *Arrival at "
  "Caelmere Keep* and *The King's Return* — are ambient wash by that measure and were "
  "rejected on it.\n")
A("| # | in | out | length | track | bpm | under |")
A("|---|---|---|---|---|---|---|")
bpm = {p["title"]: p["bpm"] for p in json.load(open("music_pick.json"))}
for m in c["music_sections"]:
    A(f"| {m['id']} | {ts(m['start'])} | {ts(m['end'])} | {m['dur']:.1f}s | *{m['track']}* | "
      f"{bpm.get(m['track'],0):.0f} | {m['energy_label']} |")
A("\n## Ambience beds\n")
A("Hand-assigned, never rotated: a bed does not duck, so a wrong one runs under the "
  "narration for a minute at a time. Cold air appears only where the picture is cold.\n")
A("| in | length | source | level | why |")
A("|---|---|---|---|---|")
for b in c["amb_beds"]:
    k = os.path.basename(b["asset"])[:-4]
    A(f"| {ts(b['at'])} | {b['dur']:.0f}s | {name(k)} | {b['rms_target_dbfs']} dBFS | {b['why']} |")
A("\n## Hand-timed beats\n")
A("Every time read off a contact sheet at the detected scene cuts, or off a 0.5–1.8 s "
  "sheet over one of eight action windows, then landed on the nearest picture change.\n")
A("| at | tier | beat | cast |")
A("|---|---|---|---|")
for s in ev:
    if not s.get("solo_ok"): continue
    A(f"| {ts(s['at'])} | `{s['tier']}` | {s['kind']} | {name(os.path.basename(s['asset'])[:-4])} "
      f"@ {s['gain_db']:+.0f} dB |")
A("\n## Mute windows\n")
A("A photograph is not an event, and neither is a map. The redraw detector cannot tell a "
  "portrait sliding in from a tower being struck — both are large mid-band redraws — so "
  "there is no quieter sound that is right. These spans drop generic cues only; a "
  "hand-timed beat inside one still sounds.\n")
for w in c["mute_windows"]: A(f"- **{ts(w[0])}–{ts(w[1])}** — {w[2]}")
A("\n## Density\n")
cnt = collections.Counter(os.path.basename(s["asset"]) for s in c["sfx_cues"])
A(f"{len(cnt)} distinct files, busiest ×{cnt.most_common(1)[0][1]}, "
  f"{len(ev)} events over 739 s = one per {739/len(ev):.2f} s.\n")
tiers = collections.Counter(s["tier"] for s in c["sfx_cues"])
A("| tier | count |"); A("|---|---|")
for t in ("hero_boom","hero_hit","impact","whoosh","swish","pop"): A(f"| `{t}` | {tiers.get(t,0)} |")
open("cue_sheet.md","w").write("\n".join(L))
print(f"wrote cue_sheet.md ({len(L)} lines)")
