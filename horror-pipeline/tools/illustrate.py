#!/usr/bin/env python3
"""Stage 1b: source an image for every THING the script names.

WHY THIS EXISTS. The pipeline sourced only canon creature art, so every
narration line got a creature picture regardless of what the line said. Checked
against a real section: eleven lines, eleven creature pictures, while the script
named a girl, a bed, a hallway, stairs, apples and cinnamon and none of them
were ever on screen.

The reference editor does the opposite. Put his narration beside his picture and
the method is one question per sentence: what does this line literally show?

  "you are driving alone"           -> a car on a night road
  "a locked room or miles of road"  -> TWO boxed images: a door, and a road
  "means a disaster is approaching" -> a tornado photograph
  "ordinary barriers"               -> TWO boxed images: a room, and a wall

Most of his frames are NOT creature images. A tornado, a door, a highway, a
wall. The canon rules govern CREATURE images and always did; a door is
illustration, needs no approval gate, and there are more of them than creatures.

HOW A LINE BECOMES QUERIES. Not a keyword list - those only ever match the
script they were written for, and the owner hands us a new script each video.
spaCy supplies the noun chunks, WordNet supplies whether the head noun names
something you can photograph:

  hallway   noun.artifact     -> photographable
  apple     noun.food         -> photographable
  skull     noun.body         -> photographable
  dream     noun.cognition    -> not photographable, needs a conventional stand-in
  purpose   noun.cognition    -> not photographable, and has no stand-in: dropped

Three routings happen before that test, and each one exists because skipping it
breaks a rule that has already cost a delivery:

  CANON    A noun naming the creature ("skull", "neck", "vertebrae") must come
           from the approved materials, never from stock. Rule 5: the image may
           not contradict the line. A stock horse skull HAS a lower jaw.
  PEOPLE   noun.person never becomes a photograph. Rule 6 is absolute about
           real identifiable people and a photo of a child has already shipped
           and had to be pulled. The reference editor draws people as stick
           figures for exactly this reason. So do we.
  CONCEPT  Some nouns are photographable but search badly on their own
           ("corner", "barrier"). A stand-in query is substituted.

Everything downloaded is then face-detected and thrown away if a face is found,
because a search for "vinyl record player" will happily return a photograph of
the person holding it.

LICENSING. Sources are public and reusable: Wikimedia Commons (returns real
LicenseShortName, unlike Fandom which returns nothing) and Openverse, which
aggregates CC-licensed and public-domain work. Every record keeps the licence,
the attribution and the source URL so a takedown or an attribution request can
be answered from the file.

  illustrate.py plan  script.md --out plan.json [--canon "horse,skull,neck"]
  illustrate.py fetch plan.json --out DIR
"""
import argparse, json, os, re, sys, time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
YUNET = os.environ.get("HP_YUNET", os.path.join(HERE, "models", "yunet.onnx"))

UA = {"User-Agent": "horror-engine/1.0 (channel illustration sourcing; contact: owner)"}
SLEEP = 1.1          # Commons returns 429 if you go faster than about 1/sec

# WordNet lexicographer files. These ARE the concreteness test: every noun in
# WordNet carries one, and the split between "names a thing you could point a
# camera at" and "names an idea" falls almost exactly along these names.
CONCRETE = {"noun.artifact", "noun.object", "noun.body", "noun.animal",
            "noun.plant", "noun.food", "noun.substance", "noun.location",
            "noun.shape", "noun.phenomenon"}
PEOPLE = {"noun.person", "noun.group"}

# Photographable, but the bare word searches badly. The stand-in is what a
# picture editor would actually go looking for.
CONCEPT = {
    "disaster": "tornado supercell storm", "misfortune": "car crash wreck roadside",
    "warning": "warning road sign", "danger": "hazard warning sign",
    "dream": "empty bed dark bedroom night", "sleep": "empty bed dark bedroom night",
    "nightmare": "empty bed dark bedroom night",
    "music": "vinyl record player turntable", "song": "vinyl record player turntable",
    "corner": "corridor corner interior", "barrier": "brick wall",
    "hallway": "dark corridor interior", "corridor": "dark corridor interior",
    "stair": "staircase interior dark", "stairs": "staircase interior dark",
    "door": "closed door interior", "doorway": "open doorway dark interior",
    "frame": "door frame interior", "road": "empty road night",
    "forest": "dark forest trees night", "tree": "dark forest trees night",
    "night": "night sky darkness", "evening": "dusk sky window",
    "bedroom": "dark bedroom night", "window": "window at night dark",
    "joint": "human finger bones xray", "vertebra": "vertebra bone",
    "list": "handwritten list paper", "news": "newspaper headline",
    "purpose": "signpost direction", "arrival": "empty road night",
}

