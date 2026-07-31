#!/usr/bin/env bash
# Container entrypoint: migrate, optionally bootstrap the owner, then run.
#
#   api     the web app (default)
#   worker  the background run advancer
#   shell   a prompt, for `docker compose run --rm app shell`
#   ...     anything else is executed verbatim
#
# Migrations run here rather than in the application so that two containers starting
# at once cannot both migrate: only the api role does it, and the worker waits for the
# schema to exist before it starts claiming runs.

set -euo pipefail

ROLE="${1:-api}"
shift || true

wait_for_schema() {
    # The worker must not poll a database whose tables do not exist yet. Ten seconds
    # is generous for SQLite and enough for Postgres to accept a first connection.
    for _ in $(seq 1 20); do
        if python -c "
import sys
from sqlalchemy import inspect
from forgecast.db import engine
sys.exit(0 if inspect(engine).has_table('runs') else 1)
" 2>/dev/null; then
            return 0
        fi
        sleep 0.5
    done
    echo "entrypoint: gave up waiting for the schema" >&2
    return 1
}

# Everything runs through `python -m` rather than a console script. The scripts are
# installed in the image, but relying on them means the entrypoint breaks whenever the
# package is installed a slightly different way — and it fails as "cannot execute: Is
# a directory" when the name happens to match a directory in the working tree, which
# is not a message that points at the cause.
migrate() {
    echo "entrypoint: applying migrations"
    python -m alembic upgrade head
}

bootstrap_owner() {
    # Only when an owner email is configured. Idempotent: `forgecast bootstrap` will
    # not recreate the account or re-grant credits on a restart.
    if [ -n "${FORGECAST_OWNER_EMAIL:-}" ]; then
        echo "entrypoint: bootstrapping ${FORGECAST_OWNER_EMAIL}"
        python -m forgecast.cli bootstrap --email "${FORGECAST_OWNER_EMAIL}" \
            --grant "${FORGECAST_OWNER_GRANT:-10000}" \
            --channel "${FORGECAST_OWNER_CHANNEL:-My Channel}"
    fi
}

case "$ROLE" in
    api)
        migrate
        bootstrap_owner
        exec python -m uvicorn forgecast.api.main:app \
            --host "${FORGECAST_BIND_HOST:-0.0.0.0}" \
            --port "${FORGECAST_PORT:-8000}" \
            --proxy-headers \
            --forwarded-allow-ips="${FORGECAST_FORWARDED_ALLOW_IPS:-127.0.0.1}" \
            "$@"
        ;;
    worker)
        wait_for_schema
        exec python -m forgecast.worker "$@"
        ;;
    migrate)
        migrate
        ;;
    bootstrap)
        migrate
        exec python -m forgecast.cli bootstrap "$@"
        ;;
    shell)
        exec bash "$@"
        ;;
    *)
        exec "$ROLE" "$@"
        ;;
esac
