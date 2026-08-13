#!/usr/bin/env python3
"""
Measure an ExplainTory script against its budget and the channel's gates.

Standalone. It imports nothing from the voiceover or sound-design tooling and
nothing from the network. Give it a draft and a target, it gives you numbers and
an edit list. That is the whole contract.

This exists because of one specific waste: writing a script by conversation and
converging on length by feel. That loop costs hours and never lands, because a
language model cannot count its own words -- it estimates them, confidently and
wrongly, and the next instruction ("make it longer") is aimed at the estimate
rather than at the file.

So nothing here asks a model anything. It counts.

Two modes:

    --plan      runtime + chapters  ->  the word budget, before a word is written
    (default)   a draft             ->  every gate scored, and the EXACT edit
                                        list needed to land it

The second mode is the one that ends the loop. It never reports "too long". It
reports "chapter 4 'The Ledger' is 118 words over; cut 118" -- an instruction
executable in a single pass, which is why the loop terminates instead of
oscillating.

Length model, two constants, both calibratable from real scripts with
calibrate.py:

    words = minutes * 180     narration pace, words per minute
    chars = seconds * 14      the same pace expressed in characters

They agree at 4.67 chars/word, which is the arithmetic check that they describe
one voice reading one kind of prose. Runtime is estimated from BOTH and the
wider of the two is reported, so a script never plans to 12 minutes and runs to
13 because one measure flattered it.
"""
import argparse
import json
import os
import re
import statistics
import sys

WPM = 180.0
CHARS_PER_SEC = 14.0

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROFILE = os.path.join(HERE, "..", "script_profile.json")


# --- text utilities ----------------------------------------------------------

# Sentence splitting without a model download. Counting sentences does not need
# a parse, and making this gate depend on a 50 MB model means the gate gets
# skipped on a fresh machine -- which is the only place it ever runs.
_ABBREV = (r"(?<!\bMr)(?<!\bMrs)(?<!\bMs)(?<!\bDr)(?<!\bSt)(?<!\bNo)(?<!\bvs)"
           r"(?<!\bU\.S)(?<!\be\.g)(?<!\bi\.e)(?<!\bJr)(?<!\bSr)")
_SENT_END = re.compile(_ABBREV + r"(?<=[.!?])[\"'”’)\]]*\s+")


def sentences(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    return [s.strip() for s in _SENT_END.split(text) if s.strip()] if text else []


def words(text):
    # Hyphenated compounds count once -- that is how they are read, and how the
    # wpm figure they are measured against was derived.
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9'’\-]*", text or "")


def wc(text):
    return len(words(text))


# Words that are capitalised because a sentence started, not because they name
# anything. Counting them as proper nouns is not a rounding error: on a draft of
# pure waffle it more than tripled the measured fact density and passed a script
# whose only "names" were the words "The" and "It" at the start of sentences.
# The gate has to be harder to satisfy than the prose it is judging.
_TITLE_STOP = re.compile(
    r"^(The|A|An|And|But|So|Then|Now|It|He|She|They|We|You|This|That|These|"
    r"Those|There|Here|His|Her|Its|Their|Our|What|When|Where|Why|How|Who|"
    r"If|As|At|By|For|From|In|Into|Of|On|Or|To|With|Within|After|Before|"
    r"Because|While|Though|Although|Every|Each|Most|Many|Some|No|Not|One|"
    r"Two|Three|Instead|Yet|Still|Even|Once|Until|Since|Both|Neither)$")


def proper_nouns(text):
    """
    Capitalised words that are not merely sentence-initial.

    Within each sentence the first word is skipped outright, and a small stop
    list catches the rest -- a capitalised 'The' after a full stop is not a
    name, and neither is one opening a paragraph.
    """
    found = []
    for sent in sentences(text):
        toks = re.findall(r"[A-Za-z][A-Za-z'’\-]*", sent)
        for i, tok in enumerate(toks):
            if i == 0:
                continue                      # sentence-initial: no information
            if re.match(r"^[A-Z][a-z]{2,}", tok) and not _TITLE_STOP.match(tok):
                found.append(tok)
    return found


def fmt_time(seconds):
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}:{s:02d}"


