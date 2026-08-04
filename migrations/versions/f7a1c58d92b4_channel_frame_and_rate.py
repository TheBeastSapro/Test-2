"""channel frame and rate

The height a channel's videos are delivered at, and the frame rate.

Both default to 0, meaning "the app default". That is deliberately not the same as
writing today's default into every row: a later change to the default would then silently
not apply to any channel created before it, and two channels set up identically would
start producing different files with nothing on either to explain the difference.

This changes existing channels' output, and it is worth being explicit about how. Before
this, `nodes/_common.dimensions` resolved 9:16 to 1080x1920 and 1:1 to 1080x1080 but 16:9
to 1280x720 — so vertical and square already rendered at 1080p and the main long-form
format was the single one shipping at 720p. Nothing decided that; it was a fallback that
outlived the two cases written above it. After this migration a channel that has not
chosen a height renders 16:9 at 1920x1080. Vertical and square are unchanged.

Frame rate was pinned at 30 in `VCODEC` and in four filter strings, with no way to change
it. The default stays 30 — it is the right answer for this footage, since the
image-to-video vendors return 24 or 30 natively and encoding those at 60 duplicates
frames — but it is now a choice rather than a constant.

Revision ID: f7a1c58d92b4
Revises: e3b9c02f47d1
Create Date: 2026-08-04
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7a1c58d92b4"
down_revision: str | None = "e3b9c02f47d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `server_default` because SQLite cannot add a NOT NULL column to a populated table
    # without one, and this table is populated on every install that has made a channel.
    op.add_column("channels", sa.Column("video_height", sa.Integer(),
                                        nullable=False, server_default="0"))
    op.add_column("channels", sa.Column("video_fps", sa.Integer(),
                                        nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("channels", "video_fps")
    op.drop_column("channels", "video_height")
