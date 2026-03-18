Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

& "$PSScriptRoot\\invoke_sync.ps1" `
    --platform omie_2025 `
    --period year_previous

exit $LASTEXITCODE
