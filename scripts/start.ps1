param([switch]$Demo, [int]$BackendPort = 8000)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run scripts\setup.ps1 first.' }
if ($BackendPort -ne 8000) { throw 'Frontends use port 8000; keep the default unless shared/api.ts is updated.' }
foreach ($port in @(8000,5173,5174)) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) { throw "Port $port is already in use. Stop the existing service first." }
}
$previousDatabaseURL = $env:DATABASE_URL
if ($Demo) {
    # Reuses this separate DB on later starts; never resets normal data.
    $env:DATABASE_URL = 'sqlite:///' + ((Join-Path $projectRoot 'backend\data\judge-demo.db') -replace '\\','/')
}
$logs = Join-Path $projectRoot 'work\logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$processes = @()
try {
    $processes += Start-Process -FilePath $pythonPath -ArgumentList @('-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000','--workers','1') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'backend.out.log') -RedirectStandardError (Join-Path $logs 'backend.err.log')
    $processes += Start-Process -FilePath 'node' -ArgumentList @('..\node_modules\vite\bin\vite.js','--host','127.0.0.1','--port','5173','--strictPort') -WorkingDirectory (Join-Path $projectRoot 'shop-frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'shop.out.log') -RedirectStandardError (Join-Path $logs 'shop.err.log')
    $processes += Start-Process -FilePath 'node' -ArgumentList @('..\node_modules\vite\bin\vite.js','--host','127.0.0.1','--port','5174','--strictPort') -WorkingDirectory (Join-Path $projectRoot 'console-frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'console.out.log') -RedirectStandardError (Join-Path $logs 'console.err.log')
    $processes | Select-Object Id,ProcessName | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logs 'processes.json')
    Write-Host 'ShopEase: http://localhost:5173'
    Write-Host 'Sentinel: http://localhost:5174 (use OPERATOR_PASSWORD or backend/data/operator-password.local)'
    Write-Host 'API docs: http://localhost:8000/docs'
    Write-Host 'Keep this session open. Ctrl+C stops these child services. Logs: work\logs'
    while ($true) {
        Start-Sleep -Seconds 2
        foreach ($process in $processes) { if ($process.HasExited) { throw "Service $($process.Id) exited. Inspect work\logs." } }
    }
} finally {
    foreach ($process in $processes) { if (-not $process.HasExited) { Stop-Process -Id $process.Id -ErrorAction SilentlyContinue } }
    $env:DATABASE_URL = $previousDatabaseURL
}
