"""
Backend for the VO Studio interface.

FastAPI rather than Gradio. Gradio was the fastest way to get something on screen
and the wrong way to keep it there: its DOM is its own, so the layout is a stack
of form rows however it is styled. That is what made it look a decade old. Here
the front-end is plain HTML/CSS/JS and this file is only an API — the pipeline
underneath is unchanged.

Everything is bound to 127.0.0.1 and rendered inside a native window by
desktop.py. Nothing is reachable from the network.
"""
import asyncio
import json
import os
import re
import time
import shutil
import tempfile
import threading
from dataclasses import asdict
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               StreamingResponse)

from vostudio import config, winfix

# Before pipeline, which pulls in torch and huggingface_hub. Patching after the
# hub has already cached its symlink-support answer is too late.
winfix.apply()

from vostudio import conversations, pipeline
from vostudio.assistant import run as agent_run, check_auth, start_login
from vostudio.voice_profile import VoiceProfile, apply_feedback

ROOT = Path(__file__).resolve().parent
UI = ROOT / "ui"

CHUNK = 1 << 20


_SAFE_PROFILE = re.compile(r"[^A-Za-z0-9 _-]")


def profile_name(asked: str = "", remember: bool = True) -> str:
    """
    THE profile. One name, resolved in one place.

    Claude used to take SETTINGS.active_profile ("default") while the panel
    sent whatever was typed in its box ("explaintory"). Two different profiles:
    Claude rendered takes into one folder and the panel played the other, and
    Claude's adjust_voice moved dials the sliders were not showing. Every
    symptom of "it is giving me the old one" came from that split.

    A name that arrives from the UI wins and is remembered, so switching
    profiles in the box switches it for the agent too.
    """
    # The name becomes a folder under VOICES_DIR, so it is a path fragment and
    # has to be treated as one. "../../../tmp/x" was accepted, remembered and
    # saved -- relocating every later take and lock outside the app's folder
    # with no way back except editing settings.json by hand.
    asked = _SAFE_PROFILE.sub("", (asked or "").strip())[:60].strip()
    if asked and remember and asked != SETTINGS.active_profile:
        SETTINGS.active_profile = asked
        SETTINGS.save()
    if asked and not remember:
        return asked
    if not SETTINGS.active_profile:
        SETTINGS.active_profile = "explaintory"
    return SETTINGS.active_profile


def upload_limit() -> int:
    """Settings -> App -> Max upload, in bytes. Read per request, not captured at
    import, so raising it takes effect without restarting the app."""
    return int(SETTINGS.app.max_upload_gb * 1024 ** 3)


async def save_upload(file: UploadFile, dest: Path, limit: int | None = None) -> int:
    """
    Stream an upload to disk, refusing anything over the limit.

    Chunked, not `dest.write_bytes(await file.read())`: read() materialises the
    whole upload in memory first, so a 1 GB file costs 1 GB of RAM on top of the
    model already loaded on the GPU box.
    """
    limit = limit or upload_limit()
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with open(dest, "wb") as out:
        while chunk := await file.read(CHUNK):
            total += len(chunk)
            if total > limit:
                out.close()
                dest.unlink(missing_ok=True)
                raise ValueError(f"{file.filename} is over the "
                                 f"{limit / 1024**3:.1f} GB limit — raise it in Settings")
            out.write(chunk)
    return total


# ---------------------------------------------------------------- progress
# A take is one generate() call with nothing to report from inside it, so a
# sweeping bar was all there was. But the two things that make it slow ARE
# measurable from outside: the first run downloads ~1 GB of weights (watch the
# cache directory grow) and every run after that takes about as long as the
# last one did (remember it). Between them there is a real status bar.
JOB: dict = {"phase": "idle", "started": 0.0, "chars": 0}

# Written on the first successful take and used to predict the next. Seeded
# from a 3050 so the very first bar is not wildly wrong; it corrects itself
# after one take on your own machine.
PACE: dict = {"secs_per_char": 0.045}


def _dir_mb(path: Path) -> float:
    try:
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6
    except OSError:
        return 0.0


def friendly(exc: BaseException) -> str:
    """Turn the errors we have actually hit into something actionable."""
    text = f"{type(exc).__name__}: {exc}"
    if "1314" in text or "required privilege" in text.lower():
        return (text + "\n\nWindows blocked a symlink while unpacking the model "
                "cache. The app now copies instead, so close and reopen it and the "
                "download resumes. If it happens again, turn on Settings > System > "
                "For developers > Developer Mode, which allows symlinks without "
                "admin, and delete runtime\\models to start the cache clean.")
    if "CUDA out of memory" in text:
        return (text + "\n\n6 GB is tight for this model. Settings > Voice & "
                "generation > Max characters per chunk: drop 300 to 200.")
    return text


SETTINGS = config.Settings.load()
config.ensure_dirs()

app = FastAPI(title="ExplainTory VO Studio")
STATE: dict = {"voice": None, "render": None, "log": []}


@app.get("/api/job")
def job_state():
    """Polled while a take runs. Cheap enough at 1 Hz; the cache walk is the
    only real cost and it only happens while weights are still arriving."""
    phase = JOB["phase"]
    elapsed = (time.perf_counter() - JOB["started"]) if JOB["started"] else 0.0
    out = {"phase": phase, "elapsed": round(elapsed, 1)}

    if phase == "loading":
        cache = Path(os.environ.get("HF_HOME", "")) if os.environ.get("HF_HOME") else None
        got = _dir_mb(cache) if cache and cache.exists() else 0.0
        out["mb"] = round(got, 1)
        # Turbo and Standard are both a little over a gigabyte. Approximate, and
        # labelled as approximate rather than dressed up as a real total.
        out["mb_total"] = 1150
        out["label"] = (f"downloading the voice model — {got:.0f} MB of ~1.1 GB"
                        if got < 1100 else "loading the model onto the GPU")
    elif phase == "generating":
        expect = max(2.0, JOB["chars"] * PACE["secs_per_char"])
        out["expect"] = round(expect, 1)
        left = max(0.0, expect - elapsed)
        out["label"] = (f"generating — about {left:.0f}s left" if left > 1
                        else "generating — almost there")
    return out


