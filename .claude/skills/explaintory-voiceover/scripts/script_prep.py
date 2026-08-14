#!/usr/bin/env python3
"""
Script -> narration text -> TTS sections.

A faithful port of the structure detection and chunker inside Voiceover Studio
(voiceover_studio.py / studio.html). The studio and this pipeline must split a
script the same way, or a section regenerated here would not drop cleanly into
a project built there.

Ported pieces, by their studio names:
    isTitleCaseHeading   -> is_title_case_heading
    detectStructure      -> detect_structure
    effectiveScript      -> narration_text
    splitScript          -> split_script
    chapterGaps          -> chapter_gaps

Markers, same as the studio:
    \x01  section break — this unit starts a fresh TTS request
    \x02  pause marker  — real digital silence is inserted here at stitch time
"""
import json
import re
import sys

SECTION_MARK = "\x01"
PAUSE_MARK = "\x02"

# chars per TTS request. 400-600 is the studio's sweet spot: the voice model
# drifts over a long generation and holds its best delivery for ~30s.
MAX_CHUNK = 450

# previous_text / next_text conditioning window, studio's CONTEXT_CHARS
CONTEXT_CHARS = 300

# Silence added around a spoken chapter heading, on top of the ~0.20s the voice
# model already renders at section edges, and before the master adds its own
# paragraph pause on top of that.
#
# These are the INSERTED amounts, not the finished ones. Measured on a delivered
# master, 'natural' lands at roughly 0.33-0.41s before a chapter name and
# 0.39-0.57s after it. An earlier version of this comment quoted those finished
# figures (~0.45/~0.50) as if they were the values in the dict below, which made
# the dict look wrong to anyone who read both.
PAUSE_PRESETS = {
    "tight":   {"before": 0.10, "after": 0.18, "cta": 0.20},
    "natural": {"before": 0.22, "after": 0.30, "cta": 0.30},
    "wide":    {"before": 0.40, "after": 0.55, "cta": 0.55},
}

CTA_RE = re.compile(
    r"\b(subscribe|leave a like|like and subscribe|smash (the|that) like( button)?"
    r"|notification bell|hit the bell|turn on notifications?|comment (below|which|what|down|if)"
    r"|drop a (like|comment)|in the comments)\b", re.I)

_META_LABELS = (r"(intro|outro|hook|conclusion|opening|closing|cta|title|the end"
                r"|script|voiceover script|vo script|body|full script)")
_SECTION_WORD = r"(section|part|chapter|act|scene|segment)"
_SMALL_WORD = re.compile(
    r"^(of|the|and|a|an|in|on|to|for|vs|or|at|by|is|it|with|from|as|but|nor|into"
    r"|onto|upon|over|under|off|out|up|down|near|no)$", re.I)


def unmark(t):
    return t.replace(SECTION_MARK, "").replace(PAUSE_MARK, "")


def strip_markdown(t):
    """Remove emphasis markers so they are never sent to the voice.

    Google Docs exports headings as '## **Coca**' and bolds names inline. Left in,
    the asterisks and underscores go to the API as literal characters.
    """
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)      # **bold**
    t = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", t)  # _em_, but not snake_case
    t = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"\1", t)   # *italic*
    return t


# A pronunciation guide sits at the end of every ExplainTory script. It is a note
# to the reader, not a line to read, and left in place it would be narrated —
# the video would close by reciting its own glossary. It is also the per-script
# answer key for how each name should sound, which is worth more than a static
# list because it arrives with the words it belongs to.
# 'names' is deliberately NOT a heading word here: a script section legitimately
# titled 'Names' would be swallowed whole. The heading has to actually say
# pronunciation for the tail to be treated as a glossary.
_GUIDE_HEAD = re.compile(
    r"^\s*#{0,6}\s*\**\s*(pronunciation|pronounciation|pronunciations|"
    r"pronounce|how to say|say it)\b[^\n]{0,40}$", re.I)
