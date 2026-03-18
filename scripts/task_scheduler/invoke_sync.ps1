param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $ForwardedArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir "..\\..")
$pythonExe = Join-Path $projectRoot ".venv\\Scripts\\python.exe"
$runnerPath = Join-Path $scriptDir "run_platform_sync.py"

if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

if (-not (Test-Path $runnerPath)) {
    throw "Runner nao encontrado: $runnerPath"
}

& $pythonExe $runnerPath @ForwardedArgs
exit $LASTEXITCODE
