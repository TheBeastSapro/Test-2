#!/usr/bin/env bash
# Everything the voiceover and sound-design skills need, in one idempotent pass.
# Safe to re-run: pip skips what is already satisfied.
#
# Called by .claude/hooks/session-start.sh on remote sessions, and runnable by
# hand anywhere:  bash .claude/scripts/install-audio-tools.sh
#
# Models are NOT fetched here. distil-large-v3 (~750 MB), MMS_FA (~1.2 GB) and
# silero-vad (~2 MB) download on first use and are cached with the container.
set -euo pipefail

PIP=(python3 -m pip install --break-system-packages -q)

command -v ffmpeg >/dev/null || { echo "ffmpeg missing and required"; exit 1; }

echo "[audio-tools] generation + read-check"
#   elevenlabs         TTS
#   faster-whisper     ASR for the read-check
#   jiwer              word error rate + alignment
#   whisper-normalizer British/American spelling and spoken numbers
#   spacy              where a fronted clause ends, for the pause breaks
"${PIP[@]}" elevenlabs faster-whisper jiwer whisper-normalizer spacy
python3 -c "import spacy; spacy.load('en_core_web_sm')" 2>/dev/null \
  || python3 -m spacy download en_core_web_sm

echo "[audio-tools] mastering"
#   humanize.py's forced alignment
"${PIP[@]}" numpy scipy soundfile
"${PIP[@]}" torch torchaudio --index-url https://download.pytorch.org/whl/cpu

echo "[audio-tools] pronunciation check"
#   espeak-ng    grapheme-to-phoneme, the reference reading of a word
#   phonemizer   espeak driver
#   allosaurus   recognises phones from audio, so a MISREAD word is visible
#   panphon      phonetic feature distance between expected and heard
# These were installed by hand in an earlier session and died with the container,
# because they were never added here. That is why "Quito" was still uncaught a
# session later: the tools were reported as installed and were not.
command -v espeak-ng >/dev/null || apt-get install -y espeak-ng >/dev/null 2>&1 \
  || echo "[audio-tools] WARN: espeak-ng unavailable — pronunciation check will not run"
"${PIP[@]}" phonemizer panphon allosaurus

echo "[audio-tools] sound design"
#   scenedetect  finds dissolves the ffmpeg scene score misses entirely
#   silero-vad   duck on speech rather than on energy
#   librosa      beat grid, so music changes and SFX land musically
#   opencv       already used by visual_redraw.py
"${PIP[@]}" scenedetect librosa silero-vad opencv-python-headless

python3 - <<'PY'
import importlib, sys
mods = ["elevenlabs", "faster_whisper", "jiwer", "whisper_normalizer", "spacy",
        "phonemizer", "panphon", "allosaurus",
        "numpy", "scipy", "soundfile", "torch", "torchaudio",
        "scenedetect", "librosa", "silero_vad", "cv2"]
missing = []
for m in mods:
    try:
        importlib.import_module(m)
    except Exception as e:
        missing.append(f"{m}: {e}")
import spacy
try:
    spacy.load("en_core_web_sm")
except Exception as e:
    missing.append(f"en_core_web_sm: {e}")
if missing:
    print("[audio-tools] MISSING:\n  " + "\n  ".join(missing)); sys.exit(1)
print(f"[audio-tools] all {len(mods)} packages present")
PY

echo "[audio-tools] done. Set ELEVENLABS_API_KEY to generate."
