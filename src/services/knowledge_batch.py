"""Resume a bounded sweep, committing its cursor only after page outputs persist."""

from __future__ import annotations

from datetime import UTC, datetime

from src.models.knowledge_contract import stable_hash
from src.models.knowledge_operations import BatchCheckpoint
from src.services.knowledge_processing import KnowledgeProcessingService


def run_sweep(
    store,
    resolver,
    *,
    name: str,
    pipeline_version: str,
    config: dict,
    page_size: int = 100,
    max_pages: int = 1,
    worker: str = "batch-worker",
    lease_seconds: int = 300,
    service=None,
) -> dict:
    if not 1 <= page_size <= 1000 or not 1 <= max_pages <= 1000:
        raise ValueError("page_size/max_pages must be in 1..1000")
    service = service or KnowledgeProcessingService(store)
    digest = stable_hash(config)
    key = "bcp_" + stable_hash([name, pipeline_version, digest])
    previous = store.read("knowledge_batch_checkpoints", key)
    if previous and not previous["completed"]:
        checkpoint = BatchCheckpoint.model_validate(previous)
    else:
        checkpoint = BatchCheckpoint(
            checkpoint_id=key,
            name=name,
            pipeline_version=pipeline_version,
            config_hash=digest,
            sweep=previous["sweep"] + 1 if previous else 1,
            updated_at=datetime.now(UTC),
        )
    attempted = scanned = matched = pages = 0
    outcomes = {}
    for _ in range(max_pages):
        rows = store.states(after=checkpoint.after, limit=page_size)
        keys = [
            r["processing_key"]
            for r in rows
            if r["pipeline_version"] == pipeline_version and r["config_hash"] == digest
        ]
        results = service.run_batch(
            keys, resolver, worker=worker, limit=page_size, lease_seconds=lease_seconds
        )
        # Interruptions/storage failures above leave the previous cursor intact.
        checkpoint = BatchCheckpoint.model_validate(
            checkpoint.model_dump()
            | {
                "after": rows[-1]["processing_key"] if rows else checkpoint.after,
                "completed": len(rows) < page_size,
                "updated_at": datetime.now(UTC),
            }
        )
        with store.transaction() as tx:
            if tx.get("knowledge_batch_checkpoints", key) != previous:
                raise RuntimeError(
                    "Checkpoint changed concurrently; resume from persisted cursor"
                )
            tx.put("knowledge_batch_checkpoints", checkpoint.model_dump(mode="json"))
        previous = checkpoint.model_dump(mode="json")
        scanned += len(rows)
        matched += len(keys)
        attempted += len(results)
        pages += 1
        for result in results:
            outcomes[result.status] = outcomes.get(result.status, 0) + 1
        if checkpoint.completed:
            break
    return {
        "checkpoint": checkpoint.model_dump(mode="json"),
        "pages": pages,
        "scanned": scanned,
        "matched": matched,
        "attempted": attempted,
        "skipped": matched - attempted,
        "outcomes": outcomes,
    }