# ------------------------------------------------------------------ shell
@app.get("/", response_class=HTMLResponse)
def index():
    return (f"<!doctype html><html><head><meta charset=utf-8>"
            f"<title>ExplainTory VO Studio</title>"
            f"<link rel=icon href='/ui/icon.png'>"
            f"<style>{(UI / 'app.css').read_text(encoding='utf-8')}</style></head><body>"
            f"{(UI / 'index.html').read_text(encoding='utf-8')}"
            f"<script>{(UI / 'app.js').read_text(encoding='utf-8')}</script></body></html>")


@app.get("/ui/icon.png")
def icon():
    return FileResponse(ROOT / "assets" / "icon.png")


@app.get("/api/hardware")
def hardware():
    try:
        import torch
        if torch.cuda.is_available():
            p = torch.cuda.get_device_properties(0)
            return {"gpu": True,
                    "label": f"{p.name} · {p.total_memory / 1024**3:.0f} GB"}
        return {"gpu": False, "label": "CPU only — ~10× realtime"}
    except Exception:
        return {"gpu": False, "label": "PyTorch not installed"}


# ------------------------------------------------------------------ voice
@app.post("/api/voice")
async def set_voice(file: UploadFile = File(...)):
    dest = config.VOICES_DIR / "reference" / Path(file.filename or "voice").name
    try:
        await save_upload(file, dest)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, 413)

    wav = dest.with_suffix(".probe.wav")
    import subprocess
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(dest),
                    "-ar", "24000", "-ac", "1", str(wav)], check=True)
    a, sr = sf.read(wav)
    dur = len(a) / sr
    peak = float(20 * np.log10(np.abs(a).max() + 1e-12))
    STATE["voice"] = str(dest)
    STATE["voice_duration"] = round(dur, 1)
    STATE["voice_peak"] = round(peak, 1)

    # Say what is wrong with the clip now, not after a bad render.
    warning = ""
    if dur < 5:
        warning = f"{dur:.1f}s is short — the clone has little to work from. 8–12s is better."
    elif dur > 25:
        warning = f"{dur:.1f}s is long — trim to 8–12s of continuous speech."
    elif peak > -0.5:
        warning = "Peaks near full scale — a clipped reference clones the clipping."
    return {"name": file.filename, "duration": dur, "peak": peak, "warning": warning}


@app.get("/api/voice/audio")
def voice_audio():
    return FileResponse(STATE["voice"]) if STATE.get("voice") else JSONResponse({}, 404)


@app.get("/api/voice/status")
def voice_status():
    """Is there a reference loaded, and what does it look like? The chat asks
    this on open so it can say "ready" or "drop me a clip" instead of guessing."""
    path = STATE.get("voice")
    if not path or not Path(path).exists():
        return {"loaded": False}
    return {"loaded": True, "name": Path(path).name,
            "duration": STATE.get("voice_duration"), "peak": STATE.get("voice_peak"),
            "profile": profile_name()}


@app.post("/api/script/analyse")
def analyse_script(payload: dict):
    """
    What the script becomes, before an hour is spent on it.

    Same parser the render uses -- not an approximation of it. A count that
    disagrees with what actually gets rendered would be worse than no count,
    because it would be believed.
    """
    from vostudio.script_prep import parse_script

    raw = (payload.get("script") or "").strip()
    if not raw:
        return {"error": "Nothing to read."}

    sections = parse_script(raw, SETTINGS.generation.max_chars_per_chunk)
    headers = [s.title for s in sections if s.is_chapter]
    chunks = sum(len(s.chunks) for s in sections)
    words = len(raw.split())

    # ~150 wpm is the measured pace of the delivered reads, and the render
    # estimate comes from the same per-character pace the take bar learned on
    # this machine -- so it gets better after the first take rather than being
    # a number from a docs page.
    speech_s = words / 150 * 60
    render_s = len(raw) * PACE["secs_per_char"]
    return {"words": words, "sections": len(sections), "chunks": chunks,
            "headers": headers, "speech_seconds": round(speech_s),
            "render_seconds": round(render_s),
            "profile": SETTINGS.active_profile or "explaintory"}


# ----------------------------------------------------------------- render
@app.post("/api/render")
async def render(payload: dict):
    script, title = payload.get("script", ""), payload.get("title") or "Untitled"
    if not STATE.get("voice"):
        return StreamingResponse(iter(["No voice reference — set one on the Voice tab.\n"]),
                                 media_type="text/plain")

    safe = "".join(c for c in title if c.isalnum() or c in " -_").strip() or "Untitled"
    project = config.PROJECTS_DIR / safe
    project.mkdir(parents=True, exist_ok=True)
    STATE["render"] = None
    lines: list[str] = []

    def work():
        try:
            STATE["render"] = pipeline.run(script, safe, Path(STATE["voice"]),
                                           SETTINGS, project, log=lines.append)
        except Exception as exc:
            lines.append("FAILED: " + friendly(exc))
            STATE["render"] = "error"

    threading.Thread(target=work, daemon=True).start()

    async def stream():
        sent = 0
        while STATE["render"] is None or sent < len(lines):
            while sent < len(lines):
                yield lines[sent] + "\n"
                sent += 1
            if STATE["render"] is not None and sent >= len(lines):
                break
            await asyncio.sleep(0.3)

    return StreamingResponse(stream(), media_type="text/plain")


@app.get("/api/render/result")
def render_result():
    r = STATE.get("render")
    if not r or r == "error" or getattr(r, "final_path", None) is None:
        return {"path": None}
    return {"path": str(r.final_path), "duration": r.duration_s,
            "warn": bool(r.unresolved or r.notes)}


@app.get("/api/render/audio")
def render_audio():
    r = STATE.get("render")
    if not r or r == "error":
        return JSONResponse({}, 404)
    return FileResponse(r.final_path)


# -------------------------------------------------------------- voice lab
@app.get("/api/profile")
def get_profile(name: str = ""):
    """A GET that switched the app's active profile and wrote settings.json was
    a mistake waiting for a typo in the profile box. Reading never remembers;
    the switch happens when something is actually rendered or locked."""
    return asdict(VoiceProfile.load(config.VOICES_DIR, profile_name(name, remember=False)))


