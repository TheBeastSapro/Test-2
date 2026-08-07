from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import nodes  # noqa: F401 - registers node handlers
from ..config import get_settings
from ..db import init_db
from ..providers import ProviderError
from . import runner
from .local import router as local_router
from .media import router as media_router
from .routes_activity import router as activity_router
from .routes_agent import connector_router
from .routes_agent import router as agent_router
from .routes_analytics import router as analytics_router
from .routes_api import router as api_router
from .routes_channel import router as channel_router
from .routes_cloud import router as cloud_router
from .routes_edit import router as edit_router
from .routes_files import router as files_router
from .routes_preview import router as preview_router
from .routes_research import router as research_router
from .routes_settings import router as settings_router
from .routes_setup import router as setup_router
from .routes_skills import router as skills_router
from .routes_styles import router as styles_router
from .routes_voice import router as voice_router
from .routes_web import router as web_router

log = logging.getLogger("forgecast.api")

# What each status actually means to somebody looking at it, in this app's terms.
# Starlette's own phrases are correct and useless — "Not Found" does not say what was
# not found or what to do instead, and that is the whole job of an error page.
_ERROR_COPY = {
    404: ("There is no page here",
          "The address does not match anything this app serves. If you followed a link "
          "from somewhere, it is probably out of date — the studio below is the way "
          "back in."),
    403: ("You are not signed in to see this",
          "This belongs to an account, and the current session is not it. Signing in "
          "again is usually all this needs."),
    405: ("That address does not take this kind of request",
          "The page exists but the method does not. This normally means a form or a "
          "bookmark is pointing at something that has since changed shape."),
    500: ("Something failed on this machine",
          "The error is recorded in the log. Nothing was charged and no run was "
          "cancelled — a stage that failed can be retried from the run's own page."),
}

# The API surface, which keeps answering in JSON whatever the browser asks for. Matched
# by prefix rather than by router, because the check runs inside an exception handler
# where the route that would have matched is exactly the thing that did not exist.
_API_PREFIXES = ("/api/", "/healthz", "/static/", "/local/", "/media/")


def _is_api_path(path: str) -> bool:
    return path.startswith(_API_PREFIXES)


