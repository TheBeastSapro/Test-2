"""
Did the voice read what the script said?

Chatterbox is a sampler, not a reader. It drops words, doubles words, and
occasionally hallucinates one that was never in the script. Nothing downstream
catches that -- the audio is clean, the levels are right, and the defect is a
missing word only a transcript can see.

The whole point of generating locally is that a re-roll is free. On ElevenLabs a
failed check cost credits, so the thresholds were tuned to avoid re-rendering. Here
they are tuned to catch defects, because being wrong costs seconds.
"""
from dataclasses import dataclass, field
from pathlib import Path
import re

_WORD = re.compile(r"[a-z0-9']+")


def normalize(text: str) -> list[str]:
    """
    Lowercase, strip punctuation, keep apostrophes.

    ASR punctuation is not a defect. It writes "Hashish!" next to a stranded
    fricative and "Hashish." without one -- real signal about the audio, but not a
    different word, and comparing on it produces failures nobody can act on.
    """
    return _WORD.findall(text.lower().replace("’", "'"))


def wer(reference: list[str], hypothesis: list[str]) -> float:
    """Levenshtein over words, normalised by reference length."""
    if not reference:
        return 0.0 if not hypothesis else 1.0
    prev = list(range(len(hypothesis) + 1))
    for i, r in enumerate(reference, 1):
        cur = [i]
        for j, h in enumerate(hypothesis, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return prev[-1] / len(reference)


def missing_words(reference: list[str], hypothesis: list[str]) -> list[str]:
    """
    Which reference words the read dropped, matched in order.

    Greedy subsequence walk, so a repeated word must be matched as many times as it
    occurs -- losing one "took" out of "took Alexandria, took Cairo" has to register,
    and a set comparison would hide it.
    """
    lost, i = [], 0
    for w in reference:
        j = i
        while j < len(hypothesis) and hypothesis[j] != w:
            j += 1
        if j < len(hypothesis):
            i = j + 1
        else:
            lost.append(w)
    return lost


@dataclass
class ChunkVerdict:
    index: int
    wer: float
    transcript: str
    missing: list[str] = field(default_factory=list)
    passed: bool = False
    exempt: bool = False
    reason: str = ""


class ReadChecker:
    """Owns the ASR model. Load once — it is ~750 MB and slow to construct."""

    def __init__(self, settings, log=print):
        self.cfg = settings.readcheck
        self.log = log
        self._model = None

    def load(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self.log(f"Loading ASR ({self.cfg.model}, {self.cfg.compute_type}) ...")
            # float32, never int8. int8 hallucinated dropped words and sent the old
            # pipeline re-rendering lines that had been read correctly.
            self._model = WhisperModel(self.cfg.model, device="cpu",
                                       compute_type=self.cfg.compute_type)
        return self._model

    def transcribe(self, path: Path) -> str:
        segments, _ = self.load().transcribe(
            str(path), language="en", vad_filter=False, beam_size=5)
        return " ".join(s.text.strip() for s in segments)

    def check(self, audio: Path, expected: str, index: int = 0,
              is_chapter: bool = False) -> ChunkVerdict:
        """
        One chunk against its script text.

        A chapter announcement is one or two words. WER is quantised to 0, 0.5, 1.0
        at that length, so a single ASR quirk reads as a 50% error rate and the check
        can only fire falsely. Those are transcribed and required to be non-empty --
        which still catches the failure that matters, a header that generated silence.
        """
        text = self.transcribe(audio)
        ref, hyp = normalize(expected), normalize(text)

        if is_chapter and self.cfg.exempt_chapter_headers \
                and len(ref) <= self.cfg.chapter_max_words:
            ok = len(hyp) > 0
            return ChunkVerdict(index, -1.0, text, [], ok, True,
                                "chapter header — checked for speech, not WER"
                                if ok else "chapter header generated no speech")

        rate = wer(ref, hyp)
        lost = missing_words(ref, hyp)
        ok = rate <= self.cfg.wer_threshold
        return ChunkVerdict(index, rate, text, lost, ok, False,
                            "" if ok else f"WER {rate:.3f} > {self.cfg.wer_threshold}")


def render_with_retries(generator, checker, chunk, voice_ref, out_dir: Path,
                        is_chapter: bool, log=print):
    """
    Generate, check, re-roll on failure — the loop that makes local generation worth it.

    The re-roll varies temperature rather than repeating the identical call, because
    an unchanged call to a sampler is a coin flip with the same bias. Raising it
    slightly moves the read off whatever attractor swallowed the word.

    The redo block sat OUTSIDE its loop in the old pipeline, so a retry re-rendered
    at the wrong settings and the check that followed judged the wrong take. Keep the
    generate/check pair together inside the loop.
    """
    best: ChunkVerdict | None = None
    best_path: Path | None = None

    for attempt in range(checker.cfg.max_redos + 1):
        temperature = generator.cfg.temperature + (0.15 * attempt)
        path = out_dir / f"chunk_{chunk.index:04d}_take{attempt}.wav"
        generator.generate_chunk(chunk.text, voice_ref, path, temperature=temperature)

        verdict = checker.check(path, chunk.text, chunk.index, is_chapter)
        chunk.attempts = attempt + 1
        chunk.wer, chunk.transcript = verdict.wer, verdict.transcript

        if verdict.passed:
            chunk.audio_path = str(path)
            return verdict, path

        if best is None or (verdict.wer >= 0 and verdict.wer < best.wer):
            best, best_path = verdict, path

        log(f"  chunk {chunk.index} take {attempt+1} failed: {verdict.reason}"
            + (f" — dropped {verdict.missing}" if verdict.missing else ""))

    # Every take failed. Keep the least-bad one and say so loudly rather than
    # silently shipping it as if it had passed.
    log(f"  chunk {chunk.index}: {checker.cfg.max_redos + 1} takes all failed — "
        f"keeping the best (WER {best.wer:.3f}). NEEDS A HUMAN EAR.")
    chunk.audio_path = str(best_path)
    return best, best_path