# Words that survive the noun test but never earn a frame. Most are idiom
# carriers: "not good news" is not about a newspaper, and photographing one
# illustrates the words rather than the sentence.
BORING = {"thing", "something", "anything", "nothing", "way", "kind", "sort",
          "lot", "bit", "part", "one", "reason", "case", "point", "time",
          "question", "answer", "fact", "example", "percent", "number",
          "news", "end", "start", "today", "year", "day", "week", "name"}

# Nouns that refer to the video itself, not to anything in the world. "the last
# creature on this list" means OUR list, and the frame for it is the roster
# grid the section already builds, not a photograph of a piece of paper.
ROSTER = {"list", "lineup", "ranking", "countdown", "video", "episode"}

# Verbs carry the picture when the sentence has no usable noun. Used only as a
# fallback, because a verb query fired alongside two good noun queries just adds
# a third frame nobody asked for.
VERB_CONCEPT = {
    "warn": "warning road sign", "drive": "car headlights night road",
    "hide": "closet door ajar dark", "follow": "footprints in snow",
    "escape": "emergency exit sign", "burn": "house fire at night",
    "drown": "dark water surface", "scream": "empty dark room interior",
    "watch": "security camera cctv", "wait": "empty bus stop night",
}

# Which CONCEPT entries name a PLACE. A place fills the frame and the creature
# is composited into it; an object sits in a box on the white canvas. The two
# are judged differently, so the planner has to say which it is.
SCENE_KEYS = {"dream", "sleep", "nightmare", "hallway", "corridor", "corner",
              "stair", "stairs", "door", "doorway", "frame", "road", "forest",
              "tree", "night", "evening", "bedroom", "window", "arrival",
              "drive", "hide", "scream", "wait", "burn", "drown", "escape"}

# Sensory adjectives describe the SOUND or FEEL of a thing, not its look. They
# poison an image query: "soft dry crack" returns nothing like a crack.
NONVISUAL_ADJ = {"soft", "dry", "loud", "quiet", "faint", "strange", "genuine",
                 "ordinary", "exact", "whatever", "personal", "real", "certain",
                 "different", "good", "bad", "last", "only", "same", "such",
                 "much", "many", "own", "sure", "possible", "likely"}


# ---------------------------------------------------------------- nlp

_NLP = None
_WN = None


def nlp():
    global _NLP
    if _NLP is None:
        import spacy
        _NLP = spacy.load("en_core_web_sm")
    return _NLP


def lexnames(lemma):
    """WordNet lexicographer names for a lemma used as a noun."""
    global _WN
    if _WN is None:
        os.environ.setdefault("NLTK_ALLOW_PROXIED_URLOPEN", "1")
        from nltk.corpus import wordnet as wn
        try:
            wn.synsets("test", pos="n")
        except LookupError:
            import nltk
            nltk.download("wordnet", quiet=True)
        _WN = wn
    return [s.lexname() for s in _WN.synsets(lemma, pos="n")]


# ---------------------------------------------------------------- sources

def commons(term, n=4):
    """Wikimedia Commons. Strong on concrete objects, weak on scene phrases."""
    try:
        r = requests.get("https://commons.wikimedia.org/w/api.php", params={
            "action": "query", "generator": "search",
            "gsrsearch": f"filetype:bitmap {term}", "gsrlimit": n, "gsrnamespace": 6,
            "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": 1400, "format": "json", "formatversion": 2},
            headers=UA, timeout=30)
        time.sleep(SLEEP)
        if r.status_code != 200:
            return []
        out = []
        for p in r.json().get("query", {}).get("pages", []):
            ii = (p.get("imageinfo") or [{}])[0]
            if not ii.get("url"):
                continue
            m = ii.get("extmetadata") or {}
            g = lambda k: re.sub("<[^>]+>", "", (m.get(k) or {}).get("value", "")).strip()
            out.append({"source": "wikimedia-commons", "title": p["title"][5:],
                        "url": ii.get("thumburl") or ii["url"], "full": ii["url"],
                        "w": ii.get("width"), "h": ii.get("height"),
                        "mime": ii.get("mime"), "page": ii.get("descriptionurl"),
                        "license": g("LicenseShortName"), "attribution": g("Artist")[:120]})
        return out
    except Exception:
        return []


