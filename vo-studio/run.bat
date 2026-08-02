@echo off
REM  Starts VO Studio with a console so errors are visible.
REM  VOStudio.exe does the same thing silently.
setlocal
cd /d "%~dp0"
set "RT=%CD%\runtime"
if not exist "%RT%\python\python.exe" ( echo Run setup.bat first. & pause & exit /b 1 )
REM  Bundled tools on PATH for this process only - nothing system-wide.
set "PATH=%RT%\ffmpeg\bin;%RT%\espeak;%RT%\node;%PATH%"
set "HF_HOME=%RT%\models"
REM  A set ANTHROPIC_API_KEY outranks the Claude subscription login.
if defined ANTHROPIC_API_KEY set "ANTHROPIC_API_KEY="
"%RT%\python\python.exe" desktop.py
pause
