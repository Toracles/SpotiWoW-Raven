@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem Resolve absolute paths explicitly so PyInstaller always receives its scriptname.
set "PY=py -3.15"
set "SCRIPT=%CD%\SpotiWoW-RavenLauncher.py"
set "ICON=%CD%\SpotiWoW-Raven.ico"
set "OUT=%CD%"
set "WORK=%CD%\build_temp"

if not exist "%SCRIPT%" (
  echo ERROR: Launcher source was not found:
  echo "%SCRIPT%"
  echo.
  echo Extract the entire ZIP and run this file from the companion folder.
  pause
  exit /b 2
)
if not exist "%ICON%" (
  echo ERROR: Icon was not found:
  echo "%ICON%"
  pause
  exit /b 2
)

%PY% --version >nul 2>nul
if errorlevel 1 (
  echo Python 3.15 was not found. Install it from python.org, then retry.
  pause
  exit /b 1
)

echo Installing the Windows launcher build dependencies...
%PY% -m pip install --upgrade "pyinstaller>=6.21" pystray pillow psutil "syncedlyrics==1.0.1"
if errorlevel 1 (
  echo Dependency installation failed. Check internet access and Python 3.15.
  pause
  exit /b 1
)

if not exist "%WORK%" mkdir "%WORK%"
echo.
echo Building SpotiWoW-Raven.exe with no console window...
echo Python: %PY%
echo Script: "%SCRIPT%"
echo Icon:   "%ICON%"
echo Output: "%OUT%"
echo.

rem Keep the source path as the final positional PyInstaller argument.
%PY% -m PyInstaller --clean --noconfirm --onefile --windowed --name "SpotiWoW-Raven" --icon "%ICON%" --collect-all syncedlyrics --collect-all pystray --collect-all psutil --distpath "%OUT%" --workpath "%WORK%" --specpath "%WORK%" "%SCRIPT%"
if errorlevel 1 (
  echo.
  echo Build failed. The full PyInstaller command above includes the source script path.
  echo Verify that the script and icon paths printed above exist.
  pause
  exit /b 1
)

if not exist "%OUT%\SpotiWoW-Raven.exe" (
  echo Build returned success but SpotiWoW-Raven.exe was not found.
  pause
  exit /b 1
)
echo.
echo SUCCESS: "%OUT%\SpotiWoW-Raven.exe"
echo The EXE is built as a Windows GUI app and does not open a CMD window when launched.
echo Keep it beside spotify_bridge.py, config.json, config.example.json and SpotiWoW-Raven.ico.
pause
exit /b 0
