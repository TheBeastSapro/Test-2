#!/usr/bin/env python3
"""Build the hand-authored cue sheet for The Weirdest Warships from Every Era.

Every time here was read off a contact sheet or measured, not estimated from
the script. Era-card times come from cards.py (white frame + red progress bar).
"""
import json, os

PAL = json.load(open("pal/palette_manifest.json"))
RMS = PAL["_rms"]
EV  = [e["t"] for e in json.load(open("redraw.json"))["events"]]
AUTO = json.load(open("cues_auto.json"))

def snap(t, win=1.2):
    """Land a hand beat on the picture change nearest to it."""
    near = [e for e in EV if abs(e - t) <= win]
    return min(near, key=lambda e: abs(e - t)) if near else t

CARDS = [0.400, 81.167, 167.667, 290.633, 386.133, 494.667, 615.600]
NAMES = ["THE ANCIENT WORLD", "THE MIDDLE AGES", "THE EARLY MODERN AGE",
         "THE AGE OF SAIL", "THE IRONCLAD AGE", "WORLD WAR I", "WORLD WAR II"]

# ---------------------------------------------------------------- music
#  id  start     end       energy label                                     track
SECTIONS = [
 ("m1",   0.000,  34.600, 0.52, "Syracusia: the garden, the town that floated", "Those Who Wander"),
 ("m2",  34.600,  81.167, 0.44, "she never fought, and then vanished",          "Something Peculiar"),
 ("m3",  81.167, 124.600, 0.58, "the paddle wheel warship, men on treadmills",  "Infernal Machine"),
 ("m4", 124.600, 167.667, 0.62, "Yue Fei's weed and logs, then the Opium War",  "Fool Me Twice"),
 ("m5", 167.667, 220.667, 0.60, "the turtle ship and its roof",                 "At Enemy Lines"),
 ("m6", 220.667, 251.967, 0.50, "Angolpo, and the ironclad claim",              "Make No Mistakes"),
 ("m7", 251.967, 290.633, 0.68, "Vasa: the maiden voyage",                      "The Last Disaster"),
 ("m8", 290.633, 335.500, 0.54, "Bushnell builds the Turtle",                   "Seekers and Finders"),
 ("m9", 335.500, 386.133, 0.62, "Ezra Lee under HMS Eagle",                     "It's Not a Game"),
 ("m10",386.133, 444.600, 0.50, "Novgorod: a circle with guns on it",           "The King of Thieves"),
 ("m11",444.600, 494.667, 0.48, "the spinning story against the service record","Confidentiality"),
 ("m12",494.667, 540.600, 0.55, "the K-boats, and five minutes to dive",        "Wiretapped"),
 ("m13",540.600, 603.600, 0.54, "the night of 31 January 1918",                 "Estimations"),
 ("m14",603.600, 615.600, 0.30, "a hundred and four men, and a locked file",    "The Changeing"),
 ("m15",615.600, 658.267, 0.58, "Surcouf: cruiser guns on a submarine",         "Rise to Power"),
 ("m16",658.267, 690.700, 0.52, "France falls; nobody has a job for her",       "Tragedy Unfolds"),
 ("m17",690.700, 718.171, 0.36, "she was never found",                          "Alluvion"),
]

# ---------------------------------------------------------------- beds
#  one per section, hand-assigned. No auto rotation: two of the sword palette's
#  ambiences were crowds with people in them, and a bed never ducks.
#  (start, end, amb file, rms target dBFS, why)
BEDS = [
 (  0.000,  34.600, "amb_02", -42, "open sea under the Syracusia's deck"),
 ( 34.600,  81.167, "amb_01", -43, "gentle sea; she sails once and is gone"),
 ( 81.167, 124.600, "amb_12", -41, "river warship: hull and water on the boards"),
 (124.600, 167.667, "amb_01", -42, "the Dongting lakes, flat water"),
 (167.667, 220.667, "amb_02", -42, "the turtle ship at sea"),
 (220.667, 251.967, "amb_09", -42, "Angolpo aftermath, wind coming up"),
 (251.967, 279.000, "amb_04", -41, "Stockholm quay: docks, ropes, boats lapping"),
 (279.000, 290.633, "amb_01", -44, "flat water where she was"),
 (290.633, 300.000, "amb_05", -38, "under HMS Eagle's bottom"),
 (300.000, 335.500, "amb_06", -42, "Bushnell's workshop timbers"),
 (335.500, 348.000, "amb_10", -41, "New York Harbor, eleven at night"),
 (348.000, 371.000, "amb_05", -37, "submerged, thirty minutes of air"),
 (371.000, 386.133, "amb_10", -42, "back on the surface, harbour at night"),
 (386.133, 444.600, "amb_01", -42, "the Black Sea shallows"),
 (444.600, 494.667, "amb_09", -42, "the Dnieper estuary, wet in any real sea"),
 (494.667, 520.000, "amb_02", -41, "the Grand Fleet at twenty-one knots"),
 (520.000, 540.600, "amb_07", -40, "inside a K-boat, thirty openings"),
 (540.600, 603.600, "amb_09", -40, "the Firth of Forth in mist, forty ships"),
 (603.600, 615.600, "amb_11", -46, "almost nothing; the file closes"),
 (615.600, 658.267, "amb_02", -42, "Surcouf on the surface"),
 (658.267, 678.000, "amb_04", -42, "Plymouth"),
 (678.000, 690.700, "amb_10", -41, "north of Cristobal, in the dark"),
 (690.700, 712.000, "amb_11", -41, "under it"),
 (712.000, 718.171, "amb_01", -45, "empty water"),
]

