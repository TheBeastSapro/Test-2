"""
Every number here was paid for once already.

The thresholds are not defaults picked from a docs page. Each one replaced a
value that let something broken reach Sapro, and the comment says which. Change
one only with a measurement in hand.
"""
from dataclasses import dataclass, field, asdict
from pathlib import Path
import json

APP_NAME = "ExplainTory VO Studio"
APP_DIR = Path.home() / "ExplainTory VO Studio"
VOICES_DIR = APP_DIR / "voices"
PROJECTS_DIR = APP_DIR / "projects"
SETTINGS_FILE = APP_DIR / "settings.json"


@dataclass
class Generation:
    # Chatterbox emits 24 kHz. Everything downstream works at 48 kHz because the
    # channel's back catalogue is 48 kHz and the mastering chain assumes it. The
    # upsample does NOT invent detail above 12 kHz -- it only stops the master
    # from resampling mid-chain. See README, "What you give up".
    model_sr: int = 24000
    work_sr: int = 48000

    exaggeration: float = 0.5   # 0.5 = neutral read. Above ~0.7 it starts acting.
    cfg_weight: float = 0.5     # lower = closer to the reference's own pacing
    temperature: float = 0.8
    repetition_penalty: float = 1.2
    min_p: float = 0.05
    top_p: float = 1.0

    # The model's own generate() caps at max_new_tokens=1000, roughly 40 s of
    # speech, and quality falls off long before that ceiling. Chunking at the
    # sentence level keeps every call well inside it and means a bad chunk is
    # re-rolled alone instead of taking a paragraph with it.
    max_chars_per_chunk: int = 300

    # 6-8 GB cards: fp16 and an empty_cache() between chunks. On a 12 GB+ card
    # this costs nothing measurable, so it is not worth branching on.
    use_fp16: bool = True
    empty_cache_between_chunks: bool = True

    seed: int | None = None     # set for reproducible re-rolls


@dataclass
class ReadCheck:
    # int8 hallucinated dropped words and sent the pipeline re-rendering lines
    # that were read correctly. float32, always.
    compute_type: str = "float32"
    model: str = "distil-large-v3"

    # 0.05 sat BELOW the 0.047 median WER measured on known-good audio, so good
    # sections failed and were re-rendered at a worse setting.
    wer_threshold: float = 0.20

    # A chapter announcement is one or two words. Speaking-rate and WER checks
    # are meaningless at that length and only ever fire falsely.
    exempt_chapter_headers: bool = True
    chapter_max_words: int = 3

    max_redos: int = 2


@dataclass
class Master:
    target_lufs: float = -14.0
    target_true_peak: float = -1.5

    # Joins clicked audibly until an edge fade went on every splice.
    edge_fade_ms: float = 3.0

    # The master used to pad EVERY comma to 160 ms, including the ones the voice
    # read straight through. That single behaviour is why one reported defect
    # survived five upstream fixes -- the master ran last and put it back each
    # time. A comma the voice already ran through is left alone.
    comma_pad_ms: float = 160.0
    runthrough_threshold_s: float = 0.060

    chapter_gap_s: float = 0.30


@dataclass
class Orphans:
    """Detector settings. See vostudio/orphans.py for why each side is fenced."""
    min_gap_s: float = 0.040
    max_island_s: float = 0.260
    min_peak_db: float = -40.0
    context_s: float = 3.0
    enabled: bool = True


@dataclass
class Settings:
    generation: Generation = field(default_factory=Generation)
    readcheck: ReadCheck = field(default_factory=ReadCheck)
    master: Master = field(default_factory=Master)
    orphans: Orphans = field(default_factory=Orphans)
    active_voice: str = ""

    @classmethod
    def load(cls) -> "Settings":
        if SETTINGS_FILE.exists():
            raw = json.loads(SETTINGS_FILE.read_text())
            return cls(
                generation=Generation(**raw.get("generation", {})),
                readcheck=ReadCheck(**raw.get("readcheck", {})),
                master=Master(**raw.get("master", {})),
                orphans=Orphans(**raw.get("orphans", {})),
                active_voice=raw.get("active_voice", ""),
            )
        s = cls()
        s.save()
        return s

    def save(self) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(asdict(self), indent=2))


def ensure_dirs() -> None:
    for d in (APP_DIR, VOICES_DIR, PROJECTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
