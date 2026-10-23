# Run the project-local CLI without requiring Python or uv on PATH.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'Project environment is missing. Run uv sync --locked --python 3.12 from the project root.'
}
Push-Location -LiteralPath $projectRoot
try {
    & $projectPython -m mcp_execution_lab.cli @args
    $labExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $labExitCode
