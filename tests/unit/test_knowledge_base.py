from __future__ import annotations

import json
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.export_knowledge_base import artifacts
from scripts.export_knowledge_contract import example_bundle
from src.models.knowledge_base import KB_MODELS, KnowledgeRevision
from src.models.knowledge_contract import CodeEvidence, FindingEvidenceLink, stable_hash
from src.repositories.knowledge_store import SQLiteKnowledgeStore
from src.services.knowledge_builder import (
    REQUIRED,
    build_page,
    claim,
    extract_claims,
    review_revision,
    save_revision,
)
from src.services.knowledge_evidence import export_knowledge
from src.services.knowledge_processing import (
    KnowledgeProcessingService,
    ResolutionResult,
    legacy_snapshot,
)
from tests.unit.test_knowledge_operations import NOW


@pytest.fixture
def prepared(tmp_path):
    body = "\n\n".join(
        f"## {category.replace('_',' ').title()}\nExplicit test statement for {category}."
        for category in sorted(REQUIRED)
    )
    snap = legacy_snapshot(
        {
            "id": "test",
            "title": "Synthetic unsafe cast",
            "content": body,
            "source_link": "https://github.com/example/findings/issues/1",
        },
        source="code4rena",
        captured_at=NOW,
    )
    store = SQLiteKnowledgeStore(tmp_path / "kb.sqlite3")
    svc = KnowledgeProcessingService(store)
    state = svc.enqueue(snap, pipeline_version="test-v1", config={})
    code = CodeEvidence.model_validate(example_bundle()["code_evidence"][0])
    lease = svc.claim(state.processing_key, worker="test")
    link = FindingEvidenceLink(
        link_id="lnk_" + stable_hash(["link-v1", state.processing_key, "body:link:0"]),
        snapshot_id=snap.snapshot_id,
        processing_key=state.processing_key,
        candidate_locator="body:link:0",
        evidence_id=code.evidence_id,
        resolution_status="resolved",
        created_at=NOW,
    )
    svc.complete(lease, ResolutionResult(1, [code], [link]))
    claims, _ = extract_claims(snap.model_dump(mode="json"))
    # Manual fixtures explicitly cover all categories, independent of heading heuristics.
    claims = []
    lines = body.splitlines()
    for category in sorted(REQUIRED):
        quote = f"Explicit test statement for {category}."
        line = lines.index(quote) + 1
        claims.append(
            claim(
                category,
                quote,
                [
                    {
                        "snapshot_id": snap.snapshot_id,
                        "start_line": line,
                        "end_line": line,
                        "quote": quote,
                    }
                ],
            )
        )
    kwargs = {
        "snapshot_id": snap.snapshot_id,
        "processing_key": state.processing_key,
        "title": snap.title,
        "claims": claims,
        "missing_information": [],
        "extraction_version": "manual-test-v1",
        "evidence_link_ids": [link.link_id],
    }
    return store, snap, state, link, kwargs


def test_candidate_build_idempotence_and_grounded_export(prepared):
    store, snap, _state, link, _ = prepared
    before = store.read("code_evidence", link.evidence_id)
    result = build_page(store, pipeline_version="test-v1", config_hash=stable_hash({}))
    assert result["results"][0]["action"] == "created"
    assert (
        build_page(store, pipeline_version="test-v1", config_hash=stable_hash({}))[
            "results"
        ][0]["action"]
        == "skipped"
    )
    assert export_knowledge(store)["records"] == []
    exported = export_knowledge(store, include_candidates=True, link_id=link.link_id)[
        "records"
    ]
    assert len(exported) == 1
    assert exported[0]["finding_evidence"][0]["evidence_id"] == link.evidence_id
    assert exported[0]["review_status"] == "needs_review"
    assert store.read("code_evidence", link.evidence_id) == before
    for values in exported[0]["knowledge"].values():
        for c in values:
            for cite in c["citations"]:
                assert (
                    "\n".join(
                        snap.content.splitlines()[
                            cite["start_line"] - 1 : cite["end_line"]
                        ]
                    )
                    == cite["quote"]
                )


@pytest.mark.parametrize(
    "change",
    [
        {"quote": "invented"},
        {"start_line": 10000, "end_line": 10000},
        {"snapshot_id": "other"},
        {"link_id": "unrelated"},
    ],
)
def test_invalid_citations_never_persist(prepared, change):
    store, _, _, _, kwargs = prepared
    original = kwargs["claims"][0]
    cite = original.citations[0].model_dump(mode="json") | change
    bad = claim(original.category, original.text, [cite])
    with pytest.raises(ValueError):
        save_revision(store, **(kwargs | {"claims": [bad]}))
    assert store.scan("knowledge_revisions") == []


