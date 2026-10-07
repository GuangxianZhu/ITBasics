@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title PLC 梯形图教学

rem ---- 1. 找 Python（3.10 以上）----
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=python"
if not defined PY goto no_python

rem ---- 2. 第一次运行：建虚拟环境 .venv 并安装 panda3d ----
if exist ".venv\Scripts\python.exe" goto check_deps
echo 第一次运行，正在准备运行环境，需要联网，约 1~3 分钟……
%PY% -m venv .venv
if errorlevel 1 goto venv_failed

:check_deps
".venv\Scripts\python.exe" -c "import panda3d" >nul 2>nul
if not errorlevel 1 goto run
echo 正在安装 panda3d ……
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto pip_failed

rem ---- 3. 启动 ----
:run
".venv\Scripts\python.exe" main.py
if errorlevel 1 goto crashed
exit /b 0

:no_python
echo.
echo 没有找到 Python 3.10 或更高版本。
echo 请到 https://www.python.org/downloads/ 下载安装，
echo 安装时务必勾选 "Add python.exe to PATH"，装好后再双击本文件。
echo.
pause
exit /b 1

:venv_failed
echo.
echo 创建运行环境失败。可以删掉本文件夹里的 .venv 文件夹后重试。
pause
exit /b 1

:pip_failed
echo.
echo 安装 panda3d 失败，请检查网络后重新双击本文件。
echo 如果公司网络需要代理，先在命令行设置 HTTPS_PROXY 再运行。
pause
exit /b 1

:crashed
echo.
echo 程序异常退出，上面是错误信息。截图发给 Claude 即可。
pause
exit /b 1