def strip_markdown(t):
    """Drop emphasis markers. Google Docs exports headings as '## **Coca**'."""
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", t)
    t = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"\1", t)
    return t


# --- structure ---------------------------------------------------------------

# Structural labels. They organise the document for the writer and are not
# chapters -- counting them as chapters is how an 8-chapter script reports 11.
_META_LABELS = re.compile(
    r"^(intro|introduction|outro|hook|conclusion|opening|closing|cta|title|"
    r"script|body|full script|the end|pronunciation.*|sources?|references?)$", re.I)

_SMALL_WORD = re.compile(
    r"^(of|the|and|a|an|in|on|to|for|vs|or|at|by|is|it|with|from|as|but|nor|"
    r"into|onto|upon|over|under|off|out|up|down|near|no)$", re.I)

_GUIDE_HEAD = re.compile(
    r"^\s*#{0,6}\s*\**\s*(pronunciation|pronounciation|pronunciations|"
    r"pronounce|how to say|say it)\b[^\n]{0,40}$", re.I)
_GUIDE_LINE = re.compile(r"^[\s\t]*[-*•●○·▪‣]?[\s\t]*(.+?)\s*[—–\-:=]\s+(.+?)\s*$")

# Blocks that live after the script and are never narrated. An animator note can
# run to hundreds of lines, so the whole document is searched for these, not
# just its tail -- a fixed tail window misses the guide heading entirely when a
# long note follows it.
_APPENDIX_HEAD = re.compile(
    r"^\s*#{0,6}\s*\**\s*(animator|animation|art|visual|thumbnail|production|"
    r"reference|source|research|accuracy|note)s?\b[^\n]{0,60}$", re.I)


def is_heading(line, prev_blank, next_blank, max_words):
    """
    A line alone in its own block, short, capitalised, unpunctuated at the end.

    Requiring blank lines either side is what keeps a short sentence inside a
    paragraph from being promoted to a chapter title. A markdown '#' prefix is
    an explicit override and skips the shape test entirely.
    """
    s = line.strip()
    if not s:
        return False
    if re.match(r"^#{1,6}\s+\S", s):
        return True
    if not (prev_blank and next_blank):
        return False
    if len(s) > 60 or re.search(r"[.!?…,;:][\"'”’)]*$", s):
        return False
    if re.match(r"^[\"'“”‘’\-–—]", s):
        return False
    ws = s.split()
    if not ws or len(ws) > max_words:
        return False
    if not re.match(r"^[A-Z0-9]", s):
        return False
    for w in ws:
        w = re.sub(r"^[\"'“‘(]+|[\"'”’)]+$", "", w)
        if w and not re.match(r"^[A-Z0-9]", w) and not _SMALL_WORD.match(w):
            return False            # a lowercase content word means it is prose
    return True


def split_appendices(text):
    """-> (script, {name: respelling})   Guide and any appendix cut off the end."""
    lines = text.split("\n")
    guide, cut = {}, None

    for i, ln in enumerate(lines):
        if _GUIDE_HEAD.match(ln):
            tail = [x for x in lines[i + 1:] if x.strip()]
            # One entry is enough -- the heading already had to say
            # "pronunciation" outright -- but most of what follows must look
            # like entries, so a heading followed by prose is left alone.
            if tail and sum(1 for x in tail if _GUIDE_LINE.match(x)) >= max(1, len(tail) * 0.6):
                for sub in lines[i + 1:]:
                    m = _GUIDE_LINE.match(sub)
                    if m:
                        w, say = m.group(1).strip(" *-•_"), m.group(2).strip(" *_")
                        if w and say:
                            guide.setdefault(w, say)
                cut = i
                break

    for i, ln in enumerate(lines):
        if _APPENDIX_HEAD.match(ln) and not _GUIDE_HEAD.match(ln):
            cut = i if cut is None else min(cut, i)
            break

    return ("\n".join(lines[:cut]).rstrip() if cut is not None else text), guide


