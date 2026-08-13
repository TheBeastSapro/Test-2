#!/usr/bin/env python3
"""
ExplainTory Compliance Linter v3.1
Mechanical verification battery for scripts, per:
  - explaintory-channel-skill v6.3 (pattern thresholds, measured VO rate, fact-density floor)
  - explaintory-scripting-sop v1.2 (Stage 5 compliance battery)
  - explaintory-punchy-dark-wit-overlay v1.0 (second-person ban, em-dash ban)
  - explaintory-weirdest-format skill (superlative-verdict discipline)
  - faceless-scripts-os master (anti-AI-slop scan)

Usage:
  python3 explaintory-lint-v3_1.py script.md [--format listicle|history|every-era]
                                             [--overlay] [--punchline WORD ...]
                                             [--no-deadzone] [--no-density]

CHANGES FROM v3.0
  NEW  deadzone scan (SOP v1.2, Stage 5 item 3). Sentence-level. Flags any
       sentence that leans on a reporting or abstract verb while naming no
       physical object, and classifies it by debt type: sourcing/attribution,
       historiography, institutional aftermath. Singles are REVIEW. TWO OR
       MORE CONSECUTIVE deadzones is a HARD FAIL — that is the failure video
       QC actually surfaced. Sentences in the closing quarter of a section
       are marked ENTRY-END, where the cost is retention as well as animation.
  NEW  fact-density floor (channel skill v6.3, "CRITICAL"; SOP Stage 5 item 8).
       Per section, hard-fails a missing date/year, named individual, or hard
       number. Also warns on filler paragraphs — two or more sentences
       carrying no date, no name, no number and no concrete spec.
  FIX  Stage 5 items 3 and 8 were documented as automated in v3.0 and were
       not. This file closes that gap; the SOP pointer should now read
       explaintory-lint-v3_1.py.

Both new scans are heuristic where the SOP rule is semantic. The deadzone
scan tests for a concrete-noun anchor against a fixed lexicon, and the
name check tests for name SHAPE, not personhood. Read the listed hits;
do not treat a clean run as proof.

Judgment checks still requiring a human/Claude pass: humor density, fact
staging, outcome-type variety, payoff spacing, recognition floor, and
factual accuracy. The battery is mechanical only — note that the Bushnell
dimension error in Warships v2.0 passed every check in this file.
"""

import argparse
import re
import sys

WPM = 185.0  # measured VO rate, channel skill v6.3 (~3.1 words/sec)
KILL_LINE_WORDS = 78  # 25 seconds at measured rate — Fix 1

FORMAT_TARGETS = {
    "listicle":  (1600, 2000),
    "every-era": (1600, 2000),
    "history":   (3300, 4000),
}

THRESHOLDS = [
    ("basically",            r"\bbasically\b",            3),
    ("genuinely",            r"\bgenuinely\b",            2),
    ("actually",             r"\bactually\b",             4),
    ("literally",            r"\bliterally\b",            2),
    ("honestly",             r"\bhonestly\b",             1),
    ('"Here\'s" pattern',    r"\bhere['’]s\b",       3),
    ('"which is/was" aside', r"\bwhich (is|was)\b",       2),
]

ZERO_TOLERANCE = [
    ('"and then" transition',      r"\band then\b"),
    ('announcement transition',    r"\bthe next (era|entry|ship|tactic|weapon|sword|war|battle|one|unit|army)\b"),
    ('announcement transition',    r"\b(what )?came next\b"),
    ('empty word',                 r"\b(game[- ]changing|transformational)\b"),
    ('"Let that sink in"',         r"\blet that sink in\b"),
    ('"what no one tells you"',    r"\bwhat no one tells you\b"),
    ('"Most people" opener',       r"^\s*most (people|historians|folks|viewers)\b"),
]

