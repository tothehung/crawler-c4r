"""Enrich evidence from explicitly mapped local Git repositories at pinned commits."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.process_knowledge import make_store
from src.services.evidence.engine_validator import EngineValidator
from src.services.evidence.repo_context import enrich_batch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument(
        "--repo-map",
        type=Path,
        required=True,
        help="JSON object mapping owner/repo to local Git checkout",
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "data/processed/engine-context"
    )
    parser.add_argument("--backend", choices=["sqlite", "bigquery"], default="sqlite")
    parser.add_argument(
        "--db", type=Path, default=ROOT / "data/checkpoints/knowledge.sqlite3"
    )
    parser.add_argument("--project-id")
    parser.add_argument("--dataset")
    parser.add_argument("--location")
    parser.add_argument("--after", default="")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    repositories = json.loads(args.repo_map.read_text(encoding="utf-8"))
    if not isinstance(repositories, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in repositories.items()
    ):
        parser.error("repo-map must map repository names to local paths")
    report = enrich_batch(
        make_store(args),
        EngineValidator(args.engine, timeout=args.timeout),
        repositories,
        args.output,
        after=args.after,
        limit=args.limit,
    )
    print(json.dumps({k: v for k, v in report.items() if k != "results"}))
    return 1 if report["counts"]["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