def openverse(term, n=4):
    """Openverse aggregates CC and public-domain images. Better on scenes."""
    try:
        r = requests.get("https://api.openverse.org/v1/images/",
                         params={"q": term, "page_size": n,
                                 "license_type": "all-cc,commercial"},
                         headers=UA, timeout=30)
        time.sleep(0.4)
        if r.status_code != 200:
            return []
        out = []
        for x in r.json().get("results", []):
            if not x.get("url"):
                continue
            out.append({"source": "openverse", "title": (x.get("title") or "")[:80],
                        "url": x["url"], "full": x["url"],
                        "w": x.get("width"), "h": x.get("height"),
                        "mime": "image/" + (x.get("filetype") or "jpeg"),
                        "page": x.get("foreign_landing_url"),
                        "license": ((x.get("license") or "").upper() + " "
                                    + (x.get("license_version") or "")).strip(),
                        "attribution": (x.get("creator") or "")[:120]})
        return out
    except Exception:
        return []


# ---------------------------------------------------------------- plan

def clean_chunk(chunk):
    """The searchable core of a noun chunk.

    Compound nouns always stay: 'door frame' and 'frame' are different pictures
    and the line said door. Adjectives are kept only when they describe how a
    thing LOOKS and only one of them, because a stack of them narrows an image
    search to nothing: 'a soft, dry crack' is a sound, and searching that phrase
    returns neither a crack nor anything else.
    """
    head = chunk.root
    words, adj = [], 0
    for t in chunk:
        if not t.is_alpha:
            continue
        if t.pos_ in ("NOUN", "PROPN"):
            words.append(t.text.lower())
        elif t.pos_ == "ADJ" and t.lemma_.lower() not in NONVISUAL_ADJ and adj == 0:
            words.append(t.text.lower())
            adj += 1
    if head.text.lower() not in words:
        words.append(head.text.lower())
    return " ".join(words)


def classify(chunk, canon):
    """One noun chunk -> what to put on screen for it, or None to drop it."""
    head = chunk.root
    lemma = head.lemma_.lower()
    text = clean_chunk(chunk)
    if not text or lemma in BORING:
        return None

    # 1. CANON first. A creature noun must come from approved materials.
    words = set(text.split()) | {lemma}
    if words & canon:
        return {"noun": lemma, "phrase": text, "kind": "canon", "query": None,
                "why": "creature noun"}

    # 2. The video talking about itself. Show the roster, not a photograph.
    if lemma in ROSTER:
        return {"noun": lemma, "phrase": text, "kind": "roster", "query": None,
                "why": "refers to this video's own list"}

    ln = lexnames(lemma)

    # 3. PEOPLE never become photographs. Rule 6.
    if ln and ln[0] in PEOPLE:
        return {"noun": lemma, "phrase": text, "kind": "icon", "icon": "figure",
                "query": None, "why": "person, drawn not photographed"}

    # 4. CONCEPT stand-in, for nouns that search badly or name an idea.
    if lemma in CONCEPT:
        return {"noun": lemma, "phrase": text, "kind": "photo",
                "query": CONCEPT[lemma],
                "role": "plate" if lemma in SCENE_KEYS else "insert",
                "why": "concept stand-in"}

    # 5. Photographable on its own terms.
    if any(x in CONCRETE for x in ln[:3]):
        return {"noun": lemma, "phrase": text, "kind": "photo", "query": text,
                "role": "plate" if ln[0] == "noun.location" else "insert",
                "why": ln[0].replace("noun.", "")}

    # 6. Names an idea and has no stand-in. Drop it: no frame is better than a
    #    frame that does not mean anything.
    return None


