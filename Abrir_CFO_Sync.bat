@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title CFO Sync :: Control Deck

for /f %%e in ('echo prompt $E^| cmd') do set "ESC=%%e"
set "C_PRIMARY=%ESC%[92m"
set "C_ACCENT=%ESC%[96m"
set "C_MUTED=%ESC%[90m"
set "C_WARN=%ESC%[93m"
set "C_ERR=%ESC%[91m"
set "C_RST=%ESC%[0m"

set "MENU_ROOT=%~dp0"
if "%MENU_ROOT:~-1%"=="\" set "MENU_ROOT=%MENU_ROOT:~0,-1%"

if exist "C:\CFO-Sync\settings\setup_docker_server.ps1" (
    set "APP_ROOT=C:\CFO-Sync"
) else (
    set "APP_ROOT=%MENU_ROOT%"
)

set "HOST_ROOT=C:\srv"
set "DOCKER_SETUP_SCRIPT=%APP_ROOT%\settings\setup_docker_server.ps1"
set "DOCKER_COMPOSE_FILE=%APP_ROOT%\settings\docker-compose.server.yml"
set "DOCKER_ENV_FILE=%APP_ROOT%\settings\docker-server.env"

goto :main_menu

:draw_header
cls
echo %C_ACCENT%+--------------------------------------------------------------+%C_RST%
echo %C_ACCENT%^|%C_PRIMARY% CFO Sync :: Dev Terminal Control Deck                       %C_ACCENT%^|%C_RST%
echo %C_ACCENT%+--------------------------------------------------------------+%C_RST%
echo %C_MUTED%APP_ROOT : %APP_ROOT%%C_RST%
echo %C_MUTED%HOST_ROOT: %HOST_ROOT%%C_RST%
echo.
exit /b

:main_menu
call :draw_header
echo %C_PRIMARY%[1]%C_RST% Ambiente Docker
echo %C_PRIMARY%[2]%C_RST% Scripts
echo %C_PRIMARY%[3]%C_RST% Logs
echo %C_PRIMARY%[4]%C_RST% Servidor
echo %C_PRIMARY%[0]%C_RST% Sair
echo.
set "main_choice="
set /p "main_choice=Escolha uma opcao: "

if "%main_choice%"=="1" goto :docker_menu
if "%main_choice%"=="2" goto :scripts_menu
if "%main_choice%"=="3" goto :logs_menu
if "%main_choice%"=="4" goto :server_menu
if "%main_choice%"=="0" goto :exit_menu

echo %C_WARN%Opcao invalida.%C_RST%
call :press_enter
goto :main_menu

:docker_menu
call :draw_header
echo %C_PRIMARY%Docker / Ambiente%C_RST%
echo %C_PRIMARY%[1]%C_RST% Criar ambiente automatico (server apenas)
echo %C_PRIMARY%[2]%C_RST% Criar ambiente automatico (server + tunnel)
echo %C_PRIMARY%[3]%C_RST% Subir stack (server apenas)
echo %C_PRIMARY%[4]%C_RST% Subir stack (server + tunnel)
echo %C_PRIMARY%[5]%C_RST% Parar stack
echo %C_PRIMARY%[6]%C_RST% Status dos containers
echo %C_PRIMARY%[7]%C_RST% Logs do servidor (tail 200)
echo %C_PRIMARY%[8]%C_RST% Logs do tunnel (tail 200)
echo %C_PRIMARY%[9]%C_RST% Recriar server_access.json
echo %C_PRIMARY%[0]%C_RST% Voltar
echo.
set "docker_choice="
set /p "docker_choice=Escolha uma opcao: "

if "%docker_choice%"=="1" call :docker_bootstrap_no_tunnel & goto :docker_after
if "%docker_choice%"=="2" call :docker_bootstrap_with_tunnel & goto :docker_after
if "%docker_choice%"=="3" call :docker_up_server & goto :docker_after
if "%docker_choice%"=="4" call :docker_up_all & goto :docker_after
if "%docker_choice%"=="5" call :docker_down_all & goto :docker_after
if "%docker_choice%"=="6" call :docker_ps & goto :docker_after
if "%docker_choice%"=="7" call :docker_logs_server & goto :docker_after
if "%docker_choice%"=="8" call :docker_logs_tunnel & goto :docker_after
if "%docker_choice%"=="9" call :docker_recreate_access & goto :docker_after
if "%docker_choice%"=="0" goto :main_menu

