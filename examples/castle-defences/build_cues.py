#!/usr/bin/env python3
"""Build the hand-authored cue sheet for the castle-defences video.

Every time here was read off a contact sheet (sheets/s00-s10 at the detected
scene cuts, sheets/fine_A-H at 0.5-1.8 s over the eight action windows) or taken
from visual_redraw.py's event list. Section boundaries are the banner-text
changes measured in scan.py, cross-checked against the grid card the animation
uses as its section transition -- this channel has no white-and-red era card, so
cards.py finds nothing here and banner.py's failure mode does not apply.
"""
import json, os

PAL = json.load(open("pal/palette_manifest.json"))
RMS = PAL["_rms"]
EV  = [e["t"] for e in json.load(open("redraw.json"))["events"]]
AUTO = json.load(open("cues_auto.json"))
DUR = 739.167

def snap(t, win=1.2):
    """Land a hand beat on the picture change nearest to it."""
    near = [e for e in EV if abs(e - t) <= win]
    return min(near, key=lambda e: abs(e - t)) if near else t

# ---------------------------------------------------------------- sections
# The eight castle features are the banner sections; music changes twice or
# three times inside each, on the story's own turns. 19 cues over 12:19 is one
# change per 38.9 s (StickTory measures 47-48 s; the warships job shipped 42.2).
# Every track was MEASURED for rhythmic drive, not chosen by title: mus_measure.py
# scores onset density, pulse regularity and percussive fraction, because
# "floaty is a casting error, not a level problem". Two medieval-sounding
# candidates -- Arrival at Caelmere Keep (2.25) and The King's Return (2.10) --
# are ambient wash by that measure and were rejected on it.
#  id   start     end      energy  what the cue is under                       track
SECTIONS = [
 ("m1",   0.000,  45.167, 0.50, "Krak has never fallen; Baybars arrives; the corridor built to kill", "Merlin's Curse"),
 ("m2",  45.167,  65.000, 0.72, "he will not use the front door: siege engines, and a hole of his own", "In Front of the Fort"),
 ("m3",  65.000,  95.708, 0.44, "it fell to a con -- a forged letter and bad paperwork",              "Bug-A-Boo"),
 ("m4",  95.708, 137.900, 0.52, "Kenilworth: Evesham lost, the survivors behind a lake",              "Time Is Running Fast"),
 ("m5", 137.900, 172.160, 0.62, "the king tries everything: trebuchets into water, barges, a flame war","Half-Time Break"),
 ("m6", 172.160, 185.417, 0.30, "six months, and an empty larder",                                    "Coldfront"),
 ("m7", 185.417, 219.000, 0.66, "the portcullis of the movies, and why it is a lie",                   "Close Call"),
 ("m8", 219.000, 253.400, 0.48, "what it really was: a grill, a fire door, a very good door",          "A Path Well Trodden"),
 ("m9", 253.400, 305.320, 0.56, "Carcassonne: he owns the city and cannot reach the walls",            "Leviathan"),
 ("m10",305.320, 356.950, 0.68, "a storm of bolts out of slits the width of a hand",                   "Don't Come Closer"),
 ("m11",356.950, 386.400, 0.46, "King John needs forty of the fattest pigs",                           "Be Honest"),
 ("m12",386.400, 418.333, 0.70, "the mine, the props, the fire, and the corner of the keep",           "Controlled Collision"),
 ("m13",418.333, 455.740, 0.58, "a corner is a weakness; Rochester is rebuilt round",                  "Rise to the Power"),
 ("m14",455.740, 490.720, 0.64, "the bridge rises, the hero leaps -- and it is almost pure invention", "On the Brink of Glory"),
 ("m15",490.720, 535.330, 0.44, "a very large garage door whose finest hour was doing nothing",        "Alter Hero"),
 ("m16",535.330, 575.167, 0.66, "Dover: Louis lands and goes straight for the strongest point",        "Incendiary Treasures"),
 ("m17",575.167, 628.530, 0.78, "the tower comes down, and Hubert holds the breach by hand",           "Call to Arms"),
 ("m18",628.530, 686.240, 0.60, "Chateau Gaillard: ring inside ring, and a breach that kills you",     "Unite and Fight"),
 ("m19",686.240, 739.167, 0.42, "a winter siege, a toilet shaft, and an empire",                       "Ghosting"),
]

