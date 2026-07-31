"""Research data model.

`Claim.verified` is the field that matters. It is set by a mechanical substring check
against the page text, not by a model's opinion, which is why it can be trusted as a
gate on what reaches the script.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

SCHEMA_VERSION = "1.0"

# Domains whose claims warrant less hedging. Deliberately short and boring — a long
# authority list encodes editorial judgement that belongs to the operator.
HIGH_TRUST_SUFFIXES = (".gov", ".edu", ".ac.uk", ".int")
HIGH_TRUST_DOMAINS = {
    "nature.com", "science.org", "nasa.gov", "who.int", "worldbank.org",
    "oecd.org", "imf.org", "reuters.com", "apnews.com", "bbc.co.uk",
}


@dataclass
class Source:
    url: str
    domain: str
    title: str
    fetched: bool = False
    characters: int = 0
    error: str | None = None

    @property
    def trust(self) -> str:
        """Coarse tier. Not a truth claim about the page — a hedging hint."""
        if self.domain in HIGH_TRUST_DOMAINS or self.domain.endswith(HIGH_TRUST_SUFFIXES):
            return "high"
        if self.domain.startswith("example") or "blogspot" in self.domain:
            return "low"
        return "medium"

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "domain": self.domain,
            "title": self.title,
            "fetched": self.fetched,
            "characters": self.characters,
            "trust": self.trust,
            "error": self.error,
        }


@dataclass
class Claim:
    text: str
    source_url: str
    quote: str
    verified: bool = False
    kind: str = "fact"              # fact | statistic | quote | definition | context
    confidence: str = "medium"
    note: str = ""

    @property
    def has_number(self) -> bool:
        return bool(re.search(r"\d", self.text))

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "source_url": self.source_url,
            "quote": self.quote,
            "verified": self.verified,
            "kind": self.kind,
            "confidence": self.confidence,
            "has_number": self.has_number,
            "note": self.note,
        }


@dataclass
class ResearchBrief:
    topic: str
    schema_version: str = SCHEMA_VERSION
    generated_at: str = ""
    queries: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    rejected_claims: list[dict] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    provider: str = ""
    credits: int = 0
    note: str = ""

    def __post_init__(self) -> None:
        if not self.generated_at:
            self.generated_at = datetime.now(UTC).isoformat()

    @property
    def verified_claims(self) -> list[Claim]:
        return [claim for claim in self.claims if claim.verified]

    @property
    def usable_sources(self) -> list[Source]:
        return [source for source in self.sources if source.fetched]

    def statistics(self) -> list[Claim]:
        """Numeric claims — the ones that most need a citation attached."""
        return [claim for claim in self.verified_claims if claim.has_number]

    def as_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "topic": self.topic,
            "generated_at": self.generated_at,
            "provider": self.provider,
            "queries": self.queries,
            "counts": {
                "sources": len(self.sources),
                "sources_fetched": len(self.usable_sources),
                "claims_verified": len(self.verified_claims),
                "claims_rejected": len(self.rejected_claims),
                "statistics": len(self.statistics()),
            },
            "sources": [source.as_dict() for source in self.sources],
            "claims": [claim.as_dict() for claim in self.verified_claims],
            "rejected_claims": self.rejected_claims,
            "open_questions": self.open_questions,
            "credits": self.credits,
            "note": self.note,
        }

    def prompt_block(self, *, limit: int = 30) -> str:
        """Render the brief for a script prompt.

        Claims arrive numbered with their source so the script can reference them, and
        the block states plainly that anything absent must not be asserted. Handing a
        model facts without that instruction invites it to pad them with invented ones.
        """
        if not self.verified_claims:
            return (
                "RESEARCH: no verifiable sources were found for this topic. Write "
                "without factual claims — no statistics, dates, quantities, or named "
                "studies. Say less rather than inventing support."
            )

        lines = [
            "RESEARCH — every factual statement in the script must trace to one of "
            "these numbered claims. If something is not here, do not assert it: "
            "rewrite the sentence so it does not need a source.",
            "",
        ]
        for index, claim in enumerate(self.verified_claims[:limit], start=1):
            trust = next(
                (source.trust for source in self.sources if source.url == claim.source_url),
                "unknown",
            )
            lines.append(f"[{index}] ({claim.kind}, {trust} trust) {claim.text}")
            lines.append(f"     source: {claim.source_url}")

        if self.open_questions:
            lines += [
                "",
                "UNRESOLVED — no source was found for these, so the script must not "
                "assert them:",
            ]
            lines += [f"  - {question}" for question in self.open_questions[:10]]

        return "\n".join(lines)