echo %C_WARN%Opcao invalida.%C_RST%
:docker_after
call :press_enter
goto :docker_menu

:scripts_menu
call :draw_header
echo %C_PRIMARY%Scripts / Testes%C_RST%
echo %C_PRIMARY%[1]%C_RST% Selecionar script e testar (py_compile)
echo %C_PRIMARY%[2]%C_RST% Selecionar script e executar manualmente
echo %C_PRIMARY%[3]%C_RST% Teste rapido em todos os scripts (*.py)
echo %C_PRIMARY%[0]%C_RST% Voltar
echo.
set "scripts_choice="
set /p "scripts_choice=Escolha uma opcao: "

if "%scripts_choice%"=="1" call :script_select_and_compile & goto :scripts_after
if "%scripts_choice%"=="2" call :script_select_and_run & goto :scripts_after
if "%scripts_choice%"=="3" call :script_compile_all & goto :scripts_after
if "%scripts_choice%"=="0" goto :main_menu

echo %C_WARN%Opcao invalida.%C_RST%
:scripts_after
call :press_enter
goto :scripts_menu

:logs_menu
call :draw_header
echo %C_PRIMARY%Logs%C_RST%
echo %C_PRIMARY%[1]%C_RST% Selecionar log local e visualizar (tail 120)
echo %C_PRIMARY%[2]%C_RST% Selecionar log local e acompanhar (tail -Wait)
echo %C_PRIMARY%[3]%C_RST% Ver logs do container servidor (tail 200)
echo %C_PRIMARY%[4]%C_RST% Ver logs do container tunnel (tail 200)
echo %C_PRIMARY%[5]%C_RST% Seguir logs do container servidor (-f)
echo %C_PRIMARY%[0]%C_RST% Voltar
echo.
set "logs_choice="
set /p "logs_choice=Escolha uma opcao: "

if "%logs_choice%"=="1" call :log_select_and_view & goto :logs_after
if "%logs_choice%"=="2" call :log_select_and_follow & goto :logs_after
if "%logs_choice%"=="3" call :docker_logs_server & goto :logs_after
if "%logs_choice%"=="4" call :docker_logs_tunnel & goto :logs_after
if "%logs_choice%"=="5" call :docker_logs_server_follow & goto :logs_after
if "%logs_choice%"=="0" goto :main_menu

echo %C_WARN%Opcao invalida.%C_RST%
:logs_after
call :press_enter
goto :logs_menu

:server_menu
call :draw_header
echo %C_PRIMARY%Servidor / Diagnostico%C_RST%
echo %C_PRIMARY%[1]%C_RST% Analise geral (health + compose ps + porta 8088)
echo %C_PRIMARY%[2]%C_RST% Ver o que esta sendo executado
echo %C_PRIMARY%[3]%C_RST% Ver consumo (docker stats + top memoria)
echo %C_PRIMARY%[4]%C_RST% Reiniciar container cfo-sync-server
echo %C_PRIMARY%[5]%C_RST% Outras opcoes (atalhos uteis)
echo %C_PRIMARY%[0]%C_RST% Voltar
echo.
set "server_choice="
set /p "server_choice=Escolha uma opcao: "

if "%server_choice%"=="1" call :server_general_analysis & goto :server_after
if "%server_choice%"=="2" call :server_whats_running & goto :server_after
if "%server_choice%"=="3" call :server_resource_usage & goto :server_after
if "%server_choice%"=="4" call :server_restart & goto :server_after
if "%server_choice%"=="5" call :server_other_options & goto :server_after
if "%server_choice%"=="0" goto :main_menu

echo %C_WARN%Opcao invalida.%C_RST%
:server_after
call :press_enter
goto :server_menu

