"""Which of the script's hard claims the research actually supports.

`research` verifies claims against fetched sources and hands the writer a list. Nothing
then checked whether the script *used* it. The writer is asked to ground its assertions
and is not audited, which is the same shape as the banned constructions in `tells.py`:
an instruction in a prompt is a request, and the output nobody reads is where requests
go to be quietly dropped.

This matters more than a style tell. `research_node` already logs the case it fears —
"no verifiable claims found — the script will be written without factual assertions
rather than with invented ones" — and that log is a hope. A model asked for a
documentary will supply numbers, because the genre expects them, and a fabricated
citation looks exactly like a real one.

## What is checked, and what deliberately is not

Only the assertions that can be wrong in a way a viewer can catch: figures, dates,
percentages, and superlatives. "The cable is four thousand kilometres long" is checkable
against the research. "The sea is dark down there" is not, and pretending to check it
would bury the findings that matter in noise.

Matching is deliberately generous — a number appearing anywhere in the research, in any
formatting, counts as support. This is a *floor*, not a proof. It catches the number
that appeared from nowhere, which is the failure worth catching, and it will pass a
number that is real but attached to the wrong subject. That limit is stated rather than
papered over: a check that claimed more than it does would be worse than none, because
somebody would trust it.

## Why it reports rather than blocks

The same reason `tells.py` does not rewrite. Ungrounded is not the same as false — a
script may legitimately say something the research did not reach, and only a person
knows which. The finding goes on the gate where somebody is already deciding whether the
script is worth voicing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Superlatives worth flagging when nothing sourced them. Each is a claim about a
#: maximum, which is the kind of statement a documentary is judged on and the kind a
#: model reaches for to sound authoritative.
SUPERLATIVES = (
    "largest", "biggest", "smallest", "longest", "deepest", "tallest", "fastest",
    "oldest", "first", "only", "most", "worst", "never", "always", "every",
)

#: A figure, with its unit if it has one. Written to catch "4,000 km", "23 m", "1.9
#: million", "40%" and "$246,000" as single tokens rather than as bare digits.
NUMBER = re.compile(
    r"(?<![\w.])(?:[$£€]\s?)?\d[\d,]*(?:\.\d+)?\s*"
    r"(?:%|percent|million|billion|thousand|km|m|kg|lbs?|ft|feet|metres|meters|"
    r"miles|years?|days?|hours?|minutes?|seconds?)?",
    re.I)

#: A year on its own. Separated from `NUMBER` because a date is checkable in a different
#: way and reads differently in a finding.
YEAR = re.compile(r"(?<!\d)(1[89]\d{2}|20\d{2})(?!\d)")

#: Numbers too small or too common to be a claim. "one of the", "two things", "3am" —
#: flagging these produces a wall of findings nobody reads, and a check nobody reads is
#: a check that does not exist.
TRIVIAL = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "100"}

# One splitter, shared. A decimal point is not a sentence end, and having two
# copies of that rule is how one of them goes stale.
from .tells import _SENTENCE


@dataclass
class Ungrounded:
    """One assertion the research does not support."""

    kind: str                       # figure | year | superlative
    token: str
    sentence: str
    where: int = -1

    def as_dict(self) -> dict:
        return {"kind": self.kind, "token": self.token, "sentence": self.sentence,
                "where": self.where}


@dataclass
class Grounding:
    """How much of the script's checkable content the research stands behind."""

    checked: int = 0
    supported: int = 0
    findings: list[Ungrounded] = field(default_factory=list)
    claims_available: int = 0

    @property
    def share(self) -> float:
        """Supported over checked. 1.0 when there was nothing to check."""
        return 1.0 if not self.checked else self.supported / self.checked

    @property
    def clean(self) -> bool:
        return not self.findings

    def as_dict(self) -> dict:
        return {"checked": self.checked, "supported": self.supported,
                "share": round(self.share, 3), "clean": self.clean,
                "claims_available": self.claims_available,
                "findings": [item.as_dict() for item in self.findings]}

    def as_text(self) -> str:
        if not self.checked:
            return "No checkable figures or dates in the script."
        head = (f"{self.supported} of {self.checked} checkable assertions are in the "
                f"research ({self.share:.0%}), from {self.claims_available} verified "
                f"claim(s).")
        if self.clean:
            return head
        lines = [head]
        for item in self.findings:
            lines.append(f"  {item.kind} {item.token!r} is not in the research")
            lines.append(f"    “{item.sentence}”")
        return "\n".join(lines)


def _digits(text: str) -> set[str]:
    """Every run of digits in a text, so 4,000 and 4000 compare equal."""
    found = set()
    for run in re.findall(r"\d[\d,.]*", text or ""):
        cleaned = run.replace(",", "").rstrip(".")
        if cleaned:
            found.add(cleaned)
    return found


def check(script: str, claims: list | None = None) -> Grounding:
    """Which of the script's figures, dates and superlatives the research supports.

    `claims` is what `research` produced — dicts with `text` and `quote`, or objects
    carrying the same. Taken loosely so this can run against a stored run as easily as
    against a live one.
    """
    body = str(script or "")
    rows = list(claims or [])

    corpus_parts: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            corpus_parts += [str(row.get("text", "")), str(row.get("quote", "")),
                             str(row.get("note", ""))]
        else:
            corpus_parts += [str(getattr(row, "text", "")),
                             str(getattr(row, "quote", "")),
                             str(getattr(row, "note", ""))]
    corpus = " ".join(corpus_parts)
    corpus_digits = _digits(corpus)
    corpus_lower = corpus.lower()

    grounding = Grounding(claims_available=len(rows))

    for match in _SENTENCE.finditer(body):
        sentence = match.group().strip()
        if not sentence:
            continue
        at = match.start()

        seen: set[str] = set()
        for finding in NUMBER.finditer(sentence):
            token = finding.group().strip()
            bare = re.sub(r"[^\d]", "", token)
            if not bare or bare in TRIVIAL or token in seen:
                continue
            seen.add(token)
            grounding.checked += 1
            if bare.lstrip("0") in {d.lstrip("0") for d in corpus_digits}:
                grounding.supported += 1
            else:
                grounding.findings.append(Ungrounded(
                    kind="figure", token=token, sentence=_trim(sentence),
                    where=at + finding.start()))

        for finding in YEAR.finditer(sentence):
            token = finding.group()
            if token in seen:
                continue
            seen.add(token)
            grounding.checked += 1
            if token in corpus_digits:
                grounding.supported += 1
            else:
                grounding.findings.append(Ungrounded(
                    kind="year", token=token, sentence=_trim(sentence),
                    where=at + finding.start()))

        lowered = sentence.lower()
        for word in SUPERLATIVES:
            if not re.search(rf"\b{word}\b", lowered):
                continue
            grounding.checked += 1
            if word in corpus_lower:
                grounding.supported += 1
            else:
                grounding.findings.append(Ungrounded(
                    kind="superlative", token=word, sentence=_trim(sentence), where=at))
            break        # one per sentence; a stack of them is one claim, not four

    return grounding


def _trim(sentence: str, limit: int = 160) -> str:
    flat = " ".join(sentence.split())
    return flat if len(flat) <= limit else flat[:limit].rsplit(" ", 1)[0] + "…"
