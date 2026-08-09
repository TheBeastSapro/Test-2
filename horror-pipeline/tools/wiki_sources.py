#!/usr/bin/env python3
"""Stage 1: source a creature's canon images, dedupe them, record provenance.

Every canon failure in this channel's QC history traces to one root cause: the
materials sheet shipped without a locked per-creature image shortlist, so the
editor chose images himself. The wrong creature frozen for nine seconds, the
fan art contradicting the narration, the Upside-Down Face rotated 180 degrees,
three mutually inconsistent Horned Serpent designs in one section, the
full-body Horned Serpent under "no one has ever seen the whole thing". Every
one of those is an image that would not have been in an approved folder.

This produces the folder. It does NOT decide what is canon: it enumerates,
downloads, dedupes and records, then hands you a contact sheet to tick.

Subcommands
  resolve <series-or-creature>     find the wiki and exact page title, confirm before crawling
  fetch   <wiki> <page> <creature> --project DIR
  report  <project>/materials/<creature>.json

Provenance policy, per the owner's 21 Jul decision: fan art is TOLERATED, the
hard rule is that an image must never contradict the narration line it plays
under. So provenance is RECORDED AND LABELLED, never used to silently drop an
image. Only four categories are hard-flagged, because they have shipped and
had to be pulled: licensed characters, real identifiable people, meme
photographs, identifiable minors.
"""
import argparse, hashlib, io, json, os, re, sys, time

import requests

UA = {"User-Agent": "horror-engine/1.0 (channel asset sourcing; contact: owner)"}
MIN_SHORT_SIDE = 400          # below this is wiki furniture: badges, icons, avatars
PHASH_DISTANCE = 6            # hamming distance treated as the same picture


def api(wiki, **params):
    params.setdefault("format", "json")
    params.setdefault("formatversion", 2)
    r = requests.get(f"https://{wiki}.fandom.com/api.php",
                     params=params, headers=UA, timeout=30)
    r.raise_for_status()
    time.sleep(0.35)                      # be polite, this is a free API
    return r.json()


# ---------------------------------------------------------------- resolve

def _candidates(name):
    """Subdomain guesses. Fandom naming is genuinely inconsistent: vitacarnis
    has no hyphens, gemini-home-entertainment does, and the Monument Mythos
    wiki is the-monument-mythos while both monumentmythos and monument-mythos
    404. So generate widely and probe."""
    w = re.sub(r"[^a-z0-9 ]", "", name.lower()).split()
    joined, hyph = "".join(w), "-".join(w)
    out = [joined, hyph, f"the{joined}", f"the-{hyph}", f"{joined}wiki", f"{hyph}-wiki"]
    if w and w[0] == "the":
        rest = w[1:]
        out += ["".join(rest), "-".join(rest)]
    seen, uniq = set(), []
    for c in out:
        if c and c not in seen:
            seen.add(c); uniq.append(c)
    return uniq


def resolve(name, creature=None):
    """Find candidate (wiki, page) pairs and show the evidence. Never auto-picks.

    Resolution is a decision, not a lookup. Two live traps make that concrete:
    a 'Rolling Giant' search on the correct wiki returns NOTHING because the
    canon page is the Julien Reverchon Giant, while a wiki that DOES answer to
    that name hosts a completely different creepypasta creature. And searching
    vitacarnis for 'The Mimic' returns 'Trucidatum Carnis' first.
    """
    target = creature or name
    print(f"resolving series={name!r} creature={target!r}\n")
    hits = []
    for cand in _candidates(name):
        try:
            si = api(cand, action="query", meta="siteinfo")["query"]["general"]
        except Exception:
            continue
        try:
            sr = api(cand, action="query", list="search", srsearch=target, srlimit=5)
            pages = [h["title"] for h in sr.get("query", {}).get("search", [])]
        except Exception:
            pages = []
        hits.append({"wiki": cand, "sitename": si.get("sitename"),
                     "server": si.get("server"), "search_hits": pages})
        print(f"  {cand:34s} {si.get('sitename')}")
        for p in pages:
            print(f"       - {p}")
        if not pages:
            print("       (wiki exists but no page matches the creature name)")

    if not hits:
        print("\nNo wiki responded. Try the series name rather than the creature name,")
        print("or find the wiki manually and pass it to `fetch` directly.")
        return hits

    print("\nA responding wiki is NOT proof it is the right one. Confirm the")
    print("sitename matches the series AND a search hit is the creature, then run:")
    print(f"  wiki_sources.py fetch <wiki> '<Exact Page Title>' <creature-slug> --project <DIR>")
    return hits


