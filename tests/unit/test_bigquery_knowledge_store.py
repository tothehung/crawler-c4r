from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from scripts.export_knowledge_contract import example_bundle
from src.models.knowledge_contract import ProcessingState
from src.repositories.bigquery_knowledge_store import BigQueryKnowledgeStore


def store_with_client():
    client = Mock()
    store = BigQueryKnowledgeStore(
        project_id="test-project", dataset="test_dataset", location="US", client=client
    )
    return store, client


def test_phase6_memberships_use_fenced_typed_writes_and_bounded_scan():
    from src.models.knowledge_contract import SourceFindingSnapshot
    from src.services.finding_dedup import memberships

    store, client = store_with_client()
    row = memberships(
        SourceFindingSnapshot.model_validate(
            example_bundle()["source_finding_snapshots"][0]
        )
    )[0].model_dump(mode="json")
    client.query.return_value.result.side_effect = [[{"revision": 9}], []]
    with store.transaction() as tx:
        tx.put("finding_dedup_memberships", row)
    sql = client.query.call_args.args[0]
    assert "Knowledge revision conflict" in sql
    assert "finding_dedup_memberships` t USING" in sql
    assert "JSON_VALUE(doc, '$.group_id')" in sql
    client.query.return_value.result.side_effect = None
    client.query.return_value.result.return_value = [{"payload": json.dumps(row)}]
    assert store.scan("finding_dedup_memberships", after="cursor", limit=3) == [row]
    sql = client.query.call_args.args[0]
    assert "LIMIT @limit" in sql and "`membership_id`>@after" in sql
    with pytest.raises(ValueError):
        store.scan("finding_dedup_memberships` DROP", limit=3)


def test_writes_use_one_fenced_transaction_and_typed_parameters():
    store, client = store_with_client()
    client.query.return_value.result.side_effect = [[{"revision": 7}], []]
    bundle = example_bundle()
    with store.transaction() as tx:
        for table in [
            "source_finding_snapshots",
            "code_evidence",
            "finding_evidence_links",
            "evidence_processing_state",
        ]:
            tx.put(table, bundle[table][0])
    sql = client.query.call_args.args[0]
    config = client.query.call_args.kwargs["job_config"]
    params = {p.name: p.value for p in config.query_parameters}
    assert params["revision"] == 7
    assert sql.startswith("BEGIN TRANSACTION;")
    assert sql.endswith("COMMIT TRANSACTION;")
    assert sql.index(
        "UPDATE `test-project.test_dataset.knowledge_processing_guard`"
    ) < sql.index("MERGE")
    assert "ASSERT @@row_count = 1" in sql
    assert sql.index("code_evidence` t USING") < sql.index(
        "evidence_processing_state` t USING"
    )
    assert "JSON_QUERY(doc, '$.raw_payload')" in sql
    assert "JSON_VALUE_ARRAY(doc, '$.transformations')" in sql
    assert "CAST(JSON_VALUE(doc, '$.created_at') AS TIMESTAMP)" in sql
    assert "Synthetic" not in sql  # Data is never interpolated into SQL.
    assert (
        json.loads(params["row_0"])["snapshot_id"]
        == bundle["source_finding_snapshots"][0]["snapshot_id"]
    )


def test_lease_is_checked_again_on_server_before_output_writes():
    store, client = store_with_client()
    client.query.return_value.result.side_effect = [[{"revision": 1}], []]
    row = example_bundle()["evidence_processing_state"][0]
    lease = ProcessingState.model_validate(
        row
        | {
            "status": "running",
            "completion_reason": None,
            "lease_owner": "worker:token",
            "lease_expires_at": "2026-09-30T00:00:00Z",
        }
    )
    with store.transaction() as tx:
        tx.require_lease(lease)
        tx.put("evidence_processing_state", row)
    sql = client.query.call_args.args[0]
    assert "lease_expires_at>CURRENT_TIMESTAMP()" in sql
    assert "lease_owner=@lease_owner" in sql
    assert sql.index("AS 'Lease lost'") < sql.index("MERGE")


def test_exception_before_commit_sends_no_mutating_query():
    store, client = store_with_client()
    client.query.return_value.result.return_value = [{"revision": 1}]
    with pytest.raises(RuntimeError), store.transaction() as tx:
        tx.put("code_evidence", example_bundle()["code_evidence"][0])
        raise RuntimeError("crash")
    assert client.query.call_count == 1
    assert client.query.call_args.args[0].startswith("SELECT")


def test_revision_conflict_is_propagated_and_not_retried_blindly():
    store, client = store_with_client()
    client.query.return_value.result.side_effect = [
        [{"revision": 1}],
        RuntimeError("revision conflict"),
    ]
    with pytest.raises(
        RuntimeError, match="revision conflict"
    ), store.transaction() as tx:
        tx.put("code_evidence", example_bundle()["code_evidence"][0])
    assert client.query.call_count == 2


def test_duplicate_guard_and_duplicate_record_are_rejected():
    store, client = store_with_client()
    client.query.return_value.result.return_value = [{"revision": 1}, {"revision": 1}]
    with pytest.raises(RuntimeError, match="exactly one"), store.transaction():
        pass
    client.query.return_value.result.return_value = [
        {"payload": "{}"},
        {"payload": "{}"},
    ]
    with pytest.raises(RuntimeError, match="Duplicate identity"):
        store.read("code_evidence", "key")


def test_read_roundtrips_contract_and_rejects_sql_identifiers():
    store, client = store_with_client()
    row = example_bundle()["source_finding_snapshots"][0]
    client.query.return_value.result.return_value = [{"payload": json.dumps(row)}]
    assert store.read("source_finding_snapshots", row["snapshot_id"]) == row
    with pytest.raises(ValueError):
        BigQueryKnowledgeStore(
            project_id="project`", dataset="dataset", location="US", client=client
        )
