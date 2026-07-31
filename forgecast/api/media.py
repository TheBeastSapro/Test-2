"""Signed URLs for run media.

## The problem this replaces

Artifacts used to be served by mounting the storage directory with `StaticFiles`.
That mount has no authorisation of any kind: anyone who knows or guesses
`/files/runs/12/final.mp4` gets the video, logged in or not, whoever's run it is. On a
laptop that is a shortcut. On anything reachable — a tunnel, a VPS, a forwarded port —
it means the private instance is only private until someone tries a path.

## Why signatures rather than a session check

A `<video src=...>` tag, a download, and a copied link all have to work, and the
browser will not attach a bearer token to any of them. A cookie would, but then every
media request needs a database round trip and the link stops working the moment you
paste it into a player.

So the URL carries its own authority: an HMAC over the path, the owner, and an expiry,
keyed on the instance secret. Minting a URL requires having already authorised the
user for that artifact — which the run routes do — and verifying one requires no
lookup at all. The URL expires, so a leaked link is a temporary embarrassment rather
than a permanent one, and it names the user it was minted for, so a leak can be traced.

## What it deliberately does not do

It does not stop the holder of a valid URL from sharing it within its lifetime. That
is the accepted trade of any signed-URL scheme, including S3's. Shorten
`media_url_ttl_seconds` if that matters more than links surviving a long watch.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from ..config import get_settings

router = APIRouter(tags=["media"])

# Guessed enough from the extension to make a browser play rather than download.
CONTENT_TYPES = {
    ".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
    ".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".wav": "audio/wav",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".srt": "text/plain; charset=utf-8",
    ".json": "application/json", ".txt": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
}


def _signature(relative: str, user_id: int, expires: int) -> str:
    settings = get_settings()
    message = f"{user_id}:{relative}:{expires}".encode()
    return hmac.new(
        settings.secret_key.encode(), message, hashlib.sha256
    ).hexdigest()[:32]


def relative_path(path: str | Path) -> str | None:
    """The storage-relative path, or None if it is not inside the storage root.

    `resolve()` on both sides is what makes `../` useless: a traversal resolves to
    somewhere outside the root and `relative_to` then raises.
    """
    settings = get_settings()
    try:
        return (Path(path).resolve()
                .relative_to(settings.storage_dir.resolve()).as_posix())
    except (ValueError, OSError):
        return None


def sign_url(path: str | Path, user_id: int, *, ttl: int | None = None) -> str | None:
    """A time-limited URL for this user to fetch this artifact."""
    relative = relative_path(path)
    if relative is None:
        return None
    settings = get_settings()
    expires = int(time.time()) + (ttl or settings.media_url_ttl_seconds)
    signature = _signature(relative, user_id, expires)
    return (f"/media/{quote(relative)}?uid={user_id}&exp={expires}&sig={signature}")


@router.get("/media/{relative:path}", include_in_schema=False)
def media(
    relative: str,
    uid: int = Query(...),
    exp: int = Query(...),
    sig: str = Query(...),
) -> FileResponse:
    settings = get_settings()

    expected = _signature(relative, uid, exp)
    # compare_digest, not ==: a timing-variable comparison on a signature is the kind
    # of thing that is free to get right and unpleasant to explain later.
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(status_code=403, detail="invalid signature")
    if exp < int(time.time()):
        raise HTTPException(status_code=403, detail="link expired")

    root = settings.storage_dir.resolve()
    target = (root / relative).resolve()
    # Re-check containment even though the signature covers the path. Signing a
    # traversal should be impossible, but a path check here costs nothing and means
    # one mistake upstream cannot become an arbitrary file read.
    if not target.is_relative_to(root) or not target.is_file():
        raise HTTPException(status_code=404, detail="not found")

    return FileResponse(
        target,
        media_type=CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream"),
        headers={
            # Private: a signed URL must never be cached by a shared proxy.
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )
