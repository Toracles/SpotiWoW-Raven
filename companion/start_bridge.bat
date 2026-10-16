@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 (
  py -3.15 --version >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=py -3.15"
)
if not defined PYTHON_CMD (
  python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,15) else 1)" >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
  echo ERROR: Python 3.15 was not found. Install it or fix the Python launcher.
  pause
  exit /b 1
)
%PYTHON_CMD% --version
%PYTHON_CMD% spotify_bridge.py
if errorlevel 1 (
  echo.
  echo SpotiWoW-Raven bridge exited with an error. Review the message above.
  pause
)
