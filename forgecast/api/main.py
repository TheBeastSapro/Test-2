from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .. import nodes  # noqa: F401 - registers node handlers
from ..config import get_settings
from ..db import init_db
from ..providers import ProviderError
from . import runner
from .local import router as local_router
from .media import router as media_router
from .routes_api import router as api_router
from .routes_preview import router as preview_router
from .routes_research import router as research_router
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
    # Artifacts are served through signed, expiring, per-user URLs rather than a
    # static mount of the storage directory. See `api.media` — a plain mount hands
    # every run's video to anyone who can guess a path.
    app.include_router(media_router)
    # Desktop-only routes. They are registered unconditionally and refuse themselves
    # when `local_mode` is off, so that whether a route exists does not depend on the
    # order in which settings were loaded.
    app.include_router(local_router)
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
