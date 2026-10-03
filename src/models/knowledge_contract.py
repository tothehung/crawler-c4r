"""Version 1 contracts. Opt-in; existing crawler/evidence models stay unchanged."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

NonEmpty = Annotated[str, Field(min_length=1)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
CommitSHA = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
PositiveLine = Annotated[int, Field(strict=True, ge=1)]


def stable_hash(value: Any) -> str:
    """Hash canonical JSON, preserving whitespace inside strings and array order."""
    data = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def source_key(source: str, source_id: str) -> str:
    return "src_" + stable_hash(["source-v1", source, source_id])


def snapshot_id(key: str, payload_hash: str) -> str:
    return "snp_" + stable_hash(["snapshot-v1", key, payload_hash])


def processing_key(snapshot: str, pipeline_version: str, config_hash: str) -> str:
    return "prc_" + stable_hash(
        ["processing-v1", snapshot, pipeline_version, config_hash]
    )


class Source(StrEnum):
    SOLODIT = "solodit"
    CODE4RENA = "code4rena"


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFORMATIONAL = "INFORMATIONAL"
    GAS = "GAS"
    UNKNOWN = "UNKNOWN"


class EvidenceRole(StrEnum):
    VULNERABLE = "vulnerable"
    FIX = "fix"
    POC = "poc"
    CONTEXT = "context"
    UNKNOWN = "unknown"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    schema_version: Literal["1.0"] = "1.0"


class LineRange(Contract):
    start_line: PositiveLine
    end_line: PositiveLine

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line (1-based inclusive)")
        return self


class CanonicalFinding(Contract):
    canonical_finding_id: NonEmpty
    title: NonEmpty
    created_at: AwareDatetime


class SourceFindingSnapshot(Contract):
    snapshot_id: NonEmpty
    source_key: NonEmpty
    source: Source
    source_id: NonEmpty
    legacy_finding_id: str | None = None
    canonical_finding_id: str | None = None
    source_url: NonEmpty
    title: NonEmpty
    content: str
    severity_original: str | None = None
    severity: Severity = Severity.UNKNOWN
    source_quality_score: float | None = None
    source_quality_scale: str | None = None
    payload_kind: Literal["api_json", "report_html", "legacy_normalized_json"]
    raw_payload: dict[str, Any] | str
    raw_payload_hash: Digest
    captured_at: AwareDatetime

    @model_validator(mode="after")
    def identity(self) -> Self:
        if self.source_key != source_key(self.source, self.source_id):
            raise ValueError("source_key does not match source identity")
        if self.raw_payload_hash != stable_hash(self.raw_payload):
            raise ValueError("raw_payload_hash does not match raw_payload")
        if self.snapshot_id != snapshot_id(self.source_key, self.raw_payload_hash):
            raise ValueError("snapshot_id does not match source payload")
        if self.source_quality_score is not None and not self.source_quality_scale:
            raise ValueError("source quality scores require an explicit scale")
        if self.payload_kind == "report_html" and not isinstance(self.raw_payload, str):
            raise ValueError("report_html requires the original HTML string")
        if self.payload_kind != "report_html" and not isinstance(
            self.raw_payload, dict
        ):
            raise ValueError("JSON payload kinds require an object")
        return self


class CodeEvidence(Contract):
    evidence_id: NonEmpty
    origin_kind: Literal["github_file", "github_diff", "gist", "inline"]
    origin_url: str | None = None
    repo: str | None = None
    commit_sha: CommitSHA | None = None
    path: str | None = None
    gist_id: str | None = None
    gist_revision: str | None = None
    origin_snapshot_id: str | None = None
    locator: NonEmpty
    source_range: LineRange | None = None
    language: NonEmpty = "Solidity"
    raw_snippet: NonEmpty
    normalized_snippet: str
    normalization_version: NonEmpty
    extractor_version: NonEmpty
    transformations: list[str] = Field(default_factory=list)
    contract_name: str | None = None
    function_name: str | None = None
    function_signature: str | None = None
    selector_4byte: Annotated[str, Field(pattern=r"^0x[0-9a-f]{8}$")] | None = None
    solidity_pragma: str | None = None
    syntax_status: Literal[
        "not_checked", "parsed", "invalid", "insufficient_context"
    ] = "not_checked"
    parser_version: str | None = None
    diagnostics: list[str] = Field(default_factory=list)
    created_at: AwareDatetime

    @field_validator("path")
    @classmethod
    def relative_path(cls, value: str | None) -> str | None:
        if value is not None:
            path = PurePosixPath(value)
            if (
                not value
                or path.is_absolute()
                or "\\" in value
                or ":" in value
                or ".." in path.parts
                or path.as_posix() != value
                or value == "."
            ):
                raise ValueError(
                    "path must be a normalized repository-relative POSIX path"
                )
        return value

    @model_validator(mode="after")
    def provenance(self) -> Self:
        if not self.raw_snippet.strip():
            raise ValueError(
                "empty code belongs in an unresolved link, not code_evidence"
            )
        if self.origin_kind.startswith("github") and not (
            self.repo and self.commit_sha and self.path and self.origin_url
        ):
            raise ValueError(
                "GitHub evidence requires repo, immutable commit, path and URL"
            )
        if self.origin_kind == "gist" and not (
            self.gist_id and self.gist_revision and self.path and self.origin_url
        ):
            raise ValueError("Gist evidence requires gist ID, revision, file and URL")
        if self.origin_kind == "inline" and not self.origin_snapshot_id:
            raise ValueError("inline evidence requires its source snapshot")
        if self.syntax_status != "not_checked" and not self.parser_version:
            raise ValueError("syntax checks require parser_version")
        if self.evidence_id != self.expected_id():
            raise ValueError("evidence_id does not match evidence content/provenance")
        return self

    def expected_id(self) -> str:
        fields = (
            "origin_kind",
            "repo",
            "commit_sha",
            "path",
            "gist_id",
            "gist_revision",
            "origin_snapshot_id",
            "locator",
            "source_range",
            "language",
            "raw_snippet",
            "normalized_snippet",
            "normalization_version",
            "extractor_version",
            "transformations",
        )
        data = self.model_dump(mode="json")
        return "evd_" + stable_hash(["evidence-v1", {key: data[key] for key in fields}])


class FindingEvidenceLink(Contract):
    link_id: NonEmpty
    snapshot_id: NonEmpty
    processing_key: NonEmpty
    candidate_locator: NonEmpty
    candidate_url: str | None = None
    evidence_id: str | None = None
    role: EvidenceRole = EvidenceRole.UNKNOWN
    role_basis: str | None = None
    related_link_id: str | None = None
    reported_range: LineRange | None = None
    report_context: str | None = None
    resolution_status: Literal["resolved", "partial", "unavailable", "retryable_error"]
    evidence_confidence: Annotated[float, Field(ge=0, le=1)] | None = None
    confidence_method: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    created_at: AwareDatetime

    @model_validator(mode="after")
    def resolution(self) -> Self:
        expected = "lnk_" + stable_hash(
            ["link-v1", self.processing_key, self.candidate_locator]
        )
        if self.link_id != expected:
            raise ValueError(
                "link_id does not match processing key and candidate locator"
            )
        if self.resolution_status in ("resolved", "partial") and not self.evidence_id:
            raise ValueError("resolved/partial links require evidence_id")
        if self.resolution_status in ("unavailable", "retryable_error") and (
            self.evidence_id or not self.error_code
        ):
            raise ValueError("unresolved links require error_code and no evidence_id")
        if self.resolution_status == "retryable_error" and not self.retryable:
            raise ValueError("retryable_error must be retryable")
        if self.resolution_status in ("resolved", "unavailable") and self.retryable:
            raise ValueError(
                "resolved/unavailable links cannot request automatic retry"
            )
        if self.role != EvidenceRole.UNKNOWN and not self.role_basis:
            raise ValueError("an assigned role needs a basis in the report or review")
        if self.evidence_confidence is not None and not self.confidence_method:
            raise ValueError("evidence confidence requires a scoring method/version")
        return self


class ProcessingState(Contract):
    processing_key: NonEmpty
    snapshot_id: NonEmpty
    pipeline_version: NonEmpty
    config_hash: Digest
    status: ProcessingStatus = ProcessingStatus.PENDING
    attempts: Annotated[int, Field(strict=True, ge=0)] = 0
    max_attempts: Annotated[int, Field(strict=True, ge=1)] = 3
    candidate_count: Annotated[int, Field(strict=True, ge=0)] = 0
    resolved_count: Annotated[int, Field(strict=True, ge=0)] = 0
    unresolved_count: Annotated[int, Field(strict=True, ge=0)] = 0
    retryable: bool = False
    next_retry_at: AwareDatetime | None = None
    lease_owner: str | None = None
    lease_expires_at: AwareDatetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    completion_reason: Literal["all_resolved", "no_candidates"] | None = None
    outputs_persisted_at: AwareDatetime | None = None
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def consistency(self) -> Self:
        if self.processing_key != processing_key(
            self.snapshot_id, self.pipeline_version, self.config_hash
        ):
            raise ValueError("processing_key does not match its inputs")
        if self.attempts > self.max_attempts:
            raise ValueError("attempts exceeds max_attempts")
        if self.resolved_count + self.unresolved_count > self.candidate_count:
            raise ValueError("candidate counters are inconsistent")
        if self.status == ProcessingStatus.RUNNING and not (
            self.lease_owner and self.lease_expires_at
        ):
            raise ValueError("running requires a lease")
        if self.status != ProcessingStatus.PENDING and self.attempts == 0:
            raise ValueError("processing has started but attempts is zero")
        if self.next_retry_at is not None and (
            not self.retryable or self.attempts >= self.max_attempts
        ):
            raise ValueError(
                "scheduled retry requires retryable state and remaining attempts"
            )
        if self.retryable and self.status not in (
            ProcessingStatus.PARTIAL,
            ProcessingStatus.FAILED,
        ):
            raise ValueError("only partial/failed states can be retryable")
        if self.status == ProcessingStatus.SUCCEEDED:
            if (
                not self.outputs_persisted_at
                or self.unresolved_count
                or self.resolved_count != self.candidate_count
            ):
                raise ValueError(
                    "success requires persisted outputs and every candidate resolved"
                )
            reason = "no_candidates" if self.candidate_count == 0 else "all_resolved"
            if self.completion_reason != reason:
                raise ValueError("completion_reason does not match successful result")
        elif self.completion_reason is not None:
            raise ValueError("completion_reason is only set on success")
        if self.status == ProcessingStatus.PARTIAL and (
            not self.outputs_persisted_at
            or self.unresolved_count == 0
            or self.resolved_count + self.unresolved_count != self.candidate_count
        ):
            raise ValueError(
                "partial requires persisted outputs and accounted unresolved candidates"
            )
        if self.status == ProcessingStatus.FAILED and not self.error_code:
            raise ValueError("failed requires error_code")
        return self


class Citation(Contract):
    snapshot_id: NonEmpty
    link_id: str | None = None
    report_locator: NonEmpty


class KnowledgeClaim(Contract):
    text: NonEmpty
    citations: list[Citation] = Field(min_length=1)


class KnowledgeCandidate(Contract):
    knowledge_id: NonEmpty
    version: Annotated[int, Field(strict=True, ge=1)]
    title: NonEmpty
    root_cause: KnowledgeClaim
    preconditions: list[KnowledgeClaim] = Field(default_factory=list)
    exploit_conditions: list[KnowledgeClaim] = Field(default_factory=list)
    impact: list[KnowledgeClaim] = Field(default_factory=list)
    detection_signals: list[KnowledgeClaim] = Field(default_factory=list)
    remediation: list[KnowledgeClaim] = Field(default_factory=list)
    limitations: list[KnowledgeClaim] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    taxonomy_tags: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    engine_support: Literal["unknown", "supported", "partial", "unsupported"] = (
        "unknown"
    )
    review_status: Literal["draft", "needs_review", "approved", "rejected"] = "draft"
    reviewed_by: str | None = None
    reviewed_at: AwareDatetime | None = None
    review_note: str | None = None
    extraction_version: NonEmpty
    extraction_config_hash: Digest
    created_at: AwareDatetime

    @model_validator(mode="after")
    def review(self) -> Self:
        if self.review_status in ("approved", "rejected") and not (
            self.reviewed_by and self.reviewed_at and self.review_note
        ):
            raise ValueError(
                "review decisions require reviewer, timestamp and rationale"
            )
        if self.review_status == "approved" and self.missing_information:
            raise ValueError("incomplete knowledge must remain in review")
        return self


TABLE_MODELS: dict[str, type[Contract]] = {
    "canonical_findings": CanonicalFinding,
    "source_finding_snapshots": SourceFindingSnapshot,
    "code_evidence": CodeEvidence,
    "finding_evidence_links": FindingEvidenceLink,
    "evidence_processing_state": ProcessingState,
    "knowledge_candidates": KnowledgeCandidate,
}
