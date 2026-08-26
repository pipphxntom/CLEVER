# One command after clone: stack + gateway.
# Usage (venv on, code root): powershell -File scripts\dev.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

& "$PSScriptRoot\first-run.ps1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Starting gateway on http://127.0.0.1:8080/  (Ctrl+C to stop)"
Write-Host "Chat /  Dashboard /dashboard  Swagger /docs  (Authorize: dev-key-change-me)"
python -m uvicorn gateway.main:app --port 8080 --reload
