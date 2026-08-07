from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.models import Finding, FindingsResponse


@pytest.fixture
def sample_payload() -> dict[str, Any]:
    sample_path = Path("data/sample_response.json")
    return json.loads(sample_path.read_text(encoding="utf-8"))


@pytest.fixture
def parsed_response(sample_payload: dict[str, Any]) -> FindingsResponse:
    return FindingsResponse.model_validate(sample_payload)


def test_parse_full_response(sample_payload: dict[str, Any]) -> None:
    # Arrange
    payload = sample_payload

    # Act
    response = FindingsResponse.model_validate(payload)

    # Assert
    assert isinstance(response, FindingsResponse)
    assert len(response.findings) == 5
    assert all(isinstance(finding, Finding) for finding in response.findings)


def test_parse_metadata_and_rate_limit(
    sample_payload: dict[str, Any],
    parsed_response: FindingsResponse,
) -> None:
    # Arrange
    expected_metadata = sample_payload["metadata"]
    expected_rate_limit = sample_payload["rateLimit"]
    response = parsed_response

    # Act
    metadata = response.metadata
    rate_limit = response.rateLimit

    # Assert
    assert metadata.totalResults == expected_metadata["totalResults"]
    assert metadata.currentPage == expected_metadata["currentPage"]
    assert metadata.pageSize == expected_metadata["pageSize"]
    assert metadata.totalPages == expected_metadata["totalPages"]
    assert metadata.elapsed == pytest.approx(expected_metadata["elapsed"])
    assert rate_limit.limit == expected_rate_limit["limit"]
    assert rate_limit.remaining == expected_rate_limit["remaining"]
    assert rate_limit.reset == expected_rate_limit["reset"]


def test_parse_first_finding_important_fields(
    parsed_response: FindingsResponse,
) -> None:
    # Arrange
    response = parsed_response

    # Act
    finding = response.findings[0]

    # Assert
    assert finding.id == "66925"
    assert (
        finding.title
        == "[L-03] `governanceCapActive` Unconditionally Disables the `emergencyCouncil` Circuit Breaker in `_distributeEnforced()`"
    )
    assert finding.impact == "LOW"
    assert finding.firm_name == "Shieldify"
    assert finding.protocol_name == "Up"


def test_parse_nested_objects_and_lists(parsed_response: FindingsResponse) -> None:
    # Arrange
    response = parsed_response

    # Act
    finding = response.findings[0]

    # Assert
    assert len(finding.issues_issue_finders) == 1
    assert finding.issues_issue_finders[0].wardens_warden is not None
    assert (
        finding.issues_issue_finders[0].wardens_warden.handle
        == "Shieldify Security"
    )
    assert finding.auditfirms_auditfirm is not None
    assert finding.auditfirms_auditfirm.name == "Shieldify"
    assert finding.auditfirms_auditfirm.logo_square == "Shieldify_square.png"
    assert finding.protocols_protocol is not None
    assert finding.protocols_protocol.name == "Up"
    assert finding.protocols_protocol.protocols_protocolcategoryscore == []
    assert finding.issues_issuetagscore == []


def test_optional_fields_can_be_missing(sample_payload: dict[str, Any]) -> None:
    # Arrange
    payload = copy.deepcopy(sample_payload)
    first_finding = payload["findings"][0]
    first_finding.pop("report_date")
    first_finding.pop("sponsor_name")
    first_finding.pop("auditfirms_auditfirm")

    # Act
    response = FindingsResponse.model_validate(payload)
    finding = response.findings[0]

    # Assert
    assert finding.report_date is None
    assert finding.sponsor_name is None
    assert finding.auditfirms_auditfirm is None


def test_empty_report_date_object_does_not_raise(
    sample_payload: dict[str, Any],
) -> None:
    # Arrange
    payload = copy.deepcopy(sample_payload)
    payload["findings"][0]["report_date"] = {}

    # Act
    response = FindingsResponse.model_validate(payload)
    finding = response.findings[0]

    # Assert
    assert finding.report_date is None


def test_finding_normalizes_nullable_api_fields(
    sample_payload: dict[str, Any],
) -> None:
    # Arrange
    payload = copy.deepcopy(sample_payload)
    finding_payload = payload["findings"][0]
    finding_payload.update(
        {
            "impact": " medium ",
            "finders_count": None,
            "quality_score": "",
            "general_score": None,
            "pdf_page_from": "",
            "content": None,
            "summary": None,
            "contest_prize_txt": None,
            "contest_link": None,
            "sponsor_link": None,
            "source_link": None,
            "github_link": None,
            "pdf_link": None,
            "contest_id": None,
            "bookmarked": None,
            "read": None,
            "issues_issue_finders": None,
            "issues_issuetagscore": None,
            "protocols_protocol": {
                "name": "Up",
                "protocols_protocolcategoryscore": None,
            },
        }
    )

    # Act
    response = FindingsResponse.model_validate(payload)
    finding = response.findings[0]

    # Assert
    assert finding.impact == "MEDIUM"
    assert finding.finders_count == 0
    assert finding.quality_score == 0
    assert finding.general_score == 0
    assert finding.pdf_page_from == 0
    assert finding.content == ""
    assert finding.summary == ""
    assert finding.contest_prize_txt == ""
    assert finding.contest_link == ""
    assert finding.sponsor_link == ""
    assert finding.source_link == ""
    assert finding.github_link == ""
    assert finding.pdf_link == ""
    assert finding.contest_id == ""
    assert finding.bookmarked is False
    assert finding.read is False
    assert finding.issues_issue_finders == []
    assert finding.issues_issuetagscore == []
    assert finding.protocols_protocol is not None
    assert finding.protocols_protocol.protocols_protocolcategoryscore == []


def test_finding_parses_numeric_strings(sample_payload: dict[str, Any]) -> None:
    # Arrange
    payload = copy.deepcopy(sample_payload)
    payload["findings"][0].update(
        {
            "finders_count": "2",
            "quality_score": "4.5",
            "general_score": "3",
            "pdf_page_from": "12",
        }
    )

    # Act
    response = FindingsResponse.model_validate(payload)
    finding = response.findings[0]

    # Assert
    assert finding.finders_count == 2
    assert finding.quality_score == 4.5
    assert finding.general_score == 3
    assert finding.pdf_page_from == 12


def test_missing_required_response_field_raises_validation_error(
    sample_payload: dict[str, Any],
) -> None:
    # Arrange
    payload = copy.deepcopy(sample_payload)
    payload.pop("findings")

    # Act / Assert
    with pytest.raises(ValidationError):
        FindingsResponse.model_validate(payload)


def test_missing_required_finding_field_raises_validation_error(
    sample_payload: dict[str, Any],
) -> None:
    # Arrange
    payload = copy.deepcopy(sample_payload)
    payload["findings"][0].pop("title")

    # Act / Assert
    with pytest.raises(ValidationError):
        FindingsResponse.model_validate(payload)


def test_invalid_field_type_raises_validation_error(
    sample_payload: dict[str, Any],
) -> None:
    # Arrange
    payload = copy.deepcopy(sample_payload)
    payload["metadata"]["totalResults"] = "not-an-int"

    # Act / Assert
    with pytest.raises(ValidationError):
        FindingsResponse.model_validate(payload)
