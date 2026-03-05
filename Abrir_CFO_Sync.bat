@echo off
cd /d "%~dp0"
call "%~dp0Iniciar_CFO_Sync_Automatico.bat"
exit /b %errorlevel%
