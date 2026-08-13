#!/usr/bin/env python3
"""
Dramatic-overlay compliance — measure a draft against the StickTory profile.

The dramatic voice state is ported from StickTory, whose template carries a
numeric rhythm and humor profile reverse-engineered from its top 8 videos.
Nothing in the ExplainTory battery measures any of it, so "did the overlay
actually get applied" has been an eyeball judgement. This makes the measurable
half measurable.

TWO MODES, because the port is partial and the differences are not cosmetic.

    --mode explaintory   (default)  the port as ExplainTory runs it
    --mode sticktory                the source profile, unmodified

Three rules invert between them. They are checked, not averaged:

  1. SECOND PERSON. StickTory's entire format is "you are the character" —
     2nd person present tense is the spine. ExplainTory does not adopt it, and
     its linter bans you/your outright. So: required in sticktory mode, must be
     ZERO in explaintory mode.

  2. HEDGING. StickTory says never hedge, just assert it. ExplainTory Stage 5A
     says the opposite and says it for a reason -- causation drawn by
     archaeologists is narrated as such, tradition is framed as tradition, and
     the gap becomes a beat. This is the dangerous conflict: importing "just
     assert it" would reintroduce the exact class of error that reaches the
     comments and gets timestamped. Attribution is REQUIRED in explaintory
     mode and flagged in sticktory mode.

  3. "basically". A signature StickTory tic, ~20x across its outliers, its most
     common filler. The ExplainTory linter caps it at 3. The cap wins in
     explaintory mode.

WHAT THIS CANNOT DO. The template is explicit and it is right:

    "keyword humor scorers are noisy and undercount novel phrasings -- judge by
     reading ALOUD, not a number."

So the humor figure here is reported as a FLOOR, never as a score. A draft can
clear it and be unfunny, and a genuinely funny draft written in fresh phrasings
will score below it. Read it aloud. The same applies to the dramatic engine --
agency, a villain with a face, the Big Mistake are judged, not counted, and
they are the part that decides whether the script works.
"""
import argparse
import json
import re
import statistics
import sys

# --- profile targets, from the template's own numbers -------------------------
RHYTHM = {
    "avg_words":     (7.5, 9.5),     # ~8.5
    "frag_pct":      (22.0, 35.0),   # ~28%, fragments <= 4 words
    "short_pct":     (50.0, 68.0),   # ~59%, <= 8 words
    "long_pct":      (2.0, 9.0),     # ~5%, >= 20 words
}
MAX_LONG_RUN = 2                     # never 3 long sentences in a row
HUMOR_PER_100 = 2.3
REACTING_TARGET = 6
ANACHRONISM_MIN = 4
WPM_STICKTORY = 165.0
WPM_EXPLAINTORY = 185.0

_H2 = re.compile(r"^##\s+(.+?)\s*$")
_BACK = re.compile(r"^#{1,6}\s*(pronunciation|audit|appendix|source|animator|"
                   r"production|research|variety|authenticity)", re.I)
_ABBREV = r"(?<!\bMr)(?<!\bMrs)(?<!\bDr)(?<!\bSt)(?<!\bNo)(?<!\bvs)"
_SENT = re.compile(_ABBREV + r"(?<=[.!?])[\"'”’)\]]*\s+")

SECOND_PERSON = re.compile(r"\b(you|your|yours|yourself|yourselves|you're|youre)\b", re.I)

# Lever 4, the reacting narrator: the template calls it the biggest lever and
# the easiest to miss -- outliers ~6x per script, weak drafts ~1x.
REACTING = re.compile(
    r"\b(are you serious|guess what|imagine|good luck with that|surprise|"
    r"no pressure|right\?\s*\.{0,3}\s*right|but hey|and just like that|"
    r"look at that|trust me|spoiler alert|and when i say)\b", re.I)

# Lever 1, anachronism: the main engine. Modern register against a period setting.
ANACHRONISM = re.compile(
    r"\b(jackpot|level up|game over|9[- ]to[- ]5|nine[- ]to[- ]five|starter pack|"
    r"amazon prime|spotify|playlist|k[- ]pop|barbie|sugar daddy|influencer|"
    r"linkedin|resume|résumé|promotion|hr\b|paperwork|customer service|"
    r"subscription|hit the gym|side hustle|networking|performance review|"
    r"job interview|corporate|middle management|tuesday)\b", re.I)