def plan(text, canon, cap=4):
    """Every sentence -> the things it names, in the order it names them.

    A sentence that yields nothing is not a failure and is not a blank frame.
    It means HOLD: stay in the scene the last line established. The reference
    editor's longest single hold is 23 seconds, so holding is the normal case
    and cutting is what has to be earned.
    """
    doc = nlp()(text)
    rows = []
    for sent in doc.sents:
        line = sent.text.strip()
        if not line:
            continue
        things, seen = [], set()
        for ch in sent.noun_chunks:
            t = classify(ch, canon)
            if not t:
                continue
            key = t.get("query") or t["kind"] + ":" + t["noun"]
            if key in seen:
                continue
            seen.add(key)
            things.append(t)

        # Verbs are a fallback only. A sentence already carrying two pictures
        # does not need a third one derived from its verb.
        if len(things) < 2:
            for tok in sent:
                q = VERB_CONCEPT.get(tok.lemma_.lower()) if tok.pos_ == "VERB" else None
                if q and q not in seen:
                    seen.add(q)
                    things.append({"noun": tok.lemma_.lower(), "kind": "photo",
                                   "query": q, "why": "verb",
                                   "role": "plate" if tok.lemma_.lower()
                                           in SCENE_KEYS else "insert"})
                    break

        # The cap drops the TAIL of a long sentence, and the tail is where the
        # specific detail lives - an earlier pass capped at three and silently
        # lost "cinnamon" from "music and apples, and it smells like cinnamon".
        # Canon and roster beats are free: they cost no new sourcing.
        free = [t for t in things if t["kind"] in ("canon", "roster")]
        paid = [t for t in things if t["kind"] not in ("canon", "roster")]
        rows.append({"line": line, "things": free[:2] + paid[:cap]})
    return rows


# ---------------------------------------------------------------- fetch

_DET = None
_CLIP = None

# Licences we can actually ship. The pipeline crops, grades, composites and
# monetises, so:
#   ND  forbids the crop and the composite outright
#   NC  forbids the monetisation
# Both are hard rejects, not warnings. SA is allowed but flagged, because the
# obligation it creates lands on the video description, not on the edit.
def licence_ok(lic):
    u = (lic or "").upper().replace("_", "-")
    if "ND" in re.split(r"[^A-Z0-9]+", u):
        return False, "no-derivatives"
    if "NC" in re.split(r"[^A-Z0-9]+", u):
        return False, "non-commercial"
    if not u:
        return False, "no licence stated"
    return True, ("share-alike" if "SA" in re.split(r"[^A-Z0-9]+", u) else "ok")


def clip():
    """Image/text relevance. This is the difference between a picture editor and
    a keyword search.

    Measured on the first pass without it: 'crack' returned crack cocaine,
    'dark corridor interior' returned a wallpaper calendar and a museum,
    'staircase interior dark' returned a mosque. The search engines rank on
    title text, so a photo captioned 'Corridor Corner Landscape' outranks an
    actual dark corridor. CLIP ranks on what the picture SHOWS, which is the
    only thing that matters here.
    """
    global _CLIP
    if _CLIP is None:
        import open_clip, torch
        m, _, pre = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="laion2b_s34b_b79k")
        m.eval()
        _CLIP = (m, pre, open_clip.get_tokenizer("ViT-B-32"), torch)
    return _CLIP


def relevance(paths, query):
    """Cosine similarity of each image to 'a photo of <query>'."""
    from PIL import Image
    m, pre, tok, torch = clip()
    prompts = [f"a photograph of {query}", f"{query}"]
    with torch.no_grad():
        tf = m.encode_text(tok(prompts))
        tf = tf / tf.norm(dim=-1, keepdim=True)
        out = []
        for p in paths:
            try:
                im = pre(Image.open(p).convert("RGB")).unsqueeze(0)
                v = m.encode_image(im)
                v = v / v.norm(dim=-1, keepdim=True)
                out.append(float((v @ tf.T)[0].max()))
            except Exception:
                out.append(0.0)
    return out


