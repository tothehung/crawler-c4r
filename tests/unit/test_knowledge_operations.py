from __future__ import annotations

import json
import subprocess
import sys
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.export_knowledge_contract import example_bundle
from scripts.export_knowledge_operations import artifacts
from src.models.knowledge_contract import (
    CodeEvidence,
    FindingEvidenceLink,
    stable_hash,
)
from src.models.knowledge_operations import OPERATIONS_MODELS
from src.repositories.knowledge_store import SQLiteKnowledgeStore
from src.services.finding_dedup import deduplicate_page, finding_url, memberships
from src.services.knowledge_batch import run_sweep
from src.services.knowledge_processing import (
    KnowledgeProcessingService,
    ResolutionResult,
    legacy_snapshot,
)
from src.services.knowledge_quality import iter_records, quality_report

NOW = datetime(2026, 9, 30, tzinfo=UTC)


def snapshot(index, *, source="solodit", url=None, title=None, content=None):
    return legacy_snapshot(
        {
            "id": str(index),
            "title": title or f"Distinct finding number {index}",
            "content": content or f"Report {index} has unique details.",
            "source_link": url
            or f"https://github.com/audit/reports-findings/issues/{index+1}",
        },
        source=source,
        captured_at=NOW,
    )


def shared_resolver():
    evidence = CodeEvidence.model_validate(example_bundle()["code_evidence"][0])

    def resolve(snap, lease):
        locator = "body:link:0"
        link = FindingEvidenceLink(
            link_id="lnk_" + stable_hash(["link-v1", lease.processing_key, locator]),
            snapshot_id=snap.snapshot_id,
            processing_key=lease.processing_key,
            candidate_locator=locator,
            evidence_id=evidence.evidence_id,
            resolution_status="resolved",
            created_at=NOW,
        )
        return ResolutionResult(1, [evidence], [link])

    return evidence, resolve


@pytest.mark.parametrize(
    "url,expected",
    [
        (
            "http://GITHUB.com/Audit/Findings/issues/12/?utm_source=x#issuecomment-1",
            "https://github.com/audit/findings/issues/12",
        ),
        (
            "https://code4rena.com/reports/2023-04-caviar#h-01-royalty-receiver",
            "https://code4rena.com/reports/2023-04-caviar#h-01-royalty-receiver",
        ),
        ("https://code4rena.com/reports/2023-04-caviar", None),
        ("https://github.com/audit/reports/blob/main/review.md", None),
        ("https://github.com/audit/repo/blob/main/Vault.sol#L10", None),
        ("https://github.com.evil.test/a/b/issues/1", None),
        ("https://github.com/a/b/issues/1?finding=2", None),
        ("https://user:pass@github.com/a/b/issues/1", None),
    ],
)
def test_finding_url_is_specific_not_report_or_code(url, expected):
    assert finding_url(url) == expected


def test_groups_link_sources_but_never_promote_content_similarity(tmp_path):
    store = SQLiteKnowledgeStore(tmp_path / "db")
    service = KnowledgeProcessingService(store)
    body = (
        "This is matching report content with sufficient detail for a review candidate. "
        * 2
    )
    snaps = [
        snapshot(1, content=body),
        snapshot(
            2,
            source="code4rena",
            url="http://github.com/AUDIT/reports-findings/issues/2/?utm_campaign=test",
            content=body,
        ),
        snapshot(3, content=body),
    ]
    original = [s.model_dump(mode="json") for s in snaps]
    _, resolver = shared_resolver()
    for snap in snaps:
        service.enqueue(snap, pipeline_version="v1", config={})
    run_sweep(
        store,
        resolver,
        name="test",
        pipeline_version="v1",
        config={},
        page_size=2,
        max_pages=3,
    )
    assert deduplicate_page(store)["indexed"] == 3
    assert deduplicate_page(store)["skipped"] == 3
    report = quality_report(store, pipeline_version="v1", config_hash=stable_hash({}))
    assert report["finding_dedup"]["cross_source_groups"] == 1
    assert report["finding_dedup"]["source_findings_linked"] == 1
    assert len(report["finding_dedup"]["review_candidates"]) == 1
    assert report["totals"]["unique_evidence"] == 1
    assert report["totals"]["evidence_shared_between_findings"] == 1
    for snap, row in zip(snaps, original, strict=True):
        assert store.read("source_finding_snapshots", snap.snapshot_id) == row
    before = len(list(iter_records(store, "finding_dedup_memberships")))
    assert deduplicate_page(store, version="finding-dedup-v2")["indexed"] == 3
    assert len(list(iter_records(store, "finding_dedup_memberships"))) == before * 2


