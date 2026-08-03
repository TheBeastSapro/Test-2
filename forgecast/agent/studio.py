"""The studio's operations as plain methods, so the agent and the buttons agree.

Every capability the app has lives here once. The chat reaches it through MCP tools
and the panels reach it through HTTP routes, but both end up in this file. Two paths
to the same operation is how the two halves of an app start disagreeing about what
is loaded — the panel showing a channel the agent has already renamed, an approval
the transcript never saw.

Returns are plain dicts, and they carry *numbers*, not adjectives. A tool result of
`{"ok": true}` gives the agent nothing to tell you; `{"outliers": 3, "strongest":
"8.0× baseline"}` gives it something worth saying.

Errors come back as `{"error": "..."}` rather than raising. An exception crossing the
MCP boundary becomes a stack trace in a log file nobody opens; a returned error is
something the agent can read, explain and work around.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import credits
from ..config import get_settings
from ..db import SessionLocal
from ..graph import formats
from ..graph.engine import create_run
from ..models import Channel, Node, NodeStatus, Run, RunEvent, RunStatus, User

log = logging.getLogger("forgecast.agent.studio")

# A YouTube link in any of the forms someone actually pastes: a watch URL, a share
# link, a Short, a channel by handle, by /c/ vanity name, or by raw channel id.
_YOUTUBE = re.compile(
    # youtu.be puts the id straight after the slash with no `watch?v=`, and it is the
    # form the share button produces — so it is the one most often pasted.
    r"youtu\.be/(?P<short>[\w-]{11})"
    r"|(?:youtube\.com|youtu\.be)/(?:"
    r"watch\?v=(?P<v1>[\w-]{11})"
    r"|shorts/(?P<v2>[\w-]{11})"
    r"|embed/(?P<v3>[\w-]{11})"
    r"|live/(?P<v4>[\w-]{11})"
    r"|channel/(?P<cid>UC[\w-]{20,})"
    r"|(?:c|user)/(?P<vanity>[\w.-]+)"
    r"|(?P<handle>@[\w.-]+)"
    r")|^(?P<bare>@[\w.-]+)$",
    re.IGNORECASE,
)


@dataclass
class Link:
    """What a pasted YouTube link turned out to be."""

    kind: str          # "video" | "channel" | "handle" | "unknown"
    value: str         # video id, channel id, or @handle
    raw: str

    def as_dict(self) -> dict:
        return {"kind": self.kind, "value": self.value, "raw": self.raw}


def parse_link(text: str) -> Link:
    """Classify a pasted link without calling anything.

    Rookcast's channel flow starts with a link, not a form, and this is the first
    step of it: work out whether you were given a video or a channel before deciding
    what to fetch.
    """
    raw = (text or "").strip()
    match = _YOUTUBE.search(raw)
    if not match:
        return Link("unknown", "", raw)
    groups = match.groupdict()
    for key in ("short", "v1", "v2", "v3", "v4"):
        if groups.get(key):
            return Link("video", groups[key], raw)
    if groups.get("cid"):
        return Link("channel", groups["cid"], raw)
    for key in ("handle", "bare"):
        if groups.get(key):
            return Link("handle", groups[key], raw)
    if groups.get("vanity"):
        return Link("handle", groups["vanity"], raw)
    return Link("unknown", "", raw)


class Studio:
    """Everything the app can do, bound to one account.

    `session_factory` rather than a live session: tools are called from the agent's
    event loop, minutes apart, while the UI is using its own request-scoped session.
    Sharing one would mean a stale identity map handing the agent a channel that was
    renamed two turns ago.
    """

    def __init__(self, session_factory: Callable[[], Session] | None = None,
                 user_id: int | None = None) -> None:
        self._factory = session_factory or SessionLocal
        self._user_id = user_id

    # ------------------------------------------------------------------ plumbing

    def _session(self) -> Session:
        return self._factory()

    def _user(self, session: Session) -> User | None:
        if self._user_id is not None:
            return session.get(User, self._user_id)
        # Mirrors the desktop handoff: an explicitly configured owner wins, and a
        # single-account database needs no configuration at all.
        settings = get_settings()
        if settings.owner_email:
            found = session.execute(
                select(User).where(User.email == settings.owner_email.strip().lower())
            ).scalar_one_or_none()
            if found is not None:
                return found
        rows = session.execute(select(User).order_by(User.id).limit(2)).scalars().all()
        return rows[0] if len(rows) == 1 else (rows[0] if rows else None)

    def _channel(self, session: Session, user: User, ref: Any) -> Channel | None:
        """A channel by id or by name, because the agent has both and neither is wrong."""
        stmt = select(Channel).where(Channel.user_id == user.id)
        if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
            return session.execute(stmt.where(Channel.id == int(ref))).scalar_one_or_none()
        name = str(ref or "").strip()
        if not name:
            return None
        exact = session.execute(
            stmt.where(func.lower(Channel.name) == name.lower())).scalars().first()
        if exact is not None:
            return exact
        return session.execute(
            stmt.where(Channel.name.ilike(f"%{name}%"))).scalars().first()

    # -------------------------------------------------------------------- status

    def status(self) -> dict:
        """What is connected and what is not — the answer to "is Claude wired up".

        Deliberately the widest tool in the set. It is what the agent should call
        first in a new conversation so its first sentence is about *this* install
        rather than a generic greeting.
        """
        from ..render.ffmpeg import ffmpeg_available
        from . import auth

        settings = get_settings()
        claude = auth.check()

        with self._session() as session:
            user = self._user(session)
            if user is None:
                return {"error": "No account exists yet. Restart the app — the "
                                 "launcher creates the owner account on first run."}
            channels = session.execute(
                select(Channel).where(Channel.user_id == user.id)).scalars().all()
            runs = session.execute(
                select(Run).where(Run.user_id == user.id)
                .order_by(Run.id.desc()).limit(200)).scalars().all()
            counts = formats.counts(list(channels), list(runs))
            waiting = [
                {"run": run.id, "topic": run.topic, "channel": run.channel.name}
                for run in runs if run.status is RunStatus.awaiting_approval
            ]
            balance = credits.balance(session, user.id)

        return {
            "account": user.email,
            "mode": settings.provider_mode,
            "mode_means": (
                "Mock — nothing is called and nothing is charged. Runs complete with "
                "placeholder script, voice and visuals so the whole pipeline can be "
                "seen before it costs anything."
                if settings.is_mock else
                "Live — real providers are called and real credits are spent."
            ),
            "claude": {"ok": claude.ok, "headline": claude.headline,
                       "account": claude.account},
            "ffmpeg": ffmpeg_available(),
            "credits": balance,
            "channels": {"total": len(channels), "by_format": counts},
            "runs_waiting_on_you": waiting,
            "studio": self.current_preview(),
            "storage": str(settings.storage_dir.resolve()),
        }

    def current_preview(self) -> dict:
        """The run the Studio panel should be showing, if any.

        Whatever is live takes precedence over whatever is newest: a run being worked
        on is what you want on screen, and a finished one from last week is not. A
        run with no script yet has nothing to draw, so it reports itself asleep rather
        than showing an empty player and letting you wonder what broke.
        """
        from ..models import NodeStatus as NS

        with self._session() as session:
            user = self._user(session)
            if user is None:
                return {"state": "asleep", "reason": "no account"}

            live = [RunStatus.running, RunStatus.awaiting_approval]
            run = session.execute(
                select(Run).where(Run.user_id == user.id, Run.status.in_(live))
                .order_by(Run.id.desc()).limit(1)).scalars().first()
            if run is None:
                run = session.execute(
                    select(Run).where(Run.user_id == user.id)
                    .order_by(Run.id.desc()).limit(1)).scalars().first()
            if run is None:
                return {"state": "asleep",
                        "reason": "no runs yet — start one and the edit appears here "
                                  "before it renders"}

            has_script = session.execute(
                select(Node).where(Node.run_id == run.id, Node.type == "script",
                                   Node.status == NS.completed)
            ).scalars().first() is not None

            return {
                "state": "live" if has_script else "waking",
                "run": run.id,
                "topic": run.topic,
                "channel": run.channel.name,
                "status": run.status.value,
                "url": f"/runs/{run.id}/preview?embed=1",
                "reason": "" if has_script else
                          f"run {run.id} has not written its script yet — there is "
                          f"nothing to draw until it does",
            }

    # ------------------------------------------------------------------ channels

    def list_channels(self, fmt: str = "") -> dict:
        with self._session() as session:
            user = self._user(session)
            if user is None:
                return {"error": "No account."}
            rows = session.execute(
                select(Channel).where(Channel.user_id == user.id)
                .order_by(Channel.id)).scalars().all()
            if fmt:
                rows = formats.channels_in(list(rows), fmt)
            out = []
            for channel in rows:
                total = session.execute(
                    select(func.count(Run.id)).where(Run.channel_id == channel.id)
                ).scalar_one()
                out.append({
                    "id": channel.id, "name": channel.name, "niche": channel.niche,
                    "format": formats.format_of_channel(channel),
                    "aspect_ratio": channel.aspect_ratio,
                    "target_seconds": channel.target_duration_seconds,
                    "language": channel.language,
                    "voice": channel.voice_id or "(default)",
                    "runs": total,
                    "youtube_connected": bool(channel.youtube_credentials),
                })
        return {"channels": out, "count": len(out)}

    def create_channel(self, name: str, *, niche: str = "", fmt: str = "longform",
                       language: str = "en", target_seconds: int = 0,
                       style_profile: dict | None = None,
                       youtube_channel_id: str = "") -> dict:
        """Make a channel. The format decides the aspect ratio and the default length."""
        name = (name or "").strip()
        if not name:
            return {"error": "A channel needs a name."}

        shape = formats.get(fmt)
        with self._session() as session:
            user = self._user(session)
            if user is None:
                return {"error": "No account."}
            clash = session.execute(
                select(Channel).where(Channel.user_id == user.id,
                                      func.lower(Channel.name) == name.lower())
            ).scalar_one_or_none()
            if clash is not None:
                return {"error": f"You already have a channel called {name!r} "
                                 f"(id {clash.id}). Rename it or pick another name."}

            channel = Channel(
                user_id=user.id, name=name, niche=(niche or "").strip(),
                language=language or "en",
                aspect_ratio=shape.aspect_ratio,
                target_duration_seconds=int(target_seconds or shape.default_seconds),
                style_profile=style_profile or {},
                youtube_channel_id=youtube_channel_id or "",
            )
            session.add(channel)
            session.commit()
            log.info("channel %s created (%s)", channel.id, shape.slug)
            return {"created": True, "id": channel.id, "name": channel.name,
                    "format": shape.slug, "aspect_ratio": channel.aspect_ratio,
                    "target_seconds": channel.target_duration_seconds,
                    "niche": channel.niche}

    def study_youtube_channel(self, reference: str, *, limit: int = 30) -> dict:
        """Read a real channel and report what it actually publishes.

        The setup flow starts with a link because a link is what you have. Asking for
        name, niche, aspect ratio and target length up front is asking you to
        summarise a channel that is sitting right there and can be measured: the
        median upload length says long-form or Shorts more reliably than a dropdown,
        and the titles say more about the niche than a one-line description would.

        This only reads. Creating the channel is a separate call, so what was measured
        can be shown to you before anything is written.
        """
        from ..research import sources
        from ..research.outliers import find_outliers, summarise

        link = parse_link(reference)
        if link.kind == "video":
            return {"error": "That is a video link. Give me the channel — I set up "
                             "channels, and a channel is the thing with a history to "
                             "measure.", "link": link.as_dict()}

        settings = get_settings()
        target = link.value or reference.strip()
        try:
            parsed, via = sources.read_channel(
                target, api_key=settings.youtube_api_key, limit=int(limit)
            )
        except sources.ResearchError as exc:
            # Not an error, because setting a channel up does not depend on measuring
            # one: the numbers are a shortcut past four questions, and losing the
            # shortcut means asking the questions rather than refusing to continue.
            return {
                "measured": False,
                "link": link.as_dict(),
                "suggested_name": target.lstrip("@").replace("-", " ").title(),
                "why_not": str(exc),
                "note": "I could not read that channel's numbers. I can still create "
                        "the channel — tell me the niche and whether it is long-form "
                        "or Shorts.",
            }
        if not parsed.videos:
            return {"error": "That channel has no readable uploads.",
                    "link": link.as_dict()}

        videos = parsed.videos
        lengths = sorted(v.duration_seconds for v in videos if v.duration_seconds)
        median = lengths[len(lengths) // 2] if lengths else 0.0
        shape = formats.get(formats.SHORTS if 0 < median <= 90 else formats.LONGFORM)
        found = find_outliers(videos)

        return {
            "measured": True,
            "via": via,
            "link": link.as_dict(),
            "name": videos[0].channel or link.value,
            "subscribers": videos[0].channel_subscribers,
            "uploads_read": len(videos),
            "median_length_seconds": round(median),
            "format": shape.slug,
            "aspect_ratio": shape.aspect_ratio,
            "recent_titles": [v.title for v in videos[:8]],
            **summarise(found),
            "next": "Say the niche in your own words and I will create the channel "
                    "with these numbers as its defaults.",
        }

    def update_channel(self, channel: Any, **changes) -> dict:
        allowed = {"name", "niche", "language", "voice_id", "avatar_id",
                   "aspect_ratio", "target_duration_seconds", "style_profile",
                   "youtube_channel_id"}
        with self._session() as session:
            user = self._user(session)
            if user is None:
                return {"error": "No account."}
            row = self._channel(session, user, channel)
            if row is None:
                return {"error": f"No channel matching {channel!r}."}
            applied = {}
            for key, value in changes.items():
                if key in allowed and value not in (None, ""):
                    setattr(row, key, value)
                    applied[key] = value
            if not applied:
                return {"error": "Nothing to change. Fields: " + ", ".join(sorted(allowed))}
            session.commit()
            return {"updated": row.id, "name": row.name, "changed": applied,
                    "format": formats.format_of_channel(row)}

    # ---------------------------------------------------------------------- runs

    def list_runs(self, *, channel: Any = None, fmt: str = "", limit: int = 20) -> dict:
        with self._session() as session:
            user = self._user(session)
            if user is None:
                return {"error": "No account."}
            stmt = select(Run).where(Run.user_id == user.id)
            if channel is not None:
                row = self._channel(session, user, channel)
                if row is None:
                    return {"error": f"No channel matching {channel!r}."}
                stmt = stmt.where(Run.channel_id == row.id)
            rows = session.execute(
                stmt.order_by(Run.id.desc()).limit(max(1, min(int(limit or 20), 100)))
            ).scalars().all()
            if fmt:
                rows = formats.runs_in(list(rows), fmt)
            out = [{
                "id": run.id, "topic": run.topic, "channel": run.channel.name,
                "status": run.status.value, "pipeline": run.pipeline,
                "format": formats.format_of_pipeline(run.pipeline),
                "credits_spent": run.credits_spent,
                "waiting_at": self._gate_key(session, run),
            } for run in rows]
        return {"runs": out, "count": len(out)}

    @staticmethod
    def _gate_key(session: Session, run: Run) -> str:
        if run.status is not RunStatus.awaiting_approval:
            return ""
        node = session.execute(
            select(Node).where(Node.run_id == run.id,
                               Node.status == NodeStatus.awaiting_approval)
        ).scalars().first()
        return node.key if node else ""

    def start_run(self, channel: Any, topic: str, *, options: dict | None = None) -> dict:
        """Queue a video. Costs credits — the gates are where it stops for you."""
        topic = (topic or "").strip()
        if not topic:
            return {"error": "A run needs a topic."}

        with self._session() as session:
            user = self._user(session)
            if user is None:
                return {"error": "No account."}
            row = self._channel(session, user, channel)
            if row is None:
                available = session.execute(
                    select(Channel.name).where(Channel.user_id == user.id)).scalars().all()
                return {"error": f"No channel matching {channel!r}.",
                        "channels": list(available)}

            shape = formats.get(formats.format_of_channel(row))
            try:
                run = create_run(session, channel=row, topic=topic,
                                 pipeline=shape.pipeline, options=dict(options or {}))
            except credits.InsufficientCredits as exc:
                return {"error": f"Not enough credits: needs {exc.needed}, "
                                 f"{exc.available} available."}
            session.commit()
            run_id, reserved = run.id, run.credits_reserved

        self._nudge(run_id)
        return {"started": True, "run": run_id, "topic": topic,
                "channel": str(channel), "pipeline": shape.pipeline,
                "credits_reserved": reserved,
                "next": "It will stop at the first gate. Call run_status to see where."}

    @staticmethod
    def _nudge(run_id: int) -> None:
        """Push the run forward now rather than at the worker's next poll."""
        from ..api import runner
        try:
            runner.schedule(run_id)
        except Exception:                                     # pragma: no cover
            log.debug("could not schedule run %s from the agent", run_id)

    def run_status(self, run_id: int) -> dict:
        with self._session() as session:
            user = self._user(session)
            run = session.get(Run, int(run_id)) if user else None
            if run is None or user is None or run.user_id != user.id:
                return {"error": f"No run {run_id}."}
            nodes = session.execute(
                select(Node).where(Node.run_id == run.id).order_by(Node.id)
            ).scalars().all()
            events = session.execute(
                select(RunEvent).where(RunEvent.run_id == run.id)
                .order_by(RunEvent.id.desc()).limit(8)).scalars().all()
            return {
                "run": run.id, "topic": run.topic, "channel": run.channel.name,
                "status": run.status.value, "pipeline": run.pipeline,
                "credits": {"reserved": run.credits_reserved, "spent": run.credits_spent},
                "error": run.error or "",
                "nodes": [{"key": n.key, "title": n.title, "type": n.type,
                           "status": n.status.value} for n in nodes],
                "gate": next(({"key": n.key, "title": n.title,
                               "output": (n.output or {})}
                              for n in nodes
                              if n.status is NodeStatus.awaiting_approval), None),
                "recent": [f"{e.level}: {e.message}" for e in reversed(events)],
            }

    def decide_gate(self, run_id: int, *, approve: bool = True, node_key: str = "",
                    note: str = "", feedback: str = "") -> dict:
        """Approve the waiting gate, or send it back with instructions."""
        from ..api import runner

        with self._session() as session:
            user = self._user(session)
            run = session.get(Run, int(run_id)) if user else None
            if run is None or user is None or run.user_id != user.id:
                return {"error": f"No run {run_id}."}

            stmt = select(Node).where(Node.run_id == run.id)
            node = (session.execute(stmt.where(Node.key == node_key)).scalar_one_or_none()
                    if node_key else
                    session.execute(
                        stmt.where(Node.status == NodeStatus.awaiting_approval)
                    ).scalars().first())
            if node is None:
                return {"error": "Nothing is waiting for approval on that run."}

            engine = runner.engine()
            try:
                if approve and not feedback:
                    engine.approve(session, node, note=note)
                    verdict = "approved"
                else:
                    engine.revise(session, node, feedback or note or "Try again.")
                    verdict = "sent back"
            except ValueError as exc:
                return {"error": str(exc)}
            session.commit()

        self._nudge(int(run_id))
        return {"run": int(run_id), "node": node.key, "verdict": verdict,
                "note": note or feedback}

    def cancel_run(self, run_id: int) -> dict:
        with self._session() as session:
            user = self._user(session)
            run = session.get(Run, int(run_id)) if user else None
            if run is None or user is None or run.user_id != user.id:
                return {"error": f"No run {run_id}."}
            if run.is_terminal:
                return {"error": f"Run {run_id} already finished ({run.status.value})."}
            run.status = RunStatus.cancelled
            credits.release_unused(session, run)
            session.commit()
        return {"cancelled": int(run_id)}

    # ------------------------------------------------------------------- preview

    def preview(self, run_id: int) -> dict:
        """The edit as a timeline, before a single frame is rendered.

        Built by the same function the Studio tab uses, so what the agent describes
        and what you scrub are the same object — including the list of stages the
        preview is *not* yet showing.
        """
        from ..api.routes_preview import build_timeline

        with self._session() as session:
            user = self._user(session)
            run = session.get(Run, int(run_id)) if user else None
            if run is None or user is None or run.user_id != user.id:
                return {"error": f"No run {run_id}."}
            try:
                timeline = build_timeline(run, user)
            except Exception as exc:                          # pragma: no cover
                return {"error": f"Could not build a preview: "
                                 f"{type(exc).__name__}: {exc}"}
            data = timeline.as_dict()

        scenes = data.get("scenes") or []
        return {
            "run": int(run_id),
            "url": f"/runs/{run_id}/preview",
            "ready": bool(data.get("ready")),
            "missing": data.get("missing") or [],
            "scenes": len(scenes),
            "seconds": round(float(data.get("duration") or 0.0), 1),
            "frame": f"{data.get('width')}x{data.get('height')}",
            "first_scenes": [
                {"at": round(float(s.get("start") or 0), 1),
                 "text": str(s.get("caption") or s.get("text") or "")[:90]}
                for s in scenes[:6]
            ],
            "note": "Open the Studio tab to scrub it. Nothing has been rendered yet.",
        }

    # -------------------------------------------------------------------- styles

    def list_styles(self) -> dict:
        from ..style import editing

        rows = editing.available()
        return {"styles": rows, "count": len(rows),
                "note": "Learn one from a creator's videos with the vision CLI, "
                        "then apply it to a channel." if not rows else ""}

    def apply_style(self, style: str, channel: Any) -> dict:
        from ..style import editing

        with self._session() as session:
            user = self._user(session)
            if user is None:
                return {"error": "No account."}
            row = self._channel(session, user, channel)
            if row is None:
                return {"error": f"No channel matching {channel!r}."}
            try:
                found = editing.get(style)
            except (KeyError, FileNotFoundError):
                names = [s["key"] for s in editing.available()]
                return {"error": f"No style called {style!r}.", "available": names}

            profile = dict(row.style_profile or {})
            profile.update(found.to_channel_profile())
            row.style_profile = profile
            session.commit()
            return {"applied": found.name, "to": row.name, "channel_id": row.id,
                    "summary": found.summary()}

    def blend_styles(self, first: str, second: str, *, weight: float = 0.5,
                     name: str = "") -> dict:
        from ..style import editing

        try:
            left, right = editing.get(first), editing.get(second)
        except (KeyError, FileNotFoundError) as exc:
            return {"error": str(exc),
                    "available": [s["key"] for s in editing.available()]}
        mixed = editing.blend(left, right, float(weight), name=name or "")
        mixed.save()
        return {"created": mixed.name, "key": editing.slug(mixed.name),
                "summary": mixed.summary(), "weight": float(weight)}

    # ------------------------------------------------------------------ research

    def research_channel(self, reference: str, *, limit: int = 50) -> dict:
        """Mine a channel for outliers, starting from a link.

        This is the flow that was missing. Research used to demand a table of numbers,
        which meant leaving the app, exporting statistics from somewhere else and
        pasting them back — so nobody used it. A channel URL, a @handle or a video
        link is what you actually have in your clipboard.

        No API key is needed: without one the public page is read directly, and dates
        that had to be reconstructed are marked rather than presented as measured.
        """
        from ..research import sources

        link = parse_link(reference)
        # The wrong link is a more specific problem than a missing key, so it is
        # reported first. Told about the key instead, you would go and get one and
        # then hit exactly the same wall with the same video link.
        if link.kind == "video":
            return {"error": "That is a single video. Give me the channel it is on — "
                             "an outlier only means something against its own cohort, "
                             "and one video has no cohort.",
                    "link": link.as_dict()}

        settings = get_settings()
        target = link.value or reference.strip()
        try:
            parsed, via = sources.read_channel(
                target, api_key=settings.youtube_api_key, limit=int(limit)
            )
        except sources.ResearchError as exc:
            return {
                "error": str(exc),
                "link": link.as_dict(),
                "alternative": "Or paste the rows yourself and I will score them "
                               "with score_videos.",
            }

        scored = self._score(parsed, source=target)
        scored["via"] = via
        return scored

    def score_videos(self, text: str, *, limit: int = 12) -> dict:
        """Turn pasted statistics into outliers: what genuinely beat its own cohort."""
        from ..research import sources

        try:
            parsed = sources.parse(text or "")
        except (ValueError, TypeError) as exc:
            return {"error": f"Could not read that: {exc}"}
        return self._score(parsed, limit=limit)

    @staticmethod
    def _score(parsed, *, source: str = "", limit: int = 12) -> dict:
        from ..research.outliers import find_outliers, summarise

        if not parsed.videos:
            return {"error": "Nothing scoreable in that. Each row needs at least a "
                             "title, a view count and a publish date.",
                    "skipped": parsed.skipped[:5]}

        found = find_outliers(parsed.videos)
        return {
            "source": source,
            "videos": len(parsed.videos),
            "skipped": len(parsed.skipped),
            **summarise(found),
            "outliers": [item.as_dict() for item in found[:limit]],
            "next": "Pick one and I will write angles from it — the multiple is the "
                    "evidence, so say what transfers and what was specific to them.",
        }

    # --------------------------------------------------------------------- voice

    def cast_voice(self, *, channel: Any = None, pitch: str = "", pace: str = "",
                   energy: str = "", accent: str = "", limit: int = 3) -> dict:
        """Shortlist voices against a described target, ranked with the reasons.

        The reasons and caveats come back with the ranking rather than being left
        behind it. "Adam, 0.82" is a number to trust blindly; "Adam — low pitch
        matches, measured 96 Hz from its own preview; caveat: no accent evidence" is
        something you can disagree with, which is the point of a shortlist.
        """
        from ..voice.casting import VoiceTarget, casting_summary, shortlist

        target = VoiceTarget(
            pitch_band=pitch or None, pace=pace or None,
            energy=energy or None, accent=accent or None,
            evidence=[f"described by you: {part}" for part in
                      (pitch, pace, energy, accent) if part],
            gaps=[name for name, part in
                  (("pitch", pitch), ("pace", pace), ("energy", energy),
                   ("accent", accent)) if not part],
        )
        found = shortlist(target, limit=max(1, min(int(limit), 8)))
        if not found:
            return {"error": "No voices to rank. Run `forgecast-voice sync` to read "
                             "your ElevenLabs account, or describe the voice you want."}

        out = {
            "target": target.as_dict(),
            "candidates": [candidate.as_dict() for candidate in found],
            "summary": casting_summary(target, found),
        }
        if channel is not None:
            out["apply_with"] = ("update_channel with voice_id set to the one you "
                                 "pick — I will not choose the voice for you")
        return out

    def voice_catalogue(self) -> dict:
        """What voices are known, and whether they were measured or assumed."""
        from ..voice.catalogue import STOCK_VOICES
        from ..voice.discover import load_catalogue

        measured = load_catalogue()
        if measured:
            return {"source": "measured from your ElevenLabs account",
                    "count": len(measured),
                    "voices": [voice.as_dict() for voice in measured[:40]]}
        return {
            "source": "offline fallback list",
            "count": len(STOCK_VOICES),
            "voices": [voice.as_dict() for voice in STOCK_VOICES],
            "caveat": "These names are the stock set and may not exist on your "
                      "account. Run `forgecast-voice sync` to read the real one and "
                      "measure each preview clip.",
        }

    # -------------------------------------------------------------------- assets

    def open_folder(self, run_id: int = 0) -> dict:
        """Where a run's files are on disk, so they can be opened in a file manager."""
        settings = get_settings()
        base: Path = settings.storage_dir.resolve()
        if run_id:
            path = base / "runs" / str(int(run_id))
            if not path.exists():
                return {"error": f"Run {run_id} has no files yet.", "path": str(path)}
            files = sorted(p.name for p in path.rglob("*") if p.is_file())[:40]
            return {"path": str(path), "files": files, "count": len(files)}
        return {"path": str(base)}

    # -------------------------------------------------------------------- skills

    # Skills are files under the installation's storage directory, like learned styles
    # and connector settings: they are this studio's craft rather than one login's, so
    # there is no per-account row to filter here. See `forgecast/skills.py`.

    def list_skills(self) -> dict:
        """Every skill, with the line that decides whether to load it — and no bodies.

        The bodies are left out on purpose. The three shipped starters alone are about
        nine thousand characters, so a listing that carried them would spend a whole
        tool result on documents that mostly turn out not to apply, and a tool that
        floods the transcript is a tool the agent learns to stop calling. `when_to_use`
        is the entire basis for the decision and `words` says whether loading one costs
        a paragraph or a page.
        """
        from .. import skills as library

        try:
            rows = library.available()
        except OSError as exc:
            return {"error": f"Could not read the skills folder: {exc}"}

        return {
            "count": len(rows),
            "skills": [{"slug": row["slug"], "name": row["name"],
                        # A skill saved without one still has to be judgeable, so the
                        # first line of prose stands in rather than an empty string.
                        "when_to_use": row["when_to_use"] or row["summary"],
                        "words": row["words"]} for row in rows],
            "folder": str(library.directory().resolve()),
            "next": "load_skill on every slug whose when_to_use covers the task, then "
                    "name the skill you followed." if rows else
                    "Nothing written yet. The Skills page is where they are added.",
        }

    def load_skill(self, slug: str) -> dict:
        """One skill in full, ready to be followed.

        A slug that names nothing comes back as an error carrying the slugs that do
        exist. Raising instead would put a stack trace in a log nobody opens, and the
        agent's only sensible next move — asking for the right one — needs the
        alternatives in this same result rather than in a second call.
        """
        from .. import skills as library

        wanted = (slug or "").strip()
        if not wanted:
            return self._no_skill("Name the skill to load — a slug from list_skills.")
        try:
            skill = library.get(wanted)
        except KeyError:
            return self._no_skill(f"No skill called {wanted!r}.")
        except (ValueError, OSError) as exc:
            return self._no_skill(f"Could not load {wanted!r}: {exc}")

        return {
            "slug": skill.slug,
            "name": skill.name,
            "when_to_use": skill.when_to_use,
            "words": len(skill.body.split()),
            "updated_at": skill.updated_at,
            "body": skill.body,
            "follow": "Follow this for the rest of the task and say in your reply that "
                      "you followed it — a document loaded silently cannot be checked "
                      "against what you produced.",
        }

    def _no_skill(self, reason: str) -> dict:
        """A refusal that names the slugs that do exist, inside the sentence.

        The MCP wrapper sends `error` as the whole tool result and drops the rest of
        the dict, so alternatives kept in a sibling key are alternatives the agent
        never sees — and asking for a real slug is its only sensible next move.
        """
        known = self._skill_slugs()
        return {"error": f"{reason} These exist: {', '.join(known) or 'none yet'}.",
                "skills": known}

    @staticmethod
    def _skill_slugs() -> list[str]:
        from .. import skills as library

        try:
            return [row["slug"] for row in library.available()]
        except OSError:                                               # pragma: no cover
            return []
