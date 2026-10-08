@echo off
rem Double-click : menu (function index / extract functions / extract by keyword)
rem Drag files or folders onto this file : merge them into _ai_out\merged_files.txt
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo Python was not found on this PC.
  pause
  exit /b 1
)
%PY% "%~dp0code_tool.py" %*
echo.
pause
