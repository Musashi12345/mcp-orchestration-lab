$ErrorActionPreference = 'Stop'

function Get-LabStatePath([string]$ProjectRoot) {
    return Join-Path $ProjectRoot '.runtime\agents\pids.json'
}

function Enter-LabProcessLock([string]$ProjectRoot) {
    $digest = [System.Security.Cryptography.SHA256]::Create()
    try {
        $key = [BitConverter]::ToString($digest.ComputeHash([Text.Encoding]::UTF8.GetBytes($ProjectRoot.ToLowerInvariant()))).Replace('-', '')
    } finally { $digest.Dispose() }
    $gate = New-Object System.Threading.Mutex($false, ('Local\McpLabAgents_' + $key.Substring(0, 24)))
    if (-not $gate.WaitOne(0)) {
        $gate.Dispose()
        throw 'Another start or stop command is already running for this project.'
    }
    return $gate
}

function Save-LabProcessState([string]$ProjectRoot, $State) {
    $path = Get-LabStatePath $ProjectRoot
    $folder = Split-Path -Parent $path
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
    $temporary = Join-Path $folder ('pids.' + [Guid]::NewGuid().ToString('N') + '.tmp')
    [IO.File]::WriteAllText($temporary, ($State | ConvertTo-Json -Depth 10), (New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $temporary -Destination $path -Force
    if ($State.launch_directory) {
        [IO.File]::WriteAllText((Join-Path $State.launch_directory 'pids.json'), ($State | ConvertTo-Json -Depth 10), (New-Object Text.UTF8Encoding($false)))
    }
}

function Test-LabOwnedProcess([string]$ProjectRoot, $Entry) {
    $process = Get-Process -Id ([int]$Entry.pid) -ErrorAction SilentlyContinue
    if (-not $process) { return $false }
    try {
        $python = [IO.Path]::GetFullPath((Join-Path $ProjectRoot '.venv\Scripts\python.exe'))
        if (-not [StringComparer]::OrdinalIgnoreCase.Equals($process.Path, $python)) { return $false }
        # PowerShell 7 may deserialize ISO timestamps as DateTime rather than string.
        $savedTime = ([DateTime]$Entry.started_utc).ToUniversalTime()
        if ($process.StartTime.ToUniversalTime().Ticks -ne $savedTime.Ticks) { return $false }
        try {
            $details = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + [int]$Entry.pid) -ErrorAction Stop
            if (-not ($details.CommandLine.Contains($Entry.module) -and $details.CommandLine.Contains($Entry.instance))) { return $false }
        } catch {
            # Restricted Windows shells can deny CIM. Exact saved creation time and
            # the project executable still prevent stopping a process after PID reuse.
        }
        return $true
    } catch { return $false }
}

function Stop-LabOwnedProcesses([string]$ProjectRoot, $State) {
    if (-not [StringComparer]::OrdinalIgnoreCase.Equals([IO.Path]::GetFullPath($State.project_root), $ProjectRoot)) {
        throw 'PID file belongs to another project; no processes were stopped.'
    }
    $tokenPath = Join-Path $ProjectRoot '.runtime\agents\access.token'
    $token = if (Test-Path -LiteralPath $tokenPath) { [IO.File]::ReadAllText($tokenPath).Trim() } else { '' }
    foreach ($entry in $State.services) {
        if (Test-LabOwnedProcess $ProjectRoot $entry) {
            try {
                Invoke-RestMethod -Uri ('http://127.0.0.1:' + $entry.port + '/shutdown') -Method Post -Headers @{ Authorization = 'Bearer ' + $token } -TimeoutSec 2 | Out-Null
            } catch { } # Forced stop below handles an unresponsive owned service.
        }
    }
    $deadline = [DateTime]::UtcNow.AddSeconds(4)
    do {
        $remaining = @($State.services | Where-Object { Test-LabOwnedProcess $ProjectRoot $_ })
        if ($remaining.Count -eq 0) { break }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)
    foreach ($entry in $State.services) {
        # Check creation time, executable and instance again immediately before using its PID.
        if (Test-LabOwnedProcess $ProjectRoot $entry) {
            & taskkill.exe /PID ([string]$entry.pid) /T /F 2>&1 | Out-Null
        }
    }
    $alive = @($State.services | Where-Object { Test-LabOwnedProcess $ProjectRoot $_ })
    $State.status = if ($alive.Count) { 'STOP_FAILED' } else { 'STOPPED' }
    Save-LabProcessState $ProjectRoot $State
    if ($alive.Count) { throw 'Some owned services could not be stopped. Inspect the saved PID file and logs.' }
}
