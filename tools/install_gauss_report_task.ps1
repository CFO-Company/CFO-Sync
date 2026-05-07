param(
    [string]$TaskName = "CFO Sync Gauss Server Report",
    [string]$HostRoot = "C:\srv",
    [string]$ServerUrl = "http://127.0.0.1:8088",
    [string]$RepoRoot = "",
    [int]$IntervalMinutes = 15,
    [string]$PowerShellPath = ""
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
    $RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
}
else {
    $RepoRoot = Resolve-Path $RepoRoot
}

$reportScript = Join-Path $RepoRoot "tools\gauss_server_report.ps1"
if (-not (Test-Path -LiteralPath $reportScript -PathType Leaf)) {
    throw "Script do Gauss nao encontrado: $reportScript"
}

if (-not $PowerShellPath) {
    $pwsh = Get-Command pwsh.exe -ErrorAction SilentlyContinue
    if ($pwsh) {
        $PowerShellPath = $pwsh.Source
    }
    else {
        $PowerShellPath = (Get-Command powershell.exe -ErrorAction Stop).Source
    }
}

$arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$reportScript`"",
    "-HostRoot", "`"$HostRoot`"",
    "-ServerUrl", "`"$ServerUrl`"",
    "-RepoRoot", "`"$RepoRoot`""
) -join " "

$action = New-ScheduledTaskAction -Execute $PowerShellPath -Argument $arguments
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Gera relatorio sanitizado do agente Gauss para o CFO Sync." `
    -Force | Out-Null

Write-Host "Tarefa agendada registrada: $TaskName"
Write-Host "Intervalo: $IntervalMinutes minutos"
Write-Host "Script: $reportScript"
Write-Host "Relatorios: $HostRoot\cfo_sync\agent_reports"