# Lever 2/3, sarcastic aside and dark-comic undercut.
SARCASM = re.compile(
    r"\b(congratulations|congrats|cute\b|romantic\b|great role model|"
    r"very healthy|lovely|charming|delightful|fantastic|wonderful|"
    r"what could go wrong|as one does|naturally\b|obviously\b)\b", re.I)

# Lever 5, casual tics. Kept even through dark stretches so drama does not
# drift earnest or literary.
TICS = re.compile(r"\b(basically|honestly|literally|actually|anyway|look,|okay,|"
                  r"yeah|nope|sure\b)\b", re.I)

OPEN_LOOPS = [
    (r"that changes everything", "changes everything"),
    (r"hopefully,? that'?s not foreshadowing", "foreshadowing"),
    (r"big mistake", "big mistake"),
    (r"you jinxed it", "jinxed it"),
    (r"spoiler alert", "spoiler alert"),
    (r"you'?re next in line", "next in line"),
    (r"no pressure,? right", "no pressure"),
]

TELEGRAPH = re.compile(
    r"(that'?s your mistake,? by the way|which (?:is|was) your mistake|"
    r"you'?ll regret (?:this|that) later|as you'?ll (?:soon )?find out|"
    r"little did (?:you|they|he|she) know|what you don'?t know yet is)", re.I)

# StickTory's NEVER USE list. Most of it overlaps ExplainTory's anti-slop scan,
# which is a good sign -- two independently derived lists agreeing.
BANNED = ["furthermore", "moreover", "in conclusion", "it's important to note",
          "let's dive in", "delve", "tapestry", "nestled",
          "stands as a testament", "weave", "little did they know",
          "have you ever wondered"]

# Attribution: required by ExplainTory Stage 5A, banned by StickTory.
HEDGE = re.compile(
    r"\b(historians (?:believe|argue|think)|records suggest|tradition (?:says|holds)|"
    r"reputation says|scholars (?:believe|argue)|according to|"
    r"(?:is|are) (?:thought|believed|said) to|no source|not attested|"
    r"the leading reading|archaeologists (?:argue|read|infer))\b", re.I)


