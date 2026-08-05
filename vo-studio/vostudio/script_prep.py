"""
Turn a script into the units that get generated, checked and re-rolled.

Two jobs, and the second one is the one that bites.

SECTIONS are what the writer sees: chapter headers and paragraphs.
CHUNKS are what the model sees, and they exist because ChatterboxTTS.generate()
caps at max_new_tokens=1000 -- about 40 s of speech -- with quality degrading
well before the ceiling. A chunk that overruns does not raise; it truncates, and
a truncated chunk is a silently dropped clause.

Chunking on sentence boundaries also means a bad roll is re-rolled alone. Chunk
a whole paragraph and one stumbled word costs you the paragraph.
"""
import re
from dataclasses import dataclass, field


# Numerals are spelled out before they reach the model AND before alignment.
# In the old pipeline they were dropped from alignment entirely, which put the
# pause beats on the wrong punctuation -- one bug that produced a mid-sentence
# stumble, a missing comma, and 21 silences that could not be traced to anything.
_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
         "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
         "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
         "eighty", "ninety"]


def _under_1000(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("-" + _ONES[n % 10] if n % 10 else "")
    return _ONES[n // 100] + " hundred" + (" " + _under_1000(n % 100) if n % 100 else "")


_SCALES = ((1_000_000_000_000, "trillion"), (1_000_000_000, "billion"),
           (1_000_000, "million"), (1_000, "thousand"))


def spell_number(n: int, year_ok: bool = True) -> str:
    """
    Words for a number.

    year_ok says whether the year reading is allowed. "1798" is a year;
    "1,250 soldiers" is a quantity, and reading it "twelve fifty" was wrong.
    The comma in the source is what tells them apart, so the caller decides.

    1805 reads "eighteen oh five", not "eighteen five".
    """
    if year_ok and 1100 <= n <= 1999 and n % 100 != 0:
        tail = n % 100
        # "oh five", the way a year with a single-digit tail is actually said.
        spoken_tail = f"oh {_ONES[tail]}" if 1 <= tail <= 9 else _under_1000(tail)
        return f"{_under_1000(n // 100)} {spoken_tail}"
    if n < 1000:
        return _under_1000(n)
    # Scales, largest first. The old code went straight to millions and handed
    # _under_1000 a value >= 2000 for anything over two billion -- an
    # IndexError that killed the render on a phone number.
    for value, word in _SCALES:
        if n >= value:
            head = spell_number(n // value, year_ok=False) + " " + word
            rest = n % value
            return head + (" " + spell_number(rest, year_ok=False) if rest else "")
    return _under_1000(n)


_ORDINAL = {1: "first", 2: "second", 3: "third", 5: "fifth", 8: "eighth",
            9: "ninth", 12: "twelfth"}


def spell_ordinal(n: int) -> str:
    """3rd -> third. Irregular below thirteen, then -th on the last word."""
    if n in _ORDINAL:
        return _ORDINAL[n]
    words = spell_number(n)
    head, _, last = words.rpartition(" ")
    stem, _, tail = last.rpartition("-")
    base = tail or last
    if base in _ORDINAL_STEM:
        base = _ORDINAL_STEM[base]
    elif base.endswith("y"):
        base = base[:-1] + "ieth"
    else:
        base = base + "th"
    # rpartition puts the WHOLE string in `tail` when there is no separator,
    # so testing `tail` produced "-fourth" and "one -thousandth". Test the
    # separator instead.
    last = (stem + "-" + base) if stem else base
    return (head + " " + last).strip()


_ORDINAL_STEM = {"one": "first", "two": "second", "three": "third", "five": "fifth",
                 "eight": "eighth", "nine": "ninth", "twelve": "twelfth"}


def _plural(word: str) -> str:
    return word[:-1] + "ies" if word.endswith("y") else word + "s"


def _decade(n: int) -> str:
    """
    1980s -> nineteen eighties. 1900s -> nineteen hundreds. 2000s -> two
    thousands. The plain year reading is wrong here: it drops the century for
    round hundreds ("one thousand nine hundreds") and it is not how a decade
    is said aloud.
    """
    if n % 1000 == 0:
        return _plural(spell_number(n, year_ok=False))
    century, tail = divmod(n, 100)
    if 11 <= century <= 20:
        head = _under_1000(century)
        return f"{head} hundreds" if tail == 0 else f"{head} {_plural(_under_1000(tail))}"
    return _plural(spell_number(n, year_ok=False))


def _decimal(whole: str, frac: str) -> str:
    """12.5 -> twelve point five. Digits after the point are read one by one,
    which is how they are said aloud: 'point four five', never 'point 45'."""
    digits = " ".join(_ONES[int(d)] for d in frac)
    return f"{spell_number(int(whole.replace(',', '')))} point {digits}"


# "$1.5 million" is not one dollar fifty. A scale word after the amount means
# the decimal is part of the NUMBER, not cents.
_SCALE_AFTER = re.compile(r"\s*(million|billion|trillion)\b", re.I)


def _money(whole: str, cents: str | None) -> str:
    """$3,400 -> three thousand four hundred dollars. $9.99 -> nine dollars
    ninety-nine. The symbol must not survive: every TTS reads a bare $ as
    'dollar sign', and it reads it in the wrong place -- before the number."""
    n = int(whole.replace(",", ""))
    head = f"{spell_number(n)} dollar{'' if n == 1 else 's'}"
    if cents and int(cents):
        return f"{head} {spell_number(int(cents.ljust(2, '0')))}"
    return head


def spell_numerals(text: str) -> str:
    """
    Everything a voice cannot read as a symbol, turned into words.

    ORDER MATTERS, and it is the whole reason this is one function rather than
    several. Spell the bare numbers first and '$3,400' becomes
    '$three thousand four hundred' -- the dollar sign survives, gets read
    literally, and lands in front of the number where nobody says it. Money and
    percentages have to be consumed WITH their symbol, before anything else
    touches the digits.
    """
    # $1.5 million -> one point five million dollars. Checked first, because
    # the plain money rule below would read the .5 as fifty cents.
    text = re.sub(r"\$\s?(\d[\d,]*)(?:\.(\d+))?\s*(million|billion|trillion)\b",
                  lambda m: (_decimal(m.group(1), m.group(2)) if m.group(2)
                             else spell_number(int(m.group(1).replace(",", "")), year_ok=False))
                            + f" {m.group(3).lower()} dollars", text, flags=re.I)
    # $3,400 / $9.99 / $1
    text = re.sub(r"\$\s?(\d[\d,]*)(?:\.(\d{1,2}))?",
                  lambda m: _money(m.group(1), m.group(2)), text)
    # 45% / 12.5%
    text = re.sub(r"(\d[\d,]*)(?:\.(\d+))?\s?%",
                  lambda m: (_decimal(m.group(1), m.group(2)) if m.group(2)
                             else spell_number(int(m.group(1).replace(",", "")))) + " percent",
                  text)
    # 3rd -> third
    text = re.sub(r"\b(\d[\d,]*)(?:st|nd|rd|th)\b",
                  lambda m: spell_ordinal(int(m.group(1).replace(",", ""))), text)
    # 12.5 on its own
    text = re.sub(r"\b(\d[\d,]*)\.(\d+)\b",
                  lambda m: _decimal(m.group(1), m.group(2)), text)
    # 1980s -> nineteen eighties, not "nineteen eightys". The old pattern had
    # no boundary before the s at all, so the digits reached the model raw.
    text = re.sub(r"\b(\d{4})s\b", lambda m: _decade(int(m.group(1))), text)
    # everything left. A comma in the source means a QUANTITY, so "1,250
    # soldiers" is twelve hundred and fifty, not the year twelve fifty.
    text = re.sub(r"\b\d[\d,]*\b",
                  lambda m: spell_number(int(m.group(0).replace(",", "")),
                                         year_ok="," not in m.group(0)), text)
    # & is read as 'ampersand' by some engines and skipped by others
    text = re.sub(r"\s&\s", " and ", text)
    return text


@dataclass
class Chunk:
    text: str
    index: int
    audio_path: str = ""
    attempts: int = 0
    wer: float = -1.0
    transcript: str = ""


@dataclass
class Section:
    title: str
    text: str
    is_chapter: bool
    index: int
    chunks: list[Chunk] = field(default_factory=list)


def split_sentences(text: str) -> list[str]:
    """
    Sentence split that does not break on the abbreviations a history script is
    full of. "Dr. Temmler" and "U.S. forces" are not two sentences.
    """
    protected = text
    for abbr in ["Dr.", "Mr.", "Mrs.", "Ms.", "St.", "Prof.", "Gen.", "Col.",
                 "Lt.", "Sgt.", "Capt.", "vs.", "etc.", "e.g.", "i.e.", "No."]:
        protected = protected.replace(abbr, abbr.replace(".", "\x00"))
    # NOT a raw replacement string: r"\1\x00" makes re's template parser read \x as
    # a bad escape, and the sentence splitter dies on any script containing "U.S."
    protected = re.sub(r"\b([A-Z])\.", "\\1\x00", protected)   # U.S. , F.D.R.

    parts = re.split(r"(?<=[.!?])\s+", protected)
    return [p.replace("\x00", ".").strip() for p in parts if p.strip()]


def _split_on_spaces(text: str, max_chars: int) -> list[str]:
    """Break a long run at the last space that fits; only cut a word if a single
    word is itself longer than the limit."""
    parts, rest = [], text.strip()
    while len(rest) > max_chars:
        cut = rest.rfind(" ", 0, max_chars + 1)
        if cut <= 0:
            cut = max_chars                      # one unbroken word, nothing to do
        parts.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        parts.append(rest)
    return [p for p in parts if p]


def chunk_text(text: str, max_chars: int) -> list[str]:
    """
    Pack whole sentences up to max_chars. A single sentence longer than the limit
    is split at a comma rather than mid-clause, and only mid-word as a last
    resort -- a chunk boundary inside a word is audible at the join no matter how
    good the crossfade is.
    """
    out: list[str] = []
    buf = ""
    for sent in split_sentences(text):
        if len(sent) > max_chars:
            if buf:
                out.append(buf.strip())
                buf = ""
            piece = ""
            for clause in re.split(r"(?<=,)\s+", sent):
                if len(piece) + len(clause) + 1 <= max_chars:
                    piece = f"{piece} {clause}".strip()
                else:
                    if piece:
                        out.append(piece.strip())
                    piece = clause if len(clause) <= max_chars else ""
                    if not piece:
                        # AT A SPACE, not at a character count. The docstring
                        # promised mid-word only as a last resort, and then went
                        # straight to a fixed-width slice -- so a long
                        # comma-free sentence (routine in narration) was handed
                        # to the model as "...the obvious qu" / "estion about".
                        # Both halves then fail the read-check, burn every
                        # re-roll, and land in NEEDS AN EAR.
                        out.extend(_split_on_spaces(clause, max_chars))
            if piece:
                out.append(piece.strip())
            continue

        if len(buf) + len(sent) + 1 <= max_chars:
            buf = f"{buf} {sent}".strip()
        else:
            out.append(buf.strip())
            buf = sent
    if buf:
        out.append(buf.strip())
    return [c for c in out if c]


def parse_script(raw: str, max_chars: int = 300) -> list[Section]:
    """
    A line alone in its own paragraph, three words or fewer, no terminal
    punctuation, is a chapter header. That is the ExplainTory convention and it
    is what earns the 0.30 s gap and the exemption from the rate/WER checks --
    those checks cannot mean anything on one word and only ever fired falsely.
    """
    sections: list[Section] = []
    blocks = [b.strip() for b in re.split(r"\n\s*\n", raw) if b.strip()]

    for i, block in enumerate(blocks):
        one_line = "\n" not in block
        words = block.split()
        is_chapter = one_line and len(words) <= 3 and not re.search(r"[.!?]$", block)

        body = spell_numerals(block)
        sec = Section(title=block if is_chapter else f"Section {i+1}",
                      text=body, is_chapter=is_chapter, index=i)
        pieces = [body] if is_chapter else chunk_text(body, max_chars)
        sec.chunks = [Chunk(text=p, index=j) for j, p in enumerate(pieces)]
        sections.append(sec)

    return sections