@app.get("/api/lab/text")
def lab_text():
    """Whatever line is currently being tuned against."""
    return {"text": STATE.get("lab_text") or SAMPLE, "default": SAMPLE}


@app.post("/api/lab/sample")
def lab_sample(payload: dict):
    name = profile_name(payload.get("name"))
    if not STATE.get("voice"):
        return {"error": "Set a reference clip on the Voice tab first."}

    # A line you paste sticks, so every take after it is the same words at
    # different settings. Re-rendering a different sentence each round means
    # comparing two things at once and learning nothing from either.
    if payload.get("text"):
        STATE["lab_text"] = payload["text"].strip()
    text = STATE.get("lab_text") or SAMPLE

    # A TAKE READS EVERYTHING YOU GAVE IT.
    #
    # generate() stops at max_new_tokens=1000 -- roughly 40 s of speech -- by
    # truncating rather than raising, so a single call cannot hold a long
    # passage. That used to mean the take was CUT to the first chunk: hand it
    # thirty seconds of script and hear six, which is not a sample of anything.
    #
    # So a long text is chunked at sentence boundaries with the same splitter
    # the pipeline uses, every chunk is generated, and they are joined. A take
    # is now as long as the words you gave it.
    from vostudio.script_prep import chunk_text
    limit = SETTINGS.generation.max_chars_per_chunk
    pieces = chunk_text(text, limit) if len(text) > limit else [text]
    note = ""

    started = time.perf_counter()
    prof = VoiceProfile.load(config.VOICES_DIR, name)
    prof.reference = STATE["voice"]

    from vostudio.generate import Generator
    gen = Generator(SETTINGS)
    # A FILE PER TAKE, not one sample.wav rewritten every round.
    #
    # Every take used to overwrite the same path, and every player in the
    # transcript pointed at it. So an old bubble either replayed the newest
    # take, or -- worse -- streamed a file that changed length underneath it
    # and came out as buzz. Keeping the takes separate is also the point of
    # having a history: round 4 is only comparable with round 6 if round 4 is
    # still there to play.
    takes = config.VOICES_DIR / name / "takes"
    takes.mkdir(parents=True, exist_ok=True)
    # Numbered from what is ON DISK, not from a counter that resets with the
    # process. After a restart the old counter started at 1 again and the next
    # take destroyed take-0001 -- the comparison history this folder exists to
    # keep -- while the panel still played the highest-numbered old file.
    existing = [int(f.stem.split("-")[1]) for f in takes.glob("take-*.wav")
                if f.stem.split("-")[-1].isdigit()]
    out = takes / f"take-{(max(existing) if existing else 0) + 1:04d}.wav"
    JOB.update(phase="loading", started=time.perf_counter(), chars=len(text))
    try:
        # Loading is separated from generating so the bar can say which one it
        # is waiting on -- they fail differently and they feel different, and
        # "downloading 1 GB" reads very differently from "hung".
        gen.load()
        JOB.update(phase="generating", started=time.perf_counter())
        if len(pieces) == 1:
            gen.generate_chunk(text, STATE["voice"], out,
                               exaggeration=prof.exaggeration,
                               temperature=prof.temperature,
                               cfg_weight=prof.cfg_weight, speed=prof.speed)
        else:
            # Joined with a short pause at the sentence boundary the split
            # happened on, and a 3 ms fade at each edge. Butt-joining two
            # generated pieces clicks audibly -- it is the same reason the
            # master fades every splice.
            parts, rate = [], SETTINGS.generation.work_sr
            for i, piece in enumerate(pieces):
                tmp = out.with_name(f"{out.stem}-part{i:02d}.wav")
                gen.generate_chunk(piece, STATE["voice"], tmp,
                                   exaggeration=prof.exaggeration,
                                   temperature=prof.temperature,
                                   cfg_weight=prof.cfg_weight, speed=prof.speed)
                audio, rate = sf.read(tmp)
                fade = max(1, int(rate * SETTINGS.master.edge_fade_ms / 1000))
                audio[:fade] *= np.linspace(0, 1, fade)
                audio[-fade:] *= np.linspace(1, 0, fade)
                parts.append(audio)
                if i < len(pieces) - 1:
                    parts.append(np.zeros(int(rate * 0.18)))
                tmp.unlink(missing_ok=True)
            sf.write(out, np.concatenate(parts), rate, subtype="PCM_24")
            note = f"Read all {len(text)} characters, in {len(pieces)} passes."
    except Exception as exc:
        JOB.update(phase="idle", started=0.0)
        return {"error": friendly(exc)}
    finally:
        gen.unload()
    # 16-bit for the browser. generate_chunk writes PCM_24 because that is what
    # the pipeline carries, and a listening copy has no use for the extra bits
    # -- while WebView2's decoder is one more thing that could be making the
    # noise. Cheap to rule out.
    try:
        audio, rate = sf.read(out)
        sf.write(out, audio, rate, subtype="PCM_16")
    except Exception:
        pass

    prof.save(config.VOICES_DIR)
    took = time.perf_counter() - started
    # Learn this machine's pace from the generate phase only -- folding a
    # one-off 1 GB download into the average would poison every later estimate.
    gen_secs = time.perf_counter() - JOB["started"]
    if JOB["phase"] == "generating" and len(text) > 20:
        PACE["secs_per_char"] = max(0.005, gen_secs / len(text))
    JOB.update(phase="idle", started=0.0)
    return {"profile": asdict(prof), "text": text, "audio": out.name,
            "seconds": round(took, 1), "note": note}


# The line the voice reads while you tune it. Two sentences with a comma, a
# date and a proper noun, because those are the things that go wrong -- a
# neutral "hello world" tells you nothing about how it handles a real script.
SAMPLE = ("The most spectacular story in this video is the one nobody can prove. "
          "In 1798, a French army landed in Egypt to cut England off from India.")


@app.get("/api/lab/latest")
def lab_latest(name: str = ""):
    """The newest take, for the panel — so the last thing rendered is to hand
    instead of scrolled away up the transcript."""
    name = profile_name(name, remember=False)
    folder = config.VOICES_DIR / name / "takes"
    takes = sorted(folder.glob("take-*.wav")) if folder.exists() else []
    return {"name": name, "file": takes[-1].name if takes else ""}