# ---------------------------------------------------------------- fetch

def gallery_filenames(wiki, page):
    """Page-order filenames from the article and its /Gallery subpage.

    Page order matters: the first images on a wiki page are almost always the
    canon debut images, and the ones further down are variants.
    """
    names = []
    for p in (page, f"{page}/Gallery"):
        try:
            names += api(wiki, action="parse", page=p, prop="images")["parse"]["images"]
        except Exception:
            pass                          # no gallery subpage is normal
    seen, ordered = set(), []
    for n in names:
        if n not in seen:
            seen.add(n); ordered.append(n)
    return ordered


def imageinfo(wiki, filenames):
    """Batch imageinfo, 50 titles at a time (MediaWiki's anonymous limit)."""
    out = []
    for i in range(0, len(filenames), 50):
        titles = "|".join("File:" + f for f in filenames[i:i + 50])
        d = api(wiki, action="query", titles=titles, prop="imageinfo",
                iiprop="url|size|mime|extmetadata", iiurlwidth=400)
        for pg in d.get("query", {}).get("pages", []):
            ii = (pg.get("imageinfo") or [{}])[0]
            if not ii.get("url"):
                continue
            out.append({"title": pg["title"], "url": ii["url"],
                        "thumb": ii.get("thumburl"), "w": ii.get("width"),
                        "h": ii.get("height"), "mime": ii.get("mime"),
                        "page": ii.get("descriptionurl"),
                        "meta": {k: v.get("value") for k, v in
                                 (ii.get("extmetadata") or {}).items()}})
    return out


def download(rec, outdir):
    """Fetch the true original.

    VERIFIED TRAP: Fandom's CDN serves WebP for a URL ending .jpg, regardless of
    the Accept header, and the API still reports mime image/jpeg. Appending
    &format=original returns the real JPEG. Without it you write WebP bytes into
    a .jpg file and every downstream tool that trusts the extension is wrong.
    """
    os.makedirs(outdir, exist_ok=True)
    r = requests.get(rec["url"] + "&format=original", headers=UA, timeout=90)
    r.raise_for_status()
    body = r.content

    # Name the file by what the bytes ACTUALLY are, never by the wiki title.
    sig = {b"\xff\xd8\xff": ".jpg", b"\x89PNG": ".png", b"GIF8": ".gif"}
    ext = next((e for m, e in sig.items() if body.startswith(m)), None)
    if ext is None:
        ext = ".webp" if body[8:12] == b"WEBP" else ".bin"
    fn = os.path.join(outdir, hashlib.sha1(rec["url"].encode()).hexdigest()[:12] + ext)
    with open(fn, "wb") as f:
        f.write(body)
    return fn, r.headers.get("content-type", "")


