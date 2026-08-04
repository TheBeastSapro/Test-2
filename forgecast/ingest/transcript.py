"""What is said, and exactly when — which is what everything else is timed against.

Word-level timings, not sentence-level. The difference decides what can be built on top:
sentence timings let you cut between sentences, word timings let you cut a filler word
out of the middle of one, place a caption that lands on the beat, and put a graphic on
the word it illustrates. Sentence timings are a transcript; word timings are an edit.

## Local, not an API

`faster-whisper` runs on this machine. Narration for a ten-minute video is thousands of
seconds of audio, and sending that to a paid endpoint on every ingest would make reading
a file cost money — which turns "drop a video in and see what it says" into a decision.
It also means a video that has not been published yet is not uploaded anywhere, which is
the operator's own footage and not this app's to send.

## Why the model is not downloaded on import

The first `WhisperModel(...)` fetches weights — tens of megabytes for `base`, gigabytes
for `large`. Doing that at import time makes an unrelated `import forgecast` hang on a
slow connection. `available()` reports whether the package is installed; the model
arrives on the first real transcription, where there is something on screen to say so.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger("forgecast.ingest.transcript")

# `base` rather than `large-v3`. On narration — one clear voice, no crosstalk, no music
# under it — the accuracy difference is small and the size difference is about thirty
# times. Somebody who wants the big one passes it; somebody who wants to drop a file in
# and see it work gets an answer this decade.
DEFAULT_MODEL = "base"

# Words this removes on request. Deliberately short and deliberately English-only: a
# list long enough to be clever starts cutting words that carry meaning, and "like" is
# a filler in one sentence and a verb in the next.
FILLERS = frozenset({"um", "uh", "erm", "hmm", "mm", "eh", "ah"})


@dataclass
class Word:
    """One word, and when it was said."""

    text: str
    start: float
    end: float
    # The model's own confidence. Kept because it is the only signal available for
    # "this line may be wrong", and a caption that is confidently wrong is worse than
    # no caption.
    probability: float = 1.0

    @property
    def is_filler(self) -> bool:
        return self.text.strip().strip(".,!?").lower() in FILLERS


@dataclass
class Line:
    """One spoken segment, with its words."""

    index: int
    text: str
    start: float
    end: float
    words: list[Word] = field(default_factory=list)

    @property
    def seconds(self) -> float:
        return round(max(0.0, self.end - self.start), 3)

    @property
    def words_per_second(self) -> float:
        spoken = len(self.text.split())
        return round(spoken / self.seconds, 2) if self.seconds > 0 else 0.0

    def as_dict(self) -> dict:
        return {**asdict(self), "seconds": self.seconds,
                "words_per_second": self.words_per_second}


def available() -> tuple[bool, str]:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        # See `ingest.shots.available` for why this names a button and not a pip command.
        return False, "transcription needs Video editing tools — install them in Setup"
    return True, ""


def read(path: Path, *, model_name: str = DEFAULT_MODEL,
         language: str | None = None) -> list[Line]:
    """Transcribe with word timings. The model downloads on first use."""
    ok, why = available()
    if not ok:                                                        # pragma: no cover
        raise RuntimeError(why)

    from faster_whisper import WhisperModel

    # int8 on CPU, which is what this runs on. The quality cost on speech is not
    # measurable and it is several times faster than float32 — and a transcription
    # somebody abandons is worth nothing however accurate it would have been.
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(path), word_timestamps=True,
                                       language=language, vad_filter=True)

    lines: list[Line] = []
    for index, segment in enumerate(segments):
        words = [
            Word(text=str(word.word).strip(), start=round(float(word.start), 3),
                 end=round(float(word.end), 3),
                 probability=round(float(getattr(word, "probability", 1.0) or 1.0), 3))
            for word in (segment.words or [])
            if str(word.word).strip()
        ]
        text = str(segment.text or "").strip()
        if not text:
            continue
        lines.append(Line(index=index, text=text,
                          start=round(float(segment.start), 3),
                          end=round(float(segment.end), 3), words=words))
    return lines
