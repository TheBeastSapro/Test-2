"""Bridge to a local Chatterbox voice pipeline — and an honest answer when it is absent.

The pipeline this talks to is somebody's own GPU box: `torch`, `chatterbox-tts` for
zero-shot cloning from a short reference recording, `faster-whisper` for checking the
result afterwards. None of that is installed here, and none of it is installable
everywhere this app runs — a laptop, a container, a small VPS.

So this module is written for two machines at once.

On the machine that has the pipeline it is a thin adapter: diagnose, then synthesise.
Everything vendor-specific lives in exactly one function,
`_synthesise_chatterbox_unverified`, which has never been executed against a real
install and says so in its own comment. One place to correct is the point.

On every other machine — the common case, and the one that decides whether this app
feels honest — it is a diagnosis. `available()` says *which* of several distinct
problems is in the way, because each needs a different action from the operator:
install torch, install a CUDA build of torch, install chatterbox-tts, or record a
reference clip. A single "local voice unavailable" would be true and useless.

Two rules hold this together.

**Nothing heavy is imported at module scope.** Importing this file must cost nothing
and print nothing on a machine with no torch. `torch` is a multi-second import, and a
loud one when its CUDA runtime disagrees with the driver — a page render that pays
that just to display a greyed-out button is a bug. Every such import sits inside a
function, inside `try/except ImportError`. (Importing `forgecast.voice` at all pulls
numpy in through the package `__init__` for the casting analysers. That cost is not
this module's to remove; torch is the one this module guards, and it stays unimported
until something actually asks whether the pipeline is there.)

**The reference clip is checked with ffprobe, not with the pipeline.** Length, channel
count, sample rate and peak level are all measurable without a single vendor import,
which means the operator can be told their recording is four seconds long and clipped
*on the machine they recorded it on*, before any of the GPU half exists. This is the
part of the module that genuinely runs everywhere, so it is the part that carries
real tests.

Nothing here touches the database or the network.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import json
import logging
import math
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("forgecast.voice.local")

FFPROBE = shutil.which("ffprobe") or "ffprobe"
PROBE_TIMEOUT_SECONDS = 120.0

# The import package for the `chatterbox-tts` distribution. Part of the same unverified
# vendor surface as `_synthesise_chatterbox_unverified` — if a real install disagrees,
# this constant and that function are the whole correction.
CHATTERBOX_MODULE = "chatterbox"
# Optional: used to verify a finished take against its script, never to produce one.
# Its absence must never block a render.
WHISPER_MODULE = "faster_whisper"

# Reference-clip constraints. A zero-shot clone copies whatever it is given, including
# the flaws: too short and there is not enough voice to copy, too long and the prompt
# is mostly wasted while encoding gets slower, clipped and the clone inherits the
# distortion as part of the "voice".
MIN_REFERENCE_SECONDS = 8.0
MAX_REFERENCE_SECONDS = 12.0
# Peak at or above this reads as "already touching the ceiling" — true clipping cannot
# be distinguished from a deliberately maximised master, and both are bad prompts.
CLIPPING_PEAK_DBFS = -0.5
# Quiet enough that the recording is mostly room noise relative to voice. An advisory,
# not a refusal: a quiet clean recording still clones acceptably.
QUIET_PEAK_DBFS = -24.0
# Below this there is not enough bandwidth left in the recording to characterise a
# voice — telephone-band audio produces a telephone-sounding clone.
MIN_SAMPLE_RATE = 16000
PREFERRED_SAMPLE_RATE = 24000

# Diagnosis codes. They exist so a caller can branch (a setup page wants to link the
# right installer) without matching on prose that is written for humans.
CODE_OK = "ok"
CODE_TORCH_MISSING = "torch_missing"
CODE_TORCH_BROKEN = "torch_broken"
CODE_CUDA_MISSING = "cuda_missing"
CODE_CHATTERBOX_MISSING = "chatterbox_missing"
CODE_REFERENCE_UNSET = "reference_unset"
CODE_REFERENCE_MISSING = "reference_missing"
CODE_REFERENCE_UNUSABLE = "reference_unusable"
CODE_REFERENCE_UNREADABLE = "reference_unreadable"

TORCH_INSTALL_HINT = (
    "install the torch build matching your GPU driver, using the command the selector "
    "at https://pytorch.org/get-started/locally/ gives you"
)


class LocalVoiceError(RuntimeError):
    """Base for every failure this module raises."""


class LocalVoiceUnavailable(LocalVoiceError):
    """The pipeline cannot run. Carries the machine-readable code alongside the prose."""

    def __init__(self, reason: str, code: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.code = code


class ReferenceClipError(LocalVoiceError):
    """The reference recording could not be read or measured at all."""


# ------------------------------------------------------------------ reference clip


@dataclass
class ReferenceClip:
    """What ffprobe can say about a reference recording, and what is wrong with it."""

    path: Path
    seconds: float
    channels: int
    sample_rate: int
    codec: str
    peak_dbfs: float | None = None
    rms_dbfs: float | None = None
    # Reasons to refuse the clip outright.
    problems: list[str] = field(default_factory=list)
    # Reasons to warn and carry on.
    advisories: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def as_dict(self) -> dict:
        return {
            "path": str(self.path),
            "seconds": round(self.seconds, 2),
            "channels": self.channels,
            "sample_rate": self.sample_rate,
            "codec": self.codec,
            "peak_dbfs": None if self.peak_dbfs is None else round(self.peak_dbfs, 2),
            "rms_dbfs": None if self.rms_dbfs is None else round(self.rms_dbfs, 2),
            "ok": self.ok,
            "problems": list(self.problems),
            "advisories": list(self.advisories),
        }


def _ffprobe(args: list[str], *, label: str) -> str:
    try:
        proc = subprocess.run(
            [FFPROBE, "-v", "error", *args],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        # Distinct from "the clip is bad": the operator's recording may be perfect and
        # the checker is what is missing. Saying "invalid clip" here sends them to
        # re-record for nothing.
        raise ReferenceClipError(
            "ffprobe is not installed, so a reference clip cannot be measured. Install "
            "ffmpeg, which ships it: `brew install ffmpeg` on macOS, `sudo apt install "
            "ffmpeg` on Linux, or let the desktop launcher fetch it."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ReferenceClipError(
            f"ffprobe timed out after {PROBE_TIMEOUT_SECONDS:.0f}s on {label}"
        ) from exc
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        raise ReferenceClipError(
            f"ffprobe could not read {label} as audio: "
            + (detail[-1] if detail else f"exit {proc.returncode}")
        )
    return proc.stdout


def _lavfi_source(path: Path) -> str:
    """Quote a path for use as the `amovie` argument of a filtergraph.

    ffprobe takes a normal path as `argv`, but the level meter runs through a
    filtergraph, and there the path passes two parsers: the graph splits on `,;[]` and
    the filter then splits its own arguments on `:` and `=`. The escaping below is not
    a guess — it is the one combination verified against filenames containing each of
    those characters, and `test_voice_local.py` pins it.

    The failure it prevents is mundane and certain: a reference recording called
    "dad's voice.wav" reporting itself as unreadable.
    """
    quoted = str(path).replace("\\", "\\\\")
    # A literal quote has to close the quoted run, escape itself, and reopen it.
    quoted = quoted.replace("'", "'\\\\\\''")
    quoted = quoted.replace(":", "\\:").replace("=", "\\=")
    return f"'{quoted}'"


def _levels(path: Path) -> tuple[float | None, float | None]:
    """Peak and RMS in dBFS, from ffprobe's own astats metadata."""
    raw = _ffprobe(
        [
            "-f", "lavfi",
            "-i", f"amovie={_lavfi_source(path)},astats=metadata=1:reset=0",
            "-show_entries",
            "frame_tags=lavfi.astats.Overall.Peak_level,lavfi.astats.Overall.RMS_level",
            "-of", "json",
        ],
        label=str(path),
    )
    try:
        frames = json.loads(raw or "{}").get("frames") or []
    except json.JSONDecodeError as exc:
        raise ReferenceClipError(f"could not parse level measurement for {path}") from exc

    def strongest(key: str) -> float | None:
        # astats with reset=0 accumulates, so the last frame usually holds the answer —
        # but a truncated read would then silently report a level from the middle of the
        # clip. Taking the maximum makes a short read wrong in the safe direction.
        best: float | None = None
        for frame in frames:
            value = (frame.get("tags") or {}).get(f"lavfi.astats.Overall.{key}")
            if value is None:
                continue
            try:
                number = float(value)
            except ValueError:
                continue
            if math.isnan(number):
                continue
            best = number if best is None else max(best, number)
        return best

    return strongest("Peak_level"), strongest("RMS_level")


