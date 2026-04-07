param(
    [string]$HostRoot = "C:\srv",
    [int]$Port = 8088,
    [int]$Workers = 2,
    [switch]$WithTunnel,
    [string]$TunnelToken = "",
    [string]$TunnelHostname = "",
    [switch]$ForceRecreateAccess
)

$ErrorActionPreference = "Stop"

function Invoke-Compose {
    param([string[]]$Args)
    & docker compose --env-file $script:EnvFile -f $script:ComposeFile @Args
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao executar docker compose: $($Args -join ' ')"
    }
}

function Convert-ToDockerPath {
    param([string]$PathValue)
    return ((Resolve-Path $PathValue).Path -replace "\\", "/")
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker nao encontrado no PATH. Instale/abra o Docker Desktop e tente novamente."
}

try {
    docker info *> $null
}
catch {
    throw "Docker nao esta em execucao. Abra o Docker Desktop e tente novamente."
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$script:ComposeFile = Join-Path $PSScriptRoot "docker-compose.server.yml"
$script:EnvFile = Join-Path $PSScriptRoot "docker-server.env"

$TunnelToken = $TunnelToken.Trim()
$TunnelHostname = $TunnelHostname.Trim()

if (Test-Path $script:EnvFile) {
    $existingEnv = @{}
    foreach ($line in (Get-Content -Path $script:EnvFile -ErrorAction SilentlyContinue)) {
        if ($line -match "^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$") {
            $existingEnv[$matches[1]] = $matches[2]
        }
    }

    if (-not $TunnelToken -and $existingEnv.ContainsKey("CLOUDFLARE_TUNNEL_TOKEN")) {
        $TunnelToken = $existingEnv["CLOUDFLARE_TUNNEL_TOKEN"]
    }
    if (-not $TunnelHostname -and $existingEnv.ContainsKey("CLOUDFLARE_TUNNEL_HOSTNAME")) {
        $TunnelHostname = $existingEnv["CLOUDFLARE_TUNNEL_HOSTNAME"]
    }
}

if (-not (Test-Path $script:ComposeFile)) {
    throw "Arquivo nao encontrado: $script:ComposeFile"
}

$hostRootAbsolute = [System.IO.Path]::GetFullPath($HostRoot)
$secretsDir = Join-Path $hostRootAbsolute "secrets"
$cfoSyncDir = Join-Path $hostRootAbsolute "cfo_sync"
$dataDir = Join-Path $hostRootAbsolute "data"
$appConfigPath = Join-Path $secretsDir "app_config.json"
$accessConfigPath = Join-Path $cfoSyncDir "server_access.json"

New-Item -ItemType Directory -Force -Path $hostRootAbsolute | Out-Null
New-Item -ItemType Directory -Force -Path $secretsDir | Out-Null
New-Item -ItemType Directory -Force -Path $cfoSyncDir | Out-Null
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

if (-not (Test-Path $appConfigPath)) {
    throw @"
Arquivo obrigatorio nao encontrado: $appConfigPath

Coloque o app_config.json dentro de $secretsDir e rode novamente.
Essa pasta (HostRoot) e a fonte unica dos dados do servidor.
"@
}

if ($WithTunnel -and -not $TunnelToken) {
    throw @"
Parametro obrigatorio ausente para tunnel nomeado.

Informe:
  -TunnelToken "SEU_TUNNEL_TOKEN"

Opcional:
  -TunnelHostname "ecfo.com.br"
"@
}

$dockerHostRoot = Convert-ToDockerPath -PathValue $hostRootAbsolute
$envLines = @(
    "CFO_SYNC_HOST_ROOT=$dockerHostRoot"
    "CFO_SYNC_SERVER_PORT=$Port"
    "CFO_SYNC_WORKERS=$Workers"
)
if ($TunnelToken) {
    $envLines += "CLOUDFLARE_TUNNEL_TOKEN=$TunnelToken"
}
if ($TunnelHostname) {
    $envLines += "CLOUDFLARE_TUNNEL_HOSTNAME=$TunnelHostname"
}
$envLines | Set-Content -Path $script:EnvFile -Encoding ascii

Write-Host ""
Write-Host "1/3 Build da imagem do servidor..."
Invoke-Compose @("build", "cfo-sync-server")

$shouldRecreateAccess = $ForceRecreateAccess -or (-not (Test-Path $accessConfigPath))
if ($shouldRecreateAccess) {
    Write-Host ""
    Write-Host "2/3 Gerando template de acesso (server_access.json)..."
    Invoke-Compose @(
        "run",
        "--rm",
        "cfo-sync-server",
        "python",
        "-m",
        "cfo_sync.server.main",
        "--init-access-template",
        "--access-config",
        "/srv/cfo_sync/server_access.json"
    )
    Write-Host "Template criado em: $accessConfigPath"
}
else {
    Write-Host ""
    Write-Host "2/3 Template de acesso ja existe, mantendo arquivo atual."
}

Write-Host ""
Write-Host "3/3 Subindo containers..."
if ($WithTunnel) {
    Invoke-Compose @("--profile", "tunnel", "up", "-d", "cfo-sync-server", "cfo-sync-tunnel")
}
else {
    Invoke-Compose @("up", "-d", "cfo-sync-server")
}

Write-Host ""
Write-Host "Status dos containers:"
Invoke-Compose @("ps")

Write-Host ""
Write-Host "Servidor local: http://127.0.0.1:$Port"
Write-Host "Healthcheck:   http://127.0.0.1:$Port/v1/health"

if ($WithTunnel) {
    $logOutput = & docker compose --env-file $script:EnvFile -f $script:ComposeFile logs --no-color cfo-sync-tunnel 2>$null
    $joinedLogs = ($logOutput -join "`n")
    $urlMatch = [regex]::Match($joinedLogs, "https://[a-zA-Z0-9\.\-]+")

    if ($TunnelHostname) {
        Write-Host "Tunnel URL:    https://$TunnelHostname"
    }
    elseif ($urlMatch.Success) {
        Write-Host "Tunnel URL:    $($urlMatch.Value)"
    }
    else {
        Write-Host "Tunnel URL:    tunnel nomeado ativo (confira o hostname no Cloudflare Dashboard)."
        Write-Host "Logs tunnel:   rode:"
        Write-Host "  docker compose --env-file `"$script:EnvFile`" -f `"$script:ComposeFile`" logs -f cfo-sync-tunnel"
    }
}

Write-Host ""
Write-Host "Arquivo de acesso: $accessConfigPath"
Write-Host "Edite esse arquivo para configurar tokens e permissoes por analista."

