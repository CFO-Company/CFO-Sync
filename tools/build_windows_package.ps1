param(
    [string]$PythonExe = ".venv\\Scripts\\python.exe",
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$versionLine = Select-String -Path (Join-Path $repoRoot "pyproject.toml") -Pattern '^version\s*=\s*".+"'
if (-not $versionLine) {
    throw "Nao foi possivel ler a versao do pyproject.toml"
}
$appVersion = ($versionLine.Line -replace '^version\s*=\s*"(.*)"\s*$', '$1')

if (-not (Test-Path $PythonExe)) {
    throw "Python do ambiente virtual nao encontrado em '$PythonExe'."
}

Write-Host "==> Instalando dependencias de build..."
& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install -r requirements.txt pyinstaller

$appName = "CFO-Sync"
$distDir = Join-Path $repoRoot "dist\\$appName"
$installerOutDir = Join-Path $repoRoot "dist\\installer"
New-Item -ItemType Directory -Force -Path $installerOutDir | Out-Null

Write-Host "==> Gerando executavel com PyInstaller..."
& $PythonExe -m PyInstaller `
    launcher_desktop.py `
    --noconfirm `
    --clean `
    --windowed `
    --name $appName `
    --paths src `
    --collect-data cfo_sync `
    --add-data "sounds;sounds" `
    --add-data "templates;templates"

if (-not (Test-Path $distDir)) {
    throw "Build do executavel falhou. Pasta nao encontrada: $distDir"
}

Write-Host "==> Executavel pronto em: $distDir"

if ($SkipInstaller) {
    Write-Host "==> Instalador pulado (flag -SkipInstaller)."
    exit 0
}

$iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
    Write-Host "==> Inno Setup (iscc.exe) nao encontrado. Instalador nao foi gerado."
    Write-Host "    Instale o Inno Setup e rode novamente este script para gerar o Setup.exe."
    exit 0
}

$issPath = Join-Path $repoRoot "installer\\CFO-Sync.iss"
if (-not (Test-Path $issPath)) {
    throw "Script do Inno Setup nao encontrado: $issPath"
}

Write-Host "==> Gerando instalador com Inno Setup..."
& $iscc.Source "/DMyAppVersion=$appVersion" $issPath

Write-Host "==> Instalador pronto em dist\\installer"
