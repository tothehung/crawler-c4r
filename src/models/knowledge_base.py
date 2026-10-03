"""Versioned, grounded knowledge and auditable review; additive to contract v1."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from src.models.knowledge_contract import Contract, Digest, NonEmpty, stable_hash

Category = Literal[
    "root_cause",
    "preconditions",
    "exploit_conditions",
    "observed_behavior",
    "impact",
    "detection_signals",
    "remediation",
    "limitations",
]


class GroundedCitation(Contract):
    snapshot_id: NonEmpty
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    quote: NonEmpty
    link_id: str | None = None

    @model_validator(mode="after")
    def ordered(self):
        if self.end_line < self.start_line:
            raise ValueError("citation line range is reversed")
        return self


class GroundedClaim(Contract):
    claim_id: NonEmpty
    category: Category
    text: NonEmpty
    citations: list[GroundedCitation] = Field(min_length=1)

    @model_validator(mode="after")
    def identity(self):
        if self.claim_id != "clm_" + stable_hash(
            [
                self.category,
                self.text,
                [c.model_dump(mode="json") for c in self.citations],
            ]
        ):
            raise ValueError("claim_id does not match claim/citations")
        return self


class KnowledgeRevision(Contract):
    revision_id: NonEmpty
    knowledge_id: NonEmpty
    version: int = Field(ge=1)
    snapshot_id: NonEmpty
    processing_key: NonEmpty
    title: NonEmpty
    claims: list[GroundedClaim]
    evidence_link_ids: list[str]
    evidence_bindings: dict[str, str]
    missing_information: list[str]
    extraction_version: NonEmpty
    input_fingerprint: Digest
    content_hash: Digest
    review_status: Literal["needs_review", "approved", "rejected"] = "needs_review"
    review_sequence: int = Field(default=0, ge=0)
    reviewed_by: str | None = None
    review_note: str | None = None
    reviewed_at: AwareDatetime | None = None
    created_at: AwareDatetime

    def payload(self):
        row = self.model_dump(mode="json")
        return {
            key: row[key]
            for key in (
                "knowledge_id",
                "version",
                "snapshot_id",
                "processing_key",
                "title",
                "claims",
                "evidence_link_ids",
                "evidence_bindings",
                "missing_information",
                "extraction_version",
                "input_fingerprint",
            )
        }

    @model_validator(mode="after")
    def identity(self):
        if set(self.evidence_link_ids) != self.evidence_bindings.keys():
            raise ValueError("evidence bindings must cover linked evidence exactly")
        if self.content_hash != stable_hash(self.payload()):
            raise ValueError("knowledge content hash mismatch")
        if self.revision_id != "krv_" + stable_hash(
            [self.knowledge_id, self.version, self.content_hash]
        ):
            raise ValueError("revision identity mismatch")
        if self.review_status == "approved" and (
            self.missing_information or not self.claims
        ):
            raise ValueError("incomplete knowledge cannot be approved")
        if self.review_sequence and not (
            self.reviewed_by and self.review_note and self.reviewed_at
        ):
            raise ValueError("review requires reviewer, rationale and time")
        if self.review_status != "needs_review" and self.review_sequence == 0:
            raise ValueError("decision requires review event")
        return self


class KnowledgeHead(Contract):
    knowledge_id: NonEmpty
    latest_revision_id: NonEmpty
    latest_version: int = Field(ge=1)


class KnowledgeBuild(Contract):
    build_id: NonEmpty
    revision_id: NonEmpty
    input_fingerprint: Digest


class KnowledgeReviewEvent(Contract):
    event_id: NonEmpty
    revision_id: NonEmpty
    sequence: int = Field(ge=1)
    previous_status: NonEmpty
    status: Literal["needs_review", "approved", "rejected"]
    reviewer: NonEmpty
    note: NonEmpty
    reviewed_at: AwareDatetime


KB_MODELS = {
    "knowledge_revisions": KnowledgeRevision,
    "knowledge_heads": KnowledgeHead,
    "knowledge_builds": KnowledgeBuild,
    "knowledge_review_events": KnowledgeReviewEvent,
}
KB_KEYS = {
    "knowledge_revisions": "revision_id",
    "knowledge_heads": "knowledge_id",
    "knowledge_builds": "build_id",
    "knowledge_review_events": "event_id",
}
