"""Tests for AI knowledge decomposer service."""

from __future__ import annotations

from datetime import UTC, datetime
from src.models.knowledge_contract import (
    SourceFindingSnapshot,
    snapshot_id,
    source_key,
    stable_hash,
)
from src.models.ai_knowledge import AIDecomposedFinding
from src.services.ai_knowledge_decomposer import (
    AIKnowledgeDecomposer,
    convert_to_knowledge_revision,
)


def make_snapshot(title: str, content: str, source_id: str = "test-1") -> SourceFindingSnapshot:
    skey = source_key("code4rena", source_id)
    payload = {"id": source_id}
    digest = stable_hash(payload)
    return SourceFindingSnapshot(
        snapshot_id=snapshot_id(skey, digest),
        source_key=skey,
        source="code4rena",
        source_id=source_id,
        source_url=f"https://code4rena.com/reports/test#{source_id}",
        title=title,
        content=content,
        payload_kind="legacy_normalized_json",
        raw_payload=payload,
        raw_payload_hash=digest,
        captured_at=datetime.now(UTC),
    )


def test_ai_decomposer_offline_cast_pattern():
    decomposer = AIKnowledgeDecomposer(provider="offline")
    snapshot = make_snapshot(
        title="[H-03] Risk of silent overflow in reserves update due to uint128 cast",
        content="In the updateReserve function, the reserves are stored as uint128 while the values that update them are of type uint256.",
        source_id="H-03",
    )
    code = "function updateReserve(uint256 amount) external { reserve = uint128(amount); }"

    result = decomposer.decompose(snapshot, code_snippet=code)

    assert isinstance(result, AIDecomposedFinding)
    assert "Narrowing" in result.vulnerability_category or "Truncation" in result.vulnerability_category
    assert result.necessary_condition.statement
    assert result.sufficient_condition.statement
    assert result.trigger_condition.statement
    assert len(result.verification_checklist) >= 3
    assert "SafeCast" in result.remediation.statement or "safe" in result.remediation.statement.lower()

    # Convert to KnowledgeRevision
    rev = convert_to_knowledge_revision(snapshot, result)
    assert rev.version == 1
    assert len(rev.claims) == 6
    assert rev.review_status == "needs_review"


def test_ai_decomposer_offline_access_control():
    decomposer = AIKnowledgeDecomposer(provider="offline")
    snapshot = make_snapshot(
        title="[H-01] Missing access control on setFeeRecipient allows unauthorized takeover",
        content="Anyone can call this function to modify critical protocol configuration. Function is declared public without restriction.",
        source_id="H-01",
    )
    code = "function setFeeRecipient(address recipient) external { feeRecipient = recipient; }"

    result = decomposer.decompose(snapshot, code_snippet=code)

    assert isinstance(result, AIDecomposedFinding)
    assert "Access Control" in result.vulnerability_category
    assert "msg.sender" in result.sufficient_condition.statement or "unprivileged" in result.trigger_condition.statement.lower()
    assert len(result.verification_checklist) >= 3
    assert "onlyOwner" in result.remediation.statement or "modifier" in result.remediation.statement.lower()