def _error_page(request: Request, code: int, headline: str, detail: str):
    """The error, rendered inside the ordinary shell.

    Imports are local because this reaches back into the web routes, and importing
    those at module scope would close a cycle: routes_web imports the app.
    """
    from ..auth import optional_user
    from ..db import session_scope
    from .routes_web import TEMPLATES, shell

    # The shell wants a signed-in user and a session. Neither is guaranteed here —
    # this runs for signed-out requests, and for crashes whose cause may be the
    # database itself — so it falls back to a bare frame rather than raising a second
    # error while reporting the first.
    frame: dict = {"nav": "", "formats": [], "format_counts": {}, "credits": 0,
                   "recent_runs": [], "user": None}
    try:
        with session_scope() as session:
            user = optional_user(request, session)
            if user is not None:
                frame = shell(session, user, "")
    except Exception:                                              # pragma: no cover
        log.debug("error page rendered without a shell", exc_info=True)

    return TEMPLATES.TemplateResponse(
        request, "error.html",
        {**frame, "settings": get_settings(), "code": code, "headline": headline,
         "detail": detail, "path": request.url.path},
        status_code=code,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    # Sync endpoints run in a threadpool and cannot see this loop on their own.
    runner.bind_loop(asyncio.get_running_loop())
    log.info("forgecast api up (provider_mode=%s)", settings.provider_mode)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Forgecast",
        version="0.1.0",
        summary="Agent platform that builds and runs faceless video channels.",
        lifespan=lifespan,
    )

    app.include_router(api_router)
    app.include_router(web_router)
    # The studio: watch a run before it renders. Registered after the web routes so
    # `/runs/{id}/preview` is matched by its own handler rather than swallowed by the
    # run detail route's path converter.
    app.include_router(preview_router)
    app.include_router(research_router)
    app.include_router(styles_router)
    # One channel as a place, at `/c/{id}`. Every other entry in the rail is the
    # account, which is invisible with one channel and is the whole problem with two.
    app.include_router(channel_router)
    # The chat and everything behind it. Registered before the web routes' catch-alls
    # so `/api/agent/...` is never matched by a page route's path converter.
    app.include_router(agent_router)
    app.include_router(connector_router)
    app.include_router(settings_router)
    # Setup is a page in the app rather than a console or a second UI toolkit:
    # the window is already open, and the stylesheet already exists.
    app.include_router(setup_router)
    # Somewhere to look at what the runs actually wrote, and the
    # instruction documents the agent loads when they apply.
    app.include_router(files_router)
    app.include_router(skills_router)
    # What the agent has spent its tool calls on, and where the
    # credits actually went — both read from rows that already exist.
    app.include_router(activity_router)
    app.include_router(analytics_router)
    # Artifacts are served through signed, expiring, per-user URLs rather than a
    # static mount of the storage directory. See `api.media` — a plain mount hands
    # every run's video to anyone who can guess a path.
    app.include_router(media_router)
    # Desktop-only routes. They are registered unconditionally and refuse themselves
    # when `local_mode` is off, so that whether a route exists does not depend on the
    # order in which settings were loaded.
    app.include_router(local_router)

    # Cloud backup. The package under `forgecast/cloud/` has been complete and tested
    # since it was written — manifest, snapshot, git transport, restore, device flow —
    # and had no HTTP end at all, so from inside the application it was indistinguishable
    # from a feature that did not exist. It was reported as missing. Registered
    # unconditionally: every endpoint asks `cloud.enabled()` first, and an install that
    # never turns it on still never opens a socket to GitHub.
    app.include_router(cloud_router)

    # The other direction: a video somebody hands the app, rather than one it generates.
    # `forgecast/ingest`, `forgecast/edit` and `forgecast/layers` were complete and
    # tested and had no importer anywhere in the tree, so the whole "here is a video,
    # edit it" direction existed on disk and nowhere else. Registered unconditionally:
    # the heavy readers are an optional extra, and every endpoint reports what it cannot
    # measure as something the app can install rather than failing.
    app.include_router(edit_router)

    # Signing in to a voice vendor with a subscription rather than a key. The CLI
    # adapter, the auth reader and the routing to it were all built and Settings offered
    # exactly one thing for that vendor: a box to paste an API key — the route the CLI
    # adapter exists to avoid, since a key bills per character and the plan does not.
    app.include_router(voice_router)

    # The stylesheet and the chat's script. A real mount rather than a route per file:
    # these are the only static assets, they are part of the package, and they must
    # keep working from a zip unpacked anywhere — hence a path resolved from this
    # module rather than from the working directory.
    static_dir = Path(__file__).resolve().parent.parent / "web" / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    settings.storage_dir.mkdir(parents=True, exist_ok=True)

    @app.exception_handler(ProviderError)
    async def provider_error_handler(_request: Request, exc: ProviderError) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={"error": "provider_error", "provider": exc.provider, "detail": str(exc)},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        """An HTTP error, answered in the shape the caller asked for.

        A browser that follows a stale bookmark used to get `{"detail":"Not Found"}`
        rendered as text on a white page — an API's error handed to a person, with no
        navigation on it and nothing saying what to do next. That is not a rare path in
        a local app whose operator types URLs and keeps bookmarks.

        The split is on Accept, not on the path prefix. `/api/...` is the obvious JSON
        caller but not the only one: the chat's own fetches, the setup stream and any
        script hitting a page route all want the JSON, and a page route can 404 too.
        Whoever did not ask for HTML keeps the response they have always had.
        """
        wants_html = "text/html" in request.headers.get("accept", "")
        if not wants_html or _is_api_path(request.url.path):
            return await http_exception_handler(request, exc)

        code = exc.status_code
        headline, detail = _ERROR_COPY.get(code, (
            "Something went wrong",
            str(exc.detail) if exc.detail else "No further detail was recorded.",
        ))
        return _error_page(request, code, headline, detail)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        """A crash, shown as a page rather than as the word "Internal Server Error".

        The 500 copy existed and nothing could reach it: only HTTPException was
        handled, so an ordinary bug answered with Starlette's bare plain-text body —
        no navigation, no sign the app was still running, and nothing saying whether
        the run in progress had survived. This is the same defect the 404 had, on the
        path where the operator is already having a bad time.

        The traceback stays in the log and out of the page. It is already logged by
        the server, and a stack trace on screen tells the operator nothing they can
        act on while showing them file paths from inside the install.
        """
        log.exception("unhandled error on %s", request.url.path)
        if "text/html" not in request.headers.get("accept", "") or _is_api_path(
            request.url.path
        ):
            raise exc            # JSON callers keep the 500 they have always had.
        headline, detail = _ERROR_COPY[500]
        return _error_page(request, 500, headline, detail)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict:
        from ..render.ffmpeg import ffmpeg_available

        return {
            "ok": True,
            "provider_mode": settings.provider_mode,
            "ffmpeg": ffmpeg_available(),
        }

    return app


app = create_app()
