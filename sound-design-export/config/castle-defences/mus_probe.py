#!/usr/bin/env python3
"""Search music by term, capture id+title+lqmp3 for every candidate."""
import json, os, sys
sys.path.insert(0, "/home/user/Test-2/.claude/skills/sound-designer/scripts")
from epidemic_api import Client, api_key, flatten

TERMS = [
 "dark cinematic tension building strings percussion medieval",
 "medieval battle drums war marching relentless",
 "driving cinematic percussion taiko action tension",
 "playful sneaky mischief pizzicato comedic tension",
 "somber slow strings mournful cinematic",
 "suspense pulse ostinato strings ticking urgent",
 "epic grand orchestral cinematic powerful",
 "heroic triumphant orchestral brass rising",
 "medieval fantasy castle adventure orchestral rhythmic",
 "tense investigative documentary underscore pulse",
]
c = Client(api_key()); c.initialize()
seen = {}
for t in TERMS:
    p = c.call("SearchRecordings", {"query": {"term": t}, "first": 14,
                                    "filter": {"vocals": False,
                                               "duration": {"min": 90000}}})
    for r in flatten(p, "music"):
        if r["id"] and r["id"] not in seen:
            r["term"] = t
            seen[r["id"]] = r
json.dump(list(seen.values()), open("mus_candidates.json", "w"), indent=1)
nv = sum(1 for r in seen.values() if r["vocals"])
print(f"{len(seen)} candidates, {nv} carry a vocal tag")
