"""
ElevenLabs, as an optional second engine.

WHY OPTIONAL AND WHY SECOND
    Chatterbox runs on Sapro's own GPU for nothing, which is the entire reason
    this app exists. ElevenLabs costs money per character and needs a network
    round trip per chunk. It earns its place in exactly two situations: when
    Chatterbox cannot hold the read on a particular script, and when a job has
    to sound right the first time and the budget is not the constraint.

    So it is a switch, not a rewrite. The read-check, the orphan sweep, the
    comma work and the mastering all run identically afterwards -- the engine
    only decides where the audio comes from.

THE KEY
    ELEVENLABS_API_KEY in the environment wins. Otherwise it comes from
    settings.json, which is a plain file in the Documents folder -- fine for a
    key on your own machine, wrong for anything shared, and said plainly here
    rather than left for someone to discover.

NOT BUILT BLIND, BUT NOT PROVEN EITHER
    Every request shape here comes from the published API. None of it has run
    against the live service from this machine -- there is no key here. The
    first real call is the test, so failures report the actual HTTP status and
    body rather than a friendly guess.
"""
import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.elevenlabs.io/v1"

# Published rate, and it moves. Shown as an estimate and labelled as one --
# a number presented as exact that later turns out not to be is worse than a
# range.
USD_PER_1K_CHARS = 0.18


def api_key(settings) -> str:
    """Environment first: a key in the shell is easier to rotate and does not
    sit in a file that gets copied around with the app folder."""
    return (os.environ.get("ELEVENLABS_API_KEY")
            or getattr(settings.eleven, "api_key", "") or "").strip()


def _request(path: str, key: str, payload: dict | None = None,
             method: str = "GET", timeout: int = 120) -> bytes:
    req = urllib.request.Request(
        f"{API}{path}", method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"xi-api-key": key, "Content-Type": "application/json",
                 "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as exc:
        # The body is where ElevenLabs says what is actually wrong -- quota,
        # a bad voice id, an unverified key. Swallowing it for a tidy message
        # is how an afternoon disappears.
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"ElevenLabs {exc.code}: {detail}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach ElevenLabs: {exc.reason}") from None


def list_voices(settings) -> list[dict]:
    """The account's voices, so a voice id is chosen from what exists rather
    than typed from memory. A wrong id is a 400 several seconds into a render."""
    key = api_key(settings)
    if not key:
        raise RuntimeError("No ElevenLabs API key. Set ELEVENLABS_API_KEY or "
                           "paste one into Settings > ElevenLabs.")
    data = json.loads(_request("/voices", key))
    return [{"voice_id": v.get("voice_id"), "name": v.get("name"),
             "labels": v.get("labels") or {}, "category": v.get("category")}
            for v in data.get("voices", [])]


def estimate_usd(text: str) -> float:
    return round(len(text) / 1000 * USD_PER_1K_CHARS, 4)


def synthesize(text: str, out_path: Path, settings, work_sr: int = 48000) -> Path:
    """
    One chunk, written as a wav at the pipeline's working rate.

    mp3 out of the API and ffmpeg into wav, rather than asking for PCM: the
    high-rate PCM formats are gated behind higher plans, and discovering that
    mid-render is a worse outcome than one extra decode of a file that is
    already on disk.
    """
    cfg = settings.eleven
    key = api_key(settings)
    if not key:
        raise RuntimeError("No ElevenLabs API key. Set ELEVENLABS_API_KEY or "
                           "paste one into Settings > ElevenLabs.")
    if not cfg.voice_id:
        raise RuntimeError("No ElevenLabs voice selected. Ask for the voice list "
                           "and pick one.")

    audio = _request(
        f"/text-to-speech/{cfg.voice_id}?output_format=mp3_44100_128", key,
        payload={
            "text": text,
            "model_id": cfg.model,
            "voice_settings": {
                "stability": cfg.stability,
                "similarity_boost": cfg.similarity_boost,
                "style": cfg.style,
                "use_speaker_boost": cfg.speaker_boost,
            },
        }, method="POST")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp.write(audio)
        raw = Path(tmp.name)
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw),
                        "-ar", str(work_sr), "-ac", "1",
                        "-c:a", "pcm_s24le", str(out_path)], check=True)
    finally:
        raw.unlink(missing_ok=True)
    return out_path
