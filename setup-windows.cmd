@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  python -c "import sys; assert sys.version_info >= (3,12), 'Python 3.12 or newer is required'"
  if errorlevel 1 goto failure
  python -m venv .venv
) else (
  py -3 -c "import sys; assert sys.version_info >= (3,12), 'Python 3.12 or newer is required'"
  if errorlevel 1 goto failure
  py -3 -m venv .venv
)
if errorlevel 1 goto failure
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failure
echo Setup complete. Double-click launch-windows.cmd to compare Gerbers.
pause
exit /b 0
:failure
echo Setup failed. Install Python 3.12 or newer from python.org and try again.
pause
exit /b 1
