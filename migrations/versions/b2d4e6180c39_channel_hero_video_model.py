"""channel hero video model

Which image-to-video model a channel's *hero* shots are generated on — the opening hook,
the reveal, the payoff, the closing shot. `video_model`, added two revisions ago, becomes
the batch model for everything else.

Empty rather than a slug written out, for the same reason `video_model` chose empty and
for one more that is specific to this column.

The shared reason: a model slug names an endpoint at a vendor that renames variants faster
than any table tracks, and the app already prices an unrecognised slug from its family
rather than failing. Writing today's default into every row would freeze channels onto it,
so a later default change would silently not apply to any channel created before it — and
two channels set up identically would start costing different amounts.

The reason particular to this one: an empty hero model means *no upgrade at all*, not "the
app's hero default". There is no hero default and there must not be one. `model_for_tier`
falls an empty hero slug through to the standard model, so every existing channel renders
every shot on exactly the endpoint it already used and this migration changes nobody's bill
by a cent. The alternative — shipping, say, Veo 3.1 as the default hero — would take a
channel quietly from $43.75 a video to something dearer on its next run, in return for a
decision the operator never made. A cost setting may do many things on its own; spending
more is not one of them.

Revision ID: b2d4e6180c39
Revises: f7a1c58d92b4
Create Date: 2026-08-04
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2d4e6180c39"
down_revision: str | None = "f7a1c58d92b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `server_default` because SQLite cannot add a NOT NULL column to a populated table
    # without one, and this table is populated on every install that has made a channel.
    op.add_column("channels", sa.Column("video_model_hero", sa.String(length=128),
                                        nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("channels", "video_model_hero")