# '- **Syracusia** — sirr-uh-KYOO-zee-uh', also en dash, hyphen, colon or '='.
# The bullet class is wide because these arrive pasted out of Google Docs.
_GUIDE_LINE = re.compile(r"^[\s\t]*[-*•●○·▪‣]?[\s\t]*(.+?)\s*[—–\-:=]\s+(.+?)\s*$")


# A guide is organised as well as populated, and its own scaffolding matches the
# entry pattern: "**Section 4 — Ross rifle**" splits into ('Section 4', 'Ross rifle')
# exactly like a real entry does. Nine of those got into a 43-entry guide, and the
# pre-flight then reported nine names "missing from the narration" that were never
# names. A warning list that is mostly noise is one nobody reads, so the divider is
# rejected here rather than filtered downstream.
_GUIDE_DIVIDER = re.compile(r"^\s*(section|part|chapter)\s+\d+\s*$", re.I)

# "**Heading: Chauchat** — *show-SHAH*" splits on the COLON first, because the regex
# is non-greedy from the left. That yields the word 'Heading' — and since three
# sections each contribute a "Heading:" line, all three collapsed onto one dict key
# and two real entries were lost outright.
_GUIDE_LABEL = re.compile(r"^(heading|word|name|term)\s*:\s*", re.I)


def _guide_entry(line):
    """-> (headword, respelling), or (None, None) if the line is not an entry.

    The respelling is the part a human reads, so it carries trailing commentary —
    'ROX-bruh* (not "rox-burg")'. Keep the pronunciation, drop the aside: it is the
    headword that has to be exact, and a value with markdown still in it corrupts
    any lexicon seeded from this guide.
    """
    m = _GUIDE_LINE.match(line)
    if not m:
        return None, None
    w, say = m.group(1).strip(" *-•_"), m.group(2).strip(" *_")

    # "**Heading: Chauchat** — *show-SHAH*" splits on the colon, which is the FIRST
    # delimiter, so the pair arrives as ('Heading', 'Chauchat** — *show-SHAH*'). The
    # real entry is inside the value: re-split it and keep that instead.
    if _GUIDE_LABEL.fullmatch(w + ":"):
        inner = _GUIDE_LINE.match(say)
        if not inner:
            return None, None
        w, say = inner.group(1).strip(" *-•_"), inner.group(2).strip(" *_")

    if not w or not say or _GUIDE_DIVIDER.match(w):
        return None, None
    if len(w.split()) > 4:                 # 'The slogan is a quoted advertising line'
        return None, None                  # is a note to the reader, not a headword
    say = re.sub(r"\s*\([^)]*\)\s*$", "", say).strip(" *_")   # drop trailing asides
    return w, say


def _looks_like_guide_body(lines):
    """A run of 'word — respelling' lines, allowing blanks and bullets.

    One entry is enough, because the heading already had to say 'pronunciation'
    outright — and a one-name guide read aloud is exactly as wrong as a ten-name
    one. What is still required is that most of what follows looks like entries,
    so a heading followed by prose is left alone.
    """
    real = [ln for ln in lines if ln.strip()]
    if not real:
        return False
    hits = sum(1 for ln in real if _GUIDE_LINE.match(ln))
    return hits >= 1 and hits >= len(real) * 0.6


# Blocks that live after the script and are never narrated. The animator note is
# the other one: pages of "NO HORNED HELMETS" and "Do not draw a mounted rider",
# written for the artist. It can sit either side of the guide, so both are found
# and the cut is made at whichever comes first.
_APPENDIX_HEAD = re.compile(
    r"^\s*#{0,6}\s*\**\s*(animator|animation|art|visual|thumbnail|production|"
    r"reference|source|research|accuracy)\b[^\n]{0,60}$", re.I)

# A top-level heading closes the guide's own section. Used only by the fallback
# below, to bound the block a guide heading owns when the document keeps going.
_H1 = re.compile(r"^\s*#\s+\S")


