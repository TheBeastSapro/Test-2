"""The skills library: read, edit and add the instruction documents the agent follows.

## Why this page is an editor rather than a viewer

The Styles page next door is deliberately read-and-apply, because a style is measured and
editing a measurement by hand destroys the evidence. A skill is the opposite: it is
someone's craft, written in prose, and it is *wrong* until it has been argued with a few
times. A library you cannot edit in the app is a library that gets edited in a text
editor instead, and then the app is showing files it does not own.

## Why the path is /skills-library

`/skills` and `/styles` are both already taken by the style shelf's routes, and a skill
and a style are different enough that reusing the word would be a bug waiting to be
filed. The nav key is still "skills" — that is what the sidebar highlights.

## What is scoped to whom

Skills are files under the installation's storage directory, exactly like learned styles
and connector settings: they describe this studio's craft, not one login's. There are
therefore no per-account rows to filter — the only database read on this page is the
shell's, which is already scoped to the signed-in user. Every route here still requires
a signed-in user, because an unauthenticated editor for files on disk is a remote file
write.
"""

from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from .. import skills
from ..auth import current_user, optional_user
from ..db import get_session
from ..models import User

log = logging.getLogger("forgecast.api.skills")

router = APIRouter(include_in_schema=False)


@router.get("/skills-library", response_class=HTMLResponse)
def skills_page(
    request: Request,
    session: Session = Depends(get_session),
    selected: str = "",
    saved: str = "",
    error: str = "",
    new: str = "",
) -> HTMLResponse:
    from .routes_web import TEMPLATES, shell

    user = optional_user(request, session)
    if user is None:
        return RedirectResponse("/login?next=/skills-library", 303)  # type: ignore[return-value]

    rows = skills.available()
    chosen: skills.Skill | None = None
    # An explicit "new" beats a selection, so the blank editor cannot be stolen back by
    # the default-to-the-first-skill rule below the moment the page reloads.
    if not new and (selected or rows):
        try:
            chosen = skills.get(selected or rows[0]["slug"])
        except (KeyError, ValueError):
            chosen = None

    return TEMPLATES.TemplateResponse(
        request,
        "skills.html",
        {
            **shell(session, user, "skills"),
            "skills": rows,
            "chosen": chosen,
            "creating": bool(new) or (chosen is None and not rows),
            "folder": str(skills.directory().resolve()),
            "saved": saved,
            "error": error,
        },
    )


@router.post("/skills-library/save")
def save_skill(
    slug: str = Form(""),
    name: str = Form(""),
    when_to_use: str = Form(""),
    body: str = Form(""),
    _user: User = Depends(current_user),
) -> RedirectResponse:
    """Create or replace one skill.

    `slug` is the document the editor loaded, and `refile` needs it to tell a rename from
    a collision: two different titles routinely land on one filename, and a save that
    overwrote the wrong document would also delete the right one. A refusal comes back as
    the banner rather than a 400, because the operator is on a page and a status code is
    not something a form post shows them.
    """
    try:
        stored = skills.refile(slug, name, when_to_use, body)
    except ValueError as exc:
        # Logged as well as shown: a refusal here means an editor's work did not land,
        # and the banner is gone the moment the operator clicks anything else.
        log.info("skill save refused for name %r: %s", name[:80], exc)
        # `selected` puts the document that was in the way on screen, which is the only
        # thing that makes a name collision explicable rather than a mystery.
        return RedirectResponse(
            f"/skills-library?selected={skills.slugify(name)}&error={_query(str(exc))}",
            303)

    return RedirectResponse(
        f"/skills-library?selected={stored.slug}&saved={_query(stored.name)}", 303)


@router.post("/skills-library/{slug}/delete")
def delete_skill(slug: str, _user: User = Depends(current_user)) -> RedirectResponse:
    try:
        skills.delete(slug)
    except ValueError as exc:
        return RedirectResponse(f"/skills-library?error={_query(str(exc))}", 303)
    return RedirectResponse("/skills-library", 303)


def _query(text: str) -> str:
    """A value safe to put in the redirect's query string.

    Names are user input and routinely contain spaces and ampersands, either of which
    turns the banner into a truncated message or an extra parameter.
    """
    return quote(text[:120], safe="")
