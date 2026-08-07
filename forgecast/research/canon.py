"""The canon lane: entities fetched from a wiki, not invented from a prompt.

`fandom.py` reads one page. This is the lane that decides *which* pages, gathers them
for a run, and hands back something the shot planner and the script can both work from.

## Why a lane rather than a branch inside research

The ordinary research path answers "what is true about this topic" with cited claims
from the open web. A canon explainer asks a different question — "what does this
universe say this creature is" — and the answer is not on the open web, it is on one
wiki that the audience already reads. Those two produce different artifacts and are
worth keeping apart: a run has verified claims *and* it has entities, and conflating
them would put a creature's fictional height in the same list as a sourced fact about
the real world.

## Where the wiki name comes from, and why it is never invented

A wiki is a real subdomain and there is no rule that derives it from a topic. `Doors`
lives on `doors-game`, not `doors`, and `doors-roblox` is a redirect to it; `Siren
Head` lives on `trevorhenderson`. Guessing produces a 404 on a good day and somebody
else's abandoned wiki on a bad one.

So `discover` never constructs a subdomain. It reads them out of URLs a search engine
returned, and then *asks each candidate whether it exists* before offering it. What
comes back is a list to choose from, with the article count that makes the choice
obvious — the real wiki for a franchise has thousands of pages and the fan mirror has
nine.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field

import httpx

from . import fandom

log = logging.getLogger("forgecast.research.canon")

#: A fandom URL, with the subdomain as the capture. Matches the two shapes these appear
#: in — `https://doors-game.fandom.com/wiki/Seek` and the legacy `wikia.com` host, which
#: still turns up in search results and still redirects.
WIKI_HOST = re.compile(r"https?://([a-z0-9][a-z0-9-]*)\.(?:fandom|wikia)\.com/", re.I)

#: Subdomains that are fandom's own infrastructure rather than a wiki about anything.
#: They rank well for any query and would otherwise be offered as candidates.
NOT_A_WIKI = {"community", "www", "auth", "images", "static", "services", "design",
              "support", "help", "createnewwiki", "about", "starter", "meta", "d"}

#: Below this an entity has too little on its page to carry a minute of narration. Not a
#: hard floor on quality — a short page can be a good segment — but a page under this is
#: a stub, and a stub read as a segment is thirty seconds of the same sentence rephrased.
MIN_BEAT_CHARS = 220

#: How many wikis to verify at once. These are somebody else's servers and the whole
#: point is to be a good citizen of them.
PROBE_CONCURRENCY = 4


@dataclass
class Wiki:
    """A candidate wiki, verified to exist."""

    name: str
    title: str = ""
    url: str = ""
    articles: int = 0
    language: str = ""

    def as_dict(self) -> dict:
        return {"name": self.name, "title": self.title, "url": self.url,
                "articles": self.articles, "language": self.language}


@dataclass
class Gathered:
    """What the lane found for one run."""

    wiki: str
    entities: list[dict] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def usable(self) -> list[dict]:
        return [entity for entity in self.entities if entity.get("usable")]

    def as_dict(self) -> dict:
        return {"wiki": self.wiki, "entities": list(self.entities),
                "missing": list(self.missing), "notes": list(self.notes),
                "counts": {"asked": len(self.entities) + len(self.missing),
                           "found": len(self.entities), "usable": len(self.usable)}}

    def attribution(self) -> list[str]:
        """One credit line per entity, for the run's attribution file.

        Written for every entity including the ones whose licence came back empty,
        because "not stated" is the state a human needs to see before publishing. An
        asset with no line is one nobody can check later.
        """
        return [entity["attribution"] for entity in self.entities
                if entity.get("attribution")]


async def _probe(name: str, *, timeout: float) -> Wiki | None:
    """Ask a wiki whether it exists, and how big it is.

    `siteinfo` is the cheapest call MediaWiki has and it is the only honest test: a
    subdomain that parses is not a wiki, and a wiki that 404s here is not one either.
    """
    try:
        data = await fandom._api(name, {"action": "query", "meta": "siteinfo",
                                        "siprop": "general|statistics"}, timeout=timeout)
    except (httpx.HTTPError, ValueError) as exc:
        log.info("wiki probe failed for %s: %s", name, exc)
        return None
    general = (data.get("query") or {}).get("general") or {}
    stats = (data.get("query") or {}).get("statistics") or {}
    if not general.get("sitename"):
        return None
    return Wiki(
        name=name,
        title=str(general.get("sitename") or ""),
        url=str(general.get("server") or f"https://{name}.fandom.com"),
        articles=int(stats.get("articles") or 0),
        language=str(general.get("lang") or ""),
    )


def wiki_names(urls) -> list[str]:
    """Fandom subdomains read out of URLs, in the order they were seen, deduped.

    Reading rather than constructing is the whole point. Every name that comes back
    here appeared in a link a search engine returned, so the worst case is a wiki that
    exists and is wrong — never a subdomain nobody ever registered.
    """
    seen: list[str] = []
    for url in urls:
        match = WIKI_HOST.search(str(url or ""))
        if not match:
            continue
        name = match.group(1).lower()
        if name in NOT_A_WIKI or name in seen:
            continue
        seen.append(name)
    return seen


async def discover(topic: str, *, search=None, limit: int = 4,
                   timeout: float = 20.0) -> list[Wiki]:
    """Candidate wikis for a topic, verified and ordered by size.

    `search` is any provider with the app's `.search(query)` shape. Without one this
    returns nothing rather than falling back to a constructed name — an empty list is a
    caller's cue to ask for the wiki, and a made-up subdomain is a wrong answer wearing
    a right answer's clothes.
    """
    if search is None or not str(topic or "").strip():
        return []
    try:
        results = await search.search(f"{topic} site:fandom.com wiki")
    except Exception as exc:
        log.info("wiki discovery search failed for %r: %s", topic, exc)
        return []

    urls = [getattr(item, "url", "") or (item.get("url", "") if isinstance(item, dict) else "")
            for item in (results or [])]
    names = wiki_names(urls)[: max(1, limit) * 2]
    if not names:
        return []

    gate = asyncio.Semaphore(PROBE_CONCURRENCY)

    async def probe(name: str):
        async with gate:
            return await _probe(name, timeout=timeout)

    found = [wiki for wiki in await asyncio.gather(*(probe(name) for name in names))
             if wiki is not None]
    # Article count, because the franchise's own wiki is the big one and the mirrors,
    # forks and abandoned starts are not. It orders the candidates; it does not pick.
    found.sort(key=lambda wiki: wiki.articles, reverse=True)
    return found[:limit]


async def gather(wiki: str, entities, *, gallery: int = 12,
                 timeout: float = 25.0) -> Gathered:
    """Read every named entity off one wiki, with its gallery.

    Sequential rather than concurrent, deliberately. This is a keyless read of somebody
    else's wiki and each entity is already three or four requests; firing a run's worth
    of them at once is the behaviour that gets a public API closed.
    """
    site = str(wiki or "").strip().lower().removesuffix(".fandom.com")
    out = Gathered(wiki=site)
    if not site:
        out.notes.append("no wiki named — the canon lane did not run")
        return out

    for name in entities:
        wanted = str(name or "").strip()
        if not wanted:
            continue
        try:
            found = await fandom.lookup(site, wanted, timeout=timeout)
        except Exception as exc:
            out.missing.append(wanted)
            out.notes.append(f"{wanted}: lookup failed — {exc}")
            continue
        if found is None:
            out.missing.append(wanted)
            # Named, not silent. A missing entity is a hole in the video's structure
            # and the operator has to know which one, because the fix is a different
            # spelling or a different wiki — never a generated stand-in.
            out.notes.append(
                f"{wanted}: no page on {site} had both artwork and a readable section, "
                f"so this entity cannot carry a segment")
            continue

        try:
            assets = await fandom.images(site, found.title, limit=gallery, timeout=timeout)
        except Exception as exc:
            assets = []
            out.notes.append(f"{found.title}: gallery read failed — {exc}")

        record = found.as_dict()
        record["asked_for"] = wanted
        record["gallery"] = [asset.as_dict() for asset in assets]
        record["attribution"] = found.attribution()

        beat_chars = sum(len(text) for text in found.beats.values())
        if beat_chars < MIN_BEAT_CHARS:
            record["thin"] = True
            out.notes.append(
                f"{found.title}: only {beat_chars} characters of readable section — "
                f"a stub, and a stub read as a segment is one sentence rephrased")
        if len(record["gallery"]) < 2:
            out.notes.append(
                f"{found.title}: {len(record['gallery'])} usable image(s) on the page — "
                f"the segment will lean on too few pictures")
        out.entities.append(record)

    return out
