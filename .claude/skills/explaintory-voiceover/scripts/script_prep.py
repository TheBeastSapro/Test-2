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
# model already renders at section edges. 'natural' matches Sapro's hand edits:
# ~0.45s before the chapter name, ~0.50s after it.
PAUSE_PRESETS = {
    "tight":   {"before": 0.10, "after": 0.18, "cta": 0.20},
    "natural": {"before": 0.22, "after": 0.30, "cta": 0.30},
    "wide":    {"before": 0.40, "after": 0.55, "cta": 0.55},
}

CTA_RE = re.compile(
    r"\b(subscribe|leave a like|like and subscribe|smash (the|that) like( button)?"
    r"|notification bell|hit the bell|turn on notifications?|comment (below|which|what|down|if)"
    r"|drop a (like|comment)|in the comments)\b", re.I)

_META_LABELS = r"(intro|outro|hook|conclusion|opening|closing|cta|title|the end)"
_SECTION_WORD = r"(section|part|chapter|act|scene|segment)"
_SMALL_WORD = re.compile(
    r"^(of|the|and|a|an|in|on|to|for|vs|or|at|by|is|it|with|from|as|but|nor|into"
    r"|onto|upon|over|under|off|out|up|down|near|no)$", re.I)


def unmark(t):
    return t.replace(SECTION_MARK, "").replace(PAUSE_MARK, "")


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


def split_pronunciation_guide(text):
    """-> (script without the guide, {word: respelling})

    Looks only at the tail, because that is where it lives and because a mid-script
    line like 'The corvus — a boarding bridge — decided the battle' must never be
    mistaken for a glossary entry.
    """
    lines = text.split("\n")
    for i in range(len(lines) - 1, max(-1, len(lines) - 60), -1):
        if not _GUIDE_HEAD.match(lines[i]):
            continue
        body = lines[i + 1:]
        if not _looks_like_guide_body(body):
            continue
        guide = {}
        for ln in body:
            m = _GUIDE_LINE.match(ln)
            if m:
                w, say = m.group(1).strip(" *-•"), m.group(2).strip()
                if w and say:
                    guide[w] = say
        return "\n".join(lines[:i]).rstrip(), guide
    return text, {}


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
        return "direction", False, ""
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


def detect_structure(text):
    """-> dict(headings, directions, ctas, cta_previews, cleaned, spoken, items)

    cleaned = headings removed entirely (skip mode)
    spoken  = headings normalised into chapter announcements (read mode)
    """
    lines = text.split("\n")
    items, headings, directions = [], [], 0
    prev_type = None
    for idx, line in enumerate(lines):
        s = line.strip()
        typ, meta, say = _classify(s, idx, lines, prev_type)
        items.append({"text": line, "type": typ, "meta": meta, "say": say})
        if typ == "heading":
            headings.append(re.sub(r"^#{1,6}\s+", "", s))
        if typ == "direction":
            directions += 1
        prev_type = typ

    kept, spoken, cta_previews = [], [], []
    pending_break = False
    prev_was_cta = False
    ctas = 0

    for it in items:
        if it["type"] in ("heading", "direction"):
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
        if pending_break and out:
            out = SECTION_MARK + out
            pending_break = False
        spoken.append(out)

    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    spoken_text = re.sub(r"\n{3,}", "\n\n", "\n".join(spoken)).strip()
    return {"headings": headings, "directions": directions, "ctas": ctas,
            "cta_previews": cta_previews, "cleaned": cleaned, "spoken": spoken_text,
            "items": items}


def narration_text(raw, skip_headings=True):
    """The text that will actually be narrated. Studio's effectiveScript()."""
    raw = raw.strip()
    if not raw:
        return ""
    st = detect_structure(raw)
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


def build_sections(script_text, skip_headings=False, max_chunk=MAX_CHUNK):
    """-> list of {index, text, send_text, is_heading, is_cta, chars}

    text      keeps the markers (for gap computation)
    send_text is what goes to the TTS endpoint
    """
    narration = narration_text(script_text, skip_headings=skip_headings)
    out = []
    for i, t in enumerate(split_script(narration, max_chunk)):
        is_heading = bool(re.search(r"\x02\s*$", t)) and "\n" not in t
        is_cta = t.startswith(PAUSE_MARK)
        send = re.sub(r"\s*\x02", "", t).replace(SECTION_MARK, "").strip()
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
        gaps.append(g)
    return gaps


def master_script_lines(script_text, skip_headings=False):
    """The script as humanize.py wants it: one paragraph per line, no markers.

    This must describe what was actually SPOKEN, or the forced alignment drifts —
    so it is derived from the same narration text the sections were built from.
    """
    narration = narration_text(script_text, skip_headings=skip_headings)
    lines = []
    for para in re.split(r"\n\s*\n", narration):
        p = unmark(para).strip()
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
