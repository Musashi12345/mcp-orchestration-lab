"""Immutable run-owned files and strict, bounded CSV inspection."""

import asyncio
import csv
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .models import Dataset, FileRef, Limits, OrchestrationError, canonical
from .storage import Store, identity


class Files:
    def __init__(self, root: Path, store: Store, limits: Limits):
        self.root = root.resolve()
        self.store = store
        self.limits = limits

    async def _file_work(self, run_id, path, action, parents=()):
        payload = {"status": "RUNNING", "relative_path": path.relative_to(self.root).as_posix()}
        record_id = await self.store.put(run_id, "file_write", payload, parents=parents)
        pending = asyncio.create_task(asyncio.to_thread(action))
        try:
            result = await asyncio.shield(pending)
        except asyncio.CancelledError:
            try:
                await pending
            except BaseException:
                pass
            await self.store.finish(run_id, record_id, payload | {"status": "INTERRUPTED"})
            raise
        except BaseException as exc:
            await self.store.finish(
                run_id, record_id, payload | {"status": "FAILED", "error": str(exc)[:2000]}
            )
            raise
        await self.store.finish(run_id, record_id, payload | {"status": "SUCCEEDED"})
        return result

    def directory(self, run_id: str) -> Path:
        if not re.fullmatch(r"run_[a-f0-9]{32}", run_id):
            raise OrchestrationError("RUN_ID", "Invalid run directory identity.")
        directory = self.root / run_id
        directory.mkdir(parents=True, exist_ok=True)
        if not directory.resolve().is_relative_to(self.root):
            raise OrchestrationError("FILE_SCOPE", "Run directory escaped the configured root.")
        return directory

    async def put_json(self, run_id, value, *, parents=()) -> FileRef:
        data = canonical(value).encode()
        if len(data) > self.limits.max_result_bytes:
            raise OrchestrationError("RESULT_SIZE", "Tool output exceeded its byte allowance.")
        artifact_id = identity("artifact")
        path = self.directory(run_id) / (artifact_id + ".json")
        await self._file_work(run_id, path, lambda: self._write_new(path, data), parents)
        ref = FileRef(
            id=artifact_id, run_id=run_id, kind="json", sha256=hashlib.sha256(data).hexdigest()
        )
        await self.store.put(
            run_id,
            "artifact",
            {"ref": ref.model_dump(), "relative_path": path.relative_to(self.root).as_posix()},
            parents=parents,
            record_id=artifact_id,
        )
        return ref

    async def put_bytes(self, run_id, data: bytes, kind: str, *, parents=()):
        if kind not in {"png", "svg", "md", "csv", "json"}:
            raise OrchestrationError("FILE_KIND", "Unsupported output file kind.")
        if len(data) > self.limits.max_file_bytes:
            raise OrchestrationError("RESULT_SIZE", "Output exceeded its file allowance.")
        if kind == "csv":
            staged = self.directory(run_id) / (identity("staged") + ".csv")
            await self._file_work(run_id, staged, lambda: self._write_new(staged, data), parents)
            dataset = await self.register_csv(run_id, staged, parents=parents)
            return dataset.ref
        artifact_id = identity("artifact")
        path = self.directory(run_id) / (artifact_id + "." + kind)
        await self._file_work(run_id, path, lambda: self._write_new(path, data), parents)
        ref = FileRef(
            id=artifact_id, run_id=run_id, kind=kind, sha256=hashlib.sha256(data).hexdigest()
        )
        await self.store.put(
            run_id,
            "artifact",
            {
                "ref": ref.model_dump(),
                "relative_path": path.relative_to(self.root).as_posix(),
                "size_bytes": len(data),
            },
            parents=parents,
            record_id=artifact_id,
        )
        return ref

    async def checked_path(self, run_id, ref: FileRef):
        if ref.run_id != run_id:
            raise OrchestrationError("FILE_OWNERSHIP", "File belongs to another run.")
        row = await self.store.get(run_id, ref.id)
        stored = row["payload"].get("ref") or row["payload"].get("dataset", {}).get("ref")
        if stored != ref.model_dump():
            raise OrchestrationError(
                "FILE_REFERENCE", "File differs from its registered reference."
            )
        path = (self.root / row["payload"]["relative_path"]).resolve()
        if not path.is_relative_to(self.directory(run_id)):
            raise OrchestrationError("FILE_SCOPE", "File escaped its run directory.")

        def digest_file():
            with path.open("rb") as stream:
                return hashlib.file_digest(stream, "sha256").hexdigest()

        digest = await asyncio.to_thread(digest_file)
        if digest != ref.sha256:
            raise OrchestrationError("FILE_CHANGED", "Saved file content changed.")
        return path

    @staticmethod
    def _write_new(path, data):
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()

    async def read_json(self, run_id, ref: FileRef):
        if ref.run_id != run_id or ref.kind != "json":
            raise OrchestrationError("FILE_OWNERSHIP", "Output is not JSON owned by this run.")
        row = await self.store.get(run_id, ref.id)
        if row["kind"] != "artifact" or row["payload"]["ref"] != ref.model_dump():
            raise OrchestrationError(
                "FILE_REFERENCE", "Output differs from its registered reference."
            )
        path = (self.root / row["payload"]["relative_path"]).resolve()
        if not path.is_relative_to(self.directory(run_id)):
            raise OrchestrationError("FILE_SCOPE", "Output escaped its run directory.")
        data = await asyncio.to_thread(path.read_bytes)
        if hashlib.sha256(data).hexdigest() != ref.sha256:
            raise OrchestrationError("FILE_CHANGED", "Saved output content changed.")
        return json.loads(data)

    async def verify_csv(self, run_id, ref: FileRef):
        if ref.run_id != run_id or ref.kind != "csv":
            raise OrchestrationError("FILE_OWNERSHIP", "CSV is not owned by this run.")
        row = await self.store.get(run_id, ref.id)
        if row["kind"] != "dataset" or row["payload"]["dataset"]["ref"] != ref.model_dump():
            raise OrchestrationError("FILE_REFERENCE", "CSV differs from its registered reference.")
        path = (self.root / row["payload"]["relative_path"]).resolve()
        if not path.is_relative_to(self.directory(run_id)):
            raise OrchestrationError("FILE_SCOPE", "CSV escaped its run directory.")

        def digest_file():
            with path.open("rb") as stream:
                return hashlib.file_digest(stream, "sha256").hexdigest()

        if await asyncio.to_thread(digest_file) != ref.sha256:
            raise OrchestrationError("FILE_CHANGED", "Saved CSV content changed.")

    async def register_csv(
        self, run_id, source: Path, *, encoding="utf-8-sig", delimiter=",", parents=()
    ):
        if source.suffix.lower() != ".csv" or len(delimiter) != 1:
            raise OrchestrationError("CSV_INPUT", "Provide a CSV and a one-character separator.")
        artifact_id = identity("dataset")
        destination = self.directory(run_id) / (artifact_id + ".csv")

        def copy_and_inspect():
            digest = hashlib.sha256()
            total = 0
            with source.open("rb") as original, destination.open("xb") as saved:
                while chunk := original.read(65536):
                    total += len(chunk)
                    if total > self.limits.max_file_bytes:
                        raise OrchestrationError(
                            "CSV_SIZE", "CSV exceeded its file-size allowance."
                        )
                    digest.update(chunk)
                    saved.write(chunk)
            csv.field_size_limit(1048576)
            with destination.open(encoding=encoding, newline="") as stream:
                reader = csv.reader(stream, delimiter=delimiter, strict=True)
                columns = next(reader, None)
                if not columns or len(columns) > 256 or any(not name.strip() for name in columns):
                    raise OrchestrationError("CSV_HEADER", "CSV needs 1-256 nonempty column names.")
                if len(set(columns)) != len(columns):
                    raise OrchestrationError(
                        "CSV_HEADER", "Duplicate CSV column names are ambiguous."
                    )
                count, sample = 0, []
                missing = dict.fromkeys(columns, 0)
                observed = {name: set() for name in columns}
                for row in reader:
                    count += 1
                    if len(row) != len(columns):
                        raise OrchestrationError("CSV_ROW", f"CSV row {count + 1} has wrong width.")
                    for name, value in zip(columns, row, strict=True):
                        missing[name] += not value.strip()
                        if value.strip():
                            try:
                                number = Decimal(value)
                                kind = (
                                    "integer"
                                    if number.is_finite() and number == number.to_integral()
                                    else "number"
                                )
                                if not number.is_finite():
                                    kind = "text"
                            except InvalidOperation:
                                kind = "text"
                            observed[name].add(kind)
                    if len(sample) < self.limits.sample_rows:
                        sample.append(
                            {name: value[:512] for name, value in zip(columns, row, strict=True)}
                        )
            return Dataset(
                ref=FileRef(id=artifact_id, run_id=run_id, kind="csv", sha256=digest.hexdigest()),
                filename=source.name,
                row_count=count,
                columns=columns,
                missing_counts=missing,
                observed_types={name: sorted(values) for name, values in observed.items()},
                sample=sample,
                encoding=encoding,
                delimiter=delimiter,
            )

        try:
            dataset = await self._file_work(run_id, destination, copy_and_inspect, parents)
        except (UnicodeError, csv.Error) as exc:
            raise OrchestrationError("CSV_PARSE", str(exc)) from exc
        await self.store.put(
            run_id,
            "dataset",
            {
                "dataset": dataset.model_dump(mode="json"),
                "relative_path": destination.relative_to(self.root).as_posix(),
                "profile_scope": "full_file",
                "sample_cell_character_limit": 512,
            },
            record_id=artifact_id,
            parents=parents,
        )
        return dataset
