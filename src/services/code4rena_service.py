from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.clients.code4rena_client import Code4renaClient, Code4renaContest
from src.clients.solodit_client import PROJECT_ROOT
from src.mappers.finding_mapper import BigQueryRow, finding_to_bigquery_row
from src.models import Finding

DEFAULT_CODE4RENA_JSONL_PATH = PROJECT_ROOT / "data" / "findings_code4rena.jsonl"
DEFAULT_CODE4RENA_CHECKPOINT_PATH = (
    PROJECT_ROOT / "data" / "checkpoints" / "code4rena_checkpoint.json"
)

logger = logging.getLogger(__name__)


@dataclass
class Code4renaCheckpoint:
    completed_slugs: list[str] = field(default_factory=list)
    last_completed_slug: str | None = None
    contests_processed: int = 0
    records_written: int = 0
    total_contests: int = 0
    completed: bool = False
    updated_at: str = ""


@dataclass(frozen=True)
class Code4renaExportResult:
    output_path: Path
    checkpoint_path: Path
    contests_processed: int
    records_written: int
    total_contests: int
    completed: bool


class Code4renaExportService:
    """Orchestrates streaming extraction of Code4rena audit findings to JSONL."""

    def __init__(
        self,
        client: Code4renaClient,
        output_path: Path = DEFAULT_CODE4RENA_JSONL_PATH,
        checkpoint_path: Path = DEFAULT_CODE4RENA_CHECKPOINT_PATH,
    ) -> None:
        self.client = client
        self.output_path = output_path
        self.checkpoint_path = checkpoint_path

    def export_all(
        self,
        *,
        max_contests: int | None = None,
        resume: bool = True,
        allowed_severities: set[str] | None = None,
    ) -> Code4renaExportResult:
        """Export findings from Code4rena contests to JSONL with checkpointing."""
        checkpoint = self.read_checkpoint() if resume else None

        if checkpoint and checkpoint.completed:
            logger.info("Code4rena export already marked completed in checkpoint.")
            return Code4renaExportResult(
                output_path=self.output_path,
                checkpoint_path=self.checkpoint_path,
                contests_processed=checkpoint.contests_processed,
                records_written=checkpoint.records_written,
                total_contests=checkpoint.total_contests,
                completed=True,
            )

        if checkpoint is None:
            self.reset_output()
            checkpoint = Code4renaCheckpoint()

        completed_slugs_set = set(checkpoint.completed_slugs)

        # 1. Fetch contest list
        all_contests = self.client.fetch_all_contests()
        checkpoint.total_contests = len(all_contests)
        logger.info("Total Code4rena contests available: %d", len(all_contests))

        # Filter contests that have not yet been processed
        pending_contests = [c for c in all_contests if c.slug not in completed_slugs_set]
        logger.info("Pending contests to process: %d", len(pending_contests))

        if max_contests is not None and max_contests > 0:
            pending_contests = pending_contests[:max_contests]
            logger.info("Limited to %d contests for this run", len(pending_contests))

        contests_in_this_run = 0
        records_in_this_run = 0

        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        for contest in pending_contests:
            try:
                raw_findings = self.client.fetch_report_findings(contest)
                findings_to_write: list[Finding] = []

                for raw_finding in raw_findings:
                    # Filter severity if specified
                    impact = str(raw_finding.get("impact", "")).upper()
                    if allowed_severities and impact not in allowed_severities:
                        continue

                    try:
                        finding_obj = Finding.model_validate(raw_finding)
                        findings_to_write.append(finding_obj)
                    except Exception as val_err:
                        logger.warning(
                            "Failed to validate finding %s: %s",
                            raw_finding.get("id"),
                            val_err,
                        )

                # Append findings to JSONL
                if findings_to_write:
                    self.append_findings_jsonl(findings_to_write)
                    records_in_this_run += len(findings_to_write)

                contests_in_this_run += 1
                checkpoint.completed_slugs.append(contest.slug)
                completed_slugs_set.add(contest.slug)
                checkpoint.last_completed_slug = contest.slug
                checkpoint.contests_processed += 1
                checkpoint.records_written += len(findings_to_write)
                checkpoint.completed = len(completed_slugs_set) >= len(all_contests)
                checkpoint.updated_at = datetime.now(UTC).isoformat()

                self.write_checkpoint(checkpoint)

                logger.info(
                    "Processed [%s] (%d/%d) - Extracted %d findings (Total: %d)",
                    contest.slug,
                    checkpoint.contests_processed,
                    checkpoint.total_contests,
                    len(findings_to_write),
                    checkpoint.records_written,
                )

            except Exception as exc:
                logger.error("Error processing contest %s: %s", contest.slug, exc, exc_info=True)
                # Continue with next contest so a single error doesn't abort the entire crawl
                continue

        return Code4renaExportResult(
            output_path=self.output_path,
            checkpoint_path=self.checkpoint_path,
            contests_processed=contests_in_this_run,
            records_written=records_in_this_run,
            total_contests=checkpoint.total_contests,
            completed=checkpoint.completed,
        )

    def append_findings_jsonl(
        self,
        findings: list[Finding],
        *,
        crawled_at: datetime | None = None,
    ) -> None:
        crawled_at = crawled_at or datetime.now(UTC)
        rows = [
            finding_to_bigquery_row(finding, crawled_at=crawled_at)
            for finding in findings
        ]
        with self.output_path.open("a", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
                f.write("\n")

    def reset_output(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text("", encoding="utf-8")
        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()

    def read_checkpoint(self) -> Code4renaCheckpoint | None:
        if not self.checkpoint_path.exists():
            return None
        try:
            data = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
            return Code4renaCheckpoint(
                completed_slugs=data.get("completed_slugs", []),
                last_completed_slug=data.get("last_completed_slug"),
                contests_processed=int(data.get("contests_processed", 0)),
                records_written=int(data.get("records_written", 0)),
                total_contests=int(data.get("total_contests", 0)),
                completed=bool(data.get("completed", False)),
                updated_at=data.get("updated_at", ""),
            )
        except Exception as exc:
            logger.warning("Could not read checkpoint %s: %s", self.checkpoint_path, exc)
            return None

    def write_checkpoint(self, checkpoint: Code4renaCheckpoint) -> None:
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path.write_text(
            json.dumps(asdict(checkpoint), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
