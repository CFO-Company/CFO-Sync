Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scripts = @(
    "meta_ads_dia_anterior.ps1",
    "google_ads_dia_anterior.ps1"
)

$finalExitCode = 0
foreach ($scriptName in $scripts) {
    & "$PSScriptRoot\\$scriptName"
    if ($LASTEXITCODE -ne 0) {
        $finalExitCode = $LASTEXITCODE
    }
}

exit $finalExitCode
