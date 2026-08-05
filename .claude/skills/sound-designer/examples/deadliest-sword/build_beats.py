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
OVERRIDE = {"AGE OF EMPIRES": 607.96,
            # Pinned, because snapping would move it. The BRONZE AGE card is
            # full-screen from 0.000 and cross-dissolves out between 0.4 and
            # 1.2, so the only strong redraw near it (0.917, strength 0.143) is
            # the MIDDLE OF THE DISSOLVE -- the card leaving. A boom snapped
            # there was reported as "unnecessary boom here", and removing it
            # altogether was the wrong correction: the card then had no sound
            # while every other era card does. It belongs at the top, on the
            # card itself, at 0.08.
            "BRONZE AGE": 0.08}

# The source sheet has seven era cards and the BRONZE AGE one is missing, so it
# was cast by generic redraw tiering as impact_08 -- a metal strike -- while the
# other seven get whoosh_01 into boom_01. Reported as "the bronze age title card
# has sword sound not boom/bass like world war 2".
#
# It gets the boom but NOT the lead-in whoosh. Every other card is drawn onto
# the screen, so a whoosh can run into it 0.40 s ahead; this one is already up
# at frame 0 (the video opens on it), which puts that whoosh at -0.32 s. The
# boom alone, at the top of the video, on the card that is on screen.
MISSING = [("BRONZE AGE", 0.08)]
for era, t in MISSING:
    if any(s_.get("kind", "").startswith(era) for s_ in cue["sfx_cues"]):
        continue
    cue["sfx_cues"].append({"at": t, "kind": f"{era} card"})
    print(f"[beats] added the missing {era} card at {t:.2f} (boom only, no lead-in)")

