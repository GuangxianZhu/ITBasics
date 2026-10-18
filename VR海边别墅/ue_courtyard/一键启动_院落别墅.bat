@echo off
rem One-click: courtyard villa (Cycladic layout v2) in Unreal Engine 5.8 - project VillaVR, level L_Courtyard
rem   1) git pull main   2) sync UE python scripts to Documents\UE-MCP-Tools\court
rem   3) choose rendering mode (forward / lumen, shared with ..\ue\gi_mode.ps1)   4) open VillaVR
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
echo Scripts synced to %TOOLS%

rem ---- rendering mode ----
set "PROJ=%USERPROFILE%\Documents\Unreal Projects\VillaVR"
set "GI=%~dp0..\ue\gi_mode.ps1"
if exist "%GI%" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%GI%" status
    echo.
    echo   1 = forward  ^(VR template default: forward shading + MSAA, no Lumen^)
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
    start "" "%PROJ%\VillaVR.uproject"
) else (
    echo [WARN] Unreal Editor is already running. Close it and run this again for a mode change to apply.
)
echo Then: toolbar Play dropdown ^> VR Preview, with Quest 3 on Virtual Desktop / Link.
echo Rebuild the scene: UE console ^> py "%TOOLS:\=/%/c2_build.py"
pause