@app.get("/api/lab/audio")
def lab_audio(name: str = "", file: str = ""):
    """One take, by name. `file` is validated rather than trusted -- it arrives
    from the page, and a page is not where path rules belong."""
    name = profile_name(name, remember=False)
    folder = (config.VOICES_DIR / name / "takes").resolve()
    if file:
        try:
            p = (folder / Path(file).name).resolve()
            p.relative_to(folder)
        except (ValueError, OSError):
            return JSONResponse({}, 404)
    else:
        takes = sorted(folder.glob("take-*.wav")) if folder.exists() else []
        p = takes[-1] if takes else config.VOICES_DIR / name / "sample.wav"
    return FileResponse(p) if p.exists() else JSONResponse({}, 404)


@app.post("/api/lab/feedback")
def lab_feedback(payload: dict):
    name = profile_name(payload.get("name"))
    prof = VoiceProfile.load(config.VOICES_DIR, name)
    prof, changes = apply_feedback(prof, payload.get("feedback", ""))
    prof.save(config.VOICES_DIR)
    return {"profile": asdict(prof), "changes": changes}


@app.post("/api/lab/lock")
def lab_lock(payload: dict):
    name = profile_name(payload.get("name"))
    prof = VoiceProfile.load(config.VOICES_DIR, name)
    prof.save(config.VOICES_DIR)
    SETTINGS.active_profile = name
    # EVERY dial the render reads, not three of five. speed and
    # repetition_penalty were tuned in the lab and then dropped on the floor
    # here, so the take you approved and the file you shipped were not the
    # same voice.
    SETTINGS.generation.exaggeration = prof.exaggeration
    SETTINGS.generation.cfg_weight = prof.cfg_weight
    SETTINGS.generation.temperature = prof.temperature
    SETTINGS.generation.speed = prof.speed
    SETTINGS.generation.repetition_penalty = prof.repetition_penalty
    SETTINGS.save()
    return {"message": f"Locked · {prof.summary()}"}


# What each dial may be set to from the Tune panel. Same bounds the sliders
# draw, enforced here as well -- a client is not where limits live.
PARAM_RANGE = {"exaggeration": (0.2, 0.9), "cfg_weight": (0.2, 0.9),
               "temperature": (0.4, 1.1), "speed": (0.85, 1.25)}


@app.post("/api/lab/params")
def lab_params(payload: dict):
    """Set a dial by hand. The feedback loop is the main way in, but sometimes
    you already know it is the speed and want to move it 0.02 yourself."""
    name = profile_name(payload.get("name"))
    prof = VoiceProfile.load(config.VOICES_DIR, name)
    for key, value in (payload.get("values") or {}).items():
        if key not in PARAM_RANGE:
            continue
        lo, hi = PARAM_RANGE[key]
        setattr(prof, key, max(lo, min(hi, float(value))))
    prof.save(config.VOICES_DIR)
    return {"profile": asdict(prof)}


@app.post("/api/lab/revert")
def lab_revert(payload: dict):
    name = profile_name(payload.get("name"))
    prof = VoiceProfile.load(config.VOICES_DIR, name)
    if not prof.history:
        return {"profile": asdict(prof), "message": "Nothing to undo."}
    prof.history.pop()
    fresh = VoiceProfile(name=name, reference=prof.reference)
    for r in prof.history:
        fresh, _ = apply_feedback(fresh, r["feedback"])
    fresh.save(config.VOICES_DIR)
    return {"profile": asdict(fresh), "message": "Undid one round."}


