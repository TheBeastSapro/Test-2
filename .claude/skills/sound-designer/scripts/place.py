#!/usr/bin/env python3
"""place.py — turn visual events into a cue sheet that is dense but not tiring.

This exists because the first full pass on a real 13-minute video failed in
three ways that are all countable, and none of which are about taste:

  1. 474 cues were served by SEVEN files -- one tick played 240 times. The ear
     learns a sample inside a minute and then hears the seam, not the picture.
  2. sync_check found 723 onsets for those 474 cues and could not match 148 of
     them: at one hit per 1.5 s the tails overlap, so hits mask each other and
     the overlaps themselves read as new attacks.
  3. Every cue sat at -15..-22 dB, i.e. under the -13 dB music bed, so whole
     minutes read as having no SFX at all.

So this script ranks events, keeps the ones that carry meaning, guards them
from each other in time, places them above the bed, and rotates a real palette
so no object comes back too soon. Quiet stretches get an ambience bed rather
than more hits.

Inputs:
  --events   visual_events.py output (cuts + in-shot action, with strength)
  --cues     a cue sheet with music_sections, and optionally hand-timed
             sfx_cues; anything whose "kind" is not one of the generic labels
             is treated as a designed beat and is never dropped
  --palette  a directory prepared by palette.py

Usage:
  place.py --cues cues.json --events events.json --palette pal --out cues.json
"""
from __future__ import annotations

import argparse
import json
import os
import random

# Levels are relative to the voice. The music bed sits at about -13 dB, so
# anything quieter than that is inaudible under narration -- which was the bug.
#   tier         gain   guard = how much room the hit gets before a lesser cue
TIERS = {
    "hero_boom":  (-5.0, 2.20),
    "hero_hit":   (-7.0, 1.30),
    "impact":     (-8.0, 1.10),
    "whoosh":    (-12.0, 1.00),
    "swish":     (-15.0, 0.85),
    "pop":       (-19.0, 0.80),
}
PRIORITY = ["hero_boom", "hero_hit", "impact", "whoosh", "swish", "pop"]
TIER_CAT = {"hero_boom": "boom", "hero_hit": "impact", "impact": "impact",
            "whoosh": "whoosh", "swish": "swish", "pop": "pop"}
VARY = {"pop": 0.35, "swish": 0.3, "whoosh": 0.2, "impact": 0.15}

# what a hand-written beat's search word means in palette terms
HERO_CAT = {"boom": "boom", "clash": "impact", "hit": "impact", "impact": "impact",
            "shatter": "impact", "ring": "draw", "draw": "draw", "forge": "forge",
            "whoosh": "whoosh", "swoosh": "whoosh", "armor": "armor"}

GENERIC = {"caption / small element", "shot change", "strong on-screen action",
           "element moves in"}


