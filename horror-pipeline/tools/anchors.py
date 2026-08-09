#!/usr/bin/env python3
"""Resolve word anchors to seconds against work/words.json.
(Stage 2, BUILD-PACKET section 4.4)

A sheet never says "t0": 25.95. It says "put this pop on the word THIRTY,
second occurrence, offset -0.05". The number is resolved at build time. That
is what makes an edit survive a re-recorded voiceover: re-transcribe,
rebuild, and the whole cut re-syncs itself instead of being redone by hand.

Two rules that are not negotiable:

1. RESTRICT EVERY SEARCH TO ITS SECTION'S TIME RANGE. The word "thirty"
   appears in four different creature sections. Passing section=(start, end)
   is what stops a pop for creature 6 resolving into creature 2.

2. A MISS RAISES AND STOPS. Never fall back to a guessed time. A LookupError
   here almost always means the model invented a phrase the narrator never
   said, which is exactly what should be caught at build time and not at
   4:12 in the finished render.

Library use:
    from anchors import Anchors, section_range
    a = Anchors("/abs/work/words.json")
    sec = section_range("/abs/work/sections.json", 4)   # by index
    t = a.at("thirty", occurrence=1, offset=-0.05, section=sec)

CLI use:
  anchors.py /abs/work/words.json thirty
  anchors.py /abs/work/words.json thirty --occurrence 2 --offset -0.05
  anchors.py /abs/work/words.json "forty feet" --sections /abs/work/sections.json --section 4
  anchors.py /abs/work/words.json thirty --range 95.0 140.0 --json
  anchors.py /abs/work/words.json --batch /abs/anchors.json

--batch takes a list of {"phrase","occurrence","offset","section"} objects,
where section is an integer section index or a [lo, hi] pair, and resolves
them all; ANY miss fails the whole batch, which is the point.

Exit codes: 0 all resolved, 1 usage error, 4 anchor not found.
"""
import json
import os
import re
import sys

_WORD_RE = re.compile(r"[^a-z0-9]")

# faster-whisper writes spoken numbers as digits: the narrator says "thirty
# feet" and base.en emits "30 feet". The packet's own example anchor is the
# word THIRTY, which therefore never resolves against a raw transcript. Worse,
# the surface form is not stable across models, so a sheet written against
# base.en can break under small.en. Both sides go through this table, so
# "thirty", "Thirty," and "30" are one token.
_NUMS = {
    "zero": 0, "oh": None, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fourty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000, "million": 1000000,
}
_NUMS = {k: v for k, v in _NUMS.items() if v is not None}
_TENS = re.compile(r"^(twenty|thirty|forty|fourty|fifty|sixty|seventy|eighty|ninety)"
                   r"(one|two|three|four|five|six|seven|eight|nine)$")


def norm(s):
    """Fold a word to its comparison key. Digits and number words collapse
    together so an anchor can be written the way the script says it."""
    t = _WORD_RE.sub("", str(s).lower())
    if t in _NUMS:
        return str(_NUMS[t])
    m = _TENS.match(t)          # "twenty-five" survives the punctuation strip
    if m:
        return str(_NUMS[m.group(1)] + _NUMS[m.group(2)])
    return t


class Anchors:
    def __init__(self, words_path):
        self.path = words_path
        self.words = json.load(open(words_path, encoding="utf-8"))
        if not isinstance(self.words, list) or not self.words:
            raise ValueError(f"{words_path} is not a non-empty list of words")
        self.norm = [norm(w["w"]) for w in self.words]

    def find(self, phrase, occurrence=1, section=None):
        """phrase may be one word or several. Returns (start, end) seconds."""
        target = [norm(p) for p in str(phrase).split() if norm(p)]
        if not target:
            raise ValueError(f"anchor phrase {phrase!r} is empty after normalisation")
        if occurrence < 1:
            raise ValueError(f"occurrence must be 1 or more, got {occurrence}")
        lo, hi = (section or (0, 10 ** 9))
        hits = []
        for i in range(len(self.norm) - len(target) + 1):
            if self.norm[i:i + len(target)] != target:
                continue
            s, e = self.words[i]["s"], self.words[i + len(target) - 1]["e"]
            if lo <= s <= hi:
                hits.append((s, e))
        if len(hits) < occurrence:
            raise LookupError(
                f"anchor {phrase!r} occurrence {occurrence} not found "
                f"in {lo:.1f}-{hi:.1f}s (found {len(hits)})"
                f"{self._hint(target, lo, hi, len(hits))}")
        return hits[occurrence - 1]

    def at(self, phrase, occurrence=1, offset=0.0, section=None):
        s, _ = self.find(phrase, occurrence, section)
        return round(s + offset, 3)

    def span(self, phrase, occurrence=1, section=None):
        """(start, end) of the whole phrase, for a pop that must cover it."""
        return self.find(phrase, occurrence, section)

    def resolve_all(self, specs, sections=None):
        """Resolve a list of anchor dicts. Any miss raises: no partial builds."""
        out = []
        for k, spec in enumerate(specs):
            rng = spec.get("section")
            if isinstance(rng, int) and sections is not None:
                rng = _range_from_sections(sections, rng)
            elif isinstance(rng, (list, tuple)):
                rng = (float(rng[0]), float(rng[1]))
            elif rng is not None and not isinstance(rng, tuple):
                raise ValueError(f"anchor {k}: bad section {rng!r}")
            try:
                out.append(self.at(spec["phrase"], int(spec.get("occurrence", 1)),
                                   float(spec.get("offset", 0.0)), rng))
            except LookupError as e:
                raise LookupError(f"anchor {k} ({spec}): {e}") from None
        return out

    def _hint(self, target, lo, hi, in_range):
        """Name the near misses. Still raises: this only improves the message."""
        total = sum(1 for i in range(len(self.norm) - len(target) + 1)
                    if self.norm[i:i + len(target)] == target)
        bits = []
        if total > in_range:
            bits.append(f"{total - in_range} occurrence(s) exist OUTSIDE this range, "
                        "so either the section restriction is doing its job or the "
                        "range is wrong")
        elif total:
            bits.append(f"{total} occurrence(s) exist in the whole file, so the "
                        "occurrence number is too high")
        if not in_range:
            head = target[0]
            near = sorted({w for w, t in zip(self.norm, self.words)
                           if w and lo <= t["s"] <= hi and w != head
                           and (w.startswith(head[:4]) or head.startswith(w[:4]))})
            if near:
                bits.append("similar words in range: " + ", ".join(near[:8]))
        return ("; " + "; ".join(bits)) if bits else ""


