@echo off
REM ============================================================================
REM  VO Studio - self-contained setup
REM
REM  Nothing is installed on this machine. Python, ffmpeg, espeak-ng and Node
REM  are downloaded into .\runtime\ inside this folder, and the app puts them on
REM  PATH for its own process only. Your system Python, system PATH and
REM  Add/Remove Programs are untouched. Delete the folder and it is all gone.
REM
REM  The one thing NOT bundled is the Chatterbox model (~1 GB). It downloads on
REM  first render and caches in .\runtime\models\, because shipping it would
REM  make the download 1 GB before you know the app even runs.
REM ============================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "RT=%CD%\runtime"
set "PY=%RT%\python\python.exe"
set "PATH=%RT%\ffmpeg\bin;%RT%\espeak;%RT%\node;%PATH%"

echo.
echo   VO STUDIO - SETUP
echo   Everything installs into this folder. Nothing touches your system.
echo   ---------------------------------------------------------------
echo.

if defined ANTHROPIC_API_KEY (
  echo   [!] ANTHROPIC_API_KEY is set on this machine. It overrides your Claude
  echo       subscription login, so the assistant would bill an API account.
  echo       The app clears it for its own process, so setup will continue.
  echo.
)

mkdir "%RT%" 2>nul

REM ---- 1. Python (embeddable, ~11 MB, no installer, no registry) ------------
if exist "%PY%" (
  echo   [1/6] Python already present.
) else (
  echo   [1/6] Downloading Python 3.11...
  powershell -NoProfile -Command ^
    "Invoke-WebRequest 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip' -OutFile '%RT%\py.zip'; Expand-Archive '%RT%\py.zip' '%RT%\python' -Force; Remove-Item '%RT%\py.zip'"
  if not exist "%PY%" ( echo   [ERROR] Python download failed. Check your connection. & pause & exit /b 1 )
  REM  The embeddable build ships with site-packages disabled; pip needs it on.
  powershell -NoProfile -Command ^
    "$p = Get-ChildItem '%RT%\python\python*._pth' | Select-Object -First 1; (Get-Content $p) -replace '^#import site','import site' | Set-Content $p"
  echo   [1/6] Enabling pip...
  powershell -NoProfile -Command ^
    "Invoke-WebRequest 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%RT%\get-pip.py'"
  "%PY%" "%RT%\get-pip.py" -q --no-warn-script-location
  del "%RT%\get-pip.py" 2>nul
)

REM ---- 2. ffmpeg (static build, no installer) -------------------------------
if exist "%RT%\ffmpeg\bin\ffmpeg.exe" (
  echo   [2/6] ffmpeg already present.
) else (
  echo   [2/6] Downloading ffmpeg...
  powershell -NoProfile -Command ^
    "Invoke-WebRequest 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile '%RT%\ff.zip'; Expand-Archive '%RT%\ff.zip' '%RT%\fftmp' -Force; $d = Get-ChildItem '%RT%\fftmp' -Directory | Select-Object -First 1; Move-Item $d.FullName '%RT%\ffmpeg' -Force; Remove-Item '%RT%\ff.zip','%RT%\fftmp' -Recurse -Force"
  if not exist "%RT%\ffmpeg\bin\ffmpeg.exe" ( echo   [ERROR] ffmpeg download failed. & pause & exit /b 1 )
)

REM ---- 3. Node + the Claude Code CLI (only for the assistant) ---------------
if exist "%RT%\node\node.exe" (
  echo   [3/6] Node already present.
) else (
  echo   [3/6] Downloading Node...
  powershell -NoProfile -Command ^
    "Invoke-WebRequest 'https://nodejs.org/dist/v22.14.0/node-v22.14.0-win-x64.zip' -OutFile '%RT%\node.zip'; Expand-Archive '%RT%\node.zip' '%RT%\ntmp' -Force; $d = Get-ChildItem '%RT%\ntmp' -Directory | Select-Object -First 1; Move-Item $d.FullName '%RT%\node' -Force; Remove-Item '%RT%\node.zip','%RT%\ntmp' -Recurse -Force"
)
if exist "%RT%\node\npm.cmd" (
  if not exist "%RT%\node\claude.cmd" (
    echo   [3/6] Installing the Claude Code CLI into the app folder...
    call "%RT%\node\npm.cmd" install -g @anthropic-ai/claude-code --prefix "%RT%\node" >nul 2>&1
  )
) else (
  echo   [3/6] Node unavailable - the Assistant will be off. Rendering is unaffected.
)

REM ---- 4. PyTorch with CUDA ------------------------------------------------
echo   [4/6] Installing PyTorch with CUDA (large download, be patient)...
"%PY%" -m pip install -q --no-warn-script-location torch==2.6.0 torchaudio==2.6.0 ^
  --index-url https://download.pytorch.org/whl/cu124
if errorlevel 1 ( echo   [ERROR] PyTorch failed. Check your NVIDIA driver. & pause & exit /b 1 )

REM ---- 5. The pipeline -----------------------------------------------------
echo   [5/6] Installing Chatterbox and the QC stack...
"%PY%" -m pip install -q --no-warn-script-location chatterbox-tts faster-whisper soundfile ^
  scipy pyloudnorm phonemizer panphon allosaurus fastapi uvicorn python-multipart ^
  pywebview pillow claude-agent-sdk pyinstaller
if errorlevel 1 ( echo   [ERROR] Install failed - see the message above. & pause & exit /b 1 )

REM  espeak-ng has no wheel and no portable zip, so it is fetched from the
REM  release MSI and unpacked WITHOUT installing (msiexec /a extracts in place).
if exist "%RT%\espeak\espeak-ng.exe" (
  echo   [5/6] espeak-ng already present.
) else (
  echo   [5/6] Unpacking espeak-ng ^(pronunciation check^)...
  powershell -NoProfile -Command ^
    "try { Invoke-WebRequest 'https://github.com/espeak-ng/espeak-ng/releases/download/1.51/espeak-ng-X64.msi' -OutFile '%RT%\es.msi' } catch { exit 1 }"
  if exist "%RT%\es.msi" (
    msiexec /a "%RT%\es.msi" /qn TARGETDIR="%RT%\esraw" >nul 2>&1
    powershell -NoProfile -Command ^
      "$e = Get-ChildItem '%RT%\esraw' -Recurse -Filter 'espeak-ng.exe' | Select-Object -First 1; if ($e) { New-Item '%RT%\espeak' -ItemType Directory -Force | Out-Null; Copy-Item $e.Directory.FullName\* '%RT%\espeak' -Recurse -Force }"
    del "%RT%\es.msi" 2>nul
    rmdir /s /q "%RT%\esraw" 2>nul
  )
  if not exist "%RT%\espeak\espeak-ng.exe" echo         espeak-ng unavailable - only the pronunciation check is affected.
)

REM ---- 6. Verify and build the launcher ------------------------------------
echo   [6/6] Verifying...
"%PY%" -c "import torch, chatterbox, faster_whisper, soundfile, fastapi, webview; print('   torch', torch.__version__, '| CUDA', torch.cuda.is_available()); print('   GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE - CPU is about 10x realtime')"
if errorlevel 1 ( echo   [ERROR] Verification failed. & pause & exit /b 1 )

"%PY%" -m PyInstaller --onefile --noconsole --clean --name VOStudio --icon assets\icon.ico ^
  --distpath . --workpath build\work --specpath build launcher.py >nul 2>&1
rmdir /s /q build 2>nul

echo.
if exist VOStudio.exe (
  echo   Done. Double-click VOStudio.exe
) else (
  echo   Done. Start it with run.bat
)
echo.
pause
