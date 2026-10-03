from __future__ import annotations

import copy
from datetime import datetime

import pytest
from pydantic import ValidationError

from scripts.export_knowledge_contract import (
    artifacts,
    bq_type,
    example_bundle,
    render_migration,
)
from src.models.knowledge_contract import (
    TABLE_MODELS,
    CodeEvidence,
    FindingEvidenceLink,
    KnowledgeCandidate,
    LineRange,
    ProcessingState,
    SourceFindingSnapshot,
    processing_key,
    source_key,
    stable_hash,
)


@pytest.fixture
def bundle():
    return example_bundle()


def test_generated_artifacts_are_current():
    for path, content in artifacts().items():
        assert path.exists(), f"Missing {path}"
        assert path.read_text(encoding="utf-8") == content, f"Stale {path}"


def test_example_relationships_and_many_to_many(bundle):
    snapshots = {r["snapshot_id"]: r for r in bundle["source_finding_snapshots"]}
    evidence = {r["evidence_id"]: r for r in bundle["code_evidence"]}
    states = {r["processing_key"]: r for r in bundle["evidence_processing_state"]}
    links = {r["link_id"]: r for r in bundle["finding_evidence_links"]}
    canonical = {r["canonical_finding_id"] for r in bundle["canonical_findings"]}
    for row in snapshots.values():
        assert row["canonical_finding_id"] in canonical
    for link in links.values():
        assert link["snapshot_id"] in snapshots
        assert states[link["processing_key"]]["snapshot_id"] == link["snapshot_id"]
        if link["evidence_id"]:
            assert link["evidence_id"] in evidence
        if link["related_link_id"]:
            assert links[link["related_link_id"]]["snapshot_id"] == link["snapshot_id"]
    first, fixed, duplicate, unavailable = list(links.values())
    assert first["snapshot_id"] != duplicate["snapshot_id"]
    assert first["evidence_id"] == duplicate["evidence_id"]
    assert (
        evidence[first["evidence_id"]]["commit_sha"]
        != evidence[fixed["evidence_id"]]["commit_sha"]
    )
    assert unavailable["evidence_id"] is None
    for state in states.values():
        run_links = [
            link
            for link in links.values()
            if link["processing_key"] == state["processing_key"]
        ]
        assert len(run_links) == state["candidate_count"]
        assert (
            sum(link["resolution_status"] == "resolved" for link in run_links)
            == state["resolved_count"]
        )
    for knowledge in bundle["knowledge_candidates"]:
        for citation in knowledge["root_cause"]["citations"]:
            assert citation["snapshot_id"] in snapshots
            assert links[citation["link_id"]]["snapshot_id"] == citation["snapshot_id"]


def test_no_code_finding_can_complete_without_fake_evidence(bundle):
    state = ProcessingState.model_validate(bundle["evidence_processing_state"][2])
    assert state.status == "succeeded"
    assert state.completion_reason == "no_candidates"
    assert not any(
        link["snapshot_id"] == state.snapshot_id
        for link in bundle["finding_evidence_links"]
    )


def test_hash_is_order_stable_but_preserves_code_semantics():
    assert stable_hash({"a": 1, "b": 2}) == stable_hash({"b": 2, "a": 1})
    assert stable_hash('require(x, "a b");') != stable_hash('require(x, "a  b");')
    assert source_key("solodit", "123") != source_key("code4rena", "123")
    assert processing_key("s", "v1", "a") != processing_key("s", "v2", "a")
    assert processing_key("s", "v1", "a") != processing_key("s", "v1", "b")


@pytest.mark.parametrize(
    "changes",
    [
        {"raw_payload_hash": "0" * 64},
        {"source": "code4rena"},
        {"snapshot_id": "invalid"},
        {"raw_payload": {"changed": True}},
        {"source_quality_score": 90},
        {"captured_at": "2026-09-28T00:00:00"},
    ],
)
def test_reject_inconsistent_source_snapshots(bundle, changes):
    row = bundle["source_finding_snapshots"][0] | changes
    with pytest.raises(ValidationError):
        SourceFindingSnapshot.model_validate(row)


@pytest.mark.parametrize("start,end", [(0, 1), (2, 1), (-1, 1), (True, 2)])
def test_invalid_ranges(start, end):
    with pytest.raises(ValidationError):
        LineRange(start_line=start, end_line=end)


