#!/usr/bin/env python3
"""
Stage 5A — pull the high-risk claims out of a draft, as a verification worksheet.

Stage 5 asks whether a date, a name and a number are PRESENT. Stage 5A asks
whether the sentences are TRUE, and the SOP is blunt about why it exists:

    "The errors that reach the comments are never slop -- they are fluent,
     confident, plausible sentences that pattern-match to something true.
     They pass every grep. The audience for this channel timestamps them."

This tool does not verify anything. Verification means opening a real source,
and no regex can do that. What it does is the tedious half: walking the script
sentence by sentence and pulling out every sentence that makes one of the seven
high-risk claim types, grouped by entry, with the SOP's rule for each type
printed beside it and a blank line for the source.

That is the part that costs an hour and that gets skipped when a script is late.

It also flags the CADENCE HEURISTIC candidates, which is the least obvious and
most valuable scan here. From the SOP:

    "Every error found in the first Stage 5A run had arrived as an improvement
     to rhythm... Fluency is the tell, not the defence."

So the sentences that read best are surfaced deliberately, because those are
the ones that were written for the ear and never checked against a source.

HEURISTIC, NOT A VERDICT. Every scan here tests for shape, not for truth. A
clean run means nothing was matched, never that the script is accurate -- the
SOP records that the Bushnell dimension error cleared every mechanical check in
the battery. Read the hits; then open the sources anyway.
"""
import argparse
import json
import re
import sys

# --- section splitting (matches the linter's convention) ---------------------
_H2 = re.compile(r"^##\s+(.+?)\s*$")
_BACK_MATTER = re.compile(r"^#{1,6}\s*(pronunciation|audit|appendix|source|"
                          r"animator|production|research|variety|authenticity)", re.I)
_ABBREV = r"(?<!\bMr)(?<!\bMrs)(?<!\bDr)(?<!\bSt)(?<!\bNo)(?<!\bvs)(?<!\bc)(?<!\bfl)"
_SENT_END = re.compile(_ABBREV + r"(?<=[.!?])[\"'”’)\]]*\s+")