def _duration(path: Path) -> float | None:
    """Length in seconds, or None when the file cannot be read as media."""
    try:
        payload = json.loads(
            _ffprobe(
                ["-show_entries", "format=duration", "-of", "json", str(path)],
                label=str(path),
            )
            or "{}"
        )
    except (ReferenceClipError, json.JSONDecodeError):
        return None
    return _first_float((payload.get("format") or {}).get("duration"))


def inspect_reference(path: str | Path) -> ReferenceClip:
    """Measure a reference recording and judge it against the cloning constraints.

    Raises `ReferenceClipError` when there is nothing to judge — no file, not audio,
    no ffprobe. Returns a clip carrying `problems` when it is measurable but wrong,
    because "10.0s, stereo, peak -0.1 dBFS, clipped" is actionable and "invalid" is not.
    """
    path = Path(path)
    if not path.exists():
        raise ReferenceClipError(f"no reference clip at {path}")

    payload = json.loads(
        _ffprobe(
            ["-show_format", "-show_streams", "-of", "json", str(path)],
            label=str(path),
        )
        or "{}"
    )
    streams = payload.get("streams") or []
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if audio is None:
        raise ReferenceClipError(
            f"{path} has no audio stream — a reference clip has to be a recording of "
            "the voice, not a silent video or an image"
        )

    seconds = _first_float(
        (payload.get("format") or {}).get("duration"), audio.get("duration")
    )
    if seconds is None:
        raise ReferenceClipError(
            f"could not determine the length of {path}; re-export it as WAV and try again"
        )

    clip = ReferenceClip(
        path=path,
        seconds=seconds,
        channels=int(audio.get("channels") or 0),
        sample_rate=int(audio.get("sample_rate") or 0),
        codec=str(audio.get("codec_name") or ""),
    )
    clip.peak_dbfs, clip.rms_dbfs = _levels(path)
    _judge(clip)
    return clip


