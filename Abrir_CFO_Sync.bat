@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto :error
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

set PYTHONPATH=%CD%\src
".venv\Scripts\python.exe" launcher_desktop.py
exit /b 0

:error
echo.
echo Falha ao preparar/iniciar o app.
pause
exit /b 1
