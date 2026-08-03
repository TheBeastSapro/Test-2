"""The local Chatterbox bridge, tested on a machine that cannot run Chatterbox.

Which is the point. Two thirds of this file is about the absent branch, because that
is the branch that runs everywhere except the one GPU box the pipeline was written for.
What is asserted here:

* importing the module costs no torch import and prints nothing, proven with a stub
  torch on the path that leaves a marker file if it is ever executed;
* each way the pipeline can be missing produces its own diagnosis, verified through
  stub packages rather than by patching the code that does the diagnosing;
* the reference-clip checks — length, sample rate, channels, clipping — run for real,
  against clips synthesised here with ffmpeg, including a filename full of the
  characters that break a naive filtergraph.

The vendor calls themselves are never executed. `_synthesise_chatterbox_unverified` is
unverified by construction and the adapter takes an injected synthesiser so everything
around it can still be held to account.
"""

from __future__ import annotations

import importlib
import inspect
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from forgecast.voice import local
from forgecast.voice.local import (
    CODE_CHATTERBOX_MISSING,
    CODE_CUDA_MISSING,
    CODE_OK,
    CODE_REFERENCE_MISSING,
    CODE_REFERENCE_UNSET,
    CODE_REFERENCE_UNUSABLE,
    CODE_TORCH_BROKEN,
    CODE_TORCH_MISSING,
    LocalVoice,
    LocalVoiceUnavailable,
    ReferenceClipError,
    inspect_reference,
)

# A bare lavfi sine peaks at about -18.1 dBFS, so a `volume` offset sets the peak.
SINE_PEAK_DBFS = -18.06


def make_clip(
    path: Path,
    *,
    seconds: float = 10.0,
    channels: int = 1,
    rate: int = 24000,
    gain_db: float = 12.0,
    silent: bool = False,
) -> Path:
    """A synthetic voice-shaped clip. `gain_db` of 12 puts the peak near -6 dBFS."""
    path.parent.mkdir(parents=True, exist_ok=True)
    source = (
        f"anullsrc=r={rate}:cl=mono"
        if silent
        else f"sine=frequency=180:duration={seconds}:sample_rate={rate}"
    )
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", source]
    if silent:
        args += ["-t", str(seconds)]
    else:
        args += ["-af", f"volume={gain_db}dB"]
    args += ["-ac", str(channels), "-c:a", "pcm_s16le", str(path)]
    subprocess.run(args, check=True)
    return path


@pytest.fixture
def good_clip(tmp_path) -> Path:
    return make_clip(tmp_path / "reference.wav")


# --------------------------------------------------------------- stub pipeline packages
#
# The stubs let the four "pipeline is missing" branches be tested by importing what a
# real machine would import, rather than by monkeypatching `_probe_runtime` — which
# would test the mock and leave the probe itself unexercised.

TORCH_STUB = '''\
"""Stand-in for torch. Not a mock of the API — only what the probe asks of it."""

import os
from pathlib import Path

_marker = os.environ.get("FORGECAST_STUB_TORCH_MARKER")
if _marker:
    Path(_marker).write_text("torch was imported", encoding="utf-8")

if os.environ.get("FORGECAST_STUB_TORCH_BROKEN"):
    # A CUDA runtime that disagrees with the driver raises this, not ImportError.
    raise OSError("libcudart.so.12: cannot open shared object file")

__version__ = "2.4.1+stub"


class _Cuda:
    @staticmethod
    def is_available():
        return bool(os.environ.get("FORGECAST_STUB_CUDA"))

    @staticmethod
    def get_device_name(index=0):
        return "NVIDIA GeForce RTX 4090"


cuda = _Cuda()
'''

CHATTERBOX_STUB = '''\
"""Stand-in for chatterbox-tts: importable, and nothing else."""

__version__ = "0.1.2+stub"
'''


