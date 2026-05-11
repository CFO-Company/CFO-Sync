[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $PythonArgs
)

$ErrorActionPreference = "Stop"

function Test-PythonCandidate {
    param([string] $CandidatePath)

    if (-not $CandidatePath) {
        return $null
    }
    if ($CandidatePath -match "\\Microsoft\\WindowsApps\\") {
        return $null
    }
    if (-not (Test-Path -LiteralPath $CandidatePath -PathType Leaf)) {
        return $null
    }

    try {
        & $CandidatePath -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" *> $null
        if ($LASTEXITCODE -eq 0) {
            return $CandidatePath
        }
    }
    catch {
        return $null
    }

    return $null
}

$candidates = New-Object System.Collections.Generic.List[string]

if ($env:CFO_SYNC_PYTHON) {
    $candidates.Add($env:CFO_SYNC_PYTHON)
}

foreach ($name in @("python", "python3")) {
    foreach ($command in (Get-Command $name -All -ErrorAction SilentlyContinue)) {
        if ($command.Source) {
            $candidates.Add($command.Source)
        }
    }
}

if ($env:LOCALAPPDATA) {
    $candidates.Add((Join-Path $env:LOCALAPPDATA "Python\bin\python.exe"))
    foreach ($python in (Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA "Programs\Python") -Recurse -Filter python.exe -ErrorAction SilentlyContinue)) {
        $candidates.Add($python.FullName)
    }
}

$pythonPath = $null
foreach ($candidate in ($candidates | Select-Object -Unique)) {
    $pythonPath = Test-PythonCandidate $candidate
    if ($pythonPath) {
        break
    }
}

if (-not $pythonPath) {
    throw "Python >= 3.11 nao encontrado. Defina CFO_SYNC_PYTHON com o caminho de python.exe ou instale Python 3.11+."
}

if (-not $PythonArgs -or $PythonArgs.Count -eq 0) {
    & $pythonPath --version
    exit $LASTEXITCODE
}

& $pythonPath @PythonArgs
exit $LASTEXITCODE
