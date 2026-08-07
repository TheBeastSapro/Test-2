"""Getting a local file to analyse.

Acquisition is deliberately separate from analysis — the same reasoning as provider
routing in the render pipeline. What fetches bytes is the part that breaks: platforms
change their delivery, block datacentre IPs, and rotate signatures. What measures
pixels does not. Keeping them apart means a platform breaking costs one adapter.

**Verified state:** `LocalSource` and `DirectUrlSource` are tested. `YtDlpSource` is
written against yt-dlp's documented interface but could not be verified end to end
here: YouTube returns HTTP 403 for media to this container's IP across every player
client, which is the well-known datacentre-IP block, not a bug in this code. Run it
from a host with working egress before trusting it.
"""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlparse


def _yt_dlp() -> list[str] | None:
    """The argv prefix that runs yt-dlp, resolved per call. See `forgecast.ytdlp`.

    A function rather than the module constant this used to be. The constant was
    computed at import, so a machine that gained yt-dlp after the app started went on
    being told it had none until the app was restarted — and it was wrong even at
    import, because it searched `PATH` for a package that lives in the app's own
    virtualenv and is not on it under Windows.
    """
    from ..ytdlp import command
    return command()


class AcquireError(RuntimeError):
    pass


@dataclass
class Acquired:
    path: Path
    source_url: str
    title: str = ""
    uploader: str = ""
    duration: float | None = None
    method: str = ""
    trimmed_to: str | None = None

    def as_dict(self) -> dict:
        return {
            "source_url": self.source_url,
            "title": self.title,
            "uploader": self.uploader,
            "method": self.method,
            "trimmed_to": self.trimmed_to,
        }


class Source(ABC):
    name = "source"

    @abstractmethod
    def matches(self, reference: str) -> bool: ...

    @abstractmethod
    def fetch(self, reference: str, workdir: Path, *, max_seconds: float | None = None
              ) -> Acquired: ...


class LocalSource(Source):
    name = "local"

    def matches(self, reference: str) -> bool:
        return not reference.startswith(("http://", "https://")) and Path(reference).exists()

    def fetch(self, reference: str, workdir: Path, *, max_seconds: float | None = None
              ) -> Acquired:
        path = Path(reference).resolve()
        if not path.exists():
            raise AcquireError(f"no such file: {path}")
        if max_seconds:
            path = trim(path, workdir / f"trimmed_{path.stem}.mp4", max_seconds)
            return Acquired(path, reference, method=self.name,
                            trimmed_to=f"0-{max_seconds:g}s")
        return Acquired(path, reference, method=self.name)


class DirectUrlSource(Source):
    """A URL that already points at a media file."""

    name = "direct_url"
    MEDIA_SUFFIXES: ClassVar[frozenset[str]] = frozenset(
        {".mp4", ".mov", ".webm", ".mkv", ".m4v", ".avi"}
    )

    def matches(self, reference: str) -> bool:
        if not reference.startswith(("http://", "https://")):
            return False
        return Path(urlparse(reference).path).suffix.lower() in self.MEDIA_SUFFIXES

    def fetch(self, reference: str, workdir: Path, *, max_seconds: float | None = None
              ) -> Acquired:
        workdir.mkdir(parents=True, exist_ok=True)
        suffix = Path(urlparse(reference).path).suffix or ".mp4"
        target = workdir / f"download{suffix}"
        proc = subprocess.run(
            ["curl", "-fsSL", "--max-time", "900", "-o", str(target), reference],
            capture_output=True,
        )
        if proc.returncode != 0 or not target.exists():
            raise AcquireError(
                f"download failed ({proc.returncode}): "
                f"{proc.stderr.decode(errors='replace')[:300]}"
            )
        if max_seconds:
            target = trim(target, workdir / "trimmed.mp4", max_seconds)
            return Acquired(target, reference, method=self.name,
                            trimmed_to=f"0-{max_seconds:g}s")
        return Acquired(target, reference, method=self.name)


