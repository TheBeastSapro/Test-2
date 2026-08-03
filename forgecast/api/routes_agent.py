"""The chat, its threads, and everything the composer needs.

Streaming is newline-delimited JSON rather than SSE. A turn here can read fifty
videos or start a render, so text and tool calls have to go out as they happen — but
SSE's framing buys nothing when the client is `fetch` in the same window, and NDJSON
survives a proxy that helpfully buffers `text/event-stream`.

Every write is scoped to the signed-in account. Threads are not shared and there is
no route that lists someone else's.
"""

from __future__ import annotations

import json
import logging
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent import assistant, connectors, engines, prefs, tools
from ..agent.studio import Studio
from ..auth import current_user
from ..config import get_settings
from ..db import SessionLocal, get_session
from ..models import ChatMessage, Conversation, User

log = logging.getLogger("forgecast.api.agent")

router = APIRouter(prefix="/api/agent", tags=["agent"], include_in_schema=False)

# A first message longer than this is a pasted script, and a pasted script belongs in
# a run rather than in a chat turn. Refused with a reason rather than truncated.
MAX_MESSAGE_CHARS = 60_000
MAX_ATTACH_BYTES = 512 * 1024 * 1024

# One turn per conversation at a time, across every window.
#
# The browser's own guard is per page, so two desktop windows — or a tab left open
# from earlier — sail straight past it. Both turns then resume the same CLI session
# id, and the last one to finish writes its session over the other's: the losing
# conversation is silently orphaned, and the next message on it resumes a session
# whose history is missing half the turns.
#
# A plain in-process set rather than a row lock, because the thing being serialised is
# a CLI subprocess owned by this process. Cleared in a `finally`, so a crashed turn
# does not leave a thread permanently refusing to talk.
_IN_FLIGHT: set[int] = set()

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
AUDIO_EXT = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


def attach_dir() -> Path:
    """Inside the app root on purpose.

    The agent is sandboxed to that folder, so a file dropped anywhere else is a path
    it is not allowed to open — the attachment would look like it worked and then
    quietly fail at the Read.
    """
    path = assistant.APP_ROOT / "attachments"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _studio(user: User) -> Studio:
    return Studio(SessionLocal, user_id=user.id)


# --------------------------------------------------------------------------- auth


@router.get("/auth")
def agent_auth(engine: str = "", _user: User = Depends(current_user)) -> dict:
    """Is the agent connected — for the selected backend, or a named one.

    `engine=` is what lets the picker say what switching would cost *before* you
    switch. Choosing ChatGPT and only then being told the Codex CLI is missing is the
    same "looked fine until it failed" shape this module exists to avoid.
    """
    return engines.auth_check(engine or None)


@router.post("/auth/login")
def agent_login(payload: dict | None = None,
                _user: User = Depends(current_user)) -> dict:
    ok, message = engines.start_login((payload or {}).get("engine"))
    return {"ok": ok, "message": message}


# -------------------------------------------------------------------------- prefs


@router.get("/prefs")
def get_prefs(_user: User = Depends(current_user)) -> dict:
    """The composer's settings, plus what may be chosen.

    `models` stays the flat list the composer already reads, and it is the *selected
    engine's* list — so the picker cannot offer a model the running backend would
    reject. `engines` carries the rest, including the one-line description of how each
    one signs in, which is the claim the operator is choosing between.
    """
    settings = prefs.load()
    engine = engines.current(settings)
    return {**settings.as_dict(),
            "engine": engine.key,
            "model": settings.model_for(engine.key),
            "models": engine.models,
            "engines": engines.catalogue()}


