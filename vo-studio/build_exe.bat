@echo off
REM  Builds VOStudio.exe -- a small launcher, not a 5 GB bundle of PyTorch.
REM  Run once after setup.bat; rebuild any time.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" ( echo Run setup.bat first. & pause & exit /b 1 )
call .venv\Scripts\activate.bat
pip install -q pyinstaller
pyinstaller --onefile --noconsole --clean --name VOStudio --icon assets\icon.ico ^
  --distpath . --workpath build\work --specpath build launcher.py
if errorlevel 1 ( echo Build failed. & pause & exit /b 1 )
rmdir /s /q build 2>nul
echo.
echo  VOStudio.exe built. Double-click it to launch.
echo.
pause
