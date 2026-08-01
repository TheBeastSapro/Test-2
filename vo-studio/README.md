# ExplainTory VO Studio

A local Windows app that replaces the ElevenLabs pipeline with **Chatterbox**, running
on Sapro's own GPU. Zero credits per render.

Status: **partly built.** `vostudio/config.py`, `script_prep.py`, and `generate.py`
are written against the real library. The UI, mastering chain, and installer are not.
See "What is left" at the bottom — nothing here is claimed to run end-to-end yet.

## Everything below was measured, not assumed

Chatterbox 0.1.7 was installed and a real line was generated in Sapro's cloned voice
before a line of this app was written. That surfaced five facts that change the design:

**1. Output is 24 kHz. Not a setting.** `S3GEN_SR = 24000`. The channel's back
catalogue is 48 kHz, so `generate.py` upsamples — which adds no detail above 12 kHz
and exists only so the master is not resampling mid-chain. This is a real quality
ceiling versus ElevenLabs and it is the main thing to listen for on the first script.

**2. It clips.** A 3.6-second test phrase came back with **53 samples at full scale in
11 consecutive runs**, peak 0.00 dBFS. Every chunk gets headroom applied at generation
time, because a squared-off peak cannot be un-clipped downstream and the loudness stage
would happily normalise the distortion along with the voice. Chunks that arrive clipped
are logged, not silently repaired.

**3. Every output is watermarked.** `ChatterboxTTS.generate()` runs
`perth.PerthImplicitWatermarker` on the way out. It is inaudible and it cannot be
disabled from the public API. Disclosed here because it is a property of the audio.

**4. The voice clone works, and the reference already exists.** A 9-second cut of
`FINAL v11.mp3` was used as the prompt; ASR read the generated line back word-perfect.
Sapro's delivered read is the reference material — no new recording needed.

**5. Chatterbox pins conflict with the QC stack.** It requires `numpy 1.26.4`, which
the sound-design tools' `numpy>=2` contradicts, and it pins `torch 2.6.0`. This is why
the installer builds an **isolated venv** rather than installing into the system
Python. Installing Chatterbox alongside the existing toolchain breaks the QC pipeline.

**Speed:** 10.3× realtime on 4 CPU cores — a 12-minute script would take ~2 hours on
CPU. That is why this is a local GPU app and not something that runs in the container.
Target hardware: Windows 11, 6–8 GB VRAM, so `config.py` defaults to fp16 with
`torch.cuda.empty_cache()` between chunks.

## The thresholds are inherited, not re-derived

`config.py` carries every number the ElevenLabs pipeline paid for once already, each
with the failure that set it: float32 ASR (int8 hallucinated dropped words), WER 0.20
(0.05 sat below the 0.047 median on good audio), chapter-header exemption from rate/WER
checks, 3 ms edge fades on splices, and `RUNTHROUGH 0.060` so the master stops padding
commas the voice read through. Changing one needs a measurement, not an opinion.

## The embedded Claude assistant

Verified against `claude-agent-sdk` 0.2.128, not from memory. It gives exactly the
surface this needs:

| Need | Field |
|---|---|
| Confine the agent to the app directory | `cwd`, `add_dirs` |
| Real OS-level sandbox | `sandbox: SandboxSettings` — filesystem *and* network |
| Ask before acting | `permission_mode`, `can_use_tool` callback |
| Block specific tools | `allowed_tools` / `disallowed_tools` |
| Cap spend | `max_budget_usd` |

`permission_mode` accepts `default`, `acceptEdits`, `plan`, `bypassPermissions`,
`dontAsk`, `auto`. **This app will ship on `default`** — every edit prompts. An agent
with unattended write access to the pipeline that generates the channel's audio is not
something to enable by default, and `bypassPermissions` should stay off.

### Subscription login, not an API key

**Login is `claude login`** — the browser OAuth flow against Sapro's existing Claude
subscription. There is no API key anywhere in this app, and none is needed: the Agent
SDK spawns the Claude Code CLI, which uses the credentials that login stores.

**The one trap, and the installer must handle it: a set `ANTHROPIC_API_KEY` silently
overrides the subscription login.** Credential resolution checks the environment
variable *first*, so a leftover key — from any earlier experiment — wins, and requests
quietly bill an API account instead of using the subscription. An empty
`ANTHROPIC_API_KEY=""` still occupies the slot and still wins; the variable has to be
genuinely unset, not blanked.

So `setup.bat` must **never** set `ANTHROPIC_API_KEY`, and `run.bat` should check for
one and warn before launching rather than letting it take over silently.

**It requires the Claude Code CLI**, not just the Python package:
`npm install -g @anthropic-ai/claude-code`. So the installer needs Node.js as well as
Python, and on Windows the SDK looks for `claude.cmd`. Worth knowing before the
installer is written — it is a second runtime, not a pip dependency.

## What is left

Not built. Listed honestly rather than implied:

- `readcheck.py` — ASR verification and re-roll loop
- `master.py` — the humanize/mastering chain
- `orphans.py` — port of the detector in `.claude/skills/explaintory-voiceover/scripts/`
- `pipeline.py` — orchestration
- `app.py` — Gradio UI (Chatterbox already ships Gradio as a dependency)
- `setup.bat` / `run.bat` — venv, CUDA torch 2.6.0, Node, CLI, desktop shortcut
- The assistant tab itself

The pronunciation check is still unbuilt in the ElevenLabs pipeline too, and its
dependencies (`espeak-ng`, `allosaurus`, `phonemizer`, `panphon`, `kokoro`) are still
missing from `install-audio-tools.sh`. Whichever pipeline ships first, that gap is the
same gap.
