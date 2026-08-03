"""Routes that exist only when Forgecast is running as a local desktop application.

## Why a handoff instead of "skip auth on localhost"

The obvious way to make a double-clicked app not ask for a password is to trust
loopback and sign every local request in as the owner. That is wrong for one specific
reason: loopback is not the boundary people assume it is. An SSH tunnel, `docker run
-p`, a VS Code port forward, or any other process on the same machine all arrive on
127.0.0.1. "It came from localhost" means "something on this host asked", not "the
person sitting here asked".

So the desktop launcher mints a random token in memory, hands it to the server through
the environment, and opens exactly one URL containing it. That URL exchanges the token
for the normal session cookie. After that, every request goes through the same
authentication as any other deployment — there is no second code path, and no request
is ever authorised by its source address alone.

Three conditions gate the exchange, and all three must hold:

* `local_mode` is on — it is off unless the launcher turned it on;
* the request arrived on the loopback interface — a forwarded port fails this;
* the token matches, compared in constant time, inside a short window after start.

The token expires a few minutes after launch because the window opens within a second
or two. Anything arriving later is not the launcher.
"""

from __future__ import annotations

import hmac
import ipaddress
import logging
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import create_access_token, current_user
from ..config import get_settings
from ..db import get_session
from ..models import User
from ..render.ffmpeg import ffmpeg_available

log = logging.getLogger("forgecast.api.local")

router = APIRouter(prefix="/local", include_in_schema=False)

COOKIE = "forgecast_session"

# Set when the operator presses Quit in the UI. The desktop supervisor waits on this
# and shuts the server down; in any other deployment nothing is watching it, which is
# why the route that sets it is refused unless `local_mode` is on.
SHUTDOWN = threading.Event()

# Process start, used for the handoff window. Module import time is close enough to
# launch time to be the same thing, and it needs no wiring from the launcher.
_STARTED_AT = time.monotonic()


def _is_loopback(request: Request) -> bool:
    """True when the peer address is a loopback address.

    A missing client (ASGI transports are allowed not to report one) counts as not
    loopback: the check has to fail closed, or an unusual transport becomes a bypass.
    """
    client = request.client
    if client is None or not client.host:
        return False
    try:
        return ipaddress.ip_address(client.host).is_loopback
    except ValueError:
        # A hostname rather than an address — only the literal name is safe to accept.
        return client.host == "localhost"


def _owner(session: Session) -> User | None:
    """The account the desktop window signs in as.

    Preference order matters. An explicitly configured owner wins, because an instance
    that has grown a second account should not start signing in as whoever happens to
    be first in the table. With no owner configured, a single-account database has
    exactly one sensible answer; more than one is ambiguous, so it declines.
    """
    settings = get_settings()
    if settings.owner_email:
        found = session.execute(
            select(User).where(User.email == settings.owner_email.strip().lower())
        ).scalar_one_or_none()
        if found is not None and found.is_active:
            return found
        return None

    users = session.execute(
        select(User).where(User.is_active.is_(True)).order_by(User.id).limit(2)
    ).scalars().all()
    return users[0] if len(users) == 1 else None


def _refuse(request: Request, reason: str) -> None:
    log.warning("local handoff refused (%s) from %s", reason,
                request.client.host if request.client else "unknown")


@router.get("/session")
def local_session(
    request: Request,
    t: str = "",
    next: str = "/",
    session: Session = Depends(get_session),
) -> RedirectResponse:
    """Exchange the launcher's token for a session cookie, then land on the dashboard.

    Every failure redirects to the ordinary login page rather than explaining itself.
    The launcher prints the owner's password, so a person who lands here can always
    still get in; anything else is telling a prober which of the three checks it
    failed.
    """
    settings = get_settings()

    if not settings.local_mode or not settings.local_handoff_token:
        _refuse(request, "not a desktop instance")
        raise HTTPException(status_code=404, detail="not found")

    if not _is_loopback(request):
        _refuse(request, "not loopback")
        raise HTTPException(status_code=404, detail="not found")

    if time.monotonic() - _STARTED_AT > settings.local_handoff_ttl_seconds:
        _refuse(request, "expired")
        return RedirectResponse("/login?error=Sign-in+link+expired,+restart+the+app", 303)

    if not hmac.compare_digest(t, settings.local_handoff_token):
        _refuse(request, "bad token")
        return RedirectResponse("/login", 303)

    user = _owner(session)
    if user is None:
        return RedirectResponse(
            "/login?error=Could+not+identify+the+local+owner+account", 303
        )

    # `next` is a path this app owns, never a URL. Redirecting to whatever arrives in
    # a query parameter is an open redirect, and this endpoint hands out a session
    # cookie — the one place it would actually be worth exploiting.
    landing = next if next.startswith("/") and not next.startswith("//") else "/"
    response = RedirectResponse(landing, 303)
    response.set_cookie(
        COOKIE,
        create_access_token(user),
        httponly=True,
        samesite="lax",
        secure=False,  # loopback http; a secure cookie would never be sent back
        max_age=settings.access_token_ttl_minutes * 60,
    )
    log.info("desktop window signed in as %s", user.email)
    return response


@router.get("/status")
def local_status() -> JSONResponse:
    """What the app can and cannot do right now.

    The dashboard reads this to warn about a missing ffmpeg *before* a run reaches the
    render node and fails twenty minutes in.
    """
    settings = get_settings()
    return JSONResponse({
        "local_mode": settings.local_mode,
        "provider_mode": settings.provider_mode,
        "ffmpeg": ffmpeg_available(),
        "storage_dir": str(settings.storage_dir.resolve()),
        "base_url": settings.base_url,
    })


@router.post("/quit")
def local_quit(request: Request, _user: User = Depends(current_user)) -> JSONResponse:
    """Stop the application from inside the application.

    Authenticated *and* loopback *and* desktop-mode. A browser tab has no window to
    close, so without this the only way to stop a launched instance is to find the
    terminal it was started from.
    """
    settings = get_settings()
    if not settings.local_mode or not _is_loopback(request):
        raise HTTPException(status_code=404, detail="not found")
    log.info("quit requested from the UI")
    SHUTDOWN.set()
    return JSONResponse({"stopping": True})
