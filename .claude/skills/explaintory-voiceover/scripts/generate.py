#!/usr/bin/env python3
"""
Script -> raw stitched voiceover, via the ElevenLabs API.

Same generation semantics as Voiceover Studio, so a section produced here is
interchangeable with one produced in the browser tool:

  * one request per section, ~450 chars
  * previous_text / next_text conditioning, 300 chars each way
  * previous_request_ids from the last 3 sections, for request stitching
  * conditioning is DROPPED right after a chapter announcement, so the narration
    starts fresh instead of continuing the heading's sentence
  * exact digital silence inserted around chapter announcements and CTAs

Unlike the browser, the stitch lands in a 48 kHz WAV rather than a re-encoded
MP3 — mastering runs on the un-degraded audio and only the delivered file is
encoded once.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs
from elevenlabs.core.api_error import ApiError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from script_prep import (CONTEXT_CHARS, build_sections, chapter_gaps,  # noqa: E402
                         master_script_lines)

SR = 48000
OUTPUT_FORMAT = "mp3_44100_128"

DEFAULT_SETTINGS = {
    "stability": 0.50,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": True,
    "speed": 1.0,
}
DEFAULT_MODEL = "eleven_multilingual_v2"


def log(m):
    print(f"[voiceover] {m}", flush=True)


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f"{cmd[0]} failed:\n{p.stderr[-2000:]}")
    return p.stdout


# ------------------------------------------------------------------ profile
def load_profile(path=None):
    """Voice id + calibrated settings. Same shape as the studio's voiceover_profile.json,
    so that file can be dropped in unchanged."""
    prof = {}
    if path and os.path.isfile(path):
        prof = json.load(open(path, encoding="utf-8"))
    cal = prof.get("calibration") or {}

    key = os.environ.get("ELEVENLABS_API_KEY") or prof.get("api_key") or ""
    voice = os.environ.get("ELEVENLABS_VOICE_ID") or cal.get("voice") or prof.get("voice_id") or ""
    model = os.environ.get("ELEVENLABS_MODEL") or cal.get("model") or prof.get("model") or DEFAULT_MODEL

    settings = dict(DEFAULT_SETTINGS)
    for k in ("stability", "similarity_boost", "style", "speed"):
        v = cal.get(k, prof.get(k))
        if v is not None:
            settings[k] = float(v)
    if cal.get("use_speaker_boost") is not None:
        settings["use_speaker_boost"] = bool(cal["use_speaker_boost"])

    return {"api_key": key, "voice_id": voice, "model": model, "settings": settings,
            "collapse_breaks": bool(cal.get("collapseBreaks", prof.get("collapse_breaks", False))),
            "chapter_pause": cal.get("chapterPause", prof.get("chapter_pause", "natural")),
            "skip_headings": bool(cal.get("skipHeadings", prof.get("skip_headings", False))),
            "chunk_size": int(cal.get("chunkSize", prof.get("chunk_size", 0)) or 0)}


def check_profile(prof):
    missing = []
    if not prof["api_key"]:
        missing.append("ELEVENLABS_API_KEY (env var, or api_key in the profile)")
    if not prof["voice_id"]:
        missing.append("ELEVENLABS_VOICE_ID (env var, or calibration.voice in the profile)")
    if missing:
        raise SystemExit("Cannot generate — missing:\n  " + "\n  ".join(missing) +
                         "\n\nExport your settings from Voiceover Studio (the profile lives at "
                         "voiceover_profile.json next to voiceover_studio.py) and pass it with "
                         "--profile, or set the environment variables.")


# ------------------------------------------------------------------ tts
def client(prof):
    return ElevenLabs(api_key=prof["api_key"], timeout=180)


def tts(client, prof, sections, index, prev_ids):
    """One section -> (mp3 bytes, request id). Retries 429/5xx with backoff."""
    sec = sections[index]
    prev = sections[index - 1] if index else None
    nxt = sections[index + 1] if index + 1 < len(sections) else None
    fresh_start = bool(prev and prev["is_heading"])

    kw = dict(
        voice_id=prof["voice_id"],
        text=sec["send_text"],
        model_id=prof["model"],
        output_format=OUTPUT_FORMAT,
        voice_settings=VoiceSettings(**prof["settings"]),
    )
    if prev and not fresh_start:
        kw["previous_text"] = prev["send_text"][-CONTEXT_CHARS:]
    if nxt:
        kw["next_text"] = nxt["send_text"][:CONTEXT_CHARS]
    if not fresh_start and prev_ids:
        kw["previous_request_ids"] = prev_ids[-3:]

    backoff = 2
    for attempt in range(4):
        try:
            # raw response so the request id header survives — it is what makes the
            # next section continue this one's delivery instead of restarting it
            raw = client.text_to_speech.with_raw_response.convert(**kw)
            audio = b"".join(raw.data)
            headers = getattr(raw, "headers", {}) or {}
            rid = headers.get("request-id") or headers.get("x-request-id")
            return audio, rid
        except ApiError as e:
            status = e.status_code or 0
            msg = str(getattr(e, "body", "") or e)
            if status == 401:
                raise RuntimeError("Invalid or expired ElevenLabs API key.")
            if status == 402 or "quota" in msg.lower():
                raise RuntimeError(f"Not enough ElevenLabs credits for section {index+1}: {msg}")
            if status in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(backoff)
                backoff *= 2
                continue
            raise RuntimeError(f"section {index+1}: {msg}")
        except Exception as e:
            if attempt == 3:
                raise RuntimeError(f"section {index+1}: {e}")
            time.sleep(backoff)
            backoff *= 2
    raise RuntimeError(f"section {index+1}: gave up after retries")


def generate_sections(prof, sections, parts_dir, only=None):
    """Render sections to parts_dir/sec_NNN.mp3. `only` = iterable of indexes to
    (re)generate; everything else is reused from disk. Returns request ids."""
    os.makedirs(parts_dir, exist_ok=True)
    cl = client(prof)
    ids_path = os.path.join(parts_dir, "request_ids.json")
    ids = json.load(open(ids_path)) if os.path.isfile(ids_path) else {}

    todo = set(range(len(sections))) if only is None else set(only)
    prev_ids = []
    for i, sec in enumerate(sections):
        path = os.path.join(parts_dir, f"sec_{i:03d}.mp3")
        if i in todo or not os.path.isfile(path):
            kind = "chapter" if sec["is_heading"] else "CTA" if sec["is_cta"] else "section"
            log(f"  {i+1}/{len(sections)} {kind}, {sec['chars']} chars")
            audio, rid = tts(cl, prof, sections, i, prev_ids)
            open(path, "wb").write(audio)
            ids[str(i)] = rid
        rid = ids.get(str(i))
        if rid:
            prev_ids.append(rid)
    json.dump(ids, open(ids_path, "w"), indent=1)
    return ids


# ------------------------------------------------------------------ stitch
def _decode(src, rate=SR):
    """-> headerless s16le mono bytes. Byte concatenation of these is sample-exact."""
    with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as f:
        tmp = f.name
    run(["ffmpeg", "-v", "error", "-i", src, "-ac", "1", "-ar", str(rate),
         "-f", "s16le", tmp, "-y"])
    data = open(tmp, "rb").read()
    os.unlink(tmp)
    return data


def stitch(parts_dir, sections, out_path, preset="natural", rate=SR):
    """Concatenate the sections with exact digital silence between them.
    Returns [{index, start, end}] so a flagged section maps back to a timestamp."""
    gaps = chapter_gaps(sections, preset)
    pcm = bytearray()
    marks = []
    for i, sec in enumerate(sections):
        if gaps[i] > 0:
            pcm += b"\x00\x00" * int(round(gaps[i] * rate))
        start = len(pcm) / 2 / rate
        pcm += _decode(os.path.join(parts_dir, f"sec_{i:03d}.mp3"), rate)
        marks.append({"index": i, "start": round(start, 3),
                      "end": round(len(pcm) / 2 / rate, 3)})

    with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as f:
        raw = f.name
    open(raw, "wb").write(bytes(pcm))
    run(["ffmpeg", "-v", "error", "-f", "s16le", "-ar", str(rate), "-ac", "1",
         "-i", raw, out_path, "-y"])
    os.unlink(raw)
    return marks


# ------------------------------------------------------------------ cli
def main():
    ap = argparse.ArgumentParser(description="Generate a raw voiceover from a script.")
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", required=True, help="stitched raw VO, .wav recommended")
    ap.add_argument("--profile", help="voiceover_profile.json from Voiceover Studio")
    ap.add_argument("--parts-dir", help="where section takes live (default: alongside --out)")
    ap.add_argument("--skip-headings", action="store_true",
                    help="do not read chapter names aloud (studio default is to read them)")
    ap.add_argument("--max-chunk", type=int, default=450)
    ap.add_argument("--chapter-pause", choices=["tight", "natural", "wide"])
    ap.add_argument("--regen", help="comma-separated 1-based sections to re-render")
    ap.add_argument("--stability", type=float,
                    help="override the profile's stability for this run. Raising it "
                         "slightly is the studio's fix for false mid-sentence pauses.")
    ap.add_argument("--stitch-only", action="store_true")
    ap.add_argument("--sections-json", help="write the section manifest here")
    a = ap.parse_args()

    prof = load_profile(a.profile)
    if a.stability is not None:
        prof["settings"]["stability"] = max(0.0, min(1.0, a.stability))
    preset = a.chapter_pause or prof["chapter_pause"]
    raw_script = open(a.script, encoding="utf-8").read()
    sections = build_sections(raw_script, a.skip_headings, a.max_chunk)
    if not sections:
        raise SystemExit("Nothing to narrate — the script is empty after removing headings.")

    parts_dir = a.parts_dir or os.path.splitext(a.out)[0] + "_parts"
    chars = sum(s["chars"] for s in sections)
    log(f"{len(sections)} sections · {chars} chars · ~{chars} credits")

    if not a.stitch_only:
        check_profile(prof)
        only = None
        if a.regen:
            only = [int(x) - 1 for x in a.regen.split(",") if x.strip()]
            log(f"re-rendering sections {', '.join(str(i+1) for i in only)}")
        generate_sections(prof, sections, parts_dir, only)

    log("stitching")
    marks = stitch(parts_dir, sections, a.out, preset)
    log(f"wrote {a.out}  ({marks[-1]['end']/60:.1f} min)")

    if a.sections_json:
        json.dump({"sections": sections, "marks": marks,
                   "script_lines": master_script_lines(raw_script, a.skip_headings)},
                  open(a.sections_json, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