# --- v3: superlative-verdict scan -----------------------------------------
# The title already promises the superlative. Every time the narration
# repeats it, the script spends credibility instead of building it, and
# states a verdict the viewer should be reaching alone. The format's
# paradox hook states a CONTRADICTION ("warships do not have roofs");
# it must never state a VERDICT ("this was the strangest ship").
#
# Not every hit is a fault — quoting a source, or judging a historical
# record rather than the subject, can be legitimate. So: WARN with every
# hit listed for eyeball review, same treatment as "powerful" in v2.
SUPERLATIVE_RE = re.compile(
    r"\b(weird|weirder|weirdest|strange|stranger|strangest|strangely|"
    r"bizarre|bizarrely|odd|oddest|oddly|peculiar|freakish|"
    r"insane|crazy|craziest|unbelievable|incredible)\b",
    re.IGNORECASE,
)

# --- v3: second-person scan -----------------------------------------------
# Overlay v1.0 bans viewer-address outright: no you/your, no imagine,
# no picture-yourself, no viewer roleplay.
SECOND_PERSON_RE = re.compile(
    r"\b(you|your|yours|yourself|yourselves)\b|"
    r"\b(imagine|picture) (yourself|you're|youre)\b",
    re.IGNORECASE,
)

NEGATE_RE = re.compile(
    r"(\b(it['’]?s not|it isn['’]?t|it wasn['’]?t|this isn['’]?t|"
    r"that['’]?s not|wasn['’]?t about|isn['’]?t about|not about)\b"
    r"[^.?!\n]{0,80}?[,.;]\s*(it['’]?s|it was|but)\b)"
    r"|(\bfor what it (was|is), not for what it (did|does)\b)"
    r"|(\bnot (a|an|the|about|because)\b[^.?!\n]{0,50}?,\s*(but|it['’]?s|it was|a|an|the)\b)",
    re.IGNORECASE,
)

EMDASH_RE = re.compile(r"—|(?<=\w)--(?=\w)|\s--\s")
NO_FRAGMENT_RE = re.compile(r"\bNo\s+[\w' ]{1,25}\.\s+No\s+[\w' ]{1,25}\.")
PCT_RE = re.compile(r"\b(47|73|37|91|83)\s*(%|percent\b)", re.IGNORECASE)
HEADER_NUM_RE = re.compile(r"^#{1,6}\s*(\d+[.):]|#?\d+\s*[-–—])")

# Body = first H2 onward, stopping at back matter. Front matter (H1 title,
# version stamp, VO note) and back matter are handoff scaffolding, not
# narration, and must not be linted or counted.
BACK_MATTER_RE = re.compile(
    r"^#{1,6}\s*(pronunciation|audit|appendix|notes?|sources?|changelog|"
    r"animator|thumbnail|references?)\b", re.IGNORECASE)
BODY_START_RE = re.compile(r"^##\s+(?!.*(pronunciation|audit|appendix))", re.IGNORECASE)

# ==========================================================================
# NEW v3.1 — DEADZONE SCAN
# ==========================================================================
# SOP v1.2, Stage 5 item 3: "every sentence must answer 'what is on screen
# while this is being said.'" A deadzone is a sentence that leans on a
# reporting or abstract verb while naming no physical object.
#
# Mechanically: cue present AND no concrete anchor present.
#
# The three debt types are listed in SOP order of severity. Type is
# reported so the fix is obvious — the fix is always to write the visual
# INTO the sentence, never to hand the animator a cue sheet.

DEADZONE_CUES = [
    ("sourcing", re.compile(
        r"\b(wrote|writes|writing|written|recorded|noted|noting|reported|"
        r"describes|described|claims|claimed|quotes|quoted|cites|cited|"
        r"documented|published|attributed|testified|stated|argues|argued|"
        r"insisted|recounted|recounts|mentions|mentioned|credited|"
        r"according to|in his account|in her account|by his own account)\b",
        re.IGNORECASE)),
    ("historiography", re.compile(
        r"\b(historians?|scholars?|archaeologists?|researchers?|archives?|"
        r"archival|historiograph\w+|scholarship|the records?|records show|"
        r"no record|documentation|the evidence|sources (say|differ|disagree|agree)|"
        r"accounts? (differ|vary|disagree|survive)|tradition holds|legend has it|"
        r"is unclear|remains unclear|remains uncertain|is disputed|is debated|"
        r"we do not know|we don['’]t know|is unknown|attested)\b",
        re.IGNORECASE)),
    ("institutional", re.compile(
        r"\b(classified|declassified|commission|inquiry|committee|"
        r"budget|funding|funded|procurement|appropriations?|"
        r"approved|authorized|authorised|cancell?ed|legislation|policy|policies|"
        r"bureaucra\w+|paperwork|regulations?|ministry|admiralty|war office|"
        r"parliament|congress|directive|memorandum|red tape|investigation|"
        r"tribunal|court[- ]martial|the report|officially|never entered service|"
        r"was shelved|was abandoned on paper)\b",
        re.IGNORECASE)),
]