def _judge(clip: ReferenceClip) -> None:
    if clip.seconds < MIN_REFERENCE_SECONDS:
        clip.problems.append(
            f"{clip.seconds:.1f}s is too short — record {MIN_REFERENCE_SECONDS:.0f} to "
            f"{MAX_REFERENCE_SECONDS:.0f} seconds of continuous speech"
        )
    elif clip.seconds > MAX_REFERENCE_SECONDS:
        clip.problems.append(
            f"{clip.seconds:.1f}s is longer than needed — trim to "
            f"{MIN_REFERENCE_SECONDS:.0f}-{MAX_REFERENCE_SECONDS:.0f} seconds of the "
            "cleanest speech"
        )

    if clip.sample_rate and clip.sample_rate < MIN_SAMPLE_RATE:
        clip.problems.append(
            f"{clip.sample_rate} Hz is below {MIN_SAMPLE_RATE} Hz — re-record at "
            f"{PREFERRED_SAMPLE_RATE} Hz or higher"
        )
    elif clip.sample_rate and clip.sample_rate < PREFERRED_SAMPLE_RATE:
        clip.advisories.append(
            f"{clip.sample_rate} Hz works, but {PREFERRED_SAMPLE_RATE} Hz or higher "
            "gives the clone more to copy"
        )

    if clip.peak_dbfs is None:
        clip.advisories.append("level could not be measured, so clipping is unchecked")
    elif clip.peak_dbfs == -math.inf:
        clip.problems.append("the clip is silent — there is no voice in it to copy")
    elif clip.peak_dbfs >= CLIPPING_PEAK_DBFS:
        clip.problems.append(
            f"peaks at {clip.peak_dbfs:.1f} dBFS, which is clipping or close enough to "
            "be indistinguishable — re-record with the input gain lower, aiming for "
            "peaks around -6 dBFS"
        )
    elif clip.peak_dbfs < QUIET_PEAK_DBFS:
        clip.advisories.append(
            f"peaks at only {clip.peak_dbfs:.1f} dBFS; a louder take carries less room "
            "noise into the clone"
        )

    if clip.channels > 1:
        # Not a refusal: the pipeline downmixes. But a stereo prompt is where a room
        # recorded in two channels smuggles phase differences into the clone.
        clip.advisories.append(
            f"{clip.channels} channels — mono is preferred for a voice prompt"
        )
    elif clip.channels == 0:
        clip.advisories.append("channel count unknown")