def fetch(wiki, page, creature, root):
    from PIL import Image
    import imagehash

    names = gallery_filenames(wiki, page)
    if not names:
        sys.exit(f"no images found on {page!r} or {page}/Gallery on {wiki}. "
                 f"Check the exact page title with `resolve`.")
    print(f"{len(names)} filenames on {page} (+/Gallery)")

    imgs = imageinfo(wiki, names)
    outdir = f"{root}/materials/{creature}"
    kept, hashes, dropped = [], [], []

    for order, rec in enumerate(imgs):
        try:
            fn, ctype = download(rec, outdir)
            im = Image.open(fn).convert("RGB")
        except Exception as e:
            dropped.append({"title": rec["title"], "why": f"{type(e).__name__}: {e}"})
            continue

        if min(im.size) < MIN_SHORT_SIDE:
            os.remove(fn)
            dropped.append({"title": rec["title"],
                            "why": f"short side {min(im.size)}px < {MIN_SHORT_SIDE}, wiki furniture"})
            continue

        ph = imagehash.phash(im)
        dupe = next((k for k, h in hashes if ph - h <= PHASH_DISTANCE), None)
        if dupe:
            os.remove(fn)
            dropped.append({"title": rec["title"], "why": f"perceptual duplicate of {dupe}"})
            continue
        hashes.append((rec["title"], ph))

        kept.append({
            "order": order,
            "file": os.path.relpath(fn, root),
            "phash": str(ph),
            "source_url": rec["url"],
            "wiki_page": rec["page"],
            "thumb": rec.get("thumb"),
            "size": list(im.size),
            "mime_reported": rec["mime"],
            "mime_actual": ctype,
            "meta": rec["meta"],

            # --- filled in by the description pass, then by the human gate ---
            "description": "",        # what is literally visible
            "not_visible": [],        # explicit absences the validator diffs against the VO
            "setting": "",            # so canon-daylight creatures keep their daylight
            "time_of_day": "",
            "design_variant": "",     # the Mimic life-stage / Horned Serpent case
            "provenance": "unknown",  # official-gallery | creator-account | fan-art
                                      # | game-model | wallpaper-scrape | unknown
            "hard_flags": [],         # licensed-character | real-identifiable-person
                                      # | meme-photograph | identifiable-minor
            "cutout_suitable": None,  # can this be matted cleanly, or is it a plate?
            "upscaled": None,
            "approved": False,
            "design_lock": False,     # the one design this video uses for this creature
            "notes": "",
        })

    os.makedirs(f"{root}/materials", exist_ok=True)
    path = f"{root}/materials/{creature}.json"
    doc = {"creature": creature, "wiki": wiki, "page": page,
           "fetched": time.strftime("%Y-%m-%d"),
           "source_of_truth": f"https://{wiki}.fandom.com/wiki/{page.replace(' ', '_')}",
           "min_short_side": MIN_SHORT_SIDE, "phash_distance": PHASH_DISTANCE,
           "counts": {"enumerated": len(imgs), "kept": len(kept), "dropped": len(dropped)},
           "dropped": dropped, "images": kept}
    json.dump(doc, open(path, "w"), indent=2)

    print(f"\n{len(kept)} kept, {len(dropped)} dropped -> {path}")
    for d in dropped[:12]:
        print(f"  dropped {d['title']}: {d['why']}")
    if len(dropped) > 12:
        print(f"  ... and {len(dropped)-12} more")
    print("\nNEXT: fill in every description, then build the contact sheet.")
    print("NOTHING RENDERS until each image used by a sheet has approved: true.")
    return doc


# ---------------------------------------------------------------- report

def report(path):
    d = json.load(open(path))
    imgs = d["images"]
    todo = [i for i in imgs if not i["description"]]
    appr = [i for i in imgs if i["approved"]]
    lock = [i for i in imgs if i.get("design_lock")]
    small = [i for i in imgs if min(i["size"]) < 900]
    print(f"{d['creature']}  ({d['wiki']} / {d['page']}, fetched {d['fetched']})")
    print(f"  kept                {len(imgs)}")
    print(f"  described           {len(imgs)-len(todo)}/{len(imgs)}")
    print(f"  approved            {len(appr)}")
    print(f"  design-locked       {len(lock)}  {'OK' if len(lock)==1 else 'NEEDS EXACTLY ONE'}")
    print(f"  under 900px         {len(small)}  (may need upscaling or a bigger source)")
    flags = [f for i in imgs for f in i["hard_flags"]]
    if flags:
        print(f"  HARD FLAGS          {flags}")
    if todo:
        print(f"\n  {len(todo)} still undescribed; the canon validator cannot run without them.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resolve"); r.add_argument("name"); r.add_argument("--creature")
    f = sub.add_parser("fetch")
    f.add_argument("wiki"); f.add_argument("page"); f.add_argument("creature")
    f.add_argument("--project", required=True)
    p = sub.add_parser("report"); p.add_argument("path")
    a = ap.parse_args()

    if a.cmd == "resolve":
        resolve(a.name, a.creature)
    elif a.cmd == "fetch":
        fetch(a.wiki, a.page, a.creature, a.project)
    else:
        report(a.path)


if __name__ == "__main__":
    main()
