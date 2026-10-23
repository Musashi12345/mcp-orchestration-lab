$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath($PSScriptRoot)
. (Join-Path $projectRoot 'scripts\agent_processes.ps1')
$gate = Enter-LabProcessLock $projectRoot
try {
    $statePath = Get-LabStatePath $projectRoot
    if (-not (Test-Path -LiteralPath $statePath)) {
        Write-Output 'No managed agent processes have been started.'
        return
    }
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    Stop-LabOwnedProcesses $projectRoot $state
    Write-Output 'Stopped the managed orchestrator and agents. Logs and PID history were retained.'
} finally {
    $gate.ReleaseMutex()
    $gate.Dispose()
}
