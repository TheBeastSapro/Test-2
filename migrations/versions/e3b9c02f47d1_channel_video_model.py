"""channel video model

Which image-to-video model a channel's shots are generated on. Empty means the app's
default slug, which is what every channel was already getting — so this migration changes
no existing channel's cost or output. It records a decision that until now could not be
expressed.

Empty rather than the default slug written out, which is the opposite of the choice
`scripting_style` made one revision ago. The difference is what happens when the value
stops resolving. A scripting method names a folder outside the tree that can disappear, so
the column had to hold something that always loads. A model slug names an endpoint at a
vendor that renames variants faster than any table tracks, and the app already prices an
unrecognised slug from its family rather than failing. Writing today's default into every
row would freeze channels onto it: a later default change would silently not apply to any
channel created before it, which is the sort of thing nobody notices until two channels
that were set up identically start costing different amounts.

Revision ID: e3b9c02f47d1
Revises: c7d5b0914ae2
Create Date: 2026-08-04
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3b9c02f47d1"
down_revision: str | None = "c7d5b0914ae2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `server_default` because SQLite cannot add a NOT NULL column to a populated table
    # without one, and this table is populated on every install that has made a channel.
    op.add_column("channels", sa.Column("video_model", sa.String(length=128),
                                        nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("channels", "video_model")
