#!/usr/bin/env python3
"""
Two questions the battery never asked: can a viewer follow it, and can the
animator draw it.

The existing checks cover accuracy, structure, pattern discipline and rhythm.
Nothing measures whether the prose is SIMPLE, and nothing reports drawability
as a per-entry figure -- the deadzone scan finds individual dead sentences, but
an entry can be 60% unanchored without ever producing two consecutive ones.

So this measures both, and reports them as the same concern, because they are:
a sentence that names a physical thing is easier to picture AND easier to
follow. Abstraction hurts the viewer and the animator in one move.

READING LEVEL. Flesch-Kincaid grade, reported TWICE:

    with names      what the raw text scores
    without names   the same text with proper nouns replaced by a one-syllable
                    token

The second number is the one to steer by. This channel's subjects are full of
long unavoidable proper nouns -- Hybertsson, tamahagane, Schienenzeppelin --
which inflate every syllable-based score without making the PROSE harder. A
script can read at grade 11 with names and grade 7 without, and grade 7 is the
truth about the writing. Cutting real words to compensate for a name you cannot
cut makes the script worse, not simpler.

Target is 6th-8th grade, the StickTory template's stated band. It is a ceiling
on difficulty, not a target to hit exactly; grade 5 prose about siege engines
is not a problem.

DRAWABILITY. Per entry, the share of sentences naming something physical,
using the LINTER'S OWN concrete lexicon rather than a second one invented here
-- that lexicon carries deliberate exclusions (documents, "spring", "lead",
"mail") that a fresh list would get wrong, and two lexicons would drift.

WHAT THIS IS NOT. A readability score is not comprehension. Short words in
short sentences can still describe a mechanism nobody follows, and the fix for
that is the SOP's comprehension analogy, which is judged and not counted. The
grade number tells you the prose is not the obstacle. It cannot tell you the
explanation landed.
"""
import argparse
import importlib.util
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import overlay as ov            # noqa: E402


def load_lint():
    """Reuse the linter's concrete lexicon rather than forking it."""
    for name in ("lint-v3_2.py", "lint-v3_1.py"):
        p = os.path.join(HERE, name)
        if os.path.isfile(p):
            spec = importlib.util.spec_from_file_location("lintmod", p)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m
    raise SystemExit("Could not find the linter next to this script.")


ERA_RE = None      # compiled at import, after ERA_WORDS is defined

GRADE_MAX = 8.0
DRAWABLE_MIN = 0.60          # share of sentences per entry naming something physical
HARD_WORD_MAX = 12.0         # % of non-name words at 3+ syllables

_VOWELS = "aeiouy"


def syllables(word):
    """
    Vowel-group count with the usual corrections. Approximate by construction --
    English spelling does not support an exact rule -- but consistent, which is
    what matters when the number is compared against a band and against another
    draft rather than read as truth.
    """
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    if len(w) <= 3:
        return 1
    w = re.sub(r"(?:[^laeiouy]es|[^laeiouy]e)$", "", w)   # silent e, -es
    w = re.sub(r"^y", "", w)
    groups = re.findall(r"[aeiouy]+", w)
    return max(1, len(groups))


def is_proper(tok, first_in_sentence):
    return bool(re.match(r"^[A-Z][a-z’']", tok)) and not first_in_sentence


def flesch(text, strip_names=False):
    sents = ov.sentences(text)
    if not sents:
        return None, None, 0, 0
    n_sent = len(sents)
    n_word = n_syll = 0
    for s in sents:
        toks = re.findall(r"[A-Za-z][A-Za-z’'-]*", s)
        for i, t in enumerate(toks):
            n_word += 1
            if strip_names and is_proper(t, i == 0):
                n_syll += 1          # names cost one syllable, not their real count
            else:
                n_syll += syllables(t)
    if not n_word:
        return None, None, 0, 0
    wps, spw = n_word / n_sent, n_syll / n_word
    grade = 0.39 * wps + 11.8 * spw - 15.59
    ease = 206.835 - 1.015 * wps - 84.6 * spw
    return grade, ease, n_word, n_sent


