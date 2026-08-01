@echo off
REM  Launch ExplainTory VO Studio. Opens in your browser on localhost.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
  echo  Not installed yet - run setup.bat first.
  pause & exit /b 1
)

REM  A set ANTHROPIC_API_KEY outranks the subscription login and would bill an
REM  API account instead. Clear it for THIS process only - the machine-wide
REM  variable is the user's to remove, and silently overriding it would hide
REM  the problem rather than fix it.
if defined ANTHROPIC_API_KEY (
  echo  [WARNING] ANTHROPIC_API_KEY is set machine-wide. Ignoring it for this
  echo            session so the assistant uses your Claude subscription.
  echo            To remove it permanently:  setx ANTHROPIC_API_KEY ""
  set "ANTHROPIC_API_KEY="
)

call .venv\Scripts\activate.bat
python app.py
pause
