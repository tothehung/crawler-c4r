"""Build, revise, review and export grounded knowledge for finding/evidence."""

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
from src.services.knowledge_builder import (
    build_page,
    claim,
    review_revision,
    save_revision,
)
from src.services.knowledge_evidence import export_knowledge


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
    build = commands.add_parser("build")
    build.add_argument("--pipeline-version", required=True)
    build.add_argument("--config", type=Path, required=True)
    build.add_argument("--after", default="")
    build.add_argument("--limit", type=int, default=100)
    show = commands.add_parser("show")
    show.add_argument("revision_id")
    revise = commands.add_parser(
        "revise",
        help="Create a new draft revision from a reviewed edit manifest; does not approve",
    )
    revise.add_argument("--input", type=Path, required=True)
    review = commands.add_parser("review")
    review.add_argument("revision_id")
    review.add_argument(
        "--status", choices=["approved", "rejected", "needs_review"], required=True
    )
    review.add_argument("--reviewer", required=True)
    review.add_argument("--note", required=True)
    review.add_argument("--expected-sequence", type=int, required=True)
    export = commands.add_parser("export")
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--include-candidates", action="store_true")
    export.add_argument("--link-id")
    export.add_argument("--max-rows", type=int, default=100_000)
    args = parser.parse_args()
    store = make_store(args)
    if args.command == "build":
        config = json.loads(args.config.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            parser.error("config must be a JSON object")
        result = build_page(
            store,
            pipeline_version=args.pipeline_version,
            config_hash=stable_hash(config),
            after=args.after,
            limit=args.limit,
        )
    elif args.command == "show":
        result = store.read("knowledge_revisions", args.revision_id)
        if result is None:
            parser.error("revision not found")
    elif args.command == "revise":
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        base = store.read("knowledge_revisions", payload["expected_revision_id"])
        if not base:
            parser.error("base revision not found")
        claims = [
            claim(c["category"], c["text"], c["citations"]) for c in payload["claims"]
        ]
        rev, created = save_revision(
            store,
            snapshot_id=base["snapshot_id"],
            processing_key=base["processing_key"],
            title=payload.get("title", base["title"]),
            claims=claims,
            missing_information=payload["missing_information"],
            extraction_version="authored-draft-v1",
            evidence_link_ids=base["evidence_link_ids"],
            expected_revision=base["revision_id"],
        )
        result = {"created": created, "revision": rev.model_dump(mode="json")}
    elif args.command == "review":
        result = review_revision(
            store,
            args.revision_id,
            status=args.status,
            reviewer=args.reviewer,
            note=args.note,
            expected_sequence=args.expected_sequence,
        ).model_dump(mode="json")
    else:
        if args.max_rows < 1:
            parser.error("max-rows must be positive")
        result = export_knowledge(
            store,
            include_candidates=args.include_candidates,
            link_id=args.link_id,
            max_rows=args.max_rows,
        )
        _atomic_json(args.output, result)
        result = {
            "output": str(args.output),
            "records": len(result["records"]),
            "include_candidates": args.include_candidates,
        }
    print(json.dumps(result, ensure_ascii=False))
    return (
        1
        if args.command == "build"
        and any(r["action"] == "error" for r in result["results"])
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
