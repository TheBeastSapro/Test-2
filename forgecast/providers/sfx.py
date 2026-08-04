"""Sound effects, in tiers, because one vendor cannot hold all three kinds.

`nodes.sound` used to ask the configured *music* vendor for its effects, which meant the
accent palette was whatever that one subscription happened to stock. That fails in two
directions at once. A channel with no music vendor got no effects at all, even though it
had asked for accents and accents are opt-out. And a channel with a good music vendor
still could not get the one sound a reference actually used — because the sounds that
carry a modern faceless edit are frequently not library sounds at all.

So the chain, in order, each tier answering a different question:

  Epidemic     the subscription, if there is one. Cleared for commercial use, no
               attribution, and the right answer whenever it has the sound
  Freesound    Creative Commons, huge, and free. Covers everything the library misses
               that is a *description* — "glass shatter", "riser", "vinyl scratch"
  web          the exact named sound. Not a description: a specific, recognisable cue
               a viewer identifies. No library has these, which is the whole reason
               this tier exists

The tiers are not interchangeable and the order is not a preference. Each one is asked
only for what the tier above could not answer, because falling through costs something:
Epidemic is cleared, Freesound needs its licence checked and sometimes credited, and the
web tier establishes no licence at all and says so.

## The web tier is the operator's call, not the app's

It gets exactly the treatment `providers.footage`'s operator lane gets, for exactly the
same reason: the app cannot establish the rights on a recognisable cue, so it does not
pretend to. The sound is fetched, it is recorded, the run is flagged with a reason in
words, and publish is never blocked. What the app owes is that the decision is visible,
not that the decision is made for the operator.

It is also off unless asked for. A palette search that quietly fell through to the web
would flag runs that never wanted it, and a flag that appears for no reason is a flag
people learn to ignore.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from .base import MediaResult, ProviderError, ProviderTimeout, SoundEffectAsset

log = logging.getLogger("forgecast.providers.sfx")

_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)
USER_AGENT = "Forgecast/0.1 (+https://github.com/TheBeastSapro/Test-2) sound effect fetcher"

# Freesound licences, in the same terms `providers.stock` uses. Freesound publishes these
# as URLs rather than slugs, so they are matched by substring on the URL.
#
# `by-nc` is excluded and that is not caution — a monetised video is commercial use, and
# a non-commercial licence is breached by it. Freesound holds a great deal of `by-nc`, so
# omitting this filter would look like the tier working well right up until it did not.
FREESOUND_SAFE = {
    "publicdomain": "cc0",
    "creativecommons.org/publicdomain": "cc0",
    "creativecommons.org/licenses/by/": "by",
}

# How long a sound may run and still be an accent. Longer than this is a bed, and a bed
# arriving through the accent path is how a "whoosh" turns out to be ninety seconds of
# ambience laid under a cut.
MAX_ACCENT_SECONDS = 6.0

# Where a fetched sound is trimmed to, when the source is longer than an accent should be.
# The web tier especially returns whole videos: a meme cue is the first second or two of
# one, and the rest is somebody talking over it.
WEB_TRIM_SECONDS = 6.0


class SfxError(ProviderError):
    """A sound-effect source failed in a way the operator can act on."""


@dataclass
class SfxResult:
    """One fetched effect, and what is known about the right to use it."""

    asset: SoundEffectAsset
    path: Path
    licence: str = ""
    attribution: str = ""
    landing_url: str = ""
    tier: str = ""
    # Set by the web tier only. Same meaning as `footage.FootageClip.operator_directed`:
    # the app did not establish the licence and will not claim to have.
    operator_directed: bool = False
    flag_reason: str = ""

    @property
    def commercially_safe(self) -> bool:
        if self.operator_directed:
            return False
        return self.licence.lower() in {"cc0", "pdm", "by", "epidemic"}

    @property
    def needs_attribution(self) -> bool:
        return self.licence.lower() == "by" or self.operator_directed

    def as_dict(self) -> dict:
        return {
            **self.asset.as_dict(),
            "path": str(self.path),
            "licence": self.licence,
            "attribution": self.attribution,
            "landing_url": self.landing_url,
            "tier": self.tier,
            "commercially_safe": self.commercially_safe,
            "needs_attribution": self.needs_attribution,
            "operator_directed": self.operator_directed,
            "flag_reason": self.flag_reason,
        }


# ------------------------------------------------------------------------ freesound


def _freesound_licence(url: str) -> str:
    """The slug for a Freesound licence URL, or empty when it is not one we may use."""
    lowered = str(url or "").lower()
    for marker, slug in FREESOUND_SAFE.items():
        if marker in lowered:
            return slug
    return ""


async def search_freesound(
    term: str, *, api_key: str, seconds_max: float = MAX_ACCENT_SECONDS, limit: int = 6
) -> list[tuple[SoundEffectAsset, str, str, str]]:
    """`(asset, licence, attribution, landing_url)` for commercially usable matches.

    Filtered on the licence at the query rather than after it, because Freesound's
    `by-nc` holdings are large enough that a post-filter would routinely empty a page
    that looked full — the tier would appear to work and return nothing.
    """
    if not str(api_key or "").strip():
        return []

    params = {
        "query": term,
        "token": api_key.strip(),
        "page_size": max(1, min(int(limit), 30)),
        "fields": "id,name,duration,license,username,url,previews,tags",
        "filter": f"duration:[0 TO {max(1.0, float(seconds_max)):.0f}]",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT,
                                     headers={"User-Agent": USER_AGENT}) as client:
            response = await client.get(
                "https://freesound.org/apiv2/search/text/", params=params)
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException as exc:
        raise ProviderTimeout("Freesound search timed out") from exc
    except httpx.HTTPError as exc:
        raise SfxError(f"Freesound search failed: {exc}") from exc

    out: list[tuple[SoundEffectAsset, str, str, str]] = []
    for row in (payload.get("results") or []):
        licence = _freesound_licence(row.get("license") or "")
        if not licence:
            continue
        who = str(row.get("username") or "")
        landing = str(row.get("url") or "")
        asset = SoundEffectAsset(
            effect_id=f"freesound:{row.get('id')}",
            title=str(row.get("name") or "sound"),
            duration_seconds=float(row.get("duration") or 0.0),
            tags=[str(tag) for tag in (row.get("tags") or [])],
            preview_url=str((row.get("previews") or {}).get("preview-hq-mp3") or ""),
            provider="freesound",
        )
        attribution = (f"{asset.title} by {who} — {licence.upper()} — {landing}"
                       if licence == "by" else "")
        out.append((asset, licence, attribution, landing))
    return out


async def fetch_freesound(preview_url: str, out_path: Path) -> Path:
    """Download a Freesound preview.

    The preview rather than the original, and that is a licence decision as much as a
    convenience: the original download endpoint needs OAuth on behalf of a user account,
    while the previews are served on the same Creative Commons terms the search reports.
    An HQ mp3 preview is well past what an accent under narration needs.
    """
    if not preview_url:
        raise SfxError("that Freesound result has no downloadable preview")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True,
                                     headers={"User-Agent": USER_AGENT}) as client:
            response = await client.get(preview_url)
            response.raise_for_status()
            out_path.write_bytes(response.content)
    except httpx.TimeoutException as exc:
        raise ProviderTimeout("Freesound download timed out") from exc
    except httpx.HTTPError as exc:
        raise SfxError(f"Freesound download failed: {exc}") from exc
    return out_path


# ----------------------------------------------------------------------- the web tier


def _ytdlp() -> str:
    found = shutil.which("yt-dlp")
    if not found:
        raise SfxError(
            "yt-dlp is needed to fetch a named sound from the web — install it in Setup"
        )
    return found


def fetch_named_sound(query: str, out_path: Path, *,
                      seconds: float = WEB_TRIM_SECONDS) -> SfxResult:
    """The exact named cue, from the open web, flagged rather than claimed.

    Searched rather than browsed, and trimmed on arrival: what comes back is a whole
    video whose first seconds are the sound and whose remainder is somebody talking over
    it. Trimming at fetch is the same rule `footage.strip_audio` follows — a later stage
    that never knew where the file came from should not be able to lay ninety seconds of
    somebody's commentary under a cut.

    Nothing here establishes a licence, and the result says so. `commercially_safe` is
    false, the run carries a reason in words, and publish is not blocked.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        _ytdlp(), f"ytsearch1:{query}",
        "--extract-audio", "--audio-format", "mp3",
        "--postprocessor-args", f"ExtractAudio:-t {max(0.5, float(seconds)):.2f}",
        "--no-playlist", "--quiet", "--no-warnings",
        "-o", str(out_path.with_suffix(".%(ext)s")),
    ]
    result = subprocess.run(command, capture_output=True, timeout=300)
    landed = out_path.with_suffix(".mp3")
    if result.returncode != 0 or not landed.exists():
        raise SfxError(
            f"could not fetch '{query}': "
            f"{result.stderr.decode(errors='replace')[-200:] or 'nothing came back'}"
        )

    return SfxResult(
        asset=SoundEffectAsset(
            effect_id=f"web:{query}", title=query,
            duration_seconds=float(seconds), provider="web",
        ),
        path=landed,
        # Not a licence, and named so nothing downstream mistakes it for one.
        licence="not_established",
        tier="web",
        operator_directed=True,
        flag_reason=(
            f"'{query}' was fetched from the open web because no library holds it. "
            f"Forgecast did not establish the rights on this sound; trimmed to "
            f"{seconds:.0f}s at fetch."
        ),
    )


