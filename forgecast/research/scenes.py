"""Where a named scene is legitimately available, and what that does not license.

The operator says "the scene where the truck flips in The Dark Knight". This answers
where that scene can lawfully be watched, where in the runtime it sits, and what is
actually known about the right to use it. It answers all three or it says which one it
could not answer — it never fills a gap in.

## Why this returns coordinates rather than a file

The tempting shape is a thing that goes and gets the scene. This app already has four
things that go and get: `vision.acquire` pulls a platform URL down with yt-dlp,
`providers.search.fetch` pulls a page, `research.keyless` reads a listing without a key,
and `providers.sfx.fetch_named_sound` pulls a named cue. A fifth would not be a fifth
capability — it would be a fourth copy of the same subprocess call, with its own timeout,
its own idea of what a proxy is, and its own way of failing at three in the morning.

So this returns a URL, an in, and an out. `vision.acquire.acquire` already takes the URL
and `providers.footage.strip_audio` already takes the timecode; `handoff` hands them
exactly what they each expect, so nothing downstream re-derives a trim.

Discovery reuses the same reach the rest of the desk uses: `research.keyless`'s subprocess
seam for anything on YouTube, and whatever `providers.search.provider_for` returned for
the press sites. The seam matters beyond tidiness — the test suite refuses a real yt-dlp
run through `keyless._run`, so a locator built on it cannot quietly start calling YouTube
from a test, which is precisely how the last one would have gone wrong.

## "Licensed" answers two questions and this module only gets one of them

A Movieclips upload is licensed. Fandango owns the channel, the studios licensed the
clips to it, and it is the right place to watch the scene. It does not follow that the
scene may be re-cut into somebody's video. The same word covers both facts and they come
apart hard:

    is this a lawful place to find the scene?     every source here answers yes
    may this footage be cut into my video?        none of them answer that

Which is why `licence` here is a statement about the *upload* — `licensed_distribution`,
`studio_official`, `press_kit` — and `commercially_safe` is false for every one of them.
Those strings are deliberately not licences and deliberately not in
`footage.COMMERCIAL_LICENCES`, which is imported rather than restated: two answers to
"may this be used" is how the two drift, and the first thing to drift would be the one
that says yes.

What the app owes the operator in exchange for not deciding is the same thing
`providers.footage`'s operator lane owes them — the position in words, on the result,
where they will read it. Publish is never blocked from here. Whether a two-second cut of
someone else's film is fair dealing where they live is their call and their lawyer's, and
a filter written here cannot make it.

## The sources are an allow-list of identities, and what is not on it

Fandango's Movieclips, the studios' own channels, the studio press and EPK sites, and
YouTube's Creative Commons filter. Nothing else, and specifically none of the streaming-rip
sites, release indexes or media-centre add-ons that a plain web search for
"the dark knight truck flip" returns above every legitimate result. There is no scraper
here for one and there will not be one.

The allow-list is the mechanism; `REFUSED_MARKERS` is a check on the allow-list rather
than a filter doing real work. Every candidate from every lane passes it, because the web
search lane returns whatever the index holds and because the day somebody adds a domain
here in a hurry is the day it is worth having a second gate that says no.

Channels are matched by *identity* — a handle or a channel id — and not by display name.
"Warner Bros. Pictures HD" is not Warner Bros. Pictures, and a display-name match is
exactly the door a re-uploader walks through. An exact name match is accepted only when
the entry carries no identity at all, and that result says so on itself: YouTube permits
duplicate display names, so a name is a presumption and a handle is a fact.

## The Creative Commons filter is not asked about somebody else's film

YouTube offers exactly one Creative Commons option and the uploader ticks it themselves.
On a stranger's re-upload of a studio film that tick is not a licence, it is a mistake,
and honouring it would be this app laundering a rip through a checkbox. So the CC lane is
asked only when the description names no title — "the Falcon 9 booster landing on the
drone ship" is a scene somebody may genuinely have shot and licensed; "the truck flip in
The Dark Knight" is not.

## Confidence is about identification, not about rights

Two axes, never collapsed. Confidence says how sure the app is that this result is the
scene that was asked for; licence says what is known about using it. A high-confidence
match to a clip nobody may reuse is the ordinary case, and rolling the rights into the
score would hide it. Rank is by confidence, because an operator asking where a scene is
does not want a wrong scene handed to them for being better licensed.

## What a timecode can honestly be

An upload short enough to *be* the scene has a window: nought to its runtime. That is the
clip's own boundary and not a measured cut — a Movieclips upload carries a channel ident
on the tail, and trimming a guess off it would be inventing a number to look precise.

An upload long enough to *contain* the scene has no window this module can produce, so it
returns none and says why. The one exception is a chapter list: when the uploader has
published chapter marks and one of them names what the operator described, that is a real
in and out, read from metadata YouTube already publishes.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from urllib.parse import quote_plus, urlparse

from ..providers.footage import ATTRIBUTION_REQUIRED, COMMERCIAL_LICENCES
from ..providers.search import SearchProvider, provider_for
from . import keyless

log = logging.getLogger("forgecast.research.scenes")

# ------------------------------------------------------------------- the source list

MOVIECLIPS = "movieclips"
STUDIO_CHANNEL = "studio_channel"
PRESS_KIT = "press_kit"
YOUTUBE_CC = "youtube_cc"

# What each lane establishes about the *upload*. None of these is a reuse licence and
# none of them is in `footage.COMMERCIAL_LICENCES`, which is what makes
# `commercially_safe` false for all of them without a second rule saying so.
LICENCE_DISTRIBUTION = "licensed_distribution"   # Fandango's Movieclips: studio-licensed
LICENCE_STUDIO = "studio_official"               # the rights holder's own channel
LICENCE_PRESS = "press_kit"                      # published for editorial coverage
LICENCE_CC_BY = "by"                             # the uploader's own CC mark
LICENCE_NONE = "not_established"

# Channels whose uploads are lawful, keyed by identity. Handles rather than display
# names — see the module docstring. A handle that has changed costs a missed result,
# which is the direction to be wrong in; a display name that matches an impostor costs
# a rip presented as a licensed clip, which is not.
LICENSED_CHANNELS: dict[str, tuple[str, str]] = {
    "@movieclips": (MOVIECLIPS, "Movieclips"),
    "@movieclipstrailers": (MOVIECLIPS, "Movieclips Trailers"),
    "@wbpictures": (STUDIO_CHANNEL, "Warner Bros. Pictures"),
    "@universalpictures": (STUDIO_CHANNEL, "Universal Pictures"),
    "@sonypictures": (STUDIO_CHANNEL, "Sony Pictures Entertainment"),
    "@paramountpictures": (STUDIO_CHANNEL, "Paramount Pictures"),
    "@20thcenturystudios": (STUDIO_CHANNEL, "20th Century Studios"),
    "@disneystudios": (STUDIO_CHANNEL, "Walt Disney Studios"),
    "@marvel": (STUDIO_CHANNEL, "Marvel Entertainment"),
    "@a24": (STUDIO_CHANNEL, "A24"),
    "@netflix": (STUDIO_CHANNEL, "Netflix"),
    "@lionsgatemovies": (STUDIO_CHANNEL, "Lionsgate Movies"),
    "@focusfeatures": (STUDIO_CHANNEL, "Focus Features"),
    "@sonypicturesclassics": (STUDIO_CHANNEL, "Sony Pictures Classics"),
}

# The same list read the other way, for the one case where an entry arrives with no
# handle and no channel id. Presumptive, not identity — a match here is flagged.
CANONICAL_NAMES: dict[str, str] = {
    label.lower(): identity for identity, (_, label) in LICENSED_CHANNELS.items()
}

# Studio press and EPK sites. Press material is published for editorial coverage under
# terms the studio sets, and this app has not read them — so the lane finds the page and
# stops there, rather than deciding what the page permits.
PRESS_DOMAINS: dict[str, str] = {
    "media.netflix.com": "Netflix Media Center",
    "about.netflix.com": "Netflix newsroom",
    "mediapass.warnerbros.com": "WB Media Pass",
    "press.wbd.com": "Warner Bros. Discovery press",
    "dmedmedia.disney.com": "Disney DMED Media",
    "press.disneyplus.com": "Disney+ press",
    "nbcumv.com": "NBCUniversal press",
    "paramountpressexpress.com": "Paramount Press Express",
}

# Hosts and add-ons this app will not reach, whatever a search index ranks first. This
# is a check on the allow-list above rather than the thing keeping them out — the
# allow-list already does that — and it is written down so the decision is visible in
# the source instead of being an absence somebody fills in later by accident.
REFUSED_MARKERS: tuple[str, ...] = (
    "hdhub", "123movies", "fmovies", "putlocker", "soap2day", "gomovies",
    "solarmovie", "primewire", "watchseries", "movierulz", "tamilrockers",
    "yts.", "1337x", "rarbg", "torrent", "kickass",
    "kodi", "exodus-", "seren-", "openload", "streamtape", "vidcloud",
)

# Above this an upload contains a scene rather than being one. A scene runs a minute or
# two; a quarter of an hour is a featurette, a compilation, or the film itself, and
# reporting 0-to-runtime as its in and out would be a guess wearing a timecode's clothes.
CLIP_SECONDS = 900.0

# How many long uploads are worth a second yt-dlp call to read chapter marks. Capped
# because each one is a network round trip and the answer is usually "no chapters".
CHAPTER_LOOKUPS = 3

# Where the confidence labels fall. Named because the label is what an operator reads
# and the float is what the ranking uses, and they must not disagree.
HIGH_CONFIDENCE = 0.65
MEDIUM_CONFIDENCE = 0.40

_STOPWORDS = frozenset({
    "the", "a", "an", "of", "in", "on", "at", "to", "from", "with", "and", "or",
    "scene", "clip", "moment", "bit", "part", "where", "when", "that", "which",
    "movie", "film", "is", "it", "its", "his", "her", "their", "he", "she", "they",
})


class SceneLookupError(RuntimeError):
    """A lane failed in a way the operator can act on. `locate` logs these and goes on."""


# ------------------------------------------------------------------------- the result


@dataclass
class SceneMatch:
    """One place a scene is legitimately available, and what that is worth.

    Shares its vocabulary with `providers.footage.FootageClip` on purpose — `licence`,
    `commercially_safe`, `flag_reason`, `credit_line` mean the same things here — so a
    run that mixes a located scene with licensed footage does not need two ideas of what
    a licence is.
    """

    url: str
    title: str
    source: str
    licence: str
    channel: str = ""
    film: str = ""
    # The window inside the upload, in seconds. `None` where this module could not
    # determine it — never 0.0 standing in for "unknown", because a caller reading 0.0
    # as a start would trim from the wrong place and never find out.
    start_seconds: float | None = None
    end_seconds: float | None = None
    duration_seconds: float = 0.0
    # How sure the app is that this is the scene that was asked for. Nothing to do with
    # the licence — see the module docstring.
    confidence: float = 0.0
    confidence_reason: str = ""
    # Why this needs a human's eye, in words on the result rather than a boolean they
    # have to interpret. Empty only when there is genuinely nothing to say.
    flag_reason: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def commercially_safe(self) -> bool:
        """Whether this app is willing to use the scene without a human deciding.

        False for every studio lane, and that is the point of the module rather than a
        limitation of it. Movieclips is a licensed distributor: the *upload* is lawful.
        The copyright in the film is the studio's, this app did not obtain a reuse
        licence, and a property named `commercially_safe` returning true on the strength
        of "it was on an official channel" is the quiet claim this codebase keeps
        removing.
        """
        return self.licence.lower() in COMMERCIAL_LICENCES

    @property
    def has_window(self) -> bool:
        """Whether an in *and* an out were determined. Half a window is not a window."""
        return self.start_seconds is not None and self.end_seconds is not None

    @property
    def trim_seconds(self) -> float:
        """Length of the window, or 0.0 — which `footage.strip_audio` reads as no trim."""
        if not self.has_window:
            return 0.0
        return max(0.0, float(self.end_seconds) - float(self.start_seconds))

    @property
    def timecode(self) -> str:
        """`HH:MM:SS.mmm-HH:MM:SS.mmm`, or empty when there is no window to print.

        Empty rather than `00:00:00.000-00:00:00.000`, because a zero-length window
        printed in a UI reads as a measurement that came out zero.
        """
        if not self.has_window:
            return ""
        return f"{format_timecode(self.start_seconds)}-{format_timecode(self.end_seconds)}"

    @property
    def confidence_label(self) -> str:
        if self.confidence >= HIGH_CONFIDENCE:
            return "high"
        return "medium" if self.confidence >= MEDIUM_CONFIDENCE else "low"

    @property
    def low_confidence(self) -> bool:
        return self.confidence_label == "low"

    @property
    def needs_attribution(self) -> bool:
        """Anything not cleared for reuse gets credited if it is used anyway."""
        return self.licence.lower() in ATTRIBUTION_REQUIRED or not self.commercially_safe

    def credit_line(self) -> str:
        """One line for `attribution.md`, never claiming a licence this app did not get."""
        who = self.channel or "unknown channel"
        if not self.commercially_safe:
            return (f"{self.title or 'untitled'} — {who} — {self.url} "
                    f"(located by Forgecast; reuse licence not established here)")
        licence = self.licence.upper() if self.licence else "licence not established"
        return f"{self.title or 'untitled'} — {who} ({licence}) {self.url}"

    def handoff(self) -> dict:
        """What the existing fetch path needs, in the argument names it already uses.

        `vision.acquire.acquire(reference, workdir)` takes the URL and
        `providers.footage.strip_audio(src, out, start=, seconds=)` takes the window, so
        this is the whole handover and there is no fetcher here. `seconds` is 0.0 when no
        window was determined, which those functions already read as "do not trim".
        """
        return {
            "reference": self.url,
            "start": float(self.start_seconds or 0.0),
            "seconds": self.trim_seconds,
            "note": self.flag_reason,
        }

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "channel": self.channel,
            "film": self.film,
            "source": self.source,
            "licence": self.licence,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "timecode": self.timecode,
            "duration_seconds": round(self.duration_seconds, 3),
            "confidence": round(self.confidence, 3),
            "confidence_label": self.confidence_label,
            "confidence_reason": self.confidence_reason,
            "commercially_safe": self.commercially_safe,
            "needs_attribution": self.needs_attribution,
            "flag_reason": self.flag_reason,
            "notes": list(self.notes),
        }


def format_timecode(seconds: float | None) -> str:
    """`HH:MM:SS.mmm` — the form ffmpeg's `-ss` takes, so nothing reformats it later."""
    total = max(0.0, float(seconds or 0.0))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{secs:06.3f}"