# ---------------------------------------------------------------- beds
# Hand-assigned, never rotated: a bed does not duck (only the music bus is
# sidechained), so rotation cannot know that a lake does not belong under a
# tunnel. The sword palette's two "Voices, Yells" ambiences were separated into
# `crowd` when the palette was rebuilt, so amb_01..05/08 carry no second voice;
# `crowd` is used only where men are visibly fighting, and kept at -38 dBFS.
# amb_05 was dropped too: its Epidemic title is not recoverable here (the sword
# job stored CDN ULIDs, a different id space from what search returns), so the
# six were tested instead -- pyin over the harmonic component, counting frames
# carrying a confident pitch in the human F0 range, calibrated against the two
# known "Voices, Yells" files. crowd_01/02 score 0.14/0.25 mean confidence and
# every other bed scores <=0.04. amb_05 scores 0.16.
#  start     end      file     rms dBFS  why
BEDS = [
 (  0.000,  45.167, "air_01",  -43, "dry air over the corridor and the gallery"),
 ( 45.167,  65.000, "amb_01",  -41, "Baybars' engines, and the assault through the breach"),
 ( 53.708,  61.000, "crowd_03",-38, "his men going in through the hole they made"),
 ( 65.000,  95.708, "amb_02",  -43, "the inner ward, waiting on a letter"),
 ( 95.708, 137.900, "lake_01", -41, "Kenilworth's water, all the way around the walls"),
 (103.120, 109.400, "crowd_07",-38, "Evesham"),
 (128.400, 137.900, "river_01",-40, "the streams dammed; the water coming up"),
 (137.900, 172.160, "lake_02", -41, "open water, and the army stuck on the shore"),
 (172.160, 185.417, "wind_02", -44, "six months; nothing left to eat"),
 (185.417, 219.000, "amb_03",  -42, "the gatehouse in daylight"),
 (219.000, 253.400, "amb_04",  -43, "the gate passage"),
 (253.400, 305.320, "air_02",  -42, "Carcassonne on its hill"),
 (305.320, 334.840, "air_04",  -41, "the open ground below a wall full of slots"),
 (334.840, 356.950, "air_03",  -43, "weeks of it, and then he rides away"),
 (356.950, 455.740, "amb_08",  -42, "England, and Rochester: forty pigs and a keep that will not fall"),
 # `fire.py` scores drawn flame area per frame: there is fire on screen from
 # 400.000 to 402.917, 2.92 s. This bed used to run 386.400-418.333 -- 31.9 s at
 # -37 dBFS, a FEATURED texture level -- so torch crackle played for 13.6 s
 # before anything was alight, and for 15.4 s after the corner had already come
 # down, over a diagram of a square tower. Reported as fire that "keeps
 # continuing and not stopping where necessary", and it was.
 (399.300, 404.200, "fire_01", -40, "the props alight under the corner: 2.9 s of flame on screen", 0.9),
 (455.740, 490.720, "river_01",-41, "the ditch under the bridge"),
 (490.720, 535.330, "amb_01",  -43, "a gate doing the least heroic job imaginable"),
 (535.330, 575.167, "amb_02",  -41, "Dover, and the French on the outer defences"),
 (575.167, 606.560, "amb_03",  -40, "the breach"),
 (588.583, 597.500, "crowd_08",-38, "hand to hand in the gap"),
 (606.560, 628.530, "amb_04",  -43, "the new passage, bent and dark"),
 (628.530, 686.240, "river_02",-41, "the Seine under the cliff"),
 (677.160, 684.500, "crowd_04",-38, "trapped in the yard between the rings"),
 (686.240, 714.120, "wind_04", -40, "winter, and a siege that grinds on"),
 (714.120, 739.167, "wind_02", -44, "empty walls"),
]

