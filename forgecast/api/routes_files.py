"""The Files browser: what a run actually wrote, read-only.

## Why this exists

A run leaves its evidence on disk — the brief, the script, each still, every voice
take, the render — and until now the only way to see whether a stage produced anything
was to open a file manager beside the app. The question people actually ask about a
finished or stalled run is not "what does the graph say", it is "did it write
anything, and how big is it". That question is answered by a listing with sizes and
modification times, so that is what this page is.

## Why it is lazy

`storage_dir` is where gigabytes go. A single run's stills directory can hold hundreds
of files and a long-form render is measured in gigabytes; walking the tree recursively
to draw it would stat tens of thousands of paths on every page load and hold the
request open while it did. So exactly one directory level is read per request: the
root ships inside the page, and every folder is read when it is opened and not before.

## Why so much of this file is a containment check

Every path here arrives from the browser, and the thing on the other end of it is the
filesystem of the machine the app is running on. A browser that can name a path can
name `../../../../etc/passwd`, an absolute path, or a symlink someone dropped in the
storage folder that points at a home directory. Containment is therefore decided in
one function, `inside()`, and decided *after* resolving — because resolving is what
collapses `..` and follows symlinks, and a check made before it is a check of a string
rather than of the file that will be opened.

Ownership is separate from containment and just as necessary: `runs/<id>/` is one
account's work, so the run row is consulted before its folder is listed or read.
"""

from __future__ import annotations

import codecs
import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..auth import current_user, optional_user
from ..config import get_settings
from ..db import get_session
from ..models import Run, User
from .media import CONTENT_TYPES, sign_url

log = logging.getLogger("forgecast.api.files")

router = APIRouter(include_in_schema=False)

# Read at most this much of a text file into the page. A 40 MB transcript pasted into
# a <pre> is a frozen tab, and the first quarter-megabyte answers every question a
# browser is the right tool for.
MAX_TEXT_BYTES = 256 * 1024

# One directory's worth of rows. A stills folder from a long run can hold thousands of
# frames, and a list that long is neither readable nor cheap to serialise; it is cut
# and the cut is reported, because a listing silently missing files is worse than a
# listing that says it is incomplete.
MAX_ENTRIES = 2000

# Sniffed rather than read whole when the extension is unfamiliar.
SNIFF_BYTES = 8192

# Folder names carry meaning here: this is the one whose contents belong to a single
# account rather than to the installation.
RUNS = "runs"

TEXT_EXT = {
    ".txt", ".md", ".json", ".jsonl", ".csv", ".tsv", ".log", ".srt", ".vtt", ".ass",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".xml", ".html", ".css", ".js", ".py",
    ".sh", ".sql",
}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".avif"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v", ".mpg", ".mpeg"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".weba"}


# ------------------------------------------------------------------- the boundary


def storage_root() -> Path:
    return get_settings().storage_dir.resolve()


def inside(relative: str) -> Path | None:
    """The absolute path a browser-supplied string names, or None if it escapes.

    `resolve()` first, containment second, and in that order for a reason. Resolving
    collapses `..` and follows symlinks, so a link sitting inside the storage folder
    that points at `/etc` becomes `/etc` here — which only a check performed after
    resolving can see. An absolute path needs no special case either: joining one onto
    the root discards the root, and the result fails the same test.

    Returning None rather than raising keeps this usable while listing a directory,
    where an entry that cannot be contained is skipped rather than fatal.
    """
    root = storage_root()
    try:
        target = (root / relative).resolve()
        target.relative_to(root)
    except (ValueError, OSError):
        # ValueError covers both the containment failure and a path with a NUL byte in
        # it, which pathlib refuses; OSError covers a symlink loop met while resolving.
        return None
    return target


def relative_of(target: Path) -> str:
    """The storage-relative, forward-slash form the browser and the API agree on.

    The root itself is the empty string rather than `.`, so it can be concatenated
    with a child name without producing `./runs`.
    """
    posix = target.relative_to(storage_root()).as_posix()
    return "" if posix == "." else posix


def owned(session: Session, user: User, relative: str) -> bool:
    """Whether this account may see a storage path.

    The storage directory belongs to the installation, not to one account: the learned
    styles, `motion_presets/` and the voice catalogue describe this machine and anyone
    signed in to it may read them. `runs/<id>/` is different — it holds one account's
    brief, script and render — so the run row decides, and the folder is invisible to
    everybody else.

    A numbered folder whose run row is gone cannot be attributed to anyone, so it is
    hidden as well. Otherwise deleting a run would be the moment its files became
    readable by every other account on the instance.
    """
    parts = [part for part in relative.split("/") if part]
    if len(parts) < 2 or parts[0] != RUNS:
        return True
    if not parts[1].isdigit():
        return False
    run = session.get(Run, int(parts[1]))
    return run is not None and run.user_id == user.id


