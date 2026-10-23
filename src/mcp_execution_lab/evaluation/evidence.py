"""Read only declared final outputs and checked run-owned file references."""

import csv
import json
from dataclasses import dataclass, field

from ..orchestration.models import FileRef, OrchestrationError


@dataclass
class Outputs:
    tables: list = field(default_factory=list)
    documents: list = field(default_factory=list)
    pngs: list = field(default_factory=list)
    reports: list = field(default_factory=list)
    references: list = field(default_factory=list)


async def collect(run_id, roots, files, *, input_ids=(), max_files=128):
    value = Outputs()
    seen = {}

    async def visit(item, depth=0):
        if depth > 16:
            raise OrchestrationError("EVAL_OUTPUT_SIZE", "Final output references are too deep.")
        if isinstance(item, list):
            for child in item:
                await visit(child, depth + 1)
        elif isinstance(item, dict):
            if {"id", "run_id", "kind", "sha256"} <= item.keys():
                ref = FileRef.model_validate(item)
                if ref.run_id != run_id:
                    raise OrchestrationError("FILE_OWNERSHIP", "Output references another run.")
                if ref.id in seen:
                    if seen[ref.id] != ref.model_dump():
                        raise OrchestrationError("FILE_REFERENCE", "Conflicting output references.")
                    return
                if len(seen) >= max_files:
                    raise OrchestrationError(
                        "EVAL_OUTPUT_SIZE", "Too many referenced output files."
                    )
                seen[ref.id] = ref.model_dump()
                path = await files.checked_path(run_id, ref)
                if path.stat().st_size > 16 * 1024 * 1024:
                    raise OrchestrationError("EVAL_OUTPUT_SIZE", "An output file is too large.")
                value.references.append(ref.model_dump())
                if ref.kind == "json":
                    data = json.loads(path.read_text(encoding="utf-8"))
                    value.documents.append(data)
                    if isinstance(data, dict):
                        for key in ("rows", "answer_rows"):
                            if isinstance(data.get(key), list):
                                value.tables.append(data[key])
                        details = data.get("details", {})
                        if isinstance(details, dict) and isinstance(details.get("groups"), list):
                            value.tables.append(
                                [g["group"] | g["metrics"] for g in details["groups"]]
                            )
                    await visit(data, depth + 1)
                elif ref.kind == "csv" and ref.id not in input_ids:
                    record = await files.store.get(run_id, ref.id)
                    info = record["payload"].get("dataset", {})
                    with path.open(
                        encoding=info.get("encoding", "utf-8-sig"), newline=""
                    ) as stream:
                        value.tables.append(
                            list(csv.DictReader(stream, delimiter=info.get("delimiter", ",")))
                        )
                elif ref.kind == "png":
                    if not path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
                        raise OrchestrationError("EVAL_IMAGE", "Chart is not a PNG file.")
                    value.pngs.append(ref.id)
                elif ref.kind == "md":
                    value.reports.append(path.read_text(encoding="utf-8"))
                return
            for child in item.values():
                await visit(child, depth + 1)

    for root in roots:
        await visit(root)
    return value