def look(path):
    """What the picture LOOKS like, as opposed to what it is of.

    Relevance and fitness are different axes, and the contact sheet proved it:
    a saturated green abstract scored 0.222 as "crack" while a genuinely
    perfect dark industrial corridor scored 0.242. The higher number was the
    unusable picture. So measure the look separately.

      saturation   a stock graphic is fluorescent; a photograph is not. The
                   green abstract sat at 0.968 and a yellow pictogram sign at
                   0.724, while the darkest usable bedroom sat at 0.665.
      ocr words    catches calendars, posters, album covers and watermarks. On
                   the first batch it fired on exactly one image, the wallpaper
                   calendar's date strip, and on nothing legitimate.
    """
    import numpy as np
    from PIL import Image
    im = Image.open(path).convert("RGB")
    a = np.asarray(im.resize((160, 90))).astype(float) / 255.0
    mx, mn = a.max(2), a.min(2)
    sat = float(((mx - mn) / (mx + 1e-6)).mean())
    lum = float((0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]).mean())
    words = 0
    try:
        import pytesseract
        g = im.convert("L")
        g.thumbnail((1000, 1000))
        d = pytesseract.image_to_data(g, output_type=pytesseract.Output.DICT)
        words = sum(1 for w, c in zip(d["text"], d["conf"])
                    if w.strip() and len(w.strip()) > 1 and float(c) >= 70)
    except Exception:
        words = -1
    return {"sat": round(sat, 3), "lum": round(lum, 3), "ocr_words": words,
            "aspect": round(im.width / max(1, im.height), 2)}


# A plate fills the frame, so it must be landscape and must not be a poster.
# An insert sits in a box and may legitimately BE text - the reference editor
# uses a warning sign and an "employee of the month" badge - so its text
# allowance is looser and its shape does not matter.
GATES = {"plate":  {"sat": 0.70, "ocr": 4, "aspect": 1.15},
         "insert": {"sat": 0.70, "ocr": 8, "aspect": 0.0}}


def look_ok(m, role):
    g = GATES.get(role, GATES["insert"])
    if m["sat"] > g["sat"]:
        return False, f"saturation {m['sat']} (graphic, not photo)"
    if m["ocr_words"] >= g["ocr"]:
        return False, f"{m['ocr_words']} words of text (poster/watermark)"
    if m["aspect"] < g["aspect"]:
        return False, f"aspect {m['aspect']} (will not fill 16:9)"
    return True, "ok"


def faces(path):
    """Number of human faces. Rule 6 backstop: any hit and the image is out."""
    global _DET
    try:
        import cv2
        import numpy as np
        if _DET is None:
            if not os.path.exists(YUNET):
                return -1          # no detector: caller decides
            _DET = cv2.FaceDetectorYN_create(YUNET, "", (320, 320), 0.6)
        im = cv2.imread(path)
        if im is None:
            return -1
        h, w = im.shape[:2]
        s = 1024.0 / max(h, w)
        if s < 1:
            im = cv2.resize(im, (int(w * s), int(h * s)))
            h, w = im.shape[:2]
        _DET.setInputSize((w, h))
        _, f = _DET.detect(im)
        return 0 if f is None else len(f)
    except Exception:
        return -1


MIN_RELEVANCE = 0.22     # below this the picture is not of the thing asked for


def write_credits(records, path):
    """The attribution block for the video description.

    Written by fetch every time, never on request. CC BY obliges us to credit
    the photographer and name the licence, and an obligation that depends on
    somebody remembering to run a second command is an obligation that gets
    skipped on the one busy week it matters. Only images that survived every
    gate appear here, so the list matches what is actually on screen.
    """
    used = [r for r in records if r.get("file")]
    lines = ["# Image credits", "",
             "Sourced from Wikimedia Commons and Openverse. Reusable licences",
             "only: anything marked No-Derivatives or Non-Commercial is rejected",
             "at fetch time, because this pipeline crops and grades every image",
             "and the channel is monetised.", ""]
    sa = [r for r in used if r.get("sa")]
    if sa:
        lines += [f"{len(sa)} of these are share-alike. If any survives into the",
                  "published cut, the derivative carries the same obligation.", ""]
    for r in sorted(used, key=lambda r: r["query"]):
        who = r.get("attribution") or "unknown"
        lines.append(f"- **{r['query']}** - \"{r['title']}\" by {who}, "
                     f"{r['license']}. {r.get('page') or r['url']}")
    open(path, "w").write("\n".join(lines) + "\n")


