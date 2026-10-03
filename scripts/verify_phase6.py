"""Offline phase-6 operational proof: real replay plus a labeled synthetic load."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx

from scripts.export_knowledge_contract import example_bundle
from src.models.knowledge_contract import (
    CodeEvidence,
    FindingEvidenceLink,
    SourceFindingSnapshot,
    snapshot_id,
    source_key,
    stable_hash,
)
from src.repositories.knowledge_store import SQLiteKnowledgeStore
from src.services.evidence.replay import replay_transport
from src.services.evidence.repo_context import _atomic_json
from src.services.evidence.resolver import PIPELINE_VERSION, EvidenceResolver
from src.services.finding_dedup import deduplicate_page
from src.services.knowledge_batch import run_sweep
from src.services.knowledge_processing import (
    KnowledgeProcessingService,
    ResolutionResult,
    legacy_snapshot,
)
from src.services.knowledge_quality import iter_records, quality_report


def index_all(store, page_size=100):
    cursor = ""
    indexed = skipped = 0
    while True:
        page = deduplicate_page(store, after=cursor, limit=page_size)
        indexed += page["indexed"]
        skipped += page["skipped"]
        if page["page_rows"] < page_size:
            return {"indexed": indexed, "skipped": skipped}
        cursor = page["next_after"]


def real_replay(directory):
    fixtures = ROOT / "tests/fixtures/evidence_benchmark_v1"
    cases = json.loads((fixtures / "cases.json").read_text(encoding="utf-8"))
    excluded = {
        r["case_id"]
        for r in json.loads((fixtures / "annotations.json").read_text(encoding="utf-8"))
        if r["status"] == "quarantined"
    }
    config = json.loads(
        (ROOT / "config/knowledge_phase4_recorded.json").read_text(encoding="utf-8")
    )
    store = SQLiteKnowledgeStore(directory / "real.sqlite3")
    service = KnowledgeProcessingService(store)
    for case in cases:
        if case["case_id"] in excluded:
            continue
        raw = case["finding"]
        skey = source_key(case["source"], str(raw["id"]))
        digest = stable_hash(raw)
        snap = SourceFindingSnapshot(
            snapshot_id=snapshot_id(skey, digest),
            source_key=skey,
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
        service.enqueue(snap, pipeline_version=PIPELINE_VERSION, config=config)
    steps = []
    with httpx.Client(
        transport=replay_transport(fixtures / "http"), timeout=30
    ) as client:
        resolver = EvidenceResolver(client, config=config, store=store)
        for size in (5, 10, 20):
            steps.append(
                run_sweep(
                    store,
                    resolver,
                    name="real",
                    pipeline_version=PIPELINE_VERSION,
                    config=config,
                    page_size=size,
                )
            )
        before_evidence = {
            r["evidence_id"] for r in iter_records(store, "code_evidence")
        }
        before_links = {
            r["link_id"] for r in iter_records(store, "finding_evidence_links")
        }
        rerun = run_sweep(
            store,
            resolver,
            name="real",
            pipeline_version=PIPELINE_VERSION,
            config=config,
            page_size=100,
        )
        assert {
            r["evidence_id"] for r in iter_records(store, "code_evidence")
        } == before_evidence
        assert {
            r["link_id"] for r in iter_records(store, "finding_evidence_links")
        } == before_links
    indexed = index_all(store)
    report = quality_report(
        store, pipeline_version=PIPELINE_VERSION, config_hash=stable_hash(config)
    )
    return {
        "mode": "recorded_http_only",
        "quarantined": sorted(excluded),
        "batch_steps": steps,
        "rerun": rerun,
        "dedup": indexed,
        "quality": report,
    }


def synthetic_load(directory, size):
    store = SQLiteKnowledgeStore(directory / "synthetic.sqlite3")
    now = [datetime.now(UTC)]
    service = KnowledgeProcessingService(store, clock=lambda: now[0])
    evidence = CodeEvidence.model_validate(example_bundle()["code_evidence"][0])
    snapshots = []
    for index in range(size):
        snap = legacy_snapshot(
            {
                "id": str(index),
                "title": f"Synthetic finding pair {index//2}",
                "content": f"Synthetic operation fixture {index}; not a real security finding.",
                "source_link": f"https://github.com/example/synthetic-findings/issues/{index//2+1}",
            },
            source="solodit" if index % 2 == 0 else "code4rena",
            captured_at=now[0],
        )
        snapshots.append(snap)
        service.enqueue(snap, pipeline_version="synthetic-v1", config={})
    calls = [0]

    def resolve(snap, lease):
        calls[0] += 1
        locator = "body:link:0"
        link = FindingEvidenceLink(
            link_id="lnk_" + stable_hash(["link-v1", lease.processing_key, locator]),
            snapshot_id=snap.snapshot_id,
            processing_key=lease.processing_key,
            candidate_locator=locator,
            evidence_id=evidence.evidence_id,
            resolution_status="resolved",
            created_at=now[0],
        )
        return ResolutionResult(1, [evidence], [link])

    def interrupted(snap, lease):
        if calls[0] == 6:
            raise KeyboardInterrupt("injected interruption before outputs commit")
        return resolve(snap, lease)

    kwargs = {
        "name": "load",
        "pipeline_version": "synthetic-v1",
        "config": {},
        "service": service,
        "lease_seconds": 10,
    }
    interrupted_observed = False
    try:
        run_sweep(store, interrupted, page_size=5, max_pages=3, **kwargs)
    except KeyboardInterrupt:
        interrupted_observed = True
    assert interrupted_observed
    now[0] += timedelta(seconds=11)
    steps = []
    for page_size in (10, 100, 1000):
        steps.append(
            run_sweep(store, resolve, page_size=page_size, max_pages=1, **kwargs)
        )
        if steps[-1]["checkpoint"]["completed"]:
            break
    while not steps[-1]["checkpoint"]["completed"]:
        steps.append(run_sweep(store, resolve, page_size=1000, max_pages=1, **kwargs))
    assert (
        run_sweep(store, resolve, page_size=1000, max_pages=100, **kwargs)["attempted"]
        == 0
    )
    first_index = index_all(store)
    assert index_all(store)["skipped"] == size
    quality = quality_report(
        store, pipeline_version="synthetic-v1", config_hash=stable_hash({})
    )
    assert (
        quality["totals"]["links"] == size and quality["totals"]["unique_evidence"] == 1
    )
    assert quality["finding_dedup"]["source_findings_linked"] == size // 2
    for snap in snapshots:
        service.enqueue(snap, pipeline_version="synthetic-v2", config={})
    upgraded = run_sweep(
        store,
        resolve,
        page_size=1000,
        max_pages=100,
        **(kwargs | {"pipeline_version": "synthetic-v2"}),
    )
    assert upgraded["attempted"] == size
    assert len(list(iter_records(store, "code_evidence"))) == 1
    assert len(list(iter_records(store, "finding_evidence_links"))) == size * 2
    return {
        "mode": "synthetic_not_crawl_accuracy",
        "size": size,
        "interruption_recovered": interrupted_observed,
        "batch_steps": steps,
        "dedup": first_index,
        "quality": quality,
        "upgrade": upgraded,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic-size", type=int, default=1000)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "data/processed/phase6-verification.json"
    )
    args = parser.parse_args()
    if not 10 <= args.synthetic_size <= 10_000:
        parser.error("synthetic-size must be in 10..10000")
    directory = ROOT / "data/checkpoints/phase6-runs" / uuid4().hex
    directory.mkdir(parents=True)
    start = time.monotonic()
    real = real_replay(directory)
    print(json.dumps({"real_replay": real["quality"]["totals"]}), flush=True)
    synthetic = synthetic_load(directory, args.synthetic_size)
    report = {
        "database_directory": str(directory),
        "elapsed_seconds": time.monotonic() - start,
        "real": real,
        "synthetic": synthetic,
    }
    _atomic_json(args.output, report)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "elapsed_seconds": report["elapsed_seconds"],
                "synthetic": synthetic["quality"]["totals"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