def parse_draft(raw, profile):
    """Split a draft into title, chapters and narration, in that order."""
    body, guide = split_appendices(raw)
    max_w = profile["structure"]["chapter_title_max_words"]

    lines = body.split("\n")

    def blank(i):
        return i < 0 or i >= len(lines) or not lines[i].strip()

    title, chapters, narration, current = None, [], [], None
    # The hook is every narration block before the first chapter title. Tracked
    # here rather than recovered afterwards by string-searching the narration --
    # that search fails whenever the opening line repeats later in the script.
    hook, stage_directions = [], 0

    for i, raw_line in enumerate(lines):
        s = strip_markdown(raw_line.strip())
        if not s:
            continue
        if re.match(r"^\[[^\]]{1,80}\]$", s) or re.fullmatch(r"[-_*=~]{3,}|[—–]{2,}", s):
            stage_directions += 1 if s.startswith("[") else 0
            continue
        if is_heading(raw_line, blank(i - 1), blank(i + 1), max_w):
            clean = strip_markdown(re.sub(r"^#{1,6}\s+", "", s)).strip()
            # An H1 at the very top is the video's title, not chapter one.
            if title is None and not chapters and (
                    re.match(r"^#\s+\S", raw_line.strip()) or i <= 2):
                title = clean
                continue
            if _META_LABELS.match(clean):
                current = None      # structural label: delimits, is not a chapter
                continue
            current = {"index": len(chapters) + 1, "title": clean,
                       "words": 0, "blocks": 0, "text": ""}
            chapters.append(current)
            continue

        narration.append(s)
        if current is None:
            hook.append(s)
        else:
            current["words"] += wc(s)
            current["blocks"] += 1
            current["text"] += " " + s

    return {"title": title, "chapters": chapters, "guide": guide,
            "narration": "\n\n".join(narration), "hook": "\n\n".join(hook),
            "stage_directions": stage_directions}


# --- profile / budget --------------------------------------------------------

def load_profile(path):
    p = os.path.abspath(os.path.expanduser(path or DEFAULT_PROFILE))
    if not os.path.isfile(p):
        raise SystemExit(f"No profile at {p}. Run calibrate.py to build one.")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def budget(runtime_min, n_chapters, profile):
    """
    Turn a target runtime into a per-chapter word budget.

    Hook and outro come off the top as FIXED costs before the rest is divided,
    because they do not scale with length: a 20-minute video does not get a
    90-second hook. Sizing them as a share of the total is how a long script
    ends up with an opening nobody reaches the end of.
    """
    wpm = profile["length"].get("wpm", WPM)
    total_words = int(round(runtime_min * wpm))
    hook_w = int(profile["hook"]["target_words"])
    outro_w = int(profile["outro"]["target_words"])

    # Chapter titles are spoken and cost real time. Ignoring them is the
    # difference between a 12:00 plan and a 12:20 read on eight chapters.
    gap_s = float(profile["structure"]["chapter_gap_seconds"])
    title_w = float(profile["structure"]["chapter_title_words"])
    ann = int(round(n_chapters * (title_w + gap_s * wpm / 60.0)))

    body_words = total_words - hook_w - outro_w - ann
    if body_words < n_chapters * 60:
        raise SystemExit(
            f"{runtime_min:g} min over {n_chapters} chapters leaves {body_words} "
            f"words of body -- under 60 a chapter. Fewer chapters, or longer.")

    per, rem = divmod(body_words, n_chapters)
    # The remainder goes to the EARLY chapters. Retention is front-loaded, and a
    # fat final chapter is the one fewest viewers reach.
    chapters = [{"index": i + 1, "target_words": per + (1 if i < rem else 0)}
                for i in range(n_chapters)]

    return {"runtime_target_min": runtime_min, "total_words": total_words,
            "total_chars_estimate": int(round(runtime_min * 60 * CHARS_PER_SEC)),
            "hook_words": hook_w, "outro_words": outro_w,
            "chapter_announcement_cost_words": ann, "body_words": body_words,
            "n_chapters": n_chapters, "chapters": chapters,
            "tolerance_pct": float(profile["length"]["tolerance_pct"])}


# --- gates -------------------------------------------------------------------

