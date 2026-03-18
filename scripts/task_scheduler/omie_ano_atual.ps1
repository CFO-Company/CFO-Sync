Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

& "$PSScriptRoot\\invoke_sync.ps1" `
    --platform omie_2026 `
    --period year_current

exit $LASTEXITCODE
