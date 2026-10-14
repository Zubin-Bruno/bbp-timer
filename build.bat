@echo off
cd /d "%~dp0"

python -m pip install -r requirements.txt || goto :err
python -m PyInstaller --noconfirm --onefile --windowed --name BBPTimer --paths bbp_timer bbp_timer\main.py || goto :err

powershell -NoProfile -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\BBPTimer.lnk'); $s.TargetPath = '%~dp0dist\BBPTimer.exe'; $s.WorkingDirectory = '%~dp0dist'; $s.Save()" || goto :err

echo.
echo Listo: dist\BBPTimer.exe y acceso directo BBPTimer en el Escritorio.
pause
exit /b 0

:err
echo.
echo Error durante la compilacion.
pause
exit /b 1