def locate(session: Session, user: User, relative: str) -> Path:
    """Resolve a requested path or refuse it with 404.

    404 and not 403 throughout: a distinguishable "forbidden" tells an unauthenticated
    prober which paths exist, and existence is the part worth not confirming.

    Ownership is checked against the *resolved* relative path, never the string that
    arrived. `runs/7/../8/script.md` names run 8 no matter which run it starts from,
    and a check made on the raw text would read it as run 7.
    """
    target = inside(relative)
    if target is None or not owned(session, user, relative_of(target)):
        raise HTTPException(status_code=404, detail="no such path")
    return target


# ------------------------------------------------------------------- descriptions


def human_size(count: int) -> str:
    if count < 1024:
        return f"{count} B"
    size = float(count)
    for unit in ("KB", "MB", "GB", "TB"):
        size /= 1024
        if size < 1024:
            return f"{size:.1f} {unit}" if size < 10 else f"{size:.0f} {unit}"
    return f"{size:.0f} PB"


def looks_like_text(path: Path) -> bool:
    """Whether an unfamiliar extension is worth showing as text.

    Run folders accumulate extension-less files and one-off suffixes, and refusing to
    show a readable manifest because it is called `manifest` rather than
    `manifest.json` is the kind of gap that sends people back to the file manager.

    An incremental decoder rather than `bytes.decode`: the sniff window almost always
    lands mid-character in a UTF-8 file, and a plain decode would call every non-ASCII
    text file binary.
    """
    try:
        with path.open("rb") as handle:
            head = handle.read(SNIFF_BYTES)
    except OSError:
        return False
    if b"\x00" in head:
        return False
    try:
        codecs.getincrementaldecoder("utf-8")().decode(head, final=False)
    except UnicodeDecodeError:
        return False
    return True


def kind_of(path: Path) -> str:
    """What a file is according to its name alone, or "unknown"."""
    ext = path.suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in TEXT_EXT:
        return "text"
    return "unknown"


def classify(path: Path) -> str:
    """As `kind_of`, but opens the file when its name does not settle the question.

    Reserved for the one file being viewed. Sniffing while listing a directory would
    mean an open and a read per entry — a stills folder would cost thousands of them —
    and that is the per-file work this page is built to avoid.
    """
    named = kind_of(path)
    if named != "unknown":
        return named
    return "text" if looks_like_text(path) else "other"


def sort_key(entry: dict) -> tuple:
    """Folders first, then numerically where the names are numbers.

    `runs/` is numbered, and a lexicographic sort puts run 10 between run 1 and run 2 —
    which reads as missing runs rather than as an ordering choice.
    """
    name = entry["name"]
    return (not entry["is_dir"], 0 if name.isdigit() else 1,
            int(name) if name.isdigit() else 0, name.lower())


def describe(path: Path, relative: str, *, stat: os.stat_result) -> dict:
    is_dir = os.path.isdir(path)
    modified = datetime.fromtimestamp(stat.st_mtime)
    return {
        # Named from the relative path rather than from the resolved one, so a link
        # inside the storage folder is listed under the name it has here instead of
        # under the name of whatever it points at.
        "name": relative.rsplit("/", 1)[-1] or path.name,
        "path": relative,
        "is_dir": is_dir,
        # A directory's own byte count says nothing about what is under it, and adding
        # up its contents would mean a scandir per child — turning one listing into
        # hundreds of directory reads, which is the recursive walk this page exists to
        # avoid. Its modification time is the honest signal, and it is the one that
        # answers "did this run write anything".
        "size": None if is_dir else stat.st_size,
        "size_label": "—" if is_dir else human_size(stat.st_size),
        "kind": "dir" if is_dir else kind_of(path),
        "modified": modified.isoformat(timespec="seconds"),
        "modified_label": modified.strftime("%Y-%m-%d %H:%M"),
    }


