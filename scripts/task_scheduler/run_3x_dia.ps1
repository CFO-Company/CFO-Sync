Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scripts = @(
    "omie_ano_atual.ps1",
    "omie_ano_anterior.ps1",
    "yampi_ultimos_3_meses.ps1",
    "mercado_livre_ultimos_3_meses.ps1"
)

$finalExitCode = 0
foreach ($scriptName in $scripts) {
    & "$PSScriptRoot\\$scriptName"
    if ($LASTEXITCODE -ne 0) {
        $finalExitCode = $LASTEXITCODE
    }
}

exit $finalExitCode