# Concrete anchors. Deliberately EXCLUDES document nouns (record, file,
# report, letter, memo, archive, paper): "a historian reading a service
# record" is the canonical deadzone, not an exemption from one. A document
# only earns its place when it is staged as an object — a drawer that
# stays shut for seventy years — and that staging brings its own anchor.
#
# Also deliberately excluded: spring, lead, mail, net, cap. Each has a
# common abstract sense ("the following spring", "led to", "red tape and
# mail") that would silently exempt real deadzones from the scan. A word
# earns its place here only if nearly every use of it puts something on
# screen. False negatives here are cheap; false exemptions are not.
CONCRETE_WORDS = r"""
ship ships shipyard hull hulls mast masts sail sails sailcloth rudder keel bow stern
anchor anchored boat boats raft rafts barge submarine submarines torpedo torpedoes
propeller propellers funnel funnels boiler boilers turret turrets gun guns gunport
cannon cannons barrel barrels muzzle shell shells bullet bullets round rounds
powder fuse fuses bomb bombs mine mines missile missiles rocket rockets grenade
blade blades sword swords spear spears pike pikes axe axes arrow arrows bowstring
shield shields armor armour helmet helmets breastplate plate plates chainmail
knife dagger club hammer hammers saw nails nail screw bolt bolts chain chains
rope ropes cable cables wire nets hook hooks pulley wheel wheels axle gear gears
pistons piston engine engines motor motors tank tanks truck trucks cart carts
wagon wagons carriage horse horses mule mules ox oxen elephant elephants camel camels
dog dogs plane planes aircraft wing wings cockpit parachute balloon balloons glider
steel iron bronze brass copper timber wood oak canvas leather glass stone stones
brick bricks concrete cloth rubber tar pitch rust paint
water sea seas ocean wave waves surf river riverbank mud sand snow ice rain fog mist
smoke fire fires flame flames ash dust blood bone bones sweat
hand hands finger fingers arm arms leg legs foot feet face eyes head shoulder skin teeth
ground earth hill hills ridge valley forest trees tree field fields road roads bridge
wall walls gate gates tower towers fort fortress trench trenches tunnel ditch
harbor harbour port dock docks shore shoreline beach coast coastline island cliff
desert mountain mountains village town city street house houses roof roofs door doors
drawer window windows floor room table chair box crate crates sack sacks chest
shelf cabinet workshop factory foundry forge furnace hangar warehouse
man men woman women crew crews sailor sailors soldier soldiers troops infantry cavalry
gunner gunners crewman rider riders horseman prisoners corpse corpses body bodies
uniform uniforms coat boots cap belt flag flags banner drum drums torch lantern lamp candle
"""

CONCRETE_VERBS = r"""
fired firing fires shot shoot sank sink sinking sunk exploded explode exploding
burned burnt burning marched march charged charge dragged drag hauled rolled
rammed smashed crushed tore ripped snapped cracked split shattered splintered
hammered welded riveted bolted poured spilled flooded capsized collapsed toppled
fell dropped lifted carried threw thrown swung stabbed slashed pierced punched
kicked climbed crawled swam sailed steamed rowed flew landed crashed drifted
floated jammed misfired recoiled reloaded loaded aimed struck hit bounced
ricocheted buckled bent melted froze boiled leaked dripped hissed roared
cut dug buried stacked tied nailed blew blown tipped slid spun rammed
"""

UNIT_RE = re.compile(
    r"\d[\d,\.]*\s*(mm|cm|km|kg|lb|lbs|ft|hp|"
    r"met(er|re)s?|feet|foot|inch(es)?|yards?|miles?|tons?|tonnes?|pounds?|"
    r"knots?|mph|rounds?|shells?|guns?|men|horses?|ships?|degrees?|"
    r"horsepower|gallons?|lit(er|re)s?)\b",
    re.IGNORECASE)


