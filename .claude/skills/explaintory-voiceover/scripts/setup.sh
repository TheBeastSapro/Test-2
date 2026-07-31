#!/usr/bin/env bash
# One-time install for the voiceover pipeline. Safe to re-run.
#
#   generation   elevenlabs
#   read-check   faster-whisper (ASR) + jiwer (WER) + whisper-normalizer (spelling/numbers)
#   breaks       spacy + en_core_web_sm, to find where a fronted phrase ends
#   mastering    numpy scipy torch torchaudio, for humanize.py's forced alignment
#
# First run of each stage also downloads a model: distil-large-v3 (~750 MB) for the
# read-check and MMS_FA (~1.2 GB) for the alignment. Both are cached afterwards.
set -euo pipefail

PIP=(python3 -m pip install --break-system-packages -q)

command -v ffmpeg >/dev/null || { echo "ffmpeg is required and not on PATH"; exit 1; }

echo "installing generation + read-check…"
"${PIP[@]}" elevenlabs faster-whisper jiwer whisper-normalizer spacy
python3 -m spacy download en_core_web_sm

echo "installing mastering deps…"
"${PIP[@]}" numpy scipy
"${PIP[@]}" torch torchaudio --index-url https://download.pytorch.org/whl/cpu

python3 - <<'PY'
import importlib
for m in ("elevenlabs", "faster_whisper", "jiwer", "whisper_normalizer",
          "spacy", "numpy", "scipy", "torch", "torchaudio"):
    importlib.import_module(m)
import spacy; spacy.load("en_core_web_sm")
print("all dependencies present")
PY

echo
echo "Set ELEVENLABS_API_KEY in the environment, then:"
echo "  python3 scripts/voiceover.py --script script.txt --profile voiceover_profile.json --out-dir ./out"