def _guide_section_end(lines, start):
    """Index of the first line after the guide's own section.

    The guide ends where the next H1 or the next appendix heading begins. Anything
    lower — '## Names', a bullet, a blank — is still inside it.
    """
    for j in range(start + 1, len(lines)):
        if _H1.match(lines[j]) or _APPENDIX_HEAD.match(lines[j]):
            return j
    return len(lines)


def split_pronunciation_guide(text):
    """-> (script without the guide and any appendices, {word: respelling})

    Two ways of recognising the guide, in order:

      1. Tail anchor (fast path). Everything after the heading looks like entries,
         which is the shape of a script that ends with its guide.
      2. Section anchor (fallback). A real production document is a container for
         several documents — script, then guide, then a 1,400-word animator note or
         a shot list — and with anything appended after it the guide is no longer
         the tail, so the ratio test in (1) is dragged under by material that was
         never part of the guide. Detection then missed entirely and the video
         closed by reciting its own glossary AND the art direction. So the block
         from the heading to the next H1 is tested on its own, and everything from
         that heading onward is treated as non-narration.

    A mid-script line like 'The corvus — a boarding bridge — decided the battle'
    is still safe: the heading regex has to match first, and it must actually say
    pronunciation.
    """
    lines = text.split("\n")
    guide, cut = {}, None

    for i, ln in enumerate(lines):
        if not _GUIDE_HEAD.match(ln):
            continue
        tail = lines[i + 1:]                                  # 1. guide IS the tail
        body = tail if _looks_like_guide_body(tail) else None
        if body is None:                                      # 2. guide is a SECTION
            block = lines[i + 1:_guide_section_end(lines, i)]
            body = block if _looks_like_guide_body(block) else None
        if body is None:
            continue                     # a 'pronunciation' heading over prose
        for sub in body:
            w, say = _guide_entry(sub)
            if w:
                guide.setdefault(w, say)
        cut = i if cut is None else min(cut, i)
        break

    for i, ln in enumerate(lines):
        if _APPENDIX_HEAD.match(ln):
            cut = i if cut is None else min(cut, i)
            break

    if cut is None:
        return text, {}
    return "\n".join(lines[:cut]).rstrip(), guide


# A decimal-leading calibre — ".303", ".22", ".50" — comes out of a Google Docs
# export with the period detached and glued to the word before it: "it was fed
# British. 303 made to loosen ones". The voice then reads a sentence boundary
# mid-clause and says "three hundred and three".
#
# Nothing downstream can catch this. The text is well-formed, and the read-check
# diffs the ASR against the SAME corrupted script, so it finds agreement and
# reports the section clean. It was caught once, by a human reading the script
# against the guide, which listed ".303 — read as three-oh-three".
_ORPHAN_DECIMAL = re.compile(r"\w\.\s+\d{2,3}\b")


def _appears_verbatim(word, text, fold=False):
    """Is `word` in `text` as a whole token? Internal whitespace is allowed to vary."""
    patt = r"(?<!\w)" + r"\s+".join(re.escape(t) for t in word.split()) + r"(?!\w)"
    return re.search(patt, text, re.I if fold else 0) is not None


def _appears_inflected(word, text):
    """Is `word` present as the stem of an inflected token?

    A guide lists the name — 'Lee-Enfield' — and the script uses it in a sentence:
    'took Lee-Enfields off the British dead'. That is the guide doing its job, not a
    drift, and warning about it spends the reader's attention on a non-problem. Only
    trailing inflections count; a prefix match on its own would let 'Mark' vouch for
    'Marketing'.
    """
    patt = (r"(?<!\w)" + r"\s+".join(re.escape(t) for t in word.split())
            + r"(?:'s|’s|s|es)(?!\w)")
    return re.search(patt, text) is not None


