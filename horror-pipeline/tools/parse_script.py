#!/usr/bin/env python3
"""script.md -> work/sections.json  (Stage 2, BUILD-PACKET section 4.1)

Splits an approved script on its section headings into an ordered list of
sections, each with a creature name, the narration text, the raw line numbers
of every narration line, the raw line numbers of any line marked as a dry
joke, and a CTA flag.

RAW LINE NUMBERS ARE THE POINT. A gag has to land on the beat the script
marked, not two sentences early, so every narration line keeps the 1-based
line number it has in script.md and joke_lines holds those same numbers.

Recognised markers (case-insensitive):
  direction line   **[VISUAL: ...]**   whole line dropped from narration
                   any whole line of the form [WORD: ...] or **[WORD: ...]**
  joke marker      **[JOKE]**  [JOKE]  [DRY JOKE]  [GAG]  <!-- joke -->
                   stripped from the narration text, line number recorded
  metadata line    **Key:** value      dropped
  rule             ---                 dropped

Section headings are level 3+ ATX headings. A heading numbered `N. Name` is a
creature section, a heading containing CTA is a cta section, anything else is
kept as kind "other" so no narration is silently lost.

Usage:
  parse_script.py /abs/path/script.md /abs/path/work/sections.json
  parse_script.py /abs/path/script.md /abs/path/work/sections.json --vo-text /abs/path/work/vo.txt

--vo-text writes the narration alone, in order, one section per paragraph.
That is the exact text to hand to the voice, and it is what makes the
transcript alignable in Stage 2.5.

Exit codes: 0 ok, 1 usage or parse error (no sections found).
"""
import json
import os
import re
import sys

HEADING = re.compile(r"^\s{0,3}(#{2,6})\s+(.*?)\s*#*\s*$")
CREATURE_HEAD = re.compile(r"^\s*(\d+)\s*[.):]\s*(.+)$")
WORDCOUNT = re.compile(r"\(\s*~?\s*\d[\d,]*\s*(?:words?|w)\s*\)", re.I)
DIRECTION_LINE = re.compile(r"^\**\s*\[[A-Z][A-Z0-9 /_&-]*:.*\]\s*\**$")
METADATA_LINE = re.compile(r"^\*\*[^*]{1,40}:\*\*")
JOKE_MARKER = re.compile(
    r"(?:\*\*)?\[\s*(?:DRY\s+)?(?:JOKE|GAG)\s*\](?:\*\*)?"
    r"|<!--\s*(?:dry\s+)?(?:joke|gag)\s*-->",
    re.I,
)
RULE_LINE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")


def abs_arg(p, what):
    if not os.path.isabs(p):
        sys.exit(f"ERROR: {what} must be an absolute path (got {p!r}). "
                 "The shell working directory is not stable between calls.")
    return p


def clean_title(raw):
    t = WORDCOUNT.sub("", raw)
    t = t.replace("**", "").replace("*", "")
    t = t.strip().strip("-").strip("—").strip("–").strip()
    return re.sub(r"\s{2,}", " ", t).strip(" .")


def creature_from_title(title):
    return re.sub(r"^(?:the|a|an)\s+", "", title, flags=re.I).strip()


