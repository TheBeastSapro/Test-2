"""Fandom wikis, read as structure rather than as prose.

Why this exists, measured rather than assumed. The reference channel this was built
against does not generate the thing its videos are about — it fetches it. Every segment
is one creature's fandom wiki page: the page's image is the shot, its infobox is the
on-screen stat card, and its `Appearance` / `Behaviour` / `How to Survive` sections are
the three beats of the narration, in that order. `How to Survive` is a wiki heading, not
a scriptwriting invention.

That is not a quirk of one channel. It is how the whole canon-explainer genre works, and
it is why generation is the wrong tool for it: these audiences know what the entity looks
like and correct the video when it is wrong. A generated depiction of a named creature is
not a stylistic choice, it is an error the comments will find. The art has to be *the*
art.

**What this module deliberately does not do.** It does not decide whether an image may be
used. Fandom's site content is CC-BY-SA under their terms, but an image uploaded to a
fandom wiki is frequently the original artist's copyright, hosted under fair use or by
permission, and the API's `extmetadata` is usually empty on these wikis. So every asset
carries its page, its file page and whatever licence fields did come back, and the
decision is left to a caller that can see them. Guessing the permissive answer here would
be the expensive kind of wrong.

**Why the MediaWiki API and not the HTML.** The API is documented, keyless, stable,
returns the infobox as parseable wikitext rather than as a rendered table, and gives the
canonical file URL for an image without scraping a CDN path. Scraping fandom's HTML gets
you an anti-bot page and a layout that changes.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import httpx

log = logging.getLogger("forgecast.research.fandom")

#: Fandom's per-wiki API endpoint. `{wiki}` is the subdomain — the part before
#: `.fandom.com` — which is what a wiki's URL already shows you.
API = "https://{wiki}.fandom.com/api.php"

#: Politeness. Fandom serves these openly and the whole point of this module is to be a
#: good citizen of somebody else's wiki, so requests identify themselves and there is a
#: contact route in the string. Wikimedia 403s a browser-shaped agent and Fandom may
#: follow; either way, impersonating a browser to read a public API is the wrong default.
USER_AGENT = "Forgecast/1.0 (local video studio; +https://github.com/TheBeastSapro)"

#: A generous ceiling on how much wikitext to parse. Long pages are lore dumps and the
#: sections this reads are near the top; a page past this is not a creature stub.
MAX_WIKITEXT = 120_000

#: Section headings that carry a segment beat, in the order a script uses them, mapped
#: to the role they play. Matched case-insensitively against `== Heading ==`.
#:
#: The aliases are not guesses — they are the headings these wikis actually use for the
#: same thing. A wiki that says "Description" means what another says with "Appearance",
#: and a script that only understood one word would come back empty on half the canon.
BEAT_SECTIONS: dict[str, tuple[str, ...]] = {
    "appearance": ("appearance", "description", "physical description", "biology",
                   "anatomy", "physiology"),
    "behaviour": ("behaviour", "behavior", "abilities", "encounters", "sightings",
                  "history", "background", "lore"),
    "survival": ("how to survive", "survival", "how to avoid", "countermeasures",
                 "containment", "special containment procedures", "defence", "defense"),
}

#: Infobox keys worth putting on screen, and what to call them. A creature page's infobox
#: is where the stat card comes from — the reference's green/yellow height and weight
#: overlay is these two fields and nothing else.
STAT_KEYS: dict[str, tuple[str, ...]] = {
    "height": ("height", "height_size", "length", "size", "tall"),
    "weight": ("weight", "mass"),
    "species": ("species", "type", "classification", "class", "object class"),
    "status": ("status", "hazardtype", "threat", "danger"),
}


@dataclass
class Entity:
    """One wiki page, reduced to the parts a video is made of."""

    title: str
    wiki: str
    url: str
    #: The page's lead image, as a direct file URL. Empty when the page has none — which
    #: is the case worth handling, not an error: a stub with no art cannot be a segment.
    image_url: str = ""
    image_name: str = ""
    image_width: int = 0
    image_height: int = 0
    #: The file's description page. Where a human goes to check the rights, so it travels
    #: with the asset rather than being reconstructed later.
    image_page: str = ""
    #: Whatever licence fields the API returned. Usually empty on fandom wikis, and an
    #: empty dict means "not stated", never "unrestricted".
    image_licence: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    beats: dict = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        """Whether this page can carry a segment.

        Art and at least one beat. A page with stats and no prose is a table, and a page
        with prose and no art would have to be generated — which is the thing this module
        exists to avoid.
        """
        return bool(self.image_url) and bool(self.beats)

    def as_dict(self) -> dict:
        return {
            "title": self.title, "wiki": self.wiki, "url": self.url,
            "image_url": self.image_url, "image_name": self.image_name,
            "image_page": self.image_page, "image_licence": self.image_licence,
            "image_size": [self.image_width, self.image_height],
            "stats": dict(self.stats), "beats": dict(self.beats),
            "usable": self.usable,
        }

    def attribution(self) -> str:
        """One line naming where this came from, for the run's credits file.

        Written even when the licence is unknown, because "we do not know" is exactly the
        state a human needs to see. An asset with no attribution line is one nobody can
        check later.
        """
        licence = self.image_licence.get("LicenseShortName") or "licence not stated"
        return (f"{self.title} — art from [{self.image_name or 'file'}]({self.image_page}), "
                f"page [{self.title}]({self.url}) on {self.wiki}.fandom.com ({licence})")


def _client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout, follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )


def _strip(text: str) -> str:
    """Wikitext to something narratable.

    Deliberately small. The goal is not a wikitext parser — it is to hand a writer clean
    sentences, and the markup that actually appears in a creature page's prose is links,
    bold/italic quotes, refs and templates. Anything cleverer is a dependency and a new
    class of bug for a job three regexes do.
    """
    text = re.sub(r"<ref[^>]*/>", "", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.S)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    # `[[target|shown]]` keeps what a reader sees; `[[target]]` keeps the target.
    text = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    # Numbered survival steps arrive as `#one per line`; they read as a list, not prose.
    text = re.sub(r"^[#*]+\s*", "", text, flags=re.M)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _templates(wikitext: str):
    """Every top-level `{{...}}` block, in order, as raw bodies."""
    index = 0
    limit = min(len(wikitext), MAX_WIKITEXT)
    while index < limit:
        start = wikitext.find("{{", index)
        if start == -1:
            return
        depth = 0
        for cursor in range(start, limit):
            if wikitext.startswith("{{", cursor):
                depth += 1
            elif wikitext.startswith("}}", cursor):
                depth -= 1
                if depth == 0:
                    yield wikitext[start + 2:cursor]
                    index = cursor + 2
                    break
        else:
            return


def parse_infobox(wikitext: str) -> dict:
    """The page's infobox, as a dict.

    Not simply the first `{{...}}`. Wikis put maintenance banners above the infobox —
    `{{ToBeRedone}}{{Cryptid-Infobox|...}}` is real, and taking the first block returned
    an empty dict for every page that had been flagged for cleanup. So: prefer a template
    whose *name* says infobox, and otherwise take the first one that actually carries
    fields. A banner has none, which is what makes it distinguishable without a list of
    banner names to keep up to date.

    Fields are hand-parsed on nesting depth rather than split on `|`, because infobox
    values contain links and templates carrying their own pipes —
    `{{Character|height=[[A|B]]}}` splits into nonsense on a naive split, and that is
    exactly the field the stat card needs.
    """
    best: dict[str, str] = {}
    for body in _templates(wikitext):
        fields = _template_fields(body)
        if not fields:
            continue
        name = body.split("|", 1)[0].strip().lower()
        if "infobox" in name:
            return fields
        if not best:
            best = fields
    return best


def _template_fields(body: str) -> dict:
    fields: dict[str, str] = {}
    depth = 0
    piece = ""
    for char in body:
        if char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
        if char == "|" and depth <= 0:
            key, _, value = piece.partition("=")
            if value:
                fields[key.strip().lower()] = _strip(value).strip()
            piece = ""
            continue
        piece += char
    key, _, value = piece.partition("=")
    if value:
        fields[key.strip().lower()] = _strip(value).strip()
    return fields


def heading_key(raw: str) -> str:
    """A heading reduced to the words in it, lowercased.

    Headings carry markup, and on some wikis they carry nothing else. The Doors wiki
    writes `== {{icons|overview}} Appearance ==` and `== [[The Mines]] ==`; keyed raw,
    those become `{{icons|overview}} appearance`, which matches no alias in
    `BEAT_SECTIONS` and never will. That page is 76,000 characters of exactly the
    sections this module wants and it read as zero beats — not a wiki this could not
    handle, a wiki it silently declined to.

    So the same stripping the body gets, plus a leading-punctuation trim for the
    bullet and icon glyphs that survive it. Found by reading the headings two live
    wikis actually return rather than the ones the fixtures were written from.
    """
    return re.sub(r"^[\W_]+", "", _strip(raw).replace("\n", " ")).strip().lower()


def parse_sections(wikitext: str) -> dict:
    """`== Heading ==` blocks, keyed by the heading's words, lowercased.

    A section runs to the next heading *at its own level or shallower*, so it carries
    its subsections. Stopping at the first `===` instead cost most of the prose on any
    wiki that breaks a section down: the Doors page's `Behaviour` is one paragraph
    followed by a subsection per area of the game, and reading only to the first
    subheading returned the paragraph and left the behaviour on the floor.

    First occurrence wins. Two headings can normalise to one key — that page carries
    four separate `Appearance` headings, one per form — and the one written first is
    the one the page leads with.
    """
    out: dict[str, str] = {}
    matches = list(re.finditer(r"^(={2,6})\s*(.+?)\s*={2,6}\s*$", wikitext, flags=re.M))
    for position, match in enumerate(matches):
        depth = len(match.group(1))
        end = len(wikitext)
        for later in matches[position + 1:]:
            if len(later.group(1)) <= depth:
                end = later.start()
                break
        body = _strip(wikitext[match.end():end])
        key = heading_key(match.group(2))
        if body and key and key not in out:
            out[key] = body
    return out


def beats_from(sections: dict) -> dict:
    """Sections mapped onto the three beats a segment is made of.

    First alias wins, so a page with both `Appearance` and `Description` uses the one the
    genre leads with rather than whichever the dict happened to iterate to.
    """
    beats: dict[str, str] = {}
    for beat, aliases in BEAT_SECTIONS.items():
        for alias in aliases:
            if alias in sections:
                beats[beat] = sections[alias]
                break
        if beat in beats:
            continue
        # Then headings that *begin* with an alias. Wikis qualify their headings —
        # "Behavior and Origin", "Appearance and Anatomy", "How to Survive an Encounter"
        # — and exact matching skipped every one of them. This was hidden on the live
        # page that prompted it, which happened to also carry an "Abilities" section and
        # so filled the beat by a different alias; the fixture is what showed the
        # heading itself had never matched.
        for alias in aliases:
            match = next((head for head in sections if head.startswith(alias)), "")
            if match:
                beats[beat] = sections[match]
                break
    return beats


def stats_from(infobox: dict) -> dict:
    """Infobox fields mapped onto the stat card's rows, first alias wins.

    Exact key first, then a prefix match. Infobox templates are per-wiki and their field
    names drift around the same idea — one wiki says `height`, the next says
    `height_size`, a third says `height_ft`. An exact-only lookup found the height on the
    wiki it was written against and nothing on the next one, which is the failure this
    whole module is most prone to: working on one sample and looking finished.
    """
    stats: dict[str, str] = {}
    for label, aliases in STAT_KEYS.items():
        for alias in aliases:
            if infobox.get(alias):
                stats[label] = infobox[alias]
                break
        if label in stats:
            continue
        for alias in aliases:
            match = next((key for key in sorted(infobox)
                          if key.startswith(alias) and infobox[key]), "")
            if match:
                stats[label] = infobox[match]
                break
    return stats


def image_name_from(infobox: dict) -> str:
    """The infobox's lead image filename, or "".

    Any `image`-ish key, in the order the wiki wrote them, rather than a fixed list.
    `image`, `image1`, `Image`, `image_name` and `img` all appear in the wild, and a
    hard-coded tuple missed a page whose only image key was one nobody had seen yet.

    Values that are not a filename are skipped rather than passed on: a caption, a
    gallery block or a bare URL all end up in these fields, and asking the file API about
    a sentence returns nothing while looking like the page had no art.
    """
    for key in sorted(infobox):
        if not (key.startswith("image") or key.startswith("img")
                or key.startswith("picture") or key.startswith("file")):
            continue
        value = (infobox[key] or "").strip()
        if not value or "\n" in value or len(value) > 200:
            continue
        if value.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            return value
    return ""


# --------------------------------------------------------------------------- fetching


async def _api(wiki: str, params: dict, *, timeout: float) -> dict:
    async with _client(timeout) as client:
        response = await client.get(API.format(wiki=wiki),
                                    params={**params, "format": "json"})
        response.raise_for_status()
        return response.json()


async def search(wiki: str, query: str, *, limit: int = 5,
                 timeout: float = 20.0) -> list[str]:
    """Page titles on `wiki` matching `query`, best first.

    Searched rather than guessed at from the name. Canon pages are titled the way the
    fandom titles them — "Unnamed Mushroom Creature", "Driving Down The Highway" — and a
    title built by capitalising the words a script used misses most of them.
    """
    try:
        data = await _api(wiki, {"action": "query", "list": "search",
                                 "srsearch": query, "srlimit": limit}, timeout=timeout)
    except (httpx.HTTPError, ValueError) as exc:
        log.info("fandom search failed on %s for %r: %s", wiki, query, exc)
        return []
    return [row["title"] for row in (data.get("query", {}).get("search") or [])]


async def _image(wiki: str, name: str, *, timeout: float) -> dict:
    """The canonical URL, size and any licence fields for one file."""
    if not name:
        return {}
    title = name if name.lower().startswith("file:") else f"File:{name}"
    try:
        data = await _api(wiki, {
            "action": "query", "titles": title, "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
        }, timeout=timeout)
    except (httpx.HTTPError, ValueError) as exc:
        log.info("fandom imageinfo failed on %s for %r: %s", wiki, name, exc)
        return {}
    for page in (data.get("query", {}).get("pages") or {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        if info.get("url"):
            return {
                "url": info["url"],
                "page": info.get("descriptionurl", ""),
                "width": int(info.get("width") or 0),
                "height": int(info.get("height") or 0),
                # Kept whole rather than reduced to a verdict. Everything downstream that
                # has to make a rights decision should see what was actually returned,
                # and on these wikis what is usually returned is nothing.
                "licence": {k: v.get("value") for k, v in
                            (info.get("extmetadata") or {}).items()
                            if k in ("LicenseShortName", "License", "UsageTerms",
                                     "Artist", "Credit", "Copyrighted")},
            }
    return {}


async def page(wiki: str, title: str, *, timeout: float = 20.0) -> Entity | None:
    """One page, reduced to art, stats and beats. `None` when it cannot be read.

    Returns an `Entity` even when it is not `usable` — a page with prose and no art is a
    real answer that a caller may want to report ("this one has no picture") rather than
    an absence it has to infer from `None`.
    """
    try:
        data = await _api(wiki, {"action": "parse", "page": title,
                                 "prop": "wikitext"}, timeout=timeout)
    except (httpx.HTTPError, ValueError) as exc:
        log.info("fandom parse failed on %s for %r: %s", wiki, title, exc)
        return None
    if "error" in data:
        return None

    wikitext = (data.get("parse", {}).get("wikitext") or {}).get("*") or ""
    if not wikitext:
        return None
    wikitext = wikitext[:MAX_WIKITEXT]

    infobox = parse_infobox(wikitext)
    resolved = (data.get("parse", {}) or {}).get("title") or title
    entity = Entity(
        title=resolved,
        wiki=wiki,
        url=f"https://{wiki}.fandom.com/wiki/{resolved.replace(' ', '_')}",
        stats=stats_from(infobox),
        beats=beats_from(parse_sections(wikitext)),
    )

    # The infobox names the lead image; that is the one the page is *about*, as opposed
    # to the first file that happens to appear in the body — which on these wikis is
    # often a comparison chart or somebody's fan edit.
    name = image_name_from(infobox)
    if name:
        found = await _image(wiki, name, timeout=timeout)
        if found:
            entity.image_url = found["url"]
            entity.image_name = name
            entity.image_page = found["page"]
            entity.image_width = found["width"]
            entity.image_height = found["height"]
            entity.image_licence = found["licence"]
    return entity


async def lookup(wiki: str, query: str, *, timeout: float = 20.0) -> Entity | None:
    """Read the page by that name, and search only if there is not one.

    The direct read comes first because a page with the asked-for title *is* the answer,
    and searching for it is a worse route to the same thing. Measured, not assumed: the
    Trevor Henderson wiki's own search ranks `Siren Head/Gallery`, `Light head` and
    `Traffic light head` above `Siren Head`, so a search-first lookup returned nothing
    usable for the single most famous entity on that wiki — while `page(wiki, "Siren
    Head")` returns it with artwork and two beats. MediaWiki resolves redirects and
    case on the direct read, so this also catches the near-misses a caller types.
    """
    direct = await page(wiki, query, timeout=timeout)
    if direct is not None and direct.usable:
        return direct

    for title in await search(wiki, query, limit=3, timeout=timeout):
        if direct is not None and title == direct.title:
            continue                    # already read, already rejected
        if not resembles(query, title):
            log.info("fandom search on %s answered %r with %r, which is a different "
                     "subject — refused", wiki, query, title)
            continue
        found = await page(wiki, title, timeout=timeout)
        if found is not None and found.usable:
            return found
    return None


#: Words that carry no identity, so an overlap on one of them is not a match. Short and
#: deliberately not a general stopword list — this is only ever comparing a creature's
#: name against a page title.
NO_IDENTITY = {"the", "a", "an", "and", "or", "of", "in", "on", "at", "for", "with",
               "from", "to", "is", "it", "its"}


def _identity(text: str) -> set[str]:
    """The words in a name that say *which* thing it is."""
    return {word for word in re.findall(r"[a-z0-9]+", str(text or "").lower())
            if len(word) >= 3 and word not in NO_IDENTITY}


def resembles(query: str, title: str) -> bool:
    """Whether a searched-up page is plausibly the thing that was asked for.

    MediaWiki's search answers everything. Asked for `Beat 3` — a placeholder beat name
    out of a brief that never got the creatures written into it — the Doors wiki returns
    `Floor 3`, `Update Logs/Development Logs` and `First Tower Heroes Collab`, and a
    lookup that takes the first usable one builds a canon segment about a crossover
    event nobody mentioned. That is the worst failure this format has: the audience
    polices canon, and a confident page about the wrong subject is not a weak shot, it
    is a lie in the video's own voice.

    So the test is whole-word overlap on the words that carry identity, in either
    direction. Whole-word matters and is not fussiness: `Beat 1` returns `Heartbeat
    Control Minigame`, and on substrings that reads as a match.

    Deliberately generous rather than clever. `seek and figure` keeps `Seek`, a
    subtitle or a disambiguator keeps its page, and a real miss like `Sirenhead` on the
    Doors wiki — which returns `First Tower Heroes Collab` — has nothing in common and
    is refused. Being loose here costs a near-miss that a human would have accepted;
    being tight costs a wrong creature, and only one of those is recoverable.
    """
    asked, offered = _identity(query), _identity(title)
    if not asked:
        # Nothing in the query to check against, so there is no way to tell whether the
        # answer is right. Refusing is the honest end of that.
        return False
    return bool(asked & offered)


# ----------------------------------------------------------------------- the gallery
#
# A page is not one picture. Amber's carries five — the infobox portrait plus four
# scene images from the gallery — and a 62-second segment cut at 2 to 4 seconds a shot
# needs roughly twenty. Holding one image for a whole segment is the difference between
# an edit and a slideshow, and it is what a Ken Burns push on a single still looks like
# no matter how well the push is tuned.
#
# So the reader returns everything the page has and says how big each one is. Which to
# use is an editorial decision, and the ranking below only orders the candidates.

#: Below this on the short edge an image is a badge, an icon or a signature rather than
#: a shot. Measured against the assets these wikis actually carry: the real ones are
#: four figures on at least one edge, and the chrome is a couple of hundred pixels.
MIN_EDGE = 400

#: Filenames that are never a shot, matched case-insensitively as substrings. Wiki
#: chrome travels with every page and would otherwise rank as a candidate.
SKIP_NAMES = ("wiki-wordmark", "favicon", "site-logo", "sitelogo", "wiki.png",
              "placeholder", "spoiler", "stub", "badge", "icon", "logo",
              "under_construction", "userbox")

#: Extensions worth fetching. Animated GIFs are excluded deliberately: they arrive as
#: reaction images and gag material rather than as the subject, and this reader is the
#: subject path.
SHOT_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


@dataclass
class Asset:
    """One image on a page, with enough about it to choose between candidates."""

    name: str
    url: str
    page: str
    width: int = 0
    height: int = 0
    licence: dict = field(default_factory=dict)
    #: Whether the file can carry transparency at all, read from the API rather than
    #: from the pixels. `None` where the API does not say — see `has_alpha`.
    colour_type: str | None = None
    mime: str = ""

    @property
    def pixels(self) -> int:
        return self.width * self.height

    @property
    def has_alpha(self) -> bool:
        """Whether this file could be a cut-out, decided without downloading it.

        MediaWiki hands back a PNG's `colorType` in the same batched `imageinfo` call
        that carries the sizes, and it is decisive in one direction: `truecolour` means
        the file has no alpha channel, so it is certainly not a cut-out. Measured across
        the Doors wiki's whole Figure gallery, fourteen usable files: every PNG reports
        a colour type, and JPEG, GIF and WEBP report none.

        A JPEG cannot carry alpha whatever it says, so that one is answered from the
        mime type. Anything else unmeasured is left as `True` — this filter is here to
        exclude what is provably flat, not to guess about what it cannot see, and
        `layers.shot.is_cutout` still checks the real pixels at render time.

        The remaining gap is stated rather than hidden: `truecolour-alpha` means the
        channel exists, not that it is used. `Figurehide.png` reports it and measures
        0.0% transparent — an opaque screenshot saved as RGBA. Only the download settles
        that one, and the render-time test does.
        """
        if self.colour_type:
            return "alpha" in self.colour_type.lower()
        return "jpeg" not in self.mime.lower()

    @property
    def is_portrait_crop(self) -> bool:
        """Roughly square or taller. A *hint* about how the asset will be used.

        It is not the cut-out test and must not be used as one. Measured across seven
        real assets: Amber's artwork is a 2265x2265 photograph of the creature on a road
        at night, fully opaque, and this returns True for it — so a caller trusting this
        stood a whole scene photograph on a plate and rendered a picture on wallpaper.
        Both shapes are square; only the alpha channel separates them, and this reader
        has the dimensions from the API without downloading a byte.

        So this orders candidates at planning time, and `layers.shot.is_cutout` decides
        at render time from the pixels. The split is deliberate: knowing for certain
        costs a download, and the plan runs before anything is fetched.
        """
        return self.height >= self.width * 0.92

    def as_dict(self) -> dict:
        return {"name": self.name, "url": self.url, "page": self.page,
                "size": [self.width, self.height], "licence": self.licence,
                "portrait": self.is_portrait_crop, "alpha": self.has_alpha}


def _colour_type(metadata) -> str | None:
    """A PNG's colour type out of `imageinfo`'s metadata list, or `None`.

    The list is MediaWiki's generic name/value shape and only PNGs carry this entry, so
    a miss is the ordinary case rather than a fault.
    """
    for entry in metadata or []:
        if isinstance(entry, dict) and entry.get("name") == "colorType":
            return str(entry.get("value") or "") or None
    return None


def _worth_fetching(name: str) -> bool:
    lowered = name.lower()
    if not lowered.endswith(SHOT_EXTENSIONS):
        return False
    return not any(skip in lowered for skip in SKIP_NAMES)


async def images(wiki: str, title: str, *, limit: int = 12,
                 timeout: float = 25.0) -> list[Asset]:
    """Every usable image on a page, largest first.

    Ordered by pixel count because on these wikis the biggest file is reliably the one
    somebody uploaded as artwork and the small ones are crops, thumbnails and chrome.
    That is a heuristic and it is stated as one — it orders candidates, it does not
    pick, and the caller still has to look.

    Sizes come back in one batched `imageinfo` call rather than one per file, because a
    page with a full gallery would otherwise be a dozen round trips against somebody
    else's wiki for information they will hand over in a single request.

    That call also asks for `metadata`, which carries a PNG's colour type and so answers
    whether a file can be a cut-out before anything is downloaded. It costs nothing —
    same request, same round trip — and it is the difference between a shot list built
    on the aspect ratio and one built on the alpha channel.
    """
    try:
        data = await _api(wiki, {"action": "parse", "page": title,
                                 "prop": "images"}, timeout=timeout)
    except (httpx.HTTPError, ValueError) as exc:
        log.info("fandom images failed on %s for %r: %s", wiki, title, exc)
        return []
    if "error" in data:
        return []

    names = [name for name in (data.get("parse", {}).get("images") or [])
             if _worth_fetching(name)][:40]
    if not names:
        return []

    titles = "|".join(f"File:{name}" for name in names)
    try:
        info = await _api(wiki, {
            "action": "query", "titles": titles, "prop": "imageinfo",
            "iiprop": "url|size|mime|metadata|extmetadata",
        }, timeout=timeout)
    except (httpx.HTTPError, ValueError) as exc:
        log.info("fandom imageinfo batch failed on %s: %s", wiki, exc)
        return []

    found: list[Asset] = []
    for page_data in (info.get("query", {}).get("pages") or {}).values():
        detail = (page_data.get("imageinfo") or [{}])[0]
        if not detail.get("url"):
            continue
        width, height = int(detail.get("width") or 0), int(detail.get("height") or 0)
        if min(width, height) < MIN_EDGE:
            continue
        found.append(Asset(
            name=str(page_data.get("title", "")).removeprefix("File:"),
            url=detail["url"], page=detail.get("descriptionurl", ""),
            width=width, height=height,
            colour_type=_colour_type(detail.get("metadata")),
            mime=str(detail.get("mime") or ""),
            licence={k: v.get("value") for k, v in
                     (detail.get("extmetadata") or {}).items()
                     if k in ("LicenseShortName", "License", "UsageTerms", "Artist",
                              "Credit", "Copyrighted")},
        ))

    found.sort(key=lambda asset: asset.pixels, reverse=True)
    return found[:limit]