:docker_bootstrap_no_tunnel
call :ensure_setup_script || exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -File "%DOCKER_SETUP_SCRIPT%" -HostRoot "%HOST_ROOT%"
exit /b %errorlevel%

:docker_bootstrap_with_tunnel
call :ensure_setup_script || exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -File "%DOCKER_SETUP_SCRIPT%" -HostRoot "%HOST_ROOT%" -WithTunnel
exit /b %errorlevel%

:docker_recreate_access
call :ensure_setup_script || exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -File "%DOCKER_SETUP_SCRIPT%" -HostRoot "%HOST_ROOT%" -ForceRecreateAccess
exit /b %errorlevel%

:docker_up_server
call :ensure_compose || exit /b 1
docker compose --env-file "%DOCKER_ENV_FILE%" -f "%DOCKER_COMPOSE_FILE%" up -d cfo-sync-server
exit /b %errorlevel%

:docker_up_all
call :ensure_compose || exit /b 1
docker compose --env-file "%DOCKER_ENV_FILE%" -f "%DOCKER_COMPOSE_FILE%" --profile tunnel up -d
exit /b %errorlevel%

:docker_down_all
call :ensure_compose || exit /b 1
docker compose --env-file "%DOCKER_ENV_FILE%" -f "%DOCKER_COMPOSE_FILE%" down
exit /b %errorlevel%

:docker_ps
call :ensure_compose || exit /b 1
docker compose --env-file "%DOCKER_ENV_FILE%" -f "%DOCKER_COMPOSE_FILE%" ps
exit /b %errorlevel%

:docker_logs_server
call :ensure_compose || exit /b 1
docker compose --env-file "%DOCKER_ENV_FILE%" -f "%DOCKER_COMPOSE_FILE%" logs --tail 200 cfo-sync-server
exit /b %errorlevel%

:docker_logs_tunnel
call :ensure_compose || exit /b 1
docker compose --env-file "%DOCKER_ENV_FILE%" -f "%DOCKER_COMPOSE_FILE%" logs --tail 200 cfo-sync-tunnel
exit /b %errorlevel%

:docker_logs_server_follow
call :ensure_compose || exit /b 1
docker compose --env-file "%DOCKER_ENV_FILE%" -f "%DOCKER_COMPOSE_FILE%" logs -f cfo-sync-server
exit /b %errorlevel%

:server_general_analysis
call :ensure_compose || exit /b 1
echo %C_ACCENT%[Healthcheck]%C_RST%
powershell -NoProfile -Command "try { irm 'http://127.0.0.1:8088/v1/health' | ConvertTo-Json -Depth 6 } catch { Write-Host 'Falha ao chamar /v1/health:'; Write-Host $_.Exception.Message; exit 1 }"
echo.
echo %C_ACCENT%[Containers]%C_RST%
docker compose --env-file "%DOCKER_ENV_FILE%" -f "%DOCKER_COMPOSE_FILE%" ps
echo.
echo %C_ACCENT%[Porta 8088]%C_RST%
netstat -ano | findstr :8088
exit /b 0

:server_whats_running
echo %C_ACCENT%[Processos Python/Docker]%C_RST%
powershell -NoProfile -Command "Get-Process | Where-Object { $_.ProcessName -match 'python|docker|cloudflared|uvicorn' } | Sort-Object ProcessName | Format-Table Id,ProcessName,CPU,WS -AutoSize"
echo.
echo %C_ACCENT%[Conexoes de rede - 8088]%C_RST%
netstat -ano | findstr :8088
echo.
if exist "%DOCKER_COMPOSE_FILE%" (
    echo %C_ACCENT%[Containers]%C_RST%
    docker compose --env-file "%DOCKER_ENV_FILE%" -f "%DOCKER_COMPOSE_FILE%" ps
)
exit /b 0

:server_resource_usage
echo %C_ACCENT%[Docker stats]%C_RST%
docker stats --no-stream cfo-sync-server cfo-sync-tunnel 2>nul
if errorlevel 1 (
    echo %C_WARN%Nao foi possivel coletar docker stats para os containers esperados.%C_RST%
)
echo.
echo %C_ACCENT%[Top processos por memoria]%C_RST%
powershell -NoProfile -Command "Get-Process | Sort-Object WS -Descending | Select-Object -First 12 Id,ProcessName,@{Name='MemMB';Expression={[math]::Round($_.WS/1MB,2)}},CPU | Format-Table -AutoSize"
exit /b 0

