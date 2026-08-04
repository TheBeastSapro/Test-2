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

import json
import logging
import re
import secrets
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import credits, scripting
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


def epidemic_cache_path() -> Path:
    """Where the Epidemic Sound half of the voice catalogue lives.

    Under the configured storage directory rather than beside
    `voice.discover.DEFAULT_CACHE`, which is a *relative* path: a launcher started from
    somewhere other than the project root writes a catalogue at a second location that
    nothing afterwards reads. Anchoring to `storage_dir` also keeps the test suite out
    of the repository, since it points that at a temporary directory.
    """
    return get_settings().storage_dir / "voice_catalogue_epidemic.json"


def styles_dir() -> Path:
    """The one shelf of learned editing styles, for the chat and the page both.

    `editing.DEFAULT_DIRECTORY` is `./storage/styles` — *relative*, so a launcher
    started from anywhere but the project root reads a different folder from the one
    `/styles` renders. A style learned in the chat would then be a style the page
    cannot see, which is the same disagreement `epidemic_cache_path` above exists to
    prevent, and it is worse here because the style shelf is the thing being written.
    """
    return get_settings().storage_dir / "styles"


def edits_dir() -> Path:
    """Where paper edits are kept between being drafted and being approved.

    On disk rather than in memory: the plan is the artifact an operator is meant to go
    away and read, and a plan that evaporates when the process restarts is a plan
    nobody is going to take their time over.
    """
    path = get_settings().storage_dir / "edits"
    path.mkdir(parents=True, exist_ok=True)
    return path


def layers_dir() -> Path:
    """Where cutouts and composites are written."""
    path = get_settings().storage_dir / "layers"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cuts_dir() -> Path:
    """Where the videos cut from approved paper edits land.

    Beside `edits/` rather than inside it, so that folder stays what its name says: the
    paper edits, and nothing that was made from one. It is also what lets the Files
    browser answer "did the approval produce anything" by opening one directory — the
    question the operator actually asks after approving.
    """
    path = get_settings().storage_dir / "cuts"
    path.mkdir(parents=True, exist_ok=True)
    return path


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

    Setting up a channel starts with a link rather than a form, because a link is
    what is already in the operator's clipboard and a form asks them to retype what
    it contains. This is the first step of that: work out whether you were given a
    video or a channel before deciding what to fetch.
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