# ------------------------------------------------------------------ reading the ask


def _stem(word: str) -> str:
    """Crude suffix strip, because the operator writes "flips" and the title says "Flip".

    Not a stemmer and not trying to be. Without it the strongest signal in a description
    — the verb naming the action — misses the title that contains it, and every result
    scores as though only the film name matched.
    """
    for suffix in ("ing", "ies", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return word[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return word


def _words(text: str) -> list[str]:
    return [word for word in re.findall(r"[a-z0-9']+", (text or "").lower()) if word]


def _content_words(text: str) -> set[str]:
    return {_stem(word) for word in _words(text) if word not in _STOPWORDS}


_QUOTED_TITLE = re.compile(r"[\"“']([^\"”']{2,60})[\"”']")
# The last one wins: "the shootout in the street in Heat" names a film once, at the end.
_TITLE_MARKER = re.compile(r"\s+(?:in|from|out of)\s+", re.I)
_TRAILING_YEAR = re.compile(r"\s*\(?(19|20)\d{2}\)?\s*$")
# How an operator opens the sentence, and none of it identifies anything. Stripped
# because the action goes into a YouTube query verbatim, and "the scene where the truck
# flips scene" is a worse query than "the truck flips scene" against titles that all
# carry the word already.
_LEAD_FILLER = re.compile(
    r"^\s*(?:the\s+)?(?:scene|clip|shot|moment|bit|part)\s+"
    r"(?:where|when|in which|that|with|of)\s+", re.I
)


def read_description(description: str) -> tuple[str, str]:
    """`(film, action)` from what the operator typed. Either may be empty.

    Two things are wanted out of one sentence: the work, which decides whether the
    Creative Commons lane may be asked at all, and the action, which is what actually
    identifies the scene inside it.

    A quoted title wins outright. Otherwise the last "in"/"from" splits the sentence, and
    the tail is only accepted as a title if it is short and carries a capital — because
    "the truck flips in slow motion" names no film, and reading "Slow Motion" as one
    would silence the CC lane on exactly the descriptions it exists for.

    A line typed entirely in lower case gives that test nothing to read, so the tie goes
    to "this is a title". The two ways of being wrong do not cost the same: mistaking a
    phrase for a film silences a lane, while mistaking a film for a phrase asks the
    Creative Commons filter about somebody else's film, which is the single thing this
    module exists to not do.
    """
    text = (description or "").strip()
    if not text:
        return "", ""

    quoted = _QUOTED_TITLE.search(text)
    if quoted:
        film = quoted.group(1).strip()
        action = (text[: quoted.start()] + " " + text[quoted.end():]).strip()
        return _TRAILING_YEAR.sub("", film).strip(), _LEAD_FILLER.sub("", action).strip()

    markers = list(_TITLE_MARKER.finditer(text))
    if not markers:
        return "", _LEAD_FILLER.sub("", text).strip()

    last = markers[-1]
    candidate = _TRAILING_YEAR.sub("", text[last.end():]).strip(" .,-—")
    action = _LEAD_FILLER.sub("", text[: last.start()]).strip()

    plausible = bool(candidate) and len(_words(candidate)) <= 6
    if plausible and any(char.isupper() for char in text):
        plausible = any(word[:1].isupper() for word in candidate.split())
    if not plausible:
        return "", _LEAD_FILLER.sub("", text).strip()
    return candidate, action


# -------------------------------------------------------------------- the URL guard


def _refused(url: str) -> bool:
    """Whether this is a piracy-class source. Checked on every candidate, every lane."""
    parsed = urlparse((url or "").lower())
    if parsed.scheme in ("magnet", "torrent"):
        return True
    # Host and path, never the query string. A YouTube video id is eleven arbitrary
    # characters and can contain any of these markers by chance, so matching the whole
    # URL would drop legitimate results at random and look like the search being empty.
    return any(marker in parsed.netloc + parsed.path for marker in REFUSED_MARKERS)


def _permitted_page(url: str) -> str:
    """The press site's name if this URL is on one, otherwise empty.

    An allow-list and not a heuristic. A web search for a scene returns streaming-rip
    sites above every legitimate result, so anything that is not a named studio press
    host is dropped without being looked at.
    """
    if _refused(url):
        log.info("scene locator refused a piracy-class result: %s", urlparse(url).netloc)
        return ""
    host = urlparse(url).netloc.lower().removeprefix("www.")
    for domain, label in PRESS_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return label
    return ""


def _identities(entry: dict) -> list[str]:
    """Every identity string a yt-dlp entry carries, normalised.

    Handles and channel ids only. The display name is deliberately not in here — see the
    module docstring — and `_permitted_channel` reaches for it separately, once, and says
    so on the result when it does.
    """
    found: list[str] = []
    for key in ("uploader_id", "channel_id", "uploader_url", "channel_url"):
        value = str(entry.get(key) or "").strip()
        if not value:
            continue
        if value.startswith("@"):
            found.append(value.lower())
            continue
        handle = re.search(r"/(@[\w.-]+)", value)
        if handle:
            found.append(handle.group(1).lower())
        elif value.startswith("UC"):
            found.append(value)
        else:
            tail = value.rstrip("/").rsplit("/", 1)[-1]
            if tail.startswith("UC"):
                found.append(tail)
    return found


def _permitted_channel(entry: dict) -> tuple[str, str, str]:
    """`(source, channel label, caveat)` for an allow-listed channel, else empties.

    The caveat is non-empty when the only thing that matched was a display name. YouTube
    permits duplicate display names, so that is a presumption rather than an identity,
    and a result carrying it says so instead of being quietly treated as the real one.

    The name is only ever consulted when the entry carries no identity at all — an older
    yt-dlp, or a listing shape that dropped the field. An entry that *has* a handle and
    whose handle is not on the list has already answered the question, and letting a
    display name overturn that is how an impostor calling itself "Warner Bros. Pictures"
    gets in through the one door built for a missing field.
    """
    identities = _identities(entry)
    for identity in identities:
        if identity in LICENSED_CHANNELS:
            source, label = LICENSED_CHANNELS[identity]
            return source, label, ""
    if identities:
        return "", "", ""

    name = str(entry.get("channel") or entry.get("uploader") or "").strip()
    if name and name.lower() in CANONICAL_NAMES:
        source, label = LICENSED_CHANNELS[CANONICAL_NAMES[name.lower()]]
        return source, label, (
            f"matched {label} by channel name and not by handle — YouTube permits "
            f"duplicate display names, so confirm the channel before using this"
        )
    return "", "", ""


# ------------------------------------------------------------------------- the lanes


def _binary() -> str:
    """The yt-dlp `research.keyless` already depends on, or "" with the fix logged."""
    found = shutil.which("yt-dlp")
    if not found:
        log.info("scene lookup needs yt-dlp: %s", keyless.available()[1])
    return found or ""


def _dump_json(command: list[str], *, label: str) -> dict:
    """Run one yt-dlp command through `keyless`'s seam and parse what it printed.

    Through `keyless._run` rather than `subprocess.run` for the reason that module gives
    for having the seam at all: one function to substitute in a test, instead of
    replacing `subprocess.run` for every thread in the interpreter. It is also what stops
    a test in this package from reaching youtube.com by accident — the suite refuses a
    real run at that exact function.
    """
    try:
        finished = keyless._run(command)
    except (subprocess.TimeoutExpired, OSError) as exc:
        # Narrow on purpose. The suite's guard fixture raises `AssertionError` from this
        # exact function when a test forgets to substitute it, and a broad `except` here
        # would turn that into "the lane was skipped" — which is silence, and silence is
        # what the guard exists to prevent.
        raise SceneLookupError(f"{label} could not run: {exc}") from exc

    if finished.returncode != 0 or not (finished.stdout or "").strip():
        detail = (finished.stderr or finished.stdout or "").strip().splitlines()
        raise SceneLookupError(
            f"{label} returned nothing: " + " ".join(line for line in detail[-2:] if line)
        )
    try:
        payload = json.loads(finished.stdout)
    except ValueError as exc:
        raise SceneLookupError(f"{label} returned something that was not JSON") from exc
    return payload if isinstance(payload, dict) else {}


def _entries(target: str, *, label: str) -> list[dict]:
    """A flat listing of whatever `target` refers to — a `ytsearch` or a results URL."""
    binary = _binary()
    if not binary:
        return []
    payload = _dump_json(
        [
            binary, "--flat-playlist", "--dump-single-json",
            "--no-warnings", "--ignore-config", target,
        ],
        label=label,
    )
    return [entry for entry in (payload.get("entries") or []) if isinstance(entry, dict)]


def _watch_url(entry: dict) -> str:
    url = str(entry.get("url") or "").strip()
    if url.startswith("http"):
        return url
    video_id = str(entry.get("id") or "").strip()
    return f"https://www.youtube.com/watch?v={video_id}" if video_id else ""


def _window(duration: float) -> tuple[float | None, float | None, str]:
    """The in and out for an upload of this length, and why it is what it is."""
    if duration <= 0:
        return None, None, "the upload's runtime was not reported, so no window was set"
    if duration > CLIP_SECONDS:
        return None, None, (
            f"this runs {duration / 60:.0f} minutes — the scene is inside it and this "
            f"module cannot say where"
        )
    return 0.0, float(duration), (
        "the whole upload is the scene, so the window is the clip's own boundary — "
        "expect a channel ident on the tail"
    )


def _from_channels(film: str, action: str, *, want: int) -> list[SceneMatch]:
    """Movieclips and the studios' own channels, found by search and kept by identity.

    Over-fetched on purpose: a scene search returns mostly re-uploads and reaction
    videos, so asking for the number of results wanted would leave the allow-list
    nothing to keep.
    """
    # "scene" is appended because the licensed clip channels put it in nearly every
    # title — and not appended twice when the operator already said it.
    tail = "" if "scene" in _words(action) else "scene"
    query = " ".join(part for part in (film, action, tail) if part).strip()
    if not query:
        return []
    entries = _entries(f"ytsearch{max(10, min(want * 5, 40))}:{query}",
                       label="the licensed-channel search")

    matches: list[SceneMatch] = []
    for entry in entries:
        url = _watch_url(entry)
        if not url or _refused(url):
            continue
        source, channel, caveat = _permitted_channel(entry)
        if not source:
            continue
        duration = float(entry.get("duration") or 0.0)
        start, end, why = _window(duration)
        licence = LICENCE_DISTRIBUTION if source == MOVIECLIPS else LICENCE_STUDIO
        matches.append(SceneMatch(
            url=url,
            title=str(entry.get("title") or "").strip(),
            source=source,
            licence=licence,
            channel=channel,
            film=film,
            start_seconds=start,
            end_seconds=end,
            duration_seconds=duration,
            flag_reason=_rights_note(source, channel, caveat),
            notes=[why] + ([caveat] if caveat else []),
        ))
    return matches


def _from_creative_commons(action: str, *, want: int) -> list[SceneMatch]:
    """YouTube's Creative Commons filter, asked only when no title was named.

    Reached as a search *URL* rather than a `ytsearch` term because the filter lives in
    the `sp` parameter and there is no search-term equivalent — yt-dlp reads the results
    page the same way a browser does.

    The licence is `by` because that is the only Creative Commons option YouTube offers,
    and it is the uploader's assertion rather than anything this app verified. That is
    survivable here precisely because of what this lane is not asked about: with no title
    in the description there is no rights holder being contradicted.
    """
    if not action.strip():
        return []
    target = (f"https://www.youtube.com/results?search_query={quote_plus(action)}"
              f"&sp=EgIwAQ%253D%253D")
    matches: list[SceneMatch] = []
    for entry in _entries(target, label="the Creative Commons search")[: max(want * 2, 6)]:
        url = _watch_url(entry)
        if not url or _refused(url):
            continue
        duration = float(entry.get("duration") or 0.0)
        start, end, why = _window(duration)
        matches.append(SceneMatch(
            url=url,
            title=str(entry.get("title") or "").strip(),
            source=YOUTUBE_CC,
            licence=LICENCE_CC_BY,
            channel=str(entry.get("channel") or entry.get("uploader") or "").strip(),
            start_seconds=start,
            end_seconds=end,
            duration_seconds=duration,
            flag_reason=(
                "Creative Commons BY as marked by the uploader. Forgecast did not verify "
                "that they own what they marked, and the licence obliges a credit."
            ),
            notes=[why],
        ))
    return matches


async def _from_press(film: str, action: str, *, search: SearchProvider,
                      want: int) -> list[SceneMatch]:
    """Studio press and EPK pages, through whatever search provider is configured.

    Searched broadly and filtered by host, rather than searched per-site: `site:` support
    varies by vendor and a query that silently means nothing to one of them returns its
    ordinary web results, which for this query is a page of streaming-rip sites.

    Skipped outright on the keyless Wikipedia fallback. That provider is real search and
    it is the right default for the research desk, but an encyclopaedia cannot hold a
    studio press page — running it here would spend a request on a lane that has no way
    to succeed, and then report the empty result as though the press sites had nothing.
    """
    if getattr(search, "name", "") == "wikipedia":
        log.info("press lane skipped: %s cannot hold a studio press page", search.name)
        return []
    query = " ".join(part for part in (film, action, "press kit b-roll") if part).strip()
    if not query:
        return []
    results = await search.search(query, limit=max(want * 3, 10))

    matches: list[SceneMatch] = []
    for result in results:
        label = _permitted_page(result.url)
        if not label:
            continue
        matches.append(SceneMatch(
            url=result.url,
            title=(result.title or label).strip(),
            source=PRESS_KIT,
            licence=LICENCE_PRESS,
            channel=label,
            film=film,
            flag_reason=(
                f"{label} publishes this for editorial coverage under terms the studio "
                f"sets. Forgecast has not read those terms and has not established that "
                f"they cover a monetised video."
            ),
            notes=["a press page, not a media file — the asset and any timecode are on it"],
        ))
    return matches


def _rights_note(source: str, channel: str, caveat: str) -> str:
    """The rights position for a studio lane, in words, on the result.

    Says what *is* established before what is not, because the first half is the useful
    part: the operator asked where the scene legitimately is and this is the answer.
    """
    if source == MOVIECLIPS:
        text = (
            f"{channel} is a studio-licensed distributor, so this upload is a lawful "
            f"place to watch the scene. The film's copyright is the studio's and "
            f"Forgecast did not obtain a licence to re-cut it — that decision is yours."
        )
    else:
        text = (
            f"{channel} is the rights holder's own channel, so this upload is official. "
            f"Publishing a clip is not licensing its reuse, and Forgecast did not obtain "
            f"one — that decision is yours."
        )
    return f"{text} {caveat}".strip() if caveat else text


# ------------------------------------------------------------------------- chapters


def _chapter_window(url: str, wanted: set[str]) -> tuple[float, float, str] | None:
    """An in and out from the uploader's own chapter marks, when one names the action.

    Metadata only — `--skip-download` reads what YouTube already publishes on the watch
    page. The download stays `vision.acquire`'s job, which is the whole reason this
    module returns coordinates.
    """
    binary = _binary()
    if not binary or not wanted:
        return None
    payload = _dump_json(
        [
            binary, "--dump-single-json", "--skip-download", "--no-playlist",
            "--no-warnings", "--ignore-config", url,
        ],
        label="the chapter read",
    )

    best: tuple[int, float, float, str] | None = None
    for chapter in (payload.get("chapters") or []):
        if not isinstance(chapter, dict):
            continue
        title = str(chapter.get("title") or "")
        overlap = len(_content_words(title) & wanted)
        if not overlap:
            continue
        start = float(chapter.get("start_time") or 0.0)
        end = float(chapter.get("end_time") or 0.0)
        if end <= start:
            continue
        if best is None or overlap > best[0]:
            best = (overlap, start, end, title)
    if best is None:
        return None
    return best[1], best[2], best[3]


# ----------------------------------------------------------------------- confidence


def _score(match: SceneMatch, film: str, wanted: set[str]) -> tuple[float, str]:
    """`(confidence, reason)` — how sure the app is this is the scene that was asked for.

    Identification only. What may be done with the result is `licence`'s job and mixing
    the two would hide the ordinary case: a clip this app is certain about and certain it
    may not reuse.
    """
    title_words = _content_words(match.title)
    reasons: list[str] = []
    score = 0.0

    film_words = _content_words(film)
    if film_words:
        share = len(film_words & title_words) / len(film_words)
        score += 0.5 * share
        if share >= 0.999:
            reasons.append("the title names the film")
        elif share > 0:
            reasons.append(f"the title carries {share:.0%} of the film's name")
        else:
            reasons.append("the title does not name the film")

    if wanted:
        share = len(wanted & title_words) / len(wanted)
        score += (0.35 if film_words else 0.85) * share
        if share >= 0.999:
            reasons.append("and every word of what you described")
        elif share > 0:
            reasons.append(f"and {len(wanted & title_words)} of {len(wanted)} words "
                           f"of what you described")
        else:
            reasons.append("and none of the words you used for the action")

    # A window is half the answer to "where is the scene", so an upload that cannot
    # produce one is a less confident answer to the question that was asked.
    if match.has_window:
        score += 0.15
        reasons.append("and the upload is short enough to be the scene itself")
    else:
        score *= 0.7
        reasons.append("but no in and out could be determined inside it")

    return min(1.0, round(score, 3)), "; ".join(reasons)


def _rank_key(match: SceneMatch) -> tuple:
    """Confidence first, then a determined window, then how firmly the source is known.

    Rank is not by licence, deliberately. An operator asking where a scene is does not
    want a different scene handed to them because it happened to be better licensed —
    the licence rides on each result so they can see it and choose.
    """
    order = {MOVIECLIPS: 0, STUDIO_CHANNEL: 1, PRESS_KIT: 2, YOUTUBE_CC: 3}
    return (-match.confidence, not match.has_window, order.get(match.source, 9))


# --------------------------------------------------------------------------- locate


async def locate(
    description: str,
    *,
    limit: int = 6,
    search: SearchProvider | None = None,
) -> list[SceneMatch]:
    """Where a described scene is legitimately available, best match first.

    One lane failing is not a reason to fail the lookup — the operator asked where a
    scene is, and two lanes answering is an answer. Every lane is allow-listed at the
    source and every candidate is checked against `REFUSED_MARKERS` on the way out, so a
    search index putting a streaming-rip site first costs a log line rather than a result.

    Returns an empty list when nothing legitimate was found, which is a real answer and
    the right one: there is no lane here that reaches further when the licensed ones come
    back empty.

    `search` defaults to whatever `providers.search.provider_for` picked, so the press
    lane runs by default rather than being a capability a caller has to know to switch
    on. Pass one to route the lane through a specific vendor's key.
    """
    film, action = read_description(description)
    if not (film or action):
        return []

    wanted = _content_words(action) - _content_words(film)
    found: list[SceneMatch] = []

    try:
        found += _from_channels(film, action, want=limit)
    except SceneLookupError as exc:
        log.warning("licensed-channel lane skipped: %s", exc)

    # Asked only when no title was named. A stranger's Creative Commons mark on a studio
    # film is a mistake rather than a licence, and honouring it would be this app
    # laundering a rip through a checkbox.
    if not film:
        try:
            found += _from_creative_commons(action, want=limit)
        except SceneLookupError as exc:
            log.warning("Creative Commons lane skipped: %s", exc)

    try:
        provider = search if search is not None else provider_for()
        found += await _from_press(film, action, search=provider, want=limit)
    except Exception as exc:
        # Broad, and only here. A search vendor raises whatever its own adapter raises,
        # and the two YouTube lanes have already answered by this point — losing them to
        # a 429 from a press-page search would be the tail wagging the dog.
        log.warning("press lane skipped: %s", exc)

    unique: dict[str, SceneMatch] = {}
    for match in found:
        unique.setdefault(match.url, match)

    ranked = list(unique.values())
    for match in ranked:
        match.confidence, match.confidence_reason = _score(match, film, wanted)
    ranked.sort(key=_rank_key)

    # Only the best few long uploads are worth a second round trip, and only the ones
    # that have no window yet — a clip that is already the scene has nothing to refine.
    refined = 0
    for match in ranked:
        if refined >= CHAPTER_LOOKUPS:
            break
        if match.has_window or match.source == PRESS_KIT:
            continue
        refined += 1
        try:
            window = _chapter_window(match.url, wanted)
        except SceneLookupError as exc:
            log.info("no chapter read for %s: %s", match.url, exc)
            continue
        if not window:
            continue
        match.start_seconds, match.end_seconds, chapter = window
        match.notes.append(f"window read from the uploader's chapter mark {chapter!r}")
        match.confidence, match.confidence_reason = _score(match, film, wanted)

    ranked.sort(key=_rank_key)
    log.info("located %d legitimate places for %r", len(ranked), description)
    return ranked[: max(1, int(limit))]
