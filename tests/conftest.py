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
os.environ.setdefault("FORGECAST_PROVIDER_MODE", "mock")
os.environ.setdefault("FORGECAST_SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("FORGECAST_SIGNUP_CREDIT_GRANT", "5000")

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
