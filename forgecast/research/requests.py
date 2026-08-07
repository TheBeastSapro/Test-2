"""What the audience asked for, read out of a channel's own comments.

Measured, not assumed. The reference this was built against ends every video with "tell
me in the comments which creature or horror topic you want to see in the next video",
its comments answer that question by name, and two of the names they answer with are
already published videos. The comment section is that channel's topic backlog, and it is
the cheapest research any of these channels does.

Nothing in this app read comment text. `research/outliers.py` reads comment *counts*, to
compute an engagement ratio, and that is all.

## Why this is counting rather than a model

A request is a short, repetitive, high-signal string — "do SCP next", "can you do the
Bolid One", "PLEASE do sirenhead" — and what matters is not any one of them but which
name recurs across hundreds. That is a tally, and a tally is cheap, deterministic, and
auditable in a way a summary is not. A model asked to "find the requests" returns a
plausible list nobody can check; this returns names with counts and the comments they
came from.

## What it deliberately does not do

It does not rank topics or decide what to make. It reports what was asked for and how
often, and the choice stays with whoever is making the video — a request appearing four
hundred times is a strong signal and still not an instruction.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

#: Phrasings that introduce a request. Deliberately narrow: these are the forms that
#: actually appear, and a looser pattern turns every mention of a creature into a demand.
ASKS = (
    r"(?:can|could|will|would)\s+(?:you|u)\s+(?:please\s+)?(?:do|make|cover|explain)",
    r"(?:please|pls|plz)\s+(?:do|make|cover|explain)",
    r"(?:do|make|cover|explain)\s+(?:a\s+)?(?:video\s+(?:on|about)\s+)?",
    r"i\s+(?:want|wanna|would like)\s+to\s+see",
    r"(?:next\s+video|next\s+time|part\s+\d+)\s*[:,]?\s*",
    r"you\s+should\s+(?:do|make|cover|explain)",
    # "An explanation of the biggest SCPs would be awesome" — the noun form, which is
    # how a politer request is phrased and which the verb patterns above all miss.
    r"(?:an?\s+)?(?:explanation|video|episode)\s+(?:of|on|about)",
)
_ASK = re.compile(r"(?:" + "|".join(ASKS) + r")\s+(?P<subject>[^.!?\n]{3,60})", re.I)

#: Words that are never the subject of a request, stripped from either end of a match.
#:
#: This list is what makes the tally work at all. "Please make us see the Anchorage on
#: your next video" and "can you do the anchorage next pls" are one request, and with a
#: shorter list they came out as "see the anchorage on your next" and "anchorage" —
#: two entries of one each, which is below the threshold, so the most-asked-for thing on
#: the video reported as nothing.
FILLER = ("the", "a", "an", "some", "more", "about", "on", "of", "us", "me", "one",
          "next", "video", "vid", "episode", "please", "pls", "plz", "see", "do",
          "make", "cover", "explain", "explaining", "your", "you", "in", "for",
          "would", "be", "awesome", "too", "again", "time", "part", "pleaseee")

#: Below this a "request" is one person, which is noise rather than a signal.
MIN_MENTIONS = 2

#: Subjects longer than this are sentences that happened to follow a request phrase.
MAX_SUBJECT_WORDS = 4


@dataclass
class Request:
    """One thing the audience asked for, and how often."""

    subject: str
    mentions: int
    likes: int = 0
    examples: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"subject": self.subject, "mentions": self.mentions,
                "likes": self.likes, "examples": list(self.examples[:3])}


@dataclass
class Backlog:
    """Everything asked for on one video, most-asked first."""

    requests: list[Request] = field(default_factory=list)
    comments_read: int = 0
    with_a_request: int = 0

    def as_dict(self) -> dict:
        return {"comments_read": self.comments_read,
                "with_a_request": self.with_a_request,
                "requests": [item.as_dict() for item in self.requests]}

    def as_text(self) -> str:
        if not self.requests:
            return (f"{self.comments_read} comments read, nothing asked for more than "
                    f"once.")
        lines = [f"{len(self.requests)} thing(s) asked for across "
                 f"{self.comments_read} comments ({self.with_a_request} contained a "
                 f"request):"]
        for item in self.requests:
            likes = f", {item.likes} likes" if item.likes else ""
            lines.append(f"  {item.mentions}x{likes}  {item.subject}")
            if item.examples:
                lines.append(f"      “{item.examples[0][:90]}”")
        return "\n".join(lines)


def _clean(subject: str) -> str:
    """A request's subject, reduced so two spellings of it tally together."""
    words = re.sub(r"[^\w\s'-]", " ", subject).split()
    while words and words[0].lower() in FILLER:
        words.pop(0)
    while words and words[-1].lower() in FILLER:
        words.pop()
    # Trimmed to the head of the phrase, not the tail. A request names its subject first
    # and then trails off — "the Anchorage on your next video" — so keeping the front is
    # what makes two phrasings of one request meet.
    return " ".join(words[:MAX_SUBJECT_WORDS]).strip().lower()


def read(comments: list) -> Backlog:
    """Tally what a video's comments asked for.

    `comments` is whatever the caller has — dicts with `textDisplay`/`text` and
    `likesCount`/`likes`, or plain strings. Taken loosely because the two sources that
    can supply them (an MCP tool and yt-dlp's dump) name their fields differently, and a
    reader that only understood one of them would be a reader with one caller.
    """
    tally: Counter = Counter()
    likes: Counter = Counter()
    examples: dict[str, list[str]] = {}
    read_count = 0
    hit_count = 0

    for row in comments or []:
        if isinstance(row, str):
            text, like_count = row, 0
        elif isinstance(row, dict):
            text = str(row.get("textDisplay") or row.get("text") or "")
            raw = str(row.get("likesCount") or row.get("likes") or "0").strip()
            like_count = int(raw) if raw.isdigit() else 0
        else:
            continue
        if not text.strip():
            continue
        read_count += 1

        found = False
        for match in _ASK.finditer(text):
            subject = _clean(match.group("subject"))
            if len(subject) < 3:
                continue
            found = True
            tally[subject] += 1
            likes[subject] += like_count
            examples.setdefault(subject, []).append(" ".join(text.split()))
        if found:
            hit_count += 1

    requests = [
        Request(subject=subject, mentions=count, likes=likes[subject],
                examples=examples.get(subject, []))
        for subject, count in tally.most_common()
        if count >= MIN_MENTIONS
    ]
    return Backlog(requests=requests, comments_read=read_count,
                   with_a_request=hit_count)
