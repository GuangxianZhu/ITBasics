@echo off
rem One-click launcher: BLDC motor (57 frame, Hall) exploded view
rem   1) git pull main   2) find Blender   3) build output\motor.blend + motor.glb + offline html   4) open
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

rem ---- optional Cycles preview renders (GPU is used automatically if available) ----
set "RENDER="
choice /c YN /n /t 10 /d N /m "Render preview images with Cycles too? (slower)  [Y/N, default N in 10 s] "
if errorlevel 2 (set "RENDER=") else (set "RENDER=--render")

echo.
echo Building the motor model ...
"%BLENDER%" --background --factory-startup --python "%~dp0build_motor.py" -- "%~dp0output" %RENDER%
if not exist "%~dp0output\motor.blend" (
    echo [ERROR] Build failed. See messages above.
    pause
    exit /b 1
)

echo.
echo Done. Files are in the "output" folder:
echo   motor.blend  - open in Blender, press Space to play the explode animation
echo   motor.glb    - for Unreal / web (File ^> Import Into Level in UE5)
echo   *.html       - offline viewer, double-click to open (no internet needed)
echo.
echo   [1] Open the web viewer   [2] Open in Blender   [3] Both   [4] Quit
choice /c 1234 /n /m "Choose 1-4: "
set "PICK=%errorlevel%"
if "%PICK%"=="1" goto web
if "%PICK%"=="2" goto blend
if "%PICK%"=="3" goto both
goto end
:both
start "" "%BLENDER%" "%~dp0output\motor.blend"
:web
for %%F in ("%~dp0output\*.html") do start "" "%%F"
goto end
:blend
start "" "%BLENDER%" "%~dp0output\motor.blend"
:end
endlocal
