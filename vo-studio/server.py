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

from vostudio import config, pipeline
from vostudio.assistant import ask, check_auth
from vostudio.voice_profile import VoiceProfile, apply_feedback

ROOT = Path(__file__).resolve().parent
UI = ROOT / "ui"
SETTINGS = config.Settings.load()
config.ensure_dirs()

app = FastAPI(title="ExplainTory VO Studio")
STATE: dict = {"voice": None, "render": None, "log": []}


# ------------------------------------------------------------------ shell
@app.get("/", response_class=HTMLResponse)
def index():
    return (f"<!doctype html><html><head><meta charset=utf-8>"
            f"<title>ExplainTory VO Studio</title>"
            f"<link rel=icon href='/ui/icon.png'>"
            f"<style>{(UI / 'app.css').read_text()}</style></head><body>"
            f"{(UI / 'index.html').read_text()}"
            f"<script>{(UI / 'app.js').read_text()}</script></body></html>")


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
    dest = config.VOICES_DIR / "reference" / file.filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(await file.read())

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
            lines.append(f"FAILED: {type(exc).__name__}: {exc}")
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


@app.post("/api/lab/sample")
def lab_sample(payload: dict):
    name = payload.get("name") or "default"
    if not STATE.get("voice"):
        return {"error": "Set a reference clip on the Voice tab first."}
    prof = VoiceProfile.load(config.VOICES_DIR, name)
    prof.reference = STATE["voice"]

    from vostudio.generate import Generator
    gen = Generator(SETTINGS)
    out = config.VOICES_DIR / name / "sample.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        gen.generate_chunk(payload.get("text") or SAMPLE, STATE["voice"], out,
                           exaggeration=prof.exaggeration,
                           temperature=prof.temperature,
                           cfg_weight=prof.cfg_weight, speed=prof.speed)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    finally:
        gen.unload()
    prof.save(config.VOICES_DIR)
    return {"profile": asdict(prof)}


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
    return {"ok": s.ok, "detail": s.detail}


@app.post("/api/assistant")
async def assistant(payload: dict):
    out: list[str] = []
    await ask(payload.get("message", ""), ROOT, on_text=out.append,
              permission_mode=payload.get("mode", "default"))
    return {"reply": "".join(out)}
