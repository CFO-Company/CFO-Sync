Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

& "$PSScriptRoot\\invoke_sync.ps1" `
    --platform meta_ads `
    --period yesterday

exit $LASTEXITCODE
