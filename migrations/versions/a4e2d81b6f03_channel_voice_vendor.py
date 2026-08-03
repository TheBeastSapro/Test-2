"""channel voice vendor

Which narration vendor a channel uses, because the two that are supported are paid for
differently and the choice therefore has to persist. ElevenLabs issues its key against a
subscription whose character allowance is already paid for; MiniMax bills text-to-speech
against an API balance. A channel set to one must not quietly drift to the other.

Empty means "let the default routing decide", which is what every existing channel gets —
so this migration changes no behaviour on an install that has not asked for MiniMax.

Revision ID: a4e2d81b6f03
Revises: 9c1f3a7b52d0
Create Date: 2026-08-03
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4e2d81b6f03"
down_revision: str | None = "9c1f3a7b52d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `server_default=""` rather than a plain non-null column: SQLite cannot add a NOT NULL
    # column to a populated table without one, and this table is populated on every
    # install that has ever made a channel.
    op.add_column("channels", sa.Column("voice_vendor", sa.String(length=64),
                                        nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("channels", "voice_vendor")
