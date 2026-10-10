@echo off
cd /d "%~dp0"
echo Checking components (first run installs PySide6 / ffmpeg, may take a few minutes)...
python -m pip install --user -q PySide6 imageio-ffmpeg deno mutagen
if errorlevel 1 goto usepy
python -m pip install --user -U -q "yt-dlp[default,curl-cffi]"
start "" pythonw "%~dp0app.py"
goto :eof
:usepy
py -m pip install --user -q PySide6 imageio-ffmpeg deno mutagen
py -m pip install --user -U -q "yt-dlp[default,curl-cffi]"
start "" pyw "%~dp0app.py"
