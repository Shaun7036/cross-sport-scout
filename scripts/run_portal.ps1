$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv was not found. Run .\scripts\setup_local.ps1 after installing uv."
    exit 1
}

Push-Location $ProjectRoot
try {
    & uv run python scripts/run_portal.py @args
    $ExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $ExitCode
