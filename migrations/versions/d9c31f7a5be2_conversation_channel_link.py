"""conversation channel link

`Conversation.channel_id` has existed since threads did, as a bare `Integer` with no
foreign key, no index, and — the part that matters — nothing anywhere that read it. It
recorded an intention. Every thread was account-wide in practice, which is why "which
chats were about the space channel" had no answer.

This makes it a real relationship. Three things change and each has a reason:

**A foreign key with `SET NULL`.** Not `CASCADE`: a thread outlives the channel it
discussed, and cascading would delete days of transcript along with a channel somebody
removed while tidying up. The cost is a conflation — a thread that never had a channel
and a thread whose channel was deleted both read as null — and that is the cheaper of
the two losses, because it loses a label rather than the work.

**An index on `(channel_id, updated_at)`.** The per-channel CHATS list orders by recency
inside one channel, and without this it scans every thread the account has ever had.

**Nothing is backfilled.** Threads that predate this have no channel and keep none.
Attaching them to the first channel would be a guess that reads as a fact, and on an
account with two channels it would silently file months of unrelated work under whichever
one happened to be created first. A null channel means "not about a channel yet", which
is a real state the shell has to render anyway.

SQLite cannot add a foreign key to an existing column, so the column is rebuilt in a
batch operation. The values survive it — this is a constraint change, not a data change.

Revision ID: d9c31f7a5be2
Revises: f7a1c58d92b4
Create Date: 2026-08-04
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "d9c31f7a5be2"
down_revision: str | None = "f7a1c58d92b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Batch mode because SQLite rebuilds the table to add a constraint. Named explicitly
    # so the downgrade can drop it — an unnamed constraint on SQLite cannot be.
    with op.batch_alter_table("conversations", schema=None) as batch:
        batch.create_foreign_key(
            "fk_conversation_channel", "channels",
            ["channel_id"], ["id"], ondelete="SET NULL",
        )
    op.create_index(
        "ix_conversation_channel_updated", "conversations", ["channel_id", "updated_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_conversation_channel_updated", table_name="conversations")
    with op.batch_alter_table("conversations", schema=None) as batch:
        batch.drop_constraint("fk_conversation_channel", type_="foreignkey")