def hard_words(text):
    """3+ syllable words that are not proper nouns. The comprehension tax."""
    out = []
    for s in ov.sentences(text):
        toks = re.findall(r"[A-Za-z][A-Za-z’'-]*", s)
        for i, t in enumerate(toks):
            if is_proper(t, i == 0):
                continue
            if syllables(t) >= 3 and len(t) > 6:
                out.append(t.lower())
    return out


# The linter's lexicon was built for this channel's naval and modern-weapons
# videos. It carries hull, turret, torpedo and propeller, and it has no chariot,
# no axle, no javelin, no parapet, no trebuchet. On a pre-modern subject that is
# not a drawability problem, it is a coverage gap: "Two hundred chariots" scored
# as an unanchored sentence. Chasing that number rewrites good prose to satisfy
# a word list built for a different video.
#
# So the linter's lexicon is EXTENDED here rather than replaced. Same rule as the
# original: a word earns its place only if nearly every use of it puts something
# on screen. False negatives stay cheap; false exemptions do not.
ERA_WORDS = r"""
chariot chariots axle axles wheelhub yoke rein reins harness stirrup saddle
javelin javelins sling slings dart darts quiver lance lances halberd glaive
trebuchet catapult ballista onager mangonel counterweight sling-arm siege
rampart ramparts parapet parapets battlement battlements portcullis drawbridge
moat palisade stockade earthwork earthworks breach breaches masonry mortar
tower towers turret keep bailey barbican buttress vault vaulting arch arches
scaffold beam beams plank planks joist rivet rivets bolt pin pins peg pegs
cylinder cylinders valve valves siphon nozzle hose bellows crucible mould
foundryman founder forge anvil tongs quench
deck decks rail rails rigging shroud shrouds yard yardarm gunwale hatch
stock barrel muzzle breech flintlock trigger hammer ramrod cartridge cartridges
bore liner shell shells casing fuse primer propellant charge wadding
picks baskets spade spades shovel trench parapet dugout sandbag sandbags
"""


ERA_RE = re.compile(r"\b(" + "|".join(sorted(set(ERA_WORDS.split()), key=len, reverse=True)) + r")\b", re.I)


def drawability(text, concrete_re, unit_re):
    """Share of sentences naming something physical, plus the ones that do not."""
    sents = ov.sentences(text)
    if not sents:
        return 1.0, []
    dead = []
    hit = 0
    for s in sents:
        if concrete_re.search(s) or unit_re.search(s) or ERA_RE.search(s):
            hit += 1
        else:
            dead.append(s)
    return hit / len(sents), dead


