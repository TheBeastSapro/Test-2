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
from ..research.outliers import baselines, find_outliers, summarise
from ..research.titles import TITLE_INSTRUCTIONS, parse_ideas

log = logging.getLogger("forgecast.api.research")

router = APIRouter(include_in_schema=False)

MAX_PASTE_CHARS = 400_000
MAX_VIDEOS = 500


class ScoreRequest(BaseModel):
    pasted: str = ""
    channel: str = ""
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


@router.post("/api/research/score")
def score(
    payload: ScoreRequest,
    user: User = Depends(current_user),
) -> JSONResponse:
    """Turn pasted or fetched statistics into a ranked outlier list."""
    if len(payload.pasted) > MAX_PASTE_CHARS:
        raise HTTPException(status_code=413, detail="that is a lot of text — paste fewer rows")

    settings = get_settings()

    # A pasted YouTube link is a channel reference, not a table of statistics.
    # Treating it as one is how this desk came to answer "nothing scoreable" to the
    # most natural thing a person can do here, which reads as the feature being
    # broken rather than as the input being in the wrong box.
    channel_ref = payload.channel.strip()
    if not channel_ref and payload.pasted.strip():
        from ..agent.studio import parse_link

        link = parse_link(payload.pasted.strip())
        if link.kind in ("channel", "handle"):
            channel_ref = link.value
        elif link.kind == "video":
            raise HTTPException(
                status_code=400,
                detail="that is a single video — paste the channel it is on. An "
                       "outlier is measured against its own cohort, and one video "
                       "has no cohort.",
            )

    via = ""
    if channel_ref:
        # No key required: `read_channel` uses one when it is configured and reads the
        # public page when it is not. This used to be a 400 telling the operator to go
        # and get an API key, which is the wall that made the desk read as broken.
        try:
            parsed, via = sources.read_channel(
                channel_ref, api_key=settings.youtube_api_key, limit=payload.limit
            )
        except sources.ResearchError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    else:
        try:
            parsed = sources.parse(payload.pasted)
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=400, detail=f"could not read that: {exc}"
            ) from exc

    if not parsed.videos:
        return JSONResponse({
            "count": 0, "outliers": [], "baselines": {}, "summary": summarise([]),
            "skipped": parsed.skipped, "via": via,
            "note": "nothing scoreable — each row needs at least a title, a view count "
                    "and a publish date",
        })

    videos = parsed.videos[:MAX_VIDEOS]
    now = datetime.now(UTC)
    found = find_outliers(videos, now=now, include_unreliable=payload.include_unreliable)
    bases = baselines(videos, now=now)

    return JSONResponse({
        "count": len(videos),
        "outliers": [item.as_dict() for item in found],
        "baselines": {name: base.as_dict() for name, base in bases.items()},
        "summary": summarise(found),
        "skipped": parsed.skipped[:20],
        "via": via,
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
