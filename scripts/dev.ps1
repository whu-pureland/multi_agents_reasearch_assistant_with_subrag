param(
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 5173,
  [switch]$Install
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

if ($Install) {
  Push-Location "$RepoRoot\\backend"
  if (!(Test-Path ".venv")) { python -m venv ".venv" }
  . ".\\.venv\\Scripts\\Activate.ps1"

  $EnvPath = Join-Path $RepoRoot ".env"
  $UseLocalEmbedding = $false
  if (Test-Path $EnvPath) {
    $EnvContent = Get-Content $EnvPath -ErrorAction SilentlyContinue
    if ($EnvContent -match '^(?i)EMBEDDING_PROVIDER\s*=\s*local\s*$') {
      $UseLocalEmbedding = $true
    }
  }

  if ($UseLocalEmbedding) {
    pip install -e ".[local_embedding]"
  } else {
    pip install -e .
  }
  Pop-Location

  Push-Location "$RepoRoot\\frontend"
  npm install
  Pop-Location
}

Start-Process powershell -ArgumentList @(
  "-NoExit",
  "-Command",
  "cd `"$RepoRoot\\backend`"; . .\\.venv\\Scripts\\Activate.ps1; uvicorn app.main:app --reload --port $BackendPort"
)

Start-Process powershell -ArgumentList @(
  "-NoExit",
  "-Command",
  "cd `"$RepoRoot\\frontend`"; $env:VITE_BACKEND_URL='http://localhost:$BackendPort'; npm run dev -- --port $FrontendPort"
)

Write-Host "Backend: http://localhost:$BackendPort"
Write-Host "Frontend: http://localhost:$FrontendPort"
