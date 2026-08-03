"""Database schema.

Design notes that matter:

* A **Run** is one video. It owns a graph of **Nodes**. Nodes are persisted rows,
  not in-memory tasks, because a run can sit paused at a human decision gate for
  days and must survive process restarts.
* **Artifacts** are content-addressed files on disk (or object storage) referenced
  by row, so a node can be re-run without losing the previous take.
* Credits are an append-only **LedgerEntry** table. Never a mutable balance column:
  provider spend is real money and the history has to be auditable.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------- enums


class RunStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    awaiting_approval = "awaiting_approval"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class NodeStatus(str, enum.Enum):
    pending = "pending"
    ready = "ready"
    running = "running"
    awaiting_approval = "awaiting_approval"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class LedgerKind(str, enum.Enum):
    grant = "grant"          # free/plan credits added
    purchase = "purchase"    # credit pack bought
    reserve = "reserve"      # hold taken when a run starts
    release = "release"      # unused hold returned
    spend = "spend"          # settled provider cost
    refund = "refund"        # spend reversed after a provider failure


class MemoryKind(str, enum.Enum):
    style = "style"          # durable channel voice/style facts
    decision = "decision"    # what the operator approved
    revision = "revision"    # what the operator rejected, and why
    performance = "performance"  # post-publish analytics signal


class Plan(str, enum.Enum):
    free = "free"
    pro = "pro"
    studio = "studio"
    max = "max"


PLAN_MONTHLY_CREDITS: dict[Plan, int] = {
    Plan.free: 0,
    Plan.pro: 3_000,
    Plan.studio: 12_000,
    Plan.max: 60_000,
}


# --------------------------------------------------------------------------- tenancy


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    plan: Mapped[Plan] = mapped_column(Enum(Plan), default=Plan.free)
    plan_renews_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    channels: Mapped[list[Channel]] = relationship(back_populates="user")
    provider_keys: Mapped[list[ProviderKey]] = relationship(back_populates="user")


class ProviderKey(Base):
    """Bring-your-own-key. Ciphertext only; see forgecast.crypto."""

    __tablename__ = "provider_keys"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_user_provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    ciphertext: Mapped[str] = mapped_column(Text)
    masked: Mapped[str] = mapped_column(String(64))
    fingerprint: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="provider_keys")


# --------------------------------------------------------------------------- channel


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    niche: Mapped[str] = mapped_column(String(200), default="")
    language: Mapped[str] = mapped_column(String(16), default="en")

    # Persona / render defaults the agent applies to every run on this channel.
    voice_id: Mapped[str] = mapped_column(String(128), default="")
    avatar_id: Mapped[str] = mapped_column(String(128), default="")
    aspect_ratio: Mapped[str] = mapped_column(String(16), default="16:9")
    target_duration_seconds: Mapped[int] = mapped_column(Integer, default=480)

    # Free-form learned profile: tone, banned words, hook patterns, CTA, etc.
    style_profile: Mapped[dict] = mapped_column(JSON, default=dict)

    # Encrypted YouTube OAuth refresh token for the publish node.
    youtube_channel_id: Mapped[str] = mapped_column(String(128), default="")
    youtube_credentials: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="channels")
    runs: Mapped[list[Run]] = relationship(back_populates="channel")
    memories: Mapped[list[ChannelMemory]] = relationship(back_populates="channel")


class ChannelMemory(Base):
    """The 'learning agent'. Every gate decision becomes retrievable context."""

    __tablename__ = "channel_memories"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[MemoryKind] = mapped_column(Enum(MemoryKind))
    content: Mapped[str] = mapped_column(Text)
    # Which node produced the lesson, so retrieval can be scoped per stage.
    node_type: Mapped[str] = mapped_column(String(64), default="")
    weight: Mapped[float] = mapped_column(default=1.0)
    run_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    channel: Mapped[Channel] = relationship(back_populates="memories")


Index("ix_memory_channel_kind", ChannelMemory.channel_id, ChannelMemory.kind)


# --------------------------------------------------------------------------- runs


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    topic: Mapped[str] = mapped_column(Text)
    pipeline: Mapped[str] = mapped_column(String(64), default="faceless_longform")
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.queued, index=True)

    # Operator overrides for this run only (duration, style hints, gate choices).
    options: Mapped[dict] = mapped_column(JSON, default=dict)

    credits_reserved: Mapped[int] = mapped_column(Integer, default=0)
    credits_spent: Mapped[int] = mapped_column(Integer, default=0)

    error: Mapped[str | None] = mapped_column(Text)

    # Cooperative lease so multiple workers never execute the same run.
    locked_by: Mapped[str | None] = mapped_column(String(64))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    channel: Mapped[Channel] = relationship(back_populates="runs")
    nodes: Mapped[list[Node]] = relationship(
        back_populates="run", order_by="Node.id", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    events: Mapped[list[RunEvent]] = relationship(
        back_populates="run", order_by="RunEvent.id", cascade="all, delete-orphan"
    )

    @property
    def is_terminal(self) -> bool:
        return self.status in {RunStatus.completed, RunStatus.failed, RunStatus.cancelled}


class Node(Base):
    __tablename__ = "nodes"
    __table_args__ = (UniqueConstraint("run_id", "key", name="uq_run_node_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)

    key: Mapped[str] = mapped_column(String(64))       # stable id inside the graph
    type: Mapped[str] = mapped_column(String(64))      # dispatch key into the node registry
    title: Mapped[str] = mapped_column(String(200))
    depends_on: Mapped[list] = mapped_column(JSON, default=list)
    params: Mapped[dict] = mapped_column(JSON, default=dict)

    status: Mapped[NodeStatus] = mapped_column(
        Enum(NodeStatus), default=NodeStatus.pending, index=True
    )
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)

    output: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)

    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    credits_spent: Mapped[int] = mapped_column(Integer, default=0)

    # Gate bookkeeping: what the human said when they revised this node.
    review_feedback: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    run: Mapped[Run] = relationship(back_populates="nodes")
    artifacts: Mapped[list[Artifact]] = relationship(back_populates="node")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id", ondelete="SET NULL"))

    kind: Mapped[str] = mapped_column(String(32))   # script | audio | image | video | json
    path: Mapped[str] = mapped_column(Text)         # local path or object-store URI
    mime: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    # Bumped when a node is re-run after a revision, so old takes stay inspectable.
    take: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[Run] = relationship(back_populates="artifacts")
    node: Mapped[Node | None] = relationship(back_populates="artifacts")


class RunEvent(Base):
    """Append-only log powering the live pipeline view and the audit trail."""

    __tablename__ = "run_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    node_key: Mapped[str | None] = mapped_column(String(64))
    level: Mapped[str] = mapped_column(String(16), default="info")
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[Run] = relationship(back_populates="events")


# --------------------------------------------------------------------------- billing


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_ledger_idempotency"),
        Index("ix_ledger_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[LedgerKind] = mapped_column(Enum(LedgerKind))

    # Signed: grants/releases/refunds are positive, reserves/spends negative.
    delta: Mapped[int] = mapped_column(Integer)
    balance_after: Mapped[int] = mapped_column(Integer)

    run_id: Mapped[int | None] = mapped_column(Integer, index=True)
    node_key: Mapped[str | None] = mapped_column(String(64))
    provider: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str] = mapped_column(Text, default="")
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ----------------------------------------------------------------------- the chat


class Conversation(Base):
    """One chat thread with the agent.

    Threads are rows rather than browser state for the reason Rookcast keeps a list
    of them down the side: the work is long. Setting up a channel, mining a niche and
    getting a run through its gates spans days, and a transcript that dies with the
    window means re-explaining the channel every morning.

    `session_id` is the Claude Code CLI's own id for this conversation. Storing it is
    what lets the next turn resume rather than start over — without it the agent
    re-reads the same state every message and still contradicts itself.
    """

    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversation_user_updated", "user_id", "updated_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="New chat")
    # Which workspace it belongs to: "longform", "shorts", or "" for neither.
    format: Mapped[str] = mapped_column(String(16), default="")
    channel_id: Mapped[int | None] = mapped_column(Integer)
    session_id: Mapped[str] = mapped_column(String(128), default="")
    model: Mapped[str] = mapped_column(String(64), default="")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan",
        order_by="ChatMessage.id",
    )


class ChatMessage(Base):
    """One turn in a thread, stored as it was shown.

    Tool calls are kept alongside the text, not discarded. Re-opening a thread and
    seeing only the prose loses the part that says what the agent actually *did* —
    which channel it read, which run it started — and that is the part worth
    scrolling back for.
    """

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))          # "user" | "assistant"
    text: Mapped[str] = mapped_column(Text, default="")
    # [{"name": "study_youtube_channel", "input": {...}}, ...]
    tool_calls: Mapped[list] = mapped_column(JSON, default=list)
    attachments: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
