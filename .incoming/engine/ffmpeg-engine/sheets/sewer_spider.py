"""EDIT SHEET — one section. This is the only file that changes per video.
Times are authored against the VO word-timing map (assets/work/words.json) + VO_OFFSET."""
VO_OFFSET = 0.7
DURATION  = 62.6

TITLE = "The Sewer Spider"

# --- BACKGROUND PLATE REGISTRY -------------------------------------------
# The M-Simplified-leaning rebuild composites scenes from ONE background plate
# plus cutout layers, and REUSES a background across consecutive beats (slot 10
# carries the hero manhole and the 34.4s return; slot 17 carries the road sign
# both by day and, red-tinted, at night). Shots reference these slots by number.
# remotion/src/sheet.ts mirrors this list — keep them in step.
PLATES = [
 (1,  "sewer access ladder, torchlight down a service shaft", 0.58),
 (2,  "flooded storm tunnel, standing water, distant light",   0.62),
 (3,  "tunnel mouth at street level, two workers in hi-vis",   0.58),
 (4,  "supervisor's face half lit, the laugh stopping",        0.68),
 (5,  "dark water surface, something long underneath",         0.58),
 (6,  "black tunnel throat, the pipe going deep",              0.56),
 (7,  "scanned forum post, monospaced text block",             0.72),
 (8,  "city works ID badge and a paper shift log",             0.70),
 (9,  "tunnel branch, three dark mouths",                      0.58),
 (10, "HERO: open manhole at night, wet asphalt",              0.62),
 (11, "archive record with the name field left blank",         0.72),
 (12, "forum thread, replies naming the creature",             0.50),
 (13, "the original post, one word highlighted",               0.66),
 (14, "macro on the word: spiders",                            0.62),
 (15, "wide: three manholes on one street, all open",          0.58),
 (16, "empty street at night, POV crossing away",              0.58),
 (17, "municipal ROAD CLOSED sign, routine maintenance",       0.82),
]

# --- CUTOUT REGISTRY (engine/cutouts.py) ----------------------------------
CUTOUTS = ["creature_tall", "creature_small", "car", "treeline", "manhole_rim", "figure"]

CARDS = [{"t0": 0.0, "t1": 2.3, "desc": "creature card, sewer spider"}]

SHOTS = [
 (2.3, 5.2, "sewer access ladder, torchlight down a service shaft", "in"),
 (5.2, 8.0, "flooded storm tunnel, standing water, distant light", "pan"),
 (8.0,10.6, "two city workers in hi-vis at a tunnel mouth", "out"),
 (10.6,12.0,"supervisor's face half lit, the laugh stopping", "in"),
 (12.0,14.2,"alligator silhouette under dark water", "pan"),
 (14.2,17.0,"black tunnel, something long folding out of frame", "in"),
 (17.0,19.3,"scanned forum post, monospaced text block", "pan"),
 (19.3,21.8,"city works ID badge and a paper shift log", "in"),
 (21.8,24.6,"tunnel branch, three dark mouths", "out"),
 (24.6,28.5,"HERO: open manhole at night, four glossy white legs rising", "in"),
 (28.5,31.2,"scale comparison, one leg against a standing man", "pan"),
 (31.2,34.4,"close on a leg joint, three bends, fine spikes", "in"),
 (34.4,37.2,"the manhole mouth, everything below it black", "out"),
 (37.2,40.3,"archive record with the name field left blank", "pan"),
 (40.3,42.7,"forum thread, replies naming the creature", "in"),
 (42.7,45.1,"the original post, one word highlighted", "pan"),
 (45.1,47.6,"macro on the word: spiders", "in"),
 (47.6,49.2,"wide: three manholes on one street, all open", "out"),
 (49.2,52.6,"storm drain grate at street level, night", "in"),
 (52.6,55.4,"manhole cover leaning on a kerb, no crew", "pan"),
 (55.4,57.9,"empty street, POV crossing away from the drain", "out"),
 (57.9,60.3,"municipal ROAD CLOSED sign, routine maintenance", "in"),
 (60.3,62.6,"the same sign at night, the cover already off", "in"),
]

# text, t0, dur, where(band|on), accent(red), size
POPS = [
 ("Not alligators",   12.05, 1.95, "band", False, 58),
 ("Spiders",          14.20, 2.40, "on",   True,  104),
 ("Former city worker",19.60, 2.10, "band", False, 56),
 ("4 legs",           25.95, 2.00, "on",   True,  92),
 ("3 joints",         31.65, 2.10, "on",   True,  92),
 ("Body never seen",  35.90, 2.00, "band", False, 58),
 ("Name: fan-coined", 40.80, 2.00, "band", False, 56),
 ("Plural",           47.90, 1.90, "on",   True,  104),
 ("No open manholes", 52.10, 2.20, "band", True,  58),
]

ICONS = [
 ("redx",   12.30, 14.10,  960, 600, 300),
 ("person", 29.30, 31.10,  560, 700, 260),
 ("arrow",  32.00, 34.20, 1250, 560, 240),
 ("warn",   49.80, 52.40, 1520, 400, 200),
]

SHAKES   = [(14.25, 0.34, 18), (25.95, 0.38, 22), (47.95, 0.32, 20)]
GLITCHES = [(14.20, 0.28, 18), (47.90, 0.22, 14), (60.50, 0.20, 10)]

# file, time, gain_db
SFX = [
 ("lowhit", 14.20, -1), ("glitch", 14.20, -13),
 ("camera", 25.30, -11),
 ("boom",   25.95,  0),
 ("lowhit", 47.90, -1), ("glitch", 47.90, -14),
 ("glitch", 60.50, -15),
 ("boom",    0.10, -10),
]
