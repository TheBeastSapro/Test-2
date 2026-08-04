"""The graph engine: turns a persisted DAG into a finished video, pausing at gates.

Execution is deliberately split into three phases per node so that no database
transaction is held open across a provider call — a single B-roll shot can take
four minutes, and a transaction that long will wedge SQLite and bloat Postgres.

    phase 1 (short tx)  claim the node, snapshot everything the handler needs
    phase 2 (no tx)     call providers, write files to disk
    phase 3 (short tx)  persist output, artifacts, credits, status

The consequence is that `NodeContext` carries plain data, never a live Session.
Handlers cannot query the database, which is a feature: it keeps them testable and
keeps their dependencies explicit.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import credits as billing
from ..config import get_settings
from ..crypto import decrypt
from ..memory import learn_from_approval, learn_from_revision, prompt_block
from ..models import (
    Artifact,
    Channel,
    Node,
    NodeStatus,
    Run,
    RunEvent,
    RunStatus,
    utcnow,
)
from ..providers import ProviderError, ProviderRegistry, registry_for
from .pipelines import get_pipeline

log = logging.getLogger("forgecast.engine")

LEASE_SECONDS = 900  # a node stuck longer than this is assumed dead


# --------------------------------------------------------------------- snapshots


@dataclass
class ChannelSnapshot:
    id: int
    name: str
    niche: str
    language: str
    voice_id: str
    avatar_id: str
    aspect_ratio: str
    target_duration_seconds: int
    style_profile: dict
    youtube_channel_id: str = ""
    youtube_refresh_token: str = ""
    # Which vendor narrates. Defaulted so every existing construction of this snapshot —
    # tests, fixtures, the CLI — keeps working and means "let the routing decide".
    voice_vendor: str = ""
    # Which scripting method the text stages write to. Empty means the built-in house
    # method, which is what `scripting.prompt_block` falls back to anyway — so a snapshot
    # built by an older caller produces a script written to a method rather than to none.
    scripting_style: str = ""
    # Which image-to-video model this channel's shots are generated on. Empty means the
    # app default, which is what every run got before the choice existed.
    video_model: str = ""
    # The frame and the rate this channel delivers at. Zero means the app default —
    # 1080p at 30fps. Both defaulted so every older construction of this snapshot keeps
    # working and means "let the app decide".
    video_height: int = 0
    video_fps: int = 0


@dataclass
class ArtifactRef:
    kind: str
    path: Path
    mime: str
    node_key: str
    meta: dict = field(default_factory=dict)


@dataclass
class PendingArtifact:
    kind: str
    path: Path
    mime: str
    meta: dict = field(default_factory=dict)


@dataclass
class NodeContext:
    """Everything a node handler is allowed to see."""

    run_id: int
    topic: str
    options: dict
    node_key: str
    node_type: str
    params: dict
    attempts: int
    channel: ChannelSnapshot
    registry: ProviderRegistry
    workdir: Path
    upstream_outputs: dict[str, dict] = field(default_factory=dict)
    upstream_artifacts: dict[str, list[ArtifactRef]] = field(default_factory=dict)
    memory_block: str = ""
    revision_feedback: str | None = None
    _artifacts: list[PendingArtifact] = field(default_factory=list, repr=False)
    _logs: list[tuple[str, str, dict]] = field(default_factory=list, repr=False)

    # -- reading upstream -------------------------------------------------------

    def output(self, node_key: str) -> dict:
        try:
            return self.upstream_outputs[node_key]
        except KeyError:
            raise ProviderError(
                f"node '{self.node_key}' needs output of '{node_key}', which has not run"
            ) from None

    def artifacts(self, node_key: str, kind: str | None = None) -> list[ArtifactRef]:
        refs = self.upstream_artifacts.get(node_key, [])
        return [ref for ref in refs if kind is None or ref.kind == kind]

    def first_artifact(self, node_key: str, kind: str | None = None) -> ArtifactRef | None:
        found = self.artifacts(node_key, kind)
        return found[0] if found else None

    # -- writing ----------------------------------------------------------------

    def path_for(self, filename: str) -> Path:
        target = self.workdir / self.node_key / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def emit_artifact(self, kind: str, path: Path, mime: str, **meta) -> PendingArtifact:
        artifact = PendingArtifact(kind=kind, path=Path(path), mime=mime, meta=meta)
        self._artifacts.append(artifact)
        return artifact

    def log(self, message: str, level: str = "info", **data) -> None:
        self._logs.append((level, message, data))
        log.info("run=%s node=%s %s", self.run_id, self.node_key, message)


@dataclass
class NodeResult:
    output: dict = field(default_factory=dict)
    credits: int = 0
    provider: str = ""


NodeHandler = Callable[[NodeContext], Awaitable[NodeResult]]
registry: dict[str, NodeHandler] = {}


def node_handler(node_type: str) -> Callable[[NodeHandler], NodeHandler]:
    def decorator(func: NodeHandler) -> NodeHandler:
        if node_type in registry:
            raise RuntimeError(f"duplicate handler for node type '{node_type}'")
        registry[node_type] = func
        return func

    return decorator


# ------------------------------------------------------------------- run creation


def create_run(
    session: Session,
    *,
    channel: Channel,
    topic: str,
    pipeline: str = "faceless_longform",
    options: dict | None = None,
) -> Run:
    """Build the graph and take the credit hold. Raises InsufficientCredits."""
    options = dict(options or {})
    spec = get_pipeline(
        pipeline,
        target_seconds=int(
            options.get("target_seconds") or channel.target_duration_seconds or 480
        ),
        use_avatar=bool(options.get("use_avatar", bool(channel.avatar_id))),
        publish=bool(options.get("publish", True)),
    )

    run = Run(
        channel_id=channel.id,
        user_id=channel.user_id,
        topic=topic.strip(),
        pipeline=spec.name,
        status=RunStatus.queued,
        options=options,
    )
    session.add(run)
    session.flush()

    nodes = spec.instantiate(run.id)
    session.add_all(nodes)
    session.flush()

    estimate = billing.estimate_run(nodes)
    billing.reserve(session, run, estimate)

    _event(session, run.id, None, f"run queued: {topic!r} ({spec.title})",
           data={"estimate_credits": estimate})
    session.flush()
    return run


def _event(
    session: Session, run_id: int, node_key: str | None, message: str,
    level: str = "info", data: dict | None = None,
) -> None:
    session.add(
        RunEvent(
            run_id=run_id, node_key=node_key, level=level, message=message, data=data or {}
        )
    )


# ------------------------------------------------------------------------- engine


class GraphEngine:
    def __init__(self, session_factory, *, worker_id: str = "engine", concurrency: int = 2):
        self._session_factory = session_factory
        self.worker_id = worker_id
        self._semaphore = asyncio.Semaphore(max(1, concurrency))

    # -- session helper ---------------------------------------------------------

    def _session(self) -> Session:
        return self._session_factory()

    def _tx(self):
        from contextlib import contextmanager

        @contextmanager
        def scope():
            session = self._session()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        return scope()

    # -- public API -------------------------------------------------------------

    async def advance(self, run_id: int, *, max_waves: int = 64) -> RunStatus:
        """Execute every runnable node until the run finishes, fails, or hits a gate."""
        for _ in range(max_waves):
            wave, status = self._next_wave(run_id)
            if status is not None:
                return status
            if not wave:
                return self._status_of(run_id)

            await asyncio.gather(*(self._run_node(run_id, node_id) for node_id in wave))

        with self._tx() as session:
            run = session.get(Run, run_id)
            if run and not run.is_terminal:
                _event(session, run_id, None, "wave limit reached — stopping", level="warning")
        return self._status_of(run_id)

    def approve(
        self, session: Session, node: Node, *, note: str = "", overrides: dict | None = None
    ) -> Run:
        """Pass a decision gate.

        `overrides` shallow-merges into the node's output, so an operator can fix a
        title or flip privacy to public at the gate without triggering a rerun.
        """
        if node.status is not NodeStatus.awaiting_approval:
            raise ValueError(f"node {node.key} is {node.status.value}, not awaiting approval")
        run = session.get(Run, node.run_id)
        if overrides:
            merged = dict(node.output or {})
            for key, value in overrides.items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    merged[key] = {**merged[key], **value}
                else:
                    merged[key] = value
            node.output = merged
        node.status = NodeStatus.completed
        node.reviewed_at = utcnow()
        node.finished_at = node.finished_at or utcnow()
        _event(session, run.id, node.key, f"gate approved: {node.title}",
               data={"note": note, "overrides": sorted(overrides or {})})

        summary = _summarise_output(node)
        learn_from_approval(session, run.channel_id, node.type, summary, run_id=run.id)

        run.status = RunStatus.queued
        run.error = None
        session.flush()
        return run

    def revise(self, session: Session, node: Node, feedback: str) -> Run:
        """Reject at a gate. The node re-runs with the feedback, and so does
        everything downstream of it — otherwise a revised script would keep the
        narration recorded from the old one."""
        if node.status not in {NodeStatus.awaiting_approval, NodeStatus.completed}:
            raise ValueError(f"node {node.key} cannot be revised from {node.status.value}")
        run = session.get(Run, node.run_id)

        node.status = NodeStatus.pending
        node.review_feedback = feedback
        node.reviewed_at = utcnow()
        node.error = None
        node.output = {}

        invalidated = self._invalidate_downstream(session, run, node)
        learn_from_revision(session, run.channel_id, node.type, feedback, run_id=run.id)
        _event(
            session, run.id, node.key,
            f"gate revision requested on {node.title}",
            data={"feedback": feedback, "invalidated": invalidated},
        )

        run.status = RunStatus.queued
        run.error = None
        session.flush()
        return run

    def cancel(self, session: Session, run: Run, reason: str = "cancelled by operator") -> Run:
        run.status = RunStatus.cancelled
        run.error = reason
        run.finished_at = utcnow()
        for node in run.nodes:
            if node.status in {NodeStatus.pending, NodeStatus.ready,
                               NodeStatus.awaiting_approval}:
                node.status = NodeStatus.skipped
        released = billing.release_unused(session, run)
        _event(session, run.id, None, reason, level="warning",
               data={"credits_released": released})
        session.flush()
        return run

    # -- wave planning ----------------------------------------------------------

    def _next_wave(self, run_id: int) -> tuple[list[int], RunStatus | None]:
        """Pick the nodes to execute next, or return a terminal status."""
        with self._tx() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise LookupError(f"no run {run_id}")
            if run.is_terminal:
                return [], run.status

            nodes = list(run.nodes)
            by_key = {node.key: node for node in nodes}

            self._reclaim_stale(session, nodes)

            if any(node.status is NodeStatus.awaiting_approval for node in nodes):
                if run.status is not RunStatus.awaiting_approval:
                    run.status = RunStatus.awaiting_approval
                    _event(session, run_id, None, "waiting for operator approval")
                return [], RunStatus.awaiting_approval

            failed = [n for n in nodes if n.status is NodeStatus.failed]
            if failed:
                run.status = RunStatus.failed
                run.error = failed[0].error or f"node {failed[0].key} failed"
                run.finished_at = utcnow()
                released = billing.release_unused(session, run)
                _event(session, run_id, failed[0].key, f"run failed: {run.error}",
                       level="error", data={"credits_released": released})
                return [], RunStatus.failed

            done = {NodeStatus.completed, NodeStatus.skipped}
            if all(node.status in done for node in nodes):
                run.status = RunStatus.completed
                run.finished_at = utcnow()
                released = billing.release_unused(session, run)
                _event(session, run_id, None, "run completed",
                       data={"credits_spent": run.credits_spent,
                             "credits_released": released})
                return [], RunStatus.completed

            if any(node.status is NodeStatus.running for node in nodes):
                # Another worker owns the in-flight nodes; let it finish.
                return [], None

            ready = [
                node
                for node in nodes
                if node.status in {NodeStatus.pending, NodeStatus.ready}
                and all(by_key[dep].status in done for dep in node.depends_on if dep in by_key)
            ]
            if not ready:
                run.status = RunStatus.failed
                run.error = "pipeline deadlocked: no node is runnable"
                run.finished_at = utcnow()
                billing.release_unused(session, run)
                _event(session, run_id, None, run.error, level="error")
                return [], RunStatus.failed

            run.status = RunStatus.running
            for node in ready:
                node.status = NodeStatus.running
                node.started_at = utcnow()
                node.attempts += 1
            run.locked_by = self.worker_id
            run.locked_at = utcnow()
            session.flush()
            return [node.id for node in ready], None

    @staticmethod
    def _reclaim_stale(session: Session, nodes: list[Node]) -> None:
        cutoff = datetime.now(UTC) - timedelta(seconds=LEASE_SECONDS)
        for node in nodes:
            if node.status is NodeStatus.running and node.started_at:
                started = node.started_at
                if started.tzinfo is None:
                    started = started.replace(tzinfo=UTC)
                if started < cutoff:
                    node.status = NodeStatus.pending
                    _event(
                        session, node.run_id, node.key,
                        f"reclaimed stale node after {LEASE_SECONDS}s", level="warning",
                    )

    def _invalidate_downstream(self, session: Session, run: Run, node: Node) -> list[str]:
        """Reset every node that transitively depends on `node`."""
        nodes = list(run.nodes)
        dependents: dict[str, list[str]] = {}
        for candidate in nodes:
            for dep in candidate.depends_on:
                dependents.setdefault(dep, []).append(candidate.key)

        stale: set[str] = set()
        queue = list(dependents.get(node.key, []))
        while queue:
            key = queue.pop()
            if key in stale:
                continue
            stale.add(key)
            queue.extend(dependents.get(key, []))

        for candidate in nodes:
            if candidate.key in stale and candidate.status is not NodeStatus.pending:
                candidate.status = NodeStatus.pending
                candidate.output = {}
                candidate.error = None
                candidate.reviewed_at = None
        return sorted(stale)

    def _status_of(self, run_id: int) -> RunStatus:
        with self._tx() as session:
            run = session.get(Run, run_id)
            return run.status if run else RunStatus.failed

    # -- node execution ---------------------------------------------------------

    async def _run_node(self, run_id: int, node_id: int) -> None:
        async with self._semaphore:
            context, node_type, estimate = self._snapshot(run_id, node_id)
            handler = registry.get(node_type)
            if handler is None:
                self._finish_failure(node_id, f"no handler registered for '{node_type}'",
                                     retryable=False)
                return

            try:
                result = await handler(context)
            except ProviderError as exc:
                self._finish_failure(
                    node_id, f"{exc}", retryable=exc.retryable, context=context
                )
                return
            except Exception as exc:
                detail = f"{type(exc).__name__}: {exc}"
                log.exception("node %s crashed", node_id)
                self._finish_failure(
                    node_id, detail, retryable=False, context=context,
                    trace=traceback.format_exc(limit=6),
                )
                return

            self._finish_success(node_id, context, result, estimate)

    def _snapshot(self, run_id: int, node_id: int) -> tuple[NodeContext, str, int]:
        settings = get_settings()
        with self._tx() as session:
            node = session.get(Node, node_id)
            run = session.get(Run, run_id)
            channel = session.get(Channel, run.channel_id)

            refresh_token = ""
            if channel.youtube_credentials:
                try:
                    refresh_token = decrypt(channel.youtube_credentials)
                except Exception:
                    refresh_token = ""

            snapshot = ChannelSnapshot(
                id=channel.id,
                name=channel.name,
                niche=channel.niche,
                language=channel.language,
                voice_id=channel.voice_id,
                avatar_id=channel.avatar_id,
                aspect_ratio=channel.aspect_ratio,
                target_duration_seconds=channel.target_duration_seconds,
                style_profile=dict(channel.style_profile or {}),
                youtube_channel_id=channel.youtube_channel_id,
                youtube_refresh_token=refresh_token,
                voice_vendor=channel.voice_vendor or "",
                scripting_style=channel.scripting_style or "",
                video_model=channel.video_model or "",
                video_height=int(channel.video_height or 0),
                video_fps=int(channel.video_fps or 0),
            )

            upstream_outputs: dict[str, dict] = {}
            for other in run.nodes:
                if other.key != node.key and other.output:
                    upstream_outputs[other.key] = dict(other.output)

            artifacts_by_node: dict[str, list[ArtifactRef]] = {}
            rows = session.execute(
                select(Artifact).where(Artifact.run_id == run_id).order_by(Artifact.id)
            ).scalars().all()
            node_keys = {other.id: other.key for other in run.nodes}
            for row in rows:
                key = node_keys.get(row.node_id or -1, "")
                if not key:
                    continue
                artifacts_by_node.setdefault(key, []).append(
                    ArtifactRef(
                        kind=row.kind,
                        path=Path(row.path),
                        mime=row.mime,
                        node_key=key,
                        meta=dict(row.meta or {}),
                    )
                )

            overrides = dict((run.options or {}).get("provider_overrides") or {})
            # The channel's own choice of narration vendor, unless this run already
            # names one. Run options win because they are the more specific decision —
            # a one-off "render this in the other voice" must not be silently ignored.
            if snapshot.voice_vendor and not overrides.get("voice"):
                overrides["voice"] = snapshot.voice_vendor

            # And the channel's chosen i2v model, on the same precedence: a run that names
            # one has already made the more specific decision. This is the only capability
            # where the model rather than the vendor is the expensive choice — one fal key
            # reaches models spanning $15 to $98 for the same eighty shots — so it is
            # carried separately from the vendor overrides above.
            models = dict((run.options or {}).get("provider_models") or {})
            if snapshot.video_model and not models.get("video"):
                models["video"] = snapshot.video_model
            context = NodeContext(
                run_id=run_id,
                topic=run.topic,
                options=dict(run.options or {}),
                node_key=node.key,
                node_type=node.type,
                params=dict(node.params or {}),
                attempts=node.attempts,
                channel=snapshot,
                registry=registry_for(session, run.user_id, overrides=overrides,
                                      models=models),
                workdir=settings.run_dir(run_id),
                upstream_outputs=upstream_outputs,
                upstream_artifacts=artifacts_by_node,
                memory_block=prompt_block(session, channel, node_type=node.type),
                revision_feedback=node.review_feedback,
            )
            estimate = billing.estimate_node(
                node.type, float((node.params or {}).get("estimated_units", 0) or 0)
            ).credits
            _event(session, run_id, node.key, f"started {node.title}",
                   data={"attempt": node.attempts})
            return context, node.type, estimate

    def _finish_success(
        self, node_id: int, context: NodeContext, result: NodeResult, estimate: int
    ) -> None:
        with self._tx() as session:
            node = session.get(Node, node_id)
            run = session.get(Run, node.run_id)

            node.output = result.output or {}
            node.error = None
            node.finished_at = utcnow()

            for pending in context._artifacts:
                path = Path(pending.path)
                session.add(
                    Artifact(
                        run_id=run.id,
                        node_id=node.id,
                        kind=pending.kind,
                        path=str(path),
                        mime=pending.mime,
                        size_bytes=path.stat().st_size if path.exists() else 0,
                        meta=pending.meta,
                        take=node.attempts,
                    )
                )

            for level, message, data in context._logs:
                _event(session, run.id, node.key, message, level=level, data=data)

            billing.settle_node(
                session, run, node,
                estimated=estimate, actual=result.credits, provider=result.provider or None,
            )

            if node.requires_approval:
                node.status = NodeStatus.awaiting_approval
                run.status = RunStatus.awaiting_approval
                _event(session, run.id, node.key,
                       f"{node.title} finished — waiting for your approval")
            else:
                node.status = NodeStatus.completed
                _event(session, run.id, node.key, f"finished {node.title}",
                       data={"credits": result.credits})
            session.flush()

    def _finish_failure(
        self, node_id: int, detail: str, *, retryable: bool,
        context: NodeContext | None = None, trace: str = "",
    ) -> None:
        with self._tx() as session:
            node = session.get(Node, node_id)
            run = session.get(Run, node.run_id)

            if context is not None:
                for level, message, data in context._logs:
                    _event(session, run.id, node.key, message, level=level, data=data)

            can_retry = retryable and node.attempts < node.max_attempts
            node.error = detail
            if can_retry:
                node.status = NodeStatus.pending
                _event(
                    session, run.id, node.key,
                    f"{node.title} failed, retrying ({node.attempts}/{node.max_attempts}): "
                    f"{detail}",
                    level="warning",
                )
            else:
                node.status = NodeStatus.failed
                node.finished_at = utcnow()
                _event(session, run.id, node.key, f"{node.title} failed: {detail}",
                       level="error", data={"trace": trace} if trace else {})
            session.flush()


def _summarise_output(node: Node) -> str:
    output = node.output or {}
    for key in ("working_title", "title", "verdict", "summary"):
        if output.get(key):
            return str(output[key])[:200]
    return f"{node.type} output accepted"
