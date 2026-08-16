#!/usr/bin/env python3
"""Turn a script into SCENES WITH EVENTS, which is what the reference actually cuts.

This replaces the shot-count generator, and the reason is a measurement that
came out the opposite way round from the assumption everything was built on.

Assumed, never measured: "the reference cuts about every 2.6 seconds, so target
shot count." Measured by frame differencing at 10 fps over 130 seconds:

                        reference     the generated cut
  hard cuts per minute     15.2            18.4
  mean gap between cuts    3.99 s          3.05 s
  longest single hold     23.1 s           6.1 s

He cuts LESS. His best sequence is eleven seconds in ONE framing with zero text
on screen, and everything that changes in it happens inside the shot: a monitor
turns on, static resolves into scan bars, the creature appears inside the
screen, the image duplicates. Reproducing his motion statistic by cutting
twenty-six times is what made the output read as a machine.

That also settles an apparent conflict with the house rule "maximum 4.0 seconds
on one unchanged frame". The rule is about an unchanged FRAME, not an unchanged
framing. A twenty-second hold obeys it as long as something happens every few
seconds inside it. Cutting to satisfy the rule was the mistake.

SO THE UNIT IS A SCENE. A scene owns a ground (a plate, the white canvas, or
the roster) and holds it. Inside it, each narration line's things arrive as
events: a boxed insert appears, an icon pops, the creature is revealed. A new
scene starts only when the ground genuinely has to change.

  build_scenes.py <plan.json> --words words.json --illus DIR --assets DIR \\
                  --creature "Long Horse" --vo vo.wav --out sheet.json

Timing comes from WORD ANCHORS. Every event records the spoken word it belongs
to, and the seconds are resolved from the VO's own word timings, so a
re-recorded voiceover re-syncs the entire edit instead of invalidating it.
"""
import argparse, json, os, re, sys


# ---------------------------------------------------------------- anchoring

def norm(w):
    return re.sub(r"[^a-z0-9]", "", w.lower())


def anchor_lines(lines, words):
    """Walk the word stream once, matching each line to its span.

    A single forward pass, never a search: the same word appears many times in
    a script ("it", "the neck") and any matcher that looks for a word rather
    than walking past it will bind a late line to an early occurrence and shear
    the whole edit.
    """
    stream = [norm(w["w"]) for w in words]
    out, i = [], 0
    for line in lines:
        toks = [norm(t) for t in line.split() if norm(t)]
        if not toks:
            continue
        start = i
        # find the first token from here
        while start < len(stream) and stream[start] != toks[0]:
            start += 1
        if start >= len(stream):
            start = min(i, len(stream) - 1)
        end = min(start + len(toks), len(stream)) - 1
        out.append({"line": line, "i0": start, "i1": max(start, end),
                    "t0": words[start]["s"], "t1": words[max(start, end)]["e"],
                    "words": toks})
        i = end + 1
    return out


def word_time(span, words, token, fallback):
    """Seconds at which a given word inside a line is spoken."""
    t = norm(token)
    for k in range(span["i0"], min(span["i1"] + 1, len(words))):
        if norm(words[k]["w"]) == t:
            return words[k]["s"]
    return fallback


# ---------------------------------------------------------------- assets

def load_illus(d):
    """query -> [approved files], best relevance first.

    APPROVED ONLY, and an unreviewed image counts as unapproved. Every gate in
    the sourcing stage answers "is this a picture of the thing"; none of them
    answers "is this the right picture". A bright purple front door with a
    letterbox passed every automatic check and was picked as the ground for the
    section's biggest reveal, which is exactly the class of failure the review
    pass exists to catch.
    """
    p = os.path.join(d, "illustrations.json")
    if not os.path.exists(p):
        return {}
    doc = json.load(open(p))
    if "reviewed" not in doc:
        print(f"WARNING: {p} has not been reviewed - no illustrations will be "
              f"placed. Run: illustrate.py approve {d} --reject ...",
              file=sys.stderr)
    by = {}
    for r in doc["images"]:
        if not r.get("approved"):
            continue
        by.setdefault(r["query"], []).append(r)
    for q in by:
        by[q].sort(key=lambda r: -r.get("relevance", 0))
    return by