def sentences(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    return [s.strip() for s in _SENT_END.split(text) if s.strip()] if text else []


# --- the seven claim types ---------------------------------------------------
# Each carries the SOP's own rule, printed with the hits, because a flagged
# sentence with no rule beside it just becomes a list to skim past.

PART_WORDS = (r"edge|edges|curve|blade|hilt|tang|point|tip|spine|groove|fuller|"
              r"rivet|haft|pommel|guard|quillon|socket|shaft|head|butt|bore|"
              r"barrel|breech|muzzle|stock|lock|hull|keel|deck|prow|ram|oar")

MATERIAL_WORDS = (r"tamahagane|wootz|damascus|pattern-?welded|forge-?welded|"
                  r"laminated|differentially hardened|case-?hardened|"
                  r"carburi[sz]ed|quench(?:ed|ing)|temper(?:ed|ing)|"
                  r"folded|alloy|bronze|brass|steel|iron|carbon")

CLAIM_TYPES = [
    {
        "id": 1,
        "name": "lineage / descent",
        "rule": "Weapons rarely descend from what they resemble. If a documented "
                "ancestor exists, NAME it — the lineage fact is almost always more "
                "interesting than the line it replaces.",
        "re": re.compile(
            r"\b(evolved (?:from|into)|descend(?:s|ed|ant)?\s+from|ancestor|"
            r"forerunner|precursor|predecessor|derived from|derives from|"
            r"gave rise to|grew out of|began as|started (?:out )?as|"
            r"the origin of|originated (?:from|in|as)|based on the|"
            r"developed from|adapted from|reborn as|successor to)\b", re.I),
    },
    {
        "id": 2,
        "name": "anatomy / which part does what",
        "rule": "The trap is merging two parts into one action. Any sentence giving "
                "an object two functions in one clause gets checked TWICE.",
        "re": re.compile(
            r"\b(" + PART_WORDS + r")\b[^.]{0,60}\b(cut|cuts|hook|hooks|catch|"
            r"catches|trap|traps|pierce|pierces|slash|slashes|grip|grips|"
            r"absorb|absorbs|deflect|deflects|hold|holds|lock|locks)\b", re.I),
    },
    {
        "id": 3,
        "name": "composite written as one material",
        "rule": "If the object is a composite, the narration must say WHICH material "
                "does WHICH job. Collapsing a laminated object into one lump drops "
                "the reason the construction exists.",
        "re": re.compile(r"\b(" + MATERIAL_WORDS + r")\b", re.I),
    },
    {
        "id": 4,
        "name": "function inferred from shape",
        "rule": "Shape does not testify. If the technique is not attested, SAY SO and "
                "turn the gap into a beat — that converts the most common comment "
                "correction into a trust signal.",
        "re": re.compile(
            r"\b(designed to|meant to|intended to|built to|shaped to|made to|"
            r"in order to|so (?:that )?it could|so (?:that )?they could|"
            r"allow(?:ed|s|ing) (?:it|them|the)|which let|letting the|"
            r"used to (?:hook|cut|catch|pierce|trap|break|punch))\b", re.I),
    },
    {
        "id": 5,
        "name": "statistics where datasets disagree",
        "rule": "Attribute the source in the narration and state the SHAPE of the "
                "finding, not a bare percentage. A named historian plus a "
                "directional claim beats a naked number that invites correction.",
        # "half THE armies of Europe" is the documented failure shape, and an
        # "of"-only pattern misses it -- the quantifier attaches straight to the
        # noun. Bare quantifiers over a population are the same unfalsifiable
        # claim as a naked percentage and get the same treatment.
        # A digits-only percent pattern misses the common case: narration written
        # for the ear spells the number out. "Swords caused four percent of
        # recorded wounds" is the exact shape the SOP warns about and it carries
        # no digit anywhere.
        "re": re.compile(
            r"(\b(?:\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten|"
            r"eleven|twelve|fifteen|twenty|thirty|forty|fifty|sixty|seventy|"
            r"eighty|ninety)\s*(?:%|per ?cent)|\bone in (?:a )?\w+|"
            r"\b(?:half|a third|two thirds|three quarters|a quarter|most|"
            r"nearly all|almost all|the majority)\s+(?:of\s+)?(?:the\s+)?[a-z]+|"
            r"\b\d+\s*(?:times|x)\s+(?:more|less|faster|stronger|heavier))", re.I),
    },
    {
        "id": 6,
        "name": "superlative about material or performance",
        "rule": "These invite the counter-example, and the counter-example always "
                "exists. Keep the material's DOCUMENTED property and drop the ranking.",
        "re": re.compile(
            r"\b(hardest|sharpest|strongest|toughest|finest|heaviest|fastest|"
            r"unbreakable|indestructible|superior to|centuries ahead|"
            r"ahead of its time|most advanced|best[- ]made|never (?:broke|failed|"
            r"bent)|could cut through)\b", re.I),
    },
]

# Type 7 is different in kind and needs its own pass, so it is not a regex row.
TYPE7 = {
    "id": 7,
    "name": "invented connective detail",
    "rule": "The most dangerous type: there is no wrong fact to catch, only a fact "
            "that was never there. EVERY concrete detail in a scene must trace to a "
            "source, including detail that merely decorates a true event. If a scene "
            "needs an image the record does not supply, use a different image or "
            "state the gap.",
}

# A scene sentence: physical motion or place, painted concretely. It becomes a
# type-7 candidate when it carries no DATE and no NUMBER.
#
# A proper noun deliberately does NOT count as an anchor here. The SOP's own
# verified failure -- "captured sabers travelled home in the baggage of half the
# armies of Europe" -- contains one, and "Europe" is exactly the vague
# geographic gesture that decorates a scene rather than sourcing it. Counting it
# as an anchor excluded the one sentence this scan exists to find.
SCENE_RE = re.compile(
    r"\b(carried|travel(?:l?ed|s)|marched|rode|sailed|dragged|hauled|piled|"
    r"stacked|scattered|buried|hidden|stowed|packed|loaded|rolled|drifted|"
    r"lay|sat|stood|hung|filled|lined|crossed|climbed|slipped|crept|"
    r"baggage|wagons|carts|saddlebags|holds|streets|fields|camps|tents)\b", re.I)
DATE_RE = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9]|[1-9][0-9]?(?:st|nd|rd|th) century|"
                     r"\bBCE?\b|\bAD\b)", re.I)
NUM_RE = re.compile(r"\b\d[\d,.]*\b|\b(?:one|two|three|four|five|six|seven|eight|"
                    r"nine|ten|twenty|thirty|forty|fifty|hundred|thousand)\b", re.I)
