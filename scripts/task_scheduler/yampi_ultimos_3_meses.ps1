Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

& "$PSScriptRoot\\invoke_sync.ps1" `
    --platform yampi `
    --period rolling_months `
    --months 3

exit $LASTEXITCODE
