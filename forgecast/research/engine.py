"""The research loop: plan, search, fetch, extract, verify.

Verification is the load-bearing step and it is deliberately dumb. The extractor is
asked to return a supporting quote copied verbatim from the page, and we then check
that the quote really appears in the page text. A model cannot argue its way past a
substring match, which is exactly the property you want guarding factual claims.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from ..providers.search import FetchedPage, SearchProvider, fetch
from .brief import Claim, ResearchBrief, Source

log = logging.getLogger("forgecast.research")

MAX_QUERIES = 5
RESULTS_PER_QUERY = 6
MAX_PAGES = 8
MAX_PAGE_CHARS = 12_000
FETCH_CONCURRENCY = 4
# Quotes are matched after whitespace/case normalisation; models reflow whitespace
# even when instructed to copy exactly, and failing them for that would reject
# perfectly good claims.
MIN_QUOTE_CHARS = 25

QUERY_INSTRUCTIONS = """Plan web searches that would establish the facts a video on
this topic needs.

Return JSON: {"queries": [...], "open_questions": [...]}

  queries         3-5 search strings. Make them specific and varied — a definition
                  query, a numbers/statistics query, a recent-developments query, and
                  a skeptical or counter-argument query. Do not repeat the topic
                  verbatim five times with synonyms.
  open_questions  what a viewer would want answered that search may not settle."""

EXTRACT_INSTRUCTIONS = """Extract only factual claims that this page actually supports.

Return JSON: {"claims": [{"text", "quote", "kind", "confidence"}]}

  text        the claim in one plain sentence, self-contained.
  quote       a span copied VERBATIM from the page text that supports the claim. It
              will be checked against the page automatically; a claim whose quote is
              not found is discarded, so do not paraphrase, summarise, or stitch
              together separate sentences.
  kind        fact | statistic | quote | definition | context
  confidence  high | medium | low

