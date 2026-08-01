@echo off
REM ============================================================================
REM  ExplainTory VO Studio - Windows installer
REM
REM  Two runtimes, on purpose:
REM    Python  - Chatterbox, the QC stack, the UI
REM    Node    - the Claude Code CLI, which the assistant drives
REM
REM  Chatterbox is installed into its OWN venv. It pins numpy 1.26.4 and
REM  torch 2.6.0, which contradicts the numpy>=2 the sound-design tools need -
REM  installing it system-wide breaks the QC pipeline. Measured, not assumed.
REM ============================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo  ExplainTory VO Studio - setup
echo  ============================================================
echo.

REM ---- an API key would silently outrank the subscription login -------------
if defined ANTHROPIC_API_KEY (
  echo  [WARNING] ANTHROPIC_API_KEY is set on this machine.
  echo.
  echo  It OVERRIDES your Claude subscription login, so the assistant would
  echo  bill an API account instead of using your subscription. An empty value
  echo  still counts as set and still wins - it must be genuinely removed:
  echo.
  echo      setx ANTHROPIC_API_KEY ""
  echo      then close this window, reopen it, and run setup again.
  echo.
  echo  Setup will continue - rendering does not need it - but the assistant
  echo  will refuse to start until it is gone.
  echo.
  pause
)

REM ---- prerequisites --------------------------------------------------------
where python >nul 2>&1 || (
  echo  [ERROR] Python not found. Install Python 3.11 from python.org and tick
  echo          "Add python.exe to PATH" during installation.
  pause & exit /b 1
)
where ffmpeg >nul 2>&1 || (
  echo  [ERROR] ffmpeg not found. Install it and add it to PATH:
  echo              winget install Gyan.FFmpeg
  echo          then reopen this window.
  pause & exit /b 1
)

echo  [1/6] Creating isolated environment...
if not exist ".venv" python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip -q

echo  [2/6] Installing PyTorch with CUDA 12.4 (large download, be patient)...
REM  cu124 matches the nvidia-*-cu12 12.4 runtime Chatterbox pulls in.
pip install -q torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
if errorlevel 1 (
  echo  [ERROR] CUDA PyTorch failed to install. Check your NVIDIA driver version.
  pause & exit /b 1
)

echo  [3/6] Installing Chatterbox...
pip install -q chatterbox-tts

echo  [4/6] Installing the QC stack...
REM  espeak-ng is the one piece with no pip wheel - it is a native binary.
pip install -q faster-whisper soundfile scipy pyloudnorm phonemizer panphon allosaurus gradio
where espeak-ng >nul 2>&1 || (
  echo.
  echo  [NOTE] espeak-ng not found. The pronunciation check needs it:
  echo             winget install eSpeak-NG.eSpeak-NG
  echo         Everything else works without it.
  echo.
)

echo  [5/6] Installing the Claude Code CLI for the assistant...
where npm >nul 2>&1 && (
  call npm install -g @anthropic-ai/claude-code
  pip install -q claude-agent-sdk
  echo.
  echo  Now sign in with your Claude subscription - a browser will open:
  echo      claude login
  echo.
) || (
  echo  [NOTE] Node.js not found, so the assistant tab is unavailable.
  echo         Install Node from nodejs.org, then run:
  echo             npm install -g @anthropic-ai/claude-code
  echo             claude login
  echo         Rendering works fine without it.
)

echo  [6/6] Verifying...
python -c "import torch, chatterbox, faster_whisper, soundfile, gradio; print('   torch', torch.__version__, '| CUDA', torch.cuda.is_available()); print('   GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE - generation will be ~10x realtime on CPU')"
if errorlevel 1 (
  echo  [ERROR] Verification failed - something above did not install.
  pause & exit /b 1
)

echo.
echo  Done. Start the app with run.bat
echo.
pause
