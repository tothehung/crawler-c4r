from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from src.clients.solodit_client import PaginationOptions, PROJECT_ROOT
from src.mappers import BigQueryRow, finding_to_bigquery_row
from src.models import Finding


DEFAULT_FINDINGS_JSONL_PATH = PROJECT_ROOT / "data" / "findings.jsonl"
DEFAULT_FINDINGS_CHECKPOINT_PATH = (
    PROJECT_ROOT / "data" / "checkpoints" / "findings_export.json"
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FindingExportCheckpoint:
    next_page: int
    last_completed_page: int | None
    pages_written: int
    records_written: int
    total_pages: int | None
    completed: bool


@dataclass(frozen=True)
class FindingExportResult:
    output_path: Path
    checkpoint_path: Path
    start_page: int
    next_page: int
    pages_written: int
    records_written: int
    total_pages: int | None
    completed: bool


class FindingsClient(Protocol):
    def fetch_findings(
        self,
        page_size: int,
        filters: dict[str, Any] | None = None,
        pagination: PaginationOptions | None = None,
    ) -> list[dict[str, Any]]:
        ...

    def iter_findings_pages(
        self,
        page_size: int,
        filters: dict[str, Any] | None = None,
        pagination: PaginationOptions | None = None,
    ) -> Any:
        ...


class FindingExportService:
    def __init__(
        self,
        client: FindingsClient,
        output_path: Path = DEFAULT_FINDINGS_JSONL_PATH,
        checkpoint_path: Path = DEFAULT_FINDINGS_CHECKPOINT_PATH,
    ) -> None:
        self.client = client
        self.output_path = output_path
        self.checkpoint_path = checkpoint_path

    def export_findings(
        self,
        page_size: int,
        filters: dict[str, Any] | None = None,
        pagination: PaginationOptions | None = None,
    ) -> list[Finding]:
        raw_findings = self.client.fetch_findings(
            page_size=page_size,
            filters=filters,
            pagination=pagination,
        )
        findings = [Finding.model_validate(raw_finding) for raw_finding in raw_findings]
        self.write_jsonl(findings, crawled_at=datetime.now(UTC))
        return findings

    def export_findings_streaming(
        self,
        page_size: int,
        filters: dict[str, Any] | None = None,
        pagination: PaginationOptions | None = None,
        resume: bool = False,
    ) -> FindingExportResult:
        pagination = pagination or PaginationOptions()
        checkpoint = self.read_checkpoint() if resume else None

        if checkpoint and checkpoint.completed:
            return FindingExportResult(
                output_path=self.output_path,
                checkpoint_path=self.checkpoint_path,
                start_page=checkpoint.next_page,
                next_page=checkpoint.next_page,
                pages_written=0,
                records_written=0,
                total_pages=checkpoint.total_pages,
                completed=True,
            )

        start_page = checkpoint.next_page if checkpoint else pagination.start_page
        effective_pagination = PaginationOptions(
            start_page=start_page,
            max_pages=pagination.max_pages,
            stop_condition=pagination.stop_condition,
            request_delay_seconds=pagination.request_delay_seconds,
        )

        if checkpoint is None:
            self.reset_output()
            self.write_checkpoint(
                FindingExportCheckpoint(
                    next_page=start_page,
                    last_completed_page=None,
                    pages_written=0,
                    records_written=0,
                    total_pages=None,
                    completed=False,
                )
            )

        pages_written = 0
        records_written = 0
        total_pages: int | None = checkpoint.total_pages if checkpoint else None
        completed = False
        next_page = start_page

        for findings_page in self.client.iter_findings_pages(
            page_size=page_size,
            filters=filters,
            pagination=effective_pagination,
        ):
            crawled_at = datetime.now(UTC)
            findings = [
                Finding.model_validate(raw_finding)
                for raw_finding in findings_page.findings
            ]
            self.append_jsonl(findings, crawled_at=crawled_at)

            pages_written += 1
            records_written += len(findings)
            total_pages = findings_page.total_pages
            next_page = findings_page.current_page + 1
            completed = (
                not findings_page.findings
                or findings_page.current_page >= findings_page.total_pages
            )

            self.write_checkpoint(
                FindingExportCheckpoint(
                    next_page=next_page,
                    last_completed_page=findings_page.current_page,
                    pages_written=(checkpoint.pages_written if checkpoint else 0)
                    + pages_written,
                    records_written=(checkpoint.records_written if checkpoint else 0)
                    + records_written,
                    total_pages=total_pages,
                    completed=completed,
                )
            )
            logger.info(
                "Wrote Solodit findings page",
                extra={
                    "current_page": findings_page.current_page,
                    "total_pages": findings_page.total_pages,
                    "records_written": len(findings),
                    "next_page": next_page,
                    "completed": completed,
                },
            )

        return FindingExportResult(
            output_path=self.output_path,
            checkpoint_path=self.checkpoint_path,
            start_page=start_page,
            next_page=next_page,
            pages_written=pages_written,
            records_written=records_written,
            total_pages=total_pages,
            completed=completed,
        )

    def write_jsonl(
        self,
        findings: list[Finding],
        *,
        crawled_at: datetime | None = None,
    ) -> None:
        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            with self.output_path.open("w", encoding="utf-8", newline="\n") as output_file:
                self.write_jsonl_records(output_file, findings, crawled_at=crawled_at)
        except OSError as exc:
            raise RuntimeError(
                f"Failed to write findings JSONL to {self.output_path}: {exc}"
            ) from exc

    def reset_output(self) -> None:
        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            self.output_path.write_text("", encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(
                f"Failed to initialize findings JSONL at {self.output_path}: {exc}"
            ) from exc

    def append_jsonl(
        self,
        findings: list[Finding],
        *,
        crawled_at: datetime | None = None,
    ) -> None:
        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            with self.output_path.open("a", encoding="utf-8", newline="\n") as output_file:
                self.write_jsonl_records(output_file, findings, crawled_at=crawled_at)
        except OSError as exc:
            raise RuntimeError(
                f"Failed to append findings JSONL to {self.output_path}: {exc}"
            ) from exc

    def read_checkpoint(self) -> FindingExportCheckpoint | None:
        if not self.checkpoint_path.exists():
            return None

        checkpoint_data = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        return FindingExportCheckpoint(
            next_page=int(checkpoint_data["next_page"]),
            last_completed_page=checkpoint_data.get("last_completed_page"),
            pages_written=int(checkpoint_data.get("pages_written", 0)),
            records_written=int(checkpoint_data.get("records_written", 0)),
            total_pages=checkpoint_data.get("total_pages"),
            completed=bool(checkpoint_data.get("completed", False)),
        )

    def write_checkpoint(self, checkpoint: FindingExportCheckpoint) -> None:
        try:
            self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            self.checkpoint_path.write_text(
                json.dumps(asdict(checkpoint), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise RuntimeError(
                f"Failed to write findings checkpoint to {self.checkpoint_path}: {exc}"
            ) from exc

    @classmethod
    def write_jsonl_records(
        cls,
        output_file: Any,
        findings: list[Finding],
        *,
        crawled_at: datetime | None = None,
        loaded_at: datetime | None = None,
    ) -> None:
        crawled_at = cls._utc_now_if_none(crawled_at)
        loaded_at = cls._utc_now_if_none(loaded_at)
        for finding in findings:
            cls.write_jsonl_record(
                output_file,
                finding_to_bigquery_row(
                    finding,
                    crawled_at=crawled_at,
                    loaded_at=loaded_at,
                ),
            )

    @staticmethod
    def write_jsonl_record(output_file: Any, row: BigQueryRow) -> None:
        output_file.write(
            json.dumps(
                row,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        output_file.write("\n")

    @staticmethod
    def _utc_now_if_none(value: datetime | None) -> datetime:
        if value is None:
            return datetime.now(UTC)
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
