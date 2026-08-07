from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from src.clients.solodit_client import PaginationOptions, PROJECT_ROOT
from src.models import Finding
from src.services.finding_export_service import FindingExportResult
from src.services.load_service import FindingLoadResult


DEFAULT_INCREMENTAL_FINDINGS_JSONL_PATH = (
    PROJECT_ROOT / "data" / "findings_incremental.jsonl"
)
DEFAULT_INCREMENTAL_MAX_PAGES = 10


class FindingSyncMode(StrEnum):
    BACKFILL = "backfill"
    INCREMENTAL = "incremental"


class Exporter(Protocol):
    output_path: Path

    def export_findings(
        self,
        page_size: int,
        filters: dict[str, object] | None = None,
        pagination: PaginationOptions | None = None,
    ) -> list[Finding]:
        ...

    def export_findings_streaming(
        self,
        page_size: int,
        filters: dict[str, object] | None = None,
        pagination: PaginationOptions | None = None,
        resume: bool = False,
    ) -> FindingExportResult:
        ...


class Loader(Protocol):
    def load_jsonl(
        self,
        input_path: Path,
        *,
        create_tables: bool = False,
        truncate_staging: bool = True,
        merge: bool = True,
    ) -> FindingLoadResult:
        ...


@dataclass(frozen=True)
class FindingSyncResult:
    mode: FindingSyncMode
    output_path: Path
    exported_records: int
    export_completed: bool | None
    next_page: int | None
    load_result: FindingLoadResult | None


class FindingSyncService:
    def __init__(self, exporter: Exporter, loader: Loader) -> None:
        self.exporter = exporter
        self.loader = loader

    def backfill(
        self,
        *,
        page_size: int,
        pagination: PaginationOptions,
        create_tables: bool = False,
        truncate_staging: bool = True,
        merge: bool = True,
    ) -> FindingSyncResult:
        export_result = self.exporter.export_findings_streaming(
            page_size=page_size,
            pagination=pagination,
            resume=True,
        )
        load_result = self._load_if_records_written(
            records_written=export_result.records_written,
            create_tables=create_tables,
            truncate_staging=truncate_staging,
            merge=merge,
        )
        return FindingSyncResult(
            mode=FindingSyncMode.BACKFILL,
            output_path=self.exporter.output_path,
            exported_records=export_result.records_written,
            export_completed=export_result.completed,
            next_page=export_result.next_page,
            load_result=load_result,
        )

    def incremental(
        self,
        *,
        page_size: int,
        pagination: PaginationOptions,
        create_tables: bool = False,
        truncate_staging: bool = True,
        merge: bool = True,
    ) -> FindingSyncResult:
        findings = self.exporter.export_findings(
            page_size=page_size,
            pagination=pagination,
        )
        load_result = self._load_if_records_written(
            records_written=len(findings),
            create_tables=create_tables,
            truncate_staging=truncate_staging,
            merge=merge,
        )
        return FindingSyncResult(
            mode=FindingSyncMode.INCREMENTAL,
            output_path=self.exporter.output_path,
            exported_records=len(findings),
            export_completed=None,
            next_page=None,
            load_result=load_result,
        )

    def _load_if_records_written(
        self,
        *,
        records_written: int,
        create_tables: bool,
        truncate_staging: bool,
        merge: bool,
    ) -> FindingLoadResult | None:
        if records_written == 0:
            return None
        return self.loader.load_jsonl(
            input_path=self.exporter.output_path,
            create_tables=create_tables,
            truncate_staging=truncate_staging,
            merge=merge,
        )