def parse(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    sections = []
    cur = None
    stray_jokes = []

    def close(end_line):
        if cur is not None:
            cur["line_end"] = end_line
            sections.append(cur)

    for n, raw in enumerate(lines, start=1):
        m = HEADING.match(raw)
        if m:
            level, htext = len(m.group(1)), m.group(2)
            if level < 3:
                # level 2 and above are document furniture (## NARRATION)
                close(n - 1)
                cur = None
                continue
            title = clean_title(htext)
            cm = CREATURE_HEAD.match(title)
            if cm:
                kind, number, title = "creature", int(cm.group(1)), cm.group(2).strip()
                creature = creature_from_title(title)
            elif re.search(r"\bCTA\b", title, re.I):
                kind, number, creature = "cta", None, ""
            else:
                kind, number, creature = "other", None, ""
            close(n - 1)
            cur = {
                "index": len(sections) + 1,
                "kind": kind,
                "number": number,
                "creature": creature,
                "title": title,
                "cta": kind == "cta",
                "heading_line": n,
                "line_start": n + 1,
                "line_end": n + 1,
                "narration_lines": [],
                "joke_lines": [],
            }
            continue

        body = raw.strip()
        if not body or RULE_LINE.match(body):
            continue
        if DIRECTION_LINE.match(body) or METADATA_LINE.match(body):
            continue

        is_joke = bool(JOKE_MARKER.search(body))
        text = JOKE_MARKER.sub("", body).strip()
        text = re.sub(r"\s{2,}", " ", text)
        if not text:
            # a bare marker on its own line belongs to the previous narration line
            if is_joke and cur is not None and cur["narration_lines"]:
                prev = cur["narration_lines"][-1]["n"]
                if prev not in cur["joke_lines"]:
                    cur["joke_lines"].append(prev)
            continue
        if cur is None:
            if is_joke:
                stray_jokes.append(n)
            continue
        cur["narration_lines"].append({"n": n, "text": text})
        if is_joke:
            cur["joke_lines"].append(n)

    close(len(lines))

    for s in sections:
        s["text"] = "\n".join(l["text"] for l in s["narration_lines"])
        s["word_count"] = len(s["text"].split())
        if s["narration_lines"]:
            s["line_start"] = s["narration_lines"][0]["n"]
            s["line_end"] = s["narration_lines"][-1]["n"]
    sections = [s for s in sections if s["narration_lines"]]
    for i, s in enumerate(sections, start=1):
        s["index"] = i
    return sections, stray_jokes, len(lines)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    vo_text = None
    for i, a in enumerate(sys.argv[1:]):
        if a == "--vo-text":
            if i + 2 >= len(sys.argv):
                sys.exit("ERROR: --vo-text needs a path")
            vo_text = abs_arg(sys.argv[i + 2], "--vo-text")
        elif a.startswith("--vo-text="):
            vo_text = abs_arg(a.split("=", 1)[1], "--vo-text")
    if vo_text:
        args = [a for a in args if a != vo_text]
    if len(args) != 2:
        sys.exit(__doc__)
    src = abs_arg(args[0], "script.md")
    out = abs_arg(args[1], "sections.json")
    if not os.path.isfile(src):
        sys.exit(f"ERROR: no such script: {src}")
    unknown = [f for f in flags if f.split("=")[0] not in ("--vo-text",)]
    if unknown:
        sys.exit(f"ERROR: unknown flag(s): {' '.join(unknown)}")

    sections, stray_jokes, nlines = parse(src)
    if not sections:
        sys.exit(f"ERROR: no sections found in {src}. Expected level 3 headings "
                 "like '### 1. Cartoon Cat' or '### - MID CTA -'.")

    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(sections, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    if vo_text:
        os.makedirs(os.path.dirname(vo_text), exist_ok=True)
        with open(vo_text, "w", encoding="utf-8") as f:
            f.write("\n\n".join(" ".join(s["text"].split("\n")) for s in sections) + "\n")

    kinds = {}
    for s in sections:
        kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
    total_words = sum(s["word_count"] for s in sections)
    jokes = [(s["index"], n) for s in sections for n in s["joke_lines"]]

    print("SUMMARY parse_script")
    print(f"  script   : {src} ({nlines} lines)")
    print(f"  sections : {len(sections)}  ({', '.join(f'{k} {v}' for k, v in sorted(kinds.items()))})")
    print(f"  {'idx':>3} {'kind':<8} {'creature/title':<34} {'lines':>9} {'words':>6}  jokes")
    for s in sections:
        label = s["creature"] or s["title"]
        span = f"{s['line_start']}-{s['line_end']}"
        jl = ",".join(str(n) for n in s["joke_lines"]) or "-"
        print(f"  {s['index']:>3} {s['kind']:<8} {label[:34]:<34} {span:>9} {s['word_count']:>6}  {jl}")
    print(f"  words    : {total_words} total, est {total_words / 170 * 60:.0f}s at 170 wpm")
    print(f"  jokes    : {len(jokes)} marked line(s)" + (f" -> {[n for _, n in jokes]}" if jokes else ""))
    if vo_text:
        print(f"  vo text  : {vo_text}")
    print(f"  wrote    : {out}")

    if stray_jokes:
        print(f"  WARNING  : joke marker outside any section at line(s) "
              f"{stray_jokes}; it will never resolve to a gag", file=sys.stderr)
    empty = [s["index"] for s in sections if s["word_count"] < 5]
    if empty:
        print(f"  WARNING  : section(s) {empty} have under 5 narration words", file=sys.stderr)


if __name__ == "__main__":
    main()
