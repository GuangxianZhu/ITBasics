@echo off
rem One-click launcher: Floating sphere robot ORB-1, sci-fi (Blender script model) + exploded view
rem   1) git pull main   2) find Blender   3) build output\orb_bot.blend + orb_bot.glb   4) menu
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
echo Building the ORB-1 robot model and exploded-view animation ...
"%BLENDER%" --background --factory-startup --python "%~dp0build_orb_bot.py" -- "%~dp0output"
if not exist "%~dp0output\orb_bot.blend" (
    echo [ERROR] Build failed. See messages above.
    pause
    exit /b 1
)

:menu
echo.
echo Done. output\orb_bot.blend and output\orb_bot.glb are ready.
echo   Frames 1-120    take apart
echo   Frames 150-270  put back together
echo.
echo   [1] Open in Blender  (press Space to play)
echo   [2] Render 3 preview PNGs (Cycles, a few minutes on CPU)
echo   [3] Quit
choice /c 123 /n /m "Choose 1-3: "
set "PICK=%errorlevel%"
if "%PICK%"=="1" goto blend
if "%PICK%"=="2" goto stills
goto end

:blend
start "" "%BLENDER%" "%~dp0output\orb_bot.blend"
goto end

:stills
"%BLENDER%" --background --factory-startup --python "%~dp0build_orb_bot.py" -- "%~dp0output" --render
start "" "%~dp0output"
goto end

:end
endlocal