# ---------------------------------------------------------------- beats
# (time, label, cat, tier, gain_db, stack, snap-to-picture)
B = [
 # --- MURDER HOLES ------------------------------------------------------
 (  0.170, "the grid of eight defences",                          "whoosh", "whoosh",   -11.0, None, False),
 (  1.500, "KRAK DES CHEVALIERS -- never fallen, not to anyone",   "boom",   "hero_boom", -5.0, ["whoosh"], True),
 (  9.040, "\"Then, in 1271\"",                                    "pop",    "pop",      -17.0, None, True),
 ( 13.500, "Baybars works through the crusader castles like a list","parch", "impact",   -12.0, ["scrape"], True),
 ( 20.500, "Krak's interior: a stone corridor bent back on itself","scrape", "whoosh",   -12.0, None, True),
 ( 28.250, "the floor of the gallery is open, on purpose",         "armor",  "impact",   -10.0, ["clatter"], True),
 ( 33.190, "packed tight, with men above them",                    "draw",   "impact",   -11.0, None, True),
 ( 38.120, "not the boiling oil of the movies",                    "sizzle", "impact",   -13.0, ["pop"], True),
 ( 40.500, "but rock",                                             "stone",  "hero_hit",  -8.0, None, True),
 ( 41.600, "boiling water",                                        "pour",   "hero_hit",  -9.0, ["sizzle"], True),
 (  43.625, "and heated sand",                                      "sand",   "impact",   -10.0, None, False),
 ( 45.167, "MURDER HOLES -- the card",                             "boom",   "hero_boom", -5.0, ["firewh"], False),
 ( 46.292, "the card clears; Baybars at the gate",                 "whoosh", "whoosh",   -11.0, False and None or None, False),
 ( 48.958, "so he did not bother with the front door",             "pop",    "impact",   -12.0, None, True),
 ( 52.380, "weeks of siege engines against the wall",              "bigrock","impact",    -9.0, ["stone"], False),
 ( 53.708, "a fresh hole knocked through a tower",                 "rubble", "hero_boom", -5.0, ["wbreak", "bigrock"], False),
 ( 55.083, "and he sent his men in through that instead",          "armor",  "impact",    -9.0, ["clatter"], True),
 ( 58.917, "the garrison falls back into the inner castle",        "wgate",  "impact",    -9.0, ["chain"], True),
 ( 60.917, "he could not get them out of that either",             "impact", "impact",    -8.0, ["shield"], True),
 ( 62.792, "the inner gate, shut",                                 "wgate",  "hero_hit",  -8.0, ["lock"], True),
 ( 65.000, "the castle he could not storm fell to a con",          "boom",   "hero_boom", -6.0, None, True),
 ( 71.250, "a letter forged, dressed as an order from their own commander", "quill", "swish", -14.0, ["parch"], True),
 ( 75.000, "the fake memo, sealed",                                "parch",  "impact",   -12.0, ["lock"], True),
 ( 83.500, "they read it, believed it, and opened the gates",      "wgate",  "hero_hit",  -8.0, ["chain", "creak"], True),
 ( 85.240, "they had held off Saladin",                            "pop",    "impact",   -13.0, None, True),
 ( 90.250, "they could not hold off bad paperwork",                "pop",    "impact",   -12.0, None, True),
 ( 93.000, "nobody wanted to walk under them, not even Bybars",    "whoosh", "whoosh",   -12.0, None, True),
 # --- MOAT --------------------------------------------------------------
 ( 95.708, "the grid scrolls on",                                  "whoosh", "whoosh",   -10.0, None, False),
 ( 96.400, "MOAT",                                                 "boom",   "hero_boom", -5.0, ["splash"], False),
 (100.450, "Kenilworth, in the middle of its lake",                "splash", "impact",   -11.0, None, True),
 (101.660, "\"In 1265\"",                                          "pop",    "pop",      -17.0, None, True),
 (103.120, "the Battle of Evesham",                                "impact", "hero_hit",  -7.0, ["armor", "body"], True),
 (107.000, "Simon de Montfort killed",                             "body",   "hero_hit",  -8.0, ["vox_cry"], True),
 (109.830, "the survivors fall back to Kenilworth",                "wgate",  "impact",   -10.0, None, True),
 (112.990, "every demand to surrender, refused",                   "parch",  "impact",   -12.0, ["lock"], True),
 (117.490, "the king comes, and stays",                            "armor",  "impact",   -11.0, None, True),
 (118.990, "\"6 Months Later\"",                                   "pop",    "pop",      -16.0, None, True),
 (124.220, "its builders had dammed the local streams",            "scrape", "whoosh",   -12.0, None, True),
 (129.110, "into a great artificial mirror",                       "splash", "impact",   -10.0, ["pour"], True),
 (134.450, "no one could tunnel: everything underground was water","dig",    "hero_hit",  -9.0, ["splash"], True),
 (137.900, "the most powerful army in England, attacking a pond",  "boom",   "hero_boom", -6.0, None, True),
 (144.333, "the largest trebuchets in the kingdom",                "treb",   "hero_hit",  -8.0, ["rope"], True),
 (147.458, "the stone goes out over the lake",                     "whoosh", "whoosh",   -10.0, None, False),
 (149.750, "and mostly into it",                                   "splash", "hero_hit",  -8.0, ["stone"], True),
 (153.292, "barges dragged overland from Chester, at night",       "creak",  "impact",   -10.0, ["splash"], False),
 (155.333, "and the garrison drove them back",                     "arrow",  "hero_hit",  -8.0, ["arrowhit"], False),
 (158.000, "a cardinal excommunicates the rebels from a safe hill","parch",  "impact",   -12.0, None, True),
 (160.840, "so they dressed one of their own men in white",        "pop",    "impact",   -12.0, None, True),
 (166.350, "and excommunicated the king right back",               "parch",  "hero_hit",  -9.0, ["pop"], True),
 (172.160, "what finally took Kenilworth was an empty larder",     "boom",   "hero_boom", -6.0, None, True),
 (177.820, "hunger and disease did what the trebuchets could not", "creak",  "swish",    -15.0, None, True),
 (181.000, "the lake had held the whole time",                     "splash", "impact",   -12.0, None, True),
 # --- PORTCULLIS --------------------------------------------------------
 (185.417, "the grid scrolls on",                                  "whoosh", "whoosh",   -10.0, None, False),
 (186.100, "PORTCULLIS",                                           "boom",   "hero_boom", -5.0, ["portc"], False),
 (189.060, "the heroes sprint through the gate",                   "armor",  "impact",   -10.0, ["clatter"], True),
 (190.417, "THE IRON GRILL COMES CRASHING DOWN",                   "portc",  "hero_boom", -4.0, ["chain", "scrape"], False),
 (190.900, "and some slower soldier gets caught underneath",       "body",   "hero_hit",  -8.0, ["vox_cry"], False),
 (196.060, "the most dramatic door in history, on a red carpet",   "pop",    "impact",   -12.0, ["whoosh"], True),
 (200.900, "\"Reality\" -- it just sits there",                    "clatter","pop",      -17.0, None, True),
 (207.030, "no great massacre in the gatehouse anyone can name",   "boom",   "impact",   -12.0, None, True),
 (213.620, "most of the time it was lowered, being a really good door", "wgate", "impact", -11.0, None, True),
 (217.410, "\"PORTCULLIS MASSACRES! In Cinema Now\"",              "parch",  "impact",   -12.0, ["pop"], True),
 (219.000, "and that was the genius",                              "boom",   "hero_boom", -6.0, None, True),
 (220.660, "a grill, not a slab: defenders shoot out through the gaps", "bowrel", "hero_hit", -8.0, ["arrow"], True),
 (221.900, "while nothing gets in",                                "arrowhit","impact",   -9.0, None, True),
 (226.030, "it dropped faster than any hinged gate could swing",   "portc",  "hero_hit",  -7.0, ["scrape"], True),
 (228.530, "and it did not burn",                                  "firewh", "impact",   -11.0, None, True),
 (232.660, "the fire door of the medieval castle",                 "arrow",  "impact",   -10.0, ["arrowhit"], True),
 (239.070, "the famous killing version waited its whole career",   "chain",  "swish",    -14.0, None, True),
 (241.410, "most attackers went off to dig at the walls instead",  "pick",   "impact",   -10.0, ["dig"], True),
 (249.030, "the trap was real",                                    "portc",  "impact",    -9.0, ["chain"], True),
 (250.370, "it just never got the memo it was supposed to be scary","pop",   "pop",      -17.0, None, True),
 # --- ARROW LOOPS -------------------------------------------------------
 (253.400, "the grid scrolls on",                                  "whoosh", "whoosh",   -10.0, None, False),
 (254.100, "ARROW LOOPS",                                          "boom",   "hero_boom", -5.0, ["arrow"], False),
 (254.910, "Carcassonne, and an army that never reached the walls","whoosh", "whoosh",   -12.0, None, False),
 (257.780, "it should have been easy",                             "armor",  "impact",   -10.0, ["clatter"], True),
 (265.490, "the city his family had held for a century",           "wgate",  "impact",   -11.0, None, True),
 (270.910, "\"In 1240\"",                                          "pop",    "pop",      -17.0, None, True),
 (277.200, "he came back to claim it, with soldiers at his back",  "armor",  "impact",   -11.0, None, True),
 (285.070, "walls pierced top to bottom with narrow vertical slits","scrape","whoosh",   -12.0, None, True),
 (288.160, "inside, a wide alcove where a crossbowman stands in cover", "cbowtick", "hero_hit", -9.0, ["bowtick"], True),
 (290.600, "and sweeps the ground below",                          "bowrel", "hero_hit",  -7.0, ["arrow"], True),
 (297.530, "a one-way window with a crossbow behind it",           "arrowhit","impact",   -9.0, None, True),
 (301.490, "Attacker's POV / Defender's POV",                      "pop",    "impact",   -13.0, None, True),
 (305.320, "a wall full of slots, any one of which might be aimed at him", "boom", "hero_boom", -6.0, None, True),
 (310.620, "Trencavel had crossbowmen by the hundred",             "cbowtick","impact",  -10.0, None, True),
 (316.820, "des Ormes writes to the queen of France",              "quill",  "swish",    -14.0, ["parch"], True),
 (320.920, "nobody could step outside the walls without being hit","arrow",  "impact",    -9.0, ["arrowhit"], True),
 (325.910, "they shot from the slits while the attackers stood exposed", "bowrel", "hero_hit", -7.0, ["arrowhit", "body"], True),
 (329.320, "a handful of men behind arrow loops could hold a wall","cbowtick","impact",  -10.0, None, True),
 (334.990, "he besieged his own city for weeks",                   "armor",  "swish",    -14.0, None, True),
 (337.950, "and never broke in",                                   "whoosh", "swish",    -15.0, None, True),
 (344.350, "a hundred years of inheritance",                       "armor",  "impact",   -11.0, None, True),
 (349.780, "and a slit the width of his hand",                     "pop",    "impact",   -12.0, None, True),
 (355.660, "it was enough",                                        "boom",   "hero_hit", -10.0, None, True),
 # --- ROUND TOWERS ------------------------------------------------------
 (356.950, "the grid scrolls on",                                  "whoosh", "whoosh",   -10.0, None, False),
 (357.700, "ROUND TOWERS",                                         "boom",   "hero_boom", -5.0, ["pig"], False),
 (359.950, "not to eat",                                           "pop",    "impact",   -12.0, ["pig"], True),
 (364.580, "forty of the fattest pigs, day and night, with all speed", "pig", "hero_hit", -8.0, None, False),
 (370.120, "the order goes out to Rochester",                      "parch",  "impact",   -12.0, None, True),
 (372.660, "forty of them",                                        "pig",    "hero_hit",  -9.0, None, True),
 (381.910, "the keep, one of the tallest in England",              "boom",   "hero_hit",  -9.0, None, True),
 (386.400, "weeks of stone throwers, with nothing to show",        "bigrock","impact",    -9.0, ["stone"], True),
 (388.200, "the stone hits, and the tower does not care",          "bigrock","hero_hit",  -8.0, None, True),
 (392.120, "so he stopped throwing stones and started digging under it", "dig", "hero_hit", -8.0, ["pick"], True),
 (396.290, "propping the tunnel with timber as they went",         "wbreak", "impact",   -10.0, ["dig"], True),
 (400.000, "they pack the props with the fattest of the forty, and set it alight", "ignite", "hero_boom", -6.0, ["pig"], False),
 (402.583, "the fire eats through the wood",                       "wbreak", "hero_hit",  -7.0, None, False),
 (405.833, "THE ENTIRE CORNER OF THE GREAT KEEP COMES DOWN",       "rubble", "hero_boom", -4.0, ["bigrock", "stone"], False),
 (410.708, "a square tower has corners",                           "pop",    "pop",      -17.0, None, True),
 (411.500, "and a corner is a weakness",                           "pop",    "pop",      -14.0, None, False),
 (415.375, "the one place a miner can dig out from two sides at once", "pick", "impact",  -11.0, None, True),
 (418.333, "so it was not rebuilt square",                         "boom",   "hero_boom", -6.0, None, True),
 (424.700, "it was rebuilt round",                                 "whoosh", "whoosh",   -11.0, ["scrape"], True),
 (429.330, "a round tower shrugs off blows that would shatter an angle", "bigrock", "hero_hit", -8.0, ["stone"], True),
 (434.870, "the shape of the serious castle",                      "rubble", "impact",   -10.0, None, True),
 (440.900, "they pulled back behind a wall inside the keep",       "wgate",  "impact",   -10.0, ["lock"], True),
 (447.820, "what a few dozen pigs had done once",                  "pig",    "swish",    -14.0, None, True),
 # --- DRAWBRIDGE --------------------------------------------------------
 (455.740, "the grid scrolls on",                                  "whoosh", "whoosh",   -10.0, None, False),
 (456.500, "DRAWBRIDGE",                                           "boom",   "hero_boom", -5.0, ["chain"], False),
 (457.410, "the bridge is rising",                                 "chain",  "hero_hit",  -8.0, ["creak", "rope"], False),
 (458.333, "the hero makes the leap",                              "whoosh", "whoosh",   -11.0, False and None or None, False),
 (459.750, "the men chasing him do not",                           "vox_cry","hero_hit",  -8.0, None, False),
 (461.542, "and drop into the moat below",                         "splash", "hero_boom", -6.0, ["body"], False),
 (463.625, "the best three seconds in any castle film",            "armor",  "impact",   -10.0, None, False),
 (466.583, "\"HERO MOVIE\"",                                       "pop",    "impact",   -12.0, ["whoosh"], True),
 (474.410, "what it actually was: a wooden bridge over a ditch",   "wgate",  "impact",   -11.0, None, True),
 (479.900, "hauled up on chains, and the crossing vanishes",       "chain",  "hero_hit",  -8.0, ["winch"], True),
 (486.280, "no army was destroyed because a bridge went up at the right second", "boom", "hero_hit", -10.0, None, True),
 (490.720, "the least heroic job imaginable",                      "boom",   "hero_boom", -6.0, None, True),
 (494.370, "down in the morning, to let the millers' carts in",    "creak",  "impact",   -10.0, ["wgate"], True),
 (496.370, "up at night, to keep everyone out",                    "winch",  "impact",   -10.0, ["chain"], True),
 (498.200, "raised, it swings flush against the gate and becomes the wall", "wgate", "hero_boom", -6.0, ["lock", "scrape"], True),
 (508.460, "no footing left below to bring a ram up at all",       "rammer", "hero_hit",  -8.0, ["wbreak"], True),
 (514.030, "the man in the moat, still there",                     "splash", "swish",    -14.0, True and None or None, True),
 (517.530, "it could make the way in simply stop existing",        "boom",   "hero_hit",  -9.0, None, True),
 (527.030, "the real drawbridge spent its career letting the groceries through", "creak", "impact", -11.0, None, True),
 (532.950, "its finest hour was doing nothing at all",             "chain",  "swish",    -15.0, None, True),
 # --- GATEHOUSE ---------------------------------------------------------
 (535.330, "the grid scrolls on",                                  "whoosh", "whoosh",   -10.0, None, False),
 (536.100, "GATEHOUSE",                                            "boom",   "hero_boom", -5.0, ["wgate"], False),
 (536.580, "the shortest crossing from the continent",             "parch",  "impact",   -12.0, None, True),
 (542.910, "whoever held it held the door to the entire country",  "boom",   "hero_hit",  -9.0, None, True),
 (547.500, "\"In 1216\"",                                          "pop",    "pop",      -17.0, None, True),
 (552.990, "Louis lands and marches straight for it",              "armor",  "impact",    -9.0, ["clatter"], True),
 (558.410, "the Great North Gatehouse -- the strongest point in the castle", "boom", "hero_hit", -8.0, ["wgate"], True),
 (563.450, "that sounds backwards",                                "pop",    "pop",      -17.0, None, True),
 (569.240, "his miners tunnel under a gate tower",                 "dig",    "hero_hit",  -8.0, ["pick"], False),
 (572.667, "and burn away the props holding it up",                "firewh", "hero_hit",  -7.0, ["wbreak"], False),
 (575.167, "THE TOWER CRACKS AND COMES DOWN",                      "rubble", "hero_boom", -4.0, ["bigrock", "stone"], False),
 (578.120, "a hole opens straight into Dover",                     "whoosh", "whoosh",   -10.0, True and None or None, True),
 (579.333, "French soldiers pour through the gap",                 "armor",  "impact",    -8.0, ["shield"], False),
 (581.375, "\"This is the moment Dover should have fallen\"",      "boom",   "hero_boom", -5.0, ["firewh"], False),
 (583.958, "the card clears",                                      "whoosh", "whoosh",   -11.0, None, False),
 (585.100, "a knight named Hubert de Burgh",                       "draw",   "impact",   -10.0, None, False),
 (588.583, "the garrison meets them in the breach",                "impact", "hero_hit",  -7.0, ["shield", "armor"], False),
 (589.958, "and fights them back out by hand",                     "stab",   "hero_hit",  -8.0, ["body"], False),
 (591.292, "they jam the gap shut with timber torn from their own castle", "wbreak", "hero_hit", -8.0, ["rammer"], False),
 (593.458, "he had broken the gate of Dover, and still could not get through it", "boom", "hero_boom", -6.0, None, False),
 (595.458, "the breach, sealed",                                   "stone",  "impact",   -10.0, ["rubble"], False),
 (597.292, "the near-miss terrified the English",                  "armor",  "impact",   -11.0, None, False),
 (606.560, "they bricked the North Gate into a solid block of stone", "stone","hero_boom", -6.0, ["scrape"], True),
 (609.910, "a passage that bent so no ram could charge it",         "scrape", "whoosh",   -12.0, None, True),
 (612.580, "running beneath holes for dropping things on whoever stood below", "stone", "hero_hit", -8.0, ["pour"], False),
 (618.330, "and sealed with grill after grill",                    "portc",  "impact",    -8.0, ["chain"], True),
 (621.830, "the most overbuilt door in the building",              "boom",   "hero_hit",  -9.0, None, True),
 (624.030, "somewhere, once, someone had almost lost a kingdom through a simple one", "wgate", "impact", -11.0, None, True),
 # --- CONCENTRIC WALLS --------------------------------------------------
 (628.530, "the grid scrolls on",                                  "whoosh", "whoosh",   -10.0, None, False),
 (629.300, "CONCENTRIC WALLS",                                     "boom",   "hero_boom", -5.0, ["stone"], False),
 (638.280, "Normandy -- England's lands in France",                "parch",  "impact",   -12.0, None, True),
 (645.660, "a cliff above the river Seine",                        "whoosh", "whoosh",   -12.0, None, True),
 (648.160, "wrapped in ring after ring of wall",                   "scrape", "hero_hit",  -9.0, ["stone"], True),
 (653.440, "his fair one-year-old daughter",                       "pop",    "impact",   -13.0, None, True),
 (656.120, "he was certain no one could ever take it",             "thunder","hero_boom", -8.0, None, True),
 (665.330, "break through the outer wall",                         "rubble", "hero_hit",  -7.0, ["stone"], True),
 (670.790, "and an attacker did not find the castle",              "armor",  "impact",   -11.0, None, True),
 (677.160, "he found a narrow yard, with defenders firing down from both sides", "arrow", "hero_hit", -7.0, ["arrowhit"], True),
 (683.990, "a breach did not get him in -- it got him killed",     "boom",   "hero_boom", -5.0, ["body"], True),
 (686.240, "so Philip did not try to smash straight through",      "armor",  "impact",   -10.0, None, True),
 (688.740, "a siege that ground on through the winter",            "creak",  "swish",    -14.0, None, True),
 (689.780, "his miners brought down part of the outer wall",       "pick",   "hero_hit",  -8.0, ["rubble"], False),
 (691.120, "and the inner rings held exactly as Richard had built them", "stone", "impact", -10.0, True and None or None, True),
 (696.620, "then a handful of them found the one thing the design had not accounted for", "pop", "impact", -12.0, None, True),
 (701.250, "a toilet shaft, from a chapel down to the outside of the wall", "scrape", "hero_hit", -9.0, None, False),
 (703.125, "outside, and inside the castle",                       "pop",    "pop",      -16.0, None, False),
 (706.833, "they climbed up it",                                   "creak",  "hero_hit",  -9.0, ["scrape"], False),
 (708.292, "came out inside, and threw the way open",              "wgate",  "hero_boom", -6.0, ["lock"], False),
 (710.042, "the winter camp, waiting",                             "armor",  "swish",    -14.0, None, False),
 (714.120, "the garrison surrendered",                             "wgate",  "hero_hit",  -9.0, ["chain"], True),
 (715.490, "the castle Richard swore could never fall",            "boom",   "hero_boom", -5.0, None, True),
 (719.830, "within months he had taken Rouen and the rest of it",  "parch",  "impact",   -12.0, None, True),
 (722.830, "rings of wall no army could break, and every one of them held", "stone", "impact", -11.0, None, True),
 (728.670, "it made no difference",                                "boom",   "hero_boom", -6.0, ["scrape"], True),
 (735.410, "lost through a hole built for going to the toilet",    "stone",  "hero_hit", -10.0, None, False),
]