@router.post("/prefs")
def set_prefs(payload: dict, _user: User = Depends(current_user)) -> dict:
    """Change them, refusing a combination that could not work.

    The model is validated against the engine it is *for* — the one being switched to
    in this same request if there is one. Validating against the currently stored
    engine would reject the pair the page sends when it switches both at once, and
    accepting it blindly would store `gpt-5.6-terra` as Claude's model.
    """
    engine_key = payload.get("engine")
    if engine_key is not None and engine_key not in engines.BY_KEY:
        raise HTTPException(status_code=400, detail=f"unknown agent {engine_key!r}")

    settings = prefs.load()
    target = engines.resolve(engine_key or settings.engine)

    model = payload.get("model")
    if model is not None:
        if model not in {entry["id"] for entry in target.models}:
            raise HTTPException(
                status_code=400,
                detail=f"{model!r} is not a {target.label} model")
        settings.set_model_for(target.key, model)

    updated = prefs.update(
        engine=engine_key,
        model=settings.model,
        chatgpt_model=settings.chatgpt_model,
        confirm_edits=payload.get("confirm_edits"),
        allow_web=payload.get("allow_web"),
    )
    return {**updated.as_dict(), "model": updated.model_for(target.key),
            "models": target.models}


# ------------------------------------------------------------------------ threads


def _thread_row(thread: Conversation, preview: str = "") -> dict:
    return {"id": thread.id, "title": thread.title, "format": thread.format,
            "channel_id": thread.channel_id, "pinned": thread.pinned,
            "model": thread.model, "resumable": bool(thread.session_id),
            "updated_at": thread.updated_at.isoformat() if thread.updated_at else "",
            "preview": preview}


def _owned(session: Session, thread_id: int, user: User) -> Conversation:
    thread = session.get(Conversation, int(thread_id))
    if thread is None or thread.user_id != user.id:
        raise HTTPException(status_code=404, detail="no such conversation")
    return thread


@router.get("/threads")
def list_threads(
    fmt: str = "", limit: int = 50,
    user: User = Depends(current_user), session: Session = Depends(get_session),
) -> dict:
    stmt = select(Conversation).where(Conversation.user_id == user.id)
    if fmt:
        stmt = stmt.where(Conversation.format == fmt)
    rows = session.execute(
        stmt.order_by(Conversation.pinned.desc(), Conversation.updated_at.desc())
        .limit(max(1, min(int(limit), 200)))
    ).scalars().all()

    out = []
    for thread in rows:
        last = session.execute(
            select(ChatMessage.text).where(ChatMessage.conversation_id == thread.id)
            .order_by(ChatMessage.id.desc()).limit(1)
        ).scalar_one_or_none()
        out.append(_thread_row(thread, (last or "").strip().replace("\n", " ")[:110]))
    return {"threads": out}


@router.post("/threads")
def new_thread(
    payload: dict | None = None,
    user: User = Depends(current_user), session: Session = Depends(get_session),
) -> dict:
    payload = payload or {}
    thread = Conversation(
        user_id=user.id,
        title=(payload.get("title") or "New chat")[:200],
        format=(payload.get("format") or "")[:16],
        channel_id=payload.get("channel_id"),
        model=prefs.load().model,
    )
    session.add(thread)
    session.commit()
    return _thread_row(thread)


@router.get("/threads/{thread_id}")
def read_thread(
    thread_id: int,
    user: User = Depends(current_user), session: Session = Depends(get_session),
) -> dict:
    thread = _owned(session, thread_id, user)
    return {
        **_thread_row(thread),
        "messages": [
            {"role": m.role, "text": m.text, "tools": m.tool_calls or [],
             "attachments": m.attachments or [],
             "at": m.created_at.isoformat() if m.created_at else ""}
            for m in thread.messages
        ],
    }


@router.patch("/threads/{thread_id}")
def edit_thread(
    thread_id: int, payload: dict,
    user: User = Depends(current_user), session: Session = Depends(get_session),
) -> dict:
    thread = _owned(session, thread_id, user)
    if "title" in payload:
        thread.title = (payload["title"] or "Untitled")[:200]
    if "pinned" in payload:
        thread.pinned = bool(payload["pinned"])
    if "format" in payload:
        thread.format = (payload["format"] or "")[:16]
    session.commit()
    return _thread_row(thread)


