from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.mappers import (
    finding_to_bigquery_row,
    findings_to_bigquery_rows,
    stable_payload_hash,
)
from src.models import Finding


EXPECTED_BIGQUERY_COLUMNS = {
    "id",
    "kind",
    "auditfirm_id",
    "impact",
    "finders_count",
    "protocol_id",
    "title",
    "content",
    "summary",
    "report_date",
    "contest_prize_txt",
    "contest_link",
    "sponsor_name",
    "sponsor_link",
    "quality_score",
    "general_score",
    "source_link",
    "github_link",
    "pdf_link",
    "pdf_page_from",
    "contest_id",
    "slug",
    "firm_name",
    "firm_logo_square",
    "protocol_name",
    "bookmarked",
    "read",
    "finder_handles",
    "auditfirm",
    "protocol",
    "issue_finders",
    "issue_tag_scores",
    "source_payload",
    "source_payload_hash",
    "crawled_at",
    "loaded_at",
}


def _sample_finding_payload() -> dict[str, Any]:
    sample_path = Path("data/sample_response.json")
    payload = json.loads(sample_path.read_text(encoding="utf-8"))
    return payload["findings"][0]


def test_finding_to_bigquery_row_matches_schema_contract() -> None:
    # Arrange
    finding = Finding.model_validate(_sample_finding_payload())
    crawled_at = datetime(2026, 8, 5, 1, 2, 3, tzinfo=UTC)
    loaded_at = datetime(2026, 8, 5, 4, 5, 6, tzinfo=UTC)

    # Act
    row = finding_to_bigquery_row(
        finding,
        crawled_at=crawled_at,
        loaded_at=loaded_at,
    )

    # Assert
    assert set(row) == EXPECTED_BIGQUERY_COLUMNS
    assert row["id"] == "66925"
    assert row["title"] == finding.title
    assert row["slug"] == finding.slug
    assert row["impact"] == "LOW"
    assert row["firm_name"] == "Shieldify"
    assert row["protocol_name"] == "Up"
    assert row["finder_handles"] == ["Shieldify Security"]
    assert row["auditfirm"] == {
        "name": "Shieldify",
        "logo_square": "Shieldify_square.png",
    }
    assert row["protocol"]["name"] == "Up"
    assert row["issue_finders"][0]["wardens_warden"]["handle"] == "Shieldify Security"
    assert row["source_payload"]["id"] == "66925"
    assert row["report_date"] is None
    assert row["crawled_at"] == "2026-08-05T01:02:03Z"
    assert row["loaded_at"] == "2026-08-05T04:05:06Z"
    assert row["source_payload_hash"] == stable_payload_hash(row["source_payload"])


def test_finding_to_bigquery_row_hash_is_stable_across_load_times() -> None:
    # Arrange
    finding = Finding.model_validate(_sample_finding_payload())

    # Act
    first_row = finding_to_bigquery_row(
        finding,
        loaded_at=datetime(2026, 8, 5, 1, 0, 0, tzinfo=UTC),
    )
    second_row = finding_to_bigquery_row(
        finding,
        loaded_at=datetime(2026, 8, 5, 2, 0, 0, tzinfo=UTC),
    )

    # Assert
    assert first_row["source_payload_hash"] == second_row["source_payload_hash"]
    assert first_row["loaded_at"] != second_row["loaded_at"]


def test_findings_to_bigquery_rows_uses_shared_batch_timestamps() -> None:
    # Arrange
    payload = _sample_finding_payload()
    findings = [
        Finding.model_validate(payload),
        Finding.model_validate({**payload, "id": "66925-copy", "slug": "copy"}),
    ]
    loaded_at = datetime(2026, 8, 5, 9, 0, 0, tzinfo=UTC)

    # Act
    rows = findings_to_bigquery_rows(findings, loaded_at=loaded_at)

    # Assert
    assert [row["id"] for row in rows] == ["66925", "66925-copy"]
    assert {row["loaded_at"] for row in rows} == {"2026-08-05T09:00:00Z"}
