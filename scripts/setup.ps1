param([switch]$SkipModels)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        uv venv --python 3.11 .venv
        if ($LASTEXITCODE) { throw 'Install Python 3.11 or allow uv to download it, then rerun setup.' }
    } else {
        py -3.11 -m venv .venv
        if ($LASTEXITCODE) { throw 'Python 3.11 is required. Install it from python.org, then rerun setup.' }
    }
}
if (Get-Command uv -ErrorAction SilentlyContinue) {
    $env:UV_CONCURRENT_INSTALLS = '1'
    uv pip install --python .venv\Scripts\python.exe -r backend\requirements.txt --link-mode copy
} else {
    & .venv\Scripts\python.exe -m ensurepip --upgrade
    & .venv\Scripts\python.exe -m pip install -r backend\requirements.txt
}
if ($LASTEXITCODE) { throw 'Backend dependency installation failed.' }
# Explicit node entrypoints avoid symlink/admin requirements on Windows.
npm ci --no-bin-links --no-audit --no-fund
if ($LASTEXITCODE) { throw 'Frontend dependency installation failed.' }
if (-not $SkipModels) {
    & .venv\Scripts\python.exe -m backend.train.train_models
    if ($LASTEXITCODE) { throw 'Model training failed. The application can still use the rule fallback.' }
}
Write-Host 'Setup complete. Run .\scripts\start.ps1'
