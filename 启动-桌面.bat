@echo off
chcp 65001 >nul
setlocal

rem ============================================================
rem  Mahjong Math Kernel - desktop (tkinter) launcher
rem ============================================================

cd /d "%~dp0"

set PY=python
where %PY% >nul 2>nul
if errorlevel 1 (
  set PY=py
)

%PY% desktop\app.py
if errorlevel 1 (
  echo.
  echo Desktop app exited with an error. See the message above.
  pause
)
