"""Engine behaviour: gates, revisions, cascading invalidation, and a real render."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from forgecast import credits as billing
from forgecast.db import SessionLocal
from forgecast.graph.engine import GraphEngine, create_run
from forgecast.models import (
    Channel,
    ChannelMemory,
    MemoryKind,
    Node,
    NodeStatus,
    Run,
    RunStatus,
    User,
)


def engine() -> GraphEngine:
    return GraphEngine(SessionLocal, worker_id="test", concurrency=2)


def _gate(session: Session, run_id: int) -> Node | None:
    return session.execute(
        select(Node).where(Node.run_id == run_id, Node.status == NodeStatus.awaiting_approval)
    ).scalars().first()


async def _drive(run_id: int, *, approve: bool = True, max_gates: int = 8) -> RunStatus:
    """Advance a run, approving each gate it stops at."""
    graph = engine()
    for _ in range(max_gates + 1):
        status = await graph.advance(run_id)
        if status is not RunStatus.awaiting_approval or not approve:
            return status
        with SessionLocal() as session:
            node = _gate(session, run_id)
            if node is None:
                return status
            graph.approve(session, node, note="test approval")
            session.commit()
    return status


async def test_run_stops_at_the_first_gate(session: Session, channel: Channel):
    run = create_run(session, channel=channel, topic="Gate test", pipeline="faceless_shorts")
    session.commit()

    status = await engine().advance(run.id)

    assert status is RunStatus.awaiting_approval
    with SessionLocal() as check:
        waiting = _gate(check, run.id)
        assert waiting is not None and waiting.key == "brief"
        # Nothing downstream may have run.
        script = check.execute(
            select(Node).where(Node.run_id == run.id, Node.key == "script")
        ).scalar_one()
        assert script.status is NodeStatus.pending


async def test_full_run_completes_and_renders_a_real_video(session: Session, channel: Channel):
    run = create_run(
        session, channel=channel, topic="Why deep-sea cables keep breaking",
        pipeline="faceless_shorts", options={"target_seconds": 20},
    )
    run_id = run.id
    session.commit()

    status = await _drive(run_id)
    assert status is RunStatus.completed, f"run ended as {status}"

    with SessionLocal() as check:
        finished = check.get(Run, run_id)
        assert all(node.status is NodeStatus.completed for node in finished.nodes)

        final = [
            a for a in finished.artifacts
            if a.kind == "video" and (a.meta or {}).get("role") == "final"
        ]
        assert len(final) == 1
        path = Path(final[0].path)
        assert path.exists() and path.stat().st_size > 50_000

        from forgecast.render import ffprobe_duration

        assert ffprobe_duration(path) > 5

        published = next(n for n in finished.nodes if n.key == "publish")
        assert published.output["url"].startswith("https://www.youtube.com/watch?v=")


async def test_render_applies_motion_graphics_and_records_what_it_did(
    session: Session, channel: Channel
):
    """Motion is opt-out, so an ordinary run must come out animated.

    Checked by comparing each animated scene's clip against its own pre-motion
    intermediate: a motion pass that silently did nothing would still exit 0 and still
    produce a playable video, which is exactly how every bug in this area presented.
    """
    channel.style_profile = {**(channel.style_profile or {}),
                             "render_spec": {"motion_intensity": 0.82}}
    run = create_run(
        session, channel=channel, topic="Why deep-sea cables keep breaking",
        pipeline="faceless_shorts", options={"target_seconds": 20},
    )
    run_id = run.id
    session.commit()

    assert await _drive(run_id) is RunStatus.completed

    with SessionLocal() as check:
        render = check.execute(
            select(Node).where(Node.run_id == run_id, Node.key == "render")
        ).scalar_one()
        motion = render.output["motion"]

        # 0.82 measured intensity must not pick a slow look.
        assert motion["intensity"] >= 0.7, motion
        animated = [item for item in motion["scenes"] if item["kind"] != "none"]
        assert animated, f"nothing animated: {motion['scenes']}"
        assert animated[0]["kind"] == "title"
        # Every plan explains itself, so a surprising layout can be audited.
        assert all(item["reason"] for item in motion["scenes"])

        workdir = Path(render.output["video_path"]).parent / "work"
        passes = sorted(workdir.glob("scene_*_motion.mp4"))
        assert len(passes) == len(animated)

        altered = _mean_frame_delta(workdir / passes[0].name.replace("_motion", ""),
                                    passes[0])
        assert altered > 0.3, f"the motion pass changed nothing (delta {altered:.3f})"


def _mean_frame_delta(first: Path, second: Path) -> float:
    """Mean absolute per-pixel difference between two clips, at a small scale."""
    import numpy as np

    def frames(path: Path):
        raw = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
             "-vf", "scale=160:90", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
            capture_output=True, check=True).stdout
        return np.frombuffer(raw, dtype=np.uint8).reshape(-1, 90, 160).astype(np.float32)

    left, right = frames(first), frames(second)
    count = min(len(left), len(right))
    return float(np.abs(left[:count] - right[:count]).mean())


async def test_completed_run_returns_every_unspent_credit(session: Session, user: User,
                                                          channel: Channel):
    opening = billing.balance(session, user.id)
    run = create_run(
        session, channel=channel, topic="Accounting", pipeline="faceless_shorts",
        options={"target_seconds": 20},
    )
    run_id = run.id
    session.commit()

    assert await _drive(run_id) is RunStatus.completed

    with SessionLocal() as check:
        finished = check.get(Run, run_id)
        # Mock providers are free, so only the publish node's flat fee is spent.
        assert billing.balance(check, user.id) == opening - finished.credits_spent


async def test_revision_reruns_the_node_and_invalidates_downstream(
    session: Session, channel: Channel
):
    run = create_run(
        session, channel=channel, topic="Revision test", pipeline="faceless_shorts",
        options={"target_seconds": 20},
    )
    run_id = run.id
    session.commit()

    graph = engine()
    # Get past the brief gate, then land on the script gate.
    await graph.advance(run_id)
    with SessionLocal() as db:
        graph.approve(db, _gate(db, run_id), note="ok")
        db.commit()
    await graph.advance(run_id)

    with SessionLocal() as db:
        script = _gate(db, run_id)
        assert script.key == "script"
        first_output = dict(script.output)
        graph.approve(db, script, note="ok")
        db.commit()

    # Let voice/broll run so there is downstream work to invalidate.
    await graph.advance(run_id)

    with SessionLocal() as db:
        script = db.execute(
            select(Node).where(Node.run_id == run_id, Node.key == "script")
        ).scalar_one()
        graph.revise(db, script, "Make the hook blunter and cut the third scene.")
        db.commit()

        script = db.execute(
            select(Node).where(Node.run_id == run_id, Node.key == "script")
        ).scalar_one()
        assert script.status is NodeStatus.pending
        assert script.output == {}
        assert script.review_feedback

        # Everything that consumed the script is reset too.
        for key in ("voice", "broll_plan", "shots", "render"):
            node = db.execute(
                select(Node).where(Node.run_id == run_id, Node.key == key)
            ).scalar_one()
            assert node.status is NodeStatus.pending, f"{key} was not invalidated"

    # And the rejection is remembered for future runs on this channel.
    with SessionLocal() as db:
        lessons = db.execute(
            select(ChannelMemory).where(
                ChannelMemory.channel_id == channel.id,
                ChannelMemory.kind == MemoryKind.revision,
            )
        ).scalars().all()
        assert any("blunter" in lesson.content for lesson in lessons)

    # The rerun must actually produce something new rather than stalling.
    status = await _drive(run_id)
    assert status in {RunStatus.completed, RunStatus.awaiting_approval}
    with SessionLocal() as db:
        script = db.execute(
            select(Node).where(Node.run_id == run_id, Node.key == "script")
        ).scalar_one()
        assert script.output != {}
        assert script.output != first_output or script.attempts > 1


async def test_gate_overrides_are_merged_into_output(session: Session, channel: Channel):
    run = create_run(
        session, channel=channel, topic="Override test", pipeline="faceless_shorts",
        options={"target_seconds": 20},
    )
    run_id = run.id
    session.commit()

    graph = engine()
    await graph.advance(run_id)
    with SessionLocal() as db:
        node = _gate(db, run_id)
        graph.approve(db, node, overrides={"working_title": "A Title I Chose"})
        db.commit()
        refreshed = db.execute(
            select(Node).where(Node.run_id == run_id, Node.key == node.key)
        ).scalar_one()
        assert refreshed.output["working_title"] == "A Title I Chose"
        # Merging must not wipe the rest of the payload.
        assert refreshed.output.get("beats")


async def test_cancel_releases_the_hold(session: Session, user: User, channel: Channel):
    opening = billing.balance(session, user.id)
    run = create_run(session, channel=channel, topic="Cancel me", pipeline="faceless_shorts")
    run_id = run.id
    session.commit()

    await engine().advance(run_id)  # stop at the brief gate

    with SessionLocal() as db:
        graph = engine()
        graph.cancel(db, db.get(Run, run_id))
        db.commit()
        finished = db.get(Run, run_id)
        assert finished.status is RunStatus.cancelled
        assert billing.balance(db, user.id) == opening - finished.credits_spent


async def test_unknown_node_type_fails_without_retrying_forever(
    session: Session, channel: Channel
):
    run = create_run(session, channel=channel, topic="Bad node", pipeline="faceless_shorts")
    run_id = run.id
    brief = next(node for node in run.nodes if node.key == "brief")
    brief.type = "no_such_handler"
    session.commit()

    status = await engine().advance(run_id)

    assert status is RunStatus.failed
    with SessionLocal() as db:
        node = db.execute(
            select(Node).where(Node.run_id == run_id, Node.key == "brief")
        ).scalar_one()
        assert node.status is NodeStatus.failed
        assert "no handler" in node.error
        assert node.attempts == 1  # not retried


async def test_channel_style_reaches_the_prompt(session: Session, channel: Channel):
    """The learning agent's context must actually be assembled for each node."""
    from forgecast.memory import prompt_block, remember

    remember(
        session, channel.id, MemoryKind.revision, "Never open with a rhetorical question",
        node_type="script",
    )
    session.commit()

    block = prompt_block(session, channel, node_type="script")
    assert "calm and precise" in block
    assert "rhetorical question" in block


@pytest.mark.parametrize("pipeline", ["faceless_shorts", "faceless_longform"])
async def test_both_pipelines_reach_a_gate(session: Session, channel: Channel, pipeline: str):
    run = create_run(
        session, channel=channel, topic="Smoke", pipeline=pipeline,
        options={"target_seconds": 20},
    )
    session.commit()
    assert await engine().advance(run.id) is RunStatus.awaiting_approval