@router.delete("/threads/{thread_id}", status_code=204)
def drop_thread(
    thread_id: int,
    user: User = Depends(current_user), session: Session = Depends(get_session),
) -> None:
    session.delete(_owned(session, thread_id, user))
    session.commit()


# -------------------------------------------------------------------- attachments


def describe(path: Path) -> dict:
    """What this file is, and what the agent can honestly do with it."""
    ext = path.suffix.lower()
    if ext in IMAGE_EXT:
        return {"kind": "image",
                "note": "an image — open it with the Read tool, you can see it"}
    if ext in AUDIO_EXT:
        return {"kind": "audio",
                # Said plainly, because a model that cannot hear will otherwise
                # describe how something sounds anyway.
                "note": "audio — you CANNOT listen to it. Measure it with ffprobe or "
                        "the analysis in forgecast/vision rather than describing it"}
    if ext in VIDEO_EXT:
        return {"kind": "video",
                "note": "a video — you cannot watch it. Measure it: "
                        "`forgecast-vision learn-style` reads cut rhythm, grade, "
                        "captions and motion out of it"}
    return {"kind": "file", "note": "a file — read it with the Read tool"}


def safe_name(raw_name: str | None, content_type: str | None) -> str:
    """A filename that is safe to write and still says what the file is.

    The extension is what everything downstream reads. `describe()` decides from it
    whether the agent is told "an image you can see" or "a file"; ffprobe and Pillow
    both use it. So a clipboard paste — which arrives with an empty filename and only
    a MIME type — has to have one derived, or a pasted screenshot is handed to the
    agent as an opaque blob it cannot open.
    """
    raw = Path(raw_name or "").name
    kept = "".join(c for c in raw if c.isalnum() or c in " .-_()").strip(" .")
    stem, suffix = Path(kept).stem, Path(kept).suffix

    if not suffix and content_type:
        # `mimetypes` maps image/png to .png without a table to maintain. Its
        # audio/video coverage is thin, hence the handful of explicit entries.
        extra = {"audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav",
                 "audio/mp4": ".m4a", "audio/flac": ".flac", "audio/webm": ".weba",
                 "video/quicktime": ".mov", "video/x-matroska": ".mkv"}
        base = content_type.split(";")[0].strip().lower()
        suffix = extra.get(base) or mimetypes.guess_extension(base) or ""

    if not stem:
        stem = "pasted"
    return f"{stem}{suffix}"


@router.post("/attach")
async def attach(file: UploadFile = File(...), _user: User = Depends(current_user)):
    raw = file.filename or "pasted"
    safe = safe_name(raw, file.content_type)
    dest = attach_dir() / safe
    # Split once, from the *sanitised* name. Splitting a name that begins with a dot
    # puts the whole thing in `suffix` and leaves `stem` empty, so a de-duplicated
    # ".env" became "-1" with no extension at all.
    stem, suffix = Path(safe).stem, Path(safe).suffix
    index = 1
    while dest.exists():                     # never clobber an earlier attachment
        dest = attach_dir() / f"{stem}-{index}{suffix}"
        index += 1

    total = 0
    try:
        with open(dest, "wb") as out:
            # Chunked rather than `await file.read()`, which materialises the whole
            # upload in memory — a 1 GB reference clip would cost 1 GB of RAM.
            while chunk := await file.read(1 << 20):
                total += len(chunk)
                if total > MAX_ATTACH_BYTES:
                    out.close()
                    dest.unlink(missing_ok=True)
                    return JSONResponse(
                        {"error": f"{raw} is over the "
                                  f"{MAX_ATTACH_BYTES / 1024 ** 3:.1f} GB limit"}, 413)
                out.write(chunk)
    except OSError as exc:
        dest.unlink(missing_ok=True)
        return JSONResponse({"error": f"could not save that: {exc}"}, 500)

    return {"name": dest.name, "path": str(dest), "size": total, **describe(dest)}