# ---------------------------------------------------------------- beats
# (time, label, cat, tier, gain_db, stack, snap-to-picture)
B = []
for t, name in zip(CARDS, NAMES):
    B.append((t - 0.40, f"era card whoosh (into the card) — {name}", "surge",  "whoosh",    -10.0, None, False))
    B.append((t,        f"era card — {name}",                        "boom",   "hero_boom",  -5.0, ["surge"], False))

B += [
 # --- The Ancient World -------------------------------------------------
 (  1.800, "card clears to the garden on the deck",              "gust",    "whoosh",    -13.0, None, True),
 (  9.440, "the catapult, loaded with an eighty-kilo stone",     "catapult","hero_hit",   -8.0, ["stone"], True),
 ( 13.220, "SYRACUSIA, 240 BC — the whole ship",                 "boom",    "hero_boom",  -6.0, ["surge"], True),
 ( 32.110, "a live fish out of the seawater tank",               "water",   "hero_hit",   -9.0, None, True),
 ( 35.890, "oars in the water; the screw pump clears the bilge", "oar",     "impact",    -10.0, ["water"], True),
 ( 58.560, "renamed ALEXANDRIA and given away",                  "shipbell","hero_hit",   -8.0, None, True),
 ( 62.330, "she sails for Egypt, once",                          "sail",    "hero_hit",  -10.0, ["surge"], True),
 ( 66.110, "\"No wreck has ever been found\"",                   "boom",    "hero_boom",  -6.0, None, True),
 ( 69.890, "the one surviving description",                      "paper",   "impact",    -11.0, None, True),
 ( 73.670, "Moschion writes it down",                            "quill",   "swish",     -14.0, None, True),
 # --- The Middle Ages ---------------------------------------------------
 ( 88.780, "PADDLE WHEEL WARSHIP — the wheel",                   "gears",   "hero_hit",   -8.0, ["creak"], True),
 ( 92.560, "men walking treadmills inside the hull",             "footdeck","impact",     -9.0, ["gears"], True),
 ( 96.330, "the wheel bites the water",                          "gears",   "hero_hit",   -8.0, ["water"], True),
 (107.670, "twelve wheels on each side",                         "gears",   "impact",    -10.0, None, True),
 (119.000, "imperial ships arrive under sail, into no wind",      "sail",    "impact",    -11.0, None, True),
 (122.780, "a paddle warship runs a sailing ship down",          "impact",  "hero_hit",   -7.0, ["woodbreak", "water"], True),
 (130.330, "rotten logs go into the water upstream",             "water",   "hero_hit",   -8.0, None, True),
 (132.400, "and the cut weed after them",                        "water",   "impact",    -10.0, None, True),
 (137.890, "the weed fouls the wheel",                           "creak",   "hero_hit",   -9.0, ["gears"], True),
 (145.440, "the wheels jam: a wooden box full of exhausted men", "boom",    "hero_boom",  -6.0, ["woodbreak"], True),
 (156.780, "a coal-fired Royal Navy squadron",                   "steam",   "hero_hit",  -10.0, ["horn"], True),
 # --- The Early Modern Age ---------------------------------------------
 (173.000, "GEOBUKSEON — the roof, and the spikes",              "impact",  "hero_hit",   -7.0, ["chain"], True),
 (191.000, "the dragon head vents smoke",                        "steam",   "hero_hit",   -9.0, None, True),
 (203.000, "guns firing through ports on every face",            "cannon",  "hero_boom",  -6.0, ["water"], True),
 (209.000, "the Japanese try to board and find spikes",          "footdeck","impact",     -9.0, ["impact"], True),
 (220.667, "ANGOLPO — fifty-nine ships",                         "boom",    "hero_boom",  -5.0, ["woodbreak"], False),
 (233.000, "\"World's First Ironclad\" — the claim arrives",     "whoosh",  "whoosh",    -12.0, None, True),
 (251.967, "VASA — sixty-four guns on two decks",                "boom",    "hero_boom",  -6.0, ["cannon"], False),
 (257.000, "under full sail, leaving Stockholm",                 "sail",    "impact",    -10.0, None, True),
 (275.680, "a gust catches her",                                 "gust",    "hero_hit",   -7.0, ["sail"], False),
 (276.190, "she heels and the open lower gunports go under",     "water",   "hero_boom",  -6.0, ["woodbreak", "creak"], False),
 (277.210, "gone, thirteen hundred metres from the quay",        "surge",   "hero_hit",   -9.0, ["bubbles"], False),
 # --- The Age of Sail ---------------------------------------------------
 (305.000, "gunpowder will detonate underwater",                 "uwexp",   "hero_boom",  -6.0, ["bubbles"], True),
 (317.000, "one propeller turned by hand",                       "winch",   "impact",    -10.0, None, True),
 (323.000, "water into the ballast tank, to sink",               "bubbles", "impact",    -10.0, ["water"], True),
 (348.470, "he starts drilling into the ship's bottom",          "winch",   "hero_hit",   -8.0, ["creak"], False),
 (351.900, "it will not bite",                                   "impact",  "hero_boom",  -6.0, None, False),
 (357.800, "an hour of his own exhaled air, in the dark",        "breath",  "impact",     -9.0, None, False),
 (362.900, "he releases the mine and pedals away",               "torpedo", "impact",     -9.0, ["bubbles"], False),
 (371.670, "it goes off in open water and hurts nobody",         "uwexp",   "hero_boom",  -7.0, ["surge"], True),
 (375.800, "the sloop carrying it goes down off Fort Lee",       "water",   "hero_hit",   -8.0, ["woodbreak"], True),
 # --- The Ironclad Age --------------------------------------------------
 (389.000, "NOVGOROD — a circle, a hundred and one feet across", "impact",  "hero_hit",   -7.0, ["water"], True),
 (401.000, "Elder's paper: a wider hull, thicker armour",        "paper",   "impact",    -12.0, None, True),
 (419.700, "the navy approves the drawings, December 1869",      "typewriter","impact",  -12.0, None, True),
 (425.000, "two and a half thousand tons on almost no draught",  "boom",    "hero_hit",   -8.0, ["water"], True),
 (431.000, "two eleven-inch guns in an open barbette",           "cannon",  "hero_boom",  -6.0, None, True),
 (443.000, "Fred T. Jane writes the story down",                 "quill",   "swish",     -14.0, None, True),
 (455.000, "firing her guns spins the whole ship — the story",   "cannon",  "hero_hit",   -8.0, ["surge"], False),
 (473.000, "slow, wet and awkward to steer — the record",        "creak",   "impact",    -11.0, ["water"], True),
 (485.000, "and they ordered a second one",                      "impact",  "hero_hit",   -8.0, ["water"], True),
 # --- World War I -------------------------------------------------------
 (497.000, "two steam funnels standing on a submarine's deck",   "steam",   "hero_hit",   -9.0, ["horn"], True),
 (503.000, "diving: shut down, fold the funnels, clamp them",    "alarm",   "hero_hit",   -8.0, ["hatch"], True),
 (521.000, "thirty separate openings, closed by hand",           "hatch",   "impact",     -9.0, ["chain"], True),
 (545.000, "the Grand Fleet sails from Rosyth into mist",        "horn",    "impact",    -12.0, ["surge"], True),
 (559.200, "K14 jams her helm and turns out of line",           "winch",   "impact",    -10.0, ["creak"], False),
 (561.000, "K22 hits her",                                       "impact",  "hero_hit",   -7.0, ["ramcrash", "water"], False),
 (563.670, "the cruiser Inflexible then hits K22",               "impact",  "hero_hit",   -7.0, ["ramcrash"], False),
 (573.900, "Fearless strikes K17 at near full speed, and cuts her open", "impact", "hero_boom", -5.0, ["ramcrash", "woodbreak"], False),
 (579.070, "K6 rams K4, and slices her nearly in half",          "impact",  "hero_hit",   -7.0, ["ramcrash", "water"], False),
 (584.070, "survivors from K17 in the water",                    "water",   "impact",    -11.0, ["bubbles"], False),
 (599.000, "a hundred and four men died",                        "boom",    "hero_boom",  -6.0, None, True),
 (605.000, "the transcripts go into a locked file for seventy years", "paper", "hero_hit", -10.0, ["lock"], True),
 # --- World War II ------------------------------------------------------
 (623.000, "SURCOUF — heavy-cruiser calibre on a submarine",     "boom",    "hero_boom",  -6.0, ["cannon"], True),
 (641.000, "ten torpedo tubes, six hundred rounds below",        "torpedo", "impact",     -9.0, None, True),
 (647.000, "the Besson floatplane, craned into the water",       "plane",   "impact",    -10.0, ["winch"], True),
 (653.000, "she surfaces and outguns the escort",                "cannon",  "hero_boom",  -6.0, ["water"], True),
 (659.440, "France fell in 1940",                                "boom",    "hero_boom",  -6.0, None, True),
 (690.220, "the freighter strikes something submerged",          "body",    "hero_boom",  -6.0, ["bubbles", "surge"], True),
 (707.500, "nobody has ever found her",                          "surge",   "hero_hit",  -10.0, ["bubbles"], True),
]