def guide_preflight(narration, guide):
    """-> [warning lines]. Check the script against its own answer key BEFORE spending.

    The pronunciation guide is a machine-readable list of the words this script
    cares about, shipped inside the script itself — and it was only ever used
    downstream, to check the finished audio. Used up front it is a free proof-read:
    a headword that does not appear verbatim in the narration is an export artifact,
    a spelling drift, or a stale guide entry, and all three are worth one line here
    rather than a re-render later.
    """
    out = []
    for word in guide or {}:
        if _appears_verbatim(word, narration):
            continue
        if _appears_inflected(word, narration):
            continue     # 'Lee-Enfield' guides the read of 'Lee-Enfields'
        if _appears_verbatim(word, narration, fold=True):
            out.append(f"guide entry “{word}” appears in the script only with "
                       f"different capitalisation")
        else:
            out.append(f"guide entry “{word}” does not appear in the narration — "
                       f"export artifact, spelling drift, or a stale guide entry")

    for m in _ORPHAN_DECIMAL.finditer(narration):
        s = max(0, m.start() - 26)
        ctx = narration[s:m.end() + 12].replace("\n", " ").strip()
        out.append(f"orphaned decimal point: “…{ctx}…” — a Docs export splits "
                   f'".303" into ". 303", so the voice reads a sentence boundary '
                   f"mid-clause and says the number in full. Fix the script.")
    return out


# A production note to the reader, at the top of the script: "READ NOTE — please
# read before recording", then the rules for the session. It is the one block that
# must never be narrated, and it is also where the delivery instructions live, so
# it is lifted out and kept rather than merely deleted.
_NOTE_HEAD = re.compile(
    r"^\s*[#*_\s]*((read\s*me|read\s*note|note\s*to\s*(the\s*)?(reader|voice|narrator)|"
    r"voice\s*note|delivery\s*note|recording\s*note|before\s*recording|"
    r"performance\s*note)s?)\b.{0,60}$", re.I)


def split_read_note(text):
    """-> (script without the production note, [note lines])

    The note runs from its heading to the first divider or chapter heading. Both
    terminators matter: a script may separate the note with a rule, or go straight
    into '## Coca'.
    """
    lines = text.split("\n")
    start = None
    for i, ln in enumerate(lines[:40]):          # it lives at the top, before the body
        if _NOTE_HEAD.match(ln):
            start = i
            break
    if start is None:
        return text, []

    end = len(lines)
    for j in range(start + 1, len(lines)):
        s = lines[j].strip()
        if re.fullmatch(r"[-_*=~]{3,}|[—–]{2,}", s) or re.match(r"^#{1,6}\s+\S", s):
            end = j
            break
    note = [ln.strip() for ln in lines[start:end] if ln.strip()]
    return "\n".join(lines[:start] + lines[end:]), note


def note_wants_runon(note):
    """Does the production note ask for the chapter name to run into the sentence?

    'Run straight from the chapter name into the first sentence. No pause.' is an
    instruction about generation, not a line to read, and it contradicts the
    profile's chapter pause — so it has to be seen rather than narrated past.
    """
    blob = " ".join(note).lower()
    if not blob:
        return None
    runon = re.search(r"no pause|without a pause|run (straight|on) (from|into)"
                      r"|straight into the first sentence|not an announcement", blob)
    return True if runon else None


def is_title_case_heading(s):
    """A standalone Title-Case line — 'Siren Head' — not a sentence."""
    if len(s) > 60:
        return False
    if re.search(r"[.!?…,;][\"'”’)]*$", s):        # real sentences end punctuated
        return False
    if re.match(r"^[\"'“”‘’\-–—]", s):             # dialogue / continuation
        return False
    words = s.split()
    if len(words) > 8 or not words:
        return False
    if not re.match(r"^[A-Z0-9]", s):
        return False
    for w in words:
        w = re.sub(r"^[\"'“‘(]+|[\"'”’)]+$", "", w)
        if not w:
            continue
        if not re.match(r"^[A-Z0-9]", w) and not _SMALL_WORD.match(w):
            return False                            # a lowercase content word = prose
    return True


