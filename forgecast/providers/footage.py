"""Real footage: licensed sources, and the one lane where the operator overrides.

## Why this is not the image provider with a different endpoint

`stock.py` fetches stills and the licence question there has a clean answer — Openverse
indexes the licence alongside the file, so a filter of `cc0,by` is the whole rule. Moving
footage does not work that way. The sources worth using have four different ideas of what
"free" means, and three of them are not Creative Commons at all:

  Pexels, Pixabay     their own licence: free for commercial use, no attribution
                      required, but redistribution *as stock* is forbidden — which a
                      video does not do, and a footage pack would
  Internet Archive     per-item, and genuinely mixed. Prelinger is public domain; the
                      item next to it may be a rip somebody uploaded. The collection
                      is the signal, not the site
  NASA, NOAA, US gov   public domain as a work of the federal government, with two
                      standing exceptions: contractor-made material may be restricted,
                      and NASA's logos are never usable as endorsement
  YouTube CC filter    `by` only — YouTube offers exactly one Creative Commons option —
                      and the uploader may have marked it wrongly, which is not a
                      licence this app can verify

So the licence is carried per clip, from the source that knows it, and `commercially_safe`
is a property of the clip rather than a filter applied once at the top. A source that
cannot answer the question does not get a default.

## The operator lane

Everything above returns clips this app is willing to stand behind. The operator lane
does not: it takes a file the operator supplies and records that the operator supplied
it. That is the whole design, and it is deliberate — the rights judgment on a clip of
someone else's film belongs to the person publishing the video, not to a filter written
here. What the app owes them in return is that the judgment is never silent:

* audio is stripped at ingest, not at render, so a muted clip cannot become unmuted by a
  later stage that never knew where the file came from
* the clip is attributed with whatever the operator gave and whatever probing found
* the run is flagged, and the flag rides on the run rather than on a log line
* publish is never blocked, because it is not this app's call to make

There is no fetcher here that reaches an unlicensed index, and there will not be. The
operator lane exists precisely so that there does not need to be one.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from .base import ProviderError, ProviderTimeout

log = logging.getLogger("forgecast.providers.footage")

_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)

# Wikimedia and Archive both police this, and Archive returns 403 on the file rather
# than on the search — the same trap `stock.py` documents, so the same shape of answer.
USER_AGENT = (
    "Forgecast/0.1 (+https://github.com/TheBeastSapro/Test-2) "
    "licensed footage fetcher"
)

# Internet Archive collections whose licence is a property of the collection rather than
# of the item. An item found inside one of these is public domain because of where it
# lives; an item found by a bare keyword search is not, however old it looks.
#
# This is the whole reason Archive is searched by collection and not by query alone. The
# site hosts a great deal of material its uploaders had no right to post, and "it was on
# archive.org" is not a licence. Naming the collections is what makes the source usable.
PUBLIC_DOMAIN_COLLECTIONS = (
    "prelinger",              # Prelinger Archives: ephemeral and industrial film
    "feature_films",          # lapsed-copyright features
    "classic_tv",             # US TV that fell out of copyright on non-renewal
    "nasa",
    "usgovfilms",
)

# What this app will put in a video without asking. Everything else is either refused or
# routed through the operator lane, where a human takes responsibility for it.
COMMERCIAL_LICENCES = frozenset({
    "cc0", "pdm", "publicdomain", "by",
    "pexels", "pixabay",      # vendor licences, permissive for this use
    "usgov",                  # a work of the US federal government
})

ATTRIBUTION_REQUIRED = frozenset({"by", "by-sa"})


class FootageError(ProviderError):
    """A footage source failed in a way the operator can act on."""


@dataclass
class FootageClip:
    """One moving-image candidate, with the licence it actually carries.

    Deliberately the same shape as `stock.StockAsset` where the fields mean the same
    thing, so a run's `attribution.md` does not need to know whether a credit came from a
    still or a clip.
    """

    url: str
    title: str
    creator: str
    licence: str
    source: str
    landing_url: str = ""
    licence_url: str = ""
    attribution: str = ""
    seconds: float = 0.0
    width: int = 0
    height: int = 0
    tags: list[str] = field(default_factory=list)

    # Set only by the operator lane. Nothing that comes back from a licensed search may
    # set it, and nothing downstream may clear it — see `operator_clip`.
    operator_directed: bool = False
    # Why the run was flagged, in words an operator reads on the run page rather than
    # a boolean they have to interpret.
    flag_reason: str = ""

    @property
    def commercially_safe(self) -> bool:
        """Whether this app is willing to use the clip without a human deciding.

        An operator-directed clip is never safe by this test, however it was licensed.
        That is not pessimism about the file — it is that the app did not establish the
        licence, the operator did, and a property named `commercially_safe` returning
        true on the strength of someone else's say-so is the kind of quiet claim this
        codebase keeps removing.
        """
        if self.operator_directed:
            return False
        return self.licence.lower() in COMMERCIAL_LICENCES

    @property
    def needs_attribution(self) -> bool:
        return self.licence.lower() in ATTRIBUTION_REQUIRED or self.operator_directed

    def relevance_to(self, query: str) -> tuple[str, float]:
        """Whether this clip depicts what was asked for, on its own words.

        Delegates to `stock.relevance` rather than repeating it. Two implementations of
        "does this depict the subject" would differ the first time either was tuned, and
        then a clip and a still would disagree about the same search — with the clip's
        answer deciding whether money is spent.
        """
        from .stock import relevance
        return relevance(query, title=self.title, tags=self.tags)

    def fetch_reference(self) -> str:
        """What to hand `vision.acquire.acquire` to get the file.

        The landing page is preferred over the raw `url` for sources whose `url` is not
        a media file — Internet Archive's is a download *directory* and NASA's is a
        collection manifest. `acquire` refuses a non-media URL through its direct path
        and hands anything http to yt-dlp, which has an extractor for archive.org
        details pages and none for a directory listing.
        """
        media_suffixes = (".mp4", ".mov", ".webm", ".m4v", ".mkv")
        if self.url.lower().split("?")[0].endswith(media_suffixes):
            return self.url
        return self.landing_url or self.url

    def credit_line(self) -> str:
        """One line for `attribution.md`. Never empty for a clip that needs one.

        An operator-directed clip never prints a licence, whatever string it happens to
        carry. The app did not establish it, so printing `CC0` beside a file somebody
        dropped in would be this app vouching for a claim it never checked — and a
        credit block is exactly where such a claim would be believed.
        """
        who = self.creator or "unknown creator"
        where = self.landing_url or self.url
        if self.operator_directed:
            supplied = self.attribution or f"{self.title or 'untitled'} — {who}"
            return f"{supplied} (supplied by the operator; licence not established here)"
        if self.attribution:
            return self.attribution
        licence = self.licence.upper() if self.licence else "licence not established"
        return f"{self.title or 'untitled'} — {who} ({licence}) {where}".strip()

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "creator": self.creator,
            "licence": self.licence,
            "licence_url": self.licence_url,
            "source": self.source,
            "landing_url": self.landing_url,
            "attribution": self.credit_line() if self.needs_attribution else "",
            "seconds": round(self.seconds, 3),
            "width": self.width,
            "height": self.height,
            "commercially_safe": self.commercially_safe,
            "needs_attribution": self.needs_attribution,
            "operator_directed": self.operator_directed,
            "flag_reason": self.flag_reason,
        }


# --------------------------------------------------------------------------- searching


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=_TIMEOUT, headers={"User-Agent": USER_AGENT},
                             follow_redirects=True)


async def _json(url: str, params: dict, *, label: str) -> dict:
    try:
        async with _client() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException as exc:
        raise ProviderTimeout(f"{label} timed out") from exc
    except httpx.HTTPError as exc:
        raise FootageError(f"{label} failed: {exc}") from exc


async def search_archive(query: str, *, limit: int = 8) -> list[FootageClip]:
    """Internet Archive, restricted to collections whose licence is known.

    Searched by collection rather than by keyword alone, for the reason
    `PUBLIC_DOMAIN_COLLECTIONS` gives: the site hosts a great deal its uploaders had no
    right to post, and age is not a licence. This is also the honest limit of the source
    — it reaches old film and lapsed-renewal television and it does not reach anything
    recent, whatever the search box suggests.
    """
    collections = " OR ".join(f"collection:{name}" for name in PUBLIC_DOMAIN_COLLECTIONS)
    payload = await _json(
        "https://archive.org/advancedsearch.php",
        {
            "q": f"({query}) AND ({collections}) AND mediatype:movies",
            "fl[]": ["identifier", "title", "creator", "licenseurl", "year"],
            "rows": max(1, min(int(limit), 50)),
            "output": "json",
        },
        label="Internet Archive search",
    )

    clips: list[FootageClip] = []
    for row in ((payload.get("response") or {}).get("docs") or []):
        identifier = str(row.get("identifier") or "")
        if not identifier:
            continue
        creator = row.get("creator") or ""
        clips.append(FootageClip(
            url=f"https://archive.org/download/{identifier}",
            title=str(row.get("title") or identifier),
            creator=str(creator[0] if isinstance(creator, list) and creator else creator),
            # The collection is what established this, not the item's own metadata —
            # which is frequently absent and occasionally wrong.
            licence="publicdomain",
            licence_url=str(row.get("licenseurl") or ""),
            source="internet_archive",
            landing_url=f"https://archive.org/details/{identifier}",
        ))
    return clips


async def search_nasa(query: str, *, limit: int = 8) -> list[FootageClip]:
    """NASA's image and video library. Keyless, and public domain with two exceptions.

    The exceptions are recorded on the clip rather than filtered out, because neither is
    decidable from a search result: contractor-produced material can carry restrictions,
    and NASA insignia may never be used in a way that implies endorsement. An operator
    cutting a space documentary needs to know the second one exists; an app that silently
    dropped every result mentioning a logo would be wrong more often than it was right.
    """
    payload = await _json(
        "https://images-api.nasa.gov/search",
        {"q": query, "media_type": "video", "page_size": max(1, min(int(limit), 50))},
        label="NASA library search",
    )

    clips: list[FootageClip] = []
    for item in ((payload.get("collection") or {}).get("items") or [])[:limit]:
        data = (item.get("data") or [{}])[0]
        identifier = str(data.get("nasa_id") or "")
        if not identifier:
            continue
        clips.append(FootageClip(
            url=str(item.get("href") or ""),
            title=str(data.get("title") or identifier),
            creator=str(data.get("center") or "NASA"),
            licence="usgov",
            source="nasa",
            landing_url=f"https://images.nasa.gov/details/{identifier}",
            tags=[str(tag) for tag in (data.get("keywords") or [])],
        ))
    return clips


async def search_pexels(query: str, *, api_key: str, limit: int = 8) -> list[FootageClip]:
    """Pexels video search. Free, and keyed — the key meters, it does not bill.

    Worth stating because this app's rule is subscriptions rather than API keys, and the
    rule is about *spend*: a key that can run up a balance is the thing being avoided.
    A Pexels key cannot. It is a rate-limit identity on a free service, so it is the same
    category as no key at all, and an empty one degrades to the source being skipped
    rather than to an error.
    """
    if not api_key.strip():
        return []
    try:
        async with _client() as client:
            response = await client.get(
                "https://api.pexels.com/videos/search",
                params={"query": query, "per_page": max(1, min(int(limit), 50))},
                headers={"Authorization": api_key.strip(), "User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException as exc:
        raise ProviderTimeout("Pexels search timed out") from exc
    except httpx.HTTPError as exc:
        raise FootageError(f"Pexels search failed: {exc}") from exc

    clips: list[FootageClip] = []
    for row in (payload.get("videos") or []):
        files = sorted(
            (entry for entry in (row.get("video_files") or []) if entry.get("link")),
            key=lambda entry: int(entry.get("width") or 0),
            reverse=True,
        )
        if not files:
            continue
        best = files[0]
        clips.append(FootageClip(
            url=str(best.get("link") or ""),
            title=str(row.get("alt") or "Pexels clip"),
            creator=str(row.get("user", {}).get("name") or ""),
            licence="pexels",
            licence_url="https://www.pexels.com/license/",
            source="pexels",
            landing_url=str(row.get("url") or ""),
            seconds=float(row.get("duration") or 0.0),
            width=int(best.get("width") or 0),
            height=int(best.get("height") or 0),
        ))
    return clips


async def search_pixabay(query: str, *, api_key: str, limit: int = 8) -> list[FootageClip]:
    """Pixabay video search. Same category of key as Pexels — metering, not billing."""
    if not api_key.strip():
        return []
    payload = await _json(
        "https://pixabay.com/api/videos/",
        {"key": api_key.strip(), "q": query, "per_page": max(3, min(int(limit), 200))},
        label="Pixabay search",
    )

    clips: list[FootageClip] = []
    for row in (payload.get("hits") or [])[:limit]:
        streams = row.get("videos") or {}
        best = max(
            (entry for entry in streams.values() if isinstance(entry, dict) and entry.get("url")),
            key=lambda entry: int(entry.get("width") or 0),
            default=None,
        )
        if not best:
            continue
        clips.append(FootageClip(
            url=str(best.get("url") or ""),
            title=str(row.get("tags") or "Pixabay clip"),
            creator=str(row.get("user") or ""),
            licence="pixabay",
            licence_url="https://pixabay.com/service/license-summary/",
            source="pixabay",
            landing_url=str(row.get("pageURL") or ""),
            seconds=float(row.get("duration") or 0.0),
            width=int(best.get("width") or 0),
            height=int(best.get("height") or 0),
            tags=[tag.strip() for tag in str(row.get("tags") or "").split(",") if tag.strip()],
        ))
    return clips


# ---------------------------------------------------------------------- operator lane


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if not found:
        raise FootageError(
            "ffmpeg is needed to take audio off a supplied clip — install it in Setup"
        )
    return found


def strip_audio(source: Path, out_path: Path, *, start: float = 0.0,
                seconds: float = 0.0) -> Path:
    """Copy the picture and drop every audio stream, optionally trimming to a moment.

    At ingest rather than at render, and that ordering is the point. A clip that arrives
    muted cannot be un-muted by a later stage, and every later stage is written by
    somebody who does not know where the file came from. Doing it at render would mean
    the silent version is the one the renderer happens to produce, which is a property of
    a code path rather than a property of the file.

    `start` and `seconds` are here so the operator can name a moment inside a longer file
    instead of trimming it by hand first — the ask that makes this lane usable.
    """
    if not source.is_file():
        raise FootageError(f"there is no file at {source}")

    command = [_ffmpeg(), "-v", "error", "-y"]
    if start > 0:
        command += ["-ss", f"{max(0.0, float(start)):.3f}"]
    command += ["-i", str(source)]
    if seconds > 0:
        command += ["-t", f"{max(0.0, float(seconds)):.3f}"]
    # `-an` drops audio; the video stream is copied where the trim allows it, so this
    # costs a remux rather than a re-encode on the common path.
    command += ["-an", "-c:v", "copy", str(out_path)]

    result = subprocess.run(command, capture_output=True, timeout=600)
    if result.returncode != 0 or not out_path.exists():
        # A stream copy cannot always start at an arbitrary frame. Re-encoding is the
        # documented fallback and it is worth taking silently, because the alternative is
        # telling an operator that a perfectly good file "failed".
        command[-3:] = ["-an", "-c:v", "libx264", "-preset", "veryfast", str(out_path)]
        result = subprocess.run(command, capture_output=True, timeout=900)
    if result.returncode != 0:
        raise FootageError(
            f"could not take the audio off {source.name}: "
            f"{result.stderr.decode(errors='replace')[-300:]}"
        )
    return out_path


def operator_clip(
    source: str | Path,
    out_path: Path,
    *,
    start: float = 0.0,
    seconds: float = 0.0,
    title: str = "",
    creator: str = "",
    note: str = "",
) -> FootageClip:
    """Take a clip the operator supplied. Muted, attributed, and flagged.

    The app does not fetch this and does not judge it. What it does is make the operator's
    decision visible on the run, which is the trade that lets the lane exist at all:

    * the audio is gone before anything else touches the file
    * whatever the operator said about provenance is recorded, and when they said nothing
      the credit line says the licence was not established rather than leaving it blank
    * `flag_reason` is set, so the run carries the reason and not merely a boolean

    Publish is never blocked from here. That is the operator's call and this returns the
    information they need to make it, not a veto.
    """
    path = Path(source)
    if not path.is_file():
        raise FootageError(
            f"operator-directed footage must be a file this machine can read; "
            f"{source} is not one"
        )

    strip_audio(path, out_path, start=start, seconds=seconds)
    clip = FootageClip(
        url=str(out_path),
        title=title.strip() or path.stem,
        creator=creator.strip(),
        # Not a licence, and named so it cannot be mistaken for one by a later reader or
        # by `COMMERCIAL_LICENCES`, which does not contain it.
        licence="operator_supplied",
        source="operator",
        landing_url="",
        seconds=float(seconds or 0.0),
        operator_directed=True,
        flag_reason=(
            note.strip()
            or "operator-directed footage: licence established by the operator, not by "
               "this app. Audio removed at ingest."
        ),
    )
    log.info("operator-directed clip accepted, muted: %s", clip.title)
    return clip


# ------------------------------------------------------------------------------ search


async def find(
    query: str,
    *,
    limit: int = 8,
    pexels_key: str = "",
    pixabay_key: str = "",
) -> list[FootageClip]:
    """Every licensed source, best licence first, failures skipped rather than fatal.

    Ordered by how firmly the licence is established rather than by how good the footage
    tends to be: a public-domain government clip needs no further thought, a vendor
    licence needs the operator to not be reselling it as stock, and anything with `by` on
    it accrues a credit line that has to ship with the video.

    One source being down is not a reason to fail the whole search — the caller wanted
    footage, and three sources answering is an answer.
    """
    found: list[FootageClip] = []
    attempts = (
        ("NASA", search_nasa(query, limit=limit)),
        ("Internet Archive", search_archive(query, limit=limit)),
        ("Pexels", search_pexels(query, api_key=pexels_key, limit=limit)),
        ("Pixabay", search_pixabay(query, api_key=pixabay_key, limit=limit)),
    )
    for label, coroutine in attempts:
        try:
            found.extend(await coroutine)
        except (FootageError, ProviderTimeout) as exc:
            log.warning("%s footage search skipped: %s", label, exc)

    safe = [clip for clip in found if clip.commercially_safe]
    safe.sort(key=lambda clip: (clip.needs_attribution, -clip.width))
    return safe[:limit]


def attribution_markdown(clips: list[FootageClip]) -> str:
    """The credit block for a run, covering both licensed and operator-directed clips.

    Operator-directed clips are listed in their own section rather than mixed in, because
    the two say different things: one is a credit the licence requires, the other is a
    record of a decision somebody made. Flattening them into one list would let the
    second read as the first.
    """
    licensed = [clip for clip in clips if not clip.operator_directed and clip.needs_attribution]
    directed = [clip for clip in clips if clip.operator_directed]

    lines: list[str] = []
    if licensed:
        lines.append("## Footage credits")
        lines.extend(f"- {clip.credit_line()}" for clip in licensed)
    if directed:
        if lines:
            lines.append("")
        lines.append("## Operator-directed footage")
        lines.append(
            "Supplied by the operator rather than sourced by Forgecast. Audio was "
            "removed at ingest. The licence position on these is the operator's."
        )
        lines.extend(f"- {clip.credit_line()}" for clip in directed)
    return "\n".join(lines)


# ----------------------------------------------------------------------- choosing one

#: How well a clip must match before it is preferred to generating the shot.
#:
#: Higher than the still lane's bar, and the asymmetry is the point rather than taste.
#: A still that matches loosely still beats the still lane's alternative, which is a
#: captioned colour card. A clip that matches loosely loses to *generation*, which will
#: depict the prompt exactly. So the free lane only wins when it is actually right, and
#: "cheaper" is never on its own a reason to show the wrong picture.
#:
#: `close` is `stock.relevance`'s existing band boundary at ratio >= 0.34, not a new
#: number invented here.
MIN_GRADE = ("exact", "close")


def best_for(
    clips: list[FootageClip],
    *,
    query: str,
    seconds: float = 0.0,
    width: int = 0,
) -> tuple[FootageClip | None, str]:
    """The clip worth using instead of generating this shot, and why not when there is none.

    Three tests, in the order they cost: may we use it, does it depict the subject, is it
    big enough and long enough. Each is an existing measurement — nothing here is a new
    judgement about footage, only about whether to prefer it.

    A dimension or duration of zero means *unknown*, not disqualified. NASA and Internet
    Archive report neither, and refusing every clip whose length nobody wrote down would
    silently reduce the free lane to the two vendors that fill the field in. Unknown
    duration is re-checked against the real file after download, where it is knowable.

    Returns the reason as well as the clip so the planner can say why a beat stayed
    paid — a free lane that silently declines is indistinguishable from one that never ran.
    """
    if not clips:
        return None, "no footage source answered"

    safe = [clip for clip in clips if clip.commercially_safe]
    if not safe:
        return None, f"{len(clips)} found, none usable in a monetised edit"

    big_enough = [
        clip for clip in safe
        # `width` is the render width; a clip narrower than the frame would be upscaled.
        if not (width and clip.width and clip.width < width)
    ]
    if not big_enough:
        return None, f"{len(safe)} usable, all narrower than the {width}px frame"

    long_enough = [
        clip for clip in big_enough
        # A tenth of slack: a clip a few frames short of the beat is trimmed to fit by
        # the same path that trims a long one, and refusing it would reject a good match
        # over rounding.
        if not (seconds and clip.seconds and clip.seconds < seconds * 0.9)
    ]
    if not long_enough:
        return None, f"{len(big_enough)} usable, all shorter than the {seconds:.1f}s beat"

    graded = [(clip, *clip.relevance_to(query)) for clip in long_enough]
    matching = [(clip, grade, ratio) for clip, grade, ratio in graded if grade in MIN_GRADE]
    if not matching:
        best = max(graded, key=lambda row: row[2], default=(None, "weak", 0.0))
        return None, (f"{len(long_enough)} usable, best only matched {best[1]} "
                      f"({best[2]:.2f}) — generating is more likely to be right")

    # Ties go to the clip that owes no credit, then to the wider one — `find`'s own sort
    # rule, applied again here because the filters above may have changed the order.
    matching.sort(key=lambda row: (-row[2], row[0].needs_attribution, -row[0].width))
    chosen, grade, ratio = matching[0]
    return chosen, f"{chosen.source} match {grade} ({ratio:.2f})"


# --------------------------------------------------------------- resolving to a file

#: Video containers worth downloading, best first. MP4 before anything else because it
#: is the one every downstream stage already handles without a transcode.
_MEDIA_ORDER = (".mp4", ".m4v", ".mov", ".webm", ".mkv", ".ogv")


def _rank(name: str) -> int:
    lowered = name.lower()
    for index, suffix in enumerate(_MEDIA_ORDER):
        if lowered.endswith(suffix):
            return index
    return len(_MEDIA_ORDER)


async def resolve_media_url(clip: FootageClip) -> str:
    """Turn a search result into something that can actually be downloaded.

    Two of the four sources do not return a media file, and this is why the keyless half
    of the free lane could not serve a single beat:

    * Internet Archive's `url` is `archive.org/download/{id}` — a **directory listing**.
    * NASA's is the `href` of the item's `collection.json` — a **manifest** of assets.

    Neither feeds `vision.acquire`: its direct path matches on a media suffix and refuses
    them, and its yt-dlp path accepts any http URL and then fails on one. So a channel
    with no Pexels or Pixabay key got nothing free, from sources that need no key at all.

    One extra request per *chosen* clip, never per candidate. A search returns eight and
    at most one is used, so resolving during the search would be eight manifest fetches
    to answer a question about one.

    Returns the original URL unchanged for sources that already give a file, and raises
    nothing: a resolution that fails returns "" and the caller leaves the beat paid.
    """
    if clip.source == "internet_archive":
        return await _resolve_archive(clip)
    if clip.source == "nasa":
        return await _resolve_nasa(clip)
    return clip.url


async def _resolve_archive(clip: FootageClip) -> str:
    """The largest usable video file inside an Archive item.

    Largest rather than first: Archive keeps derivatives beside the original — a 240p
    MPEG-4 next to the source — and the small one sorts first as often as not. The
    original is what a 1080p render wants.
    """
    identifier = (clip.landing_url or clip.url).rstrip("/").rsplit("/", 1)[-1]
    if not identifier:
        return ""
    try:
        payload = await _json(f"https://archive.org/metadata/{identifier}", {},
                              label="Internet Archive item")
    except (FootageError, ProviderTimeout):
        return ""

    files = [one for one in (payload.get("files") or []) if isinstance(one, dict)]
    usable = [one for one in files if _rank(str(one.get("name") or "")) < len(_MEDIA_ORDER)]
    if not usable:
        return ""
    usable.sort(key=lambda one: (_rank(str(one.get("name"))), -_as_int(one.get("size"))))
    return f"https://archive.org/download/{identifier}/{usable[0]['name']}"


async def _resolve_nasa(clip: FootageClip) -> str:
    """The largest rendition listed in a NASA item's asset manifest.

    The manifest is a flat array of URLs — original, several transcodes, a thumbnail and
    the caption files — with no sizes, so the choice is made on the filename. `~orig`
    marks the source rendition and is preferred; otherwise the highest numbered rendition
    wins, because NASA names them by height (`~1080.mp4`, `~720.mp4`).
    """
    if not clip.url:
        return ""
    try:
        async with _client() as client:
            response = await client.get(clip.url)
            response.raise_for_status()
            assets = response.json()
    except (httpx.HTTPError, ValueError):
        return ""
    if not isinstance(assets, list):
        return ""

    videos = [str(one) for one in assets
              if isinstance(one, str) and _rank(one.split("?")[0]) < len(_MEDIA_ORDER)]
    if not videos:
        return ""

    def quality(url: str) -> tuple[int, int]:
        name = url.lower()
        if "~orig" in name:
            return (0, 0)
        digits = "".join(ch for ch in name.rsplit("~", 1)[-1] if ch.isdigit())
        return (1, -int(digits or 0))

    videos.sort(key=quality)
    return videos[0]


def _as_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
