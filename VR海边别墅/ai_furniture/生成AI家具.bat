@echo off
rem AI furniture: text -> Z-Image product photo -> Hunyuan3D 2.1 shape (.glb), using GenImgs' ComfyUI
rem   double-click            = make every item that has no model yet
rem   with arguments, e.g.    = generate_furniture.bat --only sofa,plant
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"

rem ---- update from GitHub main ----
where git >nul 2>nul
if not errorlevel 1 (
    git -C "%~dp0" rev-parse --is-inside-work-tree >nul 2>nul
    if not errorlevel 1 (
        echo Checking for updates on main...
        git -C "%~dp0" pull --ff-only origin main
        if errorlevel 1 echo [WARN] Update failed ^(offline or local changes^). Using current version.
    )
)

rem ---- find GenImgs: genimgs_path.txt > ..\..\..\GenImgs > C:\work\GenImgs ----
set "GI="
if exist "%~dp0genimgs_path.txt" set /p GI=<"%~dp0genimgs_path.txt"
if not defined GI if exist "%~dp0..\..\..\GenImgs\gen.py" set "GI=%~dp0..\..\..\GenImgs"
if not defined GI if exist "C:\work\GenImgs\gen.py" set "GI=C:\work\GenImgs"
if not defined GI (
    echo [ERROR] GenImgs not found. Put its full path into ai_furniture\genimgs_path.txt
    pause
    exit /b 1
)
set "PY=%GI%\.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [ERROR] %GI%\.venv not found. Run GenImgs\install_comfyui.bat first.
    pause
    exit /b 1
)
echo Using GenImgs: "%GI%"

rem ---- Hunyuan3D 2.1 model (one file, several GB, resumable) ----
set "CK=%GI%\ComfyUI\models\checkpoints\hunyuan_3d_v2.1.safetensors"
if not exist "%CK%" (
    echo.
    echo Downloading Hunyuan3D 2.1 model ^(several GB, one time only, resumable^) ...
    curl.exe -L --fail --retry 5 --retry-delay 3 -C - -o "%CK%.part" "https://huggingface.co/Comfy-Org/hunyuan3D_2.1_repackaged/resolve/main/hunyuan_3d_v2.1.safetensors"
    if errorlevel 1 (
        echo [ERROR] Download failed. Run this bat again - it resumes where it stopped.
        pause
        exit /b 1
    )
    move /y "%CK%.part" "%CK%" >nul
)

rem ---- generate ----
echo.
"%PY%" "%~dp0gen_furniture.py" %*
echo.
echo Next: run the Godot launcher bat in the parent folder - new furniture is placed automatically.
pause
