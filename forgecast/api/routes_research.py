"""The research desk: find what outperformed, and turn it into a topic.

Two things happen here and the split between them is the point.

**The scoring is arithmetic.** How much a video beat its cohort by, whether the cohort
is big enough to have a meaningful median, whether a video is old enough to score —
all of it is computable from public statistics, and `research.outliers` computes it.
Asking a language model to eyeball "is 240k views good for this channel" produces a
confident number with no method behind it, and the error is invisible because the
output looks identical either way.

**The judgement is a model call.** What is transferable about a video that worked, and
what to make instead, is not arithmetic. That runs through the LLM — but only after the
arithmetic has decided which videos are worth asking about, and the model is given the
measured numbers rather than asked to invent them.

## What one fetch covers, and what the answer has to admit to

A fetch reads several competitor channels at once, plus any individual video links
pasted into the box under them. The response is built so nothing arrives silently:
`channels` and `priority` list every reference that was asked for and what became of
it, whether or not it produced a single row. A channel that could not be read and a
pasted video that turned out to be ordinary both have to be visible as *fetched*, or
the operator is left comparing a set they think they assembled against the one they
actually got.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user, optional_user
from ..config import get_settings
from ..db import get_session
from ..models import Channel, User
from ..providers import ProviderError
from ..providers.registry import registry_for
from ..research import sources
from ..research.outliers import (
    MIN_AGE_DAYS,
    baselines,
    baselines_by_channel,
    find_outliers,
    summarise,
)
from ..research.titles import TITLE_INSTRUCTIONS, parse_ideas

log = logging.getLogger("forgecast.api.research")

router = APIRouter(include_in_schema=False)

MAX_PASTE_CHARS = 400_000
MAX_VIDEOS = 500


class ScoreRequest(BaseModel):
    pasted: str = ""
    # Still singular, and still a plain string, because it now holds however many
    # references were pasted and `sources.split_references` is what decides where one
    # ends. Renaming it to `channels` would break every caller that already posts
    # `channel` — the agent's studio tools among them — to say something the field's
    # contents already say.
    channel: str = ""
    # The sub-box: specific videos to fetch alongside the channels.
    videos: str = ""
    limit: int = Field(default=50, ge=5, le=200)
    include_unreliable: bool = False


class IdeasRequest(BaseModel):
    title: str
    multiple: float = 1.0
    band: str = "soft"
    niche: str = ""
    channel_id: int | None = None
    notes: str = ""


@router.get("/research", response_class=HTMLResponse)
def research_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    from .routes_web import TEMPLATES, shell

    user = optional_user(request, session)
    if user is None:
        return RedirectResponse("/login?next=/research", 303)  # type: ignore[return-value]

    channels = session.execute(
        select(Channel).where(Channel.user_id == user.id).order_by(Channel.id)
    ).scalars().all()
    settings = get_settings()

    # Fetching needs *a* way to read a channel, and a key is only one of them. Gating
    # the box on the key alone disabled it on every install that could in fact fetch.
    from ..research import keyless

    keyless_ready, keyless_fix = keyless.available()
    return TEMPLATES.TemplateResponse(
        request,
        "research.html",
        {
            **shell(session, user, "research"),
            "channels": channels,
            # Deliberately no `has_youtube_key` here. The page ran on it and gated the
            # fetch box on it, which is the wall this change removes; leaving the flag
            # in the context is an invitation to write `{% if has_youtube_key %}` copy
            # later and put the wall back.
            "can_fetch": bool(settings.youtube_api_key) or keyless_ready,
            # The short form of the caveat, not `keyless.SOURCE_NOTE`. The full note
            # comes back as `via` with the results and the page prints it there, so
            # using it here as well put the same paragraph on screen twice — once
            # above the button and once below it.
            "fetch_note": (
                "" if settings.youtube_api_key
                else "No API key needed: the public channel page is read instead, so "
                     "publish dates are approximate and a video whose verdict turns on "
                     "one comes back with a range."
                if keyless_ready
                else keyless_fix
            ),
        },
    )


def _sort_pasted_links(text: str) -> tuple[list[str], list[str], bool]:
    """A paste that is nothing but links, sorted into channels and videos.

    A pasted YouTube link is a reference, not a table of statistics. Treating it as one
    is how this desk came to answer "nothing scoreable" to the most natural thing a
    person can do here, which reads as the feature being broken rather than as the input
    being in the wrong box.

    The "nothing but links" condition is what keeps it safe: a table with a url column
    contains words that are not links, so one unrecognised token hands the whole blob
    back to the table parser rather than routing half of it and losing the rest.
    """
    from ..agent.studio import parse_link

    references = sources.split_references(text)
    if not references:
        return [], [], False

    channels: list[str] = []
    videos: list[str] = []
    for reference in references:
        kind = parse_link(reference).kind
        if kind in ("channel", "handle"):
            channels.append(reference)
        elif kind == "video":
            videos.append(reference)
        else:
            return [], [], False
    return channels, videos, True


def _why_not_scored(video, now: datetime) -> str:
    """Why a video that was fetched has no multiple. Never "it did not appear"."""
    age = video.age_days(now)
    if age < MIN_AGE_DAYS:
        return (
            f"fetched, but it went out {age:.1f} days ago — under {MIN_AGE_DAYS:g} days "
            f"the views-per-day figure is still the subscriber notification push, so "
            f"there is no honest multiple to give yet"
        )
    return (
        "fetched, but nothing in this fetch shares its cohort — add its channel above "
        "so there is a median to measure it against"
    )


def _priority_rows(readout, found, videos, now: datetime) -> list[dict]:
    """One row per pasted link, whatever happened to it.

    This is the part the operator asked for by name. A pasted video that scored, one
    that was read and turned out ordinary, and one that could not be read at all are
    three different answers, and all three have to reach the screen — a list that only
    shows the ones that scored is indistinguishable from a box that quietly did nothing.
    """
    scored = {item.video.video_id: item for item in found if item.priority}
    fetched = {video.video_id: video for video in videos if video.is_priority}

    rows: list[dict] = []
    for row in readout.priority:
        entry = row.as_dict()
        item = scored.get(row.video_id)
        video = fetched.get(row.video_id)
        if item is not None:
            entry.update({
                "fetched": True, "scored": True,
                "views": item.video.views,
                "multiple": round(item.multiple, 2),
                "band": item.band,
                "reliable": item.reliable,
            })
        elif video is not None:
            entry.update({"fetched": True, "scored": False, "views": video.views,
                          "why": _why_not_scored(video, now)})
        else:
            entry.update({"fetched": False, "scored": False})
        rows.append(entry)
    return rows


@router.post("/api/research/score")
def score(
    payload: ScoreRequest,
    user: User = Depends(current_user),
) -> JSONResponse:
    """Turn pasted or fetched statistics into a ranked outlier list."""
    if len(payload.pasted) > MAX_PASTE_CHARS:
        raise HTTPException(status_code=413, detail="that is a lot of text — paste fewer rows")

    settings = get_settings()

    channel_refs = sources.split_references(payload.channel)
    video_refs = sources.split_references(payload.videos)

    pasted = payload.pasted.strip()
    from_paste, videos_from_paste, all_links = _sort_pasted_links(pasted)
    if all_links:
        # Consumed as references, so it is not also handed to the table parser, which
        # would read a bare URL as a one-column header and quietly return nothing.
        channel_refs += [ref for ref in from_paste if ref not in channel_refs]
        video_refs += [ref for ref in videos_from_paste if ref not in video_refs]
        pasted = ""

    if video_refs and not channel_refs and not pasted:
        raise HTTPException(
            status_code=400,
            detail="those are videos with nothing to measure them against. An outlier "
                   "is measured against its own cohort, so put the channel in the top "
                   "box — the videos in the box under it are then scored against it, "
                   "and kept out of the median so they cannot raise their own bar.",
        )

    readout = sources.Readout()
    if channel_refs or video_refs:
        # No key required: the readers use one when it is configured and read the public
        # pages when it is not. This used to be a 400 telling the operator to go and get
        # an API key, which is the wall that made the desk read as broken.
        readout = sources.read_desk(
            channel_refs, video_refs,
            api_key=settings.youtube_api_key, limit=payload.limit,
        )
    if pasted:
        try:
            parsed = sources.parse(pasted)
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=400, detail=f"could not read that: {exc}"
            ) from exc
        readout.videos += parsed.videos
        readout.skipped += parsed.skipped

    # Every channel refused. A fetch that read nothing at all is a failure to report as
    # one, not an empty table — the operator gave references and none of them worked.
    failures = [row for row in readout.channels if row.error]
    if channel_refs and len(failures) == len(readout.channels) and not readout.videos:
        raise HTTPException(
            status_code=502,
            detail="\n".join(f"{row.reference}: {row.error}" for row in failures),
        )

    now = datetime.now(UTC)
    if not readout.videos:
        return JSONResponse({
            "count": 0, "outliers": [], "baselines": {}, "channel_baselines": {},
            "summary": summarise([]),
            "channels": [row.as_dict() for row in readout.channels],
            "priority": _priority_rows(readout, [], [], now),
            "skipped": readout.skipped, "via": readout.via,
            "note": "nothing scoreable — each row needs at least a title, a view count "
                    "and a publish date",
        })

    # The cap falls on the channel listings, never on the pasted links: those are the
    # rows somebody asked for by name, and five 200-video channels would otherwise push
    # every one of them past the limit and out of the answer.
    priority = [video for video in readout.videos if video.is_priority]
    ordinary = [video for video in readout.videos if not video.is_priority]
    videos = ordinary[:MAX_VIDEOS] + priority

    found = find_outliers(videos, now=now, include_unreliable=payload.include_unreliable)
    bases = baselines(videos, now=now)

    return JSONResponse({
        "count": len(videos),
        "outliers": [item.as_dict() for item in found],
        # Kept: with one channel it is that channel's baseline, and it is what the
        # pasted-table path has — there is no channel to key those rows by.
        "baselines": {name: base.as_dict() for name, base in bases.items()},
        # And the per-channel view, which is what several competitors in one fetch
        # actually have. A median pooled across channels of different sizes is a number
        # neither of them has been near.
        "channel_baselines": {
            channel: {name: base.as_dict() for name, base in cohorts.items()}
            for channel, cohorts in baselines_by_channel(videos, now=now).items()
        },
        "channels": [row.as_dict() for row in readout.channels],
        "priority": _priority_rows(readout, found, videos, now),
        "summary": summarise(found),
        "skipped": readout.skipped[:20],
        "via": readout.via,
    })


@router.post("/api/research/ideas")
async def ideas(
    payload: IdeasRequest,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> JSONResponse:
    """Ask for transferable angles and titles, given a video that measurably worked.

    The measured numbers go into the prompt rather than being asked for. A model that
    is told "this beat its cohort 8.4x" reasons about *why*; a model asked to estimate
    how well something did will produce a number, and the number will be decoration.
    """
    niche = payload.niche
    if payload.channel_id and not niche:
        channel = session.get(Channel, payload.channel_id)
        if channel is not None and channel.user_id == user.id:
            niche = channel.niche or ""

    registry = registry_for(session, user)
    llm = registry.llm()
    prompt = (
        f"{TITLE_INSTRUCTIONS}\n\nINPUT:\n"
        f"outperforming video title: {payload.title}\n"
        f"measured performance: {payload.multiple:.1f}x its cohort median "
        f"({payload.band} outlier)\n"
        f"channel niche: {niche or 'unspecified'}\n"
        f"operator notes: {payload.notes or 'none'}\n"
    )
    try:
        result = await llm.complete(
            prompt,
            system="You help a faceless-video channel decide what to make next.",
            json_object=True,
            schema_name="title_ideas",
            max_tokens=2048,
            temperature=0.8,
        )
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    data = parse_ideas(result.text)
    data["provider"] = result.provider
    data["credits"] = result.credits
    return JSONResponse(data)
