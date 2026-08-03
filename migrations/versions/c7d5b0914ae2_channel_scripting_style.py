"""channel scripting style

Which scripting method a channel's scripts are written to. The built-in house method is
the default and needs no configuration, so this migration changes nothing about how any
existing channel writes — it records the method those channels were already getting.

The alternatives are the operator's own document folders, which live outside the tree and
can therefore stop resolving. That is why the default is the built-in slug rather than
empty: an empty column would have to be interpreted at every read site, and the site that
forgets is a run written to no method at all.

Revision ID: c7d5b0914ae2
Revises: a4e2d81b6f03
Create Date: 2026-08-03
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7d5b0914ae2"
down_revision: str | None = "a4e2d81b6f03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `server_default` for the same reason `voice_vendor` needed one: SQLite cannot add a
    # NOT NULL column to a populated table without it, and this table is populated on
    # every install that has ever made a channel. The literal is `forgecast.scripting`'s
    # HOUSE_SLUG — a migration must not import application code, because it has to keep
    # running against a future version where that constant has moved.
    op.add_column("channels", sa.Column("scripting_style", sa.String(length=64),
                                        nullable=False, server_default="house"))


def downgrade() -> None:
    op.drop_column("channels", "scripting_style")
