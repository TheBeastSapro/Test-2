#!/usr/bin/env python3
import json, collections, os
c = json.load(open("cues.json"))
mus = json.load(open("music_ids.json"))
L = []
A = L.append
A("# The Weirdest Warships from Every Era Explained — sound design cue sheet\n")
A(f"Runtime 11:58.17 · {len(c['music_sections'])} music sections · "
  f"{len([s for s in c['sfx_cues'] if not s.get('layer')])} SFX events "
  f"({len(c['sfx_cues'])} cues with layers) · {len(c['amb_beds'])} ambience beds\n")
A("## Music\n")
A("| # | in | out | length | track | what it is under |")
A("|---|---|---|---|---|---|")
def ts(t): return f"{int(t)//60}:{t%60:06.3f}"
for m in c["music_sections"]:
    A(f"| {m['id']} | {ts(m['start'])} | {ts(m['end'])} | {m['dur']:.1f}s | "
      f"*{m.get('track','?')}* | {m['energy_label']} |")
A("\n## Ambience beds\n")
A("Hand-assigned, one per scene rather than rotated — a bed never ducks, so a wrong one "
  "runs under the narration for a minute at a time.\n")
A("| in | length | source | level | why |")
A("|---|---|---|---|---|")
NAME = {"amb_01":"Sea Water, Very Gentle Waves","amb_02":"Ocean, Medium Waves, Wind",
        "amb_04":"Harbor, Docks, Boats Lapping, Squeaky Ropes","amb_05":"Underwater, Deep 01",
        "amb_06":"Sailboat, Creaks, Cabin Tone","amb_07":"Rattling Submarine, Deep, Creaks",
        "amb_09":"Sea, Light Wind, Waves Intensifies","amb_10":"Harbor, Marina Night",
        "amb_11":"Underwater, Deep, Low","amb_12":"Sailboat, Wood, Cabin, Sailing, Hull"}
for b in c["amb_beds"]:
    k = os.path.basename(b["asset"])[:-4]
    A(f"| {ts(b['at'])} | {b['dur']:.0f}s | {NAME.get(k,k)} | {b['gain_db']:+.1f} dB | {b['why']} |")
A("\n## Hand-timed beats\n")
A("Every one read off a contact sheet, then landed on the nearest picture change.\n")
A("| at | tier | beat | cast |")
A("|---|---|---|---|")
for s in c["sfx_cues"]:
    if s.get("layer") or s["kind"] in ("shot change","strike","movement","small element",
                                       "caption / small element"): continue
    if "(anticipation)" in s["kind"] or "(weight)" in s["kind"]: continue
    A(f"| {ts(s['at'])} | {s['tier']} | {s['kind']} | `{os.path.basename(s['asset'])[:-4]}` "
      f"@ {s['gain_db']:+.0f} dB |")
A("\n## Mute windows\n")
A("The redraw detector cannot tell a portrait sliding in from a hull being struck. "
  "These spans drop generic cues only.\n")
for w in c["mute_windows"]:
    A(f"- **{ts(w[0])}–{ts(w[1])}** — {w[2]}")
A("\n## Density\n")
cnt = collections.Counter(os.path.basename(s["asset"]) for s in c["sfx_cues"])
A(f"{len(cnt)} distinct files. Busiest: " +
  ", ".join(f"`{f[:-4]}` ×{n}" for f, n in cnt.most_common(6)) + ".\n")
tiers = collections.Counter(s["tier"] for s in c["sfx_cues"])
A("| tier | count |")
A("|---|---|")
for t in ("hero_boom","hero_hit","impact","whoosh","swish","pop"):
    A(f"| {t} | {tiers.get(t,0)} |")
open("cue_sheet.md","w").write("\n".join(L))
print(f"wrote cue_sheet.md ({len(L)} lines)")
