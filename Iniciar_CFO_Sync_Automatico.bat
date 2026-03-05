@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "APP_DIR=%CD%"
set "VENV_PY=%APP_DIR%\.venv\Scripts\python.exe"
set "PYTHON_EXE="
set "PY_VERSION=3.11.9"
set "PY_INSTALL_DIR=%LOCALAPPDATA%\Programs\Python\Python311"
set "PY_INSTALLER=%TEMP%\python-%PY_VERSION%-amd64.exe"

echo ============================================
echo CFO Sync - Inicializacao automatica
echo ============================================
echo.

call :find_python
if not defined PYTHON_EXE (
  call :install_python
  if errorlevel 1 goto :error
  call :find_python
)

if not defined PYTHON_EXE (
  echo Nao foi possivel localizar o Python apos a instalacao.
  goto :error
)

if not exist "%VENV_PY%" (
  echo [1/3] Criando ambiente virtual...
  "%PYTHON_EXE%" -m venv "%APP_DIR%\.venv"
  if errorlevel 1 (
    echo Falha ao criar ambiente virtual.
    goto :error
  )
) else (
  echo [1/3] Ambiente virtual ja existe.
)

echo [2/3] Instalando/atualizando dependencias...
"%VENV_PY%" -m pip install -r "%APP_DIR%\requirements.txt"
if errorlevel 1 (
  echo Falha ao instalar dependencias.
  goto :error
)

echo [3/3] Abrindo aplicativo...
set "PYTHONPATH=%APP_DIR%\src"
"%VENV_PY%" "%APP_DIR%\launcher_desktop.py"
exit /b 0

:find_python
set "PYTHON_EXE="

if exist "%PY_INSTALL_DIR%\python.exe" (
  set "PYTHON_EXE=%PY_INSTALL_DIR%\python.exe"
  goto :eof
)

for /f "delims=" %%I in ('py -3.11 -c "import sys; print(sys.executable)" 2^>nul') do (
  if not defined PYTHON_EXE set "PYTHON_EXE=%%I"
)
if defined PYTHON_EXE goto :eof

for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do (
  if not defined PYTHON_EXE set "PYTHON_EXE=%%I"
)
if defined PYTHON_EXE goto :eof

for /f "delims=" %%I in ('where python 2^>nul') do (
  if not defined PYTHON_EXE set "PYTHON_EXE=%%I"
)
goto :eof

:install_python
echo Python nao encontrado. Instalando automaticamente (primeira execucao)...
echo.
echo Baixando Python %PY_VERSION%...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/%PY_VERSION%/python-%PY_VERSION%-amd64.exe' -OutFile '%PY_INSTALLER%'"
if errorlevel 1 (
  echo Falha no download do instalador do Python.
  echo Verifique internet e permissao de rede, depois tente novamente.
  exit /b 1
)

echo Instalando Python silenciosamente...
start /wait "" "%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=0 Include_pip=1 Include_tcltk=1 Include_test=0 Include_doc=0 Shortcuts=0
if errorlevel 1 (
  echo Falha na instalacao silenciosa do Python.
  exit /b 1
)

exit /b 0

:error
echo.
echo Nao foi possivel iniciar o CFO Sync.
echo Se o erro persistir, envie este print para o time tecnico.
pause
exit /b 1
