from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.clients.solodit_client import PROJECT_ROOT


DEFAULT_FINDINGS_JSONL_PATH = PROJECT_ROOT / "data" / "findings.jsonl"


class FindingsWarehouse(Protocol):
    staging_table_id: str
    findings_table_id: str

    def create_schema_and_tables(self) -> None:
        ...

    def truncate_staging_table(self) -> None:
        ...

    def load_jsonl_to_staging(self, jsonl_path: Path) -> int | None:
        ...

    def merge_staging(self) -> None:
        ...


@dataclass(frozen=True)
class FindingLoadResult:
    input_path: Path
    records_seen: int
    rows_loaded: int | None
    staging_table_id: str
    findings_table_id: str
    created_tables: bool
    truncated_staging: bool
    merged: bool


class FindingLoadService:
    def __init__(self, warehouse: FindingsWarehouse) -> None:
        self.warehouse = warehouse

    def load_jsonl(
        self,
        input_path: Path = DEFAULT_FINDINGS_JSONL_PATH,
        *,
        create_tables: bool = False,
        truncate_staging: bool = True,
        merge: bool = True,
    ) -> FindingLoadResult:
        records_seen = self.validate_jsonl(input_path)

        if create_tables:
            self.warehouse.create_schema_and_tables()

        if truncate_staging:
            self.warehouse.truncate_staging_table()

        rows_loaded = self.warehouse.load_jsonl_to_staging(input_path)

        if merge:
            self.warehouse.merge_staging()

        return FindingLoadResult(
            input_path=input_path,
            records_seen=records_seen,
            rows_loaded=rows_loaded,
            staging_table_id=self.warehouse.staging_table_id,
            findings_table_id=self.warehouse.findings_table_id,
            created_tables=create_tables,
            truncated_staging=truncate_staging,
            merged=merge,
        )

    @staticmethod
    def validate_jsonl(input_path: Path) -> int:
        if not input_path.exists():
            raise FileNotFoundError(f"Findings JSONL does not exist: {input_path}")

        records_seen = 0
        with input_path.open("r", encoding="utf-8") as input_file:
            for line_number, line in enumerate(input_file, start=1):
                if not line.strip():
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSONL at {input_path}:{line_number}: {exc.msg}"
                    ) from exc

                if not isinstance(record, dict):
                    raise ValueError(
                        f"Invalid JSONL at {input_path}:{line_number}: "
                        "each record must be a JSON object"
                    )

                records_seen += 1

        if records_seen == 0:
            raise ValueError(f"Findings JSONL has no records: {input_path}")

        return records_seen
