@echo off
REM Forgecast — double-click to start.
REM
REM Finds a Python, hands over to launcher.py, and keeps the console open if
REM something goes wrong. Everything else happens in the launcher.

setlocal
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")

if not defined PY (
  echo.
  echo   Python was not found on this machine.
  echo   Install Python 3.11 or newer from https://python.org/downloads
  echo   and tick "Add python.exe to PATH" during setup.
  echo.
  pause
  exit /b 1
)

%PY% launcher.py %*
if errorlevel 1 pause
endlocal
