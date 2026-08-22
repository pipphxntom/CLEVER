# Requires Rancher Desktop with container engine = dockerd (moby).
# Refuses Docker Desktop. Cvent-supported runtime only.
$ErrorActionPreference = "Stop"

function Fail([string]$msg) {
    Write-Error $msg
    exit 1
}

$rdctl = Get-Command rdctl -ErrorAction SilentlyContinue
if (-not $rdctl) {
    Fail @"
Rancher Desktop is not on PATH (rdctl missing).
Cvent-supported install:
  winget install -e --id SUSE.RancherDesktop
Then open Rancher Desktop -> Preferences -> Container Engine -> dockerd (moby).
Quit Docker Desktop if it is installed; it steals the docker CLI context.
"@
}

$contexts = docker context ls --format "{{.Name}}" 2>$null
if (-not $contexts) {
    Fail "docker CLI is not talking to any engine. Start Rancher Desktop and wait until it is Running."
}

$current = docker context show 2>$null
if ($current -eq "desktop-linux" -or $current -match "desktop") {
    Fail "Active docker context is '$current' (Docker Desktop). Switch to Rancher: docker context use rancher-desktop"
}

if ($contexts -match "rancher-desktop") {
    docker context use rancher-desktop | Out-Null
}

docker info 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Fail "Rancher engine is not ready. Open Rancher Desktop and wait until the VM is Running (dockerd)."
}

Write-Host "OK: docker context=$(docker context show)"
