"""What gives a script away as machine-written, measured on the finished text.

`method.py` already bans nine constructions and puts them in the prompt. That is a
request, and this file exists because a request is not a check. This codebase's own
notes say it twice: an instruction the model may treat as context is one it drops the
moment the output gets long, and a script is exactly the output that gets long. Nothing
looked at what came back.

So this reads the finished script and reports what is in it. It does not rewrite —
a checker that silently fixes its own findings is a checker nobody can audit, and the
whole point is that a person or a revision pass sees the list.

## What is measured, and why these

Everything here is countable. "Feels like AI" is not a check; a specific phrase at a
specific offset is. Two kinds:

**Named constructions.** The nine already in `method.BANNED`, matched on the finished
text rather than hoped for in the prompt. These are the cheapest and most certain.

**Statistical tells.** The ones that survive a phrase ban, because they are habits
rather than words:

* *Uniform sentence length.* Human narration varies — a nine-word sentence lands after
  a twenty-six-word one, and that variation is most of what reads as a voice. Machine
  prose regresses to a mean and stays there. Measured as the spread of sentence lengths
  against their average, so it holds whatever the average is.
* *Tricolon habit.* Three-item lists are good and four in a row is a tic. Counted per
  hundred words rather than absolutely, because a long script is allowed more of them.
* *"Not just X, but Y".* The single most recognisable machine cadence in current use.
* *Hedging density.* "Perhaps", "arguably", "some would say" — each is fine and a pile
  of them is a narrator with no position, which is the specific thing a documentary
  cannot afford.
* *Em-dash density.* An em-dash is a good mark and its overuse is a fingerprint.

Every threshold below is a judgement rather than a measurement, and each says so. They
are set where a human editor would start noticing, not where a test goes green.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .method import BANNED

#: Sentences shorter than this are fragments — a stinger, a one-word beat — and counting
#: them in the rhythm statistic would report every punchy script as uniform.
MIN_SENTENCE_WORDS = 4

#: Coefficient of variation of sentence length below which prose reads as metronomic.
#: Human narration measured across the reference material sits well above this; machine
#: prose without an explicit instruction to vary lands under it. A judgement.
RHYTHM_FLOOR = 0.42

#: Per hundred words, above which a habit is visible rather than incidental. Judgements,
#: all three, set where an editor starts noticing rather than where a test passes.
TRICOLON_PER_100 = 1.2
HEDGE_PER_100 = 2.0
DASH_PER_100 = 2.5

#: Words that soften a claim. Individually fine; in quantity they are a narrator with no
#: position, which is the one thing an explainer cannot afford.
HEDGES = (
    "perhaps", "arguably", "possibly", "potentially", "seemingly", "somewhat",
    "relatively", "fairly", "rather", "quite possibly", "some would say",
    "it could be argued", "many believe", "it seems", "in a sense", "to some extent",
)

#: The cadence, as a pattern rather than a phrase, so its variants are caught too.
NOT_JUST = re.compile(
    r"\bnot (?:just|only|merely|simply)\b[^.?!]{0,80}?\b(?:but|it'?s|its|they'?re)\b",
    re.I)

#: Three items joined by commas and a final conjunction.
TRICOLON = re.compile(
    r"\b[\w'-]+(?:\s+[\w'-]+){0,3},\s+[\w'-]+(?:\s+[\w'-]+){0,3},\s+(?:and|or)\s+",
    re.I)

#: Sentence boundaries, ignoring the full stops that are not ones.
#:
#: The naive `[^.!?]+[.!?]*` splits "$2.4 million" into "$2" and ".4 million" — which
#: made every decimal in a script two sentences, wrecked the rhythm statistic on any
#: script containing money or measurements, and hid the figure itself from the
#: grounding check, because "$2" is a trivial number and ".4" no longer parsed as one.
#: Found by a figure that should have been flagged and silently was not.
#:
#: So: a full stop between two digits is consumed as ordinary text rather than treated
#: as a boundary. Deliberately only that case — abbreviations would need a word list to
#: keep current, and this is a splitter for narration, not a parser for prose in general.
#: Two details that each cost a wrong attempt. Python's lookbehind must be fixed width,
#: so the digit before the point is matched rather than looked behind at. And the decimal
#: branch has to come FIRST: alternation is ordered, so with `[^.!?]` leading it the digit
#: is consumed before the decimal branch is ever tried, leaving the cursor on the point
#: with nothing left to match — a fix that reads correctly and changes nothing.
_SENTENCE = re.compile(r"(?:\d\.(?=\d)|[^.!?])+[.!?]*")


@dataclass
class Tell:
    """One finding. `where` is a character offset, or -1 for a whole-text measurement."""

    kind: str
    detail: str
    where: int = -1
    quote: str = ""
    #: What to do instead. Never empty for a named construction: a ban with nothing on
    #: the other side of it gets obeyed twice and then dropped, because the writer still
    #: has to put something in the slot.
    instead: str = ""

    def as_dict(self) -> dict:
        return {"kind": self.kind, "detail": self.detail, "where": self.where,
                "quote": self.quote, "instead": self.instead}


@dataclass
class Report:
    """Everything found, and the numbers behind it."""

    tells: list[Tell] = field(default_factory=list)
    words: int = 0
    sentences: int = 0
    rhythm: float = 0.0

    @property
    def clean(self) -> bool:
        return not self.tells

    def as_dict(self) -> dict:
        return {"clean": self.clean, "words": self.words, "sentences": self.sentences,
                "rhythm": round(self.rhythm, 3),
                "tells": [tell.as_dict() for tell in self.tells]}

    def as_text(self) -> str:
        if self.clean:
            return (f"{self.words} words, {self.sentences} sentences, rhythm "
                    f"{self.rhythm:.2f} — nothing flagged.")
        lines = [f"{len(self.tells)} thing(s) to look at in {self.words} words:"]
        for tell in self.tells:
            where = f" at {tell.where}" if tell.where >= 0 else ""
            lines.append(f"  {tell.kind}{where}: {tell.detail}")
            if tell.quote:
                lines.append(f"    “{tell.quote}”")
            if tell.instead:
                lines.append(f"    instead: {tell.instead}")
        return "\n".join(lines)


def sentences(text: str) -> list[str]:
    return [found.strip() for found in _SENTENCE.findall(text or "") if found.strip()]


def rhythm(text: str) -> float:
    """Spread of sentence length against its own mean.

    A coefficient of variation rather than a standard deviation, so the number means the
    same thing for a script of nine-word sentences and one of twenty-five-word
    sentences — the question is whether the lengths vary, not how long they are.
    """
    lengths = [len(item.split()) for item in sentences(text)]
    lengths = [count for count in lengths if count >= MIN_SENTENCE_WORDS]
    if len(lengths) < 4:
        return 1.0                      # too little to judge; do not flag on noise
    mean = sum(lengths) / len(lengths)
    if mean <= 0:
        return 1.0
    variance = sum((count - mean) ** 2 for count in lengths) / len(lengths)
    return (variance ** 0.5) / mean


def _as_pattern(phrase: str) -> str:
    """A banned phrase as a regex, honouring its `X` placeholder.

    `method.BANNED` writes its entries the way a person reads them — "In the world of X",
    "When it comes to X" — where X is whatever the topic happens to be. Matched
    literally, those entries could only ever fire on a script that contained the letter
    X, so the most common opener on the list was unenforceable. Escaped everywhere else,
    because these are phrases and not patterns.
    """
    parts = [re.escape(part) for part in re.split(r"\bX\b", phrase)]
    # A word or two stands in for the placeholder — long enough for "the deep sea",
    # short enough that it cannot swallow a clause and match across a full stop.
    return r"[\w'’-]+(?:\s+[\w'’-]+){0,2}".join(parts) if len(parts) > 1 else parts[0]


def _quote(text: str, at: int, width: int = 64) -> str:
    start = max(0, at - 8)
    return " ".join(text[start:start + width].split())


def check(text: str) -> Report:
    """Read a finished script and say what is in it."""
    body = str(text or "")
    words = len(body.split())
    found: list[Tell] = []

    # The nine named constructions, matched on what came back rather than requested in
    # the prompt. Each carries its own replacement from `method.BANNED`.
    for banned in BANNED:
        for phrase in re.findall(r'"([^"]+)"', banned.construction):
            for match in re.finditer(_as_pattern(phrase), body, re.I):
                found.append(Tell(
                    kind="banned phrase",
                    detail=f"{phrase!r} is on the banned list",
                    where=match.start(), quote=_quote(body, match.start()),
                    instead=banned.instead,
                ))

    for match in NOT_JUST.finditer(body):
        found.append(Tell(
            kind="machine cadence",
            detail="\"not just X, but Y\" — the most recognisable current tell",
            where=match.start(), quote=_quote(body, match.start()),
            instead="State the second thing on its own. The contrast is doing no work.",
        ))

    per_100 = max(1.0, words / 100)

    tricolons = list(TRICOLON.finditer(body))
    if len(tricolons) / per_100 > TRICOLON_PER_100:
        found.append(Tell(
            kind="rhythm habit",
            detail=f"{len(tricolons)} three-item lists in {words} words "
                   f"({len(tricolons) / per_100:.1f} per 100). Three is a good number "
                   f"and four in a row is a tic.",
            quote=_quote(body, tricolons[0].start()) if tricolons else "",
            instead="Break some into two items, or into a sentence that names one.",
        ))

    hedges = [match for word in HEDGES
              for match in re.finditer(rf"\b{re.escape(word)}\b", body, re.I)]
    if len(hedges) / per_100 > HEDGE_PER_100:
        found.append(Tell(
            kind="hedging",
            detail=f"{len(hedges)} hedges in {words} words "
                   f"({len(hedges) / per_100:.1f} per 100) — a narrator with no position",
            quote=_quote(body, hedges[0].start()) if hedges else "",
            instead="Say the thing, or say plainly that it is not known. Both are "
                    "positions; a pile of maybes is neither.",
        ))

    dashes = body.count("—") + body.count(" -- ")
    if dashes / per_100 > DASH_PER_100:
        found.append(Tell(
            kind="punctuation habit",
            detail=f"{dashes} em-dashes in {words} words ({dashes / per_100:.1f} per "
                   f"100). A good mark, and its overuse is a fingerprint.",
            instead="Full stops for most of them. An em-dash should be the one "
                    "interruption in a paragraph, not its joinery.",
        ))

    spread = rhythm(body)
    if spread < RHYTHM_FLOOR and len(sentences(body)) >= 6:
        found.append(Tell(
            kind="metronomic",
            detail=f"sentence length varies by {spread:.0%} of its mean — under "
                   f"{RHYTHM_FLOOR:.0%} reads as machine-even",
            instead="Put a short sentence after a long one. That variation is most of "
                    "what a voice is.",
        ))

    return Report(tells=found, words=words, sentences=len(sentences(body)),
                  rhythm=spread)
