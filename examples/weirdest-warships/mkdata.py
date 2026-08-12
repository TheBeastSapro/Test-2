#!/usr/bin/env python3
import json, os, collections
c = json.load(open("cues.json"))
TIERS = ["hero_boom","hero_hit","impact","whoosh","swish","pop"]
LAYER = {None:0, "anticipation":1, "weight":2}
GENERIC = {"shot change","strike","movement","small element","caption / small element"}
kinds, kidx, files, fidx = [], {}, [], {}
def K(s):
    if s not in kidx: kidx[s]=len(kinds); kinds.append(s)
    return kidx[s]
def F(s):
    if s not in fidx: fidx[s]=len(files); files.append(s)
    return fidx[s]
sfx=[]
for s in c["sfx_cues"]:
    lay = LAYER.get(s.get("layer"),0)
    base = s["kind"].replace(" (anticipation)","").replace(" (weight)","")
    sfx.append([round(s["at"],3), TIERS.index(s["tier"]), round(s["gain_db"],1),
                K(base), F(os.path.basename(s["asset"])[:-4]), lay,
                0 if base in GENERIC else 1])
NAME={"amb_01":"Sea Water, Very Gentle Waves","amb_02":"Ocean, Medium Waves, Wind",
 "amb_04":"Harbor, Docks, Boats Lapping, Squeaky Ropes","amb_05":"Underwater, Deep 01",
 "amb_06":"Sailboat, Creaks, Cabin Tone","amb_07":"Rattling Submarine, Deep, Creaks",
 "amb_09":"Sea, Light Wind, Waves Intensifies","amb_10":"Harbor, Marina Night",
 "amb_11":"Underwater, Deep, Low","amb_12":"Sailboat, Wood, Cabin, Sailing, Hull"}
beds=[[round(b["at"],3), round(b["dur"],3), NAME.get(os.path.basename(b["asset"])[:-4],"?"),
       round(b["gain_db"],1), b["why"]] for b in c["amb_beds"]]
music=[[m["id"], round(m["start"],3), round(m["end"],3), m.get("track","?"),
        m["energy_label"], m["energy"]] for m in c["music_sections"]]
CARDS=[0.400,81.167,167.667,290.633,386.133,494.667,615.600]
NAMES=["The Ancient World","The Middle Ages","The Early Modern Age","The Age of Sail",
       "The Ironclad Age","World War I","World War II"]
SHIPS=["Syracusia · 240 BC","Song paddle-wheel warships · 1134","Geobukseon 1592 · Vasa 1628",
       "Bushnell's Turtle · 1776","Novgorod · 1873","K-class submarine · 1918","Surcouf · 1929"]
ends=CARDS[1:]+[718.171]
eras=[[NAMES[i],SHIPS[i],CARDS[i],ends[i]] for i in range(7)]
pal=json.load(open("pal/palette_manifest.json"))
cats=sorted(((k,len(v)) for k,v in pal.items() if not k.startswith("_")), key=lambda x:-x[1])
top=collections.Counter(os.path.basename(s["asset"])[:-4] for s in c["sfx_cues"]).most_common(8)
FIRE=[123.733,368.467,563.667,573.900,579.433,581.233,582.633,584.167,586.033,
      587.800,589.367,590.833,652.800]
data={"duration":718.171,"tiers":TIERS,"kinds":kinds,"files":files,"sfx":sfx,
      "beds":beds,"music":music,"eras":eras,"mutes":c["mute_windows"],
      "cats":cats,"top":top,"fire":FIRE}
open("preview_data.json","w").write(json.dumps(data,separators=(",",":")))
prim=[s for s in sfx if s[5]==0]
print("bytes",os.path.getsize("preview_data.json"),"| sfx",len(sfx),"prim",len(prim),
      "| hand",sum(1 for s in sfx if s[6]),"| music",len(music))