def band_grade_conformance(grade, target=GRADE_MAX):
    """1.0 at or below target, decaying to 0 four grades above it."""
    if grade is None:
        return 0.0
    return 1.0 if grade <= target else max(0.0, 1.0 - (grade - target) / 4.0)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script")
    ap.add_argument("--grade-max", type=float, default=GRADE_MAX)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    lint = load_lint()
    body, beats = ov.read_body(a.script)
    if not body.strip():
        raise SystemExit(f"No narration found in {a.script}.")

    g_raw, e_raw, nw, ns = flesch(body, strip_names=False)
    g_clean, e_clean, _, _ = flesch(body, strip_names=True)

    hw = hard_words(body)
    hw_rate = len(hw) / max(nw, 1) * 100
    freq = {}
    for w in hw:
        freq[w] = freq.get(w, 0) + 1
    worst_words = sorted(freq.items(), key=lambda kv: -kv[1])[:10]

    draw_all, _ = drawability(body, lint.CONCRETE_RE, lint.UNIT_RE)

    per_entry = []
    for b in beats:
        share, dead = drawability(b["text"], lint.CONCRETE_RE, lint.UNIT_RE)
        g, _, w, _ = flesch(b["text"], strip_names=True)
        per_entry.append({"title": b["title"], "drawable": share,
                          "grade": g, "words": w, "dead": dead})

    # The hardest sentences by the two things that actually block a viewer:
    # length and syllable load. These are the lines to rewrite, named.
    # Ranking on length x load alone surfaced "Six boilers, six propellers, two
    # eleven-inch guns in an open barbette" -- plain, concrete, exactly the
    # channel's voice -- as a top offender, because it is moderately long. A
    # list that names good sentences teaches the writer to skip the list. So a
    # sentence has to be genuinely dense OR genuinely sprawling to appear at
    # all; below those thresholds, length is not a comprehension problem.
    LOAD_FLOOR, LONG_FLOOR = 1.80, 30
    ranked = []
    for s in ov.sentences(body):
        toks = re.findall(r"[A-Za-z][A-Za-z’'-]*", s)
        if len(toks) < 5:
            continue
        load = sum(syllables(t) for i, t in enumerate(toks)
                   if not is_proper(t, i == 0)) / max(len(toks), 1)
        if load < LOAD_FLOOR and len(toks) < LONG_FLOOR:
            continue
        ranked.append((len(toks) * load, len(toks), round(load, 2), s))
    ranked.sort(reverse=True)

    checks = [
        ("reading_grade", g_clean <= a.grade_max,
         f"{g_clean:.1f} without names (target ≤{a.grade_max:g}) · "
         f"{g_raw:.1f} with names · ease {e_clean:.0f}"),
        ("hard_words", hw_rate <= HARD_WORD_MAX,
         f"{hw_rate:.1f}% of non-name words are 3+ syllables (max {HARD_WORD_MAX:g}%)"),
        ("drawable_overall", draw_all >= DRAWABLE_MIN,
         f"{draw_all * 100:.1f}% of sentences name something physical "
         f"(min {DRAWABLE_MIN * 100:.0f}%)"),
    ]
    thin = [e for e in per_entry if e["drawable"] < DRAWABLE_MIN]
    checks.append(("drawable_per_entry", not thin,
                   "all entries clear" if not thin else
                   ", ".join(f"{e['title'][:22]} {e['drawable'] * 100:.1f}%" for e in thin)))

    passed = all(ok for _, ok, _ in checks)

    if a.json:
        print(json.dumps({
            "grade_without_names": round(g_clean, 2), "grade_with_names": round(g_raw, 2),
            "reading_ease": round(e_clean, 1), "words": nw, "sentences": ns,
            "hard_word_pct": round(hw_rate, 2), "hard_words": worst_words,
            "drawable_overall": round(draw_all, 3),
            "entries": [{k: v for k, v in e.items() if k != "dead"} for e in per_entry],
            "hardest_sentences": [{"words": w, "syll_per_word": l, "text": s}
                                  for _, w, l, s in ranked[:8]],
            "passed": passed}, indent=2))
        return 0 if passed else 1

    print(f"\n  CLARITY · {a.script}")
    print(f"  {nw} words · {ns} sentences · {len(beats)} entries\n")
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:20} {detail}")

    if per_entry:
        print("\n  per entry:")
        print(f"    {'entry':30} {'grade':>6} {'drawable':>9}")
        for e in per_entry:
            mark = " <" if e["drawable"] < DRAWABLE_MIN else ""
            print(f"    {e['title'][:30]:30} {e['grade'] or 0:6.1f} "
                  f"{e['drawable'] * 100:8.0f}%{mark}")

    if ranked:
        print("\n  hardest sentences — rewrite these first:")
        for _, w, load, s in ranked[:5]:
            print(f"    · [{w}w, {load} syll/word] {s[:96]}")

    if worst_words:
        print("\n  most-repeated hard words: "
              + ", ".join(f"{w}({n})" for w, n in worst_words[:8]))

    if thin:
        print("\n  entries the animator cannot draw from:")
        for e in thin[:3]:
            print(f"    {e['title']} — {e['drawable'] * 100:.0f}% anchored")
            for s in e["dead"][:2]:
                print(f"      · {s[:88]}")
            print("      fix: write the visual INTO the sentence, do not hand over a cue sheet")

    print("\n  Grade is reported WITHOUT names because this channel's subjects carry")
    print("  long proper nouns that inflate every syllable score without making the")
    print("  prose harder. Steer by that number; do not cut real words to pay for a")
    print("  name you cannot cut.")
    print("\n  NOT MEASURED: whether the explanation LANDS. Simple words in short")
    print("  sentences can still describe a mechanism nobody follows. That is the")
    print("  SOP's comprehension analogy, one per unfamiliar entry, judged by ear.")
    print(f"\n  => {'PASS' if passed else 'FAIL'}\n")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
