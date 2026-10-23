param(
    [ValidateRange(1, 65535)][int]$Port = 5000,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

function Find-TaskPython {
    $candidates = @()
    foreach ($name in @('python', 'python3', 'py')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { $candidates += $command.Source }
    }
    $bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $bundledPython) { $candidates += $bundledPython }
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        try {
            & $candidate -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        } catch { continue }
    }
    throw 'Python 3.10 or newer is required. Install Python from python.org, then run Start.bat again.'
}

if (-not (Test-Path -LiteralPath $taskPython)) {
    $basePython = Find-TaskPython
    Write-Host 'Creating the project environment...' -ForegroundColor Cyan
    & $basePython -m venv (Join-Path $PSScriptRoot '.venv')
    if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Could not create the Python environment.' }
}

& $taskPython -c 'import flask, psutil' 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Installing Flask and psutil...' -ForegroundColor Cyan
    & $taskPython -m pip --version 2>$null
    if ($LASTEXITCODE -ne 0) {
        $basePython = Find-TaskPython
        & $basePython -m pip --python $taskPython install pip
        if ($LASTEXITCODE -ne 0) { throw 'Could not set up pip. Run python -m ensurepip, then try again.' }
    }
    & $taskPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your internet connection and retry.' }
}

Write-Host ''
Write-Host "Memory Systems Lab is starting at http://127.0.0.1:$Port" -ForegroundColor Cyan
Write-Host 'Keep this window open. Press Ctrl+C to stop.'
$appArguments = @((Join-Path $PSScriptRoot 'app.py'), '--port', "$Port")
if (-not $NoBrowser) { $appArguments += '--open' }
& $taskPython @appArguments
if ($LASTEXITCODE -ne 0) { throw 'Memory Systems Lab stopped unexpectedly. If the port is occupied, try: .\Start.ps1 -Port 5001' }
