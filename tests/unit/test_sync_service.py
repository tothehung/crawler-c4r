from __future__ import annotations

from pathlib import Path

from src.clients.solodit_client import PaginationOptions
from src.models import Finding
from src.services.finding_export_service import FindingExportResult
from src.services.load_service import FindingLoadResult
from src.services.sync_service import FindingSyncMode, FindingSyncService


class FakeExporter:
    def __init__(
        self,
        *,
        output_path: Path,
        findings: list[Finding] | None = None,
        export_result: FindingExportResult | None = None,
    ) -> None:
        self.output_path = output_path
        self.findings = findings or []
        self.export_result = export_result
        self.calls: list[dict[str, object]] = []

    def export_findings(
        self,
        page_size: int,
        filters: dict[str, object] | None = None,
        pagination: PaginationOptions | None = None,
    ) -> list[Finding]:
        self.calls.append(
            {
                "method": "export_findings",
                "page_size": page_size,
                "filters": filters,
                "pagination": pagination,
            }
        )
        return self.findings

    def export_findings_streaming(
        self,
        page_size: int,
        filters: dict[str, object] | None = None,
        pagination: PaginationOptions | None = None,
        resume: bool = False,
    ) -> FindingExportResult:
        self.calls.append(
            {
                "method": "export_findings_streaming",
                "page_size": page_size,
                "filters": filters,
                "pagination": pagination,
                "resume": resume,
            }
        )
        if self.export_result is None:
            raise AssertionError("export_result is required")
        return self.export_result


class FakeLoader:
    def __init__(self, result: FindingLoadResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def load_jsonl(
        self,
        input_path: Path,
        *,
        create_tables: bool = False,
        truncate_staging: bool = True,
        merge: bool = True,
    ) -> FindingLoadResult:
        self.calls.append(
            {
                "input_path": input_path,
                "create_tables": create_tables,
                "truncate_staging": truncate_staging,
                "merge": merge,
            }
        )
        return self.result


def _finding(identifier: str) -> Finding:
    return Finding(id=identifier, title=f"Finding {identifier}", slug=f"finding-{identifier}")


def _load_result(input_path: Path, records_seen: int) -> FindingLoadResult:
    return FindingLoadResult(
        input_path=input_path,
        records_seen=records_seen,
        rows_loaded=records_seen,
        staging_table_id="project.dataset.findings_staging",
        findings_table_id="project.dataset.findings",
        created_tables=False,
        truncated_staging=True,
        merged=True,
    )


def test_backfill_resumes_checkpoint_and_loads_when_records_written(tmp_path: Path) -> None:
    # Arrange
    output_path = tmp_path / "findings.jsonl"
    exporter = FakeExporter(
        output_path=output_path,
        export_result=FindingExportResult(
            output_path=output_path,
            checkpoint_path=tmp_path / "checkpoint.json",
            start_page=5,
            next_page=7,
            pages_written=2,
            records_written=100,
            total_pages=20,
            completed=False,
        ),
    )
    loader = FakeLoader(_load_result(output_path, records_seen=100))
    service = FindingSyncService(exporter=exporter, loader=loader)
    pagination = PaginationOptions(start_page=1, max_pages=2, request_delay_seconds=0)

    # Act
    result = service.backfill(page_size=50, pagination=pagination)

    # Assert
    assert result.mode == FindingSyncMode.BACKFILL
    assert result.exported_records == 100
    assert result.export_completed is False
    assert result.next_page == 7
    assert result.load_result is loader.result
    assert exporter.calls[0]["method"] == "export_findings_streaming"
    assert exporter.calls[0]["resume"] is True
    assert loader.calls == [
        {
            "input_path": output_path,
            "create_tables": False,
            "truncate_staging": True,
            "merge": True,
        }
    ]


def test_incremental_fetches_newest_pages_and_loads_output(tmp_path: Path) -> None:
    # Arrange
    output_path = tmp_path / "findings_incremental.jsonl"
    exporter = FakeExporter(
        output_path=output_path,
        findings=[_finding("1"), _finding("2")],
    )
    loader = FakeLoader(_load_result(output_path, records_seen=2))
    service = FindingSyncService(exporter=exporter, loader=loader)
    pagination = PaginationOptions(start_page=1, max_pages=10, request_delay_seconds=0)

    # Act
    result = service.incremental(page_size=50, pagination=pagination)

    # Assert
    assert result.mode == FindingSyncMode.INCREMENTAL
    assert result.exported_records == 2
    assert result.export_completed is None
    assert result.next_page is None
    assert result.load_result is loader.result
    assert exporter.calls[0]["method"] == "export_findings"
    assert exporter.calls[0]["pagination"] is pagination
    assert loader.calls[0]["input_path"] == output_path


def test_sync_skips_load_when_export_has_no_records(tmp_path: Path) -> None:
    # Arrange
    output_path = tmp_path / "findings_incremental.jsonl"
    exporter = FakeExporter(output_path=output_path, findings=[])
    loader = FakeLoader(_load_result(output_path, records_seen=0))
    service = FindingSyncService(exporter=exporter, loader=loader)

    # Act
    result = service.incremental(
        page_size=50,
        pagination=PaginationOptions(start_page=1, max_pages=10),
    )

    # Assert
    assert result.exported_records == 0
    assert result.load_result is None
    assert loader.calls == []