def phrasings(q):
    """Same subject, asked several ways.

    A long query is precise but starves the search: 'empty bed dark bedroom
    night' returned nothing usable while 'empty bedroom' returned three exact
    matches from both sources. Pooling the phrasings and letting CLIP pick the
    winner gets the precision back without the starvation.
    """
    w = q.split()
    out = [q]
    if len(w) > 2:
        out.append(" ".join(w[:2]))
        out.append(" ".join(w[-2:]))
    if len(w) > 1:
        out.append(w[-1])
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq[:3]


def fetch(plan_path, outdir, per=3, pool=14):
    rows = json.load(open(plan_path))
    os.makedirs(outdir, exist_ok=True)
    tmp = os.path.join(outdir, ".cand")
    os.makedirs(tmp, exist_ok=True)

    queries = []
    for r in rows:
        for t in r["things"]:
            if t["kind"] == "photo" and t["query"] not in [q[0] for q in queries]:
                queries.append((t["query"], t["noun"], t.get("role", "insert")))

    records, rejected, unsourced = [], [], []
    for q, noun, role in queries:
        # 1. Pool candidates across phrasings and both sources.
        cands, seen_url = [], set()
        for p in phrasings(q):
            for h in commons(p, 5) + openverse(p, 5):
                if h["url"] in seen_url or (h.get("w") or 0) < 900:
                    continue
                ok, why = licence_ok(h["license"])
                if not ok:
                    rejected.append({"query": q, "title": h["title"], "why": why})
                    continue
                h["sa"] = (why == "share-alike")
                seen_url.add(h["url"])
                cands.append(h)
            if len(cands) >= pool:
                break

        # 2. Download, then gate on faces before spending CLIP on it.
        got = []
        for i, h in enumerate(cands[:pool]):
            try:
                b = requests.get(h["url"], headers=UA, timeout=60)
                if b.status_code != 200 or len(b.content) < 25000:
                    continue
                ext = ".png" if b.content[:4] == b"\x89PNG" else ".jpg"
                fn = os.path.join(tmp, f"{abs(hash(h['url'])) % 10**10}{ext}")
                open(fn, "wb").write(b.content)
                nf = faces(fn)
                if nf > 0:
                    os.remove(fn)
                    rejected.append({"query": q, "title": h["title"],
                                     "why": f"{nf} face(s) detected"})
                    continue
                m = look(fn)
                ok, why = look_ok(m, role)
                if not ok:
                    os.remove(fn)
                    rejected.append({"query": q, "title": h["title"], "why": why})
                    continue
                h.update(m)
                h["_tmp"] = fn
                got.append(h)
            except Exception:
                continue

        # 3. Rank by what the picture actually SHOWS, not by its caption.
        if got:
            for h, s in zip(got, relevance([g["_tmp"] for g in got], q)):
                h["relevance"] = round(s, 3)
            got.sort(key=lambda h: -h["relevance"])

        kept = 0
        stem = re.sub(r"[^a-z0-9]+", "-", q)[:40].strip("-")
        for h in got:
            if kept < per and h["relevance"] >= MIN_RELEVANCE:
                ext = os.path.splitext(h["_tmp"])[1]
                fn = os.path.join(outdir, f"{stem}-{kept}{ext}")
                os.replace(h["_tmp"], fn)
                h.pop("_tmp")
                h.update({"file": os.path.basename(fn), "noun": noun, "query": q,
                          "role": role, "approved": False})
                records.append(h)
                kept += 1
            else:
                os.path.exists(h["_tmp"]) and os.remove(h["_tmp"])

        best = got[0]["relevance"] if got else 0.0
        if kept == 0:
            unsourced.append({"query": q, "noun": noun, "best": best,
                              "candidates": len(got)})
        print(f"  {q[:36]:38s} {kept} kept   best {best:.3f}   "
              f"{len(got)} candidates")

    os.path.isdir(tmp) and not os.listdir(tmp) and os.rmdir(tmp)
    json.dump({"fetched": time.strftime("%Y-%m-%d"),
               "min_relevance": MIN_RELEVANCE, "images": records,
               "rejected": rejected, "unsourced": unsourced},
              open(os.path.join(outdir, "illustrations.json"), "w"), indent=2)

    write_credits(records, os.path.join(outdir, "CREDITS.md"))

    lic = {}
    for r in records:
        lic[r["license"]] = lic.get(r["license"], 0) + 1
    print(f"\n{len(records)} images kept, {len(rejected)} rejected, "
          f"{len(unsourced)} queries UNSOURCED -> {outdir}/illustrations.json")
    for k, v in sorted(lic.items(), key=lambda x: -x[1]):
        print(f"  {v:3d}  {k}")
    for u in unsourced:
        print(f"  UNSOURCED  {u['query']:34s} best {u['best']:.3f} "
              f"of {u['candidates']}")