def test_shared_whole_report_and_body_references_do_not_confirm_duplicate():
    a = snapshot(1, url="https://github.com/audit/reports/blob/main/review.md")
    b = snapshot(
        2,
        url=a.source_url,
        content="See https://github.com/audit/reports-findings/issues/2 for related issue",
    )
    ga = {m.group_id for m in memberships(a) if m.decision == "confirmed"}
    gb = {m.group_id for m in memberships(b) if m.decision == "confirmed"}
    assert ga.isdisjoint(gb)


def test_interruption_resume_and_upgrade_reuse_evidence(tmp_path):
    store = SQLiteKnowledgeStore(tmp_path / "db")
    clock = [NOW]
    service = KnowledgeProcessingService(store, clock=lambda: clock[0])
    snaps = [snapshot(i) for i in range(12)]
    for snap in snaps:
        service.enqueue(snap, pipeline_version="v1", config={})
    evidence, resolver = shared_resolver()
    calls = [0]

    def interrupted(snap, lease):
        calls[0] += 1
        if calls[0] == 3:
            raise KeyboardInterrupt("simulated worker termination")
        return resolver(snap, lease)

    kwargs = {
        "name": "test",
        "pipeline_version": "v1",
        "config": {},
        "page_size": 5,
        "max_pages": 10,
        "service": service,
        "lease_seconds": 10,
    }
    with pytest.raises(KeyboardInterrupt):
        run_sweep(store, interrupted, **kwargs)
    assert len(store.evidence()) == 1
    assert store.scan("knowledge_batch_checkpoints") == []
    clock[0] += timedelta(seconds=11)
    report = run_sweep(store, resolver, **kwargs)
    assert report["attempted"] == 10
    assert report["checkpoint"]["completed"]
    assert run_sweep(store, resolver, **kwargs)["attempted"] == 0
    assert len(store.evidence()) == 1
    assert len(store.scan("finding_evidence_links")) == 12
    metrics = quality_report(store, pipeline_version="v1", config_hash=stable_hash({}))
    assert metrics["operations"]["retry_attempts"] == 1
    assert metrics["operations"]["untimed_attempts"] == 1
    assert metrics["operations"]["timed_attempts"] == 12
    # Validation annotations survive subsequent resolver versions reusing evidence.
    row = store.read("code_evidence", evidence.evidence_id)
    with store.transaction() as tx:
        tx.put(
            "code_evidence",
            row | {"syntax_status": "parsed", "parser_version": "test-parser"},
        )
    for snap in snaps:
        service.enqueue(snap, pipeline_version="v2", config={})
    upgraded = run_sweep(store, resolver, **(kwargs | {"pipeline_version": "v2"}))
    assert upgraded["attempted"] == 12
    assert len(store.evidence()) == 1
    assert (
        store.read("code_evidence", evidence.evidence_id)["syntax_status"] == "parsed"
    )
    assert len(store.scan("finding_evidence_links")) == 24
    scoped = quality_report(store, pipeline_version="v2", config_hash=stable_hash({}))
    assert scoped["totals"]["links"] == 12
    assert scoped["operations"]["retry_attempts"] == 0
    assert scoped["by_source"]["solodit"]["parse_success_checked"]["rate"] == 1


def test_dedup_completion_is_atomic(tmp_path):
    store = SQLiteKnowledgeStore(tmp_path / "db")
    snap = snapshot(1)
    KnowledgeProcessingService(store).enqueue(snap, pipeline_version="v1", config={})
    original = store.transaction

    @contextmanager
    def fail_after_members():
        with original() as tx:
            put = tx.put

            def guarded(table, row):
                if table == "finding_dedup_state":
                    raise OSError("simulated storage failure")
                put(table, row)

            tx.put = guarded
            yield tx

    store.transaction = fail_after_members
    with pytest.raises(OSError):
        deduplicate_page(store)
    assert store.scan("finding_dedup_memberships") == []
    assert store.scan("finding_dedup_state") == []
    store.transaction = original
    assert deduplicate_page(store)["indexed"] == 1


