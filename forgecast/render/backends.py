"""Render backends: which engine draws a motion scene.

Two exist, and the choice is deliberately reversible.

**ffmpeg** is the default and needs nothing that is not already installed. It compiles
a scene to one filtergraph. Everything it can do, it does fast and in-process.

**Remotion** renders the same scene in a headless browser. It is a large step up in
what is *possible* — real text layout with word wrapping and font metrics, blurred
shadows, masks, gradients, nesting, SVG — because a browser has a layout engine and
ffmpeg has `drawtext`. It costs a Node toolchain and a Chromium download, and it is
slower per frame.

## The licence, which is not a footnote

Remotion is **not** unconditionally free software. It is free for individuals, for
non-profits, and for for-profit companies with **up to three employees** — commercial
use included. Past three employees a paid per-seat company licence is required, and
the obligation starts when you decide to use it, not when you ship.

That is why this is an interface and not a rewrite. Today the ffmpeg backend is the
default, the Remotion one is opt-in, and the scene plan is engine-neutral. If the
licence ever stops suiting the business, swapping in Revideo (MIT) or falling back to
ffmpeg is a new implementation of this class, not a rebuild of the product.

See https://www.remotion.dev/docs/license/faq before shipping this commercially.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

from ..motion.presets import MotionPreset
from .motion_layer import MotionPlan
from .scene_plan import plan_from

log = logging.getLogger("forgecast.render.backends")

REMOTION_ROOT = Path(__file__).resolve().parent.parent.parent / "remotion"
REMOTION_ENTRY = REMOTION_ROOT / "src" / "index.ts"
COMPOSITION_ID = "MotionScene"
DEFAULT_TIMEOUT = 900.0


class RenderBackend(ABC):
    name = "backend"

    @abstractmethod
    def available(self) -> bool:
        """Whether this backend can run here, checked before it is chosen."""

    @abstractmethod
    def render(self, clip_path: Path, out_path: Path, item: MotionPlan, *,
               preset: MotionPreset, seconds: float, width: int, height: int,
               fps: int = 30, timeout: float = DEFAULT_TIMEOUT) -> Path:
        """Composite the plan's elements over `clip_path`. Returns the output."""


class FfmpegBackend(RenderBackend):
    """The default. One filtergraph, no external toolchain."""

    name = "ffmpeg"

    def available(self) -> bool:
        return bool(shutil.which("ffmpeg"))

    def render(self, clip_path: Path, out_path: Path, item: MotionPlan, *,
               preset: MotionPreset, seconds: float, width: int, height: int,
               fps: int = 30, timeout: float = DEFAULT_TIMEOUT) -> Path:
        from .motion_layer import apply as apply_motion

        return apply_motion(
            clip_path, out_path, item, preset=preset, seconds=seconds,
            width=width, height=height, fps=fps, timeout=timeout,
        )


class RemotionBackend(RenderBackend):
    """Headless-browser rendering through the Remotion project in `remotion/`."""

    name = "remotion"

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or REMOTION_ROOT

    def available(self) -> bool:
        # node_modules, not just node: an un-installed project fails several seconds
        # into a render with a module-resolution error rather than up front.
        return bool(
            shutil.which("npx")
            and (self.root / "node_modules" / "remotion").exists()
            and (self.root / "src" / "index.ts").exists()
        )

    def render(self, clip_path: Path, out_path: Path, item: MotionPlan, *,
               preset: MotionPreset, seconds: float, width: int, height: int,
               fps: int = 30, timeout: float = DEFAULT_TIMEOUT) -> Path:
        if not item.active or not item.lines:
            return clip_path

        # Remotion resolves assets through `staticFile()`, relative to a public
        # directory — it cannot read an absolute path from the page, because the
        # bundle is served over http and Chrome blocks file:// from an http origin.
        # Pointing --public-dir at the clip's own directory avoids copying anything.
        public_dir = clip_path.parent
        plan = plan_from(
            preset, item.kind, item.lines, seconds=seconds, width=width,
            height=height, fps=fps, background=clip_path,
        )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        args = [
            "npx", "remotion", "render", str(REMOTION_ENTRY), COMPOSITION_ID,
            str(out_path),
            "--props", plan.to_props(),
            "--public-dir", str(public_dir),
            "--log", "error",
            # Required for headless Chrome as a non-root user in a container, and
            # harmless outside one.
            "--gl", "swiftshader",
        ]

        environment = dict(os.environ)
        # Reuse a Chromium that is already on the machine rather than downloading a
        # second one into the image.
        browser = _existing_chromium()
        if browser:
            environment.setdefault("REMOTION_BROWSER_EXECUTABLE", str(browser))

        proc = subprocess.run(
            args, cwd=self.root, env=environment, capture_output=True, timeout=timeout,
        )
        if proc.returncode != 0 or not out_path.exists():
            detail = (proc.stderr or b"").decode(errors="replace")[-800:]
            raise RenderBackendError(
                f"remotion render failed (exit {proc.returncode}): {detail}"
            )
        return out_path


class RenderBackendError(RuntimeError):
    pass


def _existing_chromium() -> Path | None:
    """A Chromium already installed here, if there is one."""
    explicit = os.environ.get("REMOTION_BROWSER_EXECUTABLE")
    if explicit and Path(explicit).exists():
        return Path(explicit)

    for name in ("chromium", "chromium-browser", "google-chrome"):
        found = shutil.which(name)
        if found:
            return Path(found)

    # Playwright's download location, which many images already have.
    root = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers"))
    if root.exists():
        for candidate in sorted(root.glob("chromium-*/chrome-linux/chrome")):
            return candidate
    return None


BACKENDS: dict[str, type[RenderBackend]] = {
    "ffmpeg": FfmpegBackend,
    "remotion": RemotionBackend,
}


def backend_for(name: str = "") -> RenderBackend:
    """Resolve a backend by name, falling back to ffmpeg rather than failing.

    A run that has already paid for a script and a voiceover should not die because
    an optional renderer is missing. An unavailable choice is a warning and a
    downgrade — the video still gets made, with the motion the default engine can do.
    """
    chosen = (name or "ffmpeg").strip().lower()
    cls = BACKENDS.get(chosen)
    if cls is None:
        log.warning("unknown render backend %r; using ffmpeg", name)
        return FfmpegBackend()

    backend = cls()
    if not backend.available():
        if chosen != "ffmpeg":
            log.warning(
                "render backend %r is not available here (is `npm install` run in "
                "remotion/?); using ffmpeg", chosen,
            )
        return FfmpegBackend()
    return backend
