import json

import pytest

from mcp_execution_lab import cli


@pytest.mark.parametrize(
    "command",
    [
        "doctor",
        "runner-build",
        "serve",
        "fixture-check",
        "run",
        "batch",
        "compare",
        "analyze",
        "inspect",
        "export",
    ],
)
def test_removed_pricing_commands_are_not_exposed(command, capsys):
    with pytest.raises(SystemExit) as error:
        cli.main([command])
    assert error.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


@pytest.mark.parametrize("command, marker", [("analysis", "db-init"), ("eval", "grade")])
def test_csv_commands_forward_nested_help(command, marker, capsys):
    with pytest.raises(SystemExit) as error:
        cli.main([command, "--help"])
    assert error.value.code == 0
    assert marker in capsys.readouterr().out


def test_public_evaluation_listing_needs_no_database_or_provider(monkeypatch, capsys):
    monkeypatch.delenv("MCP_LAB_DATABASE_URL", raising=False)
    assert cli.main(["eval", "list"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert len(result["tasks"]) == 15
    assert result["suite_sha256"]


def test_models_uses_retained_csv_bridge_without_pricing_imports(monkeypatch, capsys):
    async def models(directory):
        assert directory.name == "model_discovery"
        return {"data": [{"id": "fixed-test-model"}]}

    monkeypatch.setattr(cli, "discover_codex_models", models)
    assert cli.main(["models"]) == 0
    assert json.loads(capsys.readouterr().out) == {"data": [{"id": "fixed-test-model"}]}
