@echo off
chcp 65001 >nul
setlocal

rem ============================================================
rem  Mahjong Math Kernel - web UI launcher
rem  Opens the browser at http://127.0.0.1:8765/
rem ============================================================

cd /d "%~dp0"

set PORT=8765
set PY=python
where %PY% >nul 2>nul
if errorlevel 1 (
  set PY=py
)

echo Starting Mahjong Math Kernel web UI on http://127.0.0.1:%PORT%/ ...
start "" http://127.0.0.1:%PORT%/
%PY% -m mahjong_kernel.api.server --port %PORT%

echo.
echo Server stopped.
pause
