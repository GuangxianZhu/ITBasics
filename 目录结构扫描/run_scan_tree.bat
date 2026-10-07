@echo off
rem Double-click to scan this folder and write file_structure.txt
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scan_tree.ps1"
echo.
pause