# ---------------------------------------------------------------- mutes
# A photograph is not an event, and neither is a map. The redraw detector cannot
# tell a portrait sliding in from a tower being struck -- both are large mid-band
# redraws -- so there is no quieter sound that is right; the beat should be
# silent. Hand-timed beats pass through a mute window, so a designed cue inside
# one still sounds.
MUTES = [
 [254.40, 257.00, "the Carcassonne plate -- an illustration sliding in"],
 [263.60, 266.20, "Raymond Roger Trencavel -- a photograph of a statue"],
 [294.90, 297.40, "the arrow-loop photographs, outside and inside"],
 [313.00, 316.20, "Guillaume des Ormes -- a painting"],
 [354.80, 356.40, "the Carcassonne plate again"],
 [357.85, 360.10, "King John -- a tomb effigy"],
 [536.20, 538.60, "the English Channel -- a map"],
 [585.90, 588.30, "Hubert de Burgh -- stained glass"],
 [629.90, 632.60, "Richard the Lionheart -- a painting"],
 [637.80, 640.20, "Normandy -- a map"],
 [719.30, 721.60, "Rouen and Chateau Gaillard -- a map"],
]

# ---------------------------------------------------------------- assemble
cue = dict(AUTO)
# No programme target. The VO arrives mastered at -14.5 LUFS and a programme
# target moves it: the mix is summed at unity and limited, so the voice comes
# out exactly as it went in and programme loudness is an output.
cue["loudness_target_lufs"] = None
cue["true_peak_ceiling_dbtp"] = -1.0