:server_restart
call :ensure_compose || exit /b 1
docker compose --env-file "%DOCKER_ENV_FILE%" -f "%DOCKER_COMPOSE_FILE%" restart cfo-sync-server
exit /b %errorlevel%

:server_other_options
echo %C_ACCENT%Atalhos uteis:%C_RST%
echo 1) Abrir APP root  : explorer "%APP_ROOT%"
echo 2) Abrir HOST root : explorer "%HOST_ROOT%"
echo 3) Ver acesso RBAC : notepad "%HOST_ROOT%\cfo_sync\server_access.json"
echo 4) Health manual   : http://127.0.0.1:8088/v1/health
echo.
echo %C_MUTED%Digite o comando desejado na linha abaixo, ou Enter para voltar.%C_RST%
set "srv_cmd="
set /p "srv_cmd=> "
if not defined srv_cmd exit /b 0
%srv_cmd%
exit /b %errorlevel%

:script_select_and_compile
call :build_script_list
if %SCRIPT_COUNT% EQU 0 (
    echo %C_WARN%Nenhum script .py encontrado em "%APP_ROOT%\scripts".%C_RST%
    exit /b 1
)
call :show_scripts
set "script_idx="
set /p "script_idx=Escolha o numero do script: "
call set "SELECTED_SCRIPT=%%SCRIPT[%script_idx%]%%"
if not defined SELECTED_SCRIPT (
    echo %C_WARN%Indice invalido.%C_RST%
    exit /b 1
)
echo.
echo %C_ACCENT%Teste rapido (py_compile):%C_RST% %SELECTED_SCRIPT%
python -m py_compile "%SELECTED_SCRIPT%"
if errorlevel 1 (
    echo %C_ERR%Falha no teste rapido.%C_RST%
    exit /b 1
)
echo %C_PRIMARY%Script validado com sucesso.%C_RST%
exit /b 0

:script_select_and_run
call :build_script_list
if %SCRIPT_COUNT% EQU 0 (
    echo %C_WARN%Nenhum script .py encontrado em "%APP_ROOT%\scripts".%C_RST%
    exit /b 1
)
call :show_scripts
set "script_idx="
set /p "script_idx=Escolha o numero do script: "
call set "SELECTED_SCRIPT=%%SCRIPT[%script_idx%]%%"
if not defined SELECTED_SCRIPT (
    echo %C_WARN%Indice invalido.%C_RST%
    exit /b 1
)
echo.
echo %C_ACCENT%Executando:%C_RST% %SELECTED_SCRIPT%
python "%SELECTED_SCRIPT%"
exit /b %errorlevel%

:script_compile_all
call :build_script_list
if %SCRIPT_COUNT% EQU 0 (
    echo %C_WARN%Nenhum script .py encontrado em "%APP_ROOT%\scripts".%C_RST%
    exit /b 1
)
set /a OK_COUNT=0
set /a FAIL_COUNT=0
for /l %%i in (1,1,%SCRIPT_COUNT%) do (
    call set "CURRENT=%%SCRIPT[%%i]%%"
    echo.
    echo %C_ACCENT%[%%i/%SCRIPT_COUNT%]%C_RST% !CURRENT!
    python -m py_compile "!CURRENT!"
    if errorlevel 1 (
        set /a FAIL_COUNT+=1
        echo %C_ERR%Falhou.%C_RST%
    ) else (
        set /a OK_COUNT+=1
        echo %C_PRIMARY%OK.%C_RST%
    )
)
echo.
echo %C_PRIMARY%Resumo:%C_RST% OK=%OK_COUNT%  FALHAS=%FAIL_COUNT%
if %FAIL_COUNT% GTR 0 exit /b 1
exit /b 0

