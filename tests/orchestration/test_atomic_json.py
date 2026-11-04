import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from mcp_execution_lab.orchestration import atomic_json
from mcp_execution_lab.orchestration.budget import Budget
from mcp_execution_lab.orchestration.models import Limits, OrchestrationError


def denied(code):
    error = PermissionError("Fixed Windows file sharing failure")
    error.winerror = code
    return error


def test_json_snapshot_retries_only_transient_windows_replace(tmp_path, monkeypatch):
    path = tmp_path / "manifest.json"
    path.write_text('{"state":"old"}')
    replace = Path.replace
    attempts, waits = [], []

    def busy(source, destination):
        attempts.append(source)
        if len(attempts) <= 2:
            raise denied(32)
        return replace(source, destination)

    monkeypatch.setattr(Path, "replace", busy)
    monkeypatch.setattr(atomic_json.time, "sleep", waits.append)
    atomic_json.save_json(path, {"state": "new"})
    assert json.loads(path.read_text()) == {"state": "new"}
    assert len(attempts) == 3 and waits == [0.025, 0.05]
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("code,expected_waits", [(5, 5), (32, 5), (33, 5), (13, 0)])
def test_permanent_denial_retains_old_snapshot_and_new_evidence(
    tmp_path, monkeypatch, code, expected_waits
):
    path = tmp_path / "manifest.json"
    path.write_text('{"state":"old"}')
    waits = []

    def busy(*args):
        raise denied(code)

    monkeypatch.setattr(Path, "replace", busy)
    monkeypatch.setattr(atomic_json.time, "sleep", waits.append)
    with pytest.raises(PermissionError):
        atomic_json.save_json(path, {"state": "new"})
    assert json.loads(path.read_text()) == {"state": "old"}
    pending = list(tmp_path.glob("*.tmp"))
    assert len(pending) == 1
    assert json.loads(pending[0].read_text()) == {"state": "new"}
    assert len(waits) == expected_waits


def test_concurrent_snapshots_have_unique_temporary_files(tmp_path):
    path = tmp_path / "manifest.json"
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda value: atomic_json.save_json(path, {"writer": value}), range(8)))
    assert json.loads(path.read_text())["writer"] in range(8)
    assert not list(tmp_path.glob("*.tmp"))


def test_token_and_time_exhaustion_report_different_causes():
    budget = Budget(Limits(max_observed_tokens=300000))
    budget.tokens = 300001
    with pytest.raises(OrchestrationError, match="Observed token allowance"):
        budget.check()
    budget.started -= budget.limits.run_seconds
    with pytest.raises(OrchestrationError, match="Run time allowance"):
        budget.check()