def test_review_gates_history_and_stale_sequence(prepared):
    store, _, _, _, kwargs = prepared
    rev, _ = save_revision(
        store, **(kwargs | {"missing_information": ["not_verified"]})
    )
    with pytest.raises(ValidationError):
        review_revision(
            store,
            rev.revision_id,
            status="approved",
            reviewer="reviewer",
            note="Checked",
            expected_sequence=0,
        )
    complete, _ = save_revision(store, **kwargs, expected_revision=rev.revision_id)
    approved = review_revision(
        store,
        complete.revision_id,
        status="approved",
        reviewer="test-reviewer",
        note="Synthetic fixture reviewed",
        expected_sequence=0,
    )
    assert approved.review_status == "approved"
    assert len(export_knowledge(store)["records"]) == 1
    with pytest.raises(ValueError, match="stale review"):
        review_revision(
            store,
            complete.revision_id,
            status="rejected",
            reviewer="test",
            note="stale",
            expected_sequence=0,
        )
    review_revision(
        store,
        complete.revision_id,
        status="rejected",
        reviewer="test",
        note="Revoke fixture",
        expected_sequence=1,
    )
    assert len(store.scan("knowledge_review_events")) == 2
    assert export_knowledge(store, include_candidates=True)["records"] == []
    assert (
        store.read("knowledge_revisions", rev.revision_id)["review_status"]
        == "needs_review"
    )


def test_new_revision_hides_old_approved_and_rejects_stale_edit(prepared):
    store, _, _, _, kwargs = prepared
    rev, _ = save_revision(store, **kwargs)
    review_revision(
        store,
        rev.revision_id,
        status="approved",
        reviewer="test",
        note="Fixture",
        expected_sequence=0,
    )
    new, _ = save_revision(
        store,
        **(kwargs | {"title": "Corrected title"}),
        expected_revision=rev.revision_id,
    )
    assert new.version == 2 and new.review_status == "needs_review"
    assert export_knowledge(store)["records"] == []
    assert (
        export_knowledge(store, include_candidates=True)["records"][0]["revision_id"]
        == new.revision_id
    )
    with pytest.raises(ValueError, match="head changed"):
        save_revision(
            store,
            **(kwargs | {"title": "Another change"}),
            expected_revision=rev.revision_id,
        )
    # A repeated old extraction is a no-op; it cannot move the head backwards.
    save_revision(store, **kwargs)
    assert (
        store.read("knowledge_heads", rev.knowledge_id)["latest_revision_id"]
        == new.revision_id
    )


def test_binding_changes_block_export_until_rebuild(prepared):
    store, _, _, link, kwargs = prepared
    rev, _ = save_revision(store, **kwargs)
    alternate = example_bundle()["code_evidence"][1]
    with store.transaction() as tx:
        tx.put("code_evidence", alternate)
        tx.put(
            "finding_evidence_links",
            link.model_dump(mode="json") | {"evidence_id": alternate["evidence_id"]},
        )
    with pytest.raises(ValueError, match="binding changed"):
        export_knowledge(store, include_candidates=True)
    new, _ = save_revision(store, **kwargs)
    assert new.version == rev.version + 1
    assert (
        export_knowledge(store, include_candidates=True)["records"][0][
            "finding_evidence"
        ][0]["evidence_id"]
        == alternate["evidence_id"]
    )


def test_content_hash_and_atomic_build(prepared):
    store, _, _, _, kwargs = prepared
    original = store.transaction

    @contextmanager
    def fail_head():
        with original() as tx:
            put = tx.put

            def put_checked(table, row):
                if table == "knowledge_heads":
                    raise OSError("interrupted commit")
                put(table, row)

            tx.put = put_checked
            yield tx

    store.transaction = fail_head
    with pytest.raises(OSError):
        save_revision(store, **kwargs)
    assert store.scan("knowledge_revisions") == []
    store.transaction = original
    rev, _ = save_revision(store, **kwargs)
    with pytest.raises(ValidationError, match="content hash"):
        KnowledgeRevision.model_validate(rev.model_dump() | {"title": "mutated"})


def test_schema_sql_and_real_cli(prepared, tmp_path):
    store, _, _, _, kwargs = prepared
    root = Path(__file__).resolve().parents[2]
    rev, _ = save_revision(store, **kwargs)
    output = tmp_path / "export.json"
    command = [
        sys.executable,
        str(root / "scripts/knowledge_base.py"),
        "--db",
        str(store.path),
    ]
    subprocess.run(
        command + ["export", "--include-candidates", "--output", str(output)],
        check=True,
        capture_output=True,
    )
    assert len(json.loads(output.read_text(encoding="utf-8"))["records"]) == 1
    subprocess.run(
        command
        + [
            "review",
            rev.revision_id,
            "--status",
            "approved",
            "--reviewer",
            "fixture",
            "--note",
            "Test only",
            "--expected-sequence",
            "0",
        ],
        check=True,
        capture_output=True,
    )
    assert (
        store.read("knowledge_revisions", rev.revision_id)["review_status"]
        == "approved"
    )
    for path, text in artifacts().items():
        assert path.read_text(encoding="utf-8") == text
    assert not any("embedding" in key or "chunk" in key for key in KB_MODELS)


def test_bigquery_serializes_claims_as_json(prepared):
    from tests.unit.test_bigquery_knowledge_store import store_with_client

    store, _, _, _, kwargs = prepared
    rev, _ = save_revision(store, **kwargs)
    bq, client = store_with_client()
    client.query.return_value.result.side_effect = [[{"revision": 3}], []]
    with bq.transaction() as tx:
        tx.put("knowledge_revisions", rev.model_dump(mode="json"))
    sql = client.query.call_args.args[0]
    assert "JSON_QUERY(doc, '$.claims')" in sql
    assert "JSON_QUERY(doc, '$.evidence_bindings')" in sql
    assert "JSON_VALUE_ARRAY(doc, '$.evidence_link_ids')" in sql
    assert "Knowledge revision conflict" in sql