# Cadence: the sentences that sound best. A tricolon (three parallel items) and
# a short punch after a long build are the two shapes that produced every error
# in the SOP's first Stage 5A run.
TRICOLON_RE = re.compile(r"[^,.]{4,40},[^,.]{4,40},\s*(?:and\s+)?[^,.]{4,40}[.?!]?$")
NEGATE_RE = re.compile(r"\b(?:was|were|is|are|it'?s)\s+not\s+\w+[^.]{0,40},\s*(?:it|they)?\s*"
                       r"(?:was|were|is|are)?\s*\w+", re.I)


def read_entries(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().split("\n")
    entries, cur = [], {"title": "(before first header)", "text": ""}
    for ln in lines:
        if _BACK_MATTER.match(ln):
            break
        m = _H2.match(ln)
        if m:
            if cur["text"].strip():
                entries.append(cur)
            cur = {"title": m.group(1).strip(" *#"), "text": ""}
        elif not ln.startswith("#"):
            cur["text"] += " " + ln
    if cur["text"].strip():
        entries.append(cur)
    return entries


def scan_entry(entry):
    hits = {}
    for sent in sentences(entry["text"]):
        for ct in CLAIM_TYPES:
            if ct["re"].search(sent):
                hits.setdefault(ct["id"], []).append(sent)
        # Type 7: concrete scene, no date and no number holding it down.
        if SCENE_RE.search(sent) and not DATE_RE.search(sent) \
                and not NUM_RE.search(sent):
            hits.setdefault(7, []).append(sent)
        # Cadence candidates, tracked separately from the claim types.
        if TRICOLON_RE.search(sent) or NEGATE_RE.search(sent):
            hits.setdefault("cadence", []).append(sent)
    return hits


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--type", type=int, choices=range(1, 8),
                    help="show only one claim type")
    a = ap.parse_args()

    entries = read_entries(a.script)
    if not entries:
        raise SystemExit(f"No '## ' section headers found in {a.script}.")

    by_type = {ct["id"]: ct for ct in CLAIM_TYPES}
    by_type[7] = TYPE7
    results, total = [], 0

    for e in entries:
        hits = scan_entry(e)
        if a.type:
            hits = {k: v for k, v in hits.items() if k == a.type}
        results.append({"entry": e["title"], "hits": hits})
        total += sum(len(v) for k, v in hits.items() if k != "cadence")

    if a.json:
        print(json.dumps(results, indent=2))
        return 0

    print("\n" + "=" * 72)
    print("  STAGE 5A — HIGH-RISK CLAIM WORKSHEET")
    print(f"  {a.script}")
    print("=" * 72)
    print("\n  This finds sentences by SHAPE. It verifies nothing. Open a real")
    print("  source for every line below — not memory, and not the dossier's")
    print("  summary of a source, because compression is where these errors are")
    print("  born.\n")

    for r in results:
        claim_hits = {k: v for k, v in r["hits"].items() if k != "cadence"}
        cadence = r["hits"].get("cadence", [])
        if not claim_hits and not cadence:
            continue
        print("-" * 72)
        print(f"  ENTRY: {r['entry']}")
        print("-" * 72)
        for tid in sorted(claim_hits, key=lambda x: (isinstance(x, str), x)):
            ct = by_type[tid]
            print(f"\n  [TYPE {ct['id']}] {ct['name'].upper()}")
            print(f"      rule: {ct['rule']}")
            for s in claim_hits[tid]:
                print(f"\n      · {s}")
                print(f"        SOURCE: ______________________________________")
        if cadence:
            print(f"\n  [CADENCE] sentences that read best — verify these hardest")
            print(f"      rule: every error in the first Stage 5A run arrived as an")
            print(f"            improvement to rhythm. Fluency is the tell, not the")
            print(f"            defence.")
            for s in cadence:
                print(f"\n      · {s}")
                print(f"        SOURCE: ______________________________________")
        print()

    print("=" * 72)
    print(f"  {total} claim-type hits across {len(entries)} entries.")
    print("\n  Still owed after this worksheet, and NOT automated:")
    print("    - the dossier re-read: flagged risks against the finished prose,")
    print("      line by line. The dossier flagged all three errors in the first")
    print("      run and the draft contradicted its own research anyway.")
    print("    - the comment-police pre-mortem: one line per entry naming the")
    print("      correction a knowledgeable viewer would most likely leave.")
    print("    - Stage 5B: report which checks actually ran. A clean scan here is")
    print("      a clean SHAPE scan, never an accuracy pass.")
    print("=" * 72 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
