@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title QwenBlender - 让 Qwen 用 Blender 建模

echo ============================================
echo   QwenBlender  让本地 Qwen 用 Blender 建模
echo ============================================

rem ---------- 1. 检查 main 分支有没有更新（只有在 git 仓库里才会做）
where git >nul 2>&1
if %errorlevel%==0 (
  git -C "%~dp0" rev-parse --is-inside-work-tree >nul 2>&1
  if not errorlevel 1 (
    echo [更新] git pull origin main ...
    git -C "%~dp0" pull origin main
  ) else (
    echo [更新] 这个文件夹不是 git 仓库，跳过 git pull
  )
) else (
  echo [更新] 没装 git，跳过 git pull
)

rem ---------- 2. 找 Blender（想指定的话，把下一行改成 set "BLENDER=你的路径\blender.exe"）
set "BLENDER="
set "BDIR="
for /d %%D in ("C:\Program Files\Blender Foundation\Blender*") do (
  if exist "%%D\blender.exe" (
    set "BLENDER=%%D\blender.exe"
    set "BDIR=%%D"
  )
)
if not defined BLENDER (
  echo [错误] 在 C:\Program Files\Blender Foundation 下面没找到 blender.exe
  echo        请用记事本打开这个 bat，在第 2 步手动写上 BLENDER 的路径
  pause
  exit /b 1
)
echo [Blender] %BLENDER%

rem ---------- 3. 用 Blender 自带的 Python 跑 agent（不用另外装 Python）
set "PY="
for /d %%V in ("%BDIR%\*") do (
  if exist "%%V\python\bin\python.exe" set "PY=%%V\python\bin\python.exe"
)
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo [错误] 找不到 Python
  pause
  exit /b 1
)

rem ---------- 4. 检查 Ollama 有没有开
curl -s -m 3 http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
  echo [Ollama] 没连上，正在尝试启动 Ollama ...
  start "" "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe" >nul 2>&1
  timeout /t 8 >nul
)

rem ---------- 5. 可调参数（不懂就别动）
if not defined QB_MODEL set "QB_MODEL=qwen3.8:27b-q8_0"
if not defined QB_CTX set "QB_CTX=65536"
if not defined QB_THINK set "QB_THINK=1"

set PYTHONUTF8=1
"%PY%" -X utf8 "%~dp0agent.py" %*

echo.
pause
