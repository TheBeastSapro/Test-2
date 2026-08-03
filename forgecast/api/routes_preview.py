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
            # Chrome off: this page is also the Studio panel inside the chat, and a
            # sidebar nested inside a sidebar is how an embed announces itself as one.
            "embed": bool(embed),
        },
    )
