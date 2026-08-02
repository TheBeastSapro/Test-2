"""The style shelf: what has been learned, what it changed, and where to apply it.

Read-and-apply rather than read-and-write. Learning a style means measuring video,
which takes minutes and belongs in the CLI where it can stream progress; this page is
for the part that happens afterwards and often — looking at what was learned, seeing
what the refinement pass departed from, mixing two, and putting one on a channel.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user, optional_user
from ..config import get_settings
from ..db import get_session
from ..graph import formats
from ..models import Channel, User
from ..style import EditingStyle, available, blend, delete, get, refine

log = logging.getLogger("forgecast.api.styles")

router = APIRouter(include_in_schema=False)


def _directory() -> str:
    return str(get_settings().storage_dir / "styles")


@router.get("/styles", response_class=HTMLResponse)
def styles_page(
    request: Request,
    session: Session = Depends(get_session),
    selected: str = "",
) -> HTMLResponse:
    from .routes_web import TEMPLATES, shell

    user = optional_user(request, session)
    if user is None:
        return RedirectResponse("/login?next=/styles", 303)  # type: ignore[return-value]

    folder = _directory()
    rows = available(folder)
    chosen: EditingStyle | None = None
    if selected or rows:
        try:
            chosen = get(selected or rows[0]["key"], folder)
        except KeyError:
            chosen = None

    channels = session.execute(
        select(Channel).where(Channel.user_id == user.id).order_by(Channel.id)
    ).scalars().all()

    return TEMPLATES.TemplateResponse(
        request,
        "styles.html",
        {
            **shell(session, user, "styles", channels=channels),
            "styles": rows,
            "chosen": chosen,
            # Refinements are stored on the style rather than recomputed, so the page
            # shows what was actually applied when it was learned — not what the
            # current thresholds would do to it now.
            "refinements": (chosen.provenance.get("refinements") or []) if chosen else [],
            "channels": channels,
            "channel_format": {c.id: formats.format_of_channel(c) for c in channels},
        },
    )


@router.post("/styles/{key}/apply")
def apply_style(
    key: str,
    channel_id: int = Form(...),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    """Put a style on a channel, keeping everything the style has no opinion about."""
    channel = session.get(Channel, channel_id)
    if channel is None or channel.user_id != user.id:
        raise HTTPException(status_code=404, detail="channel not found")
    try:
        style = get(key, _directory())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    channel.style_profile = style.to_channel_profile(channel.style_profile)
    session.commit()
    log.info("applied style %s to channel %s", style.key, channel.id)
    return RedirectResponse(f"/styles?selected={key}&applied={channel.id}", 303)


@router.post("/styles/{key}/blend")
def blend_styles(
    key: str,
    other: str = Form(...),
    weight: float = Form(0.5),
    name: str = Form(""),
    _user: User = Depends(current_user),
) -> RedirectResponse:
    folder = _directory()
    try:
        first, second = get(key, folder), get(other, folder)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    mixed = blend(first, second, weight, name=name or f"{first.name} x {second.name}")
    mixed.save(folder)
    return RedirectResponse(f"/styles?selected={mixed.key}", 303)


@router.post("/styles/{key}/refine")
def refine_style(key: str, _user: User = Depends(current_user)) -> RedirectResponse:
    """Run the upgrade pass over a style that was saved raw.

    Saved as a new style rather than in place: the measured version is evidence about
    a reference, and evidence you overwrite is not evidence.
    """
    folder = _directory()
    try:
        style = get(key, folder)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    improved, _changes = refine(style)
    improved.save(folder)
    return RedirectResponse(f"/styles?selected={improved.key}", 303)


@router.post("/styles/{key}/delete")
def delete_style(key: str, _user: User = Depends(current_user)) -> RedirectResponse:
    delete(key, _directory())
    return RedirectResponse("/styles", 303)
