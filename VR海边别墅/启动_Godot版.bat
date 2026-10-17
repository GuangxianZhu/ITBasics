@echo off
rem One-click launcher: interactive seaside villa in Godot 4 + OpenXR (Quest 3 via Virtual Desktop)
rem   1) git pull main   2) Blender exports godot\model\villa.glb   3) find / download Godot   4) run
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "GODOT_VER=4.7.2-stable"

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

rem ---- export the model + generate textures/sounds (Blender's own Python has numpy) ----
if defined BLENDER (
    echo Using Blender: "%BLENDER%"
    echo Exporting villa.glb ...
    "%BLENDER%" --background --factory-startup --python "%~dp0export_godot.py"
    echo Generating textures and sounds ^(first time ~15s, then skipped^) ...
    "%BLENDER%" --background --factory-startup --python "%~dp0make_assets.py"
) else (
    echo [WARN] Blender not found ^(put blender.exe path into blender_path.txt^).
)
if not exist "%~dp0godot\model\villa.glb" (
    echo [ERROR] godot\model\villa.glb was not created. See messages above.
    pause
    exit /b 1
)

rem ---- find Godot: godot_path.txt > tools folder > PATH > download official build from GitHub ----
set "GODOT="
if exist "%~dp0godot_path.txt" set /p GODOT=<"%~dp0godot_path.txt"
if defined GODOT if not exist "%GODOT%" set "GODOT="
if not defined GODOT (
    if exist "%~dp0tools\Godot_v%GODOT_VER%_win64.exe" set "GODOT=%~dp0tools\Godot_v%GODOT_VER%_win64.exe"
)
if not defined GODOT (
    where godot >nul 2>nul && for /f "delims=" %%G in ('where godot') do if not defined GODOT set "GODOT=%%G"
)
if not defined GODOT (
    echo Godot not found. Downloading Godot %GODOT_VER% ^(about 70 MB, one time only^) ...
    if not exist "%~dp0tools" mkdir "%~dp0tools"
    curl.exe -L --fail -o "%~dp0tools\godot.zip" "https://github.com/godotengine/godot/releases/download/%GODOT_VER%/Godot_v%GODOT_VER%_win64.exe.zip"
    if errorlevel 1 (
        echo [ERROR] Download failed. Download Godot 4 manually from godotengine.org
        echo         and put the full path of the Godot .exe into godot_path.txt
        pause
        exit /b 1
    )
    powershell -NoProfile -Command "Expand-Archive -Force '%~dp0tools\godot.zip' '%~dp0tools'"
    del "%~dp0tools\godot.zip"
    set "GODOT=%~dp0tools\Godot_v%GODOT_VER%_win64.exe"
)
if not exist "%GODOT%" (
    echo [ERROR] Godot executable not found: "%GODOT%"
    pause
    exit /b 1
)

rem ---- run ----
echo.
echo Using Godot: "%GODOT%"
echo Put on Quest 3 and connect Virtual Desktop first ^(OpenXR runtime = VDXR^).
echo Without a headset it opens in desktop mode ^(WASD + mouse^).
echo First start bakes global illumination ^(a few seconds^). Settings: godot\settings.cfg
start "" "%GODOT%" --path "%~dp0godot"
endlocal