# ---------------------------------------------------------------- settings
def _schema(s: config.Settings):
    """Each row carries the failure that set it — a settings screen that hides
    the reason invites someone to undo it."""
    g, r, m, o, e = s.generation, s.readcheck, s.master, s.orphans, s.eleven
    return [
        {"key": "generation", "title": "Model", "items": [
            {"key": "variant", "name": "Chatterbox model", "type": "choice",
             "value": g.variant, "options": ["standard", "turbo"],
             "why": "Turbo is faster, and it is NOT the same model with the same "
                    "dials — it reads neutrally at exaggeration 0.0 and cfg_weight "
                    "0.0 where Standard reads neutrally at 0.5. Switching models "
                    "means re-tuning the voice in the Tune step, not carrying the "
                    "numbers across."},
        ]},
        {"key": "generation", "title": "Voice & generation", "items": [
            {"key": "exaggeration", "name": "Exaggeration", "type": "number",
             "min": .2, "max": .9, "step": .01, "dp": 2, "value": g.exaggeration,
             "why": "0.5 is a neutral read. Above ~0.7 it starts acting."},
            {"key": "cfg_weight", "name": "Reference adherence", "type": "number",
             "min": .2, "max": .9, "step": .01, "dp": 2, "value": g.cfg_weight,
             "why": "Higher tracks the reference's phrasing — the lever for false pauses."},
            {"key": "temperature", "name": "Temperature", "type": "number",
             "min": .4, "max": 1.1, "step": .01, "dp": 2, "value": g.temperature,
             "why": "Variation between takes. Lower is steadier, higher less mechanical."},
            {"key": "repetition_penalty", "name": "Repetition penalty", "type": "number",
             "min": 1, "max": 2, "step": .05, "dp": 2, "value": g.repetition_penalty,
             "why": "Raise if words stutter or repeat."},
            {"key": "max_chars_per_chunk", "name": "Max characters per chunk", "type": "number",
             "min": 120, "max": 400, "step": 10, "dp": 0, "value": g.max_chars_per_chunk,
             "why": "generate() truncates silently past ~40 s of speech. Lower this on out-of-memory."},
            {"key": "use_fp16", "name": "fp16", "type": "bool", "value": g.use_fp16,
             "why": "Halves VRAM. Leave on for 6–8 GB cards."},
        ]},
        {"key": "readcheck", "title": "Read-check", "items": [
            {"key": "wer_threshold", "name": "WER threshold", "type": "number",
             "min": .05, "max": .5, "step": .01, "dp": 2, "value": r.wer_threshold,
             "why": "0.05 sat BELOW the 0.047 median measured on known-good audio, so good takes failed and were re-rendered worse."},
            {"key": "max_redos", "name": "Re-rolls before giving up", "type": "number",
             "min": 0, "max": 5, "step": 1, "dp": 0, "value": r.max_redos,
             "why": "Re-rolling is free on your own GPU. This is the whole reason to run locally."},
            {"key": "chapter_max_words", "name": "Chapter header max words", "type": "number",
             "min": 1, "max": 5, "step": 1, "dp": 0, "value": r.chapter_max_words,
             "why": "WER is quantised to 0 / 0.5 / 1.0 on two words, so it can only ever fire falsely."},
            {"key": "model", "name": "ASR model", "type": "choice", "value": r.model,
             "options": ["distil-large-v3", "large-v3", "medium.en", "small.en"],
             "why": "Always float32 — int8 hallucinated dropped words."},
        ]},
        {"key": "master", "title": "Mastering", "items": [
            {"key": "target_lufs", "name": "Target loudness", "type": "number",
             "min": -24, "max": -8, "step": .5, "dp": 1, "unit": " LUFS", "value": m.target_lufs,
             "why": "−14 LUFS is the YouTube norm."},
            {"key": "target_true_peak", "name": "True peak ceiling", "type": "number",
             "min": -3, "max": -.1, "step": .1, "dp": 1, "unit": " dBTP", "value": m.target_true_peak,
             "why": "Gain only, never limited. The read is the product."},
            {"key": "edge_fade_ms", "name": "Edge fade", "type": "number",
             "min": 0, "max": 20, "step": .5, "dp": 1, "unit": " ms", "value": m.edge_fade_ms,
             "why": "Section joins clicked audibly until this went in."},
            {"key": "comma_pad_ms", "name": "Comma pause target", "type": "number",
             "min": 0, "max": 400, "step": 10, "dp": 0, "unit": " ms", "value": m.comma_pad_ms,
             "why": "Applied only where a scripted comma actually lands, never to every gap that looks like a pause."},
            {"key": "runthrough_threshold_s", "name": "Run-through threshold", "type": "number",
             "min": 0, "max": .2, "step": .005, "dp": 3, "unit": " s", "value": m.runthrough_threshold_s,
             "why": "A comma the voice read through faster than this is LEFT ALONE. Ignoring that is why one defect survived five upstream fixes."},
            {"key": "chapter_gap_s", "name": "Chapter gap", "type": "number",
             "min": 0, "max": 1, "step": .05, "dp": 2, "unit": " s", "value": m.chapter_gap_s,
             "why": "Silence around a chapter announcement."},
        ]},
        {"key": "generation", "title": "Engine", "items": [
            {"key": "engine", "name": "Engine", "type": "choice",
             "value": g.engine, "options": ["chatterbox", "elevenlabs"],
             "why": "Chatterbox runs on your GPU for nothing and clones the "
                    "reference clip. ElevenLabs costs about $0.18 per 1000 "
                    "characters and reads in one of ITS voices — the reference "
                    "clip is not used. Everything after generation — read-check, "
                    "orphan sweep, comma work, mastering — is identical."},
        ]},
        {"key": "eleven", "title": "ElevenLabs", "items": [
            {"key": "voice_id", "name": "Voice ID", "type": "text", "value": e.voice_id,
             "why": "Take it from the account's voice list rather than typing it "
                    "— a wrong id is a 400 several seconds into a render. Ask in "
                    "the chat and it will list them."},
            {"key": "api_key", "name": "API key", "type": "text", "value": e.api_key,
             "why": "ELEVENLABS_API_KEY in the environment wins over this. Stored "
                    "here it sits in plain text in settings.json — fine on your "
                    "own machine, wrong for anything shared."},
            {"key": "stability", "name": "Stability", "type": "number",
             "min": 0, "max": 1, "step": .05, "dp": 2, "value": e.stability,
             "why": "Higher is steadier, lower is more emotional. Narration sits "
                    "0.55-0.65; under 0.30 it drifts within one episode."},
            {"key": "similarity_boost", "name": "Similarity", "type": "number",
             "min": 0, "max": 1, "step": .05, "dp": 2, "value": e.similarity_boost,
             "why": "How tightly it holds the source voice. 0.85 for authority "
                    "reads; below 0.65 the voice wanders."},
            {"key": "style", "name": "Style", "type": "number",
             "min": 0, "max": 1, "step": .05, "dp": 2, "value": e.style,
             "why": "Injected expressiveness. Documentary and deadpan want "
                    "0.00-0.10; above 0.50 it turns melodramatic."},
            {"key": "speaker_boost", "name": "Speaker boost", "type": "bool",
             "value": e.speaker_boost,
             "why": "Helps the voice stay consistent across a long render. "
                    "Leave it on."},
        ]},
        {"key": "app", "title": "App", "items": [
            {"key": "max_upload_gb", "name": "Max upload size", "type": "number",
             "min": .1, "max": 8, "step": .1, "dp": 1, "unit": " GB", "value": s.app.max_upload_gb,
             "why": "Applies to the voice reference and to Assistant attachments. "
                    "Uploads stream to disk in 1 MB chunks, so a big file does not "
                    "cost its own size in RAM — the ceiling is disk, not memory."},
        ]},
        {"key": "orphans", "title": "Quality gates", "items": [
            {"key": "enabled", "name": "Orphan-fragment sweep", "type": "bool", "value": o.enabled,
             "why": "Finds short bursts stranded in the gaps. Runs on the DELIVERED file, because the master is what strands them."},
            {"key": "min_gap_s", "name": "Fence width", "type": "number",
             "min": .02, "max": .2, "step": .005, "dp": 3, "unit": " s", "value": o.min_gap_s,
             "why": "Silence required on BOTH sides before a burst counts as stranded."},
            {"key": "max_island_s", "name": "Max fragment", "type": "number",
             "min": .05, "max": .5, "step": .01, "dp": 2, "unit": " s", "value": o.max_island_s,
             "why": "Longer than this is a line, not a fragment — the ceiling that stops it eating real words."},
        ]},
    ]


@app.get("/api/settings")
def get_settings():
    return _schema(SETTINGS)


