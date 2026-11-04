import pytest
from pydantic import ValidationError

from mcp_execution_lab.agents.cleaning.models import Operation, Recipe, Rules
from mcp_execution_lab.agents.cleaning.operations import clean
from mcp_execution_lab.agents.common.models import NeedsInput, Table
from mcp_execution_lab.orchestration.mcp import Connections
from mcp_execution_lab.orchestration.models import FileRef, ServerConfig

from .workers import agent_episode


def test_cleaning_preserves_source_and_explains_each_change():
    ref = FileRef(id="dataset_test", run_id="run_" + "a" * 32, kind="csv", sha256="a" * 64)
    table = Table(
        ref=ref,
        columns=["id", "value"],
        rows=[
            {"id": "001", "value": " a "},
            {"id": "001", "value": " a "},
            {"id": "002", "value": ""},
        ],
    )
    recipe = Recipe(
        operations=[
            Operation(action="trim", column="value", reason="Explicit rule"),
            Operation(action="remove_exact_duplicates", reason="Exact repeated rows"),
        ]
    )
    rows, changes, mapping, details = clean(
        table, recipe, Rules(trim_columns=["value"], remove_exact_duplicates=True)
    )
    assert rows == [{"id": "001", "value": "a"}, {"id": "002", "value": ""}]
    assert table.rows[0]["value"] == " a "
    assert mapping == [2, 4] and details.removed_rows == 1 and len(changes) == 3
    with pytest.raises(NeedsInput, match="does not allow"):
        clean(table, recipe, Rules())


async def test_cleaning_through_real_mcp_registers_a_new_dataset(tmp_path):
    def arguments(context, job):
        return {
            "job": {"kind": "literal", "value": job},
            "dataset": {"kind": "dataset", "key": context["datasets"][0]["ref"]["id"]},
            "rules": {
                "kind": "literal",
                "value": {"trim_columns": ["value"], "remove_exact_duplicates": True},
            },
        }

    result, value, published, records = await agent_episode(
        tmp_path,
        "data_cleaning",
        "clean_data",
        {
            "operations": [
                {"action": "trim", "column": "value", "reason": "Explicit rule"},
                {"action": "remove_exact_duplicates", "reason": "Exact duplicate"},
            ]
        },
        arguments,
    )
    assert result["status"] == "COMPLETED"
    assert value["details"]["after_rows"] == 2
    assert published[value["datasets"][0]["id"]].decode() == "id,value\n001,a\n002,b\n"
    assert (
        len([row for row in records if row["kind"] == "dataset"]) == 3
    )  # Source, cleaned, changes.


def test_label_normalization_is_explicit_and_rejects_unknown_values():
    ref = FileRef(id="dataset_test", run_id="run_" + "a" * 32, kind="csv", sha256="a" * 64)
    table = Table(ref=ref, columns=["id", "region"], rows=[{"id": "001", "region": " nOrTh "}])
    recipe = Recipe(
        operations=[
            Operation(action="trim", column="region", reason="Requested"),
            Operation(action="normalize_label", column="region", reason="Requested labels"),
        ]
    )
    rules = Rules(trim_columns=["region"], label_values={"region": ["North", "South"]})
    rows, changes, _, _ = clean(table, recipe, rules)
    assert rows == [{"id": "001", "region": "North"}]
    assert len(changes) == 2 and table.rows[0]["region"] == " nOrTh "
    with pytest.raises(NeedsInput, match="does not allow"):
        clean(table, recipe, Rules(trim_columns=["region"]))
    unknown = table.model_copy(update={"rows": [{"id": "001", "region": "unknown"}]})
    with pytest.raises(NeedsInput, match="Unexpected label"):
        clean(unknown, recipe, rules)


@pytest.mark.parametrize("labels", [[], ["North", "north"], [" North"], [""]])
def test_ambiguous_or_empty_labels_are_rejected(labels):
    with pytest.raises(ValidationError):
        Rules(label_values={"region": labels})


async def test_real_mcp_definition_requires_cleaning_rules():
    server = ServerConfig(
        id="cleaner", command="{python}", args=["-m", "mcp_execution_lab.agents.cleaning.server"]
    )
    async with Connections([server]) as connections:
        cache = await connections.discover()
    definition = cache.lookup("cleaner", "clean_data")
    assert "rules" in definition.input_schema["required"]
    assert "label_values" in str(definition.input_schema)


async def test_empty_cleaning_rules_need_input_before_any_worker_model_call(tmp_path):
    def arguments(context, job):
        return {
            "job": {"kind": "literal", "value": job},
            "dataset": {"kind": "dataset", "key": context["datasets"][0]["ref"]["id"]},
            "rules": {"kind": "literal", "value": {}},
        }

    result, value, _, records = await agent_episode(
        tmp_path, "data_cleaning", "clean_data", {}, arguments
    )
    assert result["status"] == "FAILED"
    assert value["outcome"] == "NEEDS_INPUT"
    assert not [
        row for row in records if row["kind"] == "model_call" and row["payload"]["role"] == "worker"
    ]


@pytest.mark.parametrize(
    "text,wanted",
    [
        ("1,799.99", "1799.99"),
        ("-1,149.50", "-1149.50"),
        ("+2,499.00", "2499.00"),
        ("1,234,567.89", "1234567.89"),
        (" 1,000 ", "1000"),
        ("", ""),
    ],
)
def test_cleaning_parses_grouped_amounts_only_in_authorized_numeric_columns(text, wanted):
    ref = FileRef(id="dataset_test", run_id="run_" + "a" * 32, kind="csv", sha256="a" * 64)
    table = Table(ref=ref, columns=["id", "amount"], rows=[{"id": "001", "amount": text}])
    recipe = Recipe(operations=[Operation(action="convert_number", column="amount", reason="Rule")])
    rows, _, mapping, _ = clean(table, recipe, Rules(number_columns=["amount"]))
    assert rows == [{"id": "001", "amount": wanted}] and mapping == [2]
    assert table.rows == [{"id": "001", "amount": text}]
    with pytest.raises(NeedsInput, match="does not allow"):
        clean(table, recipe, Rules())


@pytest.mark.parametrize("text", ["1,79", "1,234,56", "12,34", "₹1,234.00", "1,234,", "NaN"])
def test_bad_numeric_text_reports_source_row_and_column(text):
    ref = FileRef(id="dataset_test", run_id="run_" + "a" * 32, kind="csv", sha256="a" * 64)
    table = Table(ref=ref, columns=["amount"], rows=[{"amount": text}])
    recipe = Recipe(operations=[Operation(action="convert_number", column="amount", reason="Rule")])
    with pytest.raises(NeedsInput, match="'amount' at source row 2"):
        clean(table, recipe, Rules(number_columns=["amount"]))
    assert table.rows == [{"amount": text}]