def _first_float(*values) -> float | None:
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return None


# ---------------------------------------------------------------------- the runtime


@dataclass
class Runtime:
    """What of the local pipeline is actually importable on this machine."""

    torch: str | None = None
    # Set when torch is installed but importing it failed for a reason that is not
    # absence — a CUDA runtime that does not match the driver raises OSError here.
    torch_error: str = ""
    cuda: bool = False
    device_name: str = ""
    chatterbox: str | None = None
    whisper: str | None = None

    def as_dict(self) -> dict:
        return {
            "torch": self.torch,
            "torch_error": self.torch_error,
            "cuda": self.cuda,
            "device_name": self.device_name,
            "chatterbox": self.chatterbox,
            "whisper": self.whisper,
        }


def _installed(name: str) -> bool:
    """Whether a module could be imported, without importing it.

    `find_spec` locates a package without executing it, which is the whole point: the
    answer to "is torch here" must not cost a torch import on a machine that is only
    rendering a status page.
    """
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _package_version(module_name: str, distribution: str) -> str | None:
    """The installed version of a package, still without importing it.

    Importing chatterbox-tts pulls torch in behind it, which is the several-second cost
    this module exists to avoid on a machine that only wants to draw a status line. The
    version comes from the installed metadata instead.
    """
    if not _installed(module_name):
        return None
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        # Importable but not installed as a distribution — a source checkout on the
        # path. Present is the useful answer; the version is decoration.
        return "installed"


def _probe_runtime() -> Runtime:
    """Ask the machine what it has. The only place that imports torch."""
    runtime = Runtime()

    # Probed before torch, and independently of it. An environment with chatterbox-tts
    # and no torch is a real half-finished install, and reporting "chatterbox-tts
    # missing" there sends the operator to install what they already have.
    runtime.chatterbox = _package_version(CHATTERBOX_MODULE, "chatterbox-tts")
    runtime.whisper = _package_version(WHISPER_MODULE, "faster-whisper")

    if not _installed("torch"):
        return runtime

    try:
        torch = importlib.import_module("torch")
    except ImportError as exc:
        # find_spec found it, so this is a broken install rather than an absent one:
        # a dependency of torch itself is missing.
        runtime.torch_error = str(exc)
        return runtime
    except Exception as exc:
        # The common real failure, and it is not an ImportError: torch raises OSError
        # when it cannot load its own CUDA libraries. Left uncaught it would take down
        # whatever asked for a status line.
        runtime.torch_error = f"{type(exc).__name__}: {exc}"
        return runtime

    runtime.torch = str(getattr(torch, "__version__", "") or "installed")
    try:
        runtime.cuda = bool(torch.cuda.is_available())
        if runtime.cuda:
            runtime.device_name = str(torch.cuda.get_device_name(0))
    except Exception as exc:                                      # pragma: no cover
        # A driver query can fail on its own; that is a machine without usable CUDA,
        # not a crash worth propagating to a status page.
        log.debug("cuda probe failed: %s", exc)
        runtime.cuda = False

    return runtime