@router.get("/file")
def serve_attachment(path: str, _user: User = Depends(current_user)):
    """Serve an attachment back so the chat can show it rather than name it."""
    try:
        resolved = Path(path).resolve()
        resolved.relative_to(attach_dir().resolve())
        if resolved.is_file():
            return FileResponse(resolved)
    except (ValueError, OSError):
        pass
    return JSONResponse({}, 404)


@router.post("/detach")
def detach(payload: dict, _user: User = Depends(current_user)) -> dict:
    """Removing a chip deletes the file — attachments are context, not a library."""
    try:
        resolved = Path(payload.get("path", "")).resolve()
        resolved.relative_to(attach_dir().resolve())
        resolved.unlink(missing_ok=True)
    except (ValueError, OSError):
        pass
    return {"ok": True}


# --------------------------------------------------------------------------- turn


@router.get("/status")
def studio_status(user: User = Depends(current_user)) -> dict:
    """What the right-hand panel shows: the same report the agent gets."""
    return _studio(user).status()


def _title_from(text: str) -> str:
    """A thread's name from its first message, cut at a word."""
    flat = " ".join((text or "").split())
    if len(flat) <= 48:
        return flat or "New chat"
    return flat[:48].rsplit(" ", 1)[0] + "…"


@router.post("/threads/{thread_id}/chat")
async def chat(
    thread_id: int, payload: dict,
    user: User = Depends(current_user), session: Session = Depends(get_session),
):
    thread = _owned(session, thread_id, user)
    message = (payload.get("message") or "").strip()

    files: list[Path] = []
    for raw in payload.get("files") or []:
        try:
            resolved = Path(raw).resolve()
            resolved.relative_to(attach_dir().resolve())
            if resolved.is_file():
                files.append(resolved)
        except (ValueError, OSError):
            continue

    if not message and not files:
        raise HTTPException(status_code=400, detail="nothing to send")
    if len(message) > MAX_MESSAGE_CHARS:
        raise HTTPException(
            status_code=413,
            detail="that is longer than a chat turn should carry — start a run with "
                   "it as the topic, or attach it as a file")

    if thread.id in _IN_FLIGHT:
        raise HTTPException(
            status_code=409,
            detail="this conversation is still working on your last message. Wait for "
                   "it to finish, or start a new chat to ask something else now.")
    _IN_FLIGHT.add(thread.id)

    attachments = [{"name": p.name, "path": str(p), **describe(p)} for p in files]
    session.add(ChatMessage(conversation_id=thread.id, role="user", text=message,
                            attachments=attachments))
    if thread.title == "New chat" and message:
        thread.title = _title_from(message)
    session.commit()

    prompt = message
    if attachments:
        listing = "\n".join(f"  {a['path']}  — {a['note']}" for a in attachments)
        prompt = f"Files attached to this message:\n{listing}\n\n{message}"

    settings = prefs.load()
    resume = thread.session_id or None
    thread_pk = thread.id
    studio = _studio(user)
    # Read here, not inside the stream: `user` belongs to the request session, which is
    # closed by the time the generator runs, and touching a detached instance then
    # raises where nothing can report it. The ChatGPT backend needs the id to tell its
    # out-of-process tool server whose studio to open.
    user_id = user.id
    engine = engines.current(settings)

    def _save(text_parts: list[str], tool_calls: list[dict], session_id: str) -> None:
        """Write the turn down. Called from a `finally`, so it must not raise.

        Its own database session, because the request's session was closed when the
        response started streaming and writing through a closed session is how a whole
        conversation silently fails to save.
        """
        try:
            with SessionLocal() as store:
                row = store.get(Conversation, thread_pk)
                if row is None:
                    return
                if text_parts or tool_calls:
                    store.add(ChatMessage(
                        conversation_id=row.id, role="assistant",
                        text="".join(text_parts), tool_calls=tool_calls))
                if session_id:
                    row.session_id = session_id
                # The model that actually answered, which is the engine's own — not
                # `settings.model`, which is always Claude's. A thread labelled
                # claude-sonnet-5 that ChatGPT answered is a transcript that lies about
                # its own history, and there is no way to tell afterwards.
                row.model = settings.model_for(engine.key)
                store.commit()
        except Exception:                                         # pragma: no cover
            log.exception("could not save the assistant turn")

    def _forget_session(pk: int) -> None:
        """Drop a session id the CLI has forgotten, so it is never resumed again."""
        try:
            with SessionLocal() as store:
                row = store.get(Conversation, pk)
                if row is not None:
                    row.session_id = ""
                    store.commit()
        except Exception:                                         # pragma: no cover
            log.exception("could not clear a dead session id")

    def _remember_session(session_id: str) -> None:
        """Store the session id the moment it is known, not at the end of the turn.

        This is the difference between a chat with a memory and one without. The id
        arrives early and the turn can run for minutes afterwards; if it is only
        written at the end, then any turn that does not reach the end — a closed
        window, a reload, a killed process — leaves the thread with no session to
        resume, and the *next* message starts a brand-new conversation. The agent then
        says things like "I don't have the script in front of me" one turn after you
        pasted it, and nothing looks broken.
        """
        try:
            with SessionLocal() as store:
                row = store.get(Conversation, thread_pk)
                if row is not None and row.session_id != session_id:
                    row.session_id = session_id
                    store.commit()
        except Exception:                                         # pragma: no cover
            log.exception("could not record the session id")

    async def stream():
        text_parts: list[str] = []
        tool_calls: list[dict] = []
        latest_session = resume or ""
        # Set once the turn has been written down, so the `finally` cannot save twice
        # when the generator is closed after a normal finish.
        saved = False
        attempt = resume
        retried = False
        try:
            while True:
                restart = False
                async for event in engines.run(
                    prompt, studio=studio, settings=settings, resume=attempt,
                    permission_mode="default" if settings.confirm_edits else "acceptEdits",
                    allow_web=settings.allow_web, budget_usd=settings.budget_usd,
                    user_id=user_id,
                ):
                    kind = event.get("type")

                    # A session the CLI no longer has. Retried once from scratch instead
                    # of surfacing the error, because otherwise the thread is bricked:
                    # every later message resumes the same dead id, fails identically,
                    # and the only way out is abandoning the conversation.
                    if kind == "error" and event.get("resume_failed") and not retried:
                        retried = True
                        attempt = None
                        restart = True
                        _forget_session(thread_pk)
                        latest_session = ""
                        text_parts.clear()
                        tool_calls.clear()
                        yield json.dumps({
                            "type": "notice",
                            "text": "That conversation's session had expired on this "
                                    "machine, so I started a fresh one. Earlier messages "
                                    "are still above but I cannot see them.",
                        }) + "\n"
                        break
                    if kind == "text":
                        text_parts.append(event.get("text", ""))
                    elif kind == "tool":
                        tool_calls.append({"id": event.get("id", ""),
                                           "name": str(event.get("name", "")).split("__")[-1],
                                           "input": event.get("input") or {}})
                    elif kind == "tool_result":
                        # Matched back onto its call so a reopened thread shows the
                        # measurement under the tool that produced it, not a loose list
                        # of results at the bottom.
                        for call in reversed(tool_calls):
                            if call.get("id") == event.get("id"):
                                call["result"] = event.get("text", "")
                                call["is_error"] = bool(event.get("is_error"))
                                break
                    elif kind in ("result", "session") and event.get("session_id"):
                        if event["session_id"] != latest_session:
                            latest_session = event["session_id"]
                            _remember_session(latest_session)
                    elif kind == "error":
                        text_parts.append(event.get("text", ""))
                    yield json.dumps(event, default=str) + "\n"

                if not restart:
                    break
        except Exception as exc:                                  # pragma: no cover
            log.exception("chat turn failed")
            yield json.dumps({"type": "error",
                              "text": f"{type(exc).__name__}: {exc}"}) + "\n"
        finally:
            # `finally`, not a plain statement after the loop.
            #
            # Closing the window or reloading the page mid-turn makes Starlette close
            # this generator, which raises GeneratorExit at the `yield` above —
            # and GeneratorExit and CancelledError are BaseException, so
            # `except Exception` does not see them. Written after the loop instead,
            # this save is simply skipped: the assistant's reply is lost AND the
            # thread keeps no session id, so the next message starts a brand-new
            # conversation with no memory of this one. A turn here can run for
            # minutes, which makes a mid-turn reload the normal case rather than the
            # unlucky one.
            if not saved:
                saved = True
                _save(text_parts, tool_calls, latest_session)
            _IN_FLIGHT.discard(thread_pk)

        yield json.dumps({"type": "done"}) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


