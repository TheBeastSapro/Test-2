"""Channel memory — the part that makes the agent feel like it learns.

There is no vector database here on purpose. What actually improves output is a
short, high-signal list of things the operator has approved or rejected on *this*
channel, injected into the prompt for *this* stage. Recency and stage-scoping beat
semantic similarity when the corpus is a few hundred lines. Swap in embeddings when
a channel has thousands of memories and this starts to blur.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Channel, ChannelMemory, MemoryKind

MAX_INJECTED = 12
MAX_CHARS = 2_000


def remember(
    session: Session,
    channel_id: int,
    kind: MemoryKind,
    content: str,
    *,
    node_type: str = "",
    weight: float = 1.0,
    run_id: int | None = None,
) -> ChannelMemory | None:
    content = (content or "").strip()
    if not content:
        return None
    entry = ChannelMemory(
        channel_id=channel_id,
        kind=kind,
        content=content[:2000],
        node_type=node_type,
        weight=weight,
        run_id=run_id,
    )
    session.add(entry)
    session.flush()
    return entry


def recall(
    session: Session, channel_id: int, *, node_type: str = "", limit: int = MAX_INJECTED
) -> list[ChannelMemory]:
    """Most relevant memories first: stage-specific before general, recent before old."""
    stmt = select(ChannelMemory).where(ChannelMemory.channel_id == channel_id)
    rows = list(session.execute(stmt).scalars().all())

    def rank(entry: ChannelMemory) -> tuple:
        stage_match = 1 if (node_type and entry.node_type == node_type) else 0
        # A rejection teaches more than an approval, so weight revisions up.
        kind_bonus = {
            MemoryKind.revision: 3,
            MemoryKind.style: 2,
            MemoryKind.performance: 2,
            MemoryKind.decision: 1,
        }.get(entry.kind, 0)
        return (stage_match, kind_bonus, entry.weight, entry.id)

    rows.sort(key=rank, reverse=True)
    return rows[:limit]


def prompt_block(session: Session, channel: Channel, *, node_type: str = "") -> str:
    """Render channel identity + learned lessons as a prompt fragment."""
    lines: list[str] = []

    profile = channel.style_profile or {}
    if profile:
        lines.append("CHANNEL STYLE PROFILE:")
        for key, value in profile.items():
            if value in (None, "", [], {}):
                continue
            rendered = ", ".join(map(str, value)) if isinstance(value, list) else value
            lines.append(f"- {key.replace('_', ' ')}: {rendered}")

    memories = recall(session, channel.id, node_type=node_type)
    if memories:
        lines.append("")
        lines.append("LESSONS FROM PAST RUNS ON THIS CHANNEL (obey these):")
        for entry in memories:
            tag = entry.kind.value.upper()
            lines.append(f"- [{tag}] {entry.content}")

    block = "\n".join(lines)
    return block[:MAX_CHARS]


def learn_from_revision(
    session: Session, channel_id: int, node_type: str, feedback: str, run_id: int | None = None
) -> None:
    """A gate rejection is the single most valuable training signal available."""
    remember(
        session,
        channel_id,
        MemoryKind.revision,
        f"When producing the {node_type}, the operator asked for: {feedback}",
        node_type=node_type,
        weight=2.0,
        run_id=run_id,
    )


def learn_from_approval(
    session: Session, channel_id: int, node_type: str, summary: str, run_id: int | None = None
) -> None:
    remember(
        session,
        channel_id,
        MemoryKind.decision,
        f"Approved {node_type}: {summary}",
        node_type=node_type,
        weight=0.5,
        run_id=run_id,
    )