class Gate:
    def __init__(self, name, ok, detail, fix=None, severity="fail"):
        self.name, self.ok, self.detail = name, ok, detail
        self.fix, self.severity = fix, severity

    def as_dict(self):
        return {"gate": self.name, "ok": self.ok, "detail": self.detail,
                "fix": self.fix, "severity": self.severity}


def measure(raw, profile, expect_chapters, runtime_min):
    p = parse_draft(raw, profile)
    narration, chapters, guide = p["narration"], p["chapters"], p["guide"]

    total_words, total_chars = wc(narration), len(narration)
    wpm = profile["length"].get("wpm", WPM)
    # Two independent estimates; report the slower. One measure flattering the
    # script is exactly how a 12-minute plan becomes a 13-minute read.
    est_seconds = max(total_words / wpm * 60.0, total_chars / CHARS_PER_SEC)
    sents = sentences(narration)
    slens = [wc(s) for s in sents] or [0]
    g = []

    # --- length ---------------------------------------------------------------
    if runtime_min:
        target = int(round(runtime_min * wpm))
        tol = profile["length"]["tolerance_pct"] / 100.0
        lo, hi = int(target * (1 - tol)), int(target * (1 + tol))
        delta = total_words - target
        ok = lo <= total_words <= hi
        g.append(Gate("length", ok,
                      f"{total_words} words vs target {target} ({delta:+d}, "
                      f"band {lo}-{hi}) · est {fmt_time(est_seconds)} vs "
                      f"{fmt_time(runtime_min * 60)}",
                      fix=None if ok else (f"cut {abs(delta)} words" if delta > 0
                                           else f"add {abs(delta)} words")))

    # --- structure ------------------------------------------------------------
    if expect_chapters is not None:
        ok = len(chapters) == expect_chapters
        g.append(Gate("chapter_count", ok,
                      f"{len(chapters)} parsed, {expect_chapters} intended",
                      fix=None if ok else
                          "a heading is not parsing -- it needs a blank line above and "
                          "below, a capital first letter, "
                          f"{profile['structure']['chapter_title_max_words']} words max, "
                          "and no . ! or ? at the end"))

    low = [c["title"].lower() for c in chapters]
    dup = sorted({t for t in low if low.count(t) > 1})
    g.append(Gate("chapter_titles_unique", not dup,
                  "unique" if not dup else f"repeated: {dup}",
                  fix="rename the repeated heading" if dup else None))

    if chapters:
        mean_w = statistics.mean(c["words"] for c in chapters)
        spread = profile["structure"]["chapter_spread_pct"] / 100.0
        off = [(c, c["words"] - mean_w) for c in chapters
               if abs(c["words"] - mean_w) > mean_w * spread]
        # A chapter far off the mean is the structural defect that reads as
        # "this bit drags". Reported per chapter with its own delta, so the fix
        # is an edit rather than another full rewrite.
        g.append(Gate("chapter_balance", not off,
                      f"mean {mean_w:.0f} words, " + (f"all within {spread * 100:.0f}%"
                          if not off else "; ".join(
                              f"#{c['index']} '{c['title']}' {d:+.0f}" for c, d in off)),
                      fix=None if not off else "; ".join(
                          f"chapter {c['index']} '{c['title']}': "
                          f"{'cut' if d > 0 else 'add'} {abs(int(d))} words" for c, d in off),
                      severity="warn"))

    empty = [c["title"] for c in chapters if c["blocks"] == 0]
    g.append(Gate("no_empty_chapters", not empty,
                  "ok" if not empty else f"no body under: {empty}",
                  fix="every heading needs narration under it" if empty else None))

    tmax = profile["structure"]["chapter_title_max_words"]
    bad = [c["title"] for c in chapters
           if len(c["title"].split()) > tmax or re.search(r"[.!?]$", c["title"])]
    g.append(Gate("heading_format", not bad,
                  "ok" if not bad else f"malformed: {bad}",
                  fix=f"{tmax} words max, no terminal punctuation" if bad else None))

    # --- hook -----------------------------------------------------------------
    # Everything before the first chapter title. A script with no chapters at
    # all has no hook boundary to measure, so the first two blocks stand in --
    # measuring the whole script as "the hook" would fail the gate every time
    # and teach the writer to ignore it.
    hook_text = p["hook"] or "\n\n".join(narration.split("\n\n")[:2])
    hook_w = wc(hook_text)
    hmax = profile["hook"]["max_words"]
    g.append(Gate("hook_length", hook_w <= hmax,
                  f"{hook_w} words (max {hmax}, ~{fmt_time(hook_w / wpm * 60)})",
                  fix=None if hook_w <= hmax else f"cut the opening to {hmax} words"))

    opens = [ph for ph in profile["hook"]["banned_openers"]
             if re.match(r"\s*\W*" + re.escape(ph), hook_text, re.I)]
    g.append(Gate("hook_opener", not opens,
                  "clean" if not opens else f"opens with {opens!r}",
                  fix="open on the concrete fact, not the set-up" if opens else None))

    # A hook with no number and no name is a hook about nothing. Cheapest
    # available proxy for "specific", and specificity is what the first ten
    # seconds are for.
    num = bool(re.search(r"\d", hook_text))
    hook_names = proper_nouns(hook_text)
    prop = bool(hook_names)
    g.append(Gate("hook_concrete", num or prop,
                  f"number={num} names={hook_names[:4] if hook_names else 'none'}",
                  fix="put a number, date or name in the first two sentences"
                      if not (num or prop) else None))

    # --- rhythm ---------------------------------------------------------------
    # Uniform sentence length is the measurable signature of machine-written
    # narration. Real reads swing hard -- a four-word punchline after a
    # thirty-word build. Low deviation means that swing is gone, and it is gone
    # long before anyone calls the script boring.
    sd = statistics.pstdev(slens) if len(slens) > 1 else 0.0
    sd_min = profile["rhythm"]["sentence_len_stdev_min"]
    g.append(Gate("sentence_rhythm", sd >= sd_min,
                  f"stdev {sd:.1f} (min {sd_min}) · mean {statistics.mean(slens):.1f}"
                  f" · range {min(slens)}-{max(slens)}",
                  fix="break long sentences and let a short one land alone"
                      if sd < sd_min else None, severity="warn"))

    lmax = profile["rhythm"]["max_sentence_words"]
    long_s = [s for s in sents if wc(s) > lmax]
    g.append(Gate("sentence_max", not long_s,
                  f"{len(long_s)} sentences over {lmax} words",
                  fix=None if not long_s else
                      "split: " + " | ".join(s[:70] + "…" for s in long_s[:3]),
                  severity="warn"))

    # --- substance ------------------------------------------------------------
    # What separates an explainer from waffle, counted: numbers, dates and
    # proper nouns per 100 words. A script can pass every other gate and still
    # be 2,600 words of nothing. This is the gate that catches that.
    # Spelled-out numbers count too. A script written for the ear says
    # "forty-one ships", and a digit-only count scores that prose at zero and
    # then demands the writer add figures it already has.
    n_num = (len(re.findall(r"\b\d[\d,.]*\b", narration))
             + len(re.findall(r"(?<!\w)(?:one|two|three|four|five|six|seven|eight|"
                              r"nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
                              r"sixteen|seventeen|eighteen|nineteen|twenty|thirty|"
                              r"forty|fifty|sixty|seventy|eighty|ninety|hundred|"
                              r"thousand|million|billion)(?!\w)", narration, re.I)))
    n_prop = len(proper_nouns(narration))
    dens = (n_num + n_prop) / max(total_words, 1) * 100
    dmin = profile["substance"]["facts_per_100_words_min"]
    g.append(Gate("fact_density", dens >= dmin,
                  f"{dens:.1f} per 100 words ({n_num} numbers, {n_prop} names; "
                  f"min {dmin})",
                  fix="replace generalisations with named people, dates, places and "
                      "figures" if dens < dmin else None))

    # --- banned phrases -------------------------------------------------------
    hits = {}
    for ph in profile["banned_phrases"]:
        n = len(re.findall(r"(?<!\w)" + re.escape(ph) + r"(?!\w)", narration, re.I))
        if n:
            hits[ph] = n
    g.append(Gate("banned_phrases", not hits,
                  "none" if not hits else ", ".join(
                      f"'{k}' x{v}" for k, v in sorted(hits.items(), key=lambda kv: -kv[1])),
                  fix=("rewrite those lines: " + ", ".join(list(hits)[:6])) if hits else None))

    # --- deliverable completeness --------------------------------------------
    g.append(Gate("pronunciation_guide", bool(guide),
                  f"{len(guide)} entries" if guide else "missing or unparsed",
                  fix=None if guide else
                      "end with a 'Pronunciation' heading and 'Name — RES-pel-ing' "
                      "entries, one per line"))

    sdir = p["stage_directions"]
    g.append(Gate("no_stage_directions", sdir == 0,
                  "none" if sdir == 0 else f"{sdir} [bracketed] lines",
                  fix="remove them, they belong in the animator note" if sdir else None,
                  severity="warn"))

    return {"totals": {"words": total_words, "chars": total_chars,
                       "estimated_runtime": fmt_time(est_seconds),
                       "estimated_seconds": round(est_seconds, 1),
                       "sentences": len(sents), "chapters": len(chapters),
                       "chars_per_word": round(total_chars / max(total_words, 1), 2),
                       "guide_entries": len(guide or {}),
                       "title": p["title"]},
            "chapters": [{k: v for k, v in c.items() if k != "text"} for c in chapters],
            "gates": [x.as_dict() for x in g],
            "edit_list": [f"[{x.name}] {x.fix}" for x in g if not x.ok and x.fix],
            "passed": all(x.ok for x in g if x.severity == "fail"),
            "warnings": [x.name for x in g if not x.ok and x.severity == "warn"]}


