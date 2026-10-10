@echo off
cd /d "%~dp0"
echo Checking yt-dlp (first run installs it, later runs update it)...
python -m pip install --user -U -q yt-dlp
if errorlevel 1 (
  py -m pip install --user -U -q yt-dlp
  start "" pyw "%~dp0subtitle_gui.py"
) else (
  start "" pythonw "%~dp0subtitle_gui.py"
)
