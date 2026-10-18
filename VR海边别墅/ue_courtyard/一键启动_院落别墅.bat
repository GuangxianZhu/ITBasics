@echo off
rem One-click: courtyard villa (Cycladic layout v2) in Unreal Engine 5.8 - project VillaVR, level L_Courtyard
rem   1) git pull main   2) sync UE python scripts to Documents\UE-MCP-Tools\court
rem   3) sync C++ source (cpp\Source) and build VillaVREditor   4) choose rendering mode   5) open VillaVR
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

rem ---- sync scripts (UE console runs them from Documents\UE-MCP-Tools\court) ----
set "TOOLS=%USERPROFILE%\Documents\UE-MCP-Tools\court"
if not exist "%TOOLS%" mkdir "%TOOLS%"
copy /Y "%~dp0*.py" "%TOOLS%\" >nul
copy /Y "%~dp0*.json" "%TOOLS%\" >nul
copy /Y "%~dp0*.wav" "%TOOLS%\" >nul
copy /Y "%~dp0*.glb" "%TOOLS%\" >nul
if not exist "%TOOLS%\tex" mkdir "%TOOLS%\tex"
copy /Y "%~dp0tex\*.png" "%TOOLS%\tex\" >nul
echo Scripts synced to %TOOLS%

set "PROJ=%USERPROFILE%\Documents\Unreal Projects\VillaVR"

rem ---- C++ module: sync cpp\Source into the project, then build the editor target ----
rem      (VillaVR is a C++ project since 2026-10-18; undo = restore VillaVR.uproject.before_cpp)
if exist "%~dp0cpp\Source" (
    robocopy "%~dp0cpp\Source" "%PROJ%\Source" /E /NFL /NDL /NJH /NJS /NP >nul
    if not exist "%TOOLS%\remote" mkdir "%TOOLS%\remote"
    copy /Y "%~dp0remote\*.py" "%TOOLS%\remote\" >nul 2>nul
    tasklist /FI "IMAGENAME eq UnrealEditor.exe" | find /I "UnrealEditor.exe" >nul
    if errorlevel 1 (
        echo Building VillaVR C++ module...
        call "%ProgramFiles%\Epic Games\UE_5.8\Engine\Build\BatchFiles\Build.bat" VillaVREditor Win64 Development -Project="%PROJ%\VillaVR.uproject" -WaitMutex -NoHotReloadFromIDE
        if errorlevel 1 (
            echo [ERROR] C++ build failed. See the messages above and send them to Claude.
            pause
            exit /b 1
        )
    ) else (
        echo [INFO] Unreal Editor is running - C++ build skipped. Close UE and run again to rebuild.
    )
)

rem ---- rendering mode ----
set "GI=%~dp0..\ue\gi_mode.ps1"
if exist "%GI%" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%GI%" status
    echo.
    echo   1 = forward  ^(VR: forward + MSAA + baked lightmaps, ~90 fps^)
    echo   2 = lumen    ^(deferred + Lumen real-time GI + TSR, heavier^)
    echo   Enter = keep current
    set "M="
    set /p M=Choose rendering mode: 
)
if "%M%"=="1" powershell -NoProfile -ExecutionPolicy Bypass -File "%GI%" forward
if "%M%"=="2" powershell -NoProfile -ExecutionPolicy Bypass -File "%GI%" lumen

rem ---- open the project (default level is L_Courtyard) ----
if not exist "%PROJ%\VillaVR.uproject" (
    echo [ERROR] %PROJ%\VillaVR.uproject not found.
    pause
    exit /b 1
)
tasklist /FI "IMAGENAME eq UnrealEditor.exe" | find /I "UnrealEditor.exe" >nul
if errorlevel 1 (
    echo Opening VillaVR in Unreal Editor...
    rem .uproject may not be associated with UE on this PC -> call UnrealEditor.exe directly
    set "UEXE=%ProgramFiles%\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
    if exist "%UEXE%" (
        start "" "%UEXE%" "%PROJ%\VillaVR.uproject"
    ) else (
        start "" "%PROJ%\VillaVR.uproject"
    )
) else (
    echo [WARN] Unreal Editor is already running. Close it and run this again for a mode change to apply.
)
echo Then: toolbar Play = desktop mode (WASD, E interact, Tab menu, H help, Esc stop).
echo       Play dropdown ^> VR Preview = headset, with Quest 3 on Virtual Desktop / Link.
echo Rebuild the scene: UE console ^> py "%TOOLS:\=/%/c2_build.py"
pause