@pytest.mark.parametrize(
    "changes",
    [
        {"path": "E:/project/A.sol"},
        {"path": "../A.sol"},
        {"path": "src\\A.sol"},
        {"path": "src/./A.sol"},
        {"commit_sha": "main"},
        {"commit_sha": None},
        {"syntax_status": "parsed", "parser_version": None},
        {"evidence_id": "wrong"},
        {"raw_snippet": "   "},
        {"finding_id": "must-not-own-a-finding"},
    ],
)
def test_invalid_evidence_provenance(bundle, changes):
    with pytest.raises(ValidationError):
        CodeEvidence.model_validate(bundle["code_evidence"][0] | changes)


def test_inline_evidence_and_invalid_syntax_are_retained(bundle):
    row = bundle["code_evidence"][0] | {
        "origin_kind": "inline",
        "repo": None,
        "commit_sha": None,
        "path": None,
        "origin_url": None,
        "origin_snapshot_id": bundle["source_finding_snapshots"][0]["snapshot_id"],
        "source_range": None,
        "locator": "body:block:0",
        "syntax_status": "invalid",
        "parser_version": "test-parser-v1",
        "diagnostics": ["Fragment lacks context"],
    }
    projected = CodeEvidence.model_construct(
        **(row | {"created_at": datetime.fromisoformat(row["created_at"])})
    )
    row["evidence_id"] = projected.expected_id()
    validated = CodeEvidence.model_validate(row)
    assert validated.syntax_status == "invalid"
    assert validated.repo is None


@pytest.mark.parametrize(
    "changes",
    [
        {"evidence_id": None},
        {"role_basis": None},
        {"retryable": True},
        {"evidence_confidence": 0.9},
        {"evidence_confidence": 2, "confidence_method": "v1"},
        {"resolution_status": "unavailable", "error_code": "not_found"},
    ],
)
def test_inconsistent_evidence_links(bundle, changes):
    with pytest.raises(ValidationError):
        FindingEvidenceLink.model_validate(
            bundle["finding_evidence_links"][0] | changes
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"outputs_persisted_at": None},
        {"unresolved_count": 1},
        {"attempts": 0},
        {"completion_reason": "no_candidates"},
        {"pipeline_version": "changed"},
        {"retryable": True},
        {"attempts": 4},
    ],
)
def test_success_requires_committed_complete_results(bundle, changes):
    with pytest.raises(ValidationError):
        ProcessingState.model_validate(bundle["evidence_processing_state"][0] | changes)


def test_retry_budget_and_worker_lease(bundle):
    partial = bundle["evidence_processing_state"][1]
    scheduled = partial | {"next_retry_at": "2026-09-28T01:00:00Z"}
    assert ProcessingState.model_validate(scheduled).retryable
    with pytest.raises(ValidationError):
        ProcessingState.model_validate(scheduled | {"attempts": 3})
    running = partial | {"status": "running", "retryable": False}
    with pytest.raises(ValidationError):
        ProcessingState.model_validate(running)
    assert (
        ProcessingState.model_validate(
            running
            | {
                "lease_owner": "worker-1",
                "lease_expires_at": "2026-09-28T01:00:00Z",
            }
        ).status
        == "running"
    )


def test_knowledge_requires_citations_and_explicit_review(bundle):
    draft = copy.deepcopy(bundle["knowledge_candidates"][0])
    with pytest.raises(ValidationError):
        KnowledgeCandidate.model_validate(draft | {"review_status": "approved"})
    approval = draft | {
        "review_status": "approved",
        "reviewed_by": "reviewer-1",
        "reviewed_at": "2026-09-28T01:00:00Z",
        "review_note": "Example reviewed",
    }
    with pytest.raises(ValidationError):
        KnowledgeCandidate.model_validate(approval)
    assert (
        KnowledgeCandidate.model_validate(
            approval | {"missing_information": []}
        ).review_status
        == "approved"
    )
    draft["root_cause"]["citations"] = []
    with pytest.raises(ValidationError):
        KnowledgeCandidate.model_validate(draft)


def test_migration_is_additive_and_covers_every_model_field():
    sql = render_migration()
    assert sql.count("CREATE TABLE IF NOT EXISTS") == len(TABLE_MODELS)
    assert (
        "ALTER TABLE" not in sql and "DROP TABLE" not in sql and "TRUNCATE" not in sql
    )
    assert "${DATASET}.findings`" not in sql
    for table, model in TABLE_MODELS.items():
        schema = model.model_json_schema()
        table_sql = sql.split(f"${{DATASET}}.{table}`", 1)[1].split(";", 1)[0]
        for field, prop in schema["properties"].items():
            kind, _ = bq_type(prop, schema.get("$defs", {}))
            assert f"  {field} {kind}" in table_sql
    assert "raw_payload JSON NOT NULL" in sql
    assert "source_range JSON" in sql
    assert "taxonomy_tags ARRAY<STRING>" in sql
    assert "created_at TIMESTAMP NOT NULL" in sql