# NOTE, kept because it was learned the expensive way: the surviving
# sheet has seven era cards and this is not one of them, which looks like an
# omission and is not. Every other card ARRIVES -- it is drawn onto the screen,
# so there is a frame to punctuate, and it takes whoosh_01 into boom_01.
#
# This one is already on screen at t=0. The video opens on it, and between 0.4
# and 1.2 s it cross-dissolves out into the section header. The redraw action at
# 0.917 that looks like a card is the MIDDLE OF THAT DISSOLVE, so a boom snapped
# to it punctuates the card leaving, which is what it was for. Reported as
# "unnecessary boom here" the moment it was added.
#
# There is no arrival to hit, so the answer is nothing at all -- and 0.917 is
# muted below, because without a card boom to shush it the generic tiering casts
# that same dissolve as impact_08, the metal strike originally reported as "the
# bronze age title card has sword sound not boom/bass like world war 2".

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
    # Vocals, and only where a person would make one: the swing that costs
    # effort and the blow that kills. The source recording is three grunts in
    # one 3.56 s take, split by oneshot.py into vox_effort_01..03 (0.16-0.26 s,
    # anchors 4-17 ms) -- dropped whole it plays all three down one swing.
    (32.79, "the effort of the swing",        "vox_effort", ["vox_effort_01"], -11.0, []),
    (34.12, "the hook catches the shield",    "shield", ["shield_03"], -7.0, ["armor"]),
    (35.58, "the killing stab",               "stab",   ["stab_04"],  -5.0, ["impact", "armor"]),
    # 80 ms after the blade, not on it: a man cries out because he was hit, and
    # on the same frame it only thickens the stab.
    (35.66, "the cry as it lands",            "vox_cry", ["vox_cry_01"], -7.0, []),
    (37.08, "the body drops, spear clatters", "fall",   ["fall_01"],  -6.0, ["clatter", "armor"]),

    # The Iron Age wound chart. A green info panel and two labels appearing are
    # not strikes -- the redraw tiers had cast the panel as a metal impact -- but
    # each label names a wound, so each gets the sound of that wound, quietly.
    (165.42, "the wound chart appears",       "pop",    ["pop_03"],  -17.0, []),
    (166.71, "spear wound",                   "stab",   ["stab_05"], -13.0, []),
    (167.79, "arrow wound",                   "stab",   ["stab_07"], -13.0, []),
    (168.71, "both men are dead",             "boom",   ["boom_06"], -12.0, []),

    # The Dacian falx hooking over the Roman shield -- one of the beats the
    # script names ("reached over and around Roman shields"), and it had NO cue
    # at all: reported as "sfx missing in this action". The redraw event at
    # 200.000 lost its collision to a generic "movement" swish 0.71 s earlier,
    # inside the 0.85 s swish guard, so the designed moment was deleted by a
    # nothing cue. As a hand-timed beat it takes priority instead.
    # Cast for the object: the blade CLEARS the rim rather than being blocked,
    # so it is a scrape into a ring-out, not the four-blow shield take. falx_02
    # ("Weapons, Sword, Hit Sword, Block, Parry, Impact, Ringing") measures
    # front-loaded 1.00 with a 0 ms anchor, so it lands on the frame.
    (200.00, "the falx hooks over the shield", "falx",  ["falx_02"], -7.0, ["armor"]),

    # The katana through the cutting target. The log is whole at 352.0 and
    # sliced at 353.0; the element redraw at 352.792 carried no cue at all.
    # Cast for the object -- a straw-and-wood target, so wood splitting, not
    # the gore slices the search keeps offering.
    (352.792, "the blade goes through the target", "cut", ["cut_01"], -7.0, []),

    # "Chopping weight": the shamshir into stone, red impact star on the rock.
    # Same fault as the falx -- the redraw at 423.667 exists but lost its
    # collision to a generic movement swish 0.63 s earlier, inside the swish
    # tier's 0.85 s guard. A hand-timed beat takes priority instead.
    (423.667, "the shamshir bites into the stone", "chop", ["chop_01"], -7.0, ["clatter"]),

    # The second stone chop, "throwing its weight into the last inches". Same
    # guard fault: the impact star is drawn at 661.542 and a generic movement
    # swish 0.42 s earlier ate it. The existing impact_06 at 663.500 is not this
    # beat -- it sits on the cut OUT to the trooper drill, and impact_06 is
    # "Metal, Impact, Ring Out 05", a ring rather than a bite into rock.
    (661.542, "the sabre bites into the stone", "chop", ["chop_02"], -7.0, ["clatter"]),

    # The cavalry charge at Salamanca: two troopers cut down, blood on the
    # blade. Flesh, not wood or stone -- the object rule again. 688.958 had only
    # a -15 dB movement swish on it.
    (688.958, "the sabre cuts the troopers down", "slash", ["slash_01"], -7.0, ["body"]),

    # Le Marchant is shot: standing at 692.3, down with X-eyes and a blood pool
    # at 692.65, and the musket lies in the grass. The redraw at 692.500 is the
    # shot itself and carried a movement swish. No antique musket SHOT exists in
    # the library -- the "Guns, Antique, Musket" entries are frizzen and trigger
    # handling -- so this is "Rifle, Large Shot 03", a single heavy black-powder
    # style report, split to its first shot.
    (692.500, "Le Marchant is shot",           "gun",   ["gun_01"],   -6.0, []),
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
# A still figure is not an event. The redraw detector cannot tell a photograph
# sliding into frame from a blade entering a shield -- both are large mid-band
# redraws -- so the opening minute put sword strikes on a sepia portrait of
# Howard Carter (impact_05 at 2.458), on the sarcophagus reveal beside it
# (impact_03 at 4.708), on a caption (impact_10 at 6.833) and on the photograph
# of Tutankhamun's mask (impact_04 at 13.333, impact_02 at 17.625).
#
# Nothing is being struck in any of them, so there is no quieter sound that is
# right -- the beat is silent, and the answer to a bare stretch is the ambience
# bed, not more hits. Generic cues only: hand-timed beats pass through.
# Deliberately narrow: only the three cues the channel owner actually reported.
# Two more sit in the same fault class -- impact_03 at 4.708 on the sarcophagus
# sliding in beside the Carter photo, impact_02 at 17.625 on the caption beside
# the Tutankhamun photo -- and both were left in on his instruction, because a
# mix that has been through several rounds of notes should not have unreported
# beats changed underneath it. Widen only when he flags one.
MUTE = [
    # The whole dissolve, not just the 0.917 event. Muting 0.917 alone lets a
    # pop at 0.500 surface that the boom's guard had been suppressing, so
    # removing the boom would have swapped it for a tick -- a sound that was
    # never in the approved mix. The card exit gets nothing.
    (0.40,  1.10,  "the BRONZE AGE card dissolving out -- an exit, not an event"),
    (122.85, 123.15, "impact_08 on the text card \"at Cannae two years later\""),
    (2.30,  2.60,  "impact_05 on the Howard Carter photograph"),
    (6.70,  7.00,  "impact_10 on a caption -- the tick reported at 0:06"),
    (13.20, 13.50, "impact_04 on the Tutankhamun photograph"),
]
cue["mute_windows"] = [list(w) for w in MUTE]
print(f"[beats] {len(MUTE)} mute window(s) over portraits and captions")
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
SHOTS = [
    (155.5, 2.2, "legion in close formation",       [("march_01", -37.0)], [0.6, -0.6]),
    (160.6, 3.0, "the field after the battle",      [("amb_04", -34.0)],   None),
    # The one shot where a crowd is the subject, so it takes the third and last
    # vocal. Beds mix onto the SFX bus and only the MUSIC bus is sidechained, so
    # a bed never ducks -- and a crowd is mid-band, right where the narration
    # lives. It sits at -32 dBFS: above the ambience so it reads as the feature
    # of the shot, still under the -28 music bed so it cannot climb over the
    # voice, with amb_06 pulled back from -33 to -36 to make room.
    # REVERTED on the channel owner's instruction, asked twice. The crowd yell
    # added here is removed and the shot's bed goes back to exactly what it was
    # before -- crowd_01 (the renamed amb_06) at its original -33.0 dBFS. The
    # grunt and the cry on the Bronze Age fight stay; only this one is undone.
    (172.5, 3.2, "the ranks shout",                 [("crowd_01", -33.0)], None),
    (178.0, 5.8, "the legion marches in formation", [("march_05", -37.0)], [0.85, -0.85]),
]
beds = []
for i, (at, dur, label, layers, pan) in enumerate(SHOTS, 1):
    for j, (f, target) in enumerate(layers):
        # bed-category files are levelled from measurement; hit-category files
        # are already peak-normalised, so they take a plain trim
        g = round(target - LV[f], 2) if (target is not None and f in LV) else -20.0
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