@app.post("/api/settings")
def put_settings(payload: dict):
    """
    Validate everything, THEN apply.

    It used to coerce and assign field by field, so a value that failed halfway
    through left the earlier ones live in the running app while the request
    500'd and the file on disk kept the old numbers. You saw "save failed",
    used the new values for the next render, and lost them on restart. It also
    accepted anything: exaggeration 99, or max_chars_per_chunk 0, which is
    fatal later inside parse_script.
    """
    bounds = {f"{g['key']}.{it['key']}": it for g in _schema(SETTINGS)
              for it in g["items"]}
    staged, rejected = [], []

    for path, value in (payload.get("values") or {}).items():
        if "." not in path:
            rejected.append(f"{path}: not a settings key")
            continue
        group, key = path.split(".", 1)
        target = getattr(SETTINGS, group, None)
        if target is None or not hasattr(target, key):
            rejected.append(f"{path}: no such setting")
            continue
        current = getattr(target, key)
        try:
            if isinstance(current, bool):
                new = bool(value)
            elif isinstance(current, str):
                new = str(value)
            else:
                new = type(current)(value)
        except (TypeError, ValueError):
            rejected.append(f"{path}: {value!r} is not a {type(current).__name__}")
            continue
        row = bounds.get(path) or {}
        if isinstance(new, (int, float)) and not isinstance(new, bool):
            lo, hi = row.get("min"), row.get("max")
            if lo is not None and hi is not None:
                clamped = type(current)(min(hi, max(lo, new)))
                if clamped != new:
                    rejected.append(f"{path}: {new} is outside {lo}–{hi}, kept {clamped}")
                new = clamped
        if row.get("options") and new not in row["options"]:
            rejected.append(f"{path}: {new!r} is not one of {row['options']}")
            continue
        staged.append((target, key, new))

    for target, key, new in staged:
        setattr(target, key, new)
    SETTINGS.save()

    msg = f"Saved to {config.SETTINGS_FILE}"
    if rejected:
        msg += " — except: " + "; ".join(rejected)
    return {"message": msg}


@app.post("/api/settings/reset")
def reset_settings(payload: dict = None):
    return _schema(config.Settings())


# --------------------------------------------------------------- assistant
@app.get("/api/auth")
def auth():
    s = check_auth()
    return {"ok": s.ok, "detail": s.detail, "can_login": s.can_login}


@app.post("/api/auth/login")
def auth_login(payload: dict = None):
    ok, message = start_login()
    return {"ok": ok, "message": message}


# ------------------------------------------------------------------ studio
class Studio:
    """
    The pipeline, as plain methods, so the agent's tools and the panel's
    buttons drive exactly the same code. Two paths to the same operation is
    how the two ends of an app start disagreeing about what is loaded.
    """

    def voice_status(self) -> dict:
        p = STATE.get("voice")
        if not p or not Path(p).exists():
            return {"loaded": False,
                    "hint": "No reference loaded. Ask Sapro to attach an audio "
                            "clip: 8-12 seconds of continuous speech, no music."}
        return {"loaded": True, "name": Path(p).name,
                "duration_s": STATE.get("voice_duration"),
                "peak_dbfs": STATE.get("voice_peak"),
                "profile": profile_name()}

    def set_voice(self, path: str) -> dict:
        src = Path(path)
        if not src.exists():
            return {"error": f"No file at {path}"}
        dest = config.VOICES_DIR / "reference" / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != dest.resolve():
            shutil.copyfile(src, dest)

        probe = dest.with_suffix(".probe.wav")
        import subprocess
        try:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(dest),
                            "-ar", "24000", "-ac", "1", str(probe)], check=True)
            audio, rate = sf.read(probe)
        except Exception as exc:
            return {"error": f"Could not read that as audio: {exc}"}

        dur = len(audio) / rate
        peak = float(20 * np.log10(np.abs(audio).max() + 1e-12))
        STATE["voice"] = str(dest)
        STATE["voice_duration"] = round(dur, 1)
        STATE["voice_peak"] = round(peak, 1)

        # Said now rather than after a bad render, because every one of these
        # produces a clone that is wrong in a way that is hard to name later.
        warn = ""
        if dur < 5:
            warn = "Short — the clone has little to work from. 8-12s is better."
        elif dur > 25:
            warn = "Long — trim to 8-12s of continuous speech."
        elif peak > -0.5:
            warn = "Peaks near full scale. A clipped reference clones the clipping."
        return {"loaded": True, "name": dest.name, "duration_s": round(dur, 1),
                "peak_dbfs": round(peak, 1), "warning": warn}

    def take(self, text: str = "") -> dict:
        payload = {"name": profile_name()}
        if text:
            payload["text"] = text
        out = lab_sample(payload)
        if out.get("error"):
            return out
        return {"rendered": True, "seconds_on_gpu": out.get("seconds"),
                "text_read": out.get("text"), "file": out.get("audio"),
                "note": out.get("note") or "",
                "settings": {k: out["profile"][k] for k in
                             ("exaggeration", "cfg_weight", "temperature", "speed")}}

    def tune(self, feedback: str) -> dict:
        out = lab_feedback({"name": profile_name(), "feedback": feedback})
        if not out.get("changes"):
            return {"changed": [], "note": "Nothing in that matched a known "
                    "adjustment. Say which way it is wrong — too fast, too flat, "
                    "false pauses — or set a dial directly."}
        return {"changed": out["changes"], "settings": out["profile"]}

    def set_param(self, key: str, value: float) -> dict:
        if key not in PARAM_RANGE:
            return {"error": f"Unknown dial {key}. One of: {', '.join(PARAM_RANGE)}"}
        out = lab_params({"name": profile_name(), "values": {key: value}})
        return {"set": key, "to": out["profile"][key]}

    def analyse(self, script: str) -> dict:
        return analyse_script({"script": script})

    def render(self, script: str, title: str = "") -> dict:
        """
        The expensive one. Runs to completion and returns the outcome plus the
        tail of the log, so the agent reports what actually happened rather
        than that it started something.
        """
        if not STATE.get("voice"):
            return {"error": "No voice reference loaded — nothing to read it in."}
        safe = "".join(c for c in (title or "Untitled")
                       if c.isalnum() or c in " -_").strip() or "Untitled"
        project = config.PROJECTS_DIR / safe
        project.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []
        JOB.update(phase="script", started=time.perf_counter(), chars=len(script))
        STATE["log"] = lines
        try:
            result = pipeline.run(script, safe, Path(STATE["voice"]),
                                  SETTINGS, project, log=lines.append)
        except Exception as exc:
            JOB.update(phase="idle", started=0.0)
            # Cleared, or /api/render/result keeps handing out the LAST render
            # that worked -- with its duration -- as though it were this one.
            STATE["render"] = None
            lines.append("FAILED: " + friendly(exc))
            return {"error": friendly(exc), "log_tail": lines[-12:]}
        JOB.update(phase="idle", started=0.0)
        STATE["render"] = result

        return {"path": str(result.final_path), "duration_s": result.duration_s,
                "needs_an_ear": bool(result.unresolved or result.notes),
                "unresolved": list(result.unresolved or [])[:8],
                "log_tail": lines[-12:]}

    def eleven_voices(self) -> dict:
        from vostudio import eleven
        try:
            return {"voices": eleven.list_voices(SETTINGS)}
        except Exception as exc:
            return {"error": str(exc)}

    def set_engine(self, engine: str, voice_id: str = "") -> dict:
        engine = (engine or "").strip().lower()
        if engine not in ("chatterbox", "elevenlabs"):
            return {"error": "engine must be 'chatterbox' or 'elevenlabs'"}
        if engine == "elevenlabs":
            from vostudio import eleven
            if not eleven.api_key(SETTINGS):
                return {"error": "No ElevenLabs API key. Set ELEVENLABS_API_KEY "
                                 "in the environment, or paste one into "
                                 "Settings > ElevenLabs."}
            if voice_id:
                SETTINGS.eleven.voice_id = voice_id
            if not SETTINGS.eleven.voice_id:
                return {"error": "No voice selected. Call list_elevenlabs_voices "
                                 "and pass one of its ids."}
        SETTINGS.generation.engine = engine
        SETTINGS.save()
        return {"engine": engine, "voice_id": SETTINGS.eleven.voice_id,
                "note": ("Local and free — the read-check and mastering are "
                         "unchanged." if engine == "chatterbox" else
                         "Costs about $0.18 per 1000 characters. The reference "
                         "clip is not used: ElevenLabs reads in the voice you "
                         "selected, not a clone of the clip.")}

    def render_log(self) -> dict:
        return {"log": (STATE.get("log") or ["Nothing rendered yet."])[-60:]}


