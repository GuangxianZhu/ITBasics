@echo off
rem One-click launcher: seaside villa for Quest 3 (Virtual Desktop) via Blender VR Scene Inspection
rem   1) git pull main   2) find Blender   3) build villa.blend   4) open it with VR addon enabled
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
        if errorlevel 1 echo [WARN] Update failed ^(offline or local changes^). Using current version.
    )
)

rem ---- find Blender: blender_path.txt > PATH > Program Files > Steam ----
set "BLENDER="
if exist "%~dp0blender_path.txt" set /p BLENDER=<"%~dp0blender_path.txt"
if defined BLENDER if not exist "%BLENDER%" (
    echo [WARN] blender_path.txt points to a missing file: "%BLENDER%"
    set "BLENDER="
)
if not defined BLENDER (
    where blender >nul 2>nul && for /f "delims=" %%B in ('where blender') do if not defined BLENDER set "BLENDER=%%B"
)
if not defined BLENDER (
    for /d %%D in ("%ProgramFiles%\Blender Foundation\Blender*") do if exist "%%D\blender.exe" set "BLENDER=%%D\blender.exe"
)
if not defined BLENDER (
    if exist "%ProgramFiles(x86)%\Steam\steamapps\common\Blender\blender.exe" set "BLENDER=%ProgramFiles(x86)%\Steam\steamapps\common\Blender\blender.exe"
)
if not defined BLENDER (
    echo [ERROR] Blender not found.
    echo Put the full path of blender.exe into blender_path.txt next to this bat, e.g.
    echo     C:\Program Files\Blender Foundation\Blender 4.2\blender.exe
    pause
    exit /b 1
)
echo Using Blender: %BLENDER%

rem ---- build the scene (overwrites villa.blend; save your own edits under another name) ----
echo Building villa.blend ...
"%BLENDER%" --background --factory-startup --python "%~dp0build_villa.py" -- "%~dp0villa.blend"
if not exist "%~dp0villa.blend" (
    echo [ERROR] Build failed. See messages above.
    pause
    exit /b 1
)

rem ---- open it; vr_setup.py enables the VR addon and sets up the viewport ----
echo.
echo In Blender: sidebar (N) ^> VR tab ^> Start VR Session.
echo Connect Quest 3 with Virtual Desktop first, and set its OpenXR runtime to VDXR.
start "" "%BLENDER%" "%~dp0villa.blend" --python "%~dp0vr_setup.py"
endlocal
