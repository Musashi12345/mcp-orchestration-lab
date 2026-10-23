param(
    [ValidateRange(1024, 65529)][int]$BasePort = 8766,
    [string]$Config = 'configs\agents.yaml',
    [ValidateRange(10, 180)][int]$StartupSeconds = 60
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath($PSScriptRoot)
. (Join-Path $projectRoot 'scripts\agent_processes.ps1')
$gate = Enter-LabProcessLock $projectRoot
$state = $null
$previousToken = $env:MCP_LAB_ADMIN_TOKEN
try {
    $python = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) { throw 'Project Python is missing. Set up .venv first.' }
    $configPath = if ([IO.Path]::IsPathRooted($Config)) { [IO.Path]::GetFullPath($Config) } else { [IO.Path]::GetFullPath((Join-Path $projectRoot $Config)) }
    if (-not (Test-Path -LiteralPath $configPath)) { throw 'Agent configuration file is missing.' }
    $statePath = Get-LabStatePath $projectRoot
    if (Test-Path -LiteralPath $statePath) {
        $previous = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        $owned = @($previous.services | Where-Object { Test-LabOwnedProcess $projectRoot $_ })
        if ($owned.Count -eq 7) {
            foreach ($entry in $owned) {
                try { $health = Invoke-RestMethod -Uri ('http://127.0.0.1:' + $entry.port + '/health') -TimeoutSec 2 }
                catch { throw 'Managed processes exist but are not healthy. Run .\stop_agents.ps1 before restarting.' }
                if ($health.instance -ne $entry.instance -or $health.status -ne 'READY') { throw 'Managed service identity changed. Stop and inspect the saved processes.' }
            }
            Write-Output 'The orchestrator and all six agents are already running.'
            $owned | Select-Object name, pid, port | Format-Table
            return
        }
        if ($owned.Count) { throw 'Some services are still running. Run .\stop_agents.ps1 before restarting.' }
    }
    for ($port = $BasePort; $port -le $BasePort + 6; $port++) {
        $listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, $port)
        try {
            $listener.ExclusiveAddressUse = $false
            $listener.Server.SetSocketOption([Net.Sockets.SocketOptionLevel]::Socket, [Net.Sockets.SocketOptionName]::ReuseAddress, $true)
            $listener.Start()
        } catch { throw "Port $port is unavailable or reserved. Choose another -BasePort." }
        finally { $listener.Stop() }
    }
    $instance = [Guid]::NewGuid().ToString('N')
    $launchDirectory = Join-Path $projectRoot ('.runtime\agents\launch_' + $instance)
    New-Item -ItemType Directory -Path $launchDirectory -Force | Out-Null
    $bytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    $env:MCP_LAB_ADMIN_TOKEN = [Convert]::ToBase64String($bytes)
    [IO.File]::WriteAllText((Join-Path $projectRoot '.runtime\agents\access.token'), $env:MCP_LAB_ADMIN_TOKEN)
    $state = [pscustomobject]@{ schema_version = 1; project_root = $projectRoot; instance = $instance;
        status = 'STARTING'; launch_directory = $launchDirectory; services = @() }
    $definitions = @(
        @('orchestrator', 'mcp_execution_lab.orchestration.server'),
        @('data_understanding', 'mcp_execution_lab.agents.understanding.server'),
        @('data_cleaning', 'mcp_execution_lab.agents.cleaning.server'),
        @('data_combining', 'mcp_execution_lab.agents.combining.server'),
        @('data_analysis', 'mcp_execution_lab.agents.analysis.server'),
        @('prediction', 'mcp_execution_lab.agents.prediction.server'),
        @('report', 'mcp_execution_lab.agents.report.server')
    )
    for ($index = 0; $index -lt $definitions.Count; $index++) {
        $name, $module = $definitions[$index]
        $port = $BasePort + $index
        $arguments = @('-m', $module, '--port', [string]$port, '--instance', $instance)
        if ($name -eq 'orchestrator') { $arguments += @('--base-port', [string]$BasePort, '--config', ('"' + $configPath + '"')) }
        $process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $launchDirectory ($name + '.stdout.log')) -RedirectStandardError (Join-Path $launchDirectory ($name + '.stderr.log'))
        $entry = [pscustomobject]@{ name = $name; module = $module; pid = $process.Id; port = $port;
            started_utc = $process.StartTime.ToUniversalTime().ToString('o'); instance = $instance }
        $state.services += $entry
        Save-LabProcessState $projectRoot $state
    }
    $deadline = [DateTime]::UtcNow.AddSeconds($StartupSeconds)
    do {
        $ready = 0
        foreach ($entry in $state.services) {
            if (-not (Test-LabOwnedProcess $projectRoot $entry)) { throw ($entry.name + ' exited. Inspect ' + $launchDirectory) }
            try {
                $health = Invoke-RestMethod -Uri ('http://127.0.0.1:' + $entry.port + '/health') -TimeoutSec 1
                if ($health.instance -eq $instance -and $health.service -eq $entry.name -and $health.status -eq 'READY') { $ready++ }
            } catch { }
        }
        if ($ready -eq 7) { break }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)
    if ($ready -ne 7) { throw "Startup timed out. Inspect $launchDirectory" }
    $state.status = 'RUNNING'
    Save-LabProcessState $projectRoot $state
    Write-Output ('Orchestrator: http://127.0.0.1:' + $BasePort)
    $state.services | Select-Object name, pid, port | Format-Table
    Write-Output ('Logs and PID records: ' + $launchDirectory)
    Write-Output 'Model calls begin only when you submit a run. Local PostgreSQL credentials must be configured in .env before runs.'
} catch {
    if ($state) { Stop-LabOwnedProcesses $projectRoot $state }
    throw
} finally {
    $env:MCP_LAB_ADMIN_TOKEN = $previousToken
    $gate.ReleaseMutex()
    $gate.Dispose()
}