# ---------------------------------------------------------------------------- the chain


@dataclass
class SfxChain:
    """Epidemic, then Freesound, then the web — asked in that order, once each.

    Presents the two methods `nodes.sound.fetch_palette` already calls, so the palette
    builder does not learn about tiers. What it does learn is which tier answered, on
    every result, because a palette that quietly came from the web is the thing an
    operator most needs to be told about.
    """

    # The configured music vendor, or `None`. Typed loosely on purpose: this only ever
    # calls the two sound-effect methods on it, and demanding the full `MusicProvider`
    # here would make a stub in a test implement `make_bed` for no reason.
    music_provider: object | None = None
    freesound_key: str = ""
    # Off unless asked for. A palette that fell through to the web on its own would flag
    # runs that never wanted it, and a flag that appears for no reason gets ignored.
    allow_web: bool = False
    used: list[SfxResult] = field(default_factory=list)

    def tiers(self) -> list[str]:
        """Which tiers are actually available, for the run to report before it spends."""
        found = []
        if self.music_provider is not None:
            found.append("epidemic")
        if str(self.freesound_key or "").strip():
            found.append("freesound")
        if self.allow_web:
            found.append("web")
        return found

    async def search_sound_effects(
        self, *, term: str = "", tags: tuple[str, ...] = (),
        seconds_max: float = 0.0, limit: int = 10,
    ) -> list[SoundEffectAsset]:
        """Library tiers only. The web tier is not a search — see `fetch_named`.

        Deliberate: the web tier answers "get me this exact sound", which is a request
        for one named thing, not a query returning candidates to ration across a palette.
        Letting it answer a search would put an unlicensed result in a list the caller
        believes is interchangeable.
        """
        seconds_max = seconds_max or MAX_ACCENT_SECONDS
        found: list[SoundEffectAsset] = []

        if self.music_provider is not None:
            try:
                found.extend(await self.music_provider.search_sound_effects(
                    term=term, tags=tags, seconds_max=seconds_max, limit=limit))
            except (ProviderError, ProviderTimeout) as exc:
                log.warning("subscription tier skipped for %r: %s", term, exc)

        if len(found) < limit:
            try:
                found.extend(
                    asset for asset, *_ in await search_freesound(
                        term, api_key=self.freesound_key,
                        seconds_max=seconds_max, limit=limit - len(found))
                )
            except (ProviderError, ProviderTimeout) as exc:
                log.warning("Freesound tier skipped for %r: %s", term, exc)

        return found[:limit]

    async def fetch_sound_effect(self, effect_id: str, *, out_path: Path) -> MediaResult:
        """Download whichever tier the id belongs to.

        Routed on the id's own prefix rather than on a remembered search, because a
        palette is fetched well after it was searched and a chain that relied on its own
        memory would fetch the wrong file the first time two roles shared a term.
        """
        if str(effect_id).startswith("freesound:"):
            assets = await search_freesound(
                effect_id.split(":", 1)[1], api_key=self.freesound_key, limit=1)
            if not assets:
                raise SfxError(f"{effect_id} could not be resolved on Freesound")
            asset, licence, attribution, landing = assets[0]
            path = await fetch_freesound(asset.preview_url, out_path.with_suffix(".mp3"))
            self.used.append(SfxResult(asset=asset, path=path, licence=licence,
                                       attribution=attribution, landing_url=landing,
                                       tier="freesound"))
            return MediaResult(path=path, mime="audio/mpeg", provider="freesound",
                               duration_seconds=asset.duration_seconds,
                               meta={"licence": licence, "attribution": attribution,
                                     "tier": "freesound"})

        if self.music_provider is None:
            raise SfxError(f"no tier can fetch {effect_id}")
        result = await self.music_provider.fetch_sound_effect(effect_id, out_path=out_path)
        self.used.append(SfxResult(
            asset=SoundEffectAsset(effect_id=effect_id, title=effect_id,
                                   duration_seconds=result.duration_seconds,
                                   provider=result.provider or "epidemic"),
            path=result.path, licence="epidemic", tier="epidemic"))
        result.meta = {**(result.meta or {}), "licence": "epidemic", "tier": "epidemic"}
        return result

    def fetch_named(self, query: str, out_path: Path,
                    *, seconds: float = WEB_TRIM_SECONDS) -> SfxResult:
        """The exact cue, from the web, when the operator asked for that by name."""
        if not self.allow_web:
            raise SfxError(
                f"'{query}' is not in any configured library, and fetching a named sound "
                f"from the web was not enabled for this run"
            )
        result = fetch_named_sound(query, out_path, seconds=seconds)
        self.used.append(result)
        return result

    # -- reporting ---------------------------------------------------------------

    def flags(self) -> list[str]:
        """Every reason this run should be flagged. Empty when nothing needs one."""
        return [item.flag_reason for item in self.used
                if item.operator_directed and item.flag_reason]

    def credits(self) -> list[str]:
        """Attribution lines the licences oblige, for the run's credit file."""
        return [item.attribution for item in self.used
                if item.needs_attribution and item.attribution]
