"""The preview studio: watch a run before it renders.

The route does one interesting thing, and it is the thing that makes the preview worth
trusting: it resolves the motion preset and the motion plan through exactly the same
functions the render node calls. If it built its own idea of what each scene animates,
the preview would be a drawing of the video rather than the video, and it would drift
the first time either side changed.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..auth import current_user, optional_user
from ..db import get_session
from ..models import Node, Run, User
from ..render import preview as preview_builder
from ..render.ffmpeg import Scene as RenderScene
from ..render.motion_layer import plan as plan_motion
from ..render.motion_layer import resolve_preset
from .media import sign_url
from .routes_api import _owned_run

log = logging.getLogger("forgecast.api.preview")

router = APIRouter(include_in_schema=False)

_ASPECTS = {"9:16": (1080, 1920), "1:1": (1080, 1080)}
_DEFAULT_SIZE = (1280, 720)


def _node(run: Run, key: str) -> Node | None:
    return next((n for n in run.nodes if n.key == key), None)


def _node_output(run: Run, key: str) -> dict | None:
    node = _node(run, key)
    if node is None or not node.output:
        return None
    return dict(node.output)


# The finished film, if the run got that far.
#
# This exists because the page did not have it. Everything below this line builds the
# *plan* preview — scenes composited in the browser so you can judge the edit before
# paying to render it — and that is the right thing to show while a run is still going.
# But a run that has rendered has an actual video on disk, registered as an artifact on
# the render node, and the page went on showing the simulation of it. A completed run
# looked identical to one that had produced nothing: a black frame, and no way to reach
# the file. The render is the point of the product; it has to be the thing you see.
#
# Artifacts are the source rather than a hard-coded path, so a pipeline that renames or
# relocates its output stays playable without this knowing about it.
_FINAL_NODES = ("render", "hook")


def _finished_video(run: Run, user_id: int) -> dict | None:
    by_id = {node.id: node.key for node in run.nodes}
    found: dict[str, dict] = {}
    for artifact in run.artifacts:
        key = by_id.get(artifact.node_id)
        if key not in _FINAL_NODES or artifact.kind != "video":
            continue
        path = Path(artifact.path)
        # A registered artifact whose file has been moved or cleaned up would otherwise
        # render a player pointed at a 404, which reads as a broken video rather than as
        # a missing one.
        if not path.exists():
            continue
        url = sign_url(path, user_id)
        if url is None:
            continue
        found.setdefault(key, {
            "url": url,
            "name": path.name,
            "bytes": path.stat().st_size,
            # The hook is a 15-second opening, not the video. Saying so is the whole
            # difference between "here is your film" and an operator wondering why
            # eight minutes came back as fifteen seconds.
            "partial": key != "render",
        })
    for key in _FINAL_NODES:
        if key in found:
            # A poster, so the player shows the video rather than a grey rectangle
            # before it is played. `preload="metadata"` fetches no frame, so without one
            # the finished film presents as an empty box — which is the exact complaint
            # this whole panel exists to answer. The thumbnail is already generated for
            # every run and is the frame the operator chose to represent it.
            found[key]["poster"] = _first_image(run, by_id, user_id, ("thumbnail", "hook"))
            return found[key]
    return None


def _first_image(run: Run, by_id: dict, user_id: int, nodes: tuple[str, ...]) -> str | None:
    for want in nodes:
        for artifact in run.artifacts:
            if by_id.get(artifact.node_id) != want or artifact.kind != "image":
                continue
            path = Path(artifact.path)
            if path.exists():
                url = sign_url(path, user_id)
                if url:
                    return url
    return None


def _frame_size(run: Run) -> tuple[int, int]:
    """The frame the render node will actually produce.

    Mirrors `nodes._common.dimensions`, and in the same order: the render node's own
    params win over the channel's aspect ratio. Reading only the channel is how a
    Shorts run previews in landscape and renders vertical — the preview would be
    wrong about the one thing a preview is for.
    """
    render = _node(run, "render")
    params = (render.params or {}) if render is not None else {}
    width, height = int(params.get("width") or 0), int(params.get("height") or 0)
    if width and height:
        return width, height
    aspect = run.channel.aspect_ratio if run.channel else "16:9"
    return _ASPECTS.get(aspect, _DEFAULT_SIZE)


def build_timeline(run: Run, user: User):
    """Assemble the preview timeline for a run at whatever stage it has reached."""
    script = _node_output(run, "script")
    if not script:
        return None

    shots = _node_output(run, "shots")
    voice = _node_output(run, "voice")

    channel = run.channel
    width, height = _frame_size(run)

    style = (channel.style_profile or {}) if channel else {}
    options = dict(run.options or {})
    motion_off = False in (options.get("motion"), style.get("motion"))

    preset = None
    plans: list = []
    if not motion_off:
        measured = style.get("render_spec") or {}
        intensity = measured.get("motion_intensity")
        preset = resolve_preset(
            str(options.get("motion_preset") or style.get("motion_preset") or ""),
            intensity=float(intensity) if isinstance(intensity, (int, float)) else None,
            directory=options.get("motion_preset_dir") or "./storage/motion_presets",
        )
        # The plan needs Scene objects, and only three of their fields: how long the
        # scene runs, what it says, and anything the planner asked for explicitly.
        scenes = [
            RenderScene(
                index=int(entry["index"]),
                seconds=float(entry.get("seconds") or 4.0),
                narration=entry.get("narration", ""),
                meta={"on_screen_text": entry.get("on_screen_text", "")},
            )
            for entry in (script.get("scenes") or [])
        ]
        plans = plan_motion(scenes, preset=preset,
                            headline=str(script.get("title") or run.topic or ""))

    def url_for(path: Path) -> str | None:
        return sign_url(path, user.id)

    return preview_builder.build(
        script=script, shots=shots, voice=voice, width=width, height=height,
        preset=preset, motion_plans=plans, url_for=url_for,
    )


@router.get("/api/runs/{run_id}/preview")
def preview_data(
    run_id: int,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> JSONResponse:
    run = _owned_run(session, run_id, user)
    timeline = build_timeline(run, user)
    if timeline is None:
        raise HTTPException(
            status_code=409,
            detail="this run has no script yet — there is nothing to preview",
        )
    return JSONResponse(timeline.as_dict())


@router.get("/runs/{run_id}/preview", response_class=HTMLResponse)
def preview_page(
    run_id: int,
    request: Request,
    embed: int = 0,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    # Imported here rather than at module scope: `routes_web` imports `routes_api`,
    # and importing it at the top of this module closes a cycle through the router
    # registration in `main`.
    from .routes_web import TEMPLATES, _layout, shell

    user = optional_user(request, session)
    if user is None:
        return RedirectResponse(f"/login?next=/runs/{run_id}/preview", 303)  # type: ignore[return-value]

    run = _owned_run(session, run_id, user)
    # Flattened dependency layers, so the plan reads top to bottom in the order the
    # engine will actually run the steps. Relationship order is insertion order, which
    # is usually the same and is not guaranteed to be.
    plan_nodes = [node for layer in _layout(list(run.nodes)) for node in layer]

    return TEMPLATES.TemplateResponse(
        request,
        "preview.html",
        {
            **shell(session, user, "studio"),
            "run": run,
            "plan_nodes": plan_nodes,
            "finished": _finished_video(run, user.id),
            # Chrome off: this page is also the Studio panel inside the chat, and a
            # sidebar nested inside a sidebar is how an embed announces itself as one.
            "embed": bool(embed),
        },
    )
