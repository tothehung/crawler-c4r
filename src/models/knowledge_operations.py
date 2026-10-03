"""Additive phase-6 records; immutable source/evidence contract v1 stays unchanged."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from src.models.knowledge_contract import (
    Contract,
    Digest,
    NonEmpty,
    Source,
    stable_hash,
)


class FindingMembership(Contract):
    membership_id: NonEmpty
    group_id: NonEmpty
    snapshot_id: NonEmpty
    source_key: NonEmpty
    source: Source
    method: Literal["source_identity", "finding_url", "content_exact", "title_exact"]
    decision: Literal["confirmed", "candidate"]
    normalized_key: NonEmpty
    dedup_version: NonEmpty
    created_at: AwareDatetime

    @model_validator(mode="after")
    def identity(self):
        if self.group_id != "grp_" + stable_hash(
            [self.dedup_version, self.method, self.normalized_key]
        ):
            raise ValueError("group_id does not match dedup inputs")
        if self.membership_id != "mem_" + stable_hash(
            [self.group_id, self.snapshot_id]
        ):
            raise ValueError("membership_id does not match group/snapshot")
        expected = (
            "confirmed"
            if self.method in {"source_identity", "finding_url"}
            else "candidate"
        )
        if self.decision != expected:
            raise ValueError(
                "content similarity cannot automatically confirm duplicates"
            )
        return self


class FindingDedupState(Contract):
    dedup_key: NonEmpty
    snapshot_id: NonEmpty
    dedup_version: NonEmpty
    membership_ids: list[str]
    completed_at: AwareDatetime

    @model_validator(mode="after")
    def identity(self):
        if self.dedup_key != "ddp_" + stable_hash(
            [self.snapshot_id, self.dedup_version]
        ):
            raise ValueError("dedup_key does not match inputs")
        return self


class ProcessingAttempt(Contract):
    attempt_id: NonEmpty
    processing_key: NonEmpty
    attempt: int = Field(ge=1)
    outcome: Literal["succeeded", "partial", "failed"]
    resolver_seconds: float = Field(ge=0)
    completed_at: AwareDatetime

    @model_validator(mode="after")
    def identity(self):
        if self.attempt_id != "att_" + stable_hash([self.processing_key, self.attempt]):
            raise ValueError("attempt_id does not match processing attempt")
        return self


class BatchCheckpoint(Contract):
    checkpoint_id: NonEmpty
    name: NonEmpty
    pipeline_version: NonEmpty
    config_hash: Digest
    after: str = ""
    completed: bool = False
    sweep: int = Field(ge=1)
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def identity(self):
        if self.checkpoint_id != "bcp_" + stable_hash(
            [self.name, self.pipeline_version, self.config_hash]
        ):
            raise ValueError("checkpoint_id does not match scope")
        return self


OPERATIONS_MODELS = {
    "finding_dedup_memberships": FindingMembership,
    "finding_dedup_state": FindingDedupState,
    "knowledge_processing_attempts": ProcessingAttempt,
    "knowledge_batch_checkpoints": BatchCheckpoint,
}
OPERATIONS_KEYS = {
    "finding_dedup_memberships": "membership_id",
    "finding_dedup_state": "dedup_key",
    "knowledge_processing_attempts": "attempt_id",
    "knowledge_batch_checkpoints": "checkpoint_id",
}
