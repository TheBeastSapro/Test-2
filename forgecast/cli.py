"""Command line entry point.

    forgecast initdb
    forgecast user create you@example.com --password secret --grant 5000
    forgecast channel create --user 1 --name "Deep Field" --niche space
    forgecast run start --channel 1 --topic "Why Betelgeuse keeps dimming"
    forgecast run advance <id> [--auto-approve]
    forgecast run show <id>
    forgecast demo --topic "..."          # end to end in one command, mock providers
    forgecast worker
    forgecast serve
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys

from sqlalchemy import select

from . import credits as billing
from . import nodes  # noqa: F401 - registers node handlers
from .auth import hash_password
from .config import get_settings
from .db import SessionLocal, init_db, session_scope
from .graph.engine import GraphEngine, create_run
from .models import Channel, Node, NodeStatus, Run, RunStatus, User


def _engine() -> GraphEngine:
    return GraphEngine(SessionLocal, worker_id="cli", concurrency=2)


# --------------------------------------------------------------------------- users


def cmd_user_create(args) -> int:
    with session_scope() as session:
        email = args.email.strip().lower()
        if session.execute(select(User).where(User.email == email)).scalar_one_or_none():
            print(f"user {email} already exists", file=sys.stderr)
            return 1
        user = User(email=email, hashed_password=hash_password(args.password))
        session.add(user)
        session.flush()
        billing.grant(session, user.id, args.grant, note="cli grant")
        print(f"user {user.id} created with {args.grant} credits")
    return 0


def cmd_bootstrap(args) -> int:
    """Prepare an empty instance for its owner: tables, account, first channel.

    Idempotent on purpose. This runs on every container start, so a restart must not
    fail because the owner already exists, and must not top the balance up again —
    that would mint credits outside the ledger's reserve/settle discipline.
    """
    init_db()
    email = args.email.strip().lower()
    password = args.password or os.environ.get("FORGECAST_OWNER_PASSWORD", "")

    with session_scope() as session:
        user = session.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()

        if user is None:
            if len(password) < 12:
                print("refusing to create an account with a password shorter than 12 "
                      "characters — this instance may be reachable from the internet",
                      file=sys.stderr)
                return 1
            user = User(email=email, hashed_password=hash_password(password))
            session.add(user)
            session.flush()
            # The idempotency key is what makes a restart safe: a second grant with
            # the same key is a no-op rather than free money.
            billing.grant(session, user.id, args.grant, note="owner grant",
                          idempotency_key=f"bootstrap:{user.id}")
            print(f"owner {email} created (user {user.id}) with {args.grant} credits")
        elif args.reset_password:
            if len(password) < 12:
                print("refusing to set a password shorter than 12 characters",
                      file=sys.stderr)
                return 1
            user.hashed_password = hash_password(password)
            print(f"password reset for {email}")
        else:
            print(f"owner {email} already exists (user {user.id})")

        channel = session.execute(
            select(Channel).where(Channel.user_id == user.id)
        ).scalars().first()
        if channel is None and args.channel:
            channel = Channel(
                user_id=user.id, name=args.channel, niche=args.niche or "",
                voice_id="", target_duration_seconds=args.seconds,
                style_profile={"tone": args.tone} if args.tone else {},
            )
            session.add(channel)
            session.flush()
            print(f"channel {channel.id} '{channel.name}' created")

        balance = billing.balance(session, user.id)

    settings = get_settings()
    print(f"balance {balance} credits · provider mode {settings.provider_mode} · "
          f"signup {'open' if settings.allow_signup else 'closed'}")
    print(f"sign in at {settings.base_url}/login")
    return 0


def cmd_channel_create(args) -> int:
    with session_scope() as session:
        user = session.get(User, args.user)
        if user is None:
            print(f"no user {args.user}", file=sys.stderr)
            return 1
        channel = Channel(
            user_id=user.id,
            name=args.name,
            niche=args.niche or "",
            voice_id=args.voice or "",
            avatar_id=args.avatar or "",
            target_duration_seconds=args.seconds,
            style_profile={"tone": args.tone} if args.tone else {},
        )
        session.add(channel)
        session.flush()
        print(f"channel {channel.id} created")
    return 0


# ---------------------------------------------------------------------------- runs


def cmd_run_start(args) -> int:
    with session_scope() as session:
        channel = session.get(Channel, args.channel)
        if channel is None:
            print(f"no channel {args.channel}", file=sys.stderr)
            return 1
        options = {"target_seconds": args.seconds} if args.seconds else {}
        if args.no_publish:
            options["publish"] = False
        if args.motion_preset:
            options["motion_preset"] = args.motion_preset
        if args.no_motion:
            options["motion"] = False
        if args.motion_backend:
            options["motion_backend"] = args.motion_backend
        try:
            run = create_run(
                session, channel=channel, topic=args.topic, pipeline=args.pipeline,
                options=options,
            )
        except billing.InsufficientCredits as exc:
            print(f"not enough credits: {exc}", file=sys.stderr)
            return 1
        print(f"run {run.id} queued ({run.credits_reserved} credits held)")
    return 0


async def _advance(run_id: int, *, auto_approve: bool, verbose: bool = True) -> RunStatus:
    engine = _engine()
    for _ in range(60):
        status = await engine.advance(run_id)
        if verbose:
            print(f"  run {run_id}: {status.value}")
        if status is not RunStatus.awaiting_approval:
            return status
        if not auto_approve:
            return status
        with session_scope() as session:
            waiting = session.execute(
                select(Node).where(
                    Node.run_id == run_id, Node.status == NodeStatus.awaiting_approval
                )
            ).scalars().all()
            for node in waiting:
                engine.approve(session, node, note="auto-approved by cli")
                if verbose:
                    print(f"  gate {node.key}: auto-approved")
    return await _engine().advance(run_id)


def cmd_run_advance(args) -> int:
    status = asyncio.run(_advance(args.run_id, auto_approve=args.auto_approve))
    print(f"run {args.run_id} finished as {status.value}")
    return 0 if status is RunStatus.completed else 2


def cmd_run_show(args) -> int:
    with session_scope() as session:
        run = session.get(Run, args.run_id)
        if run is None:
            print(f"no run {args.run_id}", file=sys.stderr)
            return 1
        print(f"run {run.id}  {run.status.value}  {run.pipeline}")
        print(f"topic: {run.topic}")
        print(f"credits: held {run.credits_reserved}, spent {run.credits_spent} "
              f"(${billing.credits_to_usd(run.credits_spent)})")
        if run.error:
            print(f"error: {run.error}")
        print("\nnodes:")
        for node in run.nodes:
            deps = ",".join(node.depends_on) or "-"
            gate = " [gate]" if node.requires_approval else ""
            print(f"  {node.key:<14} {node.status.value:<18} deps={deps}{gate}"
                  f"  {node.credits_spent}cr")
            if node.error:
                print(f"      ! {node.error}")
        print("\nartifacts:")
        for artifact in run.artifacts:
            print(f"  {artifact.kind:<7} {artifact.path}  ({artifact.size_bytes} bytes)")
    return 0


def cmd_run_approve(args) -> int:
    engine = _engine()
    with session_scope() as session:
        node = session.execute(
            select(Node).where(Node.run_id == args.run_id, Node.key == args.node)
        ).scalar_one_or_none()
        if node is None:
            print(f"no node {args.node} on run {args.run_id}", file=sys.stderr)
            return 1
        overrides = json.loads(args.overrides) if args.overrides else None
        if args.feedback:
            engine.revise(session, node, args.feedback)
            print(f"revision requested on {args.node}")
        else:
            engine.approve(session, node, note=args.note or "", overrides=overrides)
            print(f"approved {args.node}")
    return 0


# ---------------------------------------------------------------------------- demo


def cmd_demo(args) -> int:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        user = session.execute(
            select(User).where(User.email == "demo@forgecast.local")
        ).scalar_one_or_none()
        if user is None:
            user = User(email="demo@forgecast.local", hashed_password=hash_password("demo"))
            session.add(user)
            session.flush()
        if billing.balance(session, user.id) < 2000:
            billing.grant(session, user.id, 5000, note="demo grant")

        channel = session.execute(
            select(Channel).where(Channel.user_id == user.id)
        ).scalars().first()
        if channel is None:
            channel = Channel(
                user_id=user.id,
                name="Demo Channel",
                niche=args.niche,
                voice_id="demo-voice",
                target_duration_seconds=args.seconds,
                style_profile={
                    "tone": "calm, precise, no hype",
                    "banned_words": ["insane", "crazy", "literally"],
                },
            )
            session.add(channel)
            session.flush()

        run = create_run(
            session,
            channel=channel,
            topic=args.topic,
            pipeline=args.pipeline,
            options={"target_seconds": args.seconds},
        )
        run_id = run.id
        held = run.credits_reserved
        balance_before = billing.balance(session, user.id)

    print(f"provider mode: {settings.provider_mode}")
    print(f"run {run_id} queued — {held} credits held, balance now {balance_before}")
    status = asyncio.run(_advance(run_id, auto_approve=True))

    with session_scope() as session:
        run = session.get(Run, run_id)
        print(f"\nrun {run_id} finished as {status.value}")
        print(f"credits spent: {run.credits_spent} (${billing.credits_to_usd(run.credits_spent)})")
        print(f"balance after: {billing.balance(session, run.user_id)}")
        final = [a for a in run.artifacts if a.kind == "video" and a.meta.get("role") == "final"]
        for artifact in final:
            print(f"final video: {artifact.path} ({artifact.size_bytes / 1_048_576:.2f} MB)")
        published = next((n for n in run.nodes if n.key == "publish"), None)
        if published and published.output:
            print(f"published: {published.output.get('url')}")
    return 0 if status is RunStatus.completed else 2


# --------------------------------------------------------------------------- serve


def cmd_serve(args) -> int:
    import uvicorn

    init_db()
    uvicorn.run("forgecast.api.main:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def cmd_worker(args) -> int:
    from .worker import main as worker_main

    asyncio.run(worker_main())
    return 0


def cmd_initdb(args) -> int:
    init_db()
    print(f"schema created at {get_settings().database_url}")
    return 0


def cmd_map(args) -> int:
    """Render a world-map clip on its own, without a run.

    Worth having as a command rather than only as a pipeline stage: a map is the one
    visual you want to look at and adjust before committing it to an episode, and it
    costs nothing to render, so iterating on it is free.
    """
    from pathlib import Path

    from .motion.geo import PLACES
    from .motion.worldmap import MAP_LIBRARY, available, render_clip, spec_from

    if args.list_styles:
        for style in available():
            print(f"  {style['name']:18} ocean {style['ocean']}  land {style['land']}  "
                  f"marker {style['marker']}")
        return 0
    if args.list_places:
        for name in sorted(PLACES):
            lat, lon = PLACES[name]
            print(f"  {name:22} {lat:7.2f} {lon:8.2f}")
        return 0

    unknown = [p for p in args.places
               if " ".join(p.lower().split()) not in PLACES]
    if unknown:
        print(f"unknown place(s): {', '.join(unknown)}", file=sys.stderr)
        print("run `forgecast map --list-places` to see what is known", file=sys.stderr)
        return 1
    if args.style not in MAP_LIBRARY:
        print(f"unknown style {args.style!r}; try --list-styles", file=sys.stderr)
        return 1

    spec = spec_from(
        args.places, seconds=args.seconds, width=args.width, height=args.height,
        fps=args.fps, style=args.style, labels=not args.no_labels,
    )
    out = Path(args.out)
    render_clip(spec, out)
    print(f"{out}  {args.width}x{args.height}  {args.seconds:.1f}s  style {args.style}")
    for marker in spec.markers:
        print(f"  {marker.label or 'marker':22} lands at {marker.at:5.2f}s")
    return 0


# --------------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forgecast", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("initdb", help="create database tables").set_defaults(func=cmd_initdb)

    boot = sub.add_parser(
        "bootstrap",
        help="prepare an instance for its owner: tables, account, first channel",
    )
    boot.add_argument("--email", required=True)
    boot.add_argument("--password", default="",
                      help="or set FORGECAST_OWNER_PASSWORD; minimum 12 characters")
    boot.add_argument("--grant", type=int, default=10_000)
    boot.add_argument("--channel", default="My Channel",
                      help="name for the first channel; empty to skip")
    boot.add_argument("--niche", default="")
    boot.add_argument("--tone", default="")
    boot.add_argument("--seconds", type=int, default=480)
    boot.add_argument("--reset-password", action="store_true",
                      help="set a new password for an account that already exists")
    boot.set_defaults(func=cmd_bootstrap)

    user = sub.add_parser("user").add_subparsers(dest="action", required=True)
    create = user.add_parser("create")
    create.add_argument("email")
    create.add_argument("--password", required=True)
    create.add_argument("--grant", type=int, default=1000)
    create.set_defaults(func=cmd_user_create)

    channel = sub.add_parser("channel").add_subparsers(dest="action", required=True)
    ch_create = channel.add_parser("create")
    ch_create.add_argument("--user", type=int, required=True)
    ch_create.add_argument("--name", required=True)
    ch_create.add_argument("--niche", default="")
    ch_create.add_argument("--voice", default="")
    ch_create.add_argument("--avatar", default="")
    ch_create.add_argument("--tone", default="")
    ch_create.add_argument("--seconds", type=int, default=480)
    ch_create.set_defaults(func=cmd_channel_create)

    run = sub.add_parser("run").add_subparsers(dest="action", required=True)
    start = run.add_parser("start")
    start.add_argument("--channel", type=int, required=True)
    start.add_argument("--topic", required=True)
    start.add_argument("--pipeline", default="faceless_longform")
    start.add_argument("--seconds", type=int, default=0)
    start.add_argument("--no-publish", action="store_true")
    start.add_argument("--motion-preset", default="",
                       help="a preset learned by `forgecast-vision learn-motion`, "
                            "or a built-in name")
    start.add_argument("--no-motion", action="store_true",
                       help="render without motion graphics")
    start.add_argument("--motion-backend", default="", choices=["", "ffmpeg", "remotion"],
                       help="renderer for motion scenes. remotion needs "
                            "`npm install` in remotion/ and carries its own licence "
                            "terms — see remotion/README.md")
    start.set_defaults(func=cmd_run_start)

    advance = run.add_parser("advance")
    advance.add_argument("run_id", type=int)
    advance.add_argument("--auto-approve", action="store_true")
    advance.set_defaults(func=cmd_run_advance)

    show = run.add_parser("show")
    show.add_argument("run_id", type=int)
    show.set_defaults(func=cmd_run_show)

    approve = run.add_parser("gate")
    approve.add_argument("run_id", type=int)
    approve.add_argument("node")
    approve.add_argument("--note", default="")
    approve.add_argument("--feedback", default="", help="reject and re-run with this note")
    approve.add_argument("--overrides", default="", help="JSON patch applied to node output")
    approve.set_defaults(func=cmd_run_approve)

    demo = sub.add_parser("demo", help="create everything and run one video end to end")
    demo.add_argument("--topic", default="Why deep-sea cables keep breaking")
    demo.add_argument("--niche", default="infrastructure")
    demo.add_argument("--pipeline", default="faceless_longform")
    demo.add_argument("--seconds", type=int, default=120)
    demo.set_defaults(func=cmd_demo)

    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=cmd_serve)

    sub.add_parser("worker").set_defaults(func=cmd_worker)

    world = sub.add_parser("map", help="render an animated world map clip")
    world.add_argument("places", nargs="*",
                       help="1-4 place names, in the order the scene mentions them")
    world.add_argument("--out", default="map.mp4")
    world.add_argument("--style", default="documentary_dark")
    world.add_argument("--seconds", type=float, default=8.0)
    world.add_argument("--width", type=int, default=1280)
    world.add_argument("--height", type=int, default=720)
    world.add_argument("--fps", type=int, default=30)
    world.add_argument("--no-labels", action="store_true")
    world.add_argument("--list-styles", action="store_true")
    world.add_argument("--list-places", action="store_true")
    world.set_defaults(func=cmd_map)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)-7s %(name)s: %(message)s",
    )
    init_db()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
