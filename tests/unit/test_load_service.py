from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services.load_service import FindingLoadService


class FakeWarehouse:
    staging_table_id = "project.dataset.findings_staging"
    findings_table_id = "project.dataset.findings"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def create_schema_and_tables(self) -> None:
        self.calls.append("create_schema_and_tables")

    def truncate_staging_table(self) -> None:
        self.calls.append("truncate_staging_table")

    def load_jsonl_to_staging(self, jsonl_path: Path) -> int:
        self.calls.append(f"load_jsonl_to_staging:{jsonl_path.name}")
        return 2

    def merge_staging(self) -> None:
        self.calls.append("merge_staging")


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def test_load_jsonl_validates_loads_and_merges(tmp_path: Path) -> None:
    # Arrange
    input_path = tmp_path / "findings.jsonl"
    _write_jsonl(input_path, [{"id": "1"}, {"id": "2"}])
    warehouse = FakeWarehouse()
    service = FindingLoadService(warehouse)

    # Act
    result = service.load_jsonl(input_path=input_path, create_tables=True)

    # Assert
    assert result.records_seen == 2
    assert result.rows_loaded == 2
    assert result.staging_table_id == warehouse.staging_table_id
    assert result.findings_table_id == warehouse.findings_table_id
    assert result.created_tables is True
    assert result.truncated_staging is True
    assert result.merged is True
    assert warehouse.calls == [
        "create_schema_and_tables",
        "truncate_staging_table",
        "load_jsonl_to_staging:findings.jsonl",
        "merge_staging",
    ]


def test_load_jsonl_can_skip_truncate_and_merge(tmp_path: Path) -> None:
    # Arrange
    input_path = tmp_path / "findings.jsonl"
    _write_jsonl(input_path, [{"id": "1"}])
    warehouse = FakeWarehouse()
    service = FindingLoadService(warehouse)

    # Act
    result = service.load_jsonl(
        input_path=input_path,
        truncate_staging=False,
        merge=False,
    )

    # Assert
    assert result.records_seen == 1
    assert result.truncated_staging is False
    assert result.merged is False
    assert warehouse.calls == ["load_jsonl_to_staging:findings.jsonl"]


def test_validate_jsonl_raises_for_missing_file(tmp_path: Path) -> None:
    service = FindingLoadService(FakeWarehouse())

    with pytest.raises(FileNotFoundError):
        service.validate_jsonl(tmp_path / "missing.jsonl")


def test_validate_jsonl_raises_for_invalid_json(tmp_path: Path) -> None:
    input_path = tmp_path / "findings.jsonl"
    input_path.write_text('{"id": "1"}\nnot-json\n', encoding="utf-8")
    service = FindingLoadService(FakeWarehouse())

    with pytest.raises(ValueError, match="Invalid JSONL"):
        service.validate_jsonl(input_path)


def test_validate_jsonl_raises_for_non_object_record(tmp_path: Path) -> None:
    input_path = tmp_path / "findings.jsonl"
    input_path.write_text('["not", "object"]\n', encoding="utf-8")
    service = FindingLoadService(FakeWarehouse())

    with pytest.raises(ValueError, match="JSON object"):
        service.validate_jsonl(input_path)


def test_validate_jsonl_raises_for_empty_file(tmp_path: Path) -> None:
    input_path = tmp_path / "findings.jsonl"
    input_path.write_text("\n", encoding="utf-8")
    service = FindingLoadService(FakeWarehouse())

    with pytest.raises(ValueError, match="no records"):
        service.validate_jsonl(input_path)