# ----------------------------------------------------------------------- the adapter


@dataclass
class Verdict:
    ok: bool
    code: str
    reason: str

    def as_dict(self) -> dict:
        return {"ok": self.ok, "code": self.code, "reason": self.reason}


@dataclass
class RenderedVoice:
    path: Path
    seconds: float | None
    device: str
    reference_path: Path
    advisories: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "path": str(self.path),
            "seconds": None if self.seconds is None else round(self.seconds, 2),
            "device": self.device,
            "reference_path": str(self.reference_path),
            "advisories": list(self.advisories),
        }


class LocalVoice:
    """Narration from a Chatterbox install on this machine, or a reason why not.

    `require_cuda` defaults to True because Chatterbox on CPU is slower than realtime
    by a wide margin — a 90-second narration is a coffee break, and silently taking it
    reads as a hang. A caller that genuinely wants the CPU path asks for it.
    """

    def __init__(
        self,
        reference_path: str | Path | None = None,
        *,
        require_cuda: bool = True,
        exaggeration: float = 0.5,
        cfg_weight: float = 0.5,
        synthesise=None,
    ) -> None:
        self.reference_path = Path(reference_path) if reference_path else None
        self.require_cuda = require_cuda
        self.exaggeration = exaggeration
        self.cfg_weight = cfg_weight
        # Injectable so the adapter's own behaviour — refusals, ordering, the written
        # file, the measurement afterwards — is testable on a machine with no GPU.
        self._synthesise = synthesise or _synthesise_chatterbox_unverified

    # ------------------------------------------------------------------ diagnosis

    def check(self, reference_path: str | Path | None = None) -> Verdict:
        """The full diagnosis: one blocker at a time, in the order they must be fixed."""
        runtime = _probe_runtime()
        reference = Path(reference_path) if reference_path else self.reference_path

        # Order is deliberate: the runtime first, the input second. Telling someone to
        # re-record a reference clip for a pipeline they cannot run wastes their
        # afternoon on the wrong problem.
        if runtime.torch_error:
            return Verdict(
                False,
                CODE_TORCH_BROKEN,
                f"torch is installed but failed to import ({runtime.torch_error}). This "
                "is usually a CUDA runtime that does not match the driver — reinstall "
                f"torch for this machine: {TORCH_INSTALL_HINT}.",
            )
        if runtime.torch is None:
            return Verdict(
                False,
                CODE_TORCH_MISSING,
                f"torch is not installed, so nothing can be synthesised locally — "
                f"{TORCH_INSTALL_HINT}.",
            )
        if self.require_cuda and not runtime.cuda:
            return Verdict(
                False,
                CODE_CUDA_MISSING,
                f"torch {runtime.torch} is installed but reports no CUDA device, and "
                "Chatterbox on CPU runs far slower than realtime. Either install a CUDA "
                f"build of torch ({TORCH_INSTALL_HINT}) or construct LocalVoice with "
                "require_cuda=False to accept CPU synthesis.",
            )
        if runtime.chatterbox is None:
            return Verdict(
                False,
                CODE_CHATTERBOX_MISSING,
                "torch is ready but chatterbox-tts is not installed — "
                "`pip install chatterbox-tts` into the same environment as torch.",
            )

        if reference is None:
            return Verdict(
                False,
                CODE_REFERENCE_UNSET,
                "no reference clip has been set. Record "
                f"{MIN_REFERENCE_SECONDS:.0f}-{MAX_REFERENCE_SECONDS:.0f} seconds of the "
                "voice and pass its path as reference_path.",
            )
        try:
            clip = inspect_reference(reference)
        except ReferenceClipError as exc:
            code = (
                CODE_REFERENCE_MISSING
                if not Path(reference).exists()
                else CODE_REFERENCE_UNREADABLE
            )
            return Verdict(False, code, str(exc))
        if not clip.ok:
            return Verdict(
                False,
                CODE_REFERENCE_UNUSABLE,
                f"the reference clip {clip.path.name} cannot be used: "
                + "; ".join(clip.problems),
            )

        where = runtime.device_name or ("cuda" if runtime.cuda else "cpu")
        return Verdict(
            True, CODE_OK, f"ready on {where} with {clip.path.name} ({clip.seconds:.1f}s)"
        )

    def available(self, reference_path: str | Path | None = None) -> tuple[bool, str]:
        verdict = self.check(reference_path)
        return verdict.ok, verdict.reason

    def device(self, runtime: Runtime | None = None) -> str:
        runtime = runtime or _probe_runtime()
        return "cuda" if runtime.cuda else "cpu"

    def describe(self, reference_path: str | Path | None = None) -> dict:
        """What is installed, what is missing, and what to do about it.

        Written to be rendered straight into a status panel: every entry in `missing`
        carries its own fix, because a list of absent package names is a quiz.
        """
        runtime = _probe_runtime()
        reference = Path(reference_path) if reference_path else self.reference_path
        verdict = self.check(reference)

        installed: list[str] = []
        missing: list[str] = []

        if runtime.torch:
            installed.append(f"torch {runtime.torch}")
        elif runtime.torch_error:
            missing.append(f"torch is installed but broken ({runtime.torch_error})")
        else:
            missing.append(f"torch — {TORCH_INSTALL_HINT}")

        if runtime.cuda:
            installed.append(f"CUDA device: {runtime.device_name or 'present'}")
        elif runtime.torch:
            missing.append(
                "a CUDA device torch can see — CPU synthesis works but is far slower "
                "than realtime"
            )

        if runtime.chatterbox:
            installed.append(f"chatterbox-tts {runtime.chatterbox}")
        else:
            missing.append("chatterbox-tts — `pip install chatterbox-tts`")

        if runtime.whisper:
            installed.append(f"faster-whisper {runtime.whisper} (optional, for checking)")
        else:
            missing.append(
                "faster-whisper (optional) — `pip install faster-whisper`; only used to "
                "verify a finished take against its script"
            )

        if shutil.which(FFPROBE):
            installed.append("ffprobe (reference-clip checks)")
        else:
            missing.append("ffprobe — install ffmpeg; without it a clip cannot be checked")

        reference_report: dict
        if reference is None:
            reference_report = {"path": None, "present": False, "ok": False}
        else:
            try:
                reference_report = inspect_reference(reference).as_dict()
            except ReferenceClipError as exc:
                reference_report = {
                    "path": str(reference),
                    "present": Path(reference).exists(),
                    "ok": False,
                    "problems": [str(exc)],
                }

        return {
            "pipeline": "chatterbox-local",
            "available": verdict.ok,
            "code": verdict.code,
            "reason": verdict.reason,
            "device": self.device(runtime),
            "installed": installed,
            "missing": missing,
            "runtime": runtime.as_dict(),
            "reference": reference_report,
            "constraints": {
                "reference_seconds": [MIN_REFERENCE_SECONDS, MAX_REFERENCE_SECONDS],
                "min_sample_rate": MIN_SAMPLE_RATE,
                "max_peak_dbfs": CLIPPING_PEAK_DBFS,
                "mono_preferred": True,
            },
            # Whether the vendor calls themselves have ever run here. They have not,
            # and a caller that reports "local voice ready" should be able to say so.
            "vendor_calls_verified": False,
        }

    # -------------------------------------------------------------------- rendering

    def render(
        self,
        text: str,
        reference_path: str | Path | None = None,
        out_path: str | Path | None = None,
    ) -> RenderedVoice:
        """Synthesise `text` in the reference voice. Raises when the pipeline is absent.

        The refusal is a typed `LocalVoiceUnavailable` carrying the same code and
        sentence `available()` would have given, so a caller that skipped the check
        still gets the actionable reason rather than an ImportError from three
        packages down.
        """
        if not str(text).strip():
            raise ValueError("nothing to synthesise: text is empty")
        if out_path is None:
            raise ValueError("out_path is required")

        out_path = Path(out_path)
        reference = Path(reference_path) if reference_path else self.reference_path

        verdict = self.check(reference)
        if not verdict.ok:
            raise LocalVoiceUnavailable(verdict.reason, verdict.code)
        if reference is None:                                     # pragma: no cover
            # check() returns CODE_REFERENCE_UNSET for this, so reaching here means the
            # diagnosis and the render disagree about what is required.
            raise LocalVoiceError("no reference clip was resolved for this render")

        # Re-measured rather than carried from check(): the advisories belong on the
        # result, so a take rendered from a stereo or quiet prompt says so afterwards.
        clip = inspect_reference(reference)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        device = self.device()
        self._synthesise(
            str(text),
            reference,
            out_path,
            device=device,
            exaggeration=self.exaggeration,
            cfg_weight=self.cfg_weight,
        )
        if not out_path.exists() or out_path.stat().st_size == 0:
            raise LocalVoiceError(
                f"the local pipeline reported success but wrote nothing to {out_path}"
            )

        # Measured, not assumed. A pipeline that writes a plausible file of the wrong
        # length is the failure this catches, and it costs one ffprobe call.
        seconds = _duration(out_path)
        if seconds is None:
            log.warning("wrote %s but could not measure its length", out_path)

        return RenderedVoice(
            path=out_path,
            seconds=seconds,
            device=device,
            reference_path=reference,
            advisories=list(clip.advisories),
        )