def render_human(r):
    t = r["totals"]
    out = [f"  {t['words']} words · {t['chars']} chars · est {t['estimated_runtime']}"
           f" · {t['chapters']} chapters · {t['sentences']} sentences", ""]
    for x in r["gates"]:
        mark = "PASS" if x["ok"] else ("WARN" if x["severity"] == "warn" else "FAIL")
        out.append(f"  [{mark:4}] {x['gate']:22} {x['detail']}")
    if r["chapters"]:
        out += ["", "  chapters:"]
        for c in r["chapters"]:
            out.append(f"    {c['index']:2}. {c['title'][:38]:38} {c['words']:5} words")
    if r["edit_list"]:
        out += ["", "  EDIT LIST:"] + [f"    - {e}" for e in r["edit_list"]]
    out += ["", f"  => {'PASS' if r['passed'] else 'FAIL'}"
                + (f"  (warnings: {', '.join(r['warnings'])})" if r["warnings"] else "")]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script", nargs="?")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--runtime", type=float)
    ap.add_argument("--chapters", type=int)
    ap.add_argument("--profile")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    profile = load_profile(a.profile)
    runtime = a.runtime or profile["length"]["default_runtime_min"]
    chapters = a.chapters or profile["structure"]["default_chapters"]

    if a.plan:
        b = budget(runtime, chapters, profile)
        if a.json:
            print(json.dumps(b, indent=2))
        else:
            print(f"\n  BUDGET · {runtime:g} min · {chapters} chapters\n")
            print(f"    total          {b['total_words']:5} words  "
                  f"(~{b['total_chars_estimate']} chars)")
            print(f"    hook           {b['hook_words']:5}")
            print(f"    chapter calls  {b['chapter_announcement_cost_words']:5}"
                  f"  (titles + gaps)")
            print(f"    outro          {b['outro_words']:5}")
            print(f"    body           {b['body_words']:5}")
            print(f"\n    per chapter    {b['chapters'][0]['target_words']} words"
                  f"   (±{b['tolerance_pct']:g}% on the total)\n")
        return 0

    if not a.script:
        ap.error("a script path is required unless --plan is given")
    with open(a.script, encoding="utf-8") as f:
        raw = f.read()

    r = measure(raw, profile, chapters, runtime)
    print(json.dumps(r, indent=2) if a.json else "\n" + render_human(r) + "\n")
    return 0 if r["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