def _wordset_re(blob):
    words = sorted(set(blob.split()), key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b",
                      re.IGNORECASE)


CONCRETE_RE = _wordset_re(CONCRETE_WORDS + CONCRETE_VERBS)

# ==========================================================================
# NEW v3.1 — FACT-DENSITY FLOOR
# ==========================================================================
# Channel skill v6.3, "Fact density (CRITICAL)": per entry / era block, at
# least one exact date or year, one named individual, one hard number or
# technical spec. SOP Stage 5 item 8 makes it part of the battery.

DATE_RE = re.compile(
    r"\b(1[0-9]{3}|20[0-2][0-9])\b"
    r"|\b\d{1,4}\s*(BCE?|AD|CE)\b"
    r"|\b(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2}\b"
    r"|\b\d{1,2}(st|nd|rd|th)\s+century\b"
    r"|\b(1[0-9]{3}|20[0-2][0-9])s\b")

NUMWORD_RE = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|"
    r"thousand|million|dozen)\s+"
    r"(\w+\s+){0,2}?"
    r"(men|ships?|guns?|tons?|tonnes?|pounds?|feet|foot|met(er|re)s?|miles?|"
    r"horses?|rounds?|shells?|days?|hours?|years?|soldiers?|troops?|crew|"
    r"casualties|dead|survivors?)\b",
    re.IGNORECASE)

RANK_RE = re.compile(
    r"\b(Captain|Admiral|Vice[- ]Admiral|Rear[- ]Admiral|Commodore|Commander|"
    r"General|Colonel|Major|Lieutenant|Sergeant|Corporal|Ensign|Marshal|"
    r"Sir|Lord|Lady|King|Queen|Emperor|Empress|Tsar|Czar|Prince|Princess|"
    r"Duke|Baron|Count|Sultan|Khan|Pope|Bishop|Dr|Doctor|Professor|"
    r"Engineer|Inventor|Chancellor|President|Consul|Pharaoh)\.?\s+[A-Z][a-z]+")

CAPPAIR_RE = re.compile(r"\b([A-Z][a-z’']+)\s+((?:de|van|von|of|al)\s+)?([A-Z][a-z’']+)\b")
POSSESSIVE_RE = re.compile(r"\b([A-Z][a-z’']{2,})['’]s\b")

# Capitalized tokens that mark a place, nation, unit or institution rather
# than a person. A pair containing one of these is not counted as a name.
NOT_A_PERSON = {
    "the", "a", "an", "and", "but", "so", "then", "when", "while", "after",
    "before", "by", "in", "on", "at", "for", "from", "with", "without",
    "royal", "navy", "naval", "army", "air", "force", "corps", "regiment",
    "division", "brigade", "battalion", "fleet", "squadron", "guard",
    "united", "states", "state", "kingdom", "empire", "republic", "union",
    "north", "northern", "south", "southern", "east", "eastern", "west",
    "western", "new", "great", "old", "upper", "lower", "grand",
    "world", "war", "wars", "battle", "siege", "campaign", "revolution",
    "sea", "ocean", "island", "islands", "river", "mount", "mountain",
    "fort", "cape", "bay", "gulf", "strait", "channel", "valley", "point",
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "britain", "british", "england", "english", "france", "french",
    "germany", "german", "russia", "russian", "america", "american",
    "japan", "japanese", "china", "chinese", "spain", "spanish", "italy",
    "italian", "dutch", "holland", "sweden", "swedish", "rome", "roman",
    "greece", "greek", "egypt", "egyptian", "persia", "persian", "ottoman",
    "confederate", "confederacy", "soviet", "prussia", "prussian", "austria",
    "company", "committee", "commission", "admiralty", "ministry",
    "department", "office", "parliament", "congress", "university",
    "his", "her", "their", "its", "it", "he", "she", "they",
}


