"""Footage the operator supplies, and the record that they supplied it.

## Why this exists as its own module

`providers.footage.operator_clip` has been able to ingest a file the operator hands over
since footage was added, and nothing has ever called it. It sat beside a licensed search
that the app *could* stand behind, in a module whose docstring explains at length why the
two are different — and the one the app cannot stand behind had no way in at all.

The licensed lane answers "may this app use this without asking". This lane answers a
different question, and answers it by not deciding: the operator supplies the clip, the
app records that they did, the run carries the position in words, and publish is never
blocked. The rights judgment on a clip of someone else's film belongs to the person
publishing the video. A filter written here cannot make it, and pretending otherwise
would be worse than not offering the lane.

## A folder, as well as a tool

Clips land in `storage/runs/{id}/operator/scene_{n}.mp4`, and `shots_node` looks there
before it plans anything for that scene. That path is deliberately guessable: an operator
who has the clip already should be able to drop it in with a file manager and get the
same result as one who asked the agent to fetch it. A lane reachable only through a
conversation is a lane that stops being used the moment the conversation is inconvenient.

Every clip writes a sidecar recording where it came from, what the operator said about
it, and that the licence was not established here. `finalize._write_attribution` reads
the same fields for the credits file, so an operator-directed clip is listed in its own
section rather than mixed in with clips whose licence the app did check.

## What it will not do

There is no fetcher here that reaches an unlicensed index, and there will not be one.
`acquire` handles a local path or a platform URL the operator names, which is the whole
capability: the operator decides what to point it at, the same way they decide what to
put in the folder.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .config import get_settings
from .providers import footage

#: What a scene's operator clip is called. `shots_node` globs for it, and an operator
#: writing the name by hand needs it to be obvious rather than clever.
SCENE_FILE = "scene_{index:03d}.mp4"
SIDECAR = "scene_{index:03d}.json"

_SAFE = re.compile(r"[^A-Za-z0-9 _.,'\-()]+")


def folder(run_id: int) -> Path:
    """Where a run's operator-supplied clips live. Created on first ask."""
    path = get_settings().run_dir(run_id) / "operator"
    path.mkdir(parents=True, exist_ok=True)
    return path


def clip_for(run_id: int, scene_index: int) -> Path | None:
    """The clip the operator supplied for this scene, if there is one."""
    candidate = folder(run_id) / SCENE_FILE.format(index=int(scene_index))
    return candidate if candidate.exists() and candidate.stat().st_size else None


def note_for(run_id: int, scene_index: int) -> dict:
    """What was recorded about that clip. Empty when nothing was."""
    sidecar = folder(run_id) / SIDECAR.format(index=int(scene_index))
    if not sidecar.exists():
        return {}
    try:
        return json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def supplied(run_id: int) -> dict[int, dict]:
    """Every scene the operator has supplied a clip for, with what was recorded."""
    found: dict[int, dict] = {}
    for path in sorted(folder(run_id).glob("scene_*.mp4")):
        try:
            index = int(path.stem.rsplit("_", 1)[-1])
        except ValueError:
            continue
        if path.stat().st_size:
            found[index] = {"path": str(path), **note_for(run_id, index)}
    return found


def take(
    run_id: int,
    scene_index: int,
    source: str | Path,
    *,
    start: float = 0.0,
    seconds: float = 0.0,
    title: str = "",
    creator: str = "",
    note: str = "",
    workdir: Path | None = None,
) -> dict:
    """Ingest a clip the operator chose, for one scene of one run.

    `source` is a local file, or anything `vision.acquire` can resolve — the operator
    names it, and naming it is the decision this lane exists to record.

    Audio comes off at ingest rather than at render, which is `operator_clip`'s own rule
    and the reason it is enforced here rather than later: a clip that arrives muted
    cannot be un-muted by a stage written by somebody who does not know where the file
    came from. The sound design owns this video's audio.
    """
    scene_index = int(scene_index)
    target = folder(run_id) / SCENE_FILE.format(index=scene_index)
    staging = Path(workdir or (folder(run_id) / "_fetch"))
    staging.mkdir(parents=True, exist_ok=True)

    local = Path(source)
    fetched_from = ""
    if not local.exists():
        from .vision.acquire import acquire

        got = acquire(str(source), staging)
        local = got.path
        fetched_from = got.source_url or str(source)
        title = title or got.title
        creator = creator or got.uploader

    clip = footage.operator_clip(
        local, target, start=float(start or 0.0), seconds=float(seconds or 0.0),
        title=_SAFE.sub("", title or local.stem)[:120],
        creator=_SAFE.sub("", creator)[:80],
        note=note,
    )

    record = {
        "scene_index": scene_index,
        "path": str(target),
        "from": fetched_from or str(source),
        "operator_directed": True,
        # Never a licence. The app did not establish one and a credit block is exactly
        # where a claim it never checked would be believed.
        "licence": clip.licence,
        "commercially_safe": clip.commercially_safe,
        "attribution": clip.credit_line(),
        "flag_reason": clip.flag_reason,
        "title": clip.title,
        "creator": clip.creator,
        "start": float(start or 0.0),
        "seconds": float(seconds or 0.0),
    }
    (folder(run_id) / SIDECAR.format(index=scene_index)).write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return record


def drop(run_id: int, scene_index: int) -> bool:
    """Remove a supplied clip and its record. True when there was one."""
    removed = False
    for name in (SCENE_FILE, SIDECAR):
        path = folder(run_id) / name.format(index=int(scene_index))
        if path.exists():
            path.unlink()
            removed = True
    return removed
