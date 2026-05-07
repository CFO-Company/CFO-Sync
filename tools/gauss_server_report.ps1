param(
    [string]$HostRoot = "C:\srv",
    [string]$ServerUrl = "http://127.0.0.1:8088",
    [string]$RepoRoot = "",
    [string]$OutputDir = "",
    [int]$LogTail = 120
)

$ErrorActionPreference = "Continue"

function Get-NowIso {
    return (Get-Date).ToUniversalTime().ToString("o")
}

function Test-CommandAvailable {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Convert-ToSafeString {
    param([object]$Value)
    if ($null -eq $Value) {
        return ""
    }
    return [string]$Value
}

function Redact-SecretText {
    param([string]$Text)
    if (-not $Text) {
        return ""
    }

    $safe = $Text
    $patterns = @(
        '(?i)(Authorization:\s*Bearer\s+)[^\s"]+',
        '(?i)("token"\s*:\s*")[^"]+',
        '(?i)("access_token"\s*:\s*")[^"]+',
        '(?i)("refresh_token"\s*:\s*")[^"]+',
        '(?i)(CLOUDFLARE_TUNNEL_TOKEN\s*=\s*)[^\s]+',
        '(?i)(token\s*=\s*)[^\s]+',
        '(?i)(password\s*=\s*)[^\s]+',
        '(?i)(secret\s*=\s*)[^\s]+'
    )

    foreach ($pattern in $patterns) {
        $safe = [regex]::Replace($safe, $pattern, '${1}<redacted>')
    }
    return $safe
}

function Invoke-SafeCommand {
    param(
        [scriptblock]$Command,
        [string]$Fallback = ""
    )

    try {
        $output = & $Command 2>&1
        return @{
            ok = $true
            output = (($output | ForEach-Object { Convert-ToSafeString $_ }) -join "`n")
        }
    }
    catch {
        return @{
            ok = $false
            output = if ($Fallback) { $Fallback } else { $_.Exception.Message }
        }
    }
}

function Get-FilePresence {
    param([string]$PathValue)

    if (Test-Path -LiteralPath $PathValue -PathType Leaf) {
        $item = Get-Item -LiteralPath $PathValue
        return [ordered]@{
            path = $PathValue
            exists = $true
            bytes = $item.Length
            last_write = $item.LastWriteTimeUtc.ToString("o")
        }
    }

    return [ordered]@{
        path = $PathValue
        exists = $false
        bytes = $null
        last_write = $null
    }
}

function Get-DirectoryPresence {
    param([string]$PathValue)

    if (Test-Path -LiteralPath $PathValue -PathType Container) {
        $item = Get-Item -LiteralPath $PathValue
        return [ordered]@{
            path = $PathValue
            exists = $true
            last_write = $item.LastWriteTimeUtc.ToString("o")
        }
    }

    return [ordered]@{
        path = $PathValue
        exists = $false
        last_write = $null
    }
}

function Read-EnvFileSafe {
    param([string]$PathValue)

    if (-not (Test-Path -LiteralPath $PathValue -PathType Leaf)) {
        return @()
    }

    $items = @()
    foreach ($line in (Get-Content -LiteralPath $PathValue -ErrorAction SilentlyContinue)) {
        if ($line -match "^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$") {
            $name = $matches[1]
            $value = $matches[2]
            $isSensitive = $name -match "(?i)TOKEN|SECRET|PASSWORD|KEY"
            $items += [ordered]@{
                name = $name
                present = $true
                value = if ($isSensitive) { "<redacted>" } else { $value }
            }
        }
    }
    return $items
}

function Get-AccessSummary {
    param([string]$PathValue)

    $summary = [ordered]@{
        path = $PathValue
        exists = $false
        token_count = 0
        tokens = @()
        error = $null
    }

    if (-not (Test-Path -LiteralPath $PathValue -PathType Leaf)) {
        return $summary
    }

    $summary.exists = $true
    try {
        $json = Get-Content -LiteralPath $PathValue -Raw | ConvertFrom-Json
        $tokens = @($json.tokens)
        $summary.token_count = $tokens.Count
        $safeTokens = @()
        foreach ($token in $tokens) {
            $safeTokens += [ordered]@{
                name = $token.name
                allowed_platforms = @($token.allowed_platforms)
                can_manage_secrets = [bool]$token.can_manage_secrets
                token_present = -not [string]::IsNullOrWhiteSpace([string]$token.token)
            }
        }
        $summary.tokens = $safeTokens
    }
    catch {
        $summary.error = $_.Exception.Message
    }

    return $summary
}

function Get-GitSummary {
    param([string]$PathValue)

    $summary = [ordered]@{
        repo_root = $PathValue
        available = $false
        branch = $null
        commit = $null
        dirty = $null
        error = $null
    }

    if (-not $PathValue -or -not (Test-Path -LiteralPath $PathValue -PathType Container)) {
        $summary.error = "RepoRoot nao encontrado."
        return $summary
    }
    if (-not (Test-CommandAvailable "git")) {
        $summary.error = "git nao encontrado no PATH."
        return $summary
    }

    try {
        $summary.available = $true
        $summary.branch = (& git -C $PathValue rev-parse --abbrev-ref HEAD 2>$null)
        $summary.commit = (& git -C $PathValue rev-parse --short HEAD 2>$null)
        $status = (& git -C $PathValue status --porcelain 2>$null)
        $summary.dirty = -not [string]::IsNullOrWhiteSpace(($status -join ""))
    }
    catch {
        $summary.error = $_.Exception.Message
    }

    return $summary
}

function Get-HealthSummary {
    param([string]$BaseUrl)

    $url = $BaseUrl.TrimEnd("/") + "/v1/health"
    $summary = [ordered]@{
        url = $url
        ok = $false
        status = $null
        version = $null
        server_time = $null
        error = $null
    }

    try {
        $response = Invoke-RestMethod -Method Get -Uri $url -TimeoutSec 8
        $summary.ok = $true
        $summary.status = $response.status
        $summary.version = $response.version
        $summary.server_time = $response.server_time
    }
    catch {
        $summary.error = $_.Exception.Message
    }

    return $summary
}

function Get-DockerSummary {
    param(
        [string]$ComposeFile,
        [string]$EnvFile,
        [int]$Tail
    )

    $summary = [ordered]@{
        docker_available = Test-CommandAvailable "docker"
        docker_info_ok = $false
        compose_file = $ComposeFile
        env_file = $EnvFile
        containers = @()
        compose_ps = ""
        server_logs_tail = ""
        tunnel_logs_tail = ""
        error = $null
    }

    if (-not $summary.docker_available) {
        $summary.error = "docker nao encontrado no PATH."
        return $summary
    }

    $info = Invoke-SafeCommand { docker info }
    $summary.docker_info_ok = [bool]$info.ok

    $ps = Invoke-SafeCommand { docker ps --filter "name=cfo-sync" --format "{{.Names}}|{{.Status}}|{{.Ports}}" }
    if ($ps.ok -and $ps.output) {
        $containers = @()
        foreach ($line in ($ps.output -split "`n")) {
            if (-not $line.Trim()) {
                continue
            }
            $parts = $line -split "\|", 3
            $containers += [ordered]@{
                name = $parts[0]
                status = if ($parts.Count -gt 1) { $parts[1] } else { "" }
                ports = if ($parts.Count -gt 2) { $parts[2] } else { "" }
            }
        }
        $summary.containers = $containers
    }

    if ((Test-Path -LiteralPath $ComposeFile -PathType Leaf) -and (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
        $composePs = Invoke-SafeCommand { docker compose --env-file $EnvFile -f $ComposeFile ps }
        $summary.compose_ps = Redact-SecretText $composePs.output

        $serverLogs = Invoke-SafeCommand { docker compose --env-file $EnvFile -f $ComposeFile logs --no-color --tail $Tail cfo-sync-server }
        $summary.server_logs_tail = Redact-SecretText $serverLogs.output

        $tunnelLogs = Invoke-SafeCommand { docker compose --env-file $EnvFile -f $ComposeFile logs --no-color --tail $Tail cfo-sync-tunnel }
        $summary.tunnel_logs_tail = Redact-SecretText $tunnelLogs.output
    }

    return $summary
}

function Write-MarkdownReport {
    param(
        [hashtable]$Report,
        [string]$PathValue
    )

    $lines = @()
    $lines += "# Gauss Server Report"
    $lines += ""
    $lines += "Gerado em UTC: $($Report.generated_at)"
    $lines += "Host: $($Report.host.computer_name)"
    $lines += ""
    $lines += "## Health"
    $lines += "- URL: $($Report.health.url)"
    $lines += "- OK: $($Report.health.ok)"
    $lines += "- Status: $($Report.health.status)"
    $lines += "- Versao: $($Report.health.version)"
    $lines += "- Server time: $($Report.health.server_time)"
    if ($Report.health.error) {
        $lines += "- Erro: $($Report.health.error)"
    }
    $lines += ""
    $lines += "## Git"
    $lines += "- Repo: $($Report.git.repo_root)"
    $lines += "- Branch: $($Report.git.branch)"
    $lines += "- Commit: $($Report.git.commit)"
    $lines += "- Dirty: $($Report.git.dirty)"
    if ($Report.git.error) {
        $lines += "- Observacao: $($Report.git.error)"
    }
    $lines += ""
    $lines += "## Docker"
    $lines += "- Docker disponivel: $($Report.docker.docker_available)"
    $lines += "- Docker info OK: $($Report.docker.docker_info_ok)"
    foreach ($container in $Report.docker.containers) {
        $lines += "- Container: $($container.name) | $($container.status) | $($container.ports)"
    }
    if (-not $Report.docker.containers -or $Report.docker.containers.Count -eq 0) {
        $lines += "- Containers CFO Sync encontrados: 0"
    }
    $lines += ""
    $lines += "## Caminhos"
    foreach ($dir in $Report.paths.directories) {
        $lines += "- $($dir.path): exists=$($dir.exists)"
    }
    $lines += ""
    $lines += "## Secrets Esperados"
    foreach ($file in $Report.paths.expected_secret_files) {
        $lines += "- $($file.path): exists=$($file.exists), bytes=$($file.bytes), last_write=$($file.last_write)"
    }
    $lines += ""
    $lines += "## Server Access"
    $lines += "- Arquivo existe: $($Report.access.exists)"
    $lines += "- Tokens configurados: $($Report.access.token_count)"
    foreach ($token in $Report.access.tokens) {
        $platforms = (($token.allowed_platforms | ForEach-Object { Convert-ToSafeString $_ }) -join ", ")
        $lines += "- Token name=$($token.name), token_present=$($token.token_present), can_manage_secrets=$($token.can_manage_secrets), platforms=$platforms"
    }
    if ($Report.access.error) {
        $lines += "- Erro: $($Report.access.error)"
    }
    $lines += ""
    $lines += "## Env Docker Sanitizado"
    foreach ($item in $Report.env_file) {
        $lines += "- $($item.name)=$($item.value)"
    }
    if (-not $Report.env_file -or $Report.env_file.Count -eq 0) {
        $lines += "- Nenhum env file lido."
    }
    $lines += ""
    $lines += "## Logs Recentes - Servidor"
    $lines += '```text'
    $lines += $Report.docker.server_logs_tail
    $lines += '```'
    $lines += ""
    $lines += "## Logs Recentes - Tunnel"
    $lines += '```text'
    $lines += $Report.docker.tunnel_logs_tail
    $lines += '```'

    $lines | Set-Content -LiteralPath $PathValue -Encoding UTF8
}

if (-not $RepoRoot) {
    $RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..") -ErrorAction SilentlyContinue
}

$hostRootAbsolute = [System.IO.Path]::GetFullPath($HostRoot)
$secretsDir = Join-Path $hostRootAbsolute "secrets"
$cfoSyncDir = Join-Path $hostRootAbsolute "cfo_sync"
$dataDir = Join-Path $hostRootAbsolute "data"
$accessConfigPath = Join-Path $cfoSyncDir "server_access.json"

if (-not $OutputDir) {
    $OutputDir = Join-Path $cfoSyncDir "agent_reports"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$composeFile = Join-Path $RepoRoot "settings\docker-compose.server.yml"
$envFile = Join-Path $RepoRoot "settings\docker-server.env"

$expectedSecrets = @(
    "app_config.json",
    "google_service_account.json",
    "yampi_credentials.json",
    "meta_ads_credentials.json",
    "google_ads_credentials.json",
    "tiktok_ads_credentials.json",
    "omie_credentials.json",
    "omie_2025.json",
    "mercado_livre_credentials.json"
)

$report = [ordered]@{
    generated_at = Get-NowIso
    host = [ordered]@{
        computer_name = $env:COMPUTERNAME
        user = $env:USERNAME
        os = (Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue).Caption
        powershell = $PSVersionTable.PSVersion.ToString()
    }
    inputs = [ordered]@{
        host_root = $hostRootAbsolute
        server_url = $ServerUrl
        output_dir = $OutputDir
        log_tail = $LogTail
    }
    git = Get-GitSummary -PathValue $RepoRoot
    health = Get-HealthSummary -BaseUrl $ServerUrl
    docker = Get-DockerSummary -ComposeFile $composeFile -EnvFile $envFile -Tail $LogTail
    paths = [ordered]@{
        directories = @(
            Get-DirectoryPresence -PathValue $hostRootAbsolute
            Get-DirectoryPresence -PathValue $secretsDir
            Get-DirectoryPresence -PathValue $cfoSyncDir
            Get-DirectoryPresence -PathValue $dataDir
        )
        expected_secret_files = @($expectedSecrets | ForEach-Object { Get-FilePresence -PathValue (Join-Path $secretsDir $_) })
        access_file = Get-FilePresence -PathValue $accessConfigPath
    }
    access = Get-AccessSummary -PathValue $accessConfigPath
    env_file = Read-EnvFileSafe -PathValue $envFile
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$jsonPath = Join-Path $OutputDir "gauss-server-report-$timestamp.json"
$mdPath = Join-Path $OutputDir "gauss-server-report-$timestamp.md"
$latestJsonPath = Join-Path $OutputDir "gauss-server-report.latest.json"
$latestMdPath = Join-Path $OutputDir "gauss-server-report.latest.md"

($report | ConvertTo-Json -Depth 12) | Set-Content -LiteralPath $jsonPath -Encoding UTF8
($report | ConvertTo-Json -Depth 12) | Set-Content -LiteralPath $latestJsonPath -Encoding UTF8
Write-MarkdownReport -Report $report -PathValue $mdPath
Write-MarkdownReport -Report $report -PathValue $latestMdPath

Write-Host "Gauss report gerado:"
Write-Host "Markdown: $mdPath"
Write-Host "JSON:     $jsonPath"
