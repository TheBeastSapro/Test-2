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

DEFAULT_WEIGHT = ["body"]

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
    ap.add_argument("--bed-rms", type=float, default=-42.0,
                    help="put ambience beds at this rms dBFS. Derived from the "
                         "measured source level, not a fixed trim: bed sources "
                         "run 12 dB apart, so a fixed trim put them at -55..-65 "
                         "dBFS and every bed in the mix was inaudible.")
    ap.add_argument("--no-anticipation", action="store_true")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    cue = json.load(open(args.cues))
    global DEFAULT_WEIGHT
    DEFAULT_WEIGHT = cue.get("default_weight_cats") or ["body"]
    ev = json.load(open(args.events))
    pal = json.load(open(os.path.join(args.palette, "palette_manifest.json")))
    anchors = pal.pop("_anchors", {})     # per-file rise time; see palette.py
    fronts = pal.pop("_frontload", {})    # "starts with a bang" ratio
    levels = pal.pop("_rms", {})          # measured bed rms, for levelling
    apath = os.path.abspath(args.palette)

    missing = [c for c in set(TIER_CAT.values()) | {"swish"} if c not in pal]
    if missing:
        raise SystemExit(f"[place] palette is missing categories: {missing}")

    rot = {c: Rotator(v, rng, cooldown=90.0 if c == "boom" else 30.0)
           for c, v in pal.items() if c != "amb" and v}

    # An era card or a stated turning point has to land ON its frame, so it must
    # be cast with an impact rather than a swell. Two of six boom files are
    # swells (one rises in 398 ms, one in 227 ms); using them on cards put that
    # tier 57 ms early with not one cue inside a frame. Files whose measured
    # rise is under PUNCHY_MAX are the ones that can hit a mark.
    # Front-loaded is the right test, not a small anchor: it asks whether the
    # file HAS an attack, rather than whether its energy happens to arrive early.
    punchy = [f for f in pal.get("boom", []) if fronts.get(f, 0.0) >= 0.40]
    if len(punchy) < 2:
        punchy = [f for f in pal.get("boom", []) if anchors.get(f, 0.0) <= 0.12]
    if len(punchy) >= 2:
        rot["boom_punchy"] = Rotator(punchy, rng, cooldown=90.0)
        swells = [f for f in pal.get("boom", []) if f not in punchy]
        print(f"[place] card booms cast from {len(punchy)} impact-type files; "
              f"{len(swells)} swell(s) held back: {', '.join(swells) or 'none'}")
    else:
        rot["boom_punchy"] = rot["boom"]

    cand = []      # dicts: tier, t, cat, label, and optional explicit choices

    # 1. hand-timed beats: the designed moments, never dropped.
    #
    # A hand-timed beat may name its own sound, because the pool is the wrong
    # tool for the shots that matter. On the sword video the pharaoh's khopesh
    # going into a man's chest drew "medieval shield impact" from the metal pool
    # -- correct category, wrong object, and it read as unsatisfying exactly as
    # a viewer reported. Honoured keys: cat (a palette category), files (an
    # explicit list to rotate through), tier, gain_db, stack (extra categories
    # layered on the same beat, e.g. ["body"] to put weight under a stab).
    for s in cue.get("sfx_cues", []):
        if s.get("kind") in GENERIC:
            continue
        word = (s.get("epidemic") or {}).get("search", "clash")
        cat = s.get("cat") or HERO_CAT.get(word, "impact")
        cand.append({"tier": s.get("tier") or ("hero_boom" if cat == "boom"
                                               else "hero_hit"),
                     "t": s["at"], "cat": cat, "label": s["kind"],
                     "files": s.get("files"), "gain_db": s.get("gain_db"),
                     "stack": s.get("stack"), "hand": True,
                     "solo_ok": s.get("solo_ok", False)})
    heroes = len(cand)

    # 2-3. the visual beats.
    #
    # Two event vocabularies are accepted. visual_redraw.py classifies by how
    # much of the frame was redrawn, which for animation is both more reliable
    # and self-classifying, so its labels are trusted directly. visual_events.py
    # produces a continuous optical-flow curve that has to be percentile-cut.
    #
    # Prefer redraw. Flow ranking got the beats that matter wrong: a khopesh
    # entering a chest is a small movement, so it ranked below a camera pan and
    # was cast as a generic "movement" swish, and a hook catching a shield was
    # cast as a caption tick. Both are unmistakable mid-band redraws.
    redraw_mode = any(e.get("kind") == "element" for e in ev["events"])
    if redraw_mode:
        acts = [e for e in ev["events"] if e["kind"] == "action"]
        split = (sorted(e["strength"] for e in acts)[len(acts) // 2]
                 if acts else 0.0)
        for e in ev["events"]:
            k = e["kind"]
            if k == "cut":
                cand.append({"tier": "whoosh", "t": e["t"], "cat": "whoosh",
                             "label": "shot change"})
            elif k == "action":
                big = e["strength"] >= split
                cand.append({"tier": "impact" if big else "swish", "t": e["t"],
                             "cat": "impact" if big else "swish",
                             "label": "strike" if big else "movement"})
            else:
                cand.append({"tier": "pop", "t": e["t"], "cat": "pop",
                             "label": "small element"})
        print(f"[place] redraw events: {sum(1 for e in ev['events'] if e['kind']=='cut')} cuts, "
              f"{len(acts)} actions (split at {split:.3f}), "
              f"{sum(1 for e in ev['events'] if e['kind']=='element')} elements")
    else:
        for e in ev["events"]:
            if e["kind"] == "cut":
                cand.append({"tier": "whoosh", "t": e["t"], "cat": "whoosh",
                             "label": "shot change"})
        acts = sorted((e for e in ev["events"] if e["kind"] == "action"),
                      key=lambda e: e["strength"])
        if acts:
            n = len(acts)
            lo = acts[int(n * args.drop_weakest)]["strength"]
            mid = acts[int(n * (args.drop_weakest + (1 - args.drop_weakest) * .46))]["strength"]
            hi = acts[int(n * .88)]["strength"]
            for e in acts:
                v = e["strength"]
                if v < lo:
                    continue
                tier = "impact" if v >= hi else ("swish" if v >= mid else "pop")
                cand.append({"tier": tier, "t": e["t"], "cat": TIER_CAT[tier],
                             "label": {"impact": "strike", "swish": "movement",
                                       "pop": "small element"}[tier]})

    # 3b. mute windows. The detector fires on redraw, which is a good proxy for
    # "something happened" and a bad one for "something was STRUCK". A portrait
    # of Tutankhamun sliding in with its caption is a big redraw, so it drew a
    # sword hit -- a sword sound over a museum photograph, reported by the
    # channel owner with a screenshot. There is no sound the detector could have
    # picked that would be right there, because nothing is being hit: the beat
    # should be silent, and no amount of re-tiering expresses that.
    #
    # A window names a span that generic cues may not sound in. Hand-timed beats
    # are never muted -- if a designed beat is wrong, fix or delete the beat.
    # Each entry is [start, end] or [start, end, "why"], seconds.
    mutes = [w for w in cue.get("mute_windows", []) if len(w) >= 2]
    if mutes:
        before = len(cand)
        cand = [c for c in cand
                if c.get("hand")
                or not any(w[0] <= c["t"] <= w[1] for w in mutes)]
        print(f"[place] {before - len(cand)} generic cue(s) muted "
              f"across {len(mutes)} window(s)")
        for w in mutes:
            why = w[2] if len(w) > 2 else ""
            print(f"          {w[0]:7.2f}-{w[1]:6.2f}s  {why}")

    # 4. resolve collisions by PRIORITY, not by strength -- a caption tick must
    # never elbow a sword strike. Hand-timed beats are exempt from the guard
    # against each other: an era card is deliberately a whoosh leading into a
    # boom 0.4 s later, and a 2.2 s guard would delete the whoosh.
    # A card boom is EXCLUSIVE: nothing else may sound within CARD_SOLO of it
    # except the whoosh that leads into it. The hero-vs-hero exemption above is
    # what a card needs (its whoosh sits 0.4 s ahead and must survive the boom's
    # 2.2 s guard) but it also let a hand-timed sword beat land on the exact
    # frame of one card, so a metal ring-out played over the title. A title card
    # is a boom and nothing else.
    # The guard is symmetric, and that is right for the generic pool but wrong
    # for designed action. An era card does not stop the story: the card is
    # drawn and the scene under it keeps moving, so a hand-cast beat landing
    # inside the window is silenced along with the caption ticks it was meant to
    # stop. That is how the falcata reaching over the Roman shield -- one of the
    # named beats in the script -- ended up with no sound at all under the IRON
    # AGE card. A hand-timed beat sets "solo_ok": true to say "I know, I meant
    # it"; nothing in the generic pool can.
    CARD_SOLO = 0.45
    booms = [c["t"] for c in cand if c["tier"] == "hero_boom"]

    kept, lost, shushed = [], 0, []
    for tier in PRIORITY:
        guard, hero = TIERS[tier][1], tier.startswith("hero")
        for c in sorted((c for c in cand if c["tier"] == tier), key=lambda c: c["t"]):
            if (tier != "hero_boom" and "into the card" not in c["label"]
                    and not c.get("solo_ok")):
                if any(abs(c["t"] - b) <= CARD_SOLO for b in booms):
                    shushed.append(c)
                    continue
            # A hand-timed beat is never dropped. Step 1 has said so in prose
            # since this file was written and the guard has never honoured it,
            # because the guard is sized to thin the GENERIC pool and was being
            # applied to designed cues as well. On a real render that deleted
            # 31 of 115 hand-timed beats, in three ways:
            #   * all seven era-card whooshes, every time. A card whoosh sits
            #     0.4 s ahead of a boom whose guard is 2.2 s, so it can never
            #     survive. The hero exemption below was written for exactly
            #     this case and does not reach it -- a whoosh is not a hero
            #     tier -- so every card in two finished mixes got its boom with
            #     no lead-in and nothing said so.
            #   * designed beats eaten by other designed beats: the survivors
            #     of K17 lost to the explosion directly above them, and three
            #     of the four bursts in a burning column lost to the first.
            #   * designed beats eaten by the generic pool on a higher-priority
            #     tier -- the same "a nothing-cue deletes a named beat" failure
            #     SKILL.md already describes, arriving from the other side.
            # If it is in the sheet, it was meant; spacing designed beats is
            # the sheet's job, and the log below flags any that crowd.
            if not c.get("hand"):
                rivals = [k for k in kept if not (hero and k["tier"].startswith("hero"))]
                if any(abs(c["t"] - k["t"]) < max(guard, TIERS[k["tier"]][1])
                       for k in rivals):
                    lost += 1
                    continue
            kept.append(c)
    # Name them. A bare count made a silenced *hand-cast* beat indistinguishable
    # from a silenced caption tick, so a designed moment could go missing and the
    # log looked healthy. A hand-timed beat landing here is nearly always a bug.
    if shushed:
        print(f"[place] {len(shushed)} cue(s) silenced for sitting on a title card")
        for c in shushed:
            flag = "  <-- HAND-TIMED, set solo_ok if intended" if c.get("hand") else ""
            print(f"          {c['t']:8.2f}s  {c['label']}{flag}")
    kept.sort(key=lambda c: c["t"])

    # Hand beats are now unconditionally kept, so the sheet is what stops two
    # of them landing on the same frame. Name the close pairs rather than
    # letting a doubled hit be discovered by ear.
    hands = [c for c in kept if c.get("hand")]
    crowd = [(a, b) for a, b in zip(hands, hands[1:]) if b["t"] - a["t"] < 0.30]
    if crowd:
        print(f"[place] {len(crowd)} pair(s) of hand-timed beats inside 0.30s — "
              f"check these are layers you meant, not duplicates")
        for a, b in crowd:
            print(f"          {a['t']:8.2f}s {a['label'][:38]!r}")
            print(f"          {b['t']:8.2f}s {b['label'][:38]!r}  (+{(b['t']-a['t'])*1000:.0f} ms)")

    # 5. assign files
    sfx, counts = [], {}
    _warned_missing: set[str] = set()
    adhoc = {}                       # rotators for explicit per-beat file lists

    def pick(cat, files, t):
        if files:
            key = tuple(files)
            if key not in adhoc:
                adhoc[key] = Rotator(files, rng, cooldown=20.0)
            return adhoc[key].take(t)
        return rot["boom_punchy" if cat == "boom" and pick.hero_boom else cat].take(t)

    for i, c in enumerate(kept, 1):
        tier, t, cat, label = c["tier"], c["t"], c["cat"], c["label"]
        pick.hero_boom = tier == "hero_boom"
        f = pick(cat, c.get("files"), t)
        counts[f] = counts.get(f, 0) + 1
        gain = c.get("gain_db")
        gain = TIERS[tier][0] if gain is None else float(gain)
        sfx.append({"id": f"s{i}", "at": round(t, 4), "kind": label,
                    "tier": tier, "cat": cat, "gain_db": gain,
                    "vary": VARY.get(cat, 0.0), "pre_trimmed": True,
                    "anchor": anchors.get(f, 0.0),
                    "asset": os.path.join(apath, f"{f}.wav")})
        # A strike gets a short swish just before contact. One sound is a
        # sample; two is a designed hit.
        # ...but not in front of a voice. Anticipation is the air a moving object
        # displaces before it lands; a grunt or a cry displaces nothing, so a
        # swish in front of one is a whoosh attached to a man's throat. It also
        # doubled up: the grunt on the Bronze Age swing sat on the same frame as
        # the swing's own anticipation, so the beat got two swishes and a voice.
        voice = cat.startswith("vox")
        if (not args.no_anticipation and not voice
                and tier in ("impact", "hero_hit") and t > 0.4):
            g = rot["swish"].take(t)
            sfx.append({"id": f"s{i}a", "at": round(t - 0.13, 4),
                        "kind": f"{label} (anticipation)", "tier": "swish",
                        "cat": "swish", "gain_db": gain - 7.0, "vary": 0.3,
                        "layer": "anticipation", "pre_trimmed": True,
                        "anchor": anchors.get(g, 0.0),
                        "asset": os.path.join(apath, f"{g}.wav")})
        # ...and whatever the beat asks to be stacked on it, just after contact.
        # Metal alone is thin: the weight of a hit is the flesh-and-armour
        # element under it, 35 ms late because the body reacts after the blade
        # arrives. Generic strikes default to a body layer; a hand-timed beat can
        # ask for anything in the palette (a shield drag, a spear clatter).
        stack = c.get("stack")
        if stack is None and tier in ("impact", "hero_hit"):
            # The default weight pool is per-video, because "body" names an
            # object. Four flesh punches under every generic strike is right for
            # a video about men hitting each other and wrong for one about
            # stone, timber and iron -- and with only four files they played 31
            # times each on a 12-minute castle video, twice over the reuse rule.
            # Set "default_weight_cats" in the cue sheet to say what a strike in
            # THIS video weighs; "body" stays the fallback.
            stack = DEFAULT_WEIGHT
        for k, scat in enumerate(stack or []):
            if scat not in rot:
                # Loud, because silent was expensive: rebuilding a palette once
                # dropped the "body" category, and every generic strike lost its
                # weight layer for a whole render without a single warning.
                if scat not in _warned_missing:
                    _warned_missing.add(scat)
                    print(f"[place] WARNING: stack category {scat!r} is not in the "
                          f"palette — those layers are being dropped")
                continue
            h = rot[scat].take(t)
            sfx.append({"id": f"s{i}b{k}", "at": round(t + 0.035 + k * 0.05, 4),
                        "kind": f"{label} (weight)", "tier": "swish",
                        "cat": scat, "gain_db": gain - 5.0, "vary": 0.2,
                        "layer": "weight", "pre_trimmed": True,
                        "anchor": anchors.get(h, 0.0),
                        "asset": os.path.join(apath, f"{h}.wav")})
    sfx.sort(key=lambda s: s["at"])

    # 6. beds. "This area has no SFX" is answered by room tone, not more hits.
    #
    # Hand-written beds in the input sheet are carried through untouched. They
    # cover what a hit cannot: an army marching across a field is not an event,
    # it is a continuous texture, and placing single clanks on it reads as
    # nothing happening. Mark them "hand": true.
    beds = [b for b in cue.get("amb_beds", []) if b.get("hand")]
    if beds:
        print(f"[place] {len(beds)} hand-written beds carried through "
              f"(marching, crowds, weather)")
    if not args.no_beds and pal.get("amb"):
        war = [a for a in pal["amb"] if a.endswith(("_05", "_06", "_07"))]
        calm = [a for a in pal["amb"] if a not in war] or pal["amb"]
        war = war or pal["amb"]
        for k, m in enumerate(cue.get("music_sections", [])):
            hot = m.get("energy", 0.5) >= 0.62
            pool = war if hot else calm
            src = pool[k % len(pool)]
            gain = args.bed_rms - levels.get(src, -30.0) - (2.0 if hot else 0.0)
            beds.append({"id": f"b{k+1}", "at": round(m["start"], 3),
                         "dur": round(m["dur"], 3),
                         "gain_db": round(gain, 2), "fade": 2.5,
                         "era": m.get("era", ""),
                         "asset": os.path.join(apath, f"{src}.wav")})

    cue["sfx_cues"] = sfx
    cue["amb_beds"] = beds
    with open(args.out, "w") as f:
        json.dump(cue, f, indent=1)

    dur = cue.get("duration") or (sfx[-1]["at"] if sfx else 1.0)
    # Rate is per *event*, not per cue: a three-layer strike is one thing the
    # viewer hears, and counting its layers separately makes a well-built stack
    # look like the density problem it is meant to replace.
    prim = [s for s in sfx if not s.get("layer")]
    gaps = [b["at"] - a["at"] for a, b in zip(prim, prim[1:])] or [0.0]
    busiest = sorted(counts.items(), key=lambda x: -x[1])[:3]
    print(f"[place] {len(cand)} candidates ({heroes} hand-timed) -> {len(kept)} kept, "
          f"{lost} lost a collision, {len(sfx)-len(kept)} stack layers")
    print(f"[place] {len(prim)} events over {dur:.0f}s = one per "
          f"{dur/max(1,len(prim)):.2f}s ({len(sfx)} cues including layers)")
    print(f"[place] {len(counts)} distinct files; busiest: "
          + ", ".join(f"{f} x{n}" for f, n in busiest))
    print(f"[place] median gap {sorted(gaps)[len(gaps)//2]:.2f}s, {len(beds)} ambience beds")
    for tier in PRIORITY:
        c = sum(1 for s in sfx if s["tier"] == tier)
        if c:
            print(f"        {tier:<10} {c:>4} @ {TIERS[tier][0]:+.0f} dB")


if __name__ == "__main__":
    main()
