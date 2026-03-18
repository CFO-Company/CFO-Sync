Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

& "$PSScriptRoot\\invoke_sync.ps1" `
    --platform google_ads `
    --period yesterday `
    --allow-missing-platform

exit $LASTEXITCODE
