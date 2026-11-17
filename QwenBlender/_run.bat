@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title QwenBlender
echo ============================================
echo   QwenBlender
echo ============================================

rem ---- 1. git pull (only when this folder is inside a git repo)
where git >nul 2>&1
if errorlevel 1 goto nogit
git -C "%~dp0." rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 goto nogit
echo [update] git pull origin main ...
git -C "%~dp0." pull origin main
goto gitdone
:nogit
echo [update] not a git repo, skip git pull
:gitdone

rem ---- 2. find Blender (to force a path: set "BLENDER=D:\xxx\blender.exe" here)
set "BLENDER="
set "BDIR="
for /d %%D in ("C:\Program Files\Blender Foundation\Blender*") do if exist "%%~fD\blender.exe" set "BDIR=%%~fD"
if defined BDIR set "BLENDER=%BDIR%\blender.exe"
if not defined BLENDER (
  echo [error] blender.exe not found under C:\Program Files\Blender Foundation
  goto end
)
echo [blender] %BLENDER%

rem ---- 3. python: use the one bundled with Blender
set "PY="
for /d %%V in ("%BDIR%\*") do if exist "%%~fV\python\bin\python.exe" set "PY=%%~fV\python\bin\python.exe"
if not defined PY (
  where python >nul 2>&1
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  echo [error] python not found
  goto end
)
echo [python] %PY%

rem ---- 4. make sure Ollama is running
curl -s -m 3 http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
  echo [ollama] not running, starting Ollama ...
  start "" "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
  timeout /t 10 >nul
)

rem ---- 5. settings
if not defined QB_MODEL set "QB_MODEL=qwen3.8:27b-q8_0"
if not defined QB_CTX set "QB_CTX=65536"
if not defined QB_THINK set "QB_THINK=1"
set PYTHONUTF8=1

"%PY%" -X utf8 "%~dp0agent.py" %*

:end
echo.
pause