# ---------------------------------------------------------------- mutes
# A photograph is not an event. The redraw detector cannot tell a portrait
# sliding in from a hull being struck; both are large mid-band redraws.
MUTES = [
 [ 15.9,  17.6, "Hiero II — a painting, not something being hit"],
 [ 22.4,  24.0, "the Iliad mosaic sliding onto the temple floor"],
 [ 53.2,  56.2, "Hiero II again"],
 [299.8, 301.6, "David Bushnell — an engraving"],
 [343.0, 346.0, "Admiral Howe — a portrait"],
 [395.8, 397.4, "the Novgorod historical plate"],
 [626.6, 630.4, "the Napoleonic privateer — a painting"],
 [674.6, 676.6, "Capt. Blaison — a photograph"],
 [679.6, 681.2, "the Panama Canal — a photograph"],
]

# ---------------------------------------------------------------- assemble
cue = dict(AUTO)
ms = []
for i, (mid, a, b, en, why, track) in enumerate(SECTIONS):
    ms.append({"id": mid, "role": "intro" if i == 0 else ("outro" if i == len(SECTIONS)-1 else "body"),
               "start": round(a, 3), "end": round(b, 3), "dur": round(b - a, 3),
               "energy": en, "energy_label": why, "track": track,
               "under_voiceover": True, "duck_db": -9,
               "fade_in": 1.2 if i else 0.4, "fade_out": 1.2,
               "asset": os.path.abspath(f"assets/{mid}.wav"), "gain_db": 0.0})

