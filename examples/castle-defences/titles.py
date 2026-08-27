#!/usr/bin/env python3
"""Resolve every palette file's real Epidemic title by replaying the searches
that chose it. My internal filenames are slots in a rotation, not descriptions:
`portc_07` says nothing, and quoting it attributes a sound to a recording that
may be nothing of the kind."""
import json, sys, time
sys.path.insert(0, "/home/user/Test-2/.claude/skills/sound-designer/scripts")
from epidemic_api import Client, api_key, flatten
TERMS = [
 ("crossbow bolt shot release whoosh",120,3000),("arrow impact hit wood thud stick",120,3000),
 ("arrow whoosh by fast air past",120,2500),("bow string draw creak tension",200,4000),
 ("crossbow mechanism crank load lever",200,5000),
 ("boiling water cauldron bubbling pot",500,8000),("pouring liquid heavy splash bucket",300,5000),
 ("sand gravel pour dry falling",300,5000),("hot metal sizzle steam hiss burn",300,6000),
 ("heavy iron gate grill drop slam metal",300,6000),("heavy chain rattle drag metal links",300,6000),
 ("winch ratchet crank wooden mechanism",300,6000),("large wooden door heavy open close castle",300,8000),
 ("heavy wooden door creak slow",500,8000),("wood timber break crack splinter",200,5000),
 ("battering ram heavy wooden impact gate",200,5000),("boulder stone impact wall heavy thud",200,5000),
 ("rubble collapse debris stone wall crumble",500,8000),("shovel dig earth dirt soil",200,5000),
 ("pickaxe hit stone rock mining",150,4000),("catapult trebuchet wooden release launch",200,6000),
 ("weapons siege engine launch fire",200,6000),("siege battering ram impacts break barrier",200,6000),
 ("heavy object splash into lake water deep",500,6000),("lake water lapping shore calm",3000,20000),
 ("water flowing rushing filling stream",3000,15000),("fire crackle burning wood torch flames",2000,15000),
 ("fire whoosh flame burst ignite",200,4000),("wind gust exterior cold howling",4000,20000),
 ("metal bolt latch lock heavy iron",150,4000),("parchment paper scroll unroll handle",200,5000),
 ("writing quill pen paper scratch",200,5000),("pig grunt oink squeal farm animal",200,5000),
 ("medieval crowd cheer jeer shout men",1000,12000),("medieval village ambience market crowd",5000,20000),
 ("footsteps stone gravel armour boots walk",200,6000),("rope pulley creak tension haul",300,6000),
 ("thunder lightning strike crack rumble",500,9000),("stone slab heavy grind scrape drag",300,6000),
 ("heavy metal object drop fast slam ground",200,4000),
 ("cloth fabric swish movement quick",100,1500),("air swish short whip fast",100,1500),
 ("leather armour movement rustle quick",100,1500),
]
c = Client(api_key()); c.initialize()
byid = {}
for term, lo, hi in TERMS:
    for a in range(3):
        try:
            p = c.call("SearchSoundEffects", {"query": {"term": term}, "first": 14,
                       "filter": {"duration": {"min": lo, "max": hi}}})
            break
        except SystemExit as e:
            print("  !", term, e); p = None; time.sleep(2**a)
    if not p: continue
    for r in flatten(p, "sfx"):
        byid.setdefault(r["id"], r["title"])
names = {}
for fn in ("castle_ids.txt", "swish_ids.txt"):
    for line in open(fn):
        if line.strip():
            n, sid = line.split()
            if sid in byid: names[n] = byid[sid]
json.dump(names, open("sfx_titles.json","w"), indent=1)
missing = sum(1 for line in open("castle_ids.txt") if line.strip()) + 14 - len(names)
print(f"{len(names)} titles resolved, {missing} unresolved")
