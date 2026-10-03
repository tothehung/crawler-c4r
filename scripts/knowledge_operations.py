"""Finding duplicate indexing and scoped pipeline quality reports (phase 6)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.process_knowledge import make_store
from src.models.knowledge_contract import stable_hash
from src.services.evidence.repo_context import _atomic_json
from src.services.finding_dedup import DEDUP_VERSION, deduplicate_page
from src.services.knowledge_quality import quality_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["sqlite", "bigquery"], default="sqlite")
    parser.add_argument(
        "--db", type=Path, default=ROOT / "data/checkpoints/knowledge.sqlite3"
    )
    parser.add_argument("--project-id")
    parser.add_argument("--dataset")
    parser.add_argument("--location")
    commands = parser.add_subparsers(dest="command", required=True)
    dedup = commands.add_parser("dedup")
    dedup.add_argument("--after", default="")
    dedup.add_argument("--limit", type=int, default=100)
    dedup.add_argument("--max-pages", type=int, default=1)
    report = commands.add_parser("report")
    report.add_argument("--pipeline-version", required=True)
    report.add_argument("--config", type=Path, required=True)
    report.add_argument("--output", type=Path, required=True)
    report.add_argument("--max-rows", type=int, default=100_000)
    args = parser.parse_args()
    store = make_store(args)
    if args.command == "dedup":
        if not 1 <= args.max_pages <= 1000:
            parser.error("max-pages must be in 1..1000")
        cursor = args.after
        indexed = skipped = 0
        for _ in range(args.max_pages):
            page = deduplicate_page(store, after=cursor, limit=args.limit)
            indexed += page["indexed"]
            skipped += page["skipped"]
            cursor = page["next_after"] or cursor
            if page["page_rows"] < args.limit:
                break
        print(
            json.dumps(
                {
                    "dedup_version": DEDUP_VERSION,
                    "indexed": indexed,
                    "skipped": skipped,
                    "next_after": cursor,
                    "completed": page["page_rows"] < args.limit,
                }
            )
        )
    else:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        if not isinstance(config, dict) or args.max_rows < 1:
            parser.error("config must be an object and max-rows positive")
        report = quality_report(
            store,
            pipeline_version=args.pipeline_version,
            config_hash=stable_hash(config),
            max_rows=args.max_rows,
        )
        _atomic_json(args.output, report)
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "totals": report["totals"],
                    "operations": report["operations"],
                }
            )
        )


if __name__ == "__main__":
    main()
