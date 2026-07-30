#!/usr/bin/env python3
"""Build the hand-authored beat sheet for 'The Deadliest Sword From Every Era'.

Reproducible from cues_prev.json + redraw.json, so re-running it after any
detector change re-derives the same sheet instead of accumulating patches.

Three jobs:
  1. Retime the era cards onto the redraw that actually draws them.
  2. Cast the Bronze Age fight beat by beat, read off contact sheets.
  3. Lay sustained beds under the marching/formation shots.
"""
import json
import os

J = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(J, "pal")
GENERIC = {"caption / small element", "shot change",
           "strong on-screen action", "element moves in"}

cue = json.load(open(f"{J}/cues_prev.json"))
ev = json.load(open(f"{J}/redraw.json"))["events"]

# ---------------------------------------------------------------- era cards
# Snap to the nearest *significant* redraw. Not the nearest event of any size:
# the IRON AGE card sits 0.42 s from its own 0.145-strength transition but only
# 0.08 s from a 0.006 caption tick, and nearest-of-any snapped it to the caption.
STRONG = [e for e in ev if e["strength"] >= 0.05]

# Read off the frames, and not fixable by snapping: the AGE OF EMPIRES card is
# drawn at 607.96 and the duel it cuts to starts at 609.46. The sheet had the
# card AT 609.46, so the card boom and the hand-timed duel strike landed on the
# same frame and a metal ring-out played over the title.
OVERRIDE = {"AGE OF EMPIRES": 607.96}

cards, moved = {}, 0
for s in cue["sfx_cues"]:
    k = s.get("kind", "")
    if not k.endswith("card") or "into" in k:
        continue
    era = k[:-5].strip()
    if era in OVERRIDE:
        t = OVERRIDE[era]
    else:
        near = min(STRONG, key=lambda e: abs(e["t"] - s["at"]))
        t = near["t"] if abs(near["t"] - s["at"]) <= 1.6 else s["at"]
    if abs(t - s["at"]) > 0.08:
        print(f"  {era:<24} {s['at']:8.2f} -> {t:8.2f} ({(t-s['at'])*1000:+6.0f} ms)")
        moved += 1
    s["at"] = t
    cards[era] = t
print(f"[beats] retimed {moved} of {len(cards)} era cards")

# One signature for every card: the same whoosh into the same boom, 0.40 s apart.
# Neither carries a body layer -- the default stack was putting a flesh thud
# behind every title transition.
for s in cue["sfx_cues"]:
    k = s.get("kind", "")
    if "into the card" in k:
        era = k.split("—")[0].strip()
        s.update(cat="whoosh", files=["whoosh_01"], tier="hero_hit", stack=[],
                 at=round(cards.get(era, s["at"] + 0.4) - 0.40, 3))
    elif k.endswith("card"):
        s.update(cat="boom", files=["boom_01"], tier="hero_boom", stack=[])

# ------------------------------------------------------- the Bronze Age fight
# Every beat below was previously a generic swish or a caption tick. Times come
# from the redraw curve, casting from the frames: flesh leads, metal and armour
# sit under it.
# The first two strikes land on the WOODEN SHIELD, not on the man: the impact
# star sits on the shield with the blade against it, and the defender only takes
# X-eyes at 35.58, after the hook drags his shield away at 34.12. Casting them as
# flesh stabs was wrong -- a viewer caught it -- so they are wood-and-metal blocks
# and the flesh sound is saved for the one beat that earns it.
BEATS = [
    (21.00, "pharaoh lunges",                 "swish",  ["swish_01", "swish_03"], -11.0, []),
    (28.75, "khopesh blocked on the shield",  "impact", ["impact_11"], -6.0, ["clatter"]),
    (30.21, "khopesh drives into the shield", "impact", ["impact_04"], -6.0, ["clatter"]),
    (32.79, "khopesh swings down",            "swish",  ["whoosh_11", "whoosh_12"], -10.0, []),
    (34.12, "the hook catches the shield",    "impact", ["armor_01"], -7.0, ["impact"]),
    (35.58, "the killing stab",               "stab",   ["stab_04"],  -5.0, ["impact", "armor"]),
    (37.08, "the body drops, spear clatters", "fall",   ["fall_01"],  -6.0, ["clatter", "armor"]),

    # The Iron Age wound chart. A green info panel and two labels appearing are
    # not strikes -- the redraw tiers had cast the panel as a metal impact -- but
    # each label names a wound, so each gets the sound of that wound, quietly.
    (165.42, "the wound chart appears",       "pop",    ["pop_03"],  -17.0, []),
    (166.71, "spear wound",                   "stab",   ["stab_05"], -13.0, []),
    (167.79, "arrow wound",                   "stab",   ["stab_07"], -13.0, []),
    (168.71, "both men are dead",             "boom",   ["boom_06"], -12.0, []),
]
beats = [s for s in cue["sfx_cues"]
         if s.get("kind") not in GENERIC
         and s.get("kind") != "pharaoh's khopesh strikes"]   # replaced by the seven
for at, kind, cat, files, gain, stack in BEATS:
    beats.append({"id": f"h_{int(at*100)}", "at": at, "kind": kind, "cat": cat,
                  "files": files, "gain_db": gain, "stack": stack,
                  "tier": "hero_hit", "vary": 0.0})
beats.sort(key=lambda s: s["at"])
cue["sfx_cues"] = beats
print(f"[beats] {len(BEATS)} hand-cast Bronze Age beats, {len(beats)} hand-timed total")

# ------------------------------------------------------------------ the beds
# An army crossing a field is a texture, not an event: single clanks on it read
# as nothing happening. Two layers each -- armour moving, and the weapons
# rattling with it.
# Targets are rms dBFS, converted per file from its measured level. The VO sits
# at -18 dBFS and the music bed lands near -28, so a featured texture like
# marching belongs around -31: clearly present, still under the narration.
LV = json.load(open(f"{J}/pal/palette_manifest.json")).get("_rms", {})
# Marching sat at -31 dBFS and fought the narration, so the beds drop to -37:
# under the -28 dB music rather than beside it. Present, not competing.
#
# And 160.54 is not an advancing army -- it is the AFTERMATH, corpses strewn over
# a field with survivors standing among them. Marching over dead bodies is
# exactly the "doesn't match the scene" a viewer reported. It gets cold wind.
SHOTS = [
    (155.5, 2.2, "legion in close formation",       [("march_01", -37.0)]),
    (160.6, 3.0, "the field after the battle",      [("amb_04", -34.0)]),
    (172.5, 3.2, "the ranks shout",                 [("amb_06", -33.0)]),
    (178.0, 5.8, "the legion marches in formation", [("march_05", -37.0)]),
]
beds = []
for i, (at, dur, label, layers) in enumerate(SHOTS, 1):
    for j, (f, target) in enumerate(layers):
        # bed-category files are levelled from measurement; hit-category files
        # are already peak-normalised, so they take a plain trim
        g = round(target - LV[f], 2) if (target is not None and f in LV) else -20.0
        beds.append({"id": f"hb{i}_{j}", "at": at, "dur": dur, "gain_db": g,
                     "fade": 0.35, "era": label, "hand": True,
                     "asset": os.path.join(P, f"{f}.wav")})
cue["amb_beds"] = beds
print(f"[beats] {len(cue['amb_beds'])} hand beds across {len(SHOTS)} shots")

json.dump(cue, open(f"{J}/cues_beats.json", "w"), indent=1)
print(f"[beats] wrote {J}/cues_beats.json")