def write_stubs(root: Path, *, torch: bool = True, chatterbox: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    if torch:
        (root / "torch").mkdir(exist_ok=True)
        (root / "torch" / "__init__.py").write_text(TORCH_STUB, encoding="utf-8")
    if chatterbox:
        (root / "chatterbox").mkdir(exist_ok=True)
        (root / "chatterbox" / "__init__.py").write_text(CHATTERBOX_STUB, encoding="utf-8")
        # Real distribution metadata, because the probe reads the version from here
        # rather than importing the package. A stub without it would exercise only the
        # fallback path.
        dist = root / "chatterbox_tts-0.1.2.dist-info"
        dist.mkdir(exist_ok=True)
        (dist / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: chatterbox-tts\nVersion: 0.1.2\n",
            encoding="utf-8",
        )
    return root


@pytest.fixture
def stub_pipeline(tmp_path, monkeypatch):
    """Install stub packages on `sys.path` and take them back off afterwards.

    Leaving a fake torch in `sys.modules` would poison every later test in the process,
    so the teardown is not optional.
    """

    def install(*, torch: bool = True, chatterbox: bool = True, cuda: bool = True,
                broken: bool = False) -> None:
        root = write_stubs(tmp_path / "stubs", torch=torch, chatterbox=chatterbox)
        monkeypatch.syspath_prepend(str(root))
        monkeypatch.setenv("FORGECAST_STUB_CUDA", "1" if cuda else "")
        if broken:
            monkeypatch.setenv("FORGECAST_STUB_TORCH_BROKEN", "1")
        importlib.invalidate_caches()

    before = set(sys.modules)
    yield install

    # Only what this fixture caused to be imported. Evicting a module the process
    # already had would make this fixture the reason some later test fails.
    for name in set(sys.modules) - before:
        if name == "torch" or name.startswith(("torch.", "chatterbox")):
            del sys.modules[name]
    importlib.invalidate_caches()


# ------------------------------------------------------------------- the lazy import


def test_importing_the_module_does_not_import_torch(tmp_path):
    """The whole absent-machine promise: a status page must not pay for torch.

    Run in a subprocess with a stub torch first on the path. If any import in
    `forgecast.voice.local` reaches torch, the stub writes the marker file and this
    fails — on this machine torch is absent, so an in-process check would pass for the
    wrong reason.
    """
    stubs = write_stubs(tmp_path / "stubs")
    marker = tmp_path / "torch-was-imported"
    repo_root = Path(local.__file__).resolve().parents[2]

    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(stubs), str(repo_root)]),
        "FORGECAST_STUB_TORCH_MARKER": str(marker),
        "FORGECAST_STUB_CUDA": "1",
    }
    script = textwrap.dedent(
        """
        import sys
        import forgecast.voice.local  # noqa: F401
        assert "torch" not in sys.modules, "torch was imported"
        assert "chatterbox" not in sys.modules, "chatterbox was imported"
        print("clean")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "clean"
    assert not marker.exists(), "importing the module executed torch"
    # Warnings go to stderr, and a module that mutters on import is a module that
    # mutters into every CLI command's output.
    assert result.stderr == "", result.stderr


def test_the_stub_torch_is_actually_reachable_when_asked(tmp_path, stub_pipeline):
    """Guards the test above from passing because the stub was never importable."""
    marker = tmp_path / "marker"
    os.environ["FORGECAST_STUB_TORCH_MARKER"] = str(marker)
    try:
        stub_pipeline(cuda=True)
        runtime = local._probe_runtime()
    finally:
        os.environ.pop("FORGECAST_STUB_TORCH_MARKER", None)

    assert runtime.torch == "2.4.1+stub"
    assert marker.exists()


# ---------------------------------------------------------------------- the diagnosis


def test_no_torch_at_all_says_so_and_names_the_installer(good_clip):
    verdict = LocalVoice(good_clip).check()
    assert (verdict.ok, verdict.code) == (False, CODE_TORCH_MISSING)
    assert "pytorch.org" in verdict.reason

    ok, reason = LocalVoice(good_clip).available()
    assert ok is False
    assert reason == verdict.reason


def test_torch_present_but_no_cuda_is_a_different_answer(good_clip, stub_pipeline):
    """A CPU box needs "install a CUDA build", not "install torch"."""
    stub_pipeline(cuda=False)
    verdict = LocalVoice(good_clip).check()

    assert (verdict.ok, verdict.code) == (False, CODE_CUDA_MISSING)
    assert "2.4.1+stub" in verdict.reason
    assert "require_cuda=False" in verdict.reason


def test_cpu_synthesis_can_be_opted_into(good_clip, stub_pipeline):
    stub_pipeline(cuda=False)
    voice = LocalVoice(good_clip, require_cuda=False)

    verdict = voice.check()
    assert (verdict.ok, verdict.code) == (True, CODE_OK)
    assert voice.device() == "cpu"


def test_broken_torch_is_reported_as_broken_not_missing(good_clip, stub_pipeline):
    """torch raises OSError on a CUDA mismatch. "Not installed" would be a lie."""
    stub_pipeline(broken=True)
    verdict = LocalVoice(good_clip).check()

    assert (verdict.ok, verdict.code) == (False, CODE_TORCH_BROKEN)
    assert "libcudart" in verdict.reason
    assert "reinstall" in verdict.reason


def test_missing_chatterbox_names_its_own_install(good_clip, stub_pipeline):
    stub_pipeline(chatterbox=False)
    verdict = LocalVoice(good_clip).check()

    assert (verdict.ok, verdict.code) == (False, CODE_CHATTERBOX_MISSING)
    assert "pip install chatterbox-tts" in verdict.reason


def test_an_unset_reference_is_distinct_from_a_missing_file(tmp_path, stub_pipeline):
    stub_pipeline()
    assert LocalVoice().check().code == CODE_REFERENCE_UNSET
    assert LocalVoice(tmp_path / "nope.wav").check().code == CODE_REFERENCE_MISSING


def test_a_measurable_but_wrong_reference_is_refused_with_the_measurement(
    tmp_path, stub_pipeline
):
    stub_pipeline()
    short = make_clip(tmp_path / "short.wav", seconds=3.0)

    verdict = LocalVoice(short).check()
    assert (verdict.ok, verdict.code) == (False, CODE_REFERENCE_UNUSABLE)
    assert "3.0s" in verdict.reason
    assert "too short" in verdict.reason


def test_a_full_pipeline_with_a_good_clip_is_available(good_clip, stub_pipeline):
    stub_pipeline(cuda=True)
    ok, reason = LocalVoice(good_clip).available()

    assert ok is True
    assert "RTX 4090" in reason
    assert "reference.wav" in reason


def test_the_runtime_check_is_not_cached_across_calls(good_clip, stub_pipeline):
    """The pipeline can be installed while the app is running, and should be noticed."""
    voice = LocalVoice(good_clip)
    assert voice.check().code == CODE_TORCH_MISSING

    stub_pipeline(cuda=True)
    assert voice.check().code == CODE_OK


# ------------------------------------------------------------------------- describe()


def test_describe_lists_everything_missing_with_a_fix_each(good_clip):
    report = LocalVoice(good_clip).describe()

    assert report["available"] is False
    assert report["code"] == CODE_TORCH_MISSING
    assert report["vendor_calls_verified"] is False
    # Every line an operator is shown has to say what to do about it.
    joined = " ".join(report["missing"])
    assert "pytorch.org" in joined
    assert "pip install chatterbox-tts" in joined
    assert any("faster-whisper" in line and "optional" in line for line in report["missing"])
    # ffprobe is here, so the clip checks are live and the clip itself was measured.
    assert any("ffprobe" in line for line in report["installed"])
    assert report["reference"]["ok"] is True
    assert report["reference"]["seconds"] == pytest.approx(10.0, abs=0.05)


def test_describe_on_a_complete_install_lists_versions(good_clip, stub_pipeline):
    stub_pipeline(cuda=True)
    report = LocalVoice(good_clip).describe()

    assert report["available"] is True
    assert report["device"] == "cuda"
    assert "torch 2.4.1+stub" in report["installed"]
    assert "chatterbox-tts 0.1.2" in report["installed"]
    assert any("RTX 4090" in line for line in report["installed"])
    # Still unverified, however healthy the machine looks.
    assert report["vendor_calls_verified"] is False
    assert json.dumps(report)                       # renderable straight into a panel


def test_a_half_finished_install_reports_both_halves(good_clip, stub_pipeline):
    """chatterbox-tts present, torch absent: the earlier version of this hid the first.

    The probe used to give up as soon as torch was missing, so a machine that had
    chatterbox-tts installed was told to install it.
    """
    stub_pipeline(torch=False, chatterbox=True)
    report = LocalVoice(good_clip).describe()

    assert report["code"] == CODE_TORCH_MISSING
    assert "chatterbox-tts 0.1.2" in report["installed"]
    assert not any("chatterbox" in line for line in report["missing"])


def test_describe_reports_a_bad_reference_without_raising(tmp_path, stub_pipeline):
    stub_pipeline()
    report = LocalVoice(tmp_path / "gone.wav").describe()

    assert report["reference"]["present"] is False
    assert report["reference"]["ok"] is False
    assert report["code"] == CODE_REFERENCE_MISSING


# --------------------------------------------------------------------------- render()


def test_render_raises_the_typed_error_and_writes_nothing(tmp_path, good_clip):
    out = tmp_path / "out" / "narration.wav"
    calls = []

    voice = LocalVoice(good_clip, synthesise=lambda *a, **k: calls.append(a))
    with pytest.raises(LocalVoiceUnavailable) as caught:
        voice.render("Hello there.", out_path=out)

    assert caught.value.code == CODE_TORCH_MISSING
    assert "pytorch.org" in caught.value.reason
    assert calls == []
    # Not even the parent directory: a failed render must not litter storage.
    assert not out.exists()
    assert not out.parent.exists()


def test_render_refuses_a_bad_clip_before_spending_anything(tmp_path, stub_pipeline):
    stub_pipeline()
    clipped = make_clip(tmp_path / "hot.wav", gain_db=24.0)
    calls = []

    voice = LocalVoice(clipped, synthesise=lambda *a, **k: calls.append(a))
    with pytest.raises(LocalVoiceUnavailable) as caught:
        voice.render("Hello there.", out_path=tmp_path / "out.wav")

    assert caught.value.code == CODE_REFERENCE_UNUSABLE
    assert "clipping" in caught.value.reason
    assert calls == []


def test_render_passes_the_reference_through_and_measures_what_was_written(
    tmp_path, stub_pipeline
):
    """The adapter's own contract: prompt in, file out, length measured not assumed."""
    stub_pipeline(cuda=True)
    reference = make_clip(tmp_path / "ref.wav", channels=2)
    seen = {}

    def fake_synthesise(text, reference_path, out_path, **kwargs):
        seen.update(text=text, reference=reference_path, kwargs=kwargs)
        make_clip(out_path, seconds=4.0)

    out = tmp_path / "renders" / "narration.wav"
    result = LocalVoice(reference, synthesise=fake_synthesise).render(
        "Two sentences of narration.", out_path=out
    )

    assert seen["text"] == "Two sentences of narration."
    assert seen["reference"] == reference
    assert seen["kwargs"]["device"] == "cuda"
    assert seen["kwargs"]["exaggeration"] == 0.5
    assert result.path == out
    assert result.seconds == pytest.approx(4.0, abs=0.05)
    # The stereo prompt was allowed, and the take says it was rendered from one.
    assert any("mono is preferred" in line for line in result.advisories)
    assert result.as_dict()["device"] == "cuda"


def test_render_reports_a_pipeline_that_wrote_nothing(tmp_path, stub_pipeline):
    stub_pipeline(cuda=True)
    reference = make_clip(tmp_path / "ref.wav")

    voice = LocalVoice(reference, synthesise=lambda *a, **k: None)
    with pytest.raises(local.LocalVoiceError, match="wrote nothing"):
        voice.render("Hello.", out_path=tmp_path / "silent.wav")


def test_render_rejects_empty_text_and_a_missing_destination(good_clip):
    voice = LocalVoice(good_clip)
    with pytest.raises(ValueError, match="empty"):
        voice.render("   ", out_path="anywhere.wav")
    with pytest.raises(ValueError, match="out_path"):
        voice.render("Something.", out_path=None)


def test_a_per_call_reference_overrides_the_constructor(tmp_path, stub_pipeline):
    stub_pipeline(cuda=True)
    voice = LocalVoice(tmp_path / "does-not-exist.wav")
    assert voice.check().code == CODE_REFERENCE_MISSING

    other = make_clip(tmp_path / "other.wav")
    assert voice.check(other).code == CODE_OK
    assert voice.available(other)[0] is True


# --------------------------------------------------- the part that genuinely runs here


def test_a_good_clip_passes_every_constraint(good_clip):
    clip = inspect_reference(good_clip)

    assert clip.ok is True
    assert clip.problems == []
    assert clip.channels == 1
    assert clip.sample_rate == 24000
    assert clip.seconds == pytest.approx(10.0, abs=0.05)
    assert clip.peak_dbfs == pytest.approx(SINE_PEAK_DBFS + 12.0, abs=0.5)
    assert clip.rms_dbfs is not None and clip.rms_dbfs < clip.peak_dbfs


@pytest.mark.parametrize("seconds,expected", [(4.0, "too short"), (20.0, "longer than needed")])
def test_the_length_window_is_enforced_in_both_directions(tmp_path, seconds, expected):
    clip = inspect_reference(make_clip(tmp_path / "len.wav", seconds=seconds))
    assert clip.ok is False
    assert any(expected in problem for problem in clip.problems)


@pytest.mark.parametrize("seconds", [8.0, 12.0])
def test_the_boundaries_of_the_window_are_inside_it(tmp_path, seconds):
    clip = inspect_reference(make_clip(tmp_path / f"edge{seconds}.wav", seconds=seconds))
    assert clip.ok is True, clip.problems


def test_a_clipped_clip_is_refused_and_a_hot_one_is_not(tmp_path):
    """+24 dB on a -18 dBFS source pins the waveform to the ceiling."""
    clipped = inspect_reference(make_clip(tmp_path / "clipped.wav", gain_db=24.0))
    assert clipped.ok is False
    assert any("clipping" in problem for problem in clipped.problems)
    assert clipped.peak_dbfs is not None and clipped.peak_dbfs >= -0.5

    healthy = inspect_reference(make_clip(tmp_path / "healthy.wav", gain_db=15.0))
    assert healthy.ok is True, healthy.problems


def test_silence_is_refused_with_the_reason_being_silence(tmp_path):
    clip = inspect_reference(make_clip(tmp_path / "quiet.wav", silent=True, seconds=10.0))
    assert clip.ok is False
    assert any("silent" in problem for problem in clip.problems)


def test_a_very_quiet_clip_is_advised_against_not_refused(tmp_path):
    clip = inspect_reference(make_clip(tmp_path / "faint.wav", gain_db=-12.0))
    assert clip.ok is True, clip.problems
    assert any("dBFS" in line for line in clip.advisories)


def test_stereo_is_an_advisory_because_the_pipeline_downmixes(tmp_path):
    clip = inspect_reference(make_clip(tmp_path / "stereo.wav", channels=2))
    assert clip.ok is True, clip.problems
    assert clip.channels == 2
    assert any("mono is preferred" in line for line in clip.advisories)


def test_telephone_band_audio_is_refused_and_16k_is_only_advised(tmp_path):
    narrow = inspect_reference(make_clip(tmp_path / "narrow.wav", rate=8000))
    assert narrow.ok is False
    assert any("8000 Hz" in problem for problem in narrow.problems)

    acceptable = inspect_reference(make_clip(tmp_path / "ok.wav", rate=16000))
    assert acceptable.ok is True, acceptable.problems
    assert any("16000 Hz works" in line for line in acceptable.advisories)


def test_awkward_filenames_are_still_measured(tmp_path):
    """Pins the filtergraph quoting. "dad's voice.wav" is the ordinary case that broke.

    The level meter is the only ffprobe call whose path goes through a filtergraph
    rather than argv, and the quoting there has two layers. Every character that
    separates one filter from the next is in this name on purpose.
    """
    awkward = tmp_path / "dad's take: 1, [best]; v=2 \\ final.wav"
    clip = inspect_reference(make_clip(awkward))

    assert clip.ok is True, clip.problems
    assert clip.peak_dbfs is not None


def test_a_missing_file_and_a_non_audio_file_are_told_apart(tmp_path):
    with pytest.raises(ReferenceClipError, match="no reference clip at"):
        inspect_reference(tmp_path / "absent.wav")

    text = tmp_path / "notes.txt"
    text.write_text("this is not a recording", encoding="utf-8")
    with pytest.raises(ReferenceClipError, match="could not read"):
        inspect_reference(text)


def test_a_silent_video_is_refused_for_having_no_voice_in_it(tmp_path):
    """The mistake is easy to make: pointing the reference at the source footage."""
    footage = tmp_path / "footage.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", "testsrc=size=160x120:rate=10:duration=10", "-c:v", "libx264", str(footage)],
        check=True,
    )
    with pytest.raises(ReferenceClipError, match="no audio stream"):
        inspect_reference(footage)


