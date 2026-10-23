@echo off
rem One-click launcher: 20-DOF five-finger dexterous hand (Blender script model)
rem   1) git pull main   2) find Blender   3) build output\hand.blend + web viewer   4) menu
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
    echo     C:\Program Files\Blender Foundation\Blender 5.0\blender.exe
    pause
    exit /b 1
)
echo Using Blender: %BLENDER%

echo.
echo Building the hand model, poses and exploded view ...
"%BLENDER%" --background --factory-startup --python "%~dp0build_hand.py" -- --out "%~dp0output"
if not exist "%~dp0output\hand.blend" (
    echo [ERROR] Build failed. See messages above.
    pause
    exit /b 1
)

:menu
echo.
echo Done. output\hand.blend and the offline web viewer are ready.
echo   Frames 1-180    rest -^> fist -^> open -^> pinch -^> open -^> spread -^> rest
echo   Frames 182-276  exploded view (take apart, hold, put back)
echo.
echo   [1] Open the web viewer (offline html, works on phone too)
echo   [2] Open in Blender  (press Space to play)
echo   [3] Render 8 preview PNGs (Cycles, a few minutes)
echo   [4] Interference check (finds parts that pass through each other)
echo   [5] Quit
choice /c 12345 /n /m "Choose 1-5: "
set "PICK=%errorlevel%"
if "%PICK%"=="1" goto web
if "%PICK%"=="2" goto blend
if "%PICK%"=="3" goto stills
if "%PICK%"=="4" goto check
goto end

:web
for %%F in ("%~dp0output\*.html") do start "" "%%F"
goto end

:blend
start "" "%BLENDER%" "%~dp0output\hand.blend"
goto end

:stills
"%BLENDER%" --background --factory-startup --python "%~dp0render.py" -- --out "%~dp0output\renders"
start "" "%~dp0output\renders"
goto end

:check
"%BLENDER%" --background --factory-startup --python "%~dp0check.py"
echo.
echo Report saved to output\check_report.txt
pause
goto menu

:end
endlocal