ms = []
for i, (mid, a, b, en, why, track) in enumerate(SECTIONS):
    ms.append({"id": mid, "role": "intro" if i == 0 else ("outro" if i == len(SECTIONS)-1 else "body"),
               "start": round(a, 3), "end": round(b, 3), "dur": round(b - a, 3),
               "energy": en, "energy_label": why, "track": track,
               "under_voiceover": True, "duck_db": -9,
               "fade_in": 1.2 if i else 0.4, "fade_out": 1.2,
               "asset": os.path.abspath(f"assets/{mid}.wav"), "gain_db": 0.0})

sfx = []
for j, t in enumerate(sorted(B), 1):
    at0, label, cat, tier, gain, stack, do_snap = t
    at = snap(at0) if do_snap else at0
    sfx.append({"id": f"h{j}", "at": round(at, 3), "kind": label, "cat": cat,
                "tier": tier, "gain_db": gain, "stack": stack, "solo_ok": True,
                "moved_ms": round((at - at0) * 1000)})

beds = []
for k, bed in enumerate(BEDS, 1):
    a, b, src, target, why = bed[:5]
    fade = bed[5] if len(bed) > 5 else 2.5   # a 5 s bed cannot carry a 2.5 s fade
    beds.append({"id": f"b{k}", "hand": True, "at": round(a, 3), "dur": round(b - a, 3),
                 "gain_db": round(target - RMS[src], 2), "fade": fade, "why": why,
                 "rms_target_dbfs": target, "asset": os.path.abspath(f"pal/{src}.wav")})

