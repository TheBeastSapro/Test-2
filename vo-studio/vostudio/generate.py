"""
Chatterbox generation.

MEASURED ON THE REAL MODEL, not assumed:

  sample rate       24 000 Hz. Not negotiable, not a setting. Everything after
                    this works at 48 kHz; the upsample adds no detail above
                    12 kHz and is only there so the master is not resampling
                    mid-chain.

  output level      CLIPS. A 3.6 s test phrase came back with 53 samples at full
                    scale in 11 consecutive runs, peak 0.00 dBFS. Every chunk
                    gets headroom applied here, at birth, because a clipped
                    sample cannot be un-clipped further down the chain and the
                    loudness stage would happily normalise the distortion along
                    with the voice.

  watermark         Every output is watermarked by Perth
                    (PerthImplicitWatermarker) inside ChatterboxTTS.generate().
                    It is inaudible and it cannot be switched off from the public
                    API. It is disclosed in the README because it is a property
                    of the audio, not a detail.

  chunk ceiling     generate() runs with max_new_tokens=1000, ~40 s of speech. It
                    truncates rather than raising, so an over-long chunk loses
                    its tail silently. script_prep keeps chunks far below this.
"""
import gc
from pathlib import Path

import numpy as np
import soundfile as sf


class Generator:
    """Owns the model. Load once; loading costs ~30 s and most of your VRAM."""

    def __init__(self, settings, device: str | None = None, log=print):
        self._settings = settings
        self.cfg = settings.generation
        self.log = log
        self._model = None
        self._device = device

    # -- device ------------------------------------------------------------
    def resolve_device(self) -> str:
        if self._device:
            return self._device
        import torch
        if torch.cuda.is_available():
            self._device = "cuda"
            name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
            self.log(f"GPU: {name} ({vram:.1f} GB)")
            if vram < 5.5:
                self.log("WARNING: under ~6 GB. Expect out-of-memory on long "
                         "chunks. Lower max_chars_per_chunk in Settings.")
        else:
            self._device = "cpu"
            self.log("No CUDA GPU found — falling back to CPU. Measured at 10.3x "
                     "realtime on 4 cores, so a 12-minute script takes about two "
                     "hours. Usable for a test line, not for a script.")
        return self._device

    def load(self):
        if self._model is not None:
            return self._model
        device = self.resolve_device()
        if getattr(self.cfg, "variant", "standard") == "turbo":
            from chatterbox.tts_turbo import ChatterboxTurboTTS as Model
            self.log(f"Loading Chatterbox TURBO on {device} ...")
        else:
            from chatterbox.tts import ChatterboxTTS as Model
            self.log(f"Loading Chatterbox on {device} ...")
        self._model = Model.from_pretrained(device=device)
        # NOT self._model.t3.half().
        #
        #     RuntimeError: mat1 and mat2 must have the same dtype,
        #                   but got Float and Half
        #
        # Casting one stage to fp16 leaves everything feeding it -- the speaker
        # conditioning, the reference embedding -- in fp32, and the first matmul
        # that meets both dies. Half the model in half precision is not a
        # memory optimisation, it is a type error waiting for a reference clip.
        #
        # autocast is the correct tool: it decides per operation, keeps the
        # accumulations that need range in fp32, and casts nothing permanently.
        # Applied at generate() time, in _generate below.
        if self._model.sr != self.cfg.model_sr:
            self.log(f"NOTE: model reports {self._model.sr} Hz, config expects "
                     f"{self.cfg.model_sr} Hz. Trusting the model.")
            self.cfg.model_sr = self._model.sr
        return self._model

    def unload(self):
        self._model = None
        gc.collect()
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass

    # -- generation --------------------------------------------------------
    def _seed(self):
        if self.cfg.seed is None:
            return
        import torch, random
        torch.manual_seed(self.cfg.seed)
        random.seed(self.cfg.seed)
        np.random.seed(self.cfg.seed)

    def resolve_speed(self, speed: float | None) -> float:
        """
        The pace, from the caller or from settings.

        A take passed the profile's speed; a full render passed nothing, and
        nothing was where the pace stopped existing -- the render came out at
        1.00 however the voice had been tuned. Settings now carries it, so both
        paths land on the same number.
        """
        return float(getattr(self.cfg, "speed", 1.0) if speed is None else speed)

    def _generate(self, model, text: str, kwargs: dict):
        """
        Run the model, in mixed precision where that is safe.

        With a fallback, because 6 GB is exactly the size where fp16 is worth
        having and also where an unexpected dtype ends the render. If autocast
        trips over a dtype anyway, the chunk is retried in plain fp32: slower
        and hungrier, but it produces audio instead of a traceback.
        """
        import torch
        if not (self.cfg.use_fp16 and self.resolve_device() == "cuda"):
            return model.generate(text, **kwargs)
        try:
            with torch.autocast(device_type="cuda", dtype=torch.float16):
                return model.generate(text, **kwargs)
        except RuntimeError as exc:
            if "dtype" not in str(exc).lower() and "half" not in str(exc).lower():
                raise
            self.log(f"fp16 path failed ({exc}); retrying this chunk in fp32")
            torch.cuda.empty_cache()
            return model.generate(text, **kwargs)

    def generate_chunk(self, text: str, voice_ref: str, out_path: Path,
                       exaggeration: float | None = None,
                       temperature: float | None = None,
                       cfg_weight: float | None = None,
                       speed: float | None = None) -> Path:
        # The engine decides where the audio comes from and nothing else. The
        # headroom, the resample, the speed pass and everything downstream are
        # the same either way -- which is the point of switching here rather
        # than forking the pipeline.
        if getattr(self.cfg, "engine", "chatterbox") == "elevenlabs":
            from . import eleven
            self.log(f"ElevenLabs: {len(text)} chars "
                     f"(about ${eleven.estimate_usd(text):.3f})")
            eleven.synthesize(text, out_path, self._settings, self.cfg.work_sr)
            audio, rate = sf.read(out_path)
            # Headroom here too. The local branch applies it to every chunk and
            # this one returned before it -- so an ElevenLabs render skipped
            # the -3 dB ceiling and the clip report entirely.
            sf.write(out_path, apply_headroom(audio, self.log), rate, subtype="PCM_24")
            spd = self.resolve_speed(speed)
            if abs(spd - 1.0) >= 0.005:
                from .voice_profile import apply_speed
                import shutil
                shutil.copy(apply_speed(out_path, spd), out_path)
            return out_path

        model = self.load()
        self._seed()
        kwargs = dict(
            audio_prompt_path=str(voice_ref),
            exaggeration=self.cfg.exaggeration if exaggeration is None else exaggeration,
            cfg_weight=self.cfg.cfg_weight if cfg_weight is None else cfg_weight,
            temperature=self.cfg.temperature if temperature is None else temperature,
            repetition_penalty=self.cfg.repetition_penalty,
            min_p=self.cfg.min_p,
            top_p=self.cfg.top_p,
        )
        if getattr(self.cfg, "variant", "standard") == "turbo":
            # Turbo-only. Passing these to Standard is a TypeError, so they are
            # added here rather than defaulted into the shared kwargs.
            kwargs["top_k"] = getattr(self.cfg, "top_k", 1000)
            # Turbo normalises its own loudness. Left on, it fights the mastering
            # stage for control of level; the master measures and sets LUFS, so
            # this is off and the master keeps the decision.
            kwargs["norm_loudness"] = False
        wav = self._generate(model, text, kwargs)
        audio = wav.squeeze(0).detach().cpu().float().numpy()
        audio = apply_headroom(audio, self.log)
        audio = resample(audio, self.cfg.model_sr, self.cfg.work_sr)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(out_path, audio, self.cfg.work_sr, subtype="PCM_24")

        # Chatterbox has no speed parameter, so pace is set here with atempo.
        # Pitch-preserving; a phase vocoder is NOT (measured at +4.5-8.5% f0).
        if speed is not None and abs(speed - 1.0) >= 0.005:
            from .voice_profile import apply_speed
            import shutil
            shutil.copy(apply_speed(out_path, spd), out_path)

        if self.cfg.empty_cache_between_chunks and self._device == "cuda":
            import torch
            torch.cuda.empty_cache()
        return out_path


