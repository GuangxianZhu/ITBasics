@echo off
rem One-click: 1) git pull main  2) sync scripts to Documents\UE-MCP-Tools
rem            3) open VRStudy in UE 5.8  4) wait for Unreal MCP (127.0.0.1:8000)  5) start Claude Code in the project
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

rem ---- sync UE python scripts (UE console runs them from Documents\UE-MCP-Tools) ----
set "TOOLS=%USERPROFILE%\Documents\UE-MCP-Tools"
if not exist "%TOOLS%" mkdir "%TOOLS%"
copy /Y "%~dp0*.py" "%TOOLS%\" >nul
copy /Y "%~dp0test_mcp.ps1" "%TOOLS%\" >nul
echo Scripts synced to %TOOLS%

rem ---- open the project ----
set "PROJ=%USERPROFILE%\Documents\Unreal Projects\VRStudy"
if not exist "%PROJ%\VRStudy.uproject" (
    echo [ERROR] %PROJ%\VRStudy.uproject not found.
    pause
    exit /b 1
)
tasklist /FI "IMAGENAME eq UnrealEditor.exe" | find /I "UnrealEditor.exe" >nul
if errorlevel 1 (
    echo Opening VRStudy in Unreal Editor...
    start "" "%PROJ%\VRStudy.uproject"
) else (
    echo Unreal Editor is already running.
)

rem ---- wait for MCP server (Editor Preferences > Model Context Protocol > Auto Start Server is ON) ----
set /a N=0
:wait
powershell -NoProfile -Command "if((Test-NetConnection 127.0.0.1 -Port 8000 -WarningAction SilentlyContinue).TcpTestSucceeded){exit 0}else{exit 1}"
if not errorlevel 1 goto ready
set /a N+=1
if %N% GEQ 60 (
    echo [WARN] MCP port 8000 not ready after 5 min. In UE console run: ModelContextProtocol.StartServer
    pause
    exit /b 1
)
echo Waiting for Unreal MCP on 127.0.0.1:8000 ... (%N%/60)
timeout /t 5 /nobreak >nul
goto wait

:ready
echo Unreal MCP is ready. Starting Claude Code in %PROJ%
cd /d "%PROJ%"
set TERM=xterm-256color
where claude >nul 2>nul
if errorlevel 1 (
    echo [ERROR] claude not found. Install: irm https://claude.ai/install.ps1 ^| iex
    pause
    exit /b 1
)
claude
