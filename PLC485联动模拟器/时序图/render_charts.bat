@echo off
rem One-click: update from GitHub main, then render timing charts to out\
rem   render_charts.bat          -> all charts (SVG)
rem   render_charts.bat --png    -> also PNG (for Excel / PowerPoint)
rem   render_charts.bat B2       -> only chart B2
rem Output: out\*.svg, out\*.drawio (Chinese / _ja Japanese / _en English), out\*.md
setlocal
cd /d "%~dp0"

rem ---- update from GitHub main (skipped if git missing / offline) ----
where git >nul 2>nul
if errorlevel 1 (
    echo [INFO] git not found, skip update.
) else (
    git rev-parse --is-inside-work-tree >nul 2>nul
    if errorlevel 1 (
        echo [INFO] Not a git clone, skip update.
    ) else (
        rem out\ is generated. If draw.io re-saved a file there, the pull would be refused,
        rem so back up the drawio to out_local\ and restore out\ before pulling.
        git diff --quiet -- out
        if errorlevel 1 (
            echo [INFO] out\ has local edits ^(e.g. drawio saved in draw.io^).
            echo        Backing up out\*.drawio to out_local\ and restoring out\ ...
            if not exist "out_local" mkdir "out_local"
            copy /y "out\*.drawio" "out_local\" >nul
            git checkout -- out
        )
        echo Checking for updates on main...
        git pull --ff-only origin main
        if errorlevel 1 (
            echo [WARN] Update failed ^(offline or local changes^). Using current files.
            echo        Run "git status" in this folder to see what blocks the update.
            pause
        )
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

rem ---- install matplotlib if missing ----
%PY% -c "import matplotlib" >nul 2>nul
if errorlevel 1 (
    echo matplotlib not found, installing...
    %PY% -m pip install --user matplotlib
    if errorlevel 1 (
        echo [ERROR] pip install matplotlib failed. Check network / proxy, or install manually:
        echo     %PY% -m pip install matplotlib
        pause
        exit /b 1
    )
)

rem ---- render ----
%PY% render.py %*
if errorlevel 1 (
    echo.
    echo [ERROR] Render failed. See the message above.
    pause
    exit /b 1
)
start "" "%~dp0out"
endlocal
