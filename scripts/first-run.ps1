# First-run after clone. Requires Rancher Desktop (dockerd).
# Usage (from code root, venv recommended):
#   powershell -File scripts\first-run.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "CLEVER first-run from $(Get-Location)"

if (-not (Test-Path "gateway") -or -not (Test-Path "infra\docker-compose.yml")) {
    Write-Error "Run this from the code root (folder that contains gateway\ and infra\)."
    exit 1
}

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example (mock LLM, no API key)."
}

& "$PSScriptRoot\start-stack.ps1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (Get-Command python -ErrorAction SilentlyContinue) {
    Write-Host "Loading synthetic aging fixture..."
    python -m harness.load_aging
} else {
    Write-Host "python not on PATH; skip aging load. After venv: python -m harness.load_aging"
}

Write-Host ""
Write-Host "Stack is up. In this folder, with venv active, run:"
Write-Host "  python -m uvicorn gateway.main:app --port 8080"
Write-Host "Then open http://127.0.0.1:8080/  (chat) and /dashboard (metrics)"
Write-Host "API key field: dev-key-change-me"
Write-Host "Health:  curl.exe -s http://127.0.0.1:8080/health"
