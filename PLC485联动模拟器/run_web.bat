@echo off
rem One-click launcher: PLC gateway simulator (HTML, offline, no install needed)
rem   run_web.bat   -> update from GitHub main, then open web\index.html in the default browser
setlocal
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
        if errorlevel 1 (
            echo [WARN] Update failed ^(offline or local changes^). Opening current version.
            echo        Run "git status" in this folder to see what blocks the update.
            timeout /t 4 >nul
        )
    )
)

rem ---- open ----
if not exist "%~dp0web\index.html" (
    echo [ERROR] web\index.html not found.
    pause
    exit /b 1
)
start "" "%~dp0web\index.html"
endlocal