# ------------------------------------------------------------------- vendor surface


def _synthesise_chatterbox_unverified(
    text: str,
    reference_path: Path,
    out_path: Path,
    *,
    device: str,
    exaggeration: float,
    cfg_weight: float,
) -> None:
    """Call Chatterbox. UNVERIFIED against a real install — the one place to correct.

    Nothing in this repository's test environment can install torch or chatterbox-tts,
    so these three calls have never been executed here. They are written from the
    project's published usage shape and every one of them may be wrong in detail: the
    class name, `from_pretrained(device=...)`, the `audio_prompt_path` /
    `exaggeration` / `cfg_weight` keywords, `model.sr`, and saving through torchaudio.

    That is why this function exists as a separate function and does nothing else. If a
    real install disagrees, correct it here and in `CHATTERBOX_MODULE`; availability
    reporting, reference-clip validation and the error surface around it are covered by
    tests and do not move.

    The model is loaded per call. For this app's shape — one narration per run, in a
    web process — that is the right trade: a cached model holds VRAM for the lifetime
    of the server, and the second render of the day is not worth an idle GPU.
    """
    try:
        import torchaudio
        from chatterbox.tts import ChatterboxTTS
    except ImportError as exc:
        raise LocalVoiceUnavailable(
            "the local voice pipeline is not importable: "
            f"{exc}. Install torch and chatterbox-tts into this environment.",
            CODE_CHATTERBOX_MISSING,
        ) from exc

    model = ChatterboxTTS.from_pretrained(device=device)
    wav = model.generate(
        text,
        audio_prompt_path=str(reference_path),
        exaggeration=exaggeration,
        cfg_weight=cfg_weight,
    )
    torchaudio.save(str(out_path), wav, model.sr)
