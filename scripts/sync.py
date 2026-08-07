from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.clients.solodit_client import (
    DEFAULT_BASE_URL,
    DEFAULT_REQUEST_DELAY_SECONDS,
    PaginationOptions,
    SoloditClient,
)
from src.repositories import BigQueryFindingsRepository
from src.services import (
    DEFAULT_FINDINGS_CHECKPOINT_PATH,
    DEFAULT_FINDINGS_JSONL_PATH,
    DEFAULT_INCREMENTAL_FINDINGS_JSONL_PATH,
    DEFAULT_INCREMENTAL_MAX_PAGES,
    FindingExportService,
    FindingLoadService,
    FindingSyncMode,
    FindingSyncService,
)


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export Solodit findings and load them into BigQuery.",
    )
    parser.add_argument(
        "mode",
        choices=[mode.value for mode in FindingSyncMode],
        help="backfill resumes historical crawl; incremental scans newest pages.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Output JSONL path. Defaults to data/findings.jsonl for backfill "
            "and data/findings_incremental.jsonl for incremental."
        ),
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=DEFAULT_FINDINGS_CHECKPOINT_PATH,
        help="Backfill checkpoint path. Ignored by incremental mode.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=None,
        help="Number of findings per API page. Defaults to SOLODIT_PAGE_SIZE or 100.",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=1,
        help="First page for incremental mode. Backfill uses checkpoint when present.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help=(
            "Page limit. Backfill default is unlimited; incremental default is "
            "SOLODIT_INCREMENTAL_MAX_PAGES or 10."
        ),
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help="Delay in seconds between Solodit requests.",
    )
    parser.add_argument(
        "--project-id",
        default=None,
        help="BigQuery project id. Defaults to BIGQUERY_PROJECT_ID.",
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help="BigQuery dataset. Defaults to BIGQUERY_DATASET.",
    )
    parser.add_argument(
        "--location",
        default=None,
        help="BigQuery location. Defaults to BIGQUERY_LOCATION or US.",
    )
    parser.add_argument(
        "--create-tables",
        action="store_true",
        help="Create BigQuery dataset and findings tables before loading.",
    )
    parser.add_argument(
        "--no-truncate",
        action="store_true",
        help="Append to findings_staging instead of truncating it first.",
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="Load staging only and skip merge into findings.",
    )
    return parser.parse_args()


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def request_delay_seconds(cli_delay: float | None) -> float:
    if cli_delay is not None:
        return cli_delay

    env_delay = os.getenv("SOLODIT_REQUEST_DELAY_SECONDS")
    if env_delay:
        return float(env_delay)

    rate_limit_per_minute = os.getenv("SOLODIT_RATE_LIMIT_PER_MINUTE")
    if rate_limit_per_minute:
        return 60 / int(rate_limit_per_minute)

    return DEFAULT_REQUEST_DELAY_SECONDS


def page_size(cli_page_size: int | None) -> int:
    if cli_page_size is not None:
        return cli_page_size
    return int(os.getenv("SOLODIT_PAGE_SIZE", "100"))


def max_pages(mode: FindingSyncMode, cli_max_pages: int | None) -> int | None:
    if cli_max_pages is not None:
        return cli_max_pages
    if mode == FindingSyncMode.BACKFILL:
        return None
    return int(os.getenv("SOLODIT_INCREMENTAL_MAX_PAGES", str(DEFAULT_INCREMENTAL_MAX_PAGES)))


def output_path(mode: FindingSyncMode, cli_output: Path | None) -> Path:
    if cli_output is not None:
        return cli_output
    if mode == FindingSyncMode.BACKFILL:
        return DEFAULT_FINDINGS_JSONL_PATH
    return DEFAULT_INCREMENTAL_FINDINGS_JSONL_PATH


def required_setting(name: str, value: str | None) -> str:
    if not value:
        raise RuntimeError(f"Missing {name}. Set it in .env or pass the CLI flag.")
    return value


def build_client() -> SoloditClient:
    api_key = os.getenv("CYFRIN_API_KEY")
    base_url = os.getenv("SOLODIT_BASE_URL", DEFAULT_BASE_URL)
    return SoloditClient(api_key=api_key or "", base_url=base_url)


def build_repository(args: argparse.Namespace) -> BigQueryFindingsRepository:
    project_id = required_setting(
        "BIGQUERY_PROJECT_ID",
        args.project_id or os.getenv("BIGQUERY_PROJECT_ID"),
    )
    dataset = required_setting(
        "BIGQUERY_DATASET",
        args.dataset or os.getenv("BIGQUERY_DATASET"),
    )
    location = args.location or os.getenv("BIGQUERY_LOCATION", "US")
    return BigQueryFindingsRepository(
        project_id=project_id,
        dataset=dataset,
        location=location,
    )


def main() -> None:
    configure_logging()
    load_dotenv(PROJECT_ROOT / ".env")
    args = parse_args()

    mode = FindingSyncMode(args.mode)
    effective_page_size = page_size(args.page_size)
    effective_max_pages = max_pages(mode, args.max_pages)
    effective_output_path = output_path(mode, args.output)
    pagination = PaginationOptions(
        start_page=args.start_page,
        max_pages=effective_max_pages,
        request_delay_seconds=request_delay_seconds(args.delay),
    )

    export_service = FindingExportService(
        client=build_client(),
        output_path=effective_output_path,
        checkpoint_path=args.checkpoint,
    )
    load_service = FindingLoadService(build_repository(args))
    sync_service = FindingSyncService(exporter=export_service, loader=load_service)

    logger.info(
        "Starting findings sync",
        extra={
            "mode": mode.value,
            "output_path": str(effective_output_path),
            "page_size": effective_page_size,
            "start_page": args.start_page,
            "max_pages": effective_max_pages,
            "checkpoint_path": str(args.checkpoint),
            "create_tables": args.create_tables,
            "truncate_staging": not args.no_truncate,
            "merge": not args.no_merge,
        },
    )

    if mode == FindingSyncMode.BACKFILL:
        result = sync_service.backfill(
            page_size=effective_page_size,
            pagination=pagination,
            create_tables=args.create_tables,
            truncate_staging=not args.no_truncate,
            merge=not args.no_merge,
        )
    else:
        result = sync_service.incremental(
            page_size=effective_page_size,
            pagination=pagination,
            create_tables=args.create_tables,
            truncate_staging=not args.no_truncate,
            merge=not args.no_merge,
        )

    logger.info(
        "Finished findings sync",
        extra={
            "mode": result.mode.value,
            "output_path": str(result.output_path),
            "exported_records": result.exported_records,
            "export_completed": result.export_completed,
            "next_page": result.next_page,
            "loaded_records": result.load_result.records_seen
            if result.load_result
            else None,
            "rows_loaded": result.load_result.rows_loaded
            if result.load_result
            else None,
        },
    )


if __name__ == "__main__":
    main()