def has_name(text):
    """Detect NAME SHAPE, not personhood. Returns (bool, example|None)."""
    m = RANK_RE.search(text)
    if m:
        return True, m.group(0)
    for m in CAPPAIR_RE.finditer(text):
        first, last = m.group(1), m.group(3)
        if first.lower() in NOT_A_PERSON or last.lower() in NOT_A_PERSON:
            continue
        return True, m.group(0)
    for m in POSSESSIVE_RE.finditer(text):
        if m.group(1).lower() not in NOT_A_PERSON:
            return True, m.group(0)
    return False, None


def has_number(text):
    """A hard number or spec — a bare year does not count as one."""
    stripped = DATE_RE.sub(" ", text)
    if re.search(r"\d", stripped):
        return True
    return bool(NUMWORD_RE.search(text))


def is_deadzone(sentence):
    """Returns (debt_type, cue) if the sentence is a deadzone, else None."""
    if CONCRETE_RE.search(sentence) or UNIT_RE.search(sentence):
        return None
    for label, rx in DEADZONE_CUES:
        m = rx.search(sentence)
        if m:
            return label, m.group(0)
    return None


THRESH_RESULTS = []
STARTER_RESULTS = []
NEG_OK = []


def tier(words: int) -> str:
    if 250 <= words <= 320: return "HEAVY"
    if 170 <= words <= 220: return "MEDIUM"
    if 110 <= words <= 160: return "LIGHT"
    if words > 320: return "OVER-HEAVY"
    if words < 110: return "UNDER-LIGHT"
    return "BETWEEN-TIERS"


def fmt_runtime(words: int) -> str:
    r = words / WPM
    return f"{int(r)}:{int((r % 1) * 60):02d}"


