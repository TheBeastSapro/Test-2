@echo off
REM ============================================================================
REM  Double-click this once. It opens the app's own setup window -- a real
REM  window with a progress bar, not this console.
REM
REM  This file exists only because a Windows .exe cannot be built anywhere but
REM  on Windows, so the very first launch has nothing else to start from. Setup
REM  builds VOStudio.exe as its last step, and from then on this file is dead
REM  weight you can ignore.
REM
REM  Nothing installs on your machine. Python (or an isolated environment built
REM  from the one you already have), ffmpeg, Node and espeak-ng all land in
REM  .\runtime inside this folder. Deleting the folder is the uninstall.
REM ============================================================================
cd /d "%~dp0"

REM pythonw first: it draws the window with no console behind it. The console
REM only appears if pythonw is missing, and then it is the useful kind.
where pythonw >nul 2>&1 && (start "" pythonw "%~dp0launcher.py" & exit /b 0)
where python  >nul 2>&1 && (python "%~dp0launcher.py" & exit /b 0)

echo.
echo   Python was not found on this machine.
echo.
echo   Install Python 3.11 or 3.12 from python.org -- tick "Add python.exe to
echo   PATH" on the first screen -- then double-click this file again.
echo.
echo   That is the only thing VO Studio needs you to install. Everything else
echo   it downloads into this folder by itself.
echo.
pause