def read_directory(session: Session, user: User, target: Path) -> dict:
    """One level of a directory, and nothing below it."""
    if not target.is_dir():
        raise HTTPException(status_code=404, detail="no such directory")

    here = relative_of(target)
    entries: list[dict] = []
    skipped = 0
    try:
        with os.scandir(target) as scan:
            for item in scan:
                child = f"{here}/{item.name}" if here else item.name
                resolved = inside(child)
                # An entry that does not resolve back inside the root is a symlink out
                # of the storage folder. It is left out entirely rather than listed and
                # then refused on click, so the tree only ever shows what it can open.
                if resolved is None or not owned(session, user, relative_of(resolved)):
                    continue
                if len(entries) >= MAX_ENTRIES:
                    skipped += 1
                    continue
                try:
                    entries.append(describe(resolved, child, stat=item.stat()))
                except OSError:
                    # A file deleted between the scandir and the stat. One vanished
                    # frame must not fail the whole listing.
                    continue
    except OSError as exc:
        log.warning("could not list %s: %s", target, exc)
        raise HTTPException(status_code=404, detail="no such directory") from exc

    entries.sort(key=sort_key)
    return {"path": here, "entries": entries, "truncated": bool(skipped),
            "skipped": skipped}


# ------------------------------------------------------------------------- routes


@router.get("/files", response_class=HTMLResponse)
def files_page(
    request: Request,
    session: Session = Depends(get_session),
    path: str = "",
) -> HTMLResponse:
    from .routes_web import TEMPLATES, shell

    user = optional_user(request, session)
    if user is None:
        return RedirectResponse("/login?next=/files", 303)  # type: ignore[return-value]

    root = storage_root()
    root.mkdir(parents=True, exist_ok=True)

    return TEMPLATES.TemplateResponse(
        request,
        "files.html",
        {
            **shell(session, user, "files"),
            "storage_dir": str(root),
            # The first level travels with the page, so opening /files costs no extra
            # round trip and the tree is populated before any script runs. Every level
            # below it is fetched on open by the same renderer, so a folder cannot draw
            # differently depending on how it was reached.
            "root": read_directory(session, user, root),
            # A deep link — from a run page, or a copied URL — opens with that file
            # already selected instead of the empty viewer.
            "selected": path,
        },
    )


@router.get("/api/files/list")
def list_directory(
    path: str = "",
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    """One directory level. Called once per folder the operator opens."""
    return read_directory(session, user, locate(session, user, path))


@router.get("/api/files/content")
def file_content(
    path: str = "",
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    """What the viewer needs to show one file, and never its whole body.

    Text comes back inline because it is capped and the viewer wants it now. Bytes do
    not: images, video and audio are handed over as signed media URLs, so a 2 GB render
    streams from `api.media` — with range requests, an expiry and an owner in the
    link — instead of being base64'd through this JSON response.
    """
    target = locate(session, user, path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="no such file")

    relative = relative_of(target)
    stat = target.stat()
    payload = {
        **describe(target, relative, stat=stat),
        # The one place a file is opened to find out what it is, rather than guessed at
        # from its extension.
        "kind": classify(target),
        "text": None,
        "truncated": False,
        "media_url": None,
        "note": "",
    }

    kind = payload["kind"]
    if kind == "text":
        try:
            with target.open("rb") as handle:
                # One byte past the cap, purely to learn whether there was more. Any
                # cheaper test — comparing the read length to the file size — is wrong
                # for a file still being written.
                raw = handle.read(MAX_TEXT_BYTES + 1)
        except OSError as exc:
            raise HTTPException(status_code=404, detail="could not read that") from exc
        payload["truncated"] = len(raw) > MAX_TEXT_BYTES
        payload["text"] = raw[:MAX_TEXT_BYTES].decode("utf-8", errors="replace")
        if payload["truncated"]:
            payload["note"] = (
                f"Showing the first {human_size(MAX_TEXT_BYTES)} of "
                f"{payload['size_label']}. The rest is on disk, not in this page."
            )
    elif kind in ("image", "video", "audio"):
        payload["media_url"] = sign_url(target, user.id)
        if target.suffix.lower() not in CONTENT_TYPES:
            # Said rather than discovered: a container the browser will not decode
            # otherwise shows an empty player and reads as a broken file.
            payload["note"] = (
                f"{target.suffix.lower()} is served as-is — your browser may not be "
                f"able to play this container."
            )
    else:
        payload["note"] = (
            f"A {payload['size_label']} {target.suffix.lower() or 'extension-less'} "
            f"file. Forgecast will not guess at it: it is not text, and rendering it "
            f"as any of the things it might be would only be a slower way of showing "
            f"nothing."
        )

    return payload