def _classify(s, idx, lines, prev_type):
    """One line -> (type, meta, say). Order matters; it mirrors the studio's if-chain."""
    def blank_at(i):
        if i < 0 or i >= len(lines):
            return True                             # document edges count as blank
        return not lines[i].strip()

    if not s:
        return "blank", False, ""
    if re.fullmatch(r"[-_*=~]{3,}|[—–]{2,}", s):
        # a markdown horizontal rule, the divider above the pronunciation guide.
        # It is punctuation for the eye; narrated it is at best a stray noise.
        # Counted apart from stage directions so the pre-flight summary does not
        # claim an "[SFX: …]" line where there is only a rule.
        return "divider", False, ""
    if re.match(r"^#{1,6}\s+" + _META_LABELS + r"\s*:?\s*$", s, re.I):
        return "heading", True, ""                  # ## Hook
    if re.match(r"^#{1,6}\s+", s):
        return "heading", False, ""                 # ## Siren Head
    if re.match(r"^\[[^\]]{1,80}\]$", s) or re.match(r"^\*[^*]{1,80}\*$", s):
        return "direction", False, ""               # [SFX: sirens], *pause*
    if (re.match(_SECTION_WORD + r"\s*(\d+|[ivxIVX]+)\b[:.\-–—)]?\s*.{0,60}$", s, re.I)
            and not re.search(r"[.!?…]$", s)):
        # 'Section 3: The Basement' -> announce 'The Basement'; bare 'Section 3' -> never spoken
        rest = re.sub(_SECTION_WORD + r"\s*(\d+|[ivxIVX]+)\b[:.\-–—)]?\s*", "", s, flags=re.I).strip()
        return ("heading", False, rest) if rest else ("heading", True, "")
    if re.match(r"^" + _META_LABELS + r"\s*:?\s*$", s, re.I):
        return "heading", True, ""                  # structural label, never spoken
    if (re.match(r"^\d{1,2}[.):]\s+\S", s) and len(s) <= 60
            and not re.search(r"[.!?…,]$", s) and len(s.split()) <= 8):
        return "heading", False, ""                 # 3. The Basement
    if s == s.upper() and re.search(r"[A-Z]", s) and len(s) <= 60 and not re.search(r"[.!?…]$", s):
        return "heading", False, ""                 # THE DISCOVERY
    if re.search(r":$", s) and len(s) <= 60 and len(s.split()) <= 8:
        return "heading", False, ""                 # The basement:
    if is_title_case_heading(s) and (
            blank_at(idx - 1)
            or re.search(r"[.!?…][\"'”’)]*\s*$", lines[idx - 1].strip() if idx > 0 else "")
            or prev_type in ("direction", "heading")):
        return "heading", False, ""
    return "text", False, ""


