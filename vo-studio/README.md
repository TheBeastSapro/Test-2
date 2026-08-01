# ExplainTory VO Studio

A local Windows app that replaces the ElevenLabs pipeline with **Chatterbox**, running
on Sapro's own GPU. Zero credits per render.

Status: **all modules written; never run end-to-end.** Every piece testable without a
GPU has been tested on real audio and the results are below. The generation path
itself has only been exercised on CPU, one phrase at a time — the first full render
on Sapro's GPU is the real test, and it has not happened.

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

## Two bugs the tests caught before they shipped

**The sentence splitter died on any script containing "U.S."** `re.sub(r"\b([A-Z])\.",
r"\1\x00", ...)` looks right and is not: in a raw replacement string `re`'s template
parser reads `\x` as a bad escape and raises. Every abbreviation-containing script
would have crashed at prep.

**`place_beats` padded every gap that merely looked like a pause.** Measured on 60 s of
real read: 126 gaps, of which 34 sit in the pause regime — against the 8 commas the
whole original defect ever involved. Most sub-target gaps are stop consonants and
plosive closures *inside words*; padding those inserts a beat mid-word. It now locates
each scripted comma via ASR word timings and pads only the gap that comma lands on.
With no word timings it does nothing at all, which is the safe direction to fail in.

Verified on a 12-second excerpt: 4 commas in the script, 4 located, 2 of them sitting
on 30 ms gaps the voice read through and correctly left alone, 1 padded. Locating all
4 needed one more fix — ASR writes "1798" where the script says "seventeen
ninety-eight", so the ASR token is expanded the same way and every word it becomes
shares that token's end time. Without that, alignment slipped two words at every year
and silently lost the comma after it.

ASR word timestamps are used only to *locate* words, never to measure a gap. They
return contiguous spans, so asking one how long a pause is always answers 0.000 s.
Gap length comes from an RMS envelope.

## What has NOT been proven

- **No full render has ever run.** Chatterbox has produced exactly one phrase, on CPU.
- **The Windows installer has never executed.** It is written from the measured
  dependency facts, not from a successful run.
- **The assistant has never connected.** The SDK surface is verified; the login flow
  is not.
- **The mastering chain has not run end-to-end** — its gap logic and loudness stage
  are tested in isolation on real audio.

First real job on the GPU is the test. Expect something here to be wrong.