def apply_headroom(audio: np.ndarray, log=print, ceiling_db: float = -3.0) -> np.ndarray:
    """
    Pull the chunk down to a fixed ceiling and report if it arrived clipped.

    Scaling, never limiting. A limiter would change the shape of the read to buy
    level the loudness stage is going to set anyway; this only moves the whole
    chunk down so nothing downstream inherits a squared-off peak. The clip count
    is logged rather than silently repaired -- samples already pinned at full
    scale are distortion the model produced, and scaling cannot undo them. A
    chunk that reports clipping is a candidate for a re-roll.
    """
    clipped = int((np.abs(audio) >= 0.999).sum())
    if clipped:
        log(f"  {clipped} sample(s) generated at full scale — distortion is "
            f"baked in. Re-roll this chunk if it is audible.")
    if audio.size == 0:
        # A chunk that generated nothing. .max() on an empty array raises, so
        # the whole render used to die here rather than reporting the chunk.
        log("  WARNING: this chunk generated no audio at all.")
        return audio
    peak = float(np.abs(audio).max())
    if peak <= 0:
        return audio
    return audio * (10 ** (ceiling_db / 20.0) / peak)


def resample(audio: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out:
        return audio
    from scipy.signal import resample_poly
    from math import gcd
    g = gcd(sr_in, sr_out)
    return resample_poly(audio, sr_out // g, sr_in // g)


def join(paths: list[Path], out_path: Path, sr: int, edge_fade_ms: float) -> Path:
    """
    Concatenate chunks with a short fade on each edge.

    Section joins clicked audibly until this went in. The fade is 3 ms by
    default: long enough to kill the step discontinuity, short enough that it
    cannot be heard as a fade on speech.
    """
    n_fade = max(1, int(sr * edge_fade_ms / 1000.0))
    fade_in = np.linspace(0.0, 1.0, n_fade)
    fade_out = fade_in[::-1]

    pieces = []
    for p in paths:
        a, file_sr = sf.read(p)
        if file_sr != sr:
            a = resample(a, file_sr, sr)
        if len(a) > 2 * n_fade:
            a = a.copy()
            a[:n_fade] *= fade_in
            a[-n_fade:] *= fade_out
        pieces.append(a)

    out = np.concatenate(pieces) if pieces else np.zeros(0)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out_path, out, sr, subtype="PCM_24")
    return out_path
