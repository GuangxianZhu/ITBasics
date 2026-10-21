@echo off
rem One-click launcher: pneumatic valve exploded views (three.js, offline html)
rem   1) git pull main   2) npm install (first run)   3) rebuild butterfly valve html   4) open both html files
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
        if errorlevel 1 echo [WARN] Update failed ^(offline, local changes or not on main^). Using current version.
    )
)

rem ---- Node.js is needed only to rebuild; the html files work without it ----
where node >nul 2>nul
if errorlevel 1 (
    echo [WARN] Node.js not found. Opening the prebuilt html files without rebuilding.
    goto open
)
if not exist "%~dp0work\node_modules\three" (
    echo Installing three / esbuild / puppeteer-core into work\node_modules ^(first run^) ...
    pushd "%~dp0work"
    call npm install
    popd
)
echo Rebuilding the butterfly valve page ...
node "%~dp0work\valve\build.mjs"
if errorlevel 1 (
    echo [ERROR] Build failed. See messages above.
    pause
    exit /b 1
)

:open
for %%F in ("%~dp0*.html") do start "" "%%F"
endlocal