def detect_structure(text, runon=False):
    """-> dict(headings, directions, ctas, cta_previews, cleaned, spoken, items)

    cleaned = headings removed entirely (skip mode)
    spoken  = headings normalised into chapter announcements (read mode)
    """
    lines = text.split("\n")
    items, headings, directions, dividers = [], [], 0, 0
    prev_type = None
    for idx, line in enumerate(lines):
        s = line.strip()
        typ, meta, say = _classify(s, idx, lines, prev_type)
        items.append({"text": line, "type": typ, "meta": meta, "say": say})
        if typ == "heading":
            headings.append(re.sub(r"^#{1,6}\s+", "", s))
        if typ == "direction":
            directions += 1
        if typ == "divider":
            dividers += 1
        prev_type = typ

    kept, spoken, cta_previews = [], [], []
    pending_break = False
    pending_join = False        # runon: glue the next narration line to the chapter name
    prev_was_cta = False
    ctas = 0

    for it in items:
        if it["type"] in ("heading", "direction", "divider"):
            if kept and kept[-1] != "":
                kept.append("")                     # keep a paragraph break where it was
            if it["type"] == "heading" and it["meta"]:
                pending_break = True                # silent label still starts a fresh section
            if it["type"] == "heading" and not it["meta"]:
                h = (it["say"] or it["text"].strip())
                h = re.sub(r"^#{1,6}\s+", "", h)
                h = re.sub(r"^\d{1,2}[.):]\s+", "", h)
                h = re.sub(r":$", "", h)
                if not re.search(r"[.!?…]$", h):
                    h += "."
                if spoken and spoken[-1] != "":
                    spoken.append("")
                if runon:
                    # The name is a label, not an announcement: it leads the first
                    # sentence inside the SAME request, so there is no splice, no
                    # edge silence from the model and no prosodic reset between them.
                    spoken.append(SECTION_MARK + h)
                    pending_join = True
                else:
                    spoken.append(SECTION_MARK + h + PAUSE_MARK)
                    spoken.append("")
                pending_break = False
            elif spoken and spoken[-1] != "":
                spoken.append("")                   # directions/labels are never narrated
            prev_was_cta = False
            continue

        kept_out = "" if it["type"] == "blank" else it["text"]
        out = kept_out
        if it["type"] != "blank":
            is_cta = bool(CTA_RE.search(it["text"]))
            if is_cta and not prev_was_cta:
                ctas += 1
                pv = it["text"].strip()
                cta_previews.append(pv[:56] + "…" if len(pv) > 56 else pv)
                if kept and kept[-1] != "":
                    kept.append("")
                if spoken and spoken[-1] != "":
                    spoken.append("")
                kept_out = SECTION_MARK + PAUSE_MARK + kept_out
                out = SECTION_MARK + PAUSE_MARK + out
                pending_break = False
            prev_was_cta = is_cta

        kept.append(kept_out)
        if pending_join and not out:
            continue        # the blank after '## Coca' must not become the join target
        if pending_join and out:
            # 'Coca.' + ' The Inca chasqui carried…' -> one unit, one request
            spoken[-1] = spoken[-1] + " " + out.lstrip(SECTION_MARK + PAUSE_MARK)
            pending_join = False
            continue
        if pending_break and out:
            out = SECTION_MARK + out
            pending_break = False
        spoken.append(out)

    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    spoken_text = re.sub(r"\n{3,}", "\n\n", "\n".join(spoken)).strip()
    return {"headings": headings, "directions": directions, "dividers": dividers,
            "ctas": ctas,
            "cta_previews": cta_previews, "cleaned": cleaned, "spoken": spoken_text,
            "items": items}


def narration_text(raw, skip_headings=True, runon=False):
    """The text that will actually be narrated. Studio's effectiveScript()."""
    raw = raw.strip()
    if not raw:
        return ""
    st = detect_structure(raw, runon)
    if not st["headings"] and not st["directions"]:
        return raw
    return st["cleaned"] if skip_headings else st["spoken"]


