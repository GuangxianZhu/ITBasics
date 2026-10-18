@echo off
rem One-click: seaside villa "viewing version" in Unreal Engine 5.8 (project VillaVR, level L_Villa)
rem   1) git pull main   2) sync UE python scripts to Documents\UE-MCP-Tools\villa
rem   3) choose rendering mode (forward / lumen)   4) open VillaVR
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

rem ---- sync scripts (UE console runs them from Documents\UE-MCP-Tools\villa) ----
set "TOOLS=%USERPROFILE%\Documents\UE-MCP-Tools\villa"
if not exist "%TOOLS%" mkdir "%TOOLS%"
copy /Y "%~dp0*.py" "%TOOLS%\" >nul
copy /Y "%~dp0markers.json" "%TOOLS%\" >nul
copy /Y "%~dp0names.json" "%TOOLS%\" >nul
echo Scripts synced to %TOOLS%
if not exist "%TOOLS%\villa_ue.glb" (
    echo [INFO] villa_ue.glb missing. Building it from ..\godot\model\villa.glb ...
    pushd "%TOOLS%"
    python -m pip install -q pygltflib pypinyin
    python "%~dp0prep_glb.py" "%~dp0..\godot\model\villa.glb" "%~dp0..\godot\model\villa_meta.json"
    popd
)

rem ---- rendering mode ----
set "PROJ=%USERPROFILE%\Documents\Unreal Projects\VillaVR"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0gi_mode.ps1" status
echo.
echo   1 = forward  (VR template default: forward shading + MSAA, no Lumen)
echo   2 = lumen    (deferred + Lumen real-time GI + TSR, heavier)
echo   Enter = keep current
set "M="
set /p M=Choose rendering mode: 
if "%M%"=="1" powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0gi_mode.ps1" forward
if "%M%"=="2" powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0gi_mode.ps1" lumen

rem ---- open the project ----
if not exist "%PROJ%\VillaVR.uproject" (
    echo [ERROR] %PROJ%\VillaVR.uproject not found.
    pause
    exit /b 1
)
tasklist /FI "IMAGENAME eq UnrealEditor.exe" | find /I "UnrealEditor.exe" >nul
if errorlevel 1 (
    echo Opening VillaVR in Unreal Editor ^(first start after switching mode compiles shaders, can take minutes^)...
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
echo Then: toolbar Play dropdown ^> VR Preview, with Quest 3 on Virtual Desktop / Link.
pause
