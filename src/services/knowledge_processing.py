"""Phase 3: immutable intake, fenced leases, atomic outputs and bounded retry."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from src.models.knowledge_contract import (
    CodeEvidence,
    FindingEvidenceLink,
    ProcessingState,
    SourceFindingSnapshot,
    processing_key,
    snapshot_id,
    source_key,
    stable_hash,
)
from src.models.knowledge_operations import ProcessingAttempt

SNAPSHOTS = "source_finding_snapshots"
STATES = "evidence_processing_state"
EVIDENCE = "code_evidence"
LINKS = "finding_evidence_links"


class LeaseLostError(RuntimeError):
    """The attempt no longer owns a live lease; none of its writes are accepted."""


class RetryableResolutionError(RuntimeError):
    def __init__(self, message: str, *, retry_after: float = 0):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass(frozen=True)
class ResolutionResult:
    """A complete inventory, including failed candidates (never successes only)."""

    candidate_count: int
    evidence: list[CodeEvidence]
    links: list[FindingEvidenceLink]
    retry_after: float = 0
    allow_inventory_expansion: bool = False


def legacy_snapshot(
    row: dict, *, source: str, captured_at: datetime
) -> SourceFindingSnapshot:
    """Preserve the entire input row, explicitly labelled as a legacy export."""
    native_id = str(row["id"])
    key = source_key(source, native_id)
    digest = stable_hash(row)
    url = row.get("source_link")
    if not url:
        raise ValueError(
            "Legacy intake requires source_link; use contract input otherwise"
        )
    severity = str(row.get("impact") or "UNKNOWN")
    return SourceFindingSnapshot(
        snapshot_id=snapshot_id(key, digest),
        source_key=key,
        source=source,
        source_id=native_id,
        legacy_finding_id=native_id,
        source_url=url,
        title=row["title"],
        content=row.get("content") or "",
        severity_original=severity,
        severity=(
            severity
            if severity in {"HIGH", "MEDIUM", "LOW", "CRITICAL", "GAS", "INFORMATIONAL"}
            else "UNKNOWN"
        ),
        payload_kind="legacy_normalized_json",
        raw_payload=row,
        raw_payload_hash=digest,
        captured_at=captured_at,
    )


class KnowledgeProcessingService:
    def __init__(
        self,
        store,
        *,
        clock: Callable = lambda: datetime.now(UTC),
        jitter: Callable = random.random,
    ):
        self.store = store
        self.clock = clock
        self.jitter = jitter

    def enqueue(
        self,
        snapshot: SourceFindingSnapshot,
        *,
        pipeline_version: str,
        config: dict,
        max_attempts: int = 3,
    ) -> ProcessingState:
        snapshot = SourceFindingSnapshot.model_validate(snapshot.model_dump())
        config_hash = stable_hash(config)
        state = ProcessingState(
            processing_key=processing_key(
                snapshot.snapshot_id, pipeline_version, config_hash
            ),
            snapshot_id=snapshot.snapshot_id,
            pipeline_version=pipeline_version,
            config_hash=config_hash,
            max_attempts=max_attempts,
            updated_at=self.clock(),
        )
        with self.store.transaction() as tx:
            previous = tx.get(SNAPSHOTS, snapshot.snapshot_id)
            row = snapshot.model_dump(mode="json")
            if previous:
                # Re-observation can change capture time, never the stored interpretation.
                if {k: v for k, v in previous.items() if k != "captured_at"} != {
                    k: v for k, v in row.items() if k != "captured_at"
                }:
                    raise ValueError(
                        "Snapshot identity already has different content/metadata"
                    )
            else:
                tx.put(SNAPSHOTS, row)
            existing = tx.get(STATES, state.processing_key)
            if existing:
                return ProcessingState.model_validate(existing)
            tx.put(STATES, state.model_dump(mode="json"))
        return state

    def claim(
        self, key: str, *, worker: str, lease_seconds: int = 300
    ) -> ProcessingState | None:
        if not worker or lease_seconds <= 0:
            raise ValueError("worker and positive lease_seconds required")
        with self.store.transaction() as tx:
            row = tx.get(STATES, key)
            if row is None:
                raise KeyError(key)
            state = ProcessingState.model_validate(row)
            now = self.clock()
            expired = state.status == "running" and state.lease_expires_at <= now
            eligible = (
                state.status == "pending"
                or expired
                or (
                    state.status in {"partial", "failed"}
                    and state.retryable
                    and (state.next_retry_at is None or state.next_retry_at <= now)
                )
            )
            if not eligible:
                return None
            if state.attempts >= state.max_attempts:
                if expired:
                    if hasattr(tx, "require_expired"):
                        tx.require_expired(state)
                    tx.put(
                        STATES,
                        self._changed(
                            state,
                            status="failed",
                            retryable=False,
                            next_retry_at=None,
                            lease_owner=None,
                            lease_expires_at=None,
                            error_code="lease_expired_attempts_exhausted",
                            updated_at=now,
                        ).model_dump(mode="json"),
                    )
                return None
            if hasattr(tx, "require_claim"):
                tx.require_claim(state)
            claimed = self._changed(
                state,
                status="running",
                attempts=state.attempts + 1,
                lease_owner=f"{worker}:{uuid4().hex}",
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                retryable=False,
                next_retry_at=None,
                completion_reason=None,
                error_code=None,
                error_message=None,
                updated_at=now,
            )
            tx.put(STATES, claimed.model_dump(mode="json"))
        return claimed

    @staticmethod
    def _changed(state: ProcessingState, **changes) -> ProcessingState:
        return ProcessingState.model_validate(state.model_dump() | changes)

    def _owned(self, tx, lease: ProcessingState) -> ProcessingState:
        row = tx.get(STATES, lease.processing_key)
        if row is None:
            raise LeaseLostError("Processing state missing")
        state = ProcessingState.model_validate(row)
        if (
            state.status != "running"
            or state.lease_owner != lease.lease_owner
            or state.attempts != lease.attempts
            or state.lease_expires_at <= self.clock()
        ):
            raise LeaseLostError("Lease expired or superseded")
        # BigQuery additionally checks expiry against server time at COMMIT.
        if hasattr(tx, "require_lease"):
            tx.require_lease(state)
        return state

    def heartbeat(
        self, lease: ProcessingState, *, lease_seconds: int = 300
    ) -> ProcessingState:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        with self.store.transaction() as tx:
            state = self._owned(tx, lease)
            state = self._changed(
                state,
                lease_expires_at=self.clock() + timedelta(seconds=lease_seconds),
                updated_at=self.clock(),
            )
            tx.put(STATES, state.model_dump(mode="json"))
        return state

    def _retry_at(self, state: ProcessingState, retryable: bool, retry_after: float):
        if not retryable or state.attempts >= state.max_attempts:
            return None
        seconds = max(
            retry_after,
            min(3600, 30 * 2 ** min(state.attempts - 1, 10)) * (1 + self.jitter()),
        )
        return self.clock() + timedelta(seconds=seconds)

    def complete(
        self,
        lease: ProcessingState,
        result: ResolutionResult,
        *,
        resolver_seconds: float | None = None,
    ) -> ProcessingState:
        evidence = [
            CodeEvidence.model_validate(e.model_dump()) for e in result.evidence
        ]
        links = [
            FindingEvidenceLink.model_validate(link.model_dump())
            for link in result.links
        ]
        if type(result.candidate_count) is not int or result.candidate_count != len(
            links
        ):
            raise ValueError("Every candidate must have exactly one outcome")
        ids = {link.link_id for link in links}
        if len(ids) != len(links) or len({e.evidence_id for e in evidence}) != len(
            evidence
        ):
            raise ValueError("Duplicate output identities")
        if {e.evidence_id for e in evidence} != {
            link.evidence_id for link in links if link.evidence_id
        }:
            raise ValueError("Supply exactly the evidence referenced by this result")
        for link in links:
            if (
                link.snapshot_id != lease.snapshot_id
                or link.processing_key != lease.processing_key
            ):
                raise ValueError("Link belongs to a different snapshot/run")
            if link.related_link_id and link.related_link_id not in ids:
                raise ValueError("Related link must belong to the same result")
        if any(
            e.origin_kind == "inline" and e.origin_snapshot_id != lease.snapshot_id
            for e in evidence
        ):
            raise ValueError("Inline evidence belongs to another snapshot")
        resolved = sum(link.resolution_status == "resolved" for link in links)
        unresolved = len(links) - resolved
        retryable = any(link.retryable for link in links)
        with self.store.transaction() as tx:
            state = self._owned(tx, lease)
            # Retry must account for the same inventory; never silently drop failures.
            if state.outputs_persisted_at:
                previous_ids = {
                    row["link_id"] for row in tx.links(state.processing_key)
                }
                if not previous_ids.issubset(ids):
                    raise ValueError(
                        "Retry cannot drop previously discovered candidates"
                    )
                if not result.allow_inventory_expansion and previous_ids != ids:
                    raise ValueError(
                        "Candidate inventory changed; use a new pipeline/config version"
                    )
            for e in evidence:
                if tx.get(EVIDENCE, e.evidence_id) is None:
                    tx.put(EVIDENCE, e.model_dump(mode="json"))
            for link in links:
                tx.put(LINKS, link.model_dump(mode="json"))
            now = self.clock()
            state = self._changed(
                state,
                status="partial" if unresolved else "succeeded",
                candidate_count=len(links),
                resolved_count=resolved,
                unresolved_count=unresolved,
                retryable=retryable,
                next_retry_at=self._retry_at(state, retryable, result.retry_after),
                lease_owner=None,
                lease_expires_at=None,
                outputs_persisted_at=now,
                updated_at=now,
                completion_reason=(
                    None
                    if unresolved
                    else ("all_resolved" if links else "no_candidates")
                ),
            )
            tx.put(STATES, state.model_dump(mode="json"))
            self._record_attempt(tx, state, resolver_seconds)
        return state

    @staticmethod
    def _record_attempt(tx, state: ProcessingState, seconds: float | None):
        if seconds is None:
            return
        record = ProcessingAttempt(
            attempt_id="att_" + stable_hash([state.processing_key, state.attempts]),
            processing_key=state.processing_key,
            attempt=state.attempts,
            outcome=state.status,
            resolver_seconds=seconds,
            completed_at=state.updated_at,
        )
        tx.put("knowledge_processing_attempts", record.model_dump(mode="json"))

    def fail(
        self,
        lease: ProcessingState,
        *,
        code: str,
        message: str,
        retryable: bool = False,
        retry_after: float = 0,
        resolver_seconds: float | None = None,
    ) -> ProcessingState:
        with self.store.transaction() as tx:
            state = self._owned(tx, lease)
            state = self._changed(
                state,
                status="failed",
                error_code=code,
                error_message=message,
                retryable=retryable,
                next_retry_at=self._retry_at(state, retryable, retry_after),
                lease_owner=None,
                lease_expires_at=None,
                updated_at=self.clock(),
            )
            tx.put(STATES, state.model_dump(mode="json"))
            self._record_attempt(tx, state, resolver_seconds)
        return state

    def run_batch(
        self,
        keys: list[str],
        resolver: Callable,
        *,
        worker: str,
        limit: int = 100,
        lease_seconds: int = 300,
    ) -> list[ProcessingState]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        results = []
        for key in list(dict.fromkeys(keys))[:limit]:
            lease = self.claim(key, worker=worker, lease_seconds=lease_seconds)
            if lease is None:
                continue
            snapshot = SourceFindingSnapshot.model_validate(
                self.store.read(SNAPSHOTS, lease.snapshot_id)
            )
            started = time.monotonic()
            try:
                result = resolver(snapshot, lease)
            except RetryableResolutionError as exc:
                results.append(
                    self.fail(
                        lease,
                        code="resolver_transient",
                        message=str(exc),
                        retryable=True,
                        retry_after=exc.retry_after,
                        resolver_seconds=time.monotonic() - started,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                # Isolate resolver failures and retain a diagnostic for review.
                results.append(
                    self.fail(
                        lease,
                        code="resolver_error",
                        message=str(exc),
                        resolver_seconds=time.monotonic() - started,
                    )
                )
            else:
                # Storage errors are NOT resolver failures. Leave the lease recoverable.
                results.append(
                    self.complete(
                        lease, result, resolver_seconds=time.monotonic() - started
                    )
                )
        return results
