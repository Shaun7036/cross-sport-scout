$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv was not found. Install it from https://docs.astral.sh/uv/ and try again."
    exit 1
}

Push-Location $ProjectRoot
try {
    Write-Host "Creating the project environment with uv..."
    & uv sync --extra dev
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host ""
    & uv run python scripts/run_portal.py check
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host "Setup complete. Start with: .\scripts\run_portal.ps1 friendly"
}
finally {
    Pop-Location
}