def split_script(text, max_chunk=MAX_CHUNK):
    """Paragraph boundaries first, sentences if a paragraph is too big, then greedily
    merge back up to max_chunk. Never splits mid-sentence."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    units = []
    for p in paragraphs:
        if len(p) <= max_chunk:
            units.append(p)
            continue
        sentences = re.findall(r"[^.!?…]+[.!?…]+[\"'”’)]*\s*|[^.!?…]+$", p) or [p]
        cur = ""
        for s in sentences:
            if len(cur + s) > max_chunk and cur:
                units.append(cur.strip())
                cur = ""
            while len(s) > max_chunk:               # single sentence longer than the limit
                cut = s.rfind(" ", 0, max_chunk)
                if cut < 1:
                    cut = max_chunk
                units.append(s[:cut].strip())
                s = s[cut:]
            cur += s
        if cur.strip():
            units.append(cur.strip())

    chunks, buf = [], ""
    for u in units:
        is_head = u.startswith(SECTION_MARK)
        if is_head:
            u = u[1:]
        if buf and (is_head or len(buf) + len(u) + 2 > max_chunk):
            chunks.append(buf)
            buf = u
        else:
            buf = buf + "\n\n" + u if buf else u
        # a chapter announcement leads its own request, so the narration after it
        # starts fresh instead of continuing the heading's sentence
        if re.search(r"\x02\s*$", buf) and "\n" not in buf:
            chunks.append(buf)
            buf = ""
    if buf:
        chunks.append(buf)
    return chunks


def build_sections(script_text, skip_headings=False, max_chunk=MAX_CHUNK, runon=False):
    """-> list of {index, text, send_text, is_heading, is_cta, chars}

    text      keeps the markers (for gap computation)
    send_text is what goes to the TTS endpoint
    """
    narration = narration_text(script_text, skip_headings=skip_headings, runon=runon)
    out = []
    for i, t in enumerate(split_script(narration, max_chunk)):
        is_heading = bool(re.search(r"\x02\s*$", t)) and "\n" not in t
        is_cta = t.startswith(PAUSE_MARK)
        send = strip_markdown(
            re.sub(r"\s*\x02", "", t).replace(SECTION_MARK, "")).strip()
        out.append({"index": i, "text": t, "send_text": send,
                    "is_heading": is_heading, "is_cta": is_cta, "chars": len(send)})
    return out


def chapter_gaps(sections, preset="natural"):
    """gaps[i] = seconds of digital silence inserted BEFORE section i."""
    p = PAUSE_PRESETS.get(preset, PAUSE_PRESETS["natural"])
    gaps = []
    for i, c in enumerate(sections):
        prev = sections[i - 1] if i else None
        g = 0.0
        if c["is_heading"]:
            g = max(g, p["before"])                 # breathe before the chapter name
        if prev and prev["is_heading"]:
            g = max(g, p["after"])                  # then let the story start fresh
        if c["is_cta"]:
            g = max(g, p["cta"])
        # Nothing precedes the opening line, so there is nothing to breathe after.
        # The title sits here when it is read aloud, and a beat of silence before
        # the first word is dead air at the top of the video, not a pause.
        gaps.append(0.0 if i == 0 else g)
    return gaps


def master_script_lines(script_text, skip_headings=False, runon=False):
    """The script as humanize.py wants it: one paragraph per line, no markers.

    This must describe what was actually SPOKEN, or the forced alignment drifts —
    so it is derived from the same narration text the sections were built from.
    """
    narration = narration_text(script_text, skip_headings=skip_headings, runon=runon)
    lines = []
    for para in re.split(r"\n\s*\n", narration):
        p = strip_markdown(unmark(para)).strip()
        p = re.sub(r"\s*\n\s*", " ", p)             # a paragraph is one line
        if p:
            lines.append(p)
    return lines


def _cli():
    import argparse
    ap = argparse.ArgumentParser(description="Inspect how a script will be narrated.")
    ap.add_argument("script")
    ap.add_argument("--skip-headings", action="store_true")
    ap.add_argument("--max-chunk", type=int, default=MAX_CHUNK)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    raw = open(a.script, encoding="utf-8").read()
    st = detect_structure(raw)
    secs = build_sections(raw, a.skip_headings, a.max_chunk)
    if a.json:
        json.dump({"structure": {k: st[k] for k in
                                 ("headings", "directions", "ctas", "cta_previews")},
                   "sections": secs, "gaps": chapter_gaps(secs)},
                  sys.stdout, indent=1, ensure_ascii=False)
        return
    chars = sum(s["chars"] for s in secs)
    print(f"{len(st['headings'])} headings · {st['directions']} directions · {st['ctas']} CTAs")
    print(f"{len(secs)} sections · {chars} chars · ~{chars/14.7/60:.1f} min · ~{chars} credits")
    for s in secs:
        kind = "CHAPTER" if s["is_heading"] else "CTA" if s["is_cta"] else "        "
        print(f"  {s['index']+1:>3} {kind} {s['chars']:>5}ch  {s['send_text'][:70]!r}")


if __name__ == "__main__":
    _cli()
