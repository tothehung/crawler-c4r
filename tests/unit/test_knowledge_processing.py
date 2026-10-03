from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest

from scripts.export_knowledge_contract import example_bundle
from src.models.knowledge_contract import (
    CodeEvidence,
    FindingEvidenceLink,
    SourceFindingSnapshot,
)
from src.repositories.knowledge_store import SQLiteKnowledgeStore
from src.services.knowledge_processing import (
    EVIDENCE,
    LINKS,
    SNAPSHOTS,
    STATES,
    KnowledgeProcessingService,
    LeaseLostError,
    ResolutionResult,
    RetryableResolutionError,
    legacy_snapshot,
)


@pytest.fixture
def setup(tmp_path):
    bundle = example_bundle()
    store = SQLiteKnowledgeStore(tmp_path / "queue.db")
    time = [datetime(2026, 9, 29, tzinfo=UTC)]
    service = KnowledgeProcessingService(store, clock=lambda: time[0], jitter=lambda: 0)
    states = [
        service.enqueue(
            SourceFindingSnapshot.model_validate(row),
            pipeline_version="evidence-v1",
            config={"context_lines": 10, "normalization_version": "identity-v1"},
        )
        for row in bundle[SNAPSHOTS]
    ]
    return service, store, time, bundle, states


def result_for(bundle, state):
    links = [
        FindingEvidenceLink.model_validate(row)
        for row in bundle[LINKS]
        if row["processing_key"] == state.processing_key
    ]
    used = {link.evidence_id for link in links}
    evidence = [
        CodeEvidence.model_validate(row)
        for row in bundle[EVIDENCE]
        if row["evidence_id"] in used
    ]
    return ResolutionResult(len(links), evidence, links)


def test_intake_preserves_raw_and_rerun_is_idempotent(setup):
    service, store, _, bundle, states = setup
    snapshot = SourceFindingSnapshot.model_validate(bundle[SNAPSHOTS][0])
    again = service.enqueue(
        snapshot,
        pipeline_version="evidence-v1",
        config={"normalization_version": "identity-v1", "context_lines": 10},
    )
    assert again == states[0]
    assert (
        store.read(SNAPSHOTS, snapshot.snapshot_id)["raw_payload"]
        == snapshot.raw_payload
    )
    changed = service.enqueue(snapshot, pipeline_version="evidence-v2", config={})
    assert changed.processing_key != again.processing_key
    assert len(store.states()) == 4


def test_changed_legacy_content_creates_new_snapshot(setup):
    service, _, time, _, _ = setup
    raw = {
        "id": "1",
        "source_link": "https://example.invalid",
        "title": "Report",
        "content": "a",
        "unknown_field": [1],
    }
    first = legacy_snapshot(raw, source="solodit", captured_at=time[0])
    second = legacy_snapshot(
        raw | {"content": "b"}, source="solodit", captured_at=time[0]
    )
    assert first.raw_payload == raw
    assert first.snapshot_id != second.snapshot_id
    a = service.enqueue(first, pipeline_version="v1", config={})
    b = service.enqueue(second, pipeline_version="v1", config={})
    assert a.processing_key != b.processing_key


def test_concurrent_claim_has_exactly_one_winner(setup):
    service, _, _, _, states = setup
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(
            pool.map(
                lambda worker: service.claim(states[0].processing_key, worker=worker),
                ["a", "b"],
            )
        )
    assert sum(claim is not None for claim in claims) == 1


def test_expired_worker_cannot_write_even_after_same_worker_reclaims(setup):
    service, store, time, bundle, states = setup
    old = service.claim(states[0].processing_key, worker="a", lease_seconds=10)
    time[0] += timedelta(seconds=11)
    new = service.claim(old.processing_key, worker="a")
    assert new.attempts == 2
    with pytest.raises(LeaseLostError):
        service.complete(old, result_for(bundle, old))
    assert store.read(EVIDENCE, bundle[EVIDENCE][0]["evidence_id"]) is None
    assert service.complete(new, result_for(bundle, new)).status == "succeeded"


def test_success_and_no_candidates_skip_on_rerun(setup):
    service, store, _, bundle, states = setup
    keys = [states[i].processing_key for i in [0, 2]]
    done = service.run_batch(
        keys, lambda snapshot, lease: result_for(bundle, lease), worker="a"
    )
    assert [state.completion_reason for state in done] == [
        "all_resolved",
        "no_candidates",
    ]
    assert (
        service.run_batch(keys, lambda *_: pytest.fail("must skip"), worker="a") == []
    )
    reopened = SQLiteKnowledgeStore(store.path)
    assert reopened.read(STATES, keys[0])["status"] == "succeeded"