cue["music_sections"] = ms
cue["sfx_cues"] = sfx
cue["amb_beds"] = beds
cue["mute_windows"] = MUTES
# What a generic strike weighs in THIS video. The default is four flesh punches,
# which is the wrong object under stone, timber and iron and -- with 125 generic
# strikes here -- played each of them 31 times, three times over the reuse rule.
# Rock, ram and masonry carry the weight; the flesh files stay in the pool
# because men do get hit, and stay available to hand beats that ask for "body".
cue["default_weight_cats"] = ["weight"]
json.dump(cue, open("cues_beats.json", "w"), indent=1)

moved = [s["moved_ms"] for s in sfx if s["moved_ms"]]
print(f"{len(ms)} music sections, one change per {DUR/len(ms):.1f}s")
print(f"{len(sfx)} hand-timed beats; {len(moved)} snapped to a picture change "
      f"(median {sorted(abs(m) for m in moved)[len(moved)//2]} ms)")
print(f"{len(beds)} hand-written beds, {len(MUTES)} mute windows")
for s in sfx:
    if abs(s["moved_ms"]) > 600:
        print(f"   NOTE {s['at']:8.3f}  moved {s['moved_ms']:+5d} ms  {s['kind']}")
# two hand beats inside 300 ms read as one doubled hit
prev = None
for s in sfx:
    if prev and s["at"] - prev["at"] < 0.30:
        print(f"   NOTE {prev['at']:8.3f} + {s['at']:.3f} are "
              f"{(s['at']-prev['at'])*1000:.0f} ms apart: {prev['kind']} / {s['kind']}")
    prev = s
