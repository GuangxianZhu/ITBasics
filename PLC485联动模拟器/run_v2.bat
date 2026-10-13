@echo off
rem One-click launcher: PLC <-> RS-485 water heater simulator
rem   run_v2.bat      -> v2 (two-way, PLC gateway)
rem   run_v2.bat v1   -> v1 (IO -> RS-485)
chcp 65001 >nul
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
        if errorlevel 1 echo [WARN] Update failed ^(offline or local changes^). Running current version.
    )
)

rem ---- find Python (py launcher first, then python) ----
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [ERROR] Python not found. Install Python 3 and check "Add to PATH".
    pause
    exit /b 1
)

rem ---- install panda3d if missing ----
%PY% -c "import panda3d" >nul 2>nul
if errorlevel 1 (
    echo panda3d not found, installing...
    %PY% -m pip install --user panda3d
    if errorlevel 1 (
        echo [ERROR] pip install panda3d failed. Check network / proxy, or install manually:
        echo     %PY% -m pip install panda3d
        pause
        exit /b 1
    )
)

rem ---- start ----
if /i "%~1"=="v1" (
    %PY% plc485_sim.py
) else (
    cd v2
    %PY% app.py
)
if errorlevel 1 (
    echo.
    echo [ERROR] The program exited with an error. See the message above.
    pause
)
endlocal
