param(
    [Parameter(Mandatory = $true)]
    [string]$Directory
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$queuePath = if ([IO.Path]::IsPathRooted($Directory)) { $Directory } else { Join-Path $projectRoot $Directory }
$queueRoot = [IO.Path]::GetFullPath($queuePath)
$plan = Join-Path $queueRoot 'plan.json'
$claim = Join-Path $queueRoot 'launch.claim'
if (-not (Test-Path -LiteralPath $plan)) { throw 'Prepare the queue first; plan.json is missing.' }
if (Test-Path -LiteralPath $claim) { throw 'This queue was already launched. Inspect its saved status.' }
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$script = Join-Path $projectRoot 'scripts\evaluation_queue.py'
$arguments = '-u "' + $script + '" run --directory "' + $queueRoot + '"'
$process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $projectRoot `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $queueRoot 'launcher.stdout.log') `
    -RedirectStandardError (Join-Path $queueRoot 'launcher.stderr.log')
[ordered]@{
    pid = $process.Id
    started_utc = $process.StartTime.ToUniversalTime().ToString('o')
    executable = $python
    queue_directory = $queueRoot
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $queueRoot 'launcher-pid.json') -Encoding utf8
Write-Output ('Queue launched. Progress: ' + (Join-Path $queueRoot 'progress.md'))
