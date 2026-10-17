@echo off
rem One-click launcher: 1) git pull main  2) install packages  3) open the menu
cd /d "%~dp0"

rem ---- update from GitHub main (skipped if git missing / offline) ----
where git >nul 2>nul
if errorlevel 1 (
    echo [INFO] git not found, skip update.
) else (
    git -C "%~dp0" rev-parse --is-inside-work-tree >nul 2>nul
    if errorlevel 1 (
        echo [INFO] Not a git clone, skip update.
    ) else (
        echo Checking for updates on main...
        git -C "%~dp0" pull --ff-only origin main
        if errorlevel 1 echo [WARN] Update failed ^(offline or local changes^). Using current version.
    )
)

rem ---- python + packages ----
set "PY=python"
where python >nul 2>nul
if errorlevel 1 set "PY=py"
echo Checking packages (requests, cryptography)...
%PY% -m pip install --user -q requests cryptography
if errorlevel 1 echo [WARN] pip failed. If the menu errors, check your internet / Python install.

%PY% "%~dp0router_tool.py"
pause
