$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    & '.\.venv\Scripts\ruff.exe' check src tests
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & '.\.venv\Scripts\ruff.exe' format --check src tests
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & '.\.venv\Scripts\python.exe' -m pytest -q
    $checkExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $checkExitCode
