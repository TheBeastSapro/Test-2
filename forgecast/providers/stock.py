"""Keyless stock imagery via Openverse — real visuals with no key and no spend.

Generated B-roll is ~90% of a video's cost. Licensed stock is the alternative most
faceless channels actually use, and Openverse indexes openly-licensed media across
Flickr, Wikimedia, museums and more with **no API key at all**.

## The licence rule, which is not optional

A monetised YouTube video is commercial use, and it is a derivative work. That rules
out two common Creative Commons variants outright:

  cc0     public domain — safe, no attribution required
  by      safe for commercial use, attribution REQUIRED
  by-sa   share-alike: would oblige you to license the whole video the same way
  by-nc   non-commercial only: a monetised video breaches it
  by-nd   no derivatives: cutting it into a video breaches it

So the default filter is `cc0,by` and nothing else. Widening it is possible but the
node records exactly what was used, and every `by` image accrues an attribution line
that must ship with the video. `attribution.md` is written per run for that reason —
using someone's photo without the credit their licence requires is not a technicality.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from .base import ImageProvider, MediaResult, ProviderError, ProviderTimeout

log = logging.getLogger("forgecast.providers.stock")

_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)
# Wikimedia — a major Openverse source — rejects requests whose User-Agent carries no
# contact route, per its UA policy, and returns 403 on the image itself rather than on
# the search. Anything fetching their files needs an identifiable agent.
USER_AGENT = (
    "Forgecast/0.1 (+https://github.com/TheBeastSapro/Test-2) "
    "openly-licensed media fetcher"
)

# Licences safe for a monetised, edited video. See the module docstring.
COMMERCIAL_SAFE = ("cc0", "pdm", "by")
ATTRIBUTION_REQUIRED = {"by", "by-sa"}


@dataclass
class StockAsset:
    url: str
    title: str
    creator: str
    licence: str
    licence_url: str
    attribution: str
    source: str
    landing_url: str
    width: int = 0
    height: int = 0
    tags: list[str] = field(default_factory=list)

    def relevance_to(self, query: str) -> tuple[str, float]:
        return relevance(query, title=self.title, tags=self.tags)

    @property
    def needs_attribution(self) -> bool:
        return self.licence.lower() in ATTRIBUTION_REQUIRED

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "creator": self.creator,
            "licence": self.licence,
            "licence_url": self.licence_url,
            "attribution": self.attribution,
            "source": self.source,
            "landing_url": self.landing_url,
            "needs_attribution": self.needs_attribution,
            "width": self.width,
            "height": self.height,
        }


@dataclass
class OpenverseProvider(ImageProvider):
    """Searches Openverse and downloads the best match for a prompt.

    Satisfies the ImageProvider contract so it drops into the pipeline wherever a
    generated image would go — the shots node does not know the difference.
    """

    name: str = "openverse"
    api_key: str = ""
    base_url: str = "https://api.openverse.org/v1"
    licences: tuple[str, ...] = COMMERCIAL_SAFE
    # Every asset used, so the run can emit an attribution file.
    used: list[StockAsset] = field(default_factory=list)

    async def search(
        self, query: str, *, limit: int = 8, wide_only: bool = True
    ) -> list[StockAsset]:
        params = {
            "q": query,
            "page_size": min(limit, 20),
            "license": ",".join(self.licences),
        }
        if wide_only:
            # Landscape suits 16:9, but it is a hard filter that can empty a result
            # set on its own — the ladder in `generate` drops it before giving up.
            params["aspect_ratio"] = "wide"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(
                    f"{self.base_url}/images/",
                    params=params,
                    headers={"User-Agent": USER_AGENT},
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(str(exc), provider=self.name) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(str(exc), provider=self.name, retryable=True) from exc

        if not response.is_success:
            raise ProviderError(
                f"openverse returned {response.status_code}: {response.text[:200]}",
                provider=self.name,
                retryable=response.status_code >= 500 or response.status_code == 429,
            )

        assets: list[StockAsset] = []
        for entry in response.json().get("results") or []:
            if not entry.get("url"):
                continue
            assets.append(
                StockAsset(
                    url=entry["url"],
                    title=str(entry.get("title") or "untitled"),
                    creator=str(entry.get("creator") or "unknown"),
                    licence=str(entry.get("license") or ""),
                    licence_url=str(entry.get("license_url") or ""),
                    attribution=str(entry.get("attribution") or ""),
                    source=str(entry.get("source") or ""),
                    landing_url=str(entry.get("foreign_landing_url") or ""),
                    width=int(entry.get("width") or 0),
                    height=int(entry.get("height") or 0),
                    tags=[
                        str(tag.get("name", "")).lower()
                        for tag in (entry.get("tags") or [])
                        if isinstance(tag, dict)
                    ],
                )
            )
        return assets

    async def generate(
        self, prompt: str, *, out_path: Path, width: int = 1280, height: int = 720
    ) -> MediaResult:
        """`generate` in name only — this finds and fetches, it does not synthesise.

        Keeping the ImageProvider signature is what lets stock and generation be
        swapped without touching the pipeline. The distinction still matters for the
        operator, so `meta.method` says "stock_search" and the licence travels with it.
        """
        # A relaxation ladder, because a generative prompt makes a bad search term.
        # Each rung gives up one constraint: length first, then the aspect filter,
        # then all but the most distinctive word. Failing at the top rung and stopping
        # was leaving perfectly findable subjects unillustrated.
        query = to_query(prompt)
        words = query.split()
        attempts: list[tuple[str, bool]] = [(query, True)]
        if len(words) > 3:
            attempts.append((" ".join(words[:3]), True))
        attempts.append((" ".join(words[:3]) if len(words) > 3 else query, False))
        if words:
            longest = sorted(words, key=len, reverse=True)[:2]
            attempts.append((" ".join(longest), False))

        # Which rung succeeded matters as much as whether one did. Relaxing to two
        # stray keywords will always return *something*, and that something is often
        # unrelated — a film about undersea cables was served "Blue Grass Chemical
        # Agent-Destruction". A wrong picture shown confidently is worse than an
        # honest gap, so the rung travels with the result as a relevance grade and the
        # pipeline can treat a weak match as degraded.
        assets: list[StockAsset] = []
        used_query = query
        rung = 0
        for index, (candidate_query, wide) in enumerate(attempts):
            if not candidate_query.strip():
                continue
            assets = await self.search(candidate_query, limit=8, wide_only=wide)
            if assets:
                used_query, rung = candidate_query, index
                break

        # Rank by measured relevance to the *original* prompt, not by the rung that
        # found them: a relaxed query can still surface a genuinely apt picture, and a
        # tight one can surface a dud.
        assets.sort(key=lambda item: -item.relevance_to(query)[1])

        if not assets:
            raise ProviderError(
                f"no openly-licensed image found for {query!r} after "
                f"{len(attempts)} search attempts",
                provider=self.name,
                retryable=False,
            )

        # Relevance first, then size — a big wrong picture is still a wrong picture.
        ordered = sorted(
            assets,
            key=lambda item: (
                -item.relevance_to(query)[1],
                -(item.width * item.height) if item.width >= width else 0,
            ),
        )

        out_path = out_path.with_suffix(".jpg")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Walk the candidates on download failure rather than failing the shot. Some
        # hosts rate-limit or refuse hotlinking, and there are seven other results
        # sitting right there — giving up on the first 403 was losing usable shots.
        chosen: StockAsset | None = None
        failures: list[str] = []
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            for candidate in ordered[:5]:
                try:
                    response = await client.get(
                        candidate.url, headers={"User-Agent": USER_AGENT}
                    )
                except httpx.HTTPError as exc:
                    failures.append(f"{candidate.source}: {exc}")
                    continue
                if not response.is_success:
                    failures.append(f"{candidate.source}: HTTP {response.status_code}")
                    continue
                if len(response.content) < 2048:
                    failures.append(f"{candidate.source}: file too small to be an image")
                    continue
                out_path.write_bytes(response.content)
                chosen = candidate
                break

        relevance, ratio = (chosen.relevance_to(query) if chosen else ("weak", 0.0))

        if chosen is None:
            raise ProviderError(
                f"found {len(assets)} licensed images for {used_query!r} but none "
                f"could be downloaded ({'; '.join(failures[:3])})",
                provider=self.name,
                retryable=True,
            )

        self.used.append(chosen)
        if relevance == "weak":
            log.warning(
                "weak stock match for %r -> %r: the query had to be relaxed to two "
                "keywords, so this image may not depict the subject",
                prompt[:50], chosen.title,
            )
        else:
            log.info("stock image (%s) for %r: %s (%s)", relevance, used_query[:40],
                     chosen.title, chosen.licence)

        return MediaResult(
            path=out_path,
            mime="image/jpeg",
            credits=0,          # keyless and free; do not invent a charge
            provider=self.name,
            meta={
                "method": "stock_search",
                "query": used_query,
                "prompt": prompt[:200],
                "relevance": relevance,
                "relevance_ratio": round(ratio, 3),
                "search_rung": rung,
                "title": chosen.title,
                "licence": chosen.licence,
                "attribution": chosen.attribution,
                "creator": chosen.creator,
                "landing_url": chosen.landing_url,
                "needs_attribution": chosen.needs_attribution,
            },
        )

    def attribution_markdown(self) -> str:
        """The credits file that must ship with any video using `by` assets."""
        if not self.used:
            return ""
        lines = [
            "# Image credits",
            "",
            "This video uses openly-licensed images. Credits below are required by "
            "their licences and should be included in the video description.",
            "",
        ]
        for asset in self.used:
            if asset.attribution:
                lines.append(f"- {asset.attribution}")
            else:
                lines.append(
                    f"- \"{asset.title}\" by {asset.creator}, {asset.licence.upper()} "
                    f"({asset.licence_url})"
                )
            if asset.landing_url:
                lines.append(f"  Source: {asset.landing_url}")
        return "\n".join(lines)


def relevance(query: str, *, title: str = "", tags: list[str] | None = None
              ) -> tuple[str, float]:
    """How much of the query a result's own words actually account for.

    Measured, not inferred. Grading by how far the query had to be relaxed turned out to
    be a poor proxy: Openverse returns *something* for almost any three words, so a
    lightly-shortened query still produced "Blue Grass Chemical Agent-Destruction" for a
    film about undersea cables. Comparing the query against the result's title and tags
    catches that, because a genuinely relevant result shares vocabulary with the request
    and an irrelevant one does not.

    Module-level rather than a method, because footage answers the same question about
    the same two fields. Two implementations of "does this depict the subject" would
    differ the first time either was tuned, and then a clip and a still would disagree
    about the same search — with the clip's answer deciding whether money is spent.
    """
    wanted = {word for word in query.lower().split() if len(word) > 2}
    if not wanted:
        return "weak", 0.0
    haystack = f"{title} {' '.join(tags or [])}".lower()
    hits = sum(1 for word in wanted if word in haystack)
    ratio = hits / len(wanted)
    if ratio >= 0.6:
        return "exact", ratio
    if ratio >= 0.34:
        return "close", ratio
    if ratio > 0:
        return "relaxed", ratio
    return "weak", 0.0


def to_query(prompt: str) -> str:
    """Turn a generative prompt into a search term.

    Generative prompts are long and full of camera and lighting language that a stock
    index cannot use. Stripping it to concrete nouns is the difference between results
    and none.

    Public, because the footage lane searches on the same prompts. The alternative was
    asking the shot planner for a `search_query` field beside each prompt, which doubles
    the planning tokens for a beat and creates a second description of one shot that can
    drift from the prompt the generator actually uses — and when the two disagree, the
    free lane searches for one thing while the fallback generates another.
    """
    noise = {
        "cinematic", "establishing", "shot", "illustrating", "moody", "lighting",
        "shallow", "depth", "of", "field", "b-roll", "broll", "documentary",
        "camera", "slow", "push", "in", "pan", "left", "right", "static", "closeup",
        "close-up", "wide", "angle", "lens", "natural", "light", "high", "contrast",
        "composition", "subject", "beat", "the", "a", "an", "with", "and", "for",
    }
    cleaned = prompt.lower().replace("-", " ").replace("/", " ")
    words = [word.strip(",.;:\"'()") for word in cleaned.split()]
    kept = [word for word in words if word and word not in noise and len(word) > 2]
    # Six words is about where stock relevance peaks; beyond that recall collapses.
    return " ".join(kept[:6]) or prompt[:60]
