"""Test setup.

Environment variables are set **before** any forgecast import because
`get_settings()` is cached and `db.engine` is created at module import time.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="forgecast-tests-"))
os.environ.setdefault("FORGECAST_DATABASE_URL", f"sqlite:///{_TMP / 'test.db'}")
os.environ.setdefault("FORGECAST_STORAGE_DIR", str(_TMP / "storage"))

# `setdefault` above means an inherited FORGECAST_DATABASE_URL wins — which is how the
# suite is meant to be pointed at Postgres, and also how it can be aimed at a database
# holding real work. The `fresh_database` fixture below runs `drop_all` before every
# single test, so getting this wrong does not fail: it silently destroys everything.
#
# The check is for the two names this project actually uses. It is not a general
# safety net and cannot be one; it is a stop for the specific accident of running the
# suite from a working install, where `sqlite:///./forgecast.db` is exactly what is
# sitting in `.env`.
_url = os.environ["FORGECAST_DATABASE_URL"]
if _url.startswith("sqlite") and Path(_url.split("///", 1)[-1]).name in (
    "forgecast.db", "app.db"
):
    raise SystemExit(
        f"refusing to run: FORGECAST_DATABASE_URL points at {_url}, which is a working "
        "database.\n"
        "Every test drops and recreates the whole schema, so this would delete it.\n"
        "Unset FORGECAST_DATABASE_URL and the suite will use a temporary directory."
    )
os.environ.setdefault("FORGECAST_PROVIDER_MODE", "mock")
os.environ.setdefault("FORGECAST_SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("FORGECAST_SIGNUP_CREDIT_GRANT", "5000")
# The suite creates its users through the signup endpoint, so it needs registration
# open. The shipped default is closed — see test_private_instance.py, which asserts
# both that default and what happens when it is enforced.
os.environ.setdefault("FORGECAST_ALLOW_SIGNUP", "true")

import pytest  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from forgecast import credits as billing  # noqa: E402
from forgecast import nodes  # noqa: E402,F401 - registers node handlers
from forgecast.auth import hash_password  # noqa: E402
from forgecast.db import SessionLocal, engine  # noqa: E402
from forgecast.models import Base, Channel, User  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def session() -> Session:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    finally:
        db.close()


@pytest.fixture
def user(session: Session) -> User:
    row = User(email="tester@example.com", hashed_password=hash_password("supersecret"))
    session.add(row)
    session.flush()
    billing.grant(session, row.id, 10_000, note="test grant")
    session.commit()
    return row


@pytest.fixture
def channel(session: Session, user: User) -> Channel:
    row = Channel(
        user_id=user.id,
        name="Test Channel",
        niche="space",
        voice_id="test-voice",
        target_duration_seconds=30,
        style_profile={"tone": "calm and precise"},
    )
    session.add(row)
    session.commit()
    return row


@pytest.fixture
def storage_dir() -> Path:
    return Path(os.environ["FORGECAST_STORAGE_DIR"])
