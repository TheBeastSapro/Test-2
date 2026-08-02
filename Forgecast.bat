@echo off
REM Forgecast — double-click to start.
REM
REM Finds a Python, hands over to launcher.py, and keeps the console open if
REM something goes wrong. Everything else happens in the launcher.

setlocal

REM pushd rather than "cd /d". Both handle an ordinary drive letter, but cd cannot
REM enter a UNC path at all — double-clicking from \\server\share leaves the shell in
REM C:\Windows and the launcher then cannot find its own files. pushd maps a temporary
REM drive letter for the UNC case and behaves like cd /d otherwise.
pushd "%~dp0" || (
  echo.
  echo   Could not enter the Forgecast folder:
  echo   %~dp0
  echo.
  pause
  exit /b 1
)

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
  popd
  exit /b 1
)

%PY% launcher.py %*
set "STATUS=%ERRORLEVEL%"

popd
if not "%STATUS%"=="0" pause
endlocal & exit /b %STATUS%