Extract at most 6 claims. Prefer specific, checkable statements — numbers, dates,
named entities, mechanisms — over generalities. If the page supports nothing
checkable, return an empty list. An empty list is a correct and useful answer."""


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


# A digit run plus up to three following words, so the unit attached to a figure can
# be read off it: "300 nautical miles", "8 knots", "91 m)".
_FIGURE_RE = re.compile(r"(\d[\d,.]*)((?:\s+[A-Za-z%°]+){0,3})")

# Units worth policing, mapped to a canonical form so "m", "metre" and "meters" are
# one unit and "mi" and "miles" are another. Deliberately a closed list: an open-ended
# "the word after the number" rule rejects good claims constantly, because most words
# after a number are ordinary nouns the quote had no reason to repeat.
_UNITS: dict[str, str] = {
    "mile": "mile", "miles": "mile", "mi": "mile",
    "nautical": "nautical_mile", "nm": "nautical_mile",
    "foot": "foot", "feet": "foot", "ft": "foot",
    "inch": "inch", "inches": "inch", "in": "inch",
    "metre": "metre", "metres": "metre", "meter": "metre", "meters": "metre", "m": "metre",
    "kilometre": "km", "kilometres": "km", "kilometer": "km", "kilometers": "km", "km": "km",
    "yard": "yard", "yards": "yard",
    "knot": "knot", "knots": "knot",
    "second": "second", "seconds": "second", "s": "second",
    "minute": "minute", "minutes": "minute", "min": "minute",
    "hour": "hour", "hours": "hour", "hr": "hour", "hrs": "hour",
    "day": "day", "days": "day",
    "week": "week", "weeks": "week",
    "month": "month", "months": "month",
    "year": "year", "years": "year", "yr": "year",
    "percent": "percent", "%": "percent", "pc": "percent",
    "tonne": "tonne", "tonnes": "tonne", "ton": "ton", "tons": "ton",
    "kilogram": "kg", "kilograms": "kg", "kg": "kg",
    "pound": "pound", "pounds": "pound", "lb": "pound", "lbs": "pound",
    "volt": "volt", "volts": "volt", "v": "volt",
    "watt": "watt", "watts": "watt", "w": "watt",
    "gigabit": "gbps", "gbps": "gbps", "terabit": "tbps", "tbps": "tbps",
    "celsius": "celsius", "c": "celsius", "fahrenheit": "fahrenheit", "f": "fahrenheit",
}

# Spelled-out small numbers carry no distortion risk and appear constantly in prose.
_NUMBER_WORDS = frozenset(
    ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
     "ten", "eleven", "twelve"]
)


def _figures(text: str) -> list[tuple[str, str]]:
    """(number, canonical unit) pairs. Unit is "" when none was attached."""
    out: list[tuple[str, str]] = []
    for number, trailing in _FIGURE_RE.findall(text or ""):
        cleaned = number.rstrip(".,").replace(",", "")
        if not cleaned:
            continue
        unit = ""
        for word in trailing.split():
            token = word.strip("().,;:").lower()
            if token in _UNITS:
                unit = _UNITS[token]
                break
        out.append((cleaned, unit))
    return out


def _is_year(number: str) -> bool:
    """Years are context the page establishes, not figures lifted from one sentence."""
    return len(number) == 4 and number.isdigit() and 1400 <= int(number) <= 2100


def _unsupported_numbers(claim: str, quote: str) -> list[str]:
    """Figures the claim asserts that its own supporting quote does not support.

    A verified quote proves the quote is real. It does not prove the claim reports it
    faithfully, and the gap between those two is where the damage happens. A live run
    produced this pair:

        claim  "300 nautical miles of cable was lost"
        quote  "300 feet (91 m) of cable was lost over a region known as ..."

    The quote matched the page exactly, so the citation check passed, and the video
    would have stated a distance roughly 2,000 times too large with a real source
    hanging off it. Note what a digits-only comparison does here: 300 appears in both,
    so it passes. The unit is the thing that changed, which is why this checks the
    unit attached to each figure and not just the figure.

    Two ways to fail, then: a number the quote does not contain at all, or a number
    whose unit the quote contradicts. Both are mechanical. Comparing the rest of the
    prose would need a model, and a model judging another model's faithfulness is not
    a check — it is a second opinion with the same failure mode.
    """
    in_quote = _figures(quote)
    quote_numbers = {number for number, _ in in_quote}
    quote_units: dict[str, set[str]] = {}
    for number, unit in in_quote:
        quote_units.setdefault(number, set()).add(unit)
    quote_all_units = {unit for _, unit in in_quote if unit}

    problems: list[str] = []
    for number, unit in _figures(claim):
        if number.lower() in _NUMBER_WORDS or _is_year(number):
            continue
        if number not in quote_numbers:
            problems.append(number if not unit else f"{number} {unit}")
            continue
        # The figure is there but wearing a different unit. Only flagged when the quote
        # attaches units somewhere: a quote giving a bare number and leaving the unit to
        # the surrounding sentence is ordinary writing, not a distortion.
        if (
            unit
            and unit not in quote_units.get(number, set())
            and quote_all_units
            and unit not in quote_all_units
        ):
            problems.append(f"{number} {unit}")
    return sorted(set(problems))


async def research_topic(
    topic: str,
    *,
    llm,
    search: SearchProvider,
    angle: str = "",
    max_queries: int = MAX_QUERIES,
    max_pages: int = MAX_PAGES,
) -> ResearchBrief:
    brief = ResearchBrief(topic=topic, provider=search.name)
    credits = 0

    # 1 — plan
    payload = json.dumps({"topic": topic, "angle": angle}, ensure_ascii=False)
    plan_result = await llm.complete(
        f"{QUERY_INSTRUCTIONS}\n\nINPUT:\n{payload}",
        system="You plan research for a factual video. Precise queries beat broad ones.",
        json_object=True,
        schema_name="research_queries",
        max_tokens=1200,
        temperature=0.4,
    )
    credits += plan_result.credits
    plan = _safe_json(plan_result.text)
    queries = [str(item) for item in (plan.get("queries") or []) if str(item).strip()]
    brief.queries = queries[:max_queries] or [topic]
    brief.open_questions = [str(item) for item in (plan.get("open_questions") or [])][:10]
    log.info("planned %d queries for %r", len(brief.queries), topic)

    # 2 — search
    seen: set[str] = set()
    ordered: list = []
    for query in brief.queries:
        try:
            results = await search.search(query, limit=RESULTS_PER_QUERY)
        except Exception as exc:
            log.warning("search failed for %r: %s", query, exc)
            continue
        for result in results:
            if result.url in seen:
                continue
            seen.add(result.url)
            ordered.append(result)

    if not ordered:
        brief.note = "no search results returned; the brief has no sources"
        brief.credits = credits
        return brief

    # 3 — fetch, bounded
    targets = ordered[:max_pages]
    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)

    async def _guarded(url: str) -> FetchedPage:
        async with semaphore:
            return await fetch(url)

    pages = await asyncio.gather(*(_guarded(item.url) for item in targets))

    for result, page in zip(targets, pages, strict=True):
        brief.sources.append(
            Source(
                url=result.url, domain=result.domain, title=page.title or result.title,
                fetched=page.usable, characters=len(page.text), error=page.error,
            )
        )

    usable = [page for page in pages if page.usable]
    log.info("fetched %d/%d pages usefully", len(usable), len(pages))
    if not usable:
        brief.note = (
            "search returned results but no page could be fetched and extracted; "
            "claims are empty rather than guessed"
        )
        brief.credits = credits
        return brief

    # 4 — extract and verify per page
    for page in usable:
        extract_payload = json.dumps(
            {
                "topic": topic,
                "url": page.url,
                "title": page.title,
                "page_text": page.text[:MAX_PAGE_CHARS],
            },
            ensure_ascii=False,
        )
        try:
            result = await llm.complete(
                f"{EXTRACT_INSTRUCTIONS}\n\nINPUT:\n{extract_payload}",
                system="You extract only what the given page supports. You never add "
                       "outside knowledge.",
                json_object=True,
                schema_name="research_claims",
                max_tokens=2000,
                temperature=0.1,
            )
        except Exception as exc:
            log.warning("extraction failed for %s: %s", page.url, exc)
            continue
        credits += result.credits

        haystack = _normalise(page.text)
        for entry in _safe_json(result.text).get("claims") or []:
            if not isinstance(entry, dict):
                continue
            text = str(entry.get("text") or "").strip()
            quote = str(entry.get("quote") or "").strip()
            if not text:
                continue

            reason = None
            if len(quote) < MIN_QUOTE_CHARS:
                reason = f"supporting quote too short ({len(quote)} chars)"
            elif _normalise(quote) not in haystack:
                reason = "supporting quote does not appear in the fetched page text"
            else:
                invented = _unsupported_numbers(text, quote)
                if invented:
                    reason = (
                        "the claim states numbers its own quote does not: "
                        + ", ".join(invented)
                    )

            if reason:
                brief.rejected_claims.append(
                    {"text": text, "source_url": page.url, "quote": quote,
                     "reason": reason}
                )
                continue

            brief.claims.append(
                Claim(
                    text=text,
                    source_url=page.url,
                    quote=quote,
                    verified=True,
                    kind=str(entry.get("kind") or "fact"),
                    confidence=str(entry.get("confidence") or "medium"),
                )
            )

    brief.credits = credits
    verified = len(brief.verified_claims)
    rejected = len(brief.rejected_claims)
    brief.note = (
        f"{verified} claims verified against source text, {rejected} rejected for "
        "unmatched or missing quotes"
    )
    log.info("research complete: %s", brief.note)
    return brief


def _safe_json(text: str) -> dict:
    from ..providers.llm import extract_json

    try:
        return extract_json(text)
    except Exception:
        log.warning("could not parse model JSON; continuing with empty result")
        return {}