sfx = []
for j, (t, label, cat, tier, gain, stack, do_snap) in enumerate(sorted(B), 1):
    at = snap(t) if do_snap else t
    sfx.append({"id": f"h{j}", "at": round(at, 3), "kind": label, "cat": cat,
                "tier": tier, "gain_db": gain, "stack": stack, "solo_ok": True,
                "moved_ms": round((at - t) * 1000)})

beds = []
for k, (a, b, src, target, why) in enumerate(BEDS, 1):
    beds.append({"id": f"b{k}", "hand": True, "at": round(a, 3), "dur": round(b - a, 3),
                 "gain_db": round(target - RMS[src], 2), "fade": 2.5, "why": why,
                 "asset": os.path.abspath(f"pal/{src}.wav")})

cue["music_sections"] = ms
cue["sfx_cues"] = sfx
cue["amb_beds"] = beds
cue["mute_windows"] = MUTES
json.dump(cue, open("cues_beats.json", "w"), indent=1)

moved = [s["moved_ms"] for s in sfx if s["moved_ms"]]
print(f"{len(ms)} music sections, one change per {718.171/len(ms):.1f}s")
print(f"{len(sfx)} hand-timed beats; {len(moved)} snapped to a picture change "
      f"(median {sorted(abs(m) for m in moved)[len(moved)//2]} ms)")
print(f"{len(beds)} hand-written beds, {len(MUTES)} mute windows")
for s in sfx:
    if abs(s["moved_ms"]) > 600:
        print(f"   NOTE {s['at']:8.3f}  moved {s['moved_ms']:+5d} ms  {s['kind']}")