def test_checkpoint_failure_does_not_lose_or_duplicate_outputs(tmp_path):
    store = SQLiteKnowledgeStore(tmp_path / "db")
    KnowledgeProcessingService(store).enqueue(
        snapshot(1), pipeline_version="v1", config={}
    )
    _, resolver = shared_resolver()
    original = store.transaction

    @contextmanager
    def fail_checkpoint():
        with original() as tx:
            put = tx.put

            def guarded(table, row):
                if table == "knowledge_batch_checkpoints":
                    raise OSError("checkpoint write interrupted")
                put(table, row)

            tx.put = guarded
            yield tx

    store.transaction = fail_checkpoint
    with pytest.raises(OSError):
        run_sweep(store, resolver, name="test", pipeline_version="v1", config={})
    assert len(store.scan("finding_evidence_links")) == 1
    store.transaction = original
    result = run_sweep(store, resolver, name="test", pipeline_version="v1", config={})
    assert result["attempted"] == 0
    assert result["checkpoint"]["completed"]


def test_report_does_not_hide_empty_or_truncated_denominators(tmp_path):
    store = SQLiteKnowledgeStore(tmp_path / "db")
    service = KnowledgeProcessingService(store)
    for i in range(2):
        service.enqueue(snapshot(i), pipeline_version="v1", config={})
    report = quality_report(store, pipeline_version="v1", config_hash=stable_hash({}))
    assert report["by_source"]["solodit"]["findings_with_evidence"]["rate"] == 0
    assert report["by_source"]["solodit"]["parse_success_checked"]["rate"] is None
    with pytest.raises(ValueError, match="limit exceeded"):
        quality_report(
            store, pipeline_version="v1", config_hash=stable_hash({}), max_rows=1
        )


def test_operations_artifacts_are_current_and_additive():
    for path, text in artifacts().items():
        assert path.read_text(encoding="utf-8") == text
    sql = next(v for k, v in artifacts().items() if k.suffix == ".sql")
    assert sql.count("CREATE TABLE IF NOT EXISTS") == len(OPERATIONS_MODELS)
    assert "DROP TABLE" not in sql and "ALTER TABLE" not in sql


def test_phase6_cli_checkpoint_dedup_and_report(tmp_path):
    root = Path(__file__).resolve().parents[2]
    config_path = root / "config/knowledge_phase4_recorded.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    store = SQLiteKnowledgeStore(tmp_path / "db.sqlite3")
    service = KnowledgeProcessingService(store)
    for i in range(3):
        service.enqueue(
            snapshot(i, content="```solidity\nuint x;\n```"),
            pipeline_version="evidence-resolver-v1",
            config=config,
        )

    def cli(script, *arguments):
        completed = subprocess.run(
            [
                sys.executable,
                str(root / "scripts" / script),
                "--db",
                str(store.path),
                *arguments,
            ],
            cwd=root,
            check=True,
            text=True,
            capture_output=True,
        )
        return json.loads(completed.stdout)

    run = (
        "run",
        "--config",
        str(config_path),
        "--replay-http",
        str(root / "tests/fixtures/evidence_benchmark_v1/http"),
        "--checkpoint",
        "integration",
        "--limit",
        "2",
        "--max-pages",
        "5",
    )
    assert cli("process_knowledge.py", *run)["attempted"] == 3
    assert cli("process_knowledge.py", *run)["attempted"] == 0
    assert (
        cli("knowledge_operations.py", "dedup", "--limit", "2", "--max-pages", "5")[
            "indexed"
        ]
        == 3
    )
    output = tmp_path / "quality.json"
    cli(
        "knowledge_operations.py",
        "report",
        "--pipeline-version",
        "evidence-resolver-v1",
        "--config",
        str(config_path),
        "--output",
        str(output),
    )
    quality = json.loads(output.read_text(encoding="utf-8"))
    assert quality["totals"]["source_findings"] == 3
    assert quality["operations"]["timed_attempts"] == 3
    assert quality["by_source"]["solodit"]["parse_coverage"]["rate"] == 0