class YtDlpSource(Source):
    """Platform URLs via yt-dlp (YouTube, Instagram, TikTok, and many others)."""

    name = "yt_dlp"

    def matches(self, reference: str) -> bool:
        return reference.startswith(("http://", "https://"))

    def fetch(self, reference: str, workdir: Path, *, max_seconds: float | None = None
              ) -> Acquired:
        binary = _yt_dlp()
        if not binary:
            from ..ytdlp import why_missing
            raise AcquireError(why_missing())
        workdir.mkdir(parents=True, exist_ok=True)

        # 480p is plenty: every measurement here runs on 160px-wide frames anyway,
        # and a smaller file is a faster, more reliable download.
        from ..ytdlp import cookie_args
        cmd = [
            *binary, "--no-warnings", "--no-playlist",
            # The native downloader avoids handing the media fetch to ffmpeg, which
            # does not honour HTTPS_PROXY and fails with exit 8 behind one.
            "--downloader", "native",
            # Whatever cookies this install has, or nothing at all. Spliced in
            # unconditionally so this call site does not branch on the setting.
            *cookie_args(),
            "-f", "bv*[height<=480]+ba/b[height<=480]/bv*+ba/b",
            "--merge-output-format", "mp4",
            "-o", str(workdir / "source.%(ext)s"),
            "--print-to-file", "%(title)s\t%(uploader)s\t%(duration)s",
            str(workdir / "meta.tsv"),
            reference,
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=1800)
        if proc.returncode != 0:
            stderr = proc.stderr.decode(errors="replace")
            hint = ""
            if "403" in stderr or "not a bot" in stderr:
                # Say what cookies this install actually has. The hint used to advise
                # supplying them without saying how, and with no way to — so an
                # operator who had already set them could not tell whether they were
                # being used, and one who had not was given homework with no form to
                # fill in.
                from ..ytdlp import COOKIES_FILE, COOKIES_FROM_BROWSER, describe_cookies
                hint = (
                    " — the platform refused the media fetch. This is usually the IP "
                    "range rather than a bad URL: datacentre and VPS addresses get "
                    f"blocked where a home connection does not. Currently {describe_cookies()}. "
                    f"Set {COOKIES_FROM_BROWSER} to a browser you are signed into "
                    "(chrome, firefox, edge, brave), or "
                    f"{COOKIES_FILE} to an exported cookies.txt, and try again. "
                    "Running the app on your own machine usually needs neither."
                )
            raise AcquireError(f"yt-dlp failed: {stderr[-400:]}{hint}")

        candidates = sorted(workdir.glob("source.*"), key=lambda p: p.stat().st_size)
        media = [p for p in candidates if p.suffix.lower() != ".tsv"]
        if not media:
            raise AcquireError("yt-dlp reported success but produced no file")
        path = media[-1]

        title = uploader = ""
        duration: float | None = None
        meta_file = workdir / "meta.tsv"
        if meta_file.exists():
            parts = meta_file.read_text(encoding="utf-8", errors="replace").strip().split("\t")
            if len(parts) >= 2:
                title, uploader = parts[0], parts[1]
            if len(parts) >= 3:
                try:
                    duration = float(parts[2])
                except ValueError:
                    duration = None

        trimmed = None
        if max_seconds:
            path = trim(path, workdir / "trimmed.mp4", max_seconds)
            trimmed = f"0-{max_seconds:g}s"

        return Acquired(
            path=path, source_url=reference, title=title, uploader=uploader,
            duration=duration, method=self.name, trimmed_to=trimmed,
        )


SOURCES: list[Source] = [LocalSource(), DirectUrlSource(), YtDlpSource()]


def trim(source: Path, target: Path, seconds: float) -> Path:
    """Re-encode the first `seconds`.

    Re-encoding rather than stream-copying because a copy starts at the nearest
    keyframe, which shifts every timestamp downstream — and shot times that are
    silently offset by two seconds corrupt the whole analysis.
    """
    from .probe import FFMPEG, ProbeError, run

    target.parent.mkdir(parents=True, exist_ok=True)
    proc = run(
        [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source), "-t", f"{seconds:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", str(target),
        ],
        label="trim",
        timeout=1800,
    )
    if proc.returncode != 0 or not target.exists():
        raise ProbeError(f"trim failed: {proc.stderr.decode(errors='replace')[-300:]}")
    return target


def acquire(reference: str, workdir: Path, *, max_seconds: float | None = None) -> Acquired:
    """Resolve a local path, direct media URL, or platform URL to a local file."""
    for source in SOURCES:
        if source.matches(reference):
            return source.fetch(reference, workdir, max_seconds=max_seconds)
    raise AcquireError(
        f"nothing can handle {reference!r} — expected a local file path or an http(s) URL"
    )
