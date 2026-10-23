"""Real Windows process lifecycle; no model calls or production database needed."""

import json
import os
import secrets
import shutil
import socket
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != "nt", reason="PowerShell PID management is Windows-specific.")
def test_start_discovery_repeat_start_and_safe_stop(tmp_path):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        pytest.skip("PowerShell unavailable")
    root = Path(__file__).resolve().parents[2]
    for _ in range(50):
        sockets = []
        try:
            port = 10000 + secrets.randbelow(20000)
            for offset in range(7):
                item = socket.socket()
                item.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sockets.append(item)
                item.bind(("127.0.0.1", port + offset))
            break
        except OSError:
            continue
        finally:
            for item in sockets:
                item.close()
    else:
        pytest.fail("No contiguous test port range available")
    script = tmp_path / "lifecycle.ps1"
    script.write_text(
        r"""
$ErrorActionPreference='Stop'
. (Join-Path (Get-Location) 'scripts/agent_processes.ps1')
$victim=$null
try {
    .\start_agents.ps1 -BasePort TEST_PORT -StartupSeconds 45
    $before=Get-Content .runtime/agents/pids.json -Raw | ConvertFrom-Json
    .\start_agents.ps1 -BasePort TEST_PORT
    $after=Get-Content .runtime/agents/pids.json -Raw | ConvertFrom-Json
    if($before.instance -ne $after.instance){throw 'Repeated start created duplicate processes.'}
    $token=[IO.File]::ReadAllText((Join-Path (Get-Location) '.runtime/agents/access.token')).Trim()
    $headers=@{Authorization='Bearer '+$token}
    $tools=Invoke-RestMethod -Uri http://127.0.0.1:TEST_PORT/tools -Headers $headers -TimeoutSec 30
    if($tools.tools.Count -ne 6){throw 'Expected six MCP tools.'}
    .\stop_agents.ps1
    $state=Get-Content .runtime/agents/pids.json -Raw | ConvertFrom-Json
    foreach($entry in $state.services){
        if(Test-LabOwnedProcess (Get-Location).Path $entry){throw 'Owned PID survived stop.'}
    }
    $victimArgs=@('-c','"import time; time.sleep(60)"')
    $victim=Start-Process -FilePath .\.venv\Scripts\python.exe -ArgumentList $victimArgs `
        -WindowStyle Hidden -PassThru
    $state.services[0].pid=$victim.Id
    $state.services[0].started_utc='2000-01-01T00:00:00Z'
    Save-LabProcessState (Get-Location).Path $state
    .\stop_agents.ps1
    if(-not (Get-Process -Id $victim.Id -ErrorAction SilentlyContinue)){
        throw 'Stop killed an unrelated PID.'
    }
    Write-Output 'Lifecycle, discovery, repeated start and stale-PID protection verified.'
} finally {
    .\stop_agents.ps1
    if($victim -and (Get-Process -Id $victim.Id -ErrorAction SilentlyContinue)){
        & taskkill.exe /PID ([string]$victim.Id) /T /F 2>&1 | Out-Null
    }
}
""".replace("TEST_PORT", str(port)),
        encoding="utf-8",
    )
    result = subprocess.run(
        [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=90,
    )
    (tmp_path / "lifecycle.stdout.txt").write_text(result.stdout, encoding="utf-8")
    (tmp_path / "lifecycle.stderr.txt").write_text(result.stderr, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    state = json.loads((root / ".runtime/agents/pids.json").read_text(encoding="utf-8"))
    assert state["status"] == "STOPPED"
