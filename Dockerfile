# Forgecast: API + worker in one image, selected by the entrypoint command.
#
# One image rather than two because the two processes share every dependency,
# including the expensive one — ffmpeg and its codecs are most of the image, and
# building them twice to save a few megabytes of Python is a bad trade.

FROM python:3.11-slim-bookworm

# ffmpeg is not optional here. It is the renderer, the analyser, and the thing every
# vision measurement runs through; without it the app starts and every run fails at
# the first node. fonts-dejavu supplies the typeface drawtext falls back to, so
# motion graphics have something to draw with on a slim base.
RUN apt-get update && apt-get install --no-install-recommends -y \
        ffmpeg \
        fonts-dejavu-core \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    FORGECAST_STORAGE_DIR=/data/storage \
    FORGECAST_DATABASE_URL=sqlite:////data/forgecast.db

WORKDIR /app

# Dependencies first, so a code change does not reinstall the world.
COPY pyproject.toml README.md ./
COPY forgecast/__init__.py forgecast/__init__.py
RUN pip install --no-cache-dir ".[postgres]"

COPY forgecast/ forgecast/
COPY migrations/ migrations/
COPY alembic.ini docker/entrypoint.sh ./
RUN chmod +x entrypoint.sh && pip install --no-cache-dir --no-deps -e .

# Runs as a non-root user; /data is a volume, so it has to be owned by that user or
# the first write fails.
RUN useradd --create-home --uid 10001 forgecast \
    && mkdir -p /data/storage \
    && chown -R forgecast:forgecast /data /app
USER forgecast

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["api"]
