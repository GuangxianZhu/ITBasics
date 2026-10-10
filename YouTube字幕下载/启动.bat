@echo off
cd /d "%~dp0"
echo Checking yt-dlp + curl_cffi + deno (first run installs, later runs update)...
python -m pip install --user -U -q "yt-dlp[default,curl-cffi]" deno
if errorlevel 1 (
  py -m pip install --user -U -q "yt-dlp[default,curl-cffi]" deno
  start "" pyw "%~dp0subtitle_gui.py"
) else (
  start "" pythonw "%~dp0subtitle_gui.py"
)
