"""
Script in, mastered MP3 out.

The order is the order, and each step earns its place by catching something the
next one cannot see:

    prep       -> sections and chunks; numerals spelled out ONCE, here, so every
                  later stage phonemizes and aligns the same text that was spoken
    generate   -> per chunk, with headroom applied at birth
    read-check -> per chunk, re-rolled while it is free to re-roll
    stitch     -> 3 ms edge fades, because joins clicked without them
    master     -> beats and loudness, run last
    orphans    -> after the master, because the master is what strands fragments
    pronounce  -> after the master, on the file that actually ships

The last two run on the DELIVERED audio, not the stitch. A defect the master
introduces is invisible to any check that ran before it — that is how a stray
fricative survived six repairs.
"""
from dataclasses import dataclass, field
from pathlib import Path
import shutil
import subprocess

from . import script_prep
from .generate import Generator, join
from .readcheck import ReadChecker, render_with_retries
from .master import master


@dataclass
class Result:
    title: str
    final_path: Path | None = None
    duration_s: float = 0.0
    sections: int = 0
    chunks: int = 0
    rerolled: int = 0
    unresolved: list[int] = field(default_factory=list)
    orphans: list[dict] = field(default_factory=list)
    pronunciation: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def run(script_text: str, title: str, voice_ref: Path, settings,
        project_dir: Path, log=print) -> Result:
    work = project_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    result = Result(title=title)

    # -- prep --------------------------------------------------------------
    sections = script_prep.parse_script(
        script_text, settings.generation.max_chars_per_chunk)
    result.sections = len(sections)
    result.chunks = sum(len(s.chunks) for s in sections)
    log(f"{result.sections} sections, {result.chunks} chunks")

    generator = Generator(settings, log=log)
    checker = ReadChecker(settings, log=log)

    # -- generate + read-check --------------------------------------------
    rendered: list[Path] = []
    for section in sections:
        for chunk in section.chunks:
            log(f"chunk {chunk.index+1}/{result.chunks}: {chunk.text[:56]}")
            verdict, path = render_with_retries(
                generator, checker, chunk, voice_ref, work,
                section.is_chapter, log=log)
            if chunk.attempts > 1:
                result.rerolled += 1
            if not verdict.passed:
                result.unresolved.append(chunk.index)
            rendered.append(path)
    generator.unload()          # free VRAM before the ASR and mastering passes

    if result.unresolved:
        log(f"{len(result.unresolved)} chunk(s) never passed the read-check. "
            f"They are in the file and they need an ear: {result.unresolved}")

    # -- stitch ------------------------------------------------------------
    stitched = join(rendered, work / "stitched.wav",
                    settings.generation.work_sr, settings.master.edge_fade_ms)

    # -- master ------------------------------------------------------------
    mastered = master(stitched, script_text, work / "mastered.wav",
                      settings.master, log=log)

    # -- deliver -----------------------------------------------------------
    final = project_dir / f"{title} (final).mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mastered),
                    "-c:a", "libmp3lame", "-b:a", "320k",
                    "-ar", str(settings.generation.work_sr), "-ac", "1",
                    str(final)], check=True)
    result.final_path = final

    import soundfile as sf
    info = sf.info(mastered)
    result.duration_s = info.frames / info.samplerate

    # -- post-delivery checks, on the delivered file -----------------------
    if settings.orphans.enabled:
        result.orphans = _sweep_orphans(final, settings, log)
    result.pronunciation = _check_pronunciation(final, log)

    # -- rule 7: prove the destructive edits did not eat a word ------------
    log("Transcribing the delivered file to confirm no words were lost ...")
    spoken = checker.transcribe(final)
    from .readcheck import normalize, missing_words
    lost = missing_words(normalize(script_prep.spell_numerals(script_text)),
                         normalize(spoken))
    if lost:
        result.notes.append(f"TRANSCRIPT SHORT {len(lost)} WORD(S): {lost[:12]}")
        log(f"  MISSING FROM THE DELIVERED FILE: {lost[:12]}")
    else:
        log("  every script word present in the delivered read")

    return result


def _sweep_orphans(final: Path, settings, log) -> list[dict]:
    """
    Short bursts stranded in the gaps — the defect class that cost six repairs.

    Runs on the delivered MP3 on purpose: the master is what strands them, and a
    sweep of the stitch would come back clean while the shipped file is not.
    """
    script = Path(__file__).with_name("orphans.py")
    if not script.exists():
        log("  orphans.py not present — skipping (this is NOT a pass)")
        return []
    proc = subprocess.run(["python3", str(script), "--audio", str(final)],
                          capture_output=True, text=True)
    for line in proc.stdout.splitlines():
        log("  " + line)
    return [{"raw": proc.stdout, "found": proc.returncode == 1}]


def _check_pronunciation(final: Path, log) -> list[dict]:
    script = Path(__file__).with_name("pronounce_check.py")
    if not script.exists():
        return []
    proc = subprocess.run(["python3", str(script), "--audio", str(final)],
                          capture_output=True, text=True)
    for line in proc.stdout.splitlines():
        log("  " + line)
    return [{"raw": proc.stdout, "flagged": proc.returncode == 1}]


def excerpt(final: Path, centre_s: float, out: Path, span: float = 6.0) -> Path:
    """
    Six seconds around a defect, cut from the MASTERED file.

    His rule, and it is faster for both sides: mastering a twelve-minute file makes
    him listen to twelve minutes to judge one edit. It has to come from the master
    whenever mastering could be what caused the defect — which, for beats, gaps and
    stranded fragments, it usually is.
    """
    start = max(0.0, centre_s - span / 2)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(start),
                    "-t", str(span), "-i", str(final),
                    "-c:a", "libmp3lame", "-b:a", "320k", str(out)], check=True)
    return out
