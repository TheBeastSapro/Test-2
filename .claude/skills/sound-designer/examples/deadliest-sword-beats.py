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
    # The real thing: "Weapons, Armor, Medieval Shield, Impact, Hit, Block, Sword
    # Attack" -- an actual sword-on-shield recording. It is a 3.23 s take holding
    # four blows, so dropped whole it read as a slam, and its energy accumulates
    # across all four so the measured anchor put the cluster 695 ms early. Split
    # into single hits by oneshot.py it is one clash per file, 0.23 s, attack at
    # the front. clatter carries the shield's wood.
    (28.75, "khopesh clashes on the shield",  "shield", ["shield_01"], -7.0, ["clatter"]),
    (30.21, "khopesh drives into the shield", "shield", ["shield_02"], -7.0, ["clatter"]),
    (32.79, "khopesh swings down",            "swish",  ["whoosh_11", "whoosh_12"], -10.0, []),
    # Vocals, one per fight beat that earns one, and no more -- the swing that
    # costs effort and the blow that kills. "Voices, Efforts, Male, Attack,
    # Grunt, Breath, Short, Multiple 02" is a 3.56 s take holding THREE grunts
    # (measured, find_hits), so it is split by oneshot.py into vox_effort_01..03
    # at 0.16-0.26 s each, anchors 4-17 ms. Dropped whole it would have played
    # all three grunts down one swing.
    (32.79, "the effort of the swing",        "vox_effort", ["vox_effort_01"], -11.0, []),
    (34.12, "the hook catches the shield",    "shield", ["shield_03"], -7.0, ["armor"]),
    (35.58, "the killing stab",               "stab",   ["stab_04"],  -5.0, ["impact", "armor"]),
    # 80 ms after the blade, not on it: a man cries out after he is hit, not as
    # he is hit, and on the frame itself it just thickens the stab. "Voices,
    # Male, Sudden Death, Combat, Pain 04" -- cast for the object (a man killed
    # in combat) over the shape; vox_cry_02 ("Scream, Male, Short", 0.60 s) is
    # the alternate if the 91 ms anchor reads late against picture.
    (35.66, "the cry as it lands",            "vox_cry",    ["vox_cry_01"],    -7.0, []),
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

# --------------------------------------------------------------- mute windows
# A still figure is not an event. The redraw detector cannot tell a portrait
# sliding into frame from a blade entering a shield -- both are large mid-band
# redraws -- so photographs and painted figures kept drawing sword hits, and the
# channel owner sent screenshots of two of them: a museum photograph of
# Tutankhamun's mask with its caption, and a sepia portrait plate.
#
# The right sound for a portrait appearing is a soft element or nothing at all.
# It is never a strike, because nothing is being struck, so these are muted
# rather than re-tiered. Hand-timed beats are unaffected by a window.
#
# NOTE: this list is incomplete. Only the two reported portraits and the 0:06
# tick are timed here; the rest of the video's figure shots have not been swept,
# which needs the frames (contact sheets) and the video is not in this repo.
MUTE = [
    (5.60,  6.60,  "small tick over the intro, reported at 0:06"),
    (13.20, 14.40, "Tutankhamun photograph + caption -- a portrait, not a strike"),
]
cue["mute_windows"] = [list(w) for w in MUTE]
print(f"[beats] {len(MUTE)} mute window(s) for generic cues")
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
# The legion faces and points left, so it advances right-to-left, and the sound
# should travel with it. The marching beds measured dead centre (+0.7 dB balance)
# and were described as sitting on one side -- a static source under a moving
# picture reads as stuck, because the ear localises it once and stops believing
# it. pan is [from, to] in [-1, +1]; not a full hard sweep, which on a wide shot
# draws attention to itself.
# The third shot is the one place in the video where a crowd is the SUBJECT, so
# it gets the third and last vocal: "Crowds, Battle, Medium, Yell, Short". Cast
# as a yell, not a charge -- the ranks are holding formation, and the "Battle
# Cry, Screams, Charge" recordings are men running, which is the same
# wrong-for-the-shot error as marching over corpses at 160.6.
#
# Level matters more here than for the other two, because beds are mixed onto
# the SFX bus and the SFX bus is NOT sidechained -- only the music bus ducks. A
# crowd yell is mid-band, right where the narration lives, so an un-ducked yell
# is the single most likely thing in this sheet to overlap the VO. It sits at
# -32 dBFS: above amb_06 so it reads as the feature of the shot, still ~4 dB
# under the -28 music bed so it cannot climb over the voice. amb_06 drops from
# -33 to -36 to make room rather than fighting it.
SHOTS = [
    (155.5, 2.2, "legion in close formation",       [("march_01", -37.0)], [0.6, -0.6]),
    (160.6, 3.0, "the field after the battle",      [("amb_04", -34.0)],   None),
    (172.5, 3.2, "the ranks shout",                 [("amb_06", -36.0),
                                                     ("vox_yell_01", -32.0)], None),
    (178.0, 5.8, "the legion marches in formation", [("march_05", -37.0)], [0.85, -0.85]),
]
beds = []
for i, (at, dur, label, layers, pan) in enumerate(SHOTS, 1):
    for j, (f, target) in enumerate(layers):
        # bed-category files are levelled from measurement; hit-category files
        # are already peak-normalised, so they take a plain trim.
        #
        # A named rms target that silently misses `_rms` used to fall through to
        # a flat -20 dB, which is not a near miss: on the crowd yell that is
        # ~12 dB hot and lands an un-ducked vocal on top of the narration. A
        # file only reaches _rms if its prefix was passed to palette.py
        # --bed-prefix (amb,march,vox_yell here), so a miss means the palette
        # was built without it. Say so instead of shipping the loud version.
        if target is not None and f not in LV:
            raise SystemExit(
                f"[beats] {f} wants {target} dBFS rms but was not levelled as a "
                f"bed.\n        Rebuild the palette with {f.rsplit('_', 1)[0]} "
                f"in --bed-prefix, e.g.\n        palette.py --raw pal_raw --out "
                f"pal --bed-prefix amb,march,vox_yell")
        g = round(target - LV[f], 2) if target is not None else -20.0
        bed = {"id": f"hb{i}_{j}", "at": at, "dur": dur, "gain_db": g,
               "fade": 0.35, "era": label, "hand": True,
               "asset": os.path.join(P, f"{f}.wav")}
        if pan:
            bed["pan"] = pan
        beds.append(bed)
cue["amb_beds"] = beds
print(f"[beats] {len(cue['amb_beds'])} hand beds across {len(SHOTS)} shots")

json.dump(cue, open(f"{J}/cues_beats.json", "w"), indent=1)
print(f"[beats] wrote {J}/cues_beats.json")
