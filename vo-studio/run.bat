@echo off
REM  Starts VO Studio with a console so errors are visible.
REM  VOStudio.exe does the same thing silently.
setlocal
cd /d "%~dp0"
set "RT=%CD%\runtime"
REM  Setup builds either a venv (interpreter under Scripts\) or unpacks the
REM  embeddable Python flat. Take whichever is there.
set "PY=%RT%\python\python.exe"
if exist "%RT%\python\Scripts\python.exe" set "PY=%RT%\python\Scripts\python.exe"
if not exist "%PY%" ( echo Not set up yet - double-click "VO Studio.bat" first. & pause & exit /b 1 )
REM  Bundled tools on PATH for this process only - nothing system-wide.
set "PATH=%RT%\ffmpeg\bin;%RT%\espeak;%RT%\node;%PATH%"
set "HF_HOME=%RT%\models"
REM  A set ANTHROPIC_API_KEY outranks the Claude subscription login.
if defined ANTHROPIC_API_KEY set "ANTHROPIC_API_KEY="
"%PY%" desktop.py
pause