:log_select_and_view
call :build_log_list
if %LOG_COUNT% EQU 0 (
    echo %C_WARN%Nenhum arquivo encontrado em "%APP_ROOT%\logs".%C_RST%
    exit /b 1
)
call :show_logs
set "log_idx="
set /p "log_idx=Escolha o numero do log: "
call set "SELECTED_LOG=%%LOG[%log_idx%]%%"
if not defined SELECTED_LOG (
    echo %C_WARN%Indice invalido.%C_RST%
    exit /b 1
)
echo.
echo %C_ACCENT%Visualizando ultimas 120 linhas:%C_RST%
powershell -NoProfile -Command "Get-Content -LiteralPath '%SELECTED_LOG%' -Tail 120"
exit /b %errorlevel%

:log_select_and_follow
call :build_log_list
if %LOG_COUNT% EQU 0 (
    echo %C_WARN%Nenhum arquivo encontrado em "%APP_ROOT%\logs".%C_RST%
    exit /b 1
)
call :show_logs
set "log_idx="
set /p "log_idx=Escolha o numero do log: "
call set "SELECTED_LOG=%%LOG[%log_idx%]%%"
if not defined SELECTED_LOG (
    echo %C_WARN%Indice invalido.%C_RST%
    exit /b 1
)
echo.
echo %C_ACCENT%Acompanhando log (Ctrl+C para sair):%C_RST%
powershell -NoProfile -Command "Get-Content -LiteralPath '%SELECTED_LOG%' -Tail 120 -Wait"
exit /b %errorlevel%

:build_script_list
set /a SCRIPT_COUNT=0
for /f "delims=" %%f in ('dir /b /s "%APP_ROOT%\scripts\*.py" 2^>nul') do (
    set /a SCRIPT_COUNT+=1
    set "SCRIPT[!SCRIPT_COUNT!]=%%f"
)
exit /b 0

:show_scripts
echo.
echo %C_ACCENT%Scripts disponiveis:%C_RST%
for /l %%i in (1,1,%SCRIPT_COUNT%) do (
    call set "TMP=%%SCRIPT[%%i]%%"
    call set "REL=%%TMP:%APP_ROOT%\=%%"
    echo   [%%i] !REL!
)
echo.
exit /b 0

:build_log_list
set /a LOG_COUNT=0
for /f "delims=" %%f in ('dir /b /s "%APP_ROOT%\logs\*" 2^>nul') do (
    if not exist "%%f\" (
        set /a LOG_COUNT+=1
        set "LOG[!LOG_COUNT!]=%%f"
    )
)
exit /b 0

:show_logs
echo.
echo %C_ACCENT%Logs disponiveis:%C_RST%
for /l %%i in (1,1,%LOG_COUNT%) do (
    call set "TMP=%%LOG[%%i]%%"
    call set "REL=%%TMP:%APP_ROOT%\=%%"
    echo   [%%i] !REL!
)
echo.
exit /b 0

:ensure_setup_script
if not exist "%DOCKER_SETUP_SCRIPT%" (
    echo %C_ERR%Script nao encontrado: %DOCKER_SETUP_SCRIPT%%C_RST%
    exit /b 1
)
call :check_docker
exit /b %errorlevel%

:ensure_compose
if not exist "%DOCKER_COMPOSE_FILE%" (
    echo %C_ERR%Arquivo nao encontrado: %DOCKER_COMPOSE_FILE%%C_RST%
    exit /b 1
)
if not exist "%DOCKER_ENV_FILE%" (
    echo %C_WARN%Env nao encontrado: %DOCKER_ENV_FILE%%C_RST%
    echo %C_MUTED%Rode "Criar ambiente automatico" para gerar esse arquivo.%C_RST%
    exit /b 1
)
call :check_docker
exit /b %errorlevel%

:check_docker
where docker >nul 2>&1
if errorlevel 1 (
    echo %C_ERR%Docker nao encontrado no PATH.%C_RST%
    exit /b 1
)
exit /b 0

:press_enter
echo.
set /p "=Pressione Enter para continuar..."
echo.
exit /b 0

:exit_menu
echo.
echo %C_MUTED%Encerrando menu.%C_RST%
endlocal
exit /b 0
