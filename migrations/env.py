"""Alembic environment.

The URL comes from the application's own settings rather than alembic.ini, so
`alembic upgrade head` and the running app can never disagree about which database
they are talking to — a mismatch there is how you end up migrating an empty file
while the app keeps using the real one.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from forgecast.config import get_settings
from forgecast.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite cannot ALTER most things in place; batch mode rewrites the table
        # instead, which is the only way a column change lands on the default backend.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