def fit_scale(path, max_w=0.66, max_h=0.46):
    """CSS scale that renders a cutout at a sensible SIZE in the frame.

    The sheet used to carry a raw scale, which silently assumed every cutout
    was about the same pixel size. They are not: one of this creature's cutouts
    is a 2000px wide panorama of a neck and another is a tall head. At a fixed
    scale of 1.0 the panorama filled the top half of the frame for twenty-three
    seconds and stopped reading as a horse skull at all - it was just a beige
    mass with the title lying across it.

    So the size is expressed as a fraction of the FRAME and the scale is
    derived from the image's own dimensions. Constrained on both axes, because
    a wide cutout must not overflow the sides and a tall one must not overflow
    the top.
    """
    try:
        from PIL import Image
        with Image.open(path) as im:
            w, h = im.size
    except Exception:
        return 0.62
    return round(min(max_w * 1920.0 / w, max_h * 1080.0 / h), 3)


def load_canon(assets_dir, plates_dir=None):
    """The approved creature art, split by what it is FOR.

    cut-*  are cutouts that composite onto a plate. art-*/plate-* are full
    photographs. A section that reuses one cutout at one angle is what made the
    first attempt read as a sticker, so the caller rotates through these.
    """
    f = sorted(os.listdir(assets_dir)) if os.path.isdir(assets_dir) else []
    # The grounds come from the CREATURE-FREE plate set, never from art-*.jpg.
    # A canon photograph contains the creature by definition, so compositing a
    # cutout onto one puts two of the same monster in frame and the reveal
    # reveals nothing. That shipped once and it is what made the first render
    # read as amateur.
    plates = []
    if plates_dir and os.path.isdir(plates_dir):
        plates = ["../plates/" + x for x in sorted(os.listdir(plates_dir))
                  if x.startswith("plate-") and x.endswith((".jpg", ".png"))]
    return {"cutouts": [x for x in f if x.startswith("cut-") and x.endswith(".png")],
            "plates": plates}


# ---------------------------------------------------------------- scenes

# Where boxes go. One box centred; two side by side; three across. Measured
# off the reference's 2-up: the pair sits above centre with a clear band under
# it, because that band is where the keyword pop lands.
SLOTS = {1: [(0.50, 0.46, 0.44)],
         2: [(0.28, 0.46, 0.34), (0.72, 0.46, 0.34)],
         3: [(0.22, 0.44, 0.27), (0.50, 0.44, 0.27), (0.78, 0.44, 0.27)]}


