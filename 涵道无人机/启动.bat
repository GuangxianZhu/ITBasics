@echo off
rem One-click launcher: original 3-inch cinewhoop drone (Blender script model)
rem   1) git pull main   2) find Blender   3) build output\drone.blend   4) menu: open / render video / render stills
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

echo.
echo Building the drone model and animation ...
"%BLENDER%" --background --factory-startup --python "%~dp0build_drone.py" -- "%~dp0output"
if not exist "%~dp0output\drone.blend" (
    echo [ERROR] Build failed. See messages above.
    pause
    exit /b 1
)

:menu
echo.
echo Done. output\drone.blend is ready.
echo   Frames 1-449   flight demo   (take-off, figure-8 through two gates, landing)
echo   Frames 450-750 exploded view (turntable: take apart, hold, put back)
echo.
echo   [1] Open in Blender  (press Space to play)
echo   [2] Render MP4 video (EEVEE, 1280x720, 750 frames, uses GPU, several minutes)
echo   [3] Render 4 preview PNGs (Cycles)
echo   [4] Quit
choice /c 1234 /n /m "Choose 1-4: "
set "PICK=%errorlevel%"
if "%PICK%"=="1" goto blend
if "%PICK%"=="2" goto video
if "%PICK%"=="3" goto stills
goto end

:blend
start "" "%BLENDER%" "%~dp0output\drone.blend"
goto end

:video
"%BLENDER%" --background --factory-startup --python "%~dp0build_drone.py" -- "%~dp0output" --video
if exist "%~dp0output\drone_demo.mp4" (
    start "" "%~dp0output\drone_demo.mp4"
) else (
    echo [ERROR] Video was not created. See messages above.
    pause
)
goto end

:stills
"%BLENDER%" --background --factory-startup --python "%~dp0build_drone.py" -- "%~dp0output" --render
start "" "%~dp0output"
goto end

:end
endlocal
