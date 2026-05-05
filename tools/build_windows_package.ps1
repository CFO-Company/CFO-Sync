param(
    [string]$PythonExe = ".venv\\Scripts\\python.exe",
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$versionLine = Select-String -Path (Join-Path $repoRoot "pyproject.toml") -Pattern '^version\s*=\s*".+"'
if (-not $versionLine) {
    throw "Nao foi possivel ler a versão do pyproject.toml"
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
$singleFileName = "CFO-Sync-Setup"
$singleFileDistExe = Join-Path $repoRoot "dist\\$singleFileName.exe"
$singleFileOutExe = Join-Path $installerOutDir "$singleFileName.exe"
New-Item -ItemType Directory -Force -Path $installerOutDir | Out-Null

$commonPyInstallerArgs = @(
    "launcher_desktop.py",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--paths", "src",
    "--collect-data", "cfo_sync"
)

if (Test-Path (Join-Path $repoRoot "sounds")) {
    $commonPyInstallerArgs += @("--add-data", "sounds;sounds")
} else {
    Write-Host "==> Aviso: pasta 'sounds' nao encontrada. Seguindo sem --add-data sounds."
}

if (Test-Path (Join-Path $repoRoot "templates")) {
    $commonPyInstallerArgs += @("--add-data", "templates;templates")
} else {
    Write-Host "==> Aviso: pasta 'templates' nao encontrada. Seguindo sem --add-data templates."
}

$iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
$shouldBuildSingleFile = $SkipInstaller -or (-not $iscc)

if ($shouldBuildSingleFile) {
    Write-Host "==> Gerando executavel unico (onefile) com PyInstaller..."
    $oneFileArgs = @("--onefile", "--name", $singleFileName) + $commonPyInstallerArgs
    & $PythonExe -m PyInstaller @oneFileArgs

    if (-not (Test-Path $singleFileDistExe)) {
        throw "Build onefile falhou. Arquivo nao encontrado: $singleFileDistExe"
    }

    Move-Item -Force $singleFileDistExe $singleFileOutExe
    Write-Host "==> Executavel unico pronto em: $singleFileOutExe"

    if (-not $iscc -and -not $SkipInstaller) {
        Write-Host "==> Inno Setup nao encontrado. Usando executavel unico como pacote final."
    }

    if (Test-Path $distDir) {
        Remove-Item -Recurse -Force $distDir
    }
    return
}

Write-Host "==> Gerando build base (onedir) com PyInstaller..."
$oneDirArgs = @("--name", $appName) + $commonPyInstallerArgs
& $PythonExe -m PyInstaller @oneDirArgs

if (-not (Test-Path $distDir)) {
    throw "Build do executavel falhou. Pasta nao encontrada: $distDir"
}

Write-Host "==> Build base pronto em: $distDir"

$issPath = Join-Path $repoRoot "installer\\CFO-Sync.iss"
if (-not (Test-Path $issPath)) {
    throw "Script do Inno Setup nao encontrado: $issPath"
}

Write-Host "==> Gerando instalador com Inno Setup..."
& $iscc.Source "/DMyAppVersion=$appVersion" $issPath

Write-Host "==> Instalador pronto em dist\\installer"
if (Test-Path $distDir) {
    Remove-Item -Recurse -Force $distDir
    Write-Host "==> Artefato intermediario removido: dist\\$appName"
}
