@echo off
REM  Starts VO Studio with a console so errors are visible.
REM  VOStudio.exe does the same thing silently.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" ( echo Run setup.bat first. & pause & exit /b 1 )
REM  A set ANTHROPIC_API_KEY outranks the Claude subscription login and would
REM  bill an API account instead. Cleared for this process only.
if defined ANTHROPIC_API_KEY (
  echo  [!] ANTHROPIC_API_KEY is set machine-wide - ignoring it for this session.
  echo      Remove it permanently:  setx ANTHROPIC_API_KEY ""
  set "ANTHROPIC_API_KEY="
)
call .venv\Scripts\activate.bat
python desktop.py
pause