def split_sentences(line):
    return [s for s in re.split(r"(?<=[.?!])\s+", line.strip()) if s.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--format", choices=["listicle", "every-era", "history"],
                    default="listicle")
    ap.add_argument("--overlay", action="store_true",
                    help="punchy dark-wit overlay active: second person becomes a hard fail")
    ap.add_argument("--punchline", nargs="*", default=[],
                    help="punchline words to check for reuse (max 1 each)")
    ap.add_argument("--no-deadzone", action="store_true",
                    help="skip the v3.1 deadzone scan")
    ap.add_argument("--no-density", action="store_true",
                    help="skip the v3.1 fact-density floor")
    ap.add_argument("--min-section-words", type=int, default=40,
                    help="sections shorter than this are exempt from the density floor")
    args = ap.parse_args()

    try:
        raw = open(args.script, encoding="utf-8").read()
    except OSError as e:
        sys.exit(f"Cannot read {args.script}: {e}")

    lines = raw.splitlines()
    fails, warns = [], []

    # --- Trim front and back matter ---
    start = 0
    for idx, ln in enumerate(lines):
        if BODY_START_RE.match(ln):
            start = idx
            break
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if BACK_MATTER_RE.match(lines[idx]):
            end = idx
            break
    trimmed_front = start
    trimmed_back = len(lines) - end
    offset = start
    lines = lines[start:end]

    body_lines = []
    sections = []       # (title, [words])  — tier report, unchanged from v3.0
    section_lines = []  # (title, [(lineno, text)]) — v3.1 scans
    current = None
    current_lines = None
    header_count = 0
    for i, ln in enumerate(lines, offset + 1):
        if re.match(r"^#{1,6}\s", ln):
            header_count += 1
            if HEADER_NUM_RE.match(ln):
                fails.append(f"NUMBERED HEADER (line {i}): {ln.strip()!r} — headers are never numbered")
            title = re.sub(r"^#{1,6}\s*", "", ln).strip()
            current = (title, [])
            sections.append(current)
            current_lines = (title, [])
            section_lines.append(current_lines)
        else:
            body_lines.append((i, ln))
            if current is not None:
                current[1].extend(re.findall(r"\b[\w'’]+\b", ln))
                current_lines[1].append((i, ln))

    body = "\n".join(t for _, t in body_lines)
    body_lc = body.lower()

    # --- Em dashes ---
    hits = [(i, t.strip()) for i, t in body_lines if EMDASH_RE.search(t)]
    for i, t in hits[:10]:
        fails.append(f"EM DASH (line {i}): {t[:90]!r}")
    if len(hits) > 10:
        fails.append(f"...and {len(hits)-10} more em-dash lines")

    # --- Threshold words ---
    for label, rx, mx in THRESHOLDS:
        n = len(re.findall(rx, body_lc))
        if n > mx:
            fails.append(f"{label}: {n} (max {mx})")
        THRESH_RESULTS.append((label, n, mx))

    # --- Zero tolerance ---
    for label, rx in ZERO_TOLERANCE:
        pat = re.compile(rx, re.IGNORECASE | re.MULTILINE)
        for i, t in body_lines:
            if pat.search(t):
                fails.append(f"{label.upper()} (line {i}): {t.strip()[:90]!r}")

    # --- Superlative verdicts ---
    sup_hits = []
    for i, t in body_lines:
        for m in SUPERLATIVE_RE.finditer(t):
            sup_hits.append((i, m.group(0), t.strip()))
    for i, w, t in sup_hits:
        warns.append(
            f'SUPERLATIVE VERDICT "{w}" (line {i}): {t[:85]!r}\n'
            f'      -> is the narration TELLING the viewer it is {w.lower()}? '
            f'cut and let the subject show it. Legitimate only if quoting a '
            f'source or judging the record, not the subject.'
        )

    # --- Second person ---
    sp_hits = []
    for i, t in body_lines:
        for m in SECOND_PERSON_RE.finditer(t):
            sp_hits.append((i, m.group(0), t.strip()))
    for i, w, t in sp_hits:
        msg = f'SECOND PERSON "{w}" (line {i}): {t[:85]!r}'
        if args.overlay:
            fails.append(msg + " — overlay bans viewer address")
        else:
            warns.append(msg + " — rephrase to third-person/observational")

    # ================= NEW v3.1: DEADZONE SCAN =================
    dz_hits = []      # (lineno, type, cue, sentence, at_entry_end)
    dz_runs = []      # (title, [hits])
    if not args.no_deadzone:
        for title, slines in section_lines:
            seq = []  # (lineno, sentence)
            for i, ln in slines:
                for s in split_sentences(ln):
                    seq.append((i, s))
            if not seq:
                continue
            tail_start = int(len(seq) * 0.75)
            flags = []
            for idx, (i, s) in enumerate(seq):
                d = is_deadzone(s)
                flags.append((i, s, d, idx >= tail_start))
            run = []
            for i, s, d, at_end in flags:
                if d:
                    dz_hits.append((i, d[0], d[1], s, at_end))
                    run.append((i, d[0], s))
                else:
                    if len(run) >= 2:
                        dz_runs.append((title, run))
                    run = []
            if len(run) >= 2:
                dz_runs.append((title, run))

        for i, typ, cue, s, at_end in dz_hits:
            tag = " [ENTRY-END]" if at_end else ""
            warns.append(
                f'DEADZONE / {typ}{tag} (line {i}): {s[:95]!r}\n'
                f'      -> cue {cue!r}, no physical object named. What is on screen '
                f'while this is read? Write the visual INTO the sentence.'
            )
        for title, run in dz_runs:
            fails.append(
                f'CONSECUTIVE DEADZONES ({len(run)}) in "{title[:40]}" '
                f'lines {run[0][0]}-{run[-1][0]} — seconds of screen time with '
                f'nothing to cut to. This is the serious failure.'
            )
            for i, typ, s in run:
                fails.append(f"   ({typ}, line {i}) {s[:88]!r}")

    # ================= NEW v3.1: FACT-DENSITY FLOOR =================
    density_rows = []  # (title, words, has_date, has_name, name_eg, has_num)
    if not args.no_density:
        for (title, slines), (_, swords) in zip(section_lines, sections):
            text = " ".join(t for _, t in slines)
            nwords = len(swords)
            if nwords < args.min_section_words:
                continue
            d = bool(DATE_RE.search(text))
            n_ok, n_eg = has_name(text)
            num = has_number(text)
            density_rows.append((title, nwords, d, n_ok, n_eg, num))
            missing = []
            if not d:
                missing.append("date/year")
            if not n_ok:
                missing.append("named individual (no name SHAPE found — confirm by eye)")
            if not num:
                missing.append("hard number/spec")
            if missing:
                fails.append(
                    f'FACT-DENSITY FLOOR — "{title[:44]}" ({nwords}w) missing: '
                    + "; ".join(missing)
                )

        # Filler paragraphs: 2+ sentences carrying no date, name, number or spec.
        for title, slines in section_lines:
            para, para_start = [], None
            def flush(para, para_start):
                if len(para) < 2:
                    return
                text = " ".join(para)
                if (DATE_RE.search(text) or has_number(text)
                        or has_name(text)[0] or UNIT_RE.search(text)):
                    return
                warns.append(
                    f"FILLER PARAGRAPH (line {para_start}, {len(para)} sentences): "
                    f"{text[:95]!r}\n      -> no date, no name, no number, no spec. "
                    f"Fact density is a floor, not an average."
                )
            for i, ln in slines:
                if not ln.strip():
                    flush(para, para_start)
                    para, para_start = [], None
                    continue
                if para_start is None:
                    para_start = i
                para.extend(split_sentences(ln))
            flush(para, para_start)

    # --- Negate-contrast: exactly 1 ---
    neg_hits = []
    for i, t in body_lines:
        for m in NEGATE_RE.finditer(t):
            neg_hits.append((i, m.group(0).strip()))
    if len(neg_hits) != 1:
        fails.append(f"NEGATE-CONTRAST COUNT: {len(neg_hits)} candidate(s) — rule is exactly 1. Confirm by eye:")
        for i, t in neg_hits[:8]:
            fails.append(f"   (line {i}) {t[:90]!r}")
        if not neg_hits:
            fails.append("   (none found — script may be missing its one allowed device, or uses a shape the regex misses)")
    else:
        NEG_OK.append(neg_hits[0])

    # --- Colons ---
    ncolon = body.count(":")
    if ncolon > 3:
        fails.append(f"COLONS IN BODY: {ncolon} (max 3)")

    # --- No X. No Y. ---
    for i, t in body_lines:
        if NO_FRAGMENT_RE.search(t):
            fails.append(f'"NO X. NO Y." FRAGMENT (line {i}): {t.strip()[:90]!r}')

    # --- "powerful" review flag ---
    for i, t in body_lines:
        if re.search(r"\bpowerful\b", t, re.IGNORECASE):
            warns.append(f'"POWERFUL" (line {i}): {t.strip()[:90]!r} — empty intensifier? cut; factual force claim? keep')

    # --- Suspicious percentages ---
    for i, t in body_lines:
        if PCT_RE.search(t):
            warns.append(f"SUSPICIOUS % (line {i}): {t.strip()[:90]!r} — verify this is a real sourced number")

    # --- Sentence starters ---
    starters = {"And": 12, "But": 8, "So": 6}
    sentences = re.split(r"(?<=[.?!])\s+", body)
    for word, cap in starters.items():
        n = sum(1 for s in sentences if re.match(rf"{word}\b", s.strip()))
        STARTER_RESULTS.append((word, n, cap))
        if n > cap:
            fails.append(f'SENTENCE STARTER "{word}": {n} (max {cap})')

    # --- Punchline reuse ---
    for w in args.punchline:
        n = len(re.findall(rf"\b{re.escape(w)}\b", body_lc))
        if n > 1:
            fails.append(f'PUNCHLINE WORD "{w}": used {n}x (max 1)')

    # --- Word count / runtime ---
    total_words = len(re.findall(r"\b[\w'’]+\b", body))
    lo, hi = FORMAT_TARGETS[args.format]
    if not (lo * 0.8 <= total_words <= hi * 1.25):
        warns.append(f"WORD COUNT {total_words} well outside {args.format} target {lo}-{hi}")
    elif not (lo <= total_words <= hi):
        warns.append(f"WORD COUNT {total_words} outside {args.format} target {lo}-{hi} (within tolerance — confirm intentional)")

    # ================= REPORT =================
    print("=" * 64)
    print("EXPLAINTORY COMPLIANCE LINT v3.1")
    print(f"File: {args.script}   Format: {args.format}"
          + ("   [overlay]" if args.overlay else ""))
    print("=" * 64)
    if trimmed_front or trimmed_back:
        print(f"\n(trimmed {trimmed_front} front-matter and {trimmed_back} back-matter lines"
              f" — not counted or linted)")
    print(f"\nWord count (body): {total_words}   Target: {lo}-{hi}")
    print(f"Runtime estimate:  {fmt_runtime(total_words)} at measured {WPM:.0f} WPM")

    # --- kill-line window ---
    first_words = re.findall(r"\b[\w'’]+\b", body)[:KILL_LINE_WORDS]
    print(f"\n--- Fix 1: first {KILL_LINE_WORDS} words (= 0:25) ---")
    print("  " + " ".join(first_words))
    print("  -> the kill-line must land INSIDE this window.")

    print("\n--- Pattern thresholds ---")
    for label, n, mx in THRESH_RESULTS:
        print(f"  [{'OK ' if n <= mx else 'FAIL'}] {label}: {n} / max {mx}")

    print("\n--- Sentence starters ---")
    for word, n, cap in STARTER_RESULTS:
        print(f"  [{'OK ' if n <= cap else 'FAIL'}] \"{word} ...\": {n} / max {cap}")

    print("\n--- v3 scans ---")
    print(f"  [{'OK ' if not sup_hits else 'REVIEW'}] superlative verdicts: {len(sup_hits)}")
    sp_flag = "OK " if not sp_hits else ("FAIL" if args.overlay else "REVIEW")
    print(f"  [{sp_flag}] second person: {len(sp_hits)}")

    print("\n--- v3.1 scans ---")
    if args.no_deadzone:
        print("  [SKIP] deadzone scan disabled")
    else:
        dz_flag = "FAIL" if dz_runs else ("REVIEW" if dz_hits else "OK ")
        print(f"  [{dz_flag}] deadzones: {len(dz_hits)} sentence(s), "
              f"{len(dz_runs)} consecutive run(s)")
        by_type = {}
        for _, typ, _, _, at_end in dz_hits:
            by_type.setdefault(typ, [0, 0])
            by_type[typ][0] += 1
            if at_end:
                by_type[typ][1] += 1
        for typ in ("sourcing", "historiography", "institutional"):
            if typ in by_type:
                n, e = by_type[typ]
                print(f"         {typ}: {n} ({e} at entry endings)")

    if args.no_density:
        print("  [SKIP] fact-density floor disabled")
    else:
        short = [r for r in density_rows if not (r[2] and r[3] and r[5])]
        print(f"  [{'OK ' if not short else 'FAIL'}] fact-density floor: "
              f"{len(density_rows) - len(short)}/{len(density_rows)} sections clear")
        if density_rows:
            print("         date name  num   section")
            for title, nw, d, n_ok, n_eg, num in density_rows:
                print(f"          {'Y' if d else '.'}    {'Y' if n_ok else '.'}    "
                      f"{'Y' if num else '.'}    {title[:40]}"
                      + (f"   ({n_eg})" if n_eg else ""))

    if NEG_OK:
        i, t = NEG_OK[0]
        print(f"\n--- Negate-contrast ---\n  [OK ] exactly 1, line {i}: {t[:80]!r}")

    print("\n--- Section tiers ---")
    for title, words in sections:
        if len(words) < 5:
            continue
        print(f"  {len(words):>4}w  {fmt_runtime(len(words)):>5}  {tier(len(words)):<13} {title[:44]}")

    if args.format == "every-era":
        print(f"\n--- From Every Era ---")
        print(f"  {header_count} headers found. Rule: at most 2 read aloud, rest on-screen cards.")
        print("  Which are spoken is not mechanically detectable — confirm at VO handoff.")

    if warns:
        print(f"\n--- WARNINGS / REVIEW ({len(warns)}) ---")
        for w in warns:
            print(f"  ! {w}")

    if fails:
        print(f"\n--- FAILURES ({len(fails)}) ---")
        for f in fails:
            print(f"  X {f}")
        print("\nVERDICT: FAIL — edit before presenting.")
        sys.exit(1)

    print("\nVERDICT: PASS (mechanical only). Still needs the judgment pass:")
    print("  humor density, fact staging, outcome variety, payoff spacing,")
    print("  recognition floor, and FACTUAL ACCURACY — this battery cannot")
    print("  catch a wrong number, only a banned word.")
    sys.exit(0)


if __name__ == "__main__":
    main()