def sentences(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    return [s.strip() for s in _SENT.split(text) if s.strip()] if text else []


def words(t):
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9'’\-]*", t or "")


def read_body(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().split("\n")
    out, beats, cur = [], [], None
    for ln in lines:
        if _BACK.match(ln):
            break
        m = _H2.match(ln)
        if m:
            cur = {"title": m.group(1).strip(" *#"), "text": ""}
            beats.append(cur)
        elif not ln.startswith("#") and ln.strip():
            out.append(ln.strip())
            if cur:
                cur["text"] += " " + ln.strip()
    return "\n".join(out), beats


class Check:
    def __init__(self, name, ok, detail, fix=None, severity="fail"):
        self.name, self.ok, self.detail = name, ok, detail
        self.fix, self.severity = fix, severity

    def d(self):
        return {"check": self.name, "ok": self.ok, "detail": self.detail,
                "fix": self.fix, "severity": self.severity}


def analyse(body, beats, mode):
    sents = sentences(body)
    if not sents:
        raise SystemExit("No narration found.")
    slens = [len(words(s)) for s in sents]
    n = len(sents)
    total_w = sum(slens)
    c = []

    frag = sum(1 for x in slens if x <= 4) / n * 100
    short = sum(1 for x in slens if x <= 8) / n * 100
    lng = sum(1 for x in slens if x >= 20) / n * 100
    avg = statistics.mean(slens)

    # Per-key, per-direction guidance. A single shared message got this exactly
    # backwards on every "too low" case -- it told a draft whose sentences were
    # already too short to add more fragments, which is the opposite of the fix
    # and would drive the number further out of band on the next pass.
    RHYTHM_FIX = {
        "avg_words": ("sentences run long — cut them down and punch with 1-3 word "
                      "fragments",
                      "sentences are all clipped — let some run; the profile is "
                      "short-short-FRAGMENT-longer, not short everywhere"),
        "frag_pct": ("too many fragments — let more sentences breathe into full "
                     "clauses",
                     "too few fragments — punch with 'Nope.' 'Big mistake.' "
                     "'Wait, what?'"),
        "short_pct": ("too much short — one flowing sentence, then snap back",
                      "not enough short — the velocity comes from ≤8 word lines"),
        "long_pct": ("too many long sentences — split the worst offenders",
                     "no long sentences at all — the rhythm needs one flowing "
                     "line to snap back FROM"),
    }
    for key, val, unit in (("avg_words", avg, ""), ("frag_pct", frag, "%"),
                           ("short_pct", short, "%"), ("long_pct", lng, "%")):
        lo, hi = RHYTHM[key]
        ok = lo <= val <= hi
        c.append(Check(f"rhythm:{key}", ok, f"{val:.2f}{unit} (target {lo}-{hi})",
                       fix=None if ok else RHYTHM_FIX[key][0 if val > hi else 1],
                       severity="warn" if key == "long_pct" else "fail"))

    run = best = 0
    for x in slens:
        run = run + 1 if x >= 20 else 0
        best = max(best, run)
    c.append(Check("rhythm:long_run", best <= MAX_LONG_RUN,
                   f"longest run of ≥20w sentences: {best} (max {MAX_LONG_RUN})",
                   fix="split one of them" if best > MAX_LONG_RUN else None))

    # --- POV, the rule that inverts -----------------------------------------
    pov = len(SECOND_PERSON.findall(body))
    if mode == "explaintory":
        c.append(Check("pov:second_person", pov == 0,
                       f"{pov} hits (must be 0 — the port drops StickTory's 2nd person)",
                       fix="rewrite in third person; the linter bans you/your outright"
                           if pov else None))
    else:
        c.append(Check("pov:second_person", pov > 0,
                       f"{pov} hits (StickTory is 2nd person present, required)",
                       fix="the reader IS the character — rewrite in 'you'" if not pov else None))

    # --- attribution, the dangerous inversion --------------------------------
    hedges = len(HEDGE.findall(body))
    if mode == "explaintory":
        c.append(Check("sourcing:attribution", hedges > 0,
                       f"{hedges} attributed claims",
                       fix="Stage 5A requires inference and tradition be narrated as "
                           "such. StickTory's 'never hedge, just assert it' is NOT "
                           "ported — it produces the errors that get timestamped."
                           if not hedges else None))
    else:
        c.append(Check("sourcing:attribution", hedges == 0,
                       f"{hedges} hedges (StickTory asserts, never hedges)",
                       fix="drop the hedging" if hedges else None, severity="warn"))

    # --- humor, reported as a floor -----------------------------------------
    hum = (len(REACTING.findall(body)) + len(ANACHRONISM.findall(body))
           + len(SARCASM.findall(body)) + len(TICS.findall(body)))
    per100 = hum / max(total_w, 1) * 100
    c.append(Check("humor:floor", per100 >= HUMOR_PER_100,
                   f"{per100:.1f} signals/100w (floor {HUMOR_PER_100}) — "
                   f"UNDERCOUNTS novel phrasing, judge by reading aloud",
                   fix="thin — the institutional/setup beats are the comedy playground"
                       if per100 < HUMOR_PER_100 else None,
                   severity="warn"))

    react = len(REACTING.findall(body))
    c.append(Check("humor:reacting_narrator", react >= REACTING_TARGET,
                   f"{react} (outliers ~{REACTING_TARGET}, weak drafts ~1)",
                   fix="the biggest lever and the easiest to miss — react out loud "
                       "to the absurdity alongside the viewer" if react < REACTING_TARGET
                       else None, severity="warn"))

    anach = len(ANACHRONISM.findall(body))
    c.append(Check("humor:anachronism", anach >= ANACHRONISM_MIN,
                   f"{anach} (min {ANACHRONISM_MIN})",
                   fix="compare the period to modern life" if anach < ANACHRONISM_MIN
                       else None, severity="warn"))

    # --- open loops ---------------------------------------------------------
    used = {}
    for pat, label in OPEN_LOOPS:
        k = len(re.findall(pat, body, re.I))
        if k:
            used[label] = k
    repeated = {k: v for k, v in used.items() if v > 1}
    c.append(Check("loops:rotation", not repeated,
                   f"{len(used)} distinct" + (f", repeated: {repeated}" if repeated else ""),
                   fix="rotate the phrasing, do not repeat the same one twice"
                       if repeated else None, severity="warn"))

    tele = TELEGRAPH.findall(body)
    c.append(Check("engine:no_telegraph", not tele,
                   "clean" if not tele else f"{len(tele)}: {tele[:3]}",
                   fix="never pre-explain the mistake — 'Big mistake' lands only AT "
                       "the reversal" if tele else None))

    hits = {p: len(re.findall(r"(?<!\w)" + re.escape(p) + r"(?!\w)", body, re.I))
            for p in BANNED}
    hits = {k: v for k, v in hits.items() if v}
    c.append(Check("banned_phrases", not hits,
                   "none" if not hits else ", ".join(f"'{k}'x{v}" for k, v in hits.items()),
                   fix="rewrite those lines" if hits else None))

    # --- basically, the third inversion --------------------------------------
    bas = len(re.findall(r"\bbasically\b", body, re.I))
    if mode == "explaintory":
        c.append(Check("tic:basically", bas <= 3,
                       f"{bas} (ExplainTory linter caps at 3; StickTory uses ~20 as a "
                       f"signature tic — the cap wins here)",
                       fix="cut back to 3" if bas > 3 else None))
    else:
        c.append(Check("tic:basically", True, f"{bas} (StickTory's most common filler)",
                       severity="warn"))

    # --- the ending ----------------------------------------------------------
    if beats:
        last = sentences(beats[-1]["text"])
        tail = last[-1] if last else ""
        joke = bool(SARCASM.search(tail) or ANACHRONISM.search(tail)
                    or REACTING.search(tail))
        c.append(Check("ending:cold", not joke,
                       f"final line: {tail[:60]!r}",
                       fix="the body undercuts, the final line lands cold — never a "
                           "joke after the last line" if joke else None))

    wpm = WPM_STICKTORY if mode == "sticktory" else WPM_EXPLAINTORY
    return {
        "mode": mode,
        "totals": {"words": total_w, "sentences": n,
                   "runtime": f"{int(total_w / wpm)}:{int(total_w / wpm % 1 * 60):02d}",
                   "wpm_used": wpm, "beats": len(beats)},
        "checks": [x.d() for x in c],
        "edit_list": [f"[{x.name}] {x.fix}" for x in c if not x.ok and x.fix],
        "passed": all(x.ok for x in c if x.severity == "fail"),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script")
    ap.add_argument("--mode", default="explaintory",
                    choices=["explaintory", "sticktory"])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    body, beats = read_body(a.script)
    r = analyse(body, beats, a.mode)

    if a.json:
        print(json.dumps(r, indent=2))
        return 0 if r["passed"] else 1

    t = r["totals"]
    print(f"\n  DRAMATIC OVERLAY · mode={r['mode']} · {t['words']} words · "
          f"{t['sentences']} sentences · ~{t['runtime']} at {t['wpm_used']:g} wpm\n")
    for x in r["checks"]:
        mark = "PASS" if x["ok"] else ("WARN" if x["severity"] == "warn" else "FAIL")
        print(f"  [{mark:4}] {x['check']:26} {x['detail']}")
    if r["edit_list"]:
        print("\n  EDIT LIST:")
        for e in r["edit_list"]:
            print(f"    - {e}")
    print("\n  NOT MEASURED — judged by reading aloud:")
    print("    · the dramatic engine: a WANT, a villain with a FACE, a Big Mistake")
    print("      caused by your own trust. This is what decides if it works.")
    print("    · whether the payoff BREATHES before moving on.")
    print("    · whether the humor is funny. The floor above undercounts novel")
    print("      phrasing and a draft can clear it and still be flat.")
    print(f"\n  => {'PASS' if r['passed'] else 'FAIL'}\n")
    return 0 if r["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
