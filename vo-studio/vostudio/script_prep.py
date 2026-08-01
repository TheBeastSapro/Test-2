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


def spell_number(n: int) -> str:
    """Years read as years: 1798 -> 'seventeen ninety-eight', not 'one thousand...'."""
    if 1100 <= n <= 1999 and n % 100 != 0:
        return f"{_under_1000(n // 100)} {_under_1000(n % 100)}"
    if n < 1000:
        return _under_1000(n)
    if n < 1_000_000:
        head = _under_1000(n // 1000) + " thousand"
        return head + (" " + _under_1000(n % 1000) if n % 1000 else "")
    head = _under_1000(n // 1_000_000) + " million"
    rest = n % 1_000_000
    return head + (" " + spell_number(rest) if rest else "")


def spell_numerals(text: str) -> str:
    return re.sub(r"\b\d[\d,]*\b",
                  lambda m: spell_number(int(m.group(0).replace(",", ""))), text)


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
                        for i in range(0, len(clause), max_chars):
                            out.append(clause[i:i + max_chars].strip())
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
