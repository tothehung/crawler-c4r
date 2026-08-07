from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.repositories import BigQueryFindingsRepository
from src.services import DEFAULT_FINDINGS_JSONL_PATH, FindingLoadService


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load exported Solodit findings JSONL into BigQuery.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_FINDINGS_JSONL_PATH,
        help="Input JSONL path. Defaults to data/findings.jsonl.",
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
        help="Create dataset and findings tables before loading.",
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


def required_setting(name: str, value: str | None) -> str:
    if not value:
        raise RuntimeError(f"Missing {name}. Set it in .env or pass the CLI flag.")
    return value


def main() -> None:
    configure_logging()
    load_dotenv(PROJECT_ROOT / ".env")
    args = parse_args()

    project_id = required_setting(
        "BIGQUERY_PROJECT_ID",
        args.project_id or os.getenv("BIGQUERY_PROJECT_ID"),
    )
    dataset = required_setting(
        "BIGQUERY_DATASET",
        args.dataset or os.getenv("BIGQUERY_DATASET"),
    )
    location = args.location or os.getenv("BIGQUERY_LOCATION", "US")

    repository = BigQueryFindingsRepository(
        project_id=project_id,
        dataset=dataset,
        location=location,
    )
    service = FindingLoadService(repository)

    logger.info(
        "Starting BigQuery findings load",
        extra={
            "input_path": str(args.input),
            "project_id": project_id,
            "dataset": dataset,
            "location": location,
            "create_tables": args.create_tables,
            "truncate_staging": not args.no_truncate,
            "merge": not args.no_merge,
        },
    )
    result = service.load_jsonl(
        input_path=args.input,
        create_tables=args.create_tables,
        truncate_staging=not args.no_truncate,
        merge=not args.no_merge,
    )
    logger.info(
        "Finished BigQuery findings load",
        extra={
            "records_seen": result.records_seen,
            "rows_loaded": result.rows_loaded,
            "staging_table_id": result.staging_table_id,
            "findings_table_id": result.findings_table_id,
            "merged": result.merged,
        },
    )


if __name__ == "__main__":
    main()
