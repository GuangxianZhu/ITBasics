@echo off
cd /d "%~dp0"
echo Installing packages...
python -m pip install --user pystray pillow
if errorlevel 1 (
  py -m pip install --user pystray pillow
  start "" pyw "%~dp0night_dimmer.py"
) else (
  start "" pythonw "%~dp0night_dimmer.py"
)
echo.
echo Done. Look for the moon icon in the system tray (bottom-right).
echo It will start automatically next time you log in.
pause
