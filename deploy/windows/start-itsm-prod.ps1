param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

$pythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Python venv not found: $pythonExe"
}

$env:DJANGO_ENV = "production"
$env:PYTHONUNBUFFERED = "1"

Set-Location $ProjectRoot
& $pythonExe ".\scripts\production_runner.py"
