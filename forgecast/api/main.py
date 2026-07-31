from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import nodes  # noqa: F401 - registers node handlers
from ..config import get_settings
from ..db import init_db
from ..providers import ProviderError
from . import runner
from .routes_api import router as api_router
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

    # Artifacts are served straight off disk in development. In production put them
    # in object storage behind signed URLs — this mount has no per-user authorisation.
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/files", StaticFiles(directory=settings.storage_dir), name="files")

    @app.exception_handler(ProviderError)
    async def provider_error_handler(_request: Request, exc: ProviderError) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={"error": "provider_error", "provider": exc.provider, "detail": str(exc)},
        )

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict:
        return {"ok": True, "provider_mode": settings.provider_mode}

    return app


app = create_app()
