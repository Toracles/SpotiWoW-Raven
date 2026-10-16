@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PY=py -3.15"
set "SOURCE=%~dp0SpotiWoW-RavenSetup.py"
set "ICON=%~dp0SpotiWoW-Raven.ico"
set "OUT=%~dp0dist"
set "WORK=%~dp0build_temp"

echo.
echo SpotiWoW-Raven Setup EXE builder
set /p "REPO=GitHub repository (owner/name), e.g. user/SpotiWoW-Raven: "
echo %REPO%| findstr /r /x "[A-Za-z0-9_.-][A-Za-z0-9_.-]*/[A-Za-z0-9_.-][A-Za-z0-9_.-]*" >nul
if errorlevel 1 (
  echo ERROR: Expected owner/name. This repository must have a public GitHub Release.
  pause
  exit /b 2
)
echo %REPO%>"%~dp0repo.txt"
if not exist "%SOURCE%" (
  echo ERROR: Missing %SOURCE%
  pause
  exit /b 2
)
if not exist "%ICON%" (
  echo ERROR: Missing %ICON%
  pause
  exit /b 2
)
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo Python 3.15 was not found. Install Python 3.15 first.
  pause
  exit /b 1
)
%PY% -m pip install --upgrade "pyinstaller>=6.21"
if errorlevel 1 (
  echo PyInstaller install failed.
  pause
  exit /b 1
)
if not exist "%OUT%" mkdir "%OUT%"
%PY% -m PyInstaller --clean --noconfirm --onefile --windowed --name "SpotiWoW-Raven-Setup" --icon "%ICON%" --add-data "%~dp0repo.txt;." --add-data "%ICON%;." --distpath "%OUT%" --workpath "%WORK%" --specpath "%WORK%" "%SOURCE%"
if errorlevel 1 (
  echo Setup EXE build failed. See the error output above.
  pause
  exit /b 1
)
echo.
echo SUCCESS: "%OUT%\SpotiWoW-Raven-Setup.exe"
echo The setup downloads the latest SpotiWoW-Raven-Portable.zip from the selected public GitHub repository.
pause
