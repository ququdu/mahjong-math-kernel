@echo off
chcp 65001 >nul
setlocal

rem ============================================================
rem  Mahjong Math Kernel - realtime overlay
rem  Screen capture + recognition + recommendation, live.
rem  Requires calibration first:
rem      python -m vision.cli calibrate
rem ============================================================

cd /d "%~dp0"

set PY=python
where %PY% >nul 2>nul
if errorlevel 1 (
  set PY=py
)

if not exist "vision_data\templates.npz" (
  echo.
  echo   No template pack yet.
  echo   Run this once to calibrate:
  echo.
  echo       %PY% -m vision.cli calibrate
  echo.
  pause
  exit /b 1
)
if not exist "vision_data\layout.json" (
  echo.
  echo   No layout yet. Run calibration first:
  echo.
  echo       %PY% -m vision.cli calibrate
  echo.
  pause
  exit /b 1
)

%PY% desktop\overlay.py %*
if errorlevel 1 (
  echo.
  echo Overlay exited with an error. See the message above.
  pause
)