# --------------------------------------------------------------------- connectors


connector_router = APIRouter(prefix="/api/connectors", tags=["connectors"],
                             include_in_schema=False)


@connector_router.get("")
def list_connectors(_user: User = Depends(current_user)) -> dict:
    store = connectors.Store.load()
    return {"connectors": store.listing(),
            "active": sorted(store.active().keys()),
            "note": "A connector gives the agent that service's tools. It is not the "
                    "same as a provider key, which lets the pipeline call a vendor."}


@connector_router.post("")
def save_connector(payload: dict, _user: User = Depends(current_user)) -> dict:
    key = (payload.get("key") or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="which connector?")
    url = (payload.get("url") or "").strip()
    if url and not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400,
                            detail="that does not look like a server URL — it should "
                                   "start with https://")
    store = connectors.Store.load()
    conn = store.set(key, url, payload.get("token") or "",
                     enabled=bool(payload.get("enabled", True)))
    log.info("connector %s %s", key, "configured" if conn.url else "cleared")
    return conn.as_dict()


@connector_router.delete("/{key}", status_code=204)
def drop_connector(key: str, _user: User = Depends(current_user)) -> None:
    connectors.Store.load().remove(key)


@connector_router.post("/{key}/test")
async def test_connector(key: str, _user: User = Depends(current_user)) -> dict:
    """Ask the server who it is. A saved URL that has never been reached is a guess.

    Deliberately a real request to the configured endpoint rather than a URL-shape
    check: the failure this catches is a token that was pasted with a trailing space,
    and no amount of validating the string finds that.
    """
    import httpx

    store = connectors.Store.load()
    conn = store.connections.get(key)
    if conn is None or not conn.url:
        raise HTTPException(status_code=404, detail=f"{key} is not configured")

    config = conn.as_mcp()
    body = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "forgecast", "version": "0.1.0"}}}
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream",
               **config.get("headers", {})}
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.post(conn.url, json=body, headers=headers)
    except httpx.HTTPError as exc:
        return {"ok": False, "detail": f"could not reach it: {type(exc).__name__}: {exc}"}

    if response.status_code in (401, 403):
        return {"ok": False, "status": response.status_code,
                "detail": "reached it, but the token was rejected. Check for a "
                          "trailing space, and that the token is for this workspace."}
    if response.status_code >= 400:
        return {"ok": False, "status": response.status_code,
                "detail": response.text[:200]}

    name = ""
    try:
        payload = response.json()
        name = ((payload.get("result") or {}).get("serverInfo") or {}).get("name", "")
    except ValueError:
        # A streaming transport answers initialize as an SSE frame, which is a
        # perfectly good sign of life even though it is not JSON.
        name = "(streaming server)"
    return {"ok": True, "status": response.status_code, "server": name,
            "detail": f"Connected to {name or 'the server'}. Its tools are available "
                      f"in the next chat turn."}


@connector_router.get("/mcp-config")
def mcp_config(_user: User = Depends(current_user)) -> dict:
    """What the agent will actually be handed. Shown so a mistake is visible."""
    active = connectors.Store.load().active()
    redacted = {}
    for key, config in active.items():
        clean = dict(config)
        if clean.get("headers"):
            clean["headers"] = {k: "••••" for k in clean["headers"]}
        redacted[key] = clean
    return {"servers": redacted,
            "app_tools": f"mcp__{tools.SERVER_NAME}__*",
            "storage": str(get_settings().storage_dir.resolve())}