def test_without_ffprobe_the_clip_check_blames_ffprobe_not_the_clip(
    good_clip, monkeypatch
):
    """An operator whose recording is fine must not be sent to re-record it."""
    monkeypatch.setattr(local, "FFPROBE", "ffprobe-that-is-not-installed")

    with pytest.raises(ReferenceClipError, match="ffprobe is not installed"):
        inspect_reference(good_clip)

    # And the adapter surfaces it as a reference problem rather than crashing.
    verdict = LocalVoice(good_clip).check()
    assert verdict.ok is False


def test_the_vendor_call_is_isolated_and_declares_itself_unverified():
    """A structural assertion: exactly one place in the module holds the vendor API.

    If a second call site appears, this fails — which is the whole reason the module is
    shaped this way. Nobody can run these calls here, so the correction has to be cheap.
    """
    vendor = inspect.getsource(local._synthesise_chatterbox_unverified)
    elsewhere = Path(local.__file__).read_text(encoding="utf-8").replace(vendor, "")

    assert "UNVERIFIED" in vendor
    for name in ("ChatterboxTTS", "from_pretrained", "audio_prompt_path", "torchaudio"):
        assert name in vendor, name
        assert name not in elsewhere, f"{name} escaped the unverified function"
    # The default synthesiser is that function and nothing else.
    assert LocalVoice()._synthesise is local._synthesise_chatterbox_unverified