STUDIO = Studio()


# Inside the app root on purpose. The assistant is sandboxed to that folder, so
# a file dropped anywhere else is a path it is not allowed to open — attaching it
# would look like it worked and then quietly fail at the Read.
ATTACH_DIR = ROOT / "attachments"

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
AUDIO_EXT = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus"}


def _describe(path: Path) -> dict:
    """What this file is, and what Claude can honestly do with it."""
    ext = path.suffix.lower()
    if ext in IMAGE_EXT:
        return {"kind": "image",
                "note": "an image — open it with the Read tool, you can see it"}
    if ext in AUDIO_EXT:
        detail = ""
        try:
            import subprocess
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries",
                 "format=duration:stream=sample_rate,channels",
                 "-of", "default=nw=1:nk=1", str(path)],
                capture_output=True, text=True, timeout=20)
            vals = [v for v in probe.stdout.split() if v]
            if vals:
                detail = " (" + ", ".join(vals[:3]) + ")"
        except Exception:
            pass
        return {"kind": "audio",
                # Two things stated plainly. What it is FOR, because a clip is
                # usually a reference to clone. And that you cannot hear it —
                # otherwise a model that cannot hear will describe it anyway.
                "note": (f"audio{detail} — if this is a voice to clone, pass this "
                         "path to use_voice_reference. You CANNOT listen to it; "
                         "measure it with ffprobe, soundfile, or the checks in "
                         "vostudio/ rather than describing how it sounds")}
    return {"kind": "file", "note": "a file — read it with the Read tool"}


@app.post("/api/assistant/attach")
async def assistant_attach(file: UploadFile = File(...)):
    ATTACH_DIR.mkdir(parents=True, exist_ok=True)
    raw = Path(file.filename or "file").name
    safe = "".join(c for c in raw if c.isalnum() or c in " .-_()").strip() or "file"
    dest = ATTACH_DIR / safe
    n = 1
    while dest.exists():                       # never clobber an earlier attachment
        dest = ATTACH_DIR / f"{Path(safe).stem}-{n}{Path(safe).suffix}"
        n += 1
    try:
        size = await save_upload(file, dest)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, 413)
    info = _describe(dest)
    return {"name": dest.name, "path": str(dest), "size": size, **info}


@app.get("/api/assistant/file")
def assistant_file(path: str):
    """Serve an attachment back so the chat can show it rather than name it."""
    try:
        p = Path(path).resolve()
        p.relative_to(ATTACH_DIR.resolve())    # same rule as everywhere else
        if p.is_file():
            return FileResponse(p)
    except (ValueError, OSError):
        pass
    return JSONResponse({}, 404)


@app.post("/api/assistant/detach")
def assistant_detach(payload: dict):
    """Removing a chip deletes the file — attachments are context, not a library."""
    try:
        p = Path(payload.get("path", "")).resolve()
        p.relative_to(ATTACH_DIR.resolve())    # refuse anything outside the folder
        p.unlink(missing_ok=True)
    except (ValueError, OSError):
        pass
    return {"ok": True}


# What the model picker offers. Availability follows your plan, not this list —
# an Opus-only plan limit is reported by the CLI, not predicted here.
MODELS = [
    {"id": "claude-sonnet-5", "label": "Sonnet 5",
     "note": "The default. Fast, and cheap enough on a subscription to keep going."},
    {"id": "claude-opus-5", "label": "Opus 5",
     "note": "Strongest. Use it for the changes you would not want to review twice."},
    {"id": "claude-haiku-4-5-20251001", "label": "Haiku 4.5",
     "note": "Quickest. Good for reading files and answering, not for edits."},
    {"id": "claude-fable-5", "label": "Fable 5",
     "note": "The writing model. For script and copy, not for editing code."},
]


@app.get("/api/assistant/prefs")
def assistant_prefs():
    return {"model": SETTINGS.app.assistant_model,
            "confirm_calls": SETTINGS.app.confirm_calls,
            "models": MODELS}