def _as_list(value: Any) -> list[str]:
    """One reference or several, however the caller happened to send them.

    MCP arguments arrive as whatever the model produced, and "several references" is
    the case that matters most here — a style learned from one video is an anecdote. A
    list, a comma-separated string and a pasted column of lines all mean the same
    thing, and rejecting two of the three teaches the agent to send one at a time.
    """
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[\n,]+", value)
    elif isinstance(value, (list, tuple, set)):
        parts = [str(item) for item in value]
    else:
        parts = [str(value)]
    return [item.strip() for item in parts if str(item).strip()]


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
                    # Named because the two vendors bill differently, so "which voice"
                    # and "whose credits" are two separate answers.
                    "voice_vendor": channel.voice_vendor or "(default routing)",
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
        allowed = {"name", "niche", "language", "voice_id", "voice_vendor", "avatar_id",
                   "aspect_ratio", "target_duration_seconds", "style_profile",
                   "youtube_channel_id", "scripting_style"}
        # Checked against what can actually be loaded right now, for the same reason the
        # vendor below is: `prompt_block` deliberately falls back to the house method
        # rather than failing, so a typo'd slug is not an error anybody sees — it is a
        # channel that quietly writes to a method nobody chose, run after run.
        wanted_method = str(changes.get("scripting_style") or "").strip()
        if wanted_method and scripting.get(wanted_method) is None:
            return {"error": f"{wanted_method!r} is not a scripting style that can be "
                             f"loaded right now.",
                    "available": [row["slug"] for row in scripting.available()],
                    "folder": scripting.folder_status()["note"]}
        # Checked against the catalogue rather than stored as typed, because a typo here
        # is not a wrong voice — it is a channel whose narration vendor does not exist,
        # which surfaces as an unexplained failure at the voice node several minutes and
        # several paid image calls into a run.
        vendor = str(changes.get("voice_vendor") or "").strip()
        if vendor:
            from ..providers.registry import CATALOGUE, Capability
            entry = CATALOGUE.get(vendor)
            if entry is None or entry[0] is not Capability.voice:
                usable = sorted(name for name, (cap, _, _) in CATALOGUE.items()
                                if cap is Capability.voice)
                return {"error": f"{vendor!r} is not a narration vendor. "
                                 f"Pick one of {usable}, or pass an empty string to let "
                                 f"the default routing decide."}
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

        rows = editing.available(styles_dir())
        return {"styles": rows, "count": len(rows),
                "note": "Learn one with learn_style from a video of theirs — several "
                        "rather than one — then apply it to a channel." if not rows
                        else ""}

    def list_scripting_styles(self) -> dict:
        """Which scripting methods exist, and which channel is written to each.

        A different thing from `list_styles` above, and the two are easy to conflate to
        the point of being harmful: an *editing* style is cut rhythm, grade and captions,
        applied by `apply_style`; a *scripting* style is how the words are structured,
        chosen per channel and stored on the channel row. An agent that offers to "apply
        a style" after reading this would change the wrong thing entirely, so nothing here
        writes — changing it is `update_channel`.

        The channel list is scoped to this account, and it is included because the answer
        to "which method is this channel using" is the reason anyone calls this at all.
        """
        rows = scripting.available()
        by_slug = {row["slug"]: row for row in rows}

        with self._session() as session:
            user = self._user(session)
            if user is None:
                return {"error": "No account."}
            channels = session.execute(
                select(Channel).where(Channel.user_id == user.id).order_by(Channel.id)
            ).scalars().all()
            using = [
                {"channel": channel.name,
                 "scripting_style": channel.scripting_style or scripting.HOUSE_SLUG,
                 # Named here rather than left for the agent to work out from the two
                 # lists: a channel pointing at a folder that has gone still writes
                 # scripts, to the house method, and that is the fact worth surfacing.
                 "available": (channel.scripting_style or scripting.HOUSE_SLUG) in by_slug}
                for channel in channels
            ]

        folder = scripting.folder_status()
        return {
            "styles": rows,
            "count": len(rows),
            "channels": using,
            "folder": folder["path"],
            "folder_note": folder["note"],
            "default": scripting.HOUSE_SLUG,
            "note": "Set a channel's method with update_channel(scripting_style=...). "
                    "This is not the editing style — that is list_styles/apply_style.",
        }

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
                found = editing.get(style, styles_dir())
            except (KeyError, FileNotFoundError):
                names = [s["key"] for s in editing.available(styles_dir())]
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

        folder = styles_dir()
        try:
            left, right = editing.get(first, folder), editing.get(second, folder)
        except (KeyError, FileNotFoundError) as exc:
            return {"error": str(exc),
                    "available": [s["key"] for s in editing.available(folder)]}
        mixed = editing.blend(left, right, float(weight), name=name or "")
        mixed.save(folder)
        return {"created": mixed.name, "key": editing.slug(mixed.name),
                "summary": mixed.summary(), "weight": float(weight)}

    def learn_style(self, references: Any, *, name: str = "", upgrade: bool = True,
                    max_seconds: int = 0,
                    on_note: Callable[[str], None] | None = None) -> dict:
        """Measure a creator's videos and keep what they do as a named editing style.

        The gap this closes: `style.learn` had exactly one caller in the whole tree, the
        vision CLI, so `/styles` and the agent could read, apply, blend, refine and
        delete styles and nothing in the application could produce one. A shelf you can
        only take things off is a shelf that is always empty.

        Several references rather than one, because a style is what survives across a
        creator's work and a single video is an anecdote. Each is measured on its own so
        one unreadable file costs one reference instead of the whole attempt.

        Slow — it decodes video — so it takes an `on_note` and every caller runs it off
        the event loop. The upgrade pass runs by default and every departure it makes
        from the reference is returned, because the difference between "this is how they
        cut" and "this is how we cut" is the thing that must not get quietly baked in.
        """
        from ..style import editing, refine
        from ..vision import AcquireError, ProbeError, analyse_file, analyse_reference

        def note(line: str) -> None:
            if on_note is not None:
                on_note(line)

        wanted = _as_list(references)
        if not wanted:
            return {"error": "Learning a style needs at least one reference — a video "
                             "attached to this conversation, or a link to one."}
        title = str(name or "").strip()
        if not title:
            return {"error": "Give the style a name. It is the key it is saved and "
                             "applied under, so 'their look' beats 'style 1'."}

        profiles: list[dict] = []
        failures: list[str] = []
        workdir = Path(tempfile.mkdtemp(prefix="forgecast-learn-"))
        for index, reference in enumerate(wanted, start=1):
            note(f"Measuring {index} of {len(wanted)}: {reference}")
            try:
                local, why = self._supplied(reference)
                if local is not None:
                    # `narrative=True` is what makes this a learn rather than an
                    # analyse: it transcribes the reference and sections what it says
                    # into hook, beats and close. Off by default in `analyse_file`
                    # because it costs about the length of the video — which is a price
                    # worth paying exactly once per reference, here, and never on the
                    # paths that re-measure a file to check an edit landed.
                    profiles.append(
                        analyse_file(local, narrative=True).as_dict(include_shots=False))
                elif "://" in reference:
                    # A link is acquired first. Kept separate from the local path so a
                    # mistyped filename is reported as a missing file rather than
                    # attempted as a download and reported as a network failure.
                    measured, _got = analyse_reference(
                        reference, workdir, narrative=True,
                        max_seconds=float(max_seconds) if max_seconds else None)
                    profiles.append(measured.as_dict(include_shots=False))
                else:
                    failures.append(f"{reference} — {why}")
                    continue
                note(f"Measured {reference}")
            except (AcquireError, ProbeError, OSError, ValueError) as exc:
                failures.append(f"{reference} — {exc}")
                note(f"Could not measure {reference}: {exc}")

        if not profiles:
            # The reasons are in the sentence rather than beside it: the MCP wrapper
            # sends `error` as the whole result, and "nothing could be measured" with
            # the reasons in a dropped sibling key is a refusal nobody can act on.
            return {"error": "Nothing could be measured, so there is no style to save. "
                             + "; ".join(failures),
                    "failures": failures}

        style = editing.learn(profiles, name=title, reference=str(wanted[0]))
        departures: list[str] = []
        if upgrade:
            style, changes = refine(style, name=title)
            departures = [str(item) for item in changes]
        path = style.save(styles_dir())
        note(f"Saved {style.name}")

        # Fields the references disagreed about, named. A median over sources that do
        # not agree is a number with a confidence nobody can see, and the operator is
        # the only one who can decide whether to trust it.
        weak = sorted(key for key, value in (style.spread or {}).items() if value > 0.5)
        return {
            "learned": style.name,
            "key": style.key,
            "summary": style.summary(),
            "measured": len(profiles),
            "failures": failures,
            "path": str(path),
            "departures": departures,
            "departures_note": (
                "Measured from the references, then changed — each one because the "
                "reference crossed from a choice into a defect." if departures else
                "None — the references were already inside every guard rail."),
            "weak_fields": weak,
            "next": f"apply_style('{style.key}', channel) puts it on a channel.",
        }

    # ------------------------------------------------------------- render backend

    def render_backends(self) -> dict:
        """Which engine draws motion scenes, what each channel is set to, and why.

        `finalize` reads `motion_backend` off the channel's style profile and off the
        run options, and until this existed the only writer in the tree was one CLI
        flag. So an operator who installed the layered renderer through the app kept
        rendering with ffmpeg for ever, and the downgrade was a `log.warning` in a file
        nobody opens. Reporting it is half the fix; `set_motion_backend` is the other.
        """
        from ..desktop import toolchain
        from ..render.backends import BACKENDS, backend_for

        engines = []
        for key, cls in BACKENDS.items():
            engines.append({"backend": key, "available": bool(cls().available())})
        installed, absent = toolchain.extra_installed("motion")
        spec = toolchain.EXTRAS["motion"]

        with self._session() as session:
            user = self._user(session)
            if user is None:
                return {"error": "No account."}
            channels = session.execute(
                select(Channel).where(Channel.user_id == user.id).order_by(Channel.id)
            ).scalars().all()
            using = []
            for channel in channels:
                asked = str((channel.style_profile or {}).get("motion_backend") or "ffmpeg")
                # Resolved rather than repeated, so this says what will actually run.
                # An unavailable backend downgrades silently at render time, and a
                # panel echoing the stored word would agree with the setting and
                # disagree with the video.
                using.append({"channel": channel.name, "id": channel.id,
                              "asked_for": asked,
                              "will_use": backend_for(asked).name})

        return {
            "engines": engines,
            "channels": using,
            "default": "ffmpeg",
            "motion_extra": {
                "key": "motion", "label": spec["label"], "installed": bool(installed),
                "missing": absent, "megabytes": spec["megabytes"],
                "gives": spec["gives"],
            },
            "install": "" if installed else
                       "Forgecast installs it — the Install button on the toolchain "
                       "banner, or POST /api/setup/extras/motion.",
            "note": "remotion needs that toolset and carries its own licence terms; "
                    "ffmpeg needs nothing and is the default.",
        }

    def set_motion_backend(self, channel: Any, backend: str) -> dict:
        """Choose the renderer for one channel's motion scenes.

        A targeted setter rather than `update_channel(style_profile=...)`, which takes a
        wholesale dict: writing the whole profile to change one key is how a channel's
        learned render spec, map style and loudness target get wiped by a caller that
        only meant to switch renderer. This merges one validated key.

        An unavailable choice is stored and *reported as a downgrade* rather than
        refused. Refusing it would mean the setting cannot be made before the toolset
        is installed, and the honest failure here is not "you may not want this" — it is
        that the operator never found out they were not getting it.
        """
        from ..desktop import toolchain
        from ..render.backends import BACKENDS, backend_for

        wanted = str(backend or "").strip().lower()
        if wanted not in BACKENDS:
            return {"error": f"{wanted!r} is not a render backend. "
                             f"Pick one of {sorted(BACKENDS)}."}

        with self._session() as session:
            user = self._user(session)
            if user is None:
                return {"error": "No account."}
            row = self._channel(session, user, channel)
            if row is None:
                return {"error": f"No channel matching {channel!r}."}
            profile = dict(row.style_profile or {})
            profile["motion_backend"] = wanted
            # Reassigned rather than mutated in place: the column is JSON, and
            # SQLAlchemy does not see a mutation of the dict it handed out, so the
            # commit would write nothing and the setting would appear to save.
            row.style_profile = profile
            session.commit()
            name = row.name

        resolved = backend_for(wanted).name
        installed, absent = toolchain.extra_installed("motion")
        downgraded = resolved != wanted
        return {
            "channel": name,
            "motion_backend": wanted,
            "will_use": resolved,
            "downgraded": downgraded,
            "why": (f"{wanted} is not installed here ({absent}), so renders fall back "
                    f"to {resolved} until it is." if downgraded else ""),
            "install": "" if installed or not downgraded else
                       "Forgecast installs it — the Install button on the toolchain "
                       "banner, or POST /api/setup/extras/motion.",
        }

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

    def _measured_voices(self) -> list:
        """Every cached voice from every vendor, as one pool to rank.

        Two caches, one ranking. `forgecast-voice sync` writes the ElevenLabs catalogue
        and `sync_voice_artists` writes the Epidemic Sound one, and casting reads both
        together — because a shortlist that only ever contains one vendor's voices is a
        shortlist that silently answers a different question than the one asked. Each
        voice carries its `provenance`, so the merge is visible rather than implied.
        """
        from ..voice.discover import load_catalogue

        pool = list(load_catalogue())
        known = {voice.voice_id for voice in pool}
        for voice in load_catalogue(epidemic_cache_path()):
            if voice.voice_id not in known:
                pool.append(voice)
        return pool

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
        pool = self._measured_voices()
        # `measured=None` would make shortlist load only the ElevenLabs cache, undoing
        # the merge above. An empty list is not the same as None here, and passing the
        # pool explicitly is what keeps the two vendors in one ranking.
        found = shortlist(target, limit=max(1, min(int(limit), 8)),
                          measured=pool or None)
        if not found:
            return {"error": "No voices to rank. Run `forgecast-voice sync` to read "
                             "your ElevenLabs account, or sync_voice_artists to read "
                             "Epidemic Sound, or describe the voice you want."}

        vendors = sorted({voice.provenance for voice in pool}) if pool else []
        out = {
            "target": target.as_dict(),
            "candidates": [candidate.as_dict() for candidate in found],
            "summary": casting_summary(target, found),
        }
        if vendors:
            out["ranked_across"] = vendors
        if channel is not None:
            out["apply_with"] = ("update_channel with voice_id set to the one you "
                                 "pick — I will not choose the voice for you")
        return out

    def voice_catalogue(self) -> dict:
        """What voices are known, and whether they were measured or assumed."""
        from ..voice.catalogue import STOCK_VOICES

        measured = self._measured_voices()
        if measured:
            # Named per vendor rather than always "your ElevenLabs account", which was
            # true when ElevenLabs was the only vendor and became a wrong label the
            # moment a second one could appear in the same list.
            vendors = sorted({voice.provenance or "account" for voice in measured})
            return {"source": "measured from " + ", ".join(vendors),
                    "count": len(measured),
                    "vendors": vendors,
                    "voices": [voice.as_dict() for voice in measured[:40]]}
        return {
            "source": "offline fallback list",
            "count": len(STOCK_VOICES),
            "voices": [voice.as_dict() for voice in STOCK_VOICES],
            "caveat": "These names are the stock set and may not exist on your "
                      "account. Run `forgecast-voice sync` to read the real one and "
                      "measure each preview clip, or sync_voice_artists to read "
                      "Epidemic Sound's voice artists.",
        }

    # ------------------------------------------------------- epidemic sound voices

    async def voice_artists(self, *, limit: int = 20) -> dict:
        """Epidemic Sound's voice artists, read live rather than from the cache.

        Live because this reports the one thing the cache cannot: each artist's
        `languages` list. `voice.discover.MeasuredVoice` has no field for it, so a
        synced catalogue drops it — and it is the honest basis for narrating one script
        in more than one language.
        """
        from ..providers.base import ProviderError
        from ..providers.epidemic import EpidemicVoiceProvider, MockEpidemicVoice

        settings = get_settings()
        provider = MockEpidemicVoice() if settings.is_mock else EpidemicVoiceProvider()
        usable, reason = provider.available()
        if not usable:
            return {"error": reason}

        try:
            artists = await provider.list_voices(limit=max(1, min(int(limit), 100)))
        except ProviderError as exc:
            return {"error": str(exc)}

        return {
            "source": "mock Epidemic Sound roster (offline)" if settings.is_mock
                      else "Epidemic Sound",
            "count": len(artists),
            "artists": [
                {
                    "voice_id": artist["voice_id"],
                    "name": artist["name"],
                    "gender": artist["labels"]["gender"],
                    "from": artist["labels"]["accent"],
                    "characteristics": artist["labels"]["descriptive"],
                    "languages": artist["languages"],
                    "has_preview": bool(artist["preview_url"]),
                }
                for artist in artists
            ],
            "caveat": "These are the vendor's own words about each artist, not "
                      "measurements. sync_voice_artists downloads each preview clip and "
                      "measures its pitch so cast_voice can rank them on the same scale "
                      "as everything else.",
            "next": "sync_voice_artists to put these into the casting pool.",
        }

    async def sync_voice_artists(self, *, measure: bool = True, limit: int = 60) -> dict:
        """Build the Epidemic Sound half of the casting catalogue, pitch and all.

        Written to its own file rather than the shared one. Overwriting
        `voice_catalogue.json` would delete the ElevenLabs catalogue as a side effect of
        adding a second vendor, and the operator would find out at the next casting.
        """
        from ..providers.base import ProviderError
        from ..providers.epidemic import EpidemicVoiceProvider, MockEpidemicVoice
        from ..voice.discover import build_catalogue, measured_summary

        settings = get_settings()
        provider = MockEpidemicVoice() if settings.is_mock else EpidemicVoiceProvider()
        usable, reason = provider.available()
        if not usable:
            return {"error": reason}

        cache = epidemic_cache_path()
        try:
            voices = await build_catalogue(
                provider, cache_path=cache,
                # Measuring means one preview download per artist. Worth it: measured
                # pitch is the only signal casting actually trusts.
                measure=bool(measure), limit=max(1, min(int(limit), 200)),
            )
        except ProviderError as exc:
            return {"error": str(exc)}
        except OSError as exc:
            return {"error": f"could not write the catalogue to {cache}: {exc}"}

        measured = [voice for voice in voices if voice.measurement == "measured"]
        unmeasured = [voice for voice in voices if voice.measurement != "measured"]
        out = {
            "vendor": "epidemic",
            "voices": len(voices),
            "measured": len(measured),
            "summary": measured_summary(voices),
            "cache": str(cache),
            "next": "cast_voice now ranks these alongside any ElevenLabs voices, on "
                    "measured pitch where it exists.",
        }
        if unmeasured:
            # Named, not counted. "3 unmeasured" hides that all three failed the same
            # way, which is the difference between a flaky download and a wrong URL.
            out["not_measured"] = [
                f"{voice.name}: {voice.measurement}" for voice in unmeasured[:10]
            ]
        return out

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

    # --------------------------------------------------------- supplied footage

    # Forgecast generates: topic in, brief, script, shot list, render. `ingest`, `edit`
    # and `layers` are the way in from the other end — "here is a video, edit it" — and
    # for as long as nothing imported them that direction existed on disk and nowhere
    # else. These are its door. The separation the packages keep is kept here too, as one
    # method per verb: `read_video` measures, `plan_edit` decides, `approve_edit` is the
    # operator agreeing, and `cut_plan` executes what they agreed to and nothing else.

    @staticmethod
    def _supplied(path: Any) -> tuple[Path | None, str]:
        """A file the operator actually handed this install, or a refusal saying so.

        Two roots, and both are needed: attachments land under the app root because
        that is the only folder the agent is allowed to open, and a storage directory
        pointed somewhere else entirely is a supported install rather than an oddity.

        Confined to them on purpose. Everything here is reachable over HTTP by a
        signed-in account, and "measure this video" that accepts any absolute path is a
        file-existence oracle for the whole disk.
        """
        # Lazily, because `assistant` imports this module — at call time it is loaded
        # and the cycle cannot form.
        from .assistant import APP_ROOT

        raw = str(path or "").strip()
        if not raw:
            return None, "no file was named"
        roots = [APP_ROOT.resolve(), get_settings().storage_dir.resolve()]
        try:
            resolved = Path(raw).expanduser().resolve()
        except (OSError, RuntimeError):
            return None, f"{raw} is not a path this can open"
        if not any(resolved == root or root in resolved.parents for root in roots):
            return None, (f"{raw} is outside this install. Attach the file in the chat "
                          f"and pass the path it comes back with.")
        if not resolved.is_file():
            return None, f"there is no file at {resolved}"
        return resolved, ""

    def editing_tools(self) -> dict:
        """What this machine can measure and cut, before a file is handed over.

        Asked first rather than discovered late. Dropping in a two-gigabyte video and
        being told twenty seconds later that the transcription model is absent is the
        exact shape of failure the `ingest` package refuses to have, so the answer is
        available without a file and names the install for anything missing.
        """
        from ..desktop import toolchain
        from ..ingest import available as readings_available
        from ..layers import matte

        readings = readings_available()
        readings["subject cutout"] = matte.available()
        installed, absent = toolchain.extra_installed("edit")
        spec = toolchain.EXTRAS["edit"]

        # Which installer fixes what, kept apart. The probe and the silence map need
        # ffmpeg, which the app installs as part of the mandatory toolchain; the other
        # three are the optional extra. Offering the 400 MB extra for a missing ffmpeg
        # would be an install that does not fix the thing it was offered for.
        needs_extra = [name for name in ("shots", "transcript", "subject cutout")
                       if not readings[name][0]]
        needs_ffmpeg = [name for name in ("probe", "silence")
                        if not readings[name][0]]

        return {
            "can": sorted(name for name, (ok, _why) in readings.items() if ok),
            "cannot": [{"reading": name, "why": why}
                       for name, (ok, why) in sorted(readings.items()) if not ok],
            "edit_extra": {
                "key": "edit", "label": spec["label"], "installed": bool(installed),
                "missing": absent, "megabytes": spec["megabytes"],
                "gives": spec["gives"],
            },
            # Never a command to go and run. The app installs its own tools, and being
            # handed homework instead was reported as a defect once already.
            "install": "" if not needs_extra else
                       f"Forgecast installs it ({spec['megabytes']} MB, once) — the "
                       f"Install button on the toolchain banner, or "
                       f"POST /api/setup/extras/edit.",
            "install_ffmpeg": "" if not needs_ffmpeg else
                              "ffmpeg is missing and everything here needs it. The "
                              "Setup page installs it — POST /api/setup/install.",
            "note": "A missing reading is not a blocked edit. What can be measured is "
                    "measured, and the plan names what it could not see.",
        }

    def read_video(self, path: Any, *, want_transcript: bool = True,
                   want_shots: bool = True, limit: int = 12) -> dict:
        """Measure a supplied video. Decides nothing and changes nothing.

        Partial results are the normal outcome and are returned as such — `missing`
        names every reading that could not be taken and why. An edit built from three of
        the four available readings is a worse edit; one that could not start at all is
        no edit.
        """
        from .. import ingest

        found, why = self._supplied(path)
        if found is None:
            return {"error": why}
        try:
            measured = ingest.read(found, want_transcript=bool(want_transcript),
                                   want_shots=bool(want_shots))
        except Exception as exc:
            # The probe is the one reading with nothing to degrade to: a file that
            # cannot be probed is not a video.
            return {"error": f"Could not read {found.name}: "
                             f"{type(exc).__name__}: {exc}"}

        cap = max(1, min(int(limit or 12), 60))
        return {
            "path": str(found),
            "summary": measured.summary(),
            "seconds": measured.media.duration,
            "frame": f"{measured.media.width}x{measured.media.height}",
            "fps": measured.media.fps,
            "shots": len(measured.shots),
            "shots_per_minute": measured.shots_per_minute,
            "quiet_seconds": measured.quiet_seconds,
            "speech_seconds": measured.speech_seconds,
            "lines": len(measured.lines),
            "first_lines": [{"at": round(line.start, 2), "text": line.text}
                            for line in measured.lines[:cap]],
            "missing": list(measured.missing),
            "next": "plan_edit on the same path writes the paper edit. Nothing is cut "
                    "until you have read it and approved it.",
        }

    def plan_edit(self, path: Any, *, drop_fillers: bool = True) -> dict:
        """Write the paper edit for a supplied video and save it to be argued with.

        It does not cut, open an output file or spend anything. That is the whole design
        of the package behind it: a plan costs nothing to produce, nothing to change and
        nothing to throw away, and it fixes every expensive decision that comes after
        it. An operator who can read "47s of silence across 38 gaps" corrects it in ten
        seconds; the same operator watching a finished render has to describe what is
        wrong with something already paid for.
        """
        from .. import ingest
        from ..edit import tighten
        from ..style import editing

        found, why = self._supplied(path)
        if found is None:
            return {"error": why}
        try:
            measured = ingest.read(found)
        except Exception as exc:
            return {"error": f"Could not read {found.name}: "
                             f"{type(exc).__name__}: {exc}"}
        plan = tighten(measured, drop_fillers=bool(drop_fillers))

        with self._session() as session:
            user = self._user(session)
            if user is None:
                return {"error": "No account."}
            owner = user.id

        plan_id = f"{editing.slug(found.stem)}-{secrets.token_hex(3)}"
        record = {
            "id": plan_id,
            # The owner travels with the plan, because these are files rather than rows
            # and there is no foreign key to lean on. Every read filters on it.
            "user_id": owner,
            "source": str(found),
            "state": "drafted",
            "note": "",
            "plan": plan.as_dict(),
            "markdown": plan.as_markdown(),
            "measured": measured.summary(),
        }
        (edits_dir() / f"{plan_id}.json").write_text(
            json.dumps(record, indent=2), encoding="utf-8")

        return {
            "plan_id": plan_id,
            "source": str(found),
            "original_seconds": plan.original_seconds,
            "final_seconds": plan.final_seconds,
            "removed_seconds": plan.removed_seconds,
            "tightened_by": plan.tightened_by,
            "cuts": len([item for item in plan.decisions if item.action != "keep"]),
            "unknown": list(plan.unknown),
            "markdown": plan.as_markdown(),
            "state": "drafted",
            "next": "Nothing has been cut. Show this to the operator and let them "
                    "approve or reject it — approve_edit is theirs to call, not yours. "
                    "Once they have approved it, cut_plan makes the file.",
        }

    def edit_plans(self, plan_id: str = "", *, limit: int = 20) -> dict:
        """The saved paper edits, or one of them in full. Reads only."""
        with self._session() as session:
            user = self._user(session)
            if user is None:
                return {"error": "No account."}
            owner = user.id

        wanted = str(plan_id or "").strip()
        if wanted:
            record = self._edit_record(wanted, owner)
            if record is None:
                return {"error": f"No edit plan {wanted!r}."}
            return {"plan_id": record["id"], "source": record["source"],
                    "state": record["state"], "note": record.get("note", ""),
                    "measured": record.get("measured", ""),
                    # What executing it produced, if it has been executed. Carried on the
                    # plan rather than looked up from the folder so that a plan and the
                    # file cut from it cannot disagree about which is which.
                    "cut": record.get("cut") or {},
                    "markdown": record["markdown"], **record["plan"]}

        rows = []
        for record in self._edit_records(owner):
            body = record.get("plan") or {}
            rows.append({"plan_id": record["id"], "source": record["source"],
                         "state": record["state"],
                         "original_seconds": body.get("original_seconds"),
                         "final_seconds": body.get("final_seconds"),
                         "tightened_by": body.get("tightened_by"),
                         "cut": (record.get("cut") or {}).get("path", "")})
        rows = rows[:max(1, min(int(limit or 20), 100))]
        return {"plans": rows, "count": len(rows)}

    def approve_edit(self, plan_id: str, *, approve: bool = True,
                     note: str = "") -> dict:
        """Accept or reject a paper edit. The operator's call, never the agent's.

        This is the gate, and it sits here rather than beside a cutting function because
        this app puts gates on the stage that *determines* the spend, not the stage that
        incurs it. Everything expensive downstream is committed to by this decision, and
        it is reversible up to the moment it is taken.

        It records the decision and releases the cut; it does not perform it. Cutting a
        twenty-minute source is minutes of encoding, and an approval that waited for it
        would be an operator's decision that could fail because ffmpeg was busy. So this
        stays instant and `cut_plan` — which refuses anything this has not approved — is
        the stage that does the work.
        """
        with self._session() as session:
            user = self._user(session)
            if user is None:
                return {"error": "No account."}
            owner = user.id

        wanted = str(plan_id or "").strip()
        record = self._edit_record(wanted, owner)
        if record is None:
            known = [row["plan_id"] for row in self.edit_plans().get("plans", [])]
            # The ids that do exist go in the sentence, not beside it. Asking for the
            # right one is the only sensible next move, and the MCP wrapper drops every
            # key but `error`.
            return {"error": f"No edit plan {wanted!r}. These exist: "
                             f"{', '.join(known) or 'none yet'}.",
                    "plans": known}

        record["state"] = "approved" if approve else "rejected"
        record["note"] = str(note or "")
        (edits_dir() / f"{record['id']}.json").write_text(
            json.dumps(record, indent=2), encoding="utf-8")

        body = record.get("plan") or {}
        return {
            "plan_id": record["id"], "state": record["state"],
            "source": record["source"], "note": record["note"],
            "final_seconds": body.get("final_seconds"),
            "keeps": [item for item in (body.get("decisions") or [])
                      if item.get("action") == "keep"] if approve else [],
            # Whether the work behind the gate has been released, as a fact rather than
            # as a claim that it is finished. The cut is a separate stage and it may not
            # have started yet, so an approval that reported "done" would be the app
            # claiming work that is still queued.
            "released": bool(approve),
            "note_to_reader": (
                "Approved. The cut is released — cut_plan executes these spans and "
                "writes the video; nothing is cut until it runs." if approve else
                "Rejected. Say what was wrong and plan_edit can be run again with "
                "different thresholds."),
        }

    def cut_plan(self, plan_id: str, *, on_note: Callable[[str], None] | None = None,
                 fps: int = 0) -> dict:
        """Cut the video an approved paper edit describes. Refuses an unapproved one.

        The refusal is the point of the method existing separately. Anything that can
        reach the studio can reach this — the chat's tools included — and it will not act
        on a plan the operator has not agreed to, which is what keeps `approve_edit` a
        gate rather than a formality that something downstream can route around.

        Slow: it re-encodes, because cutting on keyframes lands on the wrong frame. See
        `render/cut.py` for the measurements behind that choice. Callers in a request or
        on an event loop have to run it on a thread.
        """
        from ..edit import EditPlan
        from ..render import cut as cutter

        with self._session() as session:
            user = self._user(session)
            if user is None:
                return {"error": "No account."}
            owner = user.id

        wanted = str(plan_id or "").strip()
        record = self._edit_record(wanted, owner)
        if record is None:
            return {"error": f"No edit plan {wanted!r}."}
        if record.get("state") != "approved":
            state = record.get("state") or "drafted"
            return {"error": f"Edit plan {wanted} is {state}, not approved. Show it to "
                             f"the operator and let them approve it — approving is "
                             f"theirs to do, and it is what releases this.",
                    "state": state}

        # The plan travels with its own source path, and the file behind it is checked
        # against the same two roots everything else here is. A plan is a JSON file, and
        # a JSON file whose `source` is `/etc/shadow` is a plausible thing to be handed.
        source, why = self._supplied((record.get("plan") or {}).get("source")
                                     or record.get("source"))
        if source is None:
            return {"error": why}

        plan = EditPlan.from_dict(record.get("plan") or {})
        target = cuts_dir() / f"{record['id']}.mp4"
        try:
            made = cutter.execute(plan, target, source=source,
                                  fps=int(fps) or None, on_note=on_note)
        except Exception as exc:
            # Everything ffmpeg can do wrong ends up here as a sentence. A raise would
            # cross the MCP boundary as a stack trace in a log file nobody opens, and it
            # would leave the streaming route's worker thread with nothing to report.
            return {"error": f"Could not cut {source.name}: "
                             f"{type(exc).__name__}: {exc}"}

        record["cut"] = made.as_dict()
        (edits_dir() / f"{record['id']}.json").write_text(
            json.dumps(record, indent=2), encoding="utf-8")

        return {
            "plan_id": record["id"], "state": record["state"],
            **made.as_dict(),
            # Storage-relative as well as absolute, because the two readers of this
            # answer want different ones: a person opens the Files browser at the
            # relative path, and anything on this machine opens the absolute one.
            "relative": f"cuts/{record['id']}.mp4",
            "summary": made.summary(),
            "next": "Watch it before it goes anywhere. The plan is still on disk, so a "
                    "cut that took out too much can be re-planned and cut again.",
        }

    @staticmethod
    def _edit_records(owner: int) -> list[dict]:
        """Every plan this account owns, newest first."""
        rows: list[dict] = []
        for path in sorted(edits_dir().glob("*.json"),
                           key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):                              # pragma: no cover
                continue
            if int(record.get("user_id") or 0) == int(owner):
                rows.append(record)
        return rows

    @staticmethod
    def _edit_record(plan_id: str, owner: int) -> dict | None:
        """One plan, by id, for this account only.

        The id is never joined onto a path directly — it arrives from a model or a
        request body, and `../../.env` is a valid string. It is matched against the ids
        of the files this account owns instead.
        """
        for record in Studio._edit_records(owner):
            if str(record.get("id")) == str(plan_id):
                return record
        return None

    def cut_subject(self, image: Any, *, text: str = "", background: Any = None,
                    out: str = "") -> dict:
        """Lift the subject onto its own layer, and optionally put a title behind it.

        A refused matte is a result, not an error. Hair, motion blur and soft edges are
        where automatic segmentation fails, and it fails by leaving a fringe the eye
        catches instantly — so a bad cutout falls back to the plain still and says why,
        which is the same degradation the renderer already does when an animation fails.
        """
        from ..layers import cut, matte, text_behind

        ok, why = matte.available()
        if not ok:
            # The offer goes *inside* the sentence. The MCP wrapper sends `error` as the
            # whole tool result and drops every sibling key, so a next step kept in one
            # is a next step the agent never reads — and it then reports the feature as
            # unavailable full stop, which is how a 400 MB install nobody was offered
            # becomes a capability nobody has.
            spec = self._install_hint("edit")
            return {"error": f"{why}. {spec['install']}", **spec}

        source, complaint = self._supplied(image)
        if source is None:
            return {"error": complaint}

        stem = str(out or "").strip() or f"{source.stem}-{secrets.token_hex(3)}"
        target = layers_dir() / f"{Path(stem).name}.png"
        try:
            result = cut(source, target)
        except Exception as exc:                                      # pragma: no cover
            return {"error": f"Could not cut {source.name}: "
                             f"{type(exc).__name__}: {exc}"}

        answer = {**result.as_dict(), "composited": ""}
        if not result.usable:
            answer["next"] = ("Use the plain still. A fringed cutout reads as cheaper "
                              "than no cutout at all, which is why this one is refused.")
            return answer

        wanted = str(text or "").strip()
        if wanted:
            plate = None
            if background is not None:
                plate, complaint = self._supplied(background)
                if plate is None:
                    return {**answer, "error": complaint}
            layered = text_behind(result.path, layers_dir() / f"{Path(stem).name}-title",
                                  wanted, background=plate)
            answer["composited"] = layered.path
            answer["layers"] = layered.layers
        answer["next"] = ("Open the file to check the edge before it goes in a video."
                          if not wanted else
                          "The subject occludes the title — check the overlap reads as "
                          "deliberate rather than as a mistake.")
        return answer

    @staticmethod
    def _install_hint(extra: str) -> dict:
        """The offer that replaces a command to go and run.

        Offered whenever the capability is missing, and deliberately not conditioned on
        the toolset reporting itself installed. The two disagree in the case that
        matters — a stale virtualenv is recorded as installed and imports nothing — and
        the branch that trusts the record is the branch that hands the operator a reason
        with no next step.
        """
        from ..desktop import toolchain

        spec = toolchain.EXTRAS.get(extra) or {}
        return {
            "extra": extra,
            "install": f"Forgecast installs it ({spec.get('megabytes', 0)} MB, once) — "
                       f"the Install button on the toolchain banner, or "
                       f"POST /api/setup/extras/{extra}.",
        }

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