def _range_from_sections(sections, index):
    for s in sections:
        if s.get("index") == index:
            if "start" not in s or "end" not in s:
                raise KeyError(f"section {index} has no start/end. "
                               "Run tools/align_sections.py first.")
            return (float(s["start"]), float(s["end"]))
    raise KeyError(f"no section with index {index}")


def section_range(sections_path, index):
    """(start, end) for a section index, from an aligned sections.json."""
    return _range_from_sections(json.load(open(sections_path, encoding="utf-8")), index)


def abs_arg(p, what):
    if not os.path.isabs(p):
        sys.exit(f"ERROR: {what} must be an absolute path (got {p!r}). "
                 "The shell working directory is not stable between calls.")
    return p


def main():
    argv, pos = sys.argv[1:], []
    occurrence, offset, rng, sec_idx, sec_path, batch, as_json = 1, 0.0, None, None, None, None, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--json":
            as_json = True
        elif a == "--range":
            if i + 2 >= len(argv):
                sys.exit("ERROR: --range needs LO HI")
            rng = (float(argv[i + 1]), float(argv[i + 2]))
            i += 2
        elif a.startswith("--"):
            key, _, inline = a.partition("=")
            val = inline if inline else (argv[i + 1] if i + 1 < len(argv) else None)
            if not inline:
                i += 1
            if val is None:
                sys.exit(f"ERROR: {key} needs a value")
            if key == "--occurrence":
                occurrence = int(val)
            elif key == "--offset":
                offset = float(val)
            elif key == "--section":
                sec_idx = int(val)
            elif key == "--sections":
                sec_path = abs_arg(val, "--sections")
            elif key == "--batch":
                batch = abs_arg(val, "--batch")
            else:
                sys.exit(f"ERROR: unknown flag {key}")
        else:
            pos.append(a)
        i += 1

    if not pos:
        sys.exit(__doc__)
    words_path = abs_arg(pos[0], "words.json")
    if not os.path.isfile(words_path):
        sys.exit(f"ERROR: no such words file: {words_path}")
    a = Anchors(words_path)
    sections = json.load(open(sec_path, encoding="utf-8")) if sec_path else None

    if batch:
        specs = json.load(open(batch, encoding="utf-8"))
        try:
            times = a.resolve_all(specs, sections)
        except (LookupError, KeyError, ValueError) as e:
            print(f"ANCHOR FAILURE: {e}", file=sys.stderr)
            print("Nothing was resolved. Fix the sheet or the transcript; "
                  "do not guess a time.", file=sys.stderr)
            sys.exit(4)
        if as_json:
            print(json.dumps([{**s, "t": t} for s, t in zip(specs, times)], indent=1))
        else:
            print("SUMMARY anchors (batch)")
            print(f"  words   : {words_path} ({len(a.words)} words)")
            print(f"  resolved: {len(times)}/{len(specs)}")
            for s, t in zip(specs, times):
                print(f"    {t:8.3f}s  {s['phrase']!r} occ {s.get('occurrence', 1)} "
                      f"offset {s.get('offset', 0.0):+g} section {s.get('section', 'any')}")
        return

    if len(pos) < 2:
        sys.exit("ERROR: need a phrase to resolve (or --batch)")
    phrase = " ".join(pos[1:])
    if sec_idx is not None:
        if not sec_path:
            sys.exit("ERROR: --section needs --sections /abs/work/sections.json")
        try:
            rng = _range_from_sections(sections, sec_idx)
        except KeyError as e:
            sys.exit(f"ERROR: {e}")

    try:
        s, e = a.find(phrase, occurrence, rng)
    except (LookupError, ValueError) as err:
        print(f"ANCHOR FAILURE: {err}", file=sys.stderr)
        print("Not resolving to a guessed time. This usually means the phrase "
              "was never spoken, or it belongs to a different section.", file=sys.stderr)
        sys.exit(4)
    t = round(s + offset, 3)

    if as_json:
        print(json.dumps({"phrase": phrase, "occurrence": occurrence, "offset": offset,
                          "t": t, "word_start": s, "word_end": e,
                          "section": sec_idx, "range": rng}))
        return
    where = (f"section {sec_idx} ({rng[0]:.2f}-{rng[1]:.2f}s)" if sec_idx is not None
             else (f"{rng[0]:.2f}-{rng[1]:.2f}s" if rng else "whole file"))
    print("SUMMARY anchors")
    print(f"  words   : {words_path} ({len(a.words)} words)")
    print(f"  search  : {phrase!r} occurrence {occurrence} in {where}")
    print(f"  word    : {s:.3f}s -> {e:.3f}s")
    print(f"  t       : {t:.3f}s (offset {offset:+g})")


if __name__ == "__main__":
    main()