class Rotator:
    """Hand out palette files so the same object never comes back too soon."""

    def __init__(self, files, rng, cooldown=30.0):
        self.files = list(files)
        self.cooldown = cooldown
        self.last = {f: -1e9 for f in self.files}
        self.order = list(self.files)
        rng.shuffle(self.order)
        self.i = 0

    def take(self, t: float) -> str:
        for _ in range(len(self.order)):
            f = self.order[self.i % len(self.order)]
            self.i += 1
            if t - self.last[f] >= self.cooldown:
                self.last[f] = t
                return f
        f = min(self.files, key=lambda x: self.last[x])   # all cooling: oldest
        self.last[f] = t
        return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cues", required=True)
    ap.add_argument("--events", required=True)
    ap.add_argument("--palette", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--drop-weakest", type=float, default=0.35,
                    help="fraction of in-shot action events to discard as "
                         "camera drift rather than things that happen")
    ap.add_argument("--no-beds", action="store_true")
    ap.add_argument("--no-anticipation", action="store_true")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    cue = json.load(open(args.cues))
    ev = json.load(open(args.events))
    pal = json.load(open(os.path.join(args.palette, "palette_manifest.json")))
    apath = os.path.abspath(args.palette)

    missing = [c for c in set(TIER_CAT.values()) | {"swish"} if c not in pal]
    if missing:
        raise SystemExit(f"[place] palette is missing categories: {missing}")

    rot = {c: Rotator(v, rng, cooldown=90.0 if c == "boom" else 30.0)
           for c, v in pal.items() if c != "amb"}

    cand = []                                    # (tier, t, category, label)

    # 1. hand-timed beats: the designed moments, never dropped
    for s in cue.get("sfx_cues", []):
        if s.get("kind") in GENERIC:
            continue
        word = (s.get("epidemic") or {}).get("search", "clash")
        cat = HERO_CAT.get(word, "impact")
        cand.append(("hero_boom" if cat == "boom" else "hero_hit",
                     s["at"], cat, s["kind"]))
    heroes = len(cand)

    # 2. shot changes get air
    for e in ev["events"]:
        if e["kind"] == "cut":
            cand.append(("whoosh", e["t"], "whoosh", "shot change"))

    # 3. in-shot action, ranked; the weakest slice is camera drift, not action
    acts = sorted((e for e in ev["events"] if e["kind"] == "action"),
                  key=lambda e: e["strength"])
    if acts:
        n = len(acts)
        lo = acts[int(n * args.drop_weakest)]["strength"]
        mid = acts[int(n * (args.drop_weakest + (1 - args.drop_weakest) * .46))]["strength"]
        hi = acts[int(n * .88)]["strength"]
        for e in acts:
            s = e["strength"]
            if s < lo:
                continue
            tier = "impact" if s >= hi else ("swish" if s >= mid else "pop")
            cand.append((tier, e["t"], TIER_CAT[tier],
                         {"impact": "strike", "swish": "movement",
                          "pop": "small element"}[tier]))

    # 4. resolve collisions by PRIORITY, not by strength -- a caption tick must
    # never elbow a sword strike. Hand-timed beats are exempt from the guard
    # against each other: an era card is deliberately a whoosh leading into a
    # boom 0.4 s later, and a 2.2 s guard would delete the whoosh.
    kept, lost = [], 0
    for tier in PRIORITY:
        guard, hero = TIERS[tier][1], tier.startswith("hero")
        for c in sorted((c for c in cand if c[0] == tier), key=lambda c: c[1]):
            rivals = [k for k in kept if not (hero and k[0].startswith("hero"))]
            if any(abs(c[1] - k[1]) < max(guard, TIERS[k[0]][1]) for k in rivals):
                lost += 1
                continue
            kept.append(c)
    kept.sort(key=lambda c: c[1])

    # 5. assign files
    sfx, counts = [], {}
    for i, (tier, t, cat, label) in enumerate(kept, 1):
        f = rot[cat].take(t)
        counts[f] = counts.get(f, 0) + 1
        gain = TIERS[tier][0]
        sfx.append({"id": f"s{i}", "at": round(t, 4), "kind": label,
                    "tier": tier, "cat": cat, "gain_db": gain,
                    "vary": VARY.get(cat, 0.0),
                    "asset": os.path.join(apath, f"{f}.wav")})
        # A strike gets a short swish just before contact. One sound is a
        # sample; two is a designed hit.
        if not args.no_anticipation and tier in ("impact", "hero_hit") and t > 0.4:
            g = rot["swish"].take(t)
            sfx.append({"id": f"s{i}a", "at": round(t - 0.13, 4),
                        "kind": f"{label} (anticipation)", "tier": "swish",
                        "cat": "swish", "gain_db": gain - 7.0, "vary": 0.3,
                        "asset": os.path.join(apath, f"{g}.wav")})
    sfx.sort(key=lambda s: s["at"])

    # 6. beds. "This area has no SFX" is answered by room tone, not more hits.
    beds = []
    if not args.no_beds and pal.get("amb"):
        war = [a for a in pal["amb"] if a.endswith(("_05", "_06", "_07"))]
        calm = [a for a in pal["amb"] if a not in war] or pal["amb"]
        war = war or pal["amb"]
        for k, m in enumerate(cue.get("music_sections", [])):
            hot = m.get("energy", 0.5) >= 0.62
            pool = war if hot else calm
            beds.append({"id": f"b{k+1}", "at": round(m["start"], 3),
                         "dur": round(m["dur"], 3),
                         "gain_db": -30.0 if hot else -28.0, "fade": 2.5,
                         "era": m.get("era", ""),
                         "asset": os.path.join(apath, f"{pool[k % len(pool)]}.wav")})

    cue["sfx_cues"] = sfx
    cue["amb_beds"] = beds
    with open(args.out, "w") as f:
        json.dump(cue, f, indent=1)

    dur = cue.get("duration") or (sfx[-1]["at"] if sfx else 1.0)
    gaps = [b["at"] - a["at"] for a, b in zip(sfx, sfx[1:])] or [0.0]
    busiest = sorted(counts.items(), key=lambda x: -x[1])[:3]
    print(f"[place] {len(cand)} candidates ({heroes} hand-timed) -> {len(kept)} kept, "
          f"{lost} lost a collision, {len(sfx)-len(kept)} anticipation layers")
    print(f"[place] {len(sfx)} cues over {dur:.0f}s = one per {dur/max(1,len(sfx)):.2f}s")
    print(f"[place] {len(counts)} distinct files; busiest: "
          + ", ".join(f"{f} x{n}" for f, n in busiest))
    print(f"[place] median gap {sorted(gaps)[len(gaps)//2]:.2f}s, {len(beds)} ambience beds")
    for tier in PRIORITY:
        c = sum(1 for s in sfx if s["tier"] == tier)
        if c:
            print(f"        {tier:<10} {c:>4} @ {TIERS[tier][0]:+.0f} dB")


if __name__ == "__main__":
    main()
