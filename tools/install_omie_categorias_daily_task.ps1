param(
    [string]$TaskName = "CFO Sync Omie Categorias Diario",
    [string]$RepoRoot = "",
    [string]$At = "06:00",
    [string]$SpreadsheetId = "14W1swSXAdvOzz1A8DwZug02aKRQnhROQyaqr1D2Mq-E",
    [string]$Gid = "2087624295",
    [string[]]$CredentialFile = @("omie_credentials.json"),
    [string]$PowerShellPath = ""
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
    $RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
}
else {
    $RepoRoot = Resolve-Path $RepoRoot
}

$scriptPath = Join-Path $RepoRoot "scripts\task_scheduler\omie_categorias_diario.py"
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    throw "Script de categorias Omie nao encontrado: $scriptPath"
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

$python = Get-Command python.exe -ErrorAction Stop
$credentialArgs = @()
foreach ($file in $CredentialFile) {
    $credentialArgs += "--credentials-file"
    $credentialArgs += "`"$file`""
}

$pythonCommand = @(
    "`"$($python.Source)`"",
    "`"$scriptPath`"",
    "--spreadsheet-id", "`"$SpreadsheetId`"",
    "--gid", "`"$Gid`""
) + $credentialArgs

$arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-Command",
    "`"Set-Location -LiteralPath '$RepoRoot'; $($pythonCommand -join ' ')`""
) -join " "

try {
    $atTime = [datetime]::ParseExact($At, "HH:mm", $null)
}
catch {
    throw "Horario invalido em -At '$At'. Use HH:mm, por exemplo 06:00."
}

$action = New-ScheduledTaskAction -Execute $PowerShellPath -Argument $arguments
$trigger = New-ScheduledTaskTrigger -Daily -At $atTime
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
    -Description "Atualiza diariamente a planilha de categorias da Omie para o CFO Sync." `
    -Force | Out-Null

Write-Host "Tarefa agendada registrada: $TaskName"
Write-Host "Horario diario: $At"
Write-Host "Script: $scriptPath"
Write-Host "Planilha: $SpreadsheetId"
Write-Host "GID: $Gid"
Write-Host "Credenciais Omie: $($CredentialFile -join ', ')"
