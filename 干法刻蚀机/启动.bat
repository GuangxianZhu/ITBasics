@echo off
setlocal
cd /d "%~dp0"
where git >nul 2>nul && git pull --ff-only origin main
for %%f in ("output\*.html") do start "" "%%f"
endlocal
