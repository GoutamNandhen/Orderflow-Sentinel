$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
$testFolder = 'work\pytest-' + [guid]::NewGuid().ToString('N')
& .venv\Scripts\python.exe -m pytest backend\tests -q --tb=short --basetemp=$testFolder --junitxml=docs\pytest-results.xml
if ($LASTEXITCODE) { throw 'Backend tests failed.' }
npm run build
if ($LASTEXITCODE) { throw 'Frontend builds failed.' }
Write-Host 'Backend tests and both production builds passed.'