def test_partial_retry_backoff_retry_after_and_budget(setup):
    service, _, time, bundle, states = setup
    key = states[1].processing_key
    for attempt in range(1, 4):
        lease = service.claim(key, worker="a")
        result = result_for(bundle, lease)
        state = service.complete(
            lease,
            ResolutionResult(
                result.candidate_count, result.evidence, result.links, retry_after=120
            ),
        )
        assert state.status == "partial"
        assert state.attempts == attempt
        assert service.claim(key, worker="b") is None
        if attempt < 3:
            assert state.next_retry_at >= time[0] + timedelta(seconds=120)
            time[0] = state.next_retry_at
        else:
            assert state.next_retry_at is None
            time[0] += timedelta(days=1)
            assert service.claim(key, worker="b") is None


def test_partial_can_be_completed_without_duplicate_links(setup):
    service, store, time, bundle, states = setup
    key = states[1].processing_key
    lease = service.claim(key, worker="a")
    result = result_for(bundle, lease)
    partial = service.complete(lease, result)
    time[0] = partial.next_retry_at
    lease = service.claim(key, worker="b")
    fixed = FindingEvidenceLink.model_validate(
        result.links[1].model_dump()
        | {
            "resolution_status": "resolved",
            "retryable": False,
            "error_code": None,
            "error_message": None,
            "evidence_id": result.evidence[0].evidence_id,
        }
    )
    done = service.complete(
        lease, ResolutionResult(2, result.evidence, [result.links[0], fixed])
    )
    assert done.resolved_count == 2 and done.status == "succeeded"
    assert store.read(LINKS, fixed.link_id)["resolution_status"] == "resolved"


def test_transaction_failure_rolls_back_outputs_and_recovers(setup):
    service, store, time, bundle, states = setup
    lease = service.claim(states[0].processing_key, worker="a", lease_seconds=10)
    original = store.transaction

    @contextmanager
    def broken_transaction():
        with original() as tx:
            put = tx.put

            def broken_put(table, row):
                if table == STATES:
                    raise OSError("simulated disk failure after output writes")
                put(table, row)

            tx.put = broken_put
            yield tx

    store.transaction = broken_transaction
    with pytest.raises(OSError):
        service.complete(lease, result_for(bundle, lease))
    store.transaction = original
    assert store.read(EVIDENCE, bundle[EVIDENCE][0]["evidence_id"]) is None
    assert store.read(LINKS, bundle[LINKS][0]["link_id"]) is None
    assert store.read(STATES, lease.processing_key)["status"] == "running"
    time[0] += timedelta(seconds=11)
    new = service.claim(lease.processing_key, worker="b")
    assert service.complete(new, result_for(bundle, new)).status == "succeeded"


def test_reject_incomplete_or_wrong_run_inventory(setup):
    service, _, _, bundle, states = setup
    lease = service.claim(states[0].processing_key, worker="a")
    result = result_for(bundle, lease)
    with pytest.raises(ValueError, match="Every candidate"):
        service.complete(lease, ResolutionResult(3, result.evidence, result.links))
    with pytest.raises(ValueError, match="different snapshot/run"):
        service.complete(lease, result_for(bundle, states[1]))


def test_heartbeat_and_exhausted_crashed_attempt(setup):
    service, store, time, _, states = setup
    key = states[2].processing_key
    for _ in range(3):
        lease = service.claim(key, worker="a", lease_seconds=5)
        extended = service.heartbeat(lease, lease_seconds=10)
        assert extended.lease_expires_at == time[0] + timedelta(seconds=10)
        time[0] += timedelta(seconds=11)
    assert service.claim(key, worker="b") is None
    assert store.read(STATES, key)["error_code"] == "lease_expired_attempts_exhausted"


@pytest.mark.parametrize("transient", [True, False])
def test_resolver_failure_is_recorded(setup, transient):
    service, _, _, _, states = setup

    def resolver(*_):
        if transient:
            raise RetryableResolutionError("rate limited", retry_after=120)
        raise ValueError("bad input")

    done = service.run_batch([states[0].processing_key], resolver, worker="a")[0]
    assert done.status == "failed"
    assert done.retryable is transient