def build_scenes(spans, plan, illus, canon, max_gap=4.0):
    """Group lines into scenes, then fill each scene with events.

    A new scene is started only by a genuine change of ground: a different
    place, a switch to the white canvas, or the roster. Lines that name only
    objects or the creature stay in the scene they are in and add events to it,
    which is how a framing survives long enough to be held.
    """
    scenes = []
    cur = None
    cut_i = 0

    for span, row in zip(spans, plan):
        things = row["things"]
        plate_things = [t for t in things if t.get("role") == "plate"
                        and t["kind"] == "photo" and illus.get(t["query"])]
        wants_roster = any(t["kind"] == "roster" for t in things)
        # Only the FIRST place becomes the ground. A line that names more than
        # one place gets the rest as boxes, which is precisely the reference's
        # move on "a locked room or miles of empty road": two boxed images, not
        # a cut between two locations. Dropping them instead left one sentence
        # holding 23 seconds on 2 events.
        inserts = [t for t in things if t.get("role") == "insert"
                   and t["kind"] == "photo" and illus.get(t["query"])]
        inserts += plate_things[1:]
        canon_things = [t for t in things if t["kind"] == "canon"]
        icons = [t for t in things if t["kind"] == "icon"]

        # what ground would this line like to be on?
        if wants_roster:
            ground = "roster"
        elif plate_things:
            ground = "illus:" + illus[plate_things[0]["query"]][0]["file"]
        elif inserts and not canon_things:
            # objects with no place to put them: the canvas, which is what the
            # canvas is FOR - the reference goes white for exactly this beat.
            ground = "white"
        else:
            ground = None            # no opinion: stay where we are

        if cur is None or (ground and ground != cur["ground"]):
            if cur:
                cur["t1"] = span["t0"]
            cur = {"ground": ground or "creature", "t0": span["t0"],
                   "t1": span["t1"], "lines": [], "events": []}
            scenes.append(cur)
            # a scene that shows the creature picks a cutout it has not used
            if cur["ground"] == "creature" and canon["cutouts"]:
                cur["asset"] = canon["cutouts"][cut_i % len(canon["cutouts"])]
                cut_i += 1
        cur["t1"] = span["t1"]
        cur["lines"].append(span["line"])

        # ---- events inside the scene, each anchored to its spoken word
        # Boxes arrive in waves of at most three. A line naming five things
        # gets 3 + 2, not five boxes crammed across the frame - "too much is
        # going on and texts are overlapping" was the note that killed a cut.
        for base in range(0, min(6, len(inserts)), 3):
            wave = inserts[base:base + 3]
            slot_n = len(wave)
            for k, t in enumerate(wave):
                rec = illus[t["query"]][0]
                x, y, w = SLOTS[slot_n][k]
                at = word_time(span, WORDS, t["noun"], span["t0"] + 0.15 * k)
                cur["events"].append({
                    "type": "insert", "at": round(at, 3), "word": t["noun"],
                    "src": rec["file"], "x": x, "y": y, "w": w,
                    "wave": base // 3,
                    "tilt": (-2.5 if k == 0 else 2.5) if slot_n == 2 else 0})

        for t in canon_things:
            if not canon["cutouts"]:
                continue
            at = word_time(span, WORDS, t["noun"], span["t0"])
            cur["events"].append({
                "type": "reveal", "at": round(at, 3), "word": t["noun"],
                "src": canon["cutouts"][cut_i % len(canon["cutouts"])]})
            cut_i += 1
        # A section that shows one cutout at one angle reads as a sticker. The
        # reference gets roughly ten treatments out of a single artwork, so
        # when a line names several creature parts each one is a separate
        # layer arriving on its own word.

        for t in icons:
            at = word_time(span, WORDS, t["noun"], span["t0"])
            cur["events"].append({"type": "icon", "kind": t.get("icon", "figure"),
                                  "at": round(at, 3), "word": t["noun"]})

    fill_dead_air(scenes, max_gap)
    return scenes


