# voiceover-export

ExplainTory voiceover pipeline, packaged so another Claude (e.g. Cowork) can run it
the same way.

Read in this order:

1. **RUN.md**: exact commands, script → final MP3, plus a test with expected output
2. **VOICEOVER-SOP.md**: every setting, gap, and processing step, tagged GENERAL or
   CHANNEL TASTE, and where the docs disagree with the code
3. **MANUAL-STEPS.md**: what is still done by hand or checked by ear

`config/voice-calibration.json` is the locked voice profile. The API key comes only
from the `ELEVENLABS_API_KEY` environment variable. No file in this folder holds a key.
