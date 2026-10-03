"""Knowledge intake, live/recorded resolution, and processing state."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.models.knowledge_contract import (
    CodeEvidence,
    FindingEvidenceLink,
    SourceFindingSnapshot,
)
from src.repositories.knowledge_store import SQLiteKnowledgeStore
from src.services.knowledge_processing import (
    KnowledgeProcessingService,
    ResolutionResult,
    legacy_snapshot,
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["sqlite", "bigquery"], default="sqlite")
    parser.add_argument(
        "--db", type=Path, default=ROOT / "data/checkpoints/knowledge.sqlite3"
    )
    parser.add_argument("--project-id")
    parser.add_argument("--dataset")
    parser.add_argument("--location")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Initialize storage; run with workers stopped")
    ingest = commands.add_parser(
        "ingest", help="Persist JSONL input and enqueue processing"
    )
    ingest.add_argument("--input", type=Path, required=True)
    ingest.add_argument("--format", choices=["contract", "legacy"], default="contract")
    ingest.add_argument("--source", choices=["solodit", "code4rena"])
    ingest.add_argument("--pipeline-version", required=True)
    ingest.add_argument(
        "--config",
        type=Path,
        required=True,
        help="JSON object of output-affecting settings; no secrets",
    )
    ingest.add_argument("--max-attempts", type=int, default=3)
    ingest.add_argument("--limit", type=int, default=100)
    ingest.add_argument(
        "--offset", type=int, default=0, help="Number of physical JSONL lines to skip"
    )
    status = commands.add_parser(
        "status", help="Read a bounded page of processing state"
    )
    status.add_argument("--after", default="")
    status.add_argument("--limit", type=int, default=100)
    apply = commands.add_parser(
        "apply-results", help="Run a bounded batch of complete resolver manifests"
    )
    apply.add_argument("--input", type=Path, required=True)
    apply.add_argument("--worker", default="manifest-worker")
    apply.add_argument("--limit", type=int, default=100)
    apply.add_argument("--lease-seconds", type=int, default=300)
    run = commands.add_parser(
        "run", help="Resolve a bounded page of matching queued findings"
    )
    run.add_argument("--config", type=Path, required=True)
    run.add_argument(
        "--replay-http",
        type=Path,
        help="Recorded HTTP directory with index.json; no network fallback",
    )
    run.add_argument("--worker", default="resolver-worker")
    run.add_argument("--limit", type=int, default=20)
    run.add_argument("--after", default="")
    run.add_argument("--lease-seconds", type=int, default=300)
    run.add_argument(
        "--checkpoint",
        help="Named resumable multi-page sweep; do not combine with --after",
    )
    run.add_argument("--max-pages", type=int, default=1)
    return parser.parse_args()


def make_store(args):
    if args.backend == "sqlite":
        return SQLiteKnowledgeStore(args.db)
    from dotenv import load_dotenv

    from src.repositories.bigquery_knowledge_store import BigQueryKnowledgeStore

    load_dotenv(ROOT / ".env")
    return BigQueryKnowledgeStore(
        project_id=args.project_id or os.environ["BIGQUERY_PROJECT_ID"],
        dataset=args.dataset or os.environ["BIGQUERY_DATASET"],
        location=args.location or os.getenv("BIGQUERY_LOCATION", "US"),
    )


def emit(value):
    print(json.dumps(value, ensure_ascii=False))


def run_resolver(args, store, service):
    import httpx
    from dotenv import load_dotenv

    from src.models.knowledge_contract import stable_hash
    from src.services.evidence.replay import replay_transport
    from src.services.evidence.resolver import (
        PIPELINE_VERSION,
        EvidenceResolver,
        ResolverConfig,
    )

    config = json.loads(args.config.read_text(encoding="utf-8"))
    settings = ResolverConfig.model_validate(config)
    if (settings.transport_mode == "recorded") != bool(args.replay_http):
        raise ValueError(
            "transport_mode must agree with --replay-http; use a new fingerprint for live runs"
        )
    if args.checkpoint and args.after:
        raise ValueError("Use checkpoint or --after, not both")
    if not args.checkpoint and args.max_pages != 1:
        raise ValueError("--max-pages requires --checkpoint")
    states = [] if args.checkpoint else store.states(after=args.after, limit=args.limit)
    keys = [
        row["processing_key"]
        for row in states
        if row["pipeline_version"] == PIPELINE_VERSION
        and row["config_hash"] == stable_hash(config)
    ]
    load_dotenv(ROOT / ".env")
    transport = replay_transport(args.replay_http) if args.replay_http else None
    with httpx.Client(transport=transport, timeout=30, trust_env=False) as client:

        def resolve(snapshot, lease):
            last = time.monotonic()

            def heartbeat():
                nonlocal last
                if time.monotonic() - last >= args.lease_seconds / 3:
                    service.heartbeat(lease, lease_seconds=args.lease_seconds)
                    last = time.monotonic()

            resolver = EvidenceResolver(
                client,
                config=config,
                store=store,
                token=os.getenv("GITHUB_TOKEN") if transport is None else None,
                heartbeat=heartbeat,
            )
            return resolver(snapshot, lease)

        if args.checkpoint:
            from src.services.knowledge_batch import run_sweep

            report = run_sweep(
                store,
                resolve,
                name=args.checkpoint,
                pipeline_version=PIPELINE_VERSION,
                config=config,
                page_size=args.limit,
                max_pages=args.max_pages,
                worker=args.worker,
                lease_seconds=args.lease_seconds,
                service=service,
            )
            emit(report)
            return
        results = service.run_batch(
            keys,
            resolve,
            worker=args.worker,
            limit=args.limit,
            lease_seconds=args.lease_seconds,
        )
    emit(
        {
            "attempted": len(results),
            "page_rows": len(states),
            "next_after": states[-1]["processing_key"] if states else None,
            "states": [row.model_dump(mode="json") for row in results],
        }
    )


def main():
    args = parse_args()
    if hasattr(args, "limit") and not 1 <= args.limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    store = make_store(args)
    service = KnowledgeProcessingService(store)
    if args.command == "init":
        if args.backend == "bigquery":
            for name in [
                "001_knowledge_contract_v1.sql",
                "002_knowledge_processing_guard.sql",
                "003_knowledge_operations.sql",
                "004_grounded_knowledge.sql",
            ]:
                store.repository.execute_sql_file(ROOT / "sql/migrations" / name)
        emit({"initialized": args.backend})
    elif args.command == "status":
        for row in store.states(after=args.after, limit=args.limit):
            emit(row)
    elif args.command == "run":
        run_resolver(args, store, service)
    elif args.command == "ingest":
        if args.offset < 0 or (args.format == "legacy" and not args.source):
            raise ValueError(
                "Nonnegative offset and explicit source for legacy input required"
            )
        config = json.loads(args.config.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("config must be a JSON object")
        count = 0
        with args.input.open(encoding="utf-8") as stream:
            for index, line in enumerate(stream):
                if index < args.offset or not line.strip():
                    continue
                row = json.loads(line)
                snapshot = (
                    legacy_snapshot(
                        row, source=args.source, captured_at=datetime.now(UTC)
                    )
                    if args.format == "legacy"
                    else SourceFindingSnapshot.model_validate(row)
                )
                state = service.enqueue(
                    snapshot,
                    pipeline_version=args.pipeline_version,
                    config=config,
                    max_attempts=args.max_attempts,
                )
                emit(
                    {
                        "processing_key": state.processing_key,
                        "snapshot_id": state.snapshot_id,
                        "status": state.status,
                        "next_offset": index + 1,
                    }
                )
                count += 1
                if count >= args.limit:
                    break
    else:
        # Parse/validate the full bounded batch before any claim. A missing or
        # malformed manifest must never be interpreted as an empty finding.
        manifests = {}
        with args.input.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                row = json.loads(line)
                key = row["processing_key"]
                if key in manifests:
                    raise ValueError("Duplicate processing key in manifest")
                if row.get("inventory_complete") is not True:
                    raise ValueError(
                        "Manifest must explicitly assert inventory_complete=true"
                    )
                manifests[key] = ResolutionResult(
                    candidate_count=row["candidate_count"],
                    evidence=[CodeEvidence.model_validate(e) for e in row["evidence"]],
                    links=[
                        FindingEvidenceLink.model_validate(link)
                        for link in row["links"]
                    ],
                    retry_after=row.get("retry_after", 0),
                )
                if len(manifests) >= args.limit:
                    break
        results = service.run_batch(
            list(manifests),
            lambda snapshot, lease: manifests[lease.processing_key],
            worker=args.worker,
            limit=args.limit,
            lease_seconds=args.lease_seconds,
        )
        emit(
            {
                "attempted": len(results),
                "skipped": len(manifests) - len(results),
                "states": [state.model_dump(mode="json") for state in results],
            }
        )


if __name__ == "__main__":
    main()
