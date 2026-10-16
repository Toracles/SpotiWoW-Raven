@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHON_CMD="

rem Prefer the Windows Python launcher and explicitly select Python 3.15.
where py >nul 2>nul
if not errorlevel 1 (
  py -3.15 --version >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=py -3.15"
)

rem Fallback to `python` only if that executable is Python 3.15.
if not defined PYTHON_CMD (
  python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,15) else 1)" >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
  echo ERROR: Python 3.15 was not found.
  echo Install Python 3.15 and ensure the Windows Python launcher or python.exe is available.
  pause
  exit /b 1
)

echo Using:
%PYTHON_CMD% --version
%PYTHON_CMD% -m pip --version >nul 2>nul
if errorlevel 1 (
  %PYTHON_CMD% -m ensurepip --upgrade
  if errorlevel 1 (
    echo ERROR: Could not enable pip for the selected Python 3.15 installation.
    pause
    exit /b 1
  )
)

%PYTHON_CMD% -m pip install --upgrade pip
if errorlevel 1 (
  echo WARNING: pip upgrade failed; trying dependency installation with current pip.
)
%PYTHON_CMD% -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Dependency installation failed. Check your internet connection and Python 3.15 installation.
  echo Note: syncedlyrics lists Python >=3.8, but its published classifiers currently stop at 3.12,
  echo so compatibility with Python 3.15 has not been explicitly declared by its maintainer.
  pause
  exit /b 1
)
echo.
echo SpotiWoW-Raven dependencies installed for Python 3.15.
pause
