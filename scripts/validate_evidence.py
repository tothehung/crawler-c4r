"""Annotate persisted evidence using the strict Go engine protocol."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.process_knowledge import make_store
from src.services.evidence.engine_validator import EngineValidator, validate_batch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--backend", choices=["sqlite", "bigquery"], default="sqlite")
    parser.add_argument(
        "--db", type=Path, default=ROOT / "data/checkpoints/knowledge.sqlite3"
    )
    parser.add_argument("--project-id")
    parser.add_argument("--dataset")
    parser.add_argument("--location")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--after", default="")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument(
        "--report", type=Path, help="Detailed engine response and mapping audit JSON"
    )
    args = parser.parse_args()
    validator = EngineValidator(args.engine, timeout=args.timeout)
    store = make_store(args)
    report = validate_batch(store, validator, after=args.after, limit=args.limit)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps({key: value for key, value in report.items() if key != "results"}))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