# ---------------------------------------------------------------- approve

def approve(indir, rejects, note):
    """Record the editorial pass over the contact sheet.

    Every automatic gate here answers "is this a picture of the thing" and none
    of them answers "is this the right picture". A saturated green abstract and
    a perfect dark corridor scored within 0.02 of each other; a purple front
    door with a letterbox scored well and is unusable for a horror beat. So the
    last gate is a person looking, and this is where that judgement is written
    down instead of being remembered.

    Nothing downstream may use an image that has not passed through here: an
    unreviewed image is not approved, and build_scenes will not place it.
    """
    p = os.path.join(indir, "illustrations.json")
    d = json.load(open(p))
    rej = {r.strip() for r in rejects if r.strip()}
    unknown = rej - {r["file"] for r in d["images"]}
    if unknown:
        print("no such file:", ", ".join(sorted(unknown)))
        return
    n_ok = 0
    for r in d["images"]:
        r["approved"] = r["file"] not in rej
        if not r["approved"]:
            r["rejected_because"] = note or "editorial: wrong picture for the beat"
        else:
            r.pop("rejected_because", None)
            n_ok += 1
    d["reviewed"] = time.strftime("%Y-%m-%d")
    json.dump(d, open(p, "w"), indent=2)
    write_credits([r for r in d["images"] if r["approved"]],
                  os.path.join(indir, "CREDITS.md"))

    left = {}
    for r in d["images"]:
        if r["approved"]:
            left[r["query"]] = left.get(r["query"], 0) + 1
    print(f"{n_ok} approved, {len(rej)} rejected")
    for q in sorted({r['query'] for r in d['images']}):
        n = left.get(q, 0)
        print(f"  {'  ' if n else 'XX'} {q:36s} {n} usable")


# ---------------------------------------------------------------- calibrate

def calibrate(outdir):
    """Run every stand-in query in the tables and show what it actually returns.

    The stand-ins are the one part of this file that is pure authorship: I chose
    "door frame interior" to stand for a doorway and "corridor corner interior"
    to stand for a corner. Unverified, they returned a bright purple front door
    and a museum. That is the same mistake that has cost this build four
    rebuilds - write a mapping, build on it, never check it - so the table gets
    a test and the test produces a picture, not a number.

    Worst score first. Anything at the bottom of the list is a stand-in to
    rewrite, and a rewritten stand-in improves every future script, not just
    the one in front of us.
    """
    qs = sorted(set(CONCEPT.values()) | set(VERB_CONCEPT.values()))
    key = {}
    for k, v in list(CONCEPT.items()) + list(VERB_CONCEPT.items()):
        key.setdefault(v, k)
    os.makedirs(outdir, exist_ok=True)
    plan_path = os.path.join(outdir, "_calibrate-plan.json")
    json.dump([{"line": f"stand-in for '{key[q]}'",
                "things": [{"noun": key[q], "kind": "photo", "query": q,
                            "role": "plate" if key[q] in SCENE_KEYS else "insert",
                            "why": "calibration"}]} for q in qs],
              open(plan_path, "w"), indent=2)
    fetch(plan_path, outdir, per=1)

    d = json.load(open(os.path.join(outdir, "illustrations.json")))
    got = {r["query"]: r for r in d["images"]}
    print("\nworst stand-ins first - rewrite the ones at the top:")
    for q in sorted(qs, key=lambda q: got[q]["relevance"] if q in got else -1):
        r = got.get(q)
        print(f"  {(r['relevance'] if r else 0):.3f}  {key[q]:12s} -> {q}"
              + ("" if r else "   NOTHING FOUND"))


