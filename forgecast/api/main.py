from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

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
from .routes_files import router as files_router
from .routes_preview import router as preview_router
from .routes_research import router as research_router
from .routes_settings import router as settings_router
from .routes_setup import router as setup_router
from .routes_skills import router as skills_router
from .routes_styles import router as styles_router
from .routes_web import router as web_router

log = logging.getLogger("forgecast.api")


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