@app.post("/api/assistant/prefs")
def set_assistant_prefs(payload: dict):
    """Saved immediately. The composer is the place these are actually decided,
    so making you find Settings afterwards to keep the choice would be silly."""
    if "model" in payload and any(m["id"] == payload["model"] for m in MODELS):
        SETTINGS.app.assistant_model = payload["model"]
    if "confirm_calls" in payload:
        SETTINGS.app.confirm_calls = bool(payload["confirm_calls"])
    SETTINGS.save()
    return {"model": SETTINGS.app.assistant_model,
            "confirm_calls": SETTINGS.app.confirm_calls}


@app.post("/api/assistant/reset")
async def assistant_reset(payload: dict = None):
    """Kept for the old shape of the app: start a fresh conversation.

    Now the same thing the sidebar's New conversation button does, so a stale
    page cannot end up dropping the session without a file to show for it."""
    return await conversation_new()


# ─────────────────────────────────────────────────────────── conversations
# A LIST IN THE SIDEBAR, NOT A BUTTON IN A CORNER
#
# Every one of these returns the whole list and which one is open, because
# every one of them changes both, and a second request to find out what just
# happened is a race the sidebar would lose.

def _convo_view() -> dict:
    rec = conversations.active(ROOT)
    return {"active": rec["id"], "items": conversations.summaries(ROOT)}


@app.get("/api/conversations")
def conversation_list():
    return _convo_view()


@app.get("/api/conversations/open")
def conversation_open(id: str = ""):
    """Switch to one and hand back its transcript to replay.

    The agent session is NOT reconnected here — it is rebuilt on the next turn,
    resuming the session id stored with the conversation. Doing it now would
    spend a CLI start-up on a conversation you might only be glancing at.
    """
    rec = conversations.load(ROOT, id)
    if rec is None:
        return JSONResponse({"error": "That conversation is gone."}, 404)
    conversations.set_active(ROOT, rec["id"])
    return {**_convo_view(), "turns": rec.get("turns") or []}


@app.post("/api/conversations/new")
async def conversation_new(payload: dict = None):
    from vostudio.assistant import reset_session
    await reset_session()               # the old session belongs to the old file
    rec = conversations.create(ROOT)
    return {**_convo_view(), "turns": [], "opened": rec["id"]}


@app.post("/api/conversations/delete")
async def conversation_delete(payload: dict):
    """
    Delete one, and land somewhere real.

    Deleting the conversation you are IN cannot leave the app pointing at a
    file that no longer exists, so this always returns the transcript of
    whatever is open afterwards — the next most recent, or a fresh one.
    """
    cid = str((payload or {}).get("id") or "")
    was_active = conversations.active_id(ROOT) == cid
    if not conversations.delete(ROOT, cid):
        return JSONResponse({"error": "That conversation is already gone."}, 404)
    if was_active:
        from vostudio.assistant import reset_session
        await reset_session()
    rec = conversations.active(ROOT)     # picks the next one, or makes one
    return {**_convo_view(), "turns": rec.get("turns") or [], "opened": rec["id"]}


@app.post("/api/assistant")
async def assistant(payload: dict):
    """
    One turn, streamed as newline-delimited JSON.

    A turn can now render audio, which means it can take tens of minutes. A
    response that arrives only at the end is indistinguishable from a hang, so
    text and tool calls go out as they happen.

    It is also written down as it happens. The transcript is the conversation —
    if it only existed in the page, closing the window would lose the script,
    the takes and the notes about the read.
    """
    files = []
    for raw in payload.get("files") or []:
        try:
            p = Path(raw).resolve()
            p.relative_to(ATTACH_DIR.resolve())
            if p.is_file():
                files.append(p)
        except (ValueError, OSError):
            continue

    typed = payload.get("message", "")
    message = typed
    if files:
        listing = "\n".join(f"  {p}  — {_describe(p)['note']}" for p in files)
        message = (f"Sapro attached these files to this message:\n{listing}\n\n"
                   f"{typed}")

    mode = "default" if SETTINGS.app.confirm_calls else "acceptEdits"

    convo = conversations.active(ROOT)
    cid = convo["id"]
    conversations.add_turn(ROOT, cid, {
        "role": "me", "text": typed,
        # Names and kinds, not paths: the transcript is replayed in a page, and
        # a detached attachment is deleted from disk, so a link to one would
        # be a broken image in every reopened conversation.
        "files": [{"name": p.name, "kind": _describe(p)["kind"]} for p in files],
    })

    async def stream():
        said: list[str] = []
        takes: list[dict] = []
        try:
            async for event in agent_run(message, ROOT, conversation=cid,
                                         resume=convo.get("session_id"),
                                         permission_mode=mode,
                                         model=SETTINGS.app.assistant_model,
                                         studio=STUDIO):
                if event.get("type") == "session":
                    conversations.set_session(ROOT, cid, event["id"])
                    continue            # the page has no use for it
                if event.get("type") == "forget_session":
                    # The stored id would not resume. Dropped so the next turn
                    # does not try it again and fail the same way.
                    conversations.set_session(ROOT, cid, None)
                    continue
                if event.get("type") == "text":
                    said.append(event.get("text", ""))
                elif event.get("type") == "result":
                    took = _take_from(event.get("text", ""))
                    if took:
                        takes.append(took)
                elif event.get("type") == "error":
                    said.append(event.get("text", ""))
                yield json.dumps(event) + "\n"
        except Exception as exc:
            said.append(friendly(exc))
            yield json.dumps({"type": "error", "text": friendly(exc)}) + "\n"
        conversations.add_turn(ROOT, cid, {
            "role": "ai", "text": "".join(said), "takes": takes})
        yield json.dumps({"type": "done"}) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


_TAKE_FILE = re.compile(r"take-\d+\.wav$")


def _take_from(text: str) -> dict | None:
    """A tool result that rendered audio, or nothing.

    The same test the page makes, made here too, because the transcript has to
    replay the player and the page is not around to be asked later.
    """
    try:
        j = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(j, dict) or not _TAKE_FILE.search(str(j.get("file") or "")):
        return None
    return {"name": profile_name(), "file": j["file"], "seconds": j.get("seconds")}