# ---------------------------------------------------------------- sheet

def sheet(indir, out, cols=6, cell=320):
    """One PNG of everything sourced, labelled. Look at this before building.

    Every wrong turn in this build came from trusting a number over a picture:
    a clear-fraction gate passed visibly smeared plates, an alpha statistic
    passed a matte with the arms cut off. CLIP relevance is another number. It
    is a good one, and it still gets looked at before anything ships.
    """
    from PIL import Image, ImageDraw, ImageFont
    d = json.load(open(os.path.join(indir, "illustrations.json")))
    imgs = d["images"]
    if not imgs:
        print("nothing to show")
        return
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except Exception:
        font = ImageFont.load_default()

    lab = 34
    rows = (len(imgs) + cols - 1) // cols
    W, H = cols * cell, rows * (cell + lab)
    canvas = Image.new("RGB", (W, H), (18, 18, 20))
    dr = ImageDraw.Draw(canvas)
    for i, r in enumerate(imgs):
        x, y = (i % cols) * cell, (i // cols) * (cell + lab)
        try:
            im = Image.open(os.path.join(indir, r["file"])).convert("RGB")
            im.thumbnail((cell - 6, cell - 6), Image.LANCZOS)
            canvas.paste(im, (x + (cell - im.width) // 2,
                              y + (cell - im.height) // 2))
        except Exception:
            dr.rectangle([x + 3, y + 3, x + cell - 3, y + cell - 3],
                         outline=(120, 40, 40))
        rel = r.get("relevance", 0)
        col = (110, 210, 120) if rel >= 0.30 else (
            (215, 195, 110) if rel >= 0.25 else (225, 120, 110))
        dr.text((x + 6, y + cell + 2), r["query"][:36], font=font,
                fill=(235, 235, 235))
        dr.text((x + 6, y + cell + 17),
                f"{rel:.3f}  {r['license']}"[:40], font=font, fill=col)
    canvas.save(out)
    print(f"{len(imgs)} images -> {out}  ({W}x{H})")


# ---------------------------------------------------------------- cli

def read_text(path):
    raw = open(path).read()
    if path.endswith(".json"):
        d = json.loads(raw)
        secs = d.get("sections", [d]) if isinstance(d, dict) else d
        return "\n\n".join(s.get("text") or s.get("narration") or "" for s in secs)
    # markdown: drop headings, keep prose
    return "\n".join(l for l in raw.splitlines() if not l.lstrip().startswith("#"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("script")
    p.add_argument("--out", required=True)
    p.add_argument("--canon", default="",
                   help="comma list of nouns that name the creature and must "
                        "come from approved canon art, not stock")
    f = sub.add_parser("fetch")
    f.add_argument("plan")
    f.add_argument("--out", required=True)
    f.add_argument("--per", type=int, default=3)
    s = sub.add_parser("sheet")
    s.add_argument("dir")
    s.add_argument("--out", required=True)
    c = sub.add_parser("calibrate")
    c.add_argument("--out", required=True)
    v = sub.add_parser("approve")
    v.add_argument("dir")
    v.add_argument("--reject", default="", help="comma list of filenames")
    v.add_argument("--note", default="")
    a = ap.parse_args()

    if a.cmd == "plan":
        canon = {w.strip().lower() for w in a.canon.split(",") if w.strip()}
        rows = plan(read_text(a.script), canon)
        json.dump(rows, open(a.out, "w"), indent=2)
        for r in rows:
            bits = []
            for t in r["things"]:
                bits.append(t["query"] if t["kind"] == "photo"
                            else f"[{t['kind']}:{t['noun']}]")
            print(f"  {r['line'][:60]:62s} -> {', '.join(bits) or '(nothing)'}")
        n = sum(len(r["things"]) for r in rows)
        print(f"\n{len(rows)} lines, {n} things -> {a.out}")
    elif a.cmd == "fetch":
        fetch(a.plan, a.out, a.per)
    elif a.cmd == "calibrate":
        calibrate(a.out)
    elif a.cmd == "approve":
        approve(a.dir, a.reject.split(","), a.note)
    else:
        sheet(a.dir, a.out)
