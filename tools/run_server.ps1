param(
    [string]$Host = "127.0.0.1",
    [int]$Port = 8088,
    [string]$AppConfig = "C:\srv\secrets\app_config.json",
    [string]$AccessConfig = "C:\srv\cfo_sync\server_access.json",
    [int]$Workers = 2
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python da .venv nao encontrado em: $python"
}

Push-Location $repoRoot
try {
    $env:PYTHONPATH = "src"
    & $python -m cfo_sync.server.main `
        --host $Host `
        --port $Port `
        --app-config $AppConfig `
        --access-config $AccessConfig `
        --workers $Workers
}
finally {
    Pop-Location
}

