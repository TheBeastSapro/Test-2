from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings
from .models import Base

log = logging.getLogger("forgecast.db")


def _make_engine():
    settings = get_settings()
    url = settings.database_url
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        # check_same_thread=False so the worker thread and request threads share it.
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - driver glue
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.close()

    return engine


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    """Create tables, and record that they are already at the latest migration.

    Two mechanisms create schema here: `create_all` for a one-command start, and
    Alembic for a deployment that has to evolve. They have to agree, and the stamp is
    what makes them agree. Without it, a fresh instance that booted the app first
    would have every table but no `alembic_version` row, so the first
    `alembic upgrade head` would try to create tables that already exist and fail —
    at exactly the moment you least want a migration to fail.
    """
    Base.metadata.create_all(engine)
    _stamp_head_if_unstamped()


def _stamp_head_if_unstamped() -> None:
    """Mark a freshly created database as being at head. Never re-stamps."""
    try:
        from alembic.config import Config
        from alembic.migration import MigrationContext
        from alembic.script import ScriptDirectory
    except ImportError:  # pragma: no cover - alembic is an install-time dependency
        return

    root = Path(__file__).resolve().parent.parent
    ini = root / "alembic.ini"
    if not ini.exists():  # installed as a package without the migration tree
        return

    try:
        with engine.begin() as connection:
            context = MigrationContext.configure(connection)
            if context.get_current_heads():
                return  # already under Alembic's control; leave it alone
            config = Config(str(ini))
            config.set_main_option("script_location", str(root / "migrations"))
            heads = ScriptDirectory.from_config(config).get_heads()
            if heads:
                context.stamp(ScriptDirectory.from_config(config), "head")
    except Exception:  # pragma: no cover - a stamp failure must not stop startup
        log.warning("could not stamp the migration version", exc_info=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
