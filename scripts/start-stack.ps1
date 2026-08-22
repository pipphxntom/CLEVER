# Start Postgres + Redis via Rancher Desktop, apply schema, seed FAQ.
# Usage (from repo root):  powershell -File scripts\start-stack.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

& "$PSScriptRoot\ensure-rancher.ps1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example"
}

docker compose -p clever -f infra\docker-compose.yml up -d
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Waiting for Postgres..."
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    docker exec clever_postgres pg_isready -U clever -d clever 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $ready) {
    Write-Error "Postgres did not become ready"
    exit 1
}

docker cp db\schema.sql clever_postgres:/schema.sql
docker exec clever_postgres psql -U clever -d clever -f /schema.sql
docker cp db\schema_novel.sql clever_postgres:/schema_novel.sql
docker exec clever_postgres psql -U clever -d clever -f /schema_novel.sql
docker cp db\schema_v03.sql clever_postgres:/schema_v03.sql
docker exec clever_postgres psql -U clever -d clever -f /schema_v03.sql
docker cp db\schema_v04.sql clever_postgres:/schema_v04.sql
docker exec clever_postgres psql -U clever -d clever -f /schema_v04.sql
docker cp harness\seed_faq.sql clever_postgres:/seed_faq.sql
docker exec clever_postgres psql -U clever -d clever -f /seed_faq.sql

Write-Host "Stack ready. Start the gateway with:"
Write-Host "  python -m uvicorn gateway.main:app --reload --port 8080"
