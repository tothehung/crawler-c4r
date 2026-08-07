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
from src.services import (
    DEFAULT_FINDINGS_CHECKPOINT_PATH,
    DEFAULT_FINDINGS_JSONL_PATH,
    FindingExportService,
)


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Solodit findings, validate them, and export JSONL.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_FINDINGS_JSONL_PATH,
        help="Output JSONL path. Defaults to data/findings.jsonl.",
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
        help="First Solodit API page to fetch.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Optional page limit for safe test runs.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help="Delay in seconds between page requests.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=DEFAULT_FINDINGS_CHECKPOINT_PATH,
        help="Checkpoint JSON path. Defaults to data/checkpoints/findings_export.json.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint and append to the existing output file.",
    )
    parser.add_argument(
        "--no-streaming",
        action="store_true",
        help="Use the legacy fetch-all-then-write mode.",
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


def build_client() -> SoloditClient:
    api_key = os.getenv("CYFRIN_API_KEY")
    base_url = os.getenv("SOLODIT_BASE_URL", DEFAULT_BASE_URL)
    return SoloditClient(api_key=api_key or "", base_url=base_url)


def main() -> None:
    configure_logging()
    load_dotenv(PROJECT_ROOT / ".env")
    args = parse_args()

    service = FindingExportService(
        client=build_client(),
        output_path=args.output,
        checkpoint_path=args.checkpoint,
    )
    pagination = PaginationOptions(
        start_page=args.start_page,
        max_pages=args.max_pages,
        request_delay_seconds=request_delay_seconds(args.delay),
    )

    logger.info(
        "Starting Solodit findings export",
        extra={
            "output_path": str(args.output),
            "page_size": page_size(args.page_size),
            "start_page": args.start_page,
            "max_pages": args.max_pages,
            "checkpoint_path": str(args.checkpoint),
            "resume": args.resume,
            "streaming": not args.no_streaming,
        },
    )

    if args.no_streaming:
        findings = service.export_findings(
            page_size=page_size(args.page_size),
            pagination=pagination,
        )
        written_records = len(findings)
        completed = True
        next_page = None
        pages_written = None
    else:
        result = service.export_findings_streaming(
            page_size=page_size(args.page_size),
            pagination=pagination,
            resume=args.resume,
        )
        written_records = result.records_written
        completed = result.completed
        next_page = result.next_page
        pages_written = result.pages_written

    logger.info(
        "Finished Solodit findings export",
        extra={
            "output_path": str(args.output),
            "written_records": written_records,
            "pages_written": pages_written,
            "next_page": next_page,
            "completed": completed,
        },
    )


if __name__ == "__main__":
    main()
