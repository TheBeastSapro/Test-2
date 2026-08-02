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

from vostudio import pipeline
from vostudio.assistant import ask, check_auth, start_login
from vostudio.voice_profile import VoiceProfile, apply_feedback

ROOT = Path(__file__).resolve().parent
UI = ROOT / "ui"

CHUNK = 1 << 20


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
def get_profile(name: str = "default"):
    return asdict(VoiceProfile.load(config.VOICES_DIR, name))


@app.get("/api/lab/text")
def lab_text():
    """Whatever line is currently being tuned against."""
    return {"text": STATE.get("lab_text") or SAMPLE, "default": SAMPLE}


@app.post("/api/lab/sample")
def lab_sample(payload: dict):
    name = payload.get("name") or "default"
    if not STATE.get("voice"):
        return {"error": "Set a reference clip on the Voice tab first."}

    # A line you paste sticks, so every take after it is the same words at
    # different settings. Re-rendering a different sentence each round means
    # comparing two things at once and learning nothing from either.
    if payload.get("text"):
        STATE["lab_text"] = payload["text"].strip()
    text = STATE.get("lab_text") or SAMPLE

    # A take is ONE generate() call, and generate() stops at max_new_tokens=1000
    # -- about 40 s of speech -- by truncating, not by raising. Paste four
    # paragraphs here and the tail would vanish with nothing said about it, and
    # you would be tuning against a read you never heard the end of. So the
    # sample is cut to one chunk at a sentence boundary, using the same splitter
    # the pipeline uses, and the reply says what was actually read.
    from vostudio.script_prep import chunk_text
    limit = SETTINGS.generation.max_chars_per_chunk
    note = ""
    if len(text) > limit:
        pieces = chunk_text(text, limit)
        text = pieces[0] if pieces else text[:limit]
        note = (f"Read the first {len(text)} characters — a take is a single "
                f"pass and anything past roughly 40 seconds gets cut off. "
                f"Step 3 chunks a full script for you.")

    started = time.perf_counter()
    prof = VoiceProfile.load(config.VOICES_DIR, name)
    prof.reference = STATE["voice"]

    from vostudio.generate import Generator
    gen = Generator(SETTINGS)
    out = config.VOICES_DIR / name / "sample.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    JOB.update(phase="loading", started=time.perf_counter(), chars=len(text))
    try:
        # Loading is separated from generating so the bar can say which one it
        # is waiting on -- they fail differently and they feel different, and
        # "downloading 1 GB" reads very differently from "hung".
        gen.load()
        JOB.update(phase="generating", started=time.perf_counter())
        gen.generate_chunk(text, STATE["voice"], out,
                           exaggeration=prof.exaggeration,
                           temperature=prof.temperature,
                           cfg_weight=prof.cfg_weight, speed=prof.speed)
    except Exception as exc:
        JOB.update(phase="idle", started=0.0)
        return {"error": friendly(exc)}
    finally:
        gen.unload()
    prof.save(config.VOICES_DIR)
    took = time.perf_counter() - started
    # Learn this machine's pace from the generate phase only -- folding a
    # one-off 1 GB download into the average would poison every later estimate.
    gen_secs = time.perf_counter() - JOB["started"]
    if JOB["phase"] == "generating" and len(text) > 20:
        PACE["secs_per_char"] = max(0.005, gen_secs / len(text))
    JOB.update(phase="idle", started=0.0)
    return {"profile": asdict(prof), "text": text,
            "seconds": round(took, 1), "note": note}


# The line the voice reads while you tune it. Two sentences with a comma, a
# date and a proper noun, because those are the things that go wrong -- a
# neutral "hello world" tells you nothing about how it handles a real script.
SAMPLE = ("The most spectacular story in this video is the one nobody can prove. "
          "In 1798, a French army landed in Egypt to cut England off from India.")


@app.get("/api/lab/audio")
def lab_audio(name: str = "explaintory"):
    p = config.VOICES_DIR / name / "sample.wav"
    return FileResponse(p) if p.exists() else JSONResponse({}, 404)


@app.post("/api/lab/feedback")
def lab_feedback(payload: dict):
    name = payload.get("name") or "default"
    prof = VoiceProfile.load(config.VOICES_DIR, name)
    prof, changes = apply_feedback(prof, payload.get("feedback", ""))
    prof.save(config.VOICES_DIR)
    return {"profile": asdict(prof), "changes": changes}


@app.post("/api/lab/lock")
def lab_lock(payload: dict):
    name = payload.get("name") or "default"
    prof = VoiceProfile.load(config.VOICES_DIR, name)
    prof.save(config.VOICES_DIR)
    SETTINGS.active_profile = name
    SETTINGS.generation.exaggeration = prof.exaggeration
    SETTINGS.generation.cfg_weight = prof.cfg_weight
    SETTINGS.generation.temperature = prof.temperature
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
    name = payload.get("name") or "default"
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
    name = payload.get("name") or "default"
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
    g, r, m, o = s.generation, s.readcheck, s.master, s.orphans
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
    for path, value in payload.get("values", {}).items():
        group, key = path.split(".", 1)
        target = getattr(SETTINGS, group)
        current = getattr(target, key)
        setattr(target, key, type(current)(value) if not isinstance(current, bool) else bool(value))
    SETTINGS.save()
    return {"message": f"Saved to {config.SETTINGS_FILE}"}


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
                # Stated plainly because the failure is otherwise invisible: a
                # model that cannot hear will happily describe audio anyway.
                "note": (f"audio{detail} — you CANNOT listen to it. Measure it "
                         "instead: ffprobe, soundfile, or the checks in vostudio/")}
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


@app.post("/api/assistant")
async def assistant(payload: dict):
    # Only paths inside ATTACH_DIR. The client sends these back, and a client is
    # not a place to enforce where the agent may read from.
    files = []
    for raw in payload.get("files") or []:
        try:
            p = Path(raw).resolve()
            p.relative_to(ATTACH_DIR.resolve())
            if p.is_file():
                files.append(p)
        except (ValueError, OSError):
            continue

    message = payload.get("message", "")
    if files:
        listing = "\n".join(f"  {p}  — {_describe(p)['note']}" for p in files)
        message = (f"Sapro attached these files to this message:\n{listing}\n\n"
                   f"{message}")

    # Confirm calls on = every edit prompts. Off = it edits and reports after.
    mode = "default" if SETTINGS.app.confirm_calls else "acceptEdits"

    out: list[str] = []
    await ask(message, ROOT, on_text=out.append,
              permission_mode=mode, model=SETTINGS.app.assistant_model)
    return {"reply": "".join(out)}
