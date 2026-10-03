"""Resolve the frozen reviewed corpus offline, retaining all missing-fixture errors."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx

from src.models.knowledge_contract import (
    SourceFindingSnapshot,
    snapshot_id,
    source_key,
    stable_hash,
)
from src.repositories.knowledge_store import SQLiteKnowledgeStore
from src.services.evidence.replay import replay_transport
from src.services.evidence.resolver import PIPELINE_VERSION, EvidenceResolver
from src.services.knowledge_processing import KnowledgeProcessingService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", type=Path, default=ROOT / "data/checkpoints/phase4-replay.sqlite3"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "data/processed/phase4-resolution.json"
    )
    args = parser.parse_args()
    fixtures = ROOT / "tests/fixtures/evidence_benchmark_v1"
    cases = json.loads((fixtures / "cases.json").read_text(encoding="utf-8"))
    annotations = json.loads(
        (fixtures / "annotations.json").read_text(encoding="utf-8")
    )
    excluded = {row["case_id"] for row in annotations if row["status"] == "quarantined"}
    config = json.loads(
        (ROOT / "config/knowledge_phase4_recorded.json").read_text(encoding="utf-8")
    )
    store = SQLiteKnowledgeStore(args.db)
    service = KnowledgeProcessingService(store)
    keys = {}
    for case in cases:
        if case["case_id"] in excluded:
            continue
        raw = case["finding"]
        key = source_key(case["source"], str(raw["id"]))
        digest = stable_hash(raw)
        snapshot = SourceFindingSnapshot(
            snapshot_id=snapshot_id(key, digest),
            source_key=key,
            source=case["source"],
            source_id=str(raw["id"]),
            source_url=case["provenance"]["source_url"],
            title=raw["title"],
            content=raw["content"],
            payload_kind="legacy_normalized_json",
            raw_payload=raw,
            raw_payload_hash=digest,
            captured_at=datetime.now(UTC),
        )
        state = service.enqueue(
            snapshot, pipeline_version=PIPELINE_VERSION, config=config
        )
        keys[state.processing_key] = case["case_id"]
    with httpx.Client(
        transport=replay_transport(fixtures / "http"), timeout=30
    ) as client:
        resolver = EvidenceResolver(client, config=config, store=store)
        service.run_batch(list(keys), resolver, worker="phase4-recorded", limit=100)
    states = [store.read("evidence_processing_state", key) for key in keys]
    links = [link for key in keys for link in store.links(key)]
    ids = {link["evidence_id"] for link in links if link["evidence_id"]}
    evidence = [store.read("code_evidence", key) for key in sorted(ids)]
    report = {
        "mode": "recorded_http_only",
        "pipeline_version": PIPELINE_VERSION,
        "scored_findings": len(keys),
        "quarantined": sorted(excluded),
        "states": dict(Counter(row["status"] for row in states)),
        "unique_evidence": len(evidence),
        "links": len(links),
        "resolution_status": dict(Counter(row["resolution_status"] for row in links)),
        "error_codes": dict(
            Counter(row["error_code"] for row in links if row["error_code"])
        ),
        "evidence_kinds": dict(Counter(row["origin_kind"] for row in evidence)),
        "syntax_status": dict(Counter(row["syntax_status"] for row in evidence)),
        "cases": [
            {
                "case_id": keys[row["processing_key"]],
                "processing_key": row["processing_key"],
                "status": row["status"],
                "resolved": row["resolved_count"],
                "unresolved": row["unresolved_count"],
            }
            for row in states
        ],
        "limitations": [
            "Missing recorded requests are fixture_missing, not real HTTP failures.",
            "Candidate recall is assessed separately; this is not vulnerability accuracy.",
            "Diff immutable metadata/source paths require synthetic coverage beyond the 7 recorded responses.",
            "Engine syntax validation and role accuracy evaluation remain separate.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in {"cases", "limitations"}},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