def fill_dead_air(scenes, max_gap=4.0):
    """No stretch of a scene may sit unchanged longer than the house limit.

    This is where the two measurements are reconciled. The house rule caps an
    unchanged FRAME at 4.0 seconds. The reference holds a FRAMING for 23. Both
    hold at once only if something happens inside the framing every few
    seconds, so any gap longer than the cap gets a punch: a hard cut to a
    tighter crop of the same plate. The location does not change, the frame
    does, and cuts per minute rise for an honest reason rather than because a
    generator was told to hit a number.
    """
    for sc in scenes:
        marks = sorted([sc["t0"]] + [e["at"] for e in sc["events"]] + [sc["t1"]])
        for a, b in zip(marks, marks[1:]):
            gap = b - a
            if gap <= max_gap:
                continue
            n = int(gap // max_gap)
            for k in range(1, n + 1):
                at = a + gap * k / (n + 1)
                if at >= sc["t1"] - 0.35:
                    continue
                sc["events"].append({"type": "punch", "at": round(at, 3),
                                     "word": None})
        sc["events"].sort(key=lambda e: e["at"])


# ---------------------------------------------------------------- pops

# The reference ran eleven seconds with no text but the persistent title. The
# generated cut fired 12 pops in 62 seconds, one every 5.2s, and the owner's
# word for it was "too much is going on". Pops are punctuation.
POP_MIN_GAP = 7.0
# Generic nouns are not keywords. "CREATURE" under a video whose title is the
# creature's name adds nothing, and a pop that adds nothing is the density that
# got a cut called "too much is going on".
POP_GENERIC = {"creature", "creatures", "monster", "monsters", "thing", "things",
               "list", "purpose", "people", "person", "someone", "everyone"}
POP_SKIP = set("""the a an and or but so of to in on at it its is are was were
be this that these those there here you your i we they he she her his not no
for from with into up down out over under as if""".split())


def choose_pops(spans, plan, words, creature=""):
    """The pop is a PHRASE lifted from the line, not the line's longest word.

    Picking the longest word produced HORSE, EVENING, DISAPPEARING, PERSONALLY,
    WHATEVER and SHOWED - grammatical debris, and "PERSONALLY" on screen in
    96px is nobody's idea of a keyword. The reference pops the thing the
    sentence is about: NO LOWER JAW, IMPOSSIBLE ANGLES, 100% FRIENDLY, EMPLOYEE
    OF THE MONTH. Those are noun phrases straight out of his narration, which
    is exactly what the plan already extracted in order to go find pictures.

    So the pop comes from the same place the picture does. If a line earned no
    picture it earns no pop either, which is the correct answer for "That is
    not good news."
    """
    out, last = [], -99.0
    seen = set()
    name = norm(creature)
    for sp, row in zip(spans, plan):
        # The SPECIFIC thing outranks the creature. The creature's name is
        # already on screen as the persistent title in every single frame, so
        # popping it is the caption repeating the caption - a first pass did it
        # three times in one minute. Pop what this line adds.
        order = {"photo": 0, "canon": 1, "roster": 3, "icon": 3}
        cands = sorted(row["things"], key=lambda t: (order.get(t["kind"], 4),
                       -len((t.get("phrase") or "").split())))
        phrase = None
        for t in cands:
            p = (t.get("phrase") or t.get("noun") or "").strip()
            ws = [w for w in p.split() if w not in POP_SKIP]
            if not (1 <= len(ws) <= 4 and len("".join(ws)) > 3):
                continue
            cand = " ".join(ws)
            if norm(cand) == name or norm(cand) in seen:
                continue        # never the title, never the same pop twice
            if len(ws) == 1 and ws[0] in POP_GENERIC:
                continue        # a generic single word is not worth 96px
            phrase, anchor = cand, ws[-1]
            break
        if not phrase:
            continue
        at = word_time(sp, words, anchor, sp["t0"])
        if at - last < POP_MIN_GAP:
            continue
        seen.add(norm(phrase))
        out.append({"t0": round(at, 3),
                    "t1": round(min(at + 2.1, sp["t1"] + 0.7), 3),
                    "text": phrase.upper(), "word": anchor, "y": 806})
        last = at
    return out


# ---------------------------------------------------------------- sheet

def to_sheet(scenes, pops, creature, vo, duration, illus_dir, canon_plates,
             assets_dir):
    """Flatten scenes into the shot list the renderer already understands.

    One scene is ONE shot. Everything that happens inside it is an insert, an
    icon or a pop with its own time, so the framing is held while the frame
    keeps changing.
    """
    shots, titles = [], []
    art_i = 0
    for sc in scenes:
        g = sc["ground"]
        if g.startswith("illus:"):
            ground = "plate:" + os.path.join(os.path.basename(illus_dir),
                                             g.split(":", 1)[1])
        elif g in ("creature", "roster"):
            # A creature beat is not a blank canvas. It gets a canon photograph
            # as its ground with a cutout performing over it, because a white
            # frame with a floating creature on it is the "floating creature
            # and icon soup" the owner rejected in a competitor's work.
            arts = canon_plates or []
            ground = (f"plate:assets/{arts[art_i % len(arts)]}" if arts else "white")
            art_i += 1
        else:
            ground = "white"
        white = ground == "white"

        reveals = [e for e in sc["events"] if e["type"] == "reveal"]
        span = max(0.5, sc["t1"] - sc["t0"])
        shot = {"t0": round(sc["t0"], 3), "t1": round(sc["t1"], 3),
                "ground": ground, "hold": True,
                "plate_scale": [1.05, round(min(1.05 + 0.022 * span, 1.42), 3)],
                "scene_lines": sc["lines"]}
        asset = (reveals[0]["src"] if reveals else sc.get("asset"))
        layers = []
        for k, rv in enumerate(reveals[1:3]):
            src = f"assets/{rv['src']}"
            fs = fit_scale(os.path.join(assets_dir, rv["src"]),
                           max_w=0.50, max_h=0.40)
            layers.append({"src": src, "at": rv["at"], "word": rv["word"],
                           "x": 0.24 if k == 0 else 0.78, "y": 0.70,
                           "scale": fs, "from_left": k == 0})
        if layers:
            shot["layers"] = layers
        if asset:
            shot["asset"] = f"assets/{asset}"
            # Scale and anchor measured off the reference: the skull is BIG and
            # sits high, with the neck running out of frame. A cutout at 0.62
            # centred on the frame is the "floating creature" the owner
            # rejected - it reads as a sticker laid on a backdrop rather than
            # something standing in the room.
            sc0 = fit_scale(os.path.join(assets_dir, asset))
            drift = min(0.09, 0.006 * span)
            shot["from_"] = [0.54 + drift, 0.58, sc0]
            shot["to"] = [0.54 - drift, 0.565, round(sc0 * (1 + 0.02 * span), 3)]
            shot["hold"] = False
        ins = [e for e in sc["events"] if e["type"] == "insert"]
        if ins:
            shot["inserts"] = [{"src": os.path.join(os.path.basename(illus_dir),
                                                    e["src"]),
                                "x": e["x"], "y": e["y"], "w": e["w"],
                                "h": e["w"] * 0.62 * 1920 / 1080,
                                "at": e["at"], "tilt": e["tilt"],
                                "word": e["word"],
                                "out": next((o["at"] - 0.05 for o in ins
                                             if o.get("wave", 0) > e.get("wave", 0)),
                                            None)} for e in ins]
        ic = [e for e in sc["events"] if e["type"] == "icon"]
        if ic:
            shot["icons"] = [{"kind": e["kind"], "x": 0.20, "y": 0.62,
                              "scale": 2.4, "at": e["at"], "word": e["word"]}
                             for e in ic]
        # A punch is a real cut, so it splits the scene into separate shots on
        # the same ground at a tighter crop.
        punches = [e["at"] for e in sc["events"] if e["type"] == "punch"]
        if punches:
            bounds = [shot["t0"]] + punches + [shot["t1"]]
            for k in range(len(bounds) - 1):
                part = dict(shot)
                part["t0"], part["t1"] = round(bounds[k], 3), round(bounds[k + 1], 3)
                zoom = 1.05 + 0.20 * k
                psp = max(0.5, bounds[k + 1] - bounds[k])
                part["plate_scale"] = [round(zoom, 3),
                                       round(zoom + min(0.022 * psp, 0.34), 3)]
                # An element that arrived in an EARLIER part is still on
                # screen; it must be re-declared in this part, entering at the
                # part's own start instead of being dropped. Dropping it is
                # what produced a 4.5 second dead zone in QC: a box appeared,
                # the next punch silently deleted it, and the white canvas sat
                # empty at 1.4% frame change until the next line.
                for key in ("inserts", "icons", "layers"):
                    if key not in shot:
                        continue
                    live = []
                    for e in shot[key]:
                        out = e.get("out")
                        if e["at"] >= part["t1"]:
                            continue                    # not yet
                        if out is not None and out <= part["t0"]:
                            continue                    # already gone
                        e2 = dict(e)
                        if e2["at"] < part["t0"]:
                            e2["at"] = part["t0"]       # already present: hold
                            e2["carried"] = True
                        live.append(e2)
                    if live:
                        part[key] = live
                    else:
                        part.pop(key, None)
                # Each punch is a tighter framing of the SAME cutout, which is
                # how the reference keeps a location for twenty seconds and
                # still changes the picture. 12% per punch is enough to read as
                # a new shot without turning the subject into wallpaper.
                if k > 0 and "asset" in part:
                    z = round(shot["from_"][2] * (1 + 0.22 * k), 3)
                    part["from_"] = [0.51, 0.56, z]
                    part["to"] = [0.50, 0.55, round(z * 1.08, 3)]
                shots.append(part)
                titles.append({"t0": part["t0"], "t1": part["t1"], "white": white})
            continue
        shots.append(shot)
        titles.append({"t0": shot["t0"], "t1": shot["t1"], "white": white})

    # merge adjacent title runs that share a fill, so it does not re-animate
    merged = []
    for t in titles:
        if merged and merged[-1]["white"] == t["white"]:
            merged[-1]["t1"] = t["t1"]
        else:
            merged.append(dict(t))

    end = round(duration, 3)
    # The composition carries a short tail past the last spoken word so the
    # section does not end on a hard stop. NOTHING occupied it, so the render
    # closed on 18 black frames and 0.66s of digital silence - both QC
    # failures. The last shot holds through the tail instead.
    if shots:
        shots[-1]["t1"] = end
        merged[-1]["t1"] = end
    for p in pops:
        p["t1"] = min(p["t1"], end - 0.1)
        p["t0"] = min(p["t0"], p["t1"] - 0.2)
    for sh in shots:
        sh["t1"] = min(sh["t1"], end)
    return {"creature": creature, "duration": end, "vo": vo,
            "shots": shots, "pops": pops, "titles": merged}


WORDS = []


def main():
    global WORDS
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--words", required=True)
    ap.add_argument("--illus", required=True)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--plates", default=None,
                    help="creature-FREE plates; grounds for creature scenes")
    ap.add_argument("--creature", required=True)
    ap.add_argument("--vo", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    plan = json.load(open(a.plan))
    WORDS = json.load(open(a.words))
    illus = load_illus(a.illus)
    canon = load_canon(a.assets, a.plates)

    spans = anchor_lines([r["line"] for r in plan], WORDS)
    plan = plan[:len(spans)]
    scenes = build_scenes(spans, plan, illus, canon)
    pops = choose_pops(spans, plan, WORDS, a.creature)
    duration = WORDS[-1]["e"] + 0.6

    sheet = to_sheet(scenes, pops, a.creature, a.vo, duration, a.illus,
                     canon["plates"], a.assets)
    json.dump(sheet, open(a.out, "w"), indent=1)

    ins = sum(len(s.get("inserts", [])) for s in sheet["shots"])
    ico = sum(len(s.get("icons", [])) for s in sheet["shots"])
    print(f"{len(scenes)} scenes over {duration:.1f}s "
          f"({60*len(scenes)/duration:.1f} cuts/min, reference 15.2)")
    for i, s in enumerate(sheet["shots"], 1):
        ev = len(s.get("inserts", [])) + len(s.get("icons", []))
        print(f"  {i:2d}  {s['t0']:6.2f}-{s['t1']:6.2f}  {s['t1']-s['t0']:5.2f}s  "
              f"{s['ground'][:34]:36s} {ev} events")
        for ln in s["scene_lines"]:
            print(f"        \"{ln[:78]}\"")
    print(f"\n{ins} inserts, {ico} icons, {len(pops)} pops "
          f"({60*len(pops)/duration:.1f}/min) -> {a.out}")
    longest = max(s["t1"] - s["t0"] for s in sheet["shots"])
    print(f"longest hold {longest:.1f}s (reference 23.1s, previous build 6.1s)")


if __name__ == "__main__":
    main()
