from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.clients.solodit_client import FindingsPage, PaginationOptions
from src.mappers import finding_to_bigquery_row, stable_payload_hash
from src.models import Finding
from src.services import FindingExportService


class FakeSoloditClient:
    def __init__(self, findings: list[dict[str, Any]]) -> None:
        self.findings = findings
        self.calls: list[dict[str, Any]] = []

    def fetch_findings(
        self,
        page_size: int,
        filters: dict[str, Any] | None = None,
        pagination: PaginationOptions | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "page_size": page_size,
                "filters": filters,
                "pagination": pagination,
            }
        )
        return self.findings


class StreamingFakeSoloditClient:
    def __init__(self, pages: list[FindingsPage]) -> None:
        self.pages = pages
        self.calls: list[dict[str, Any]] = []

    def fetch_findings(
        self,
        page_size: int,
        filters: dict[str, Any] | None = None,
        pagination: PaginationOptions | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "page_size": page_size,
                "filters": filters,
                "pagination": pagination,
            }
        )
        return [
            raw_finding
            for page in self.pages
            for raw_finding in page.findings
        ]

    def iter_findings_pages(
        self,
        page_size: int,
        filters: dict[str, Any] | None = None,
        pagination: PaginationOptions | None = None,
    ) -> Any:
        self.calls.append(
            {
                "page_size": page_size,
                "filters": filters,
                "pagination": pagination,
            }
        )
        yield from self.pages


@pytest.fixture
def sample_payload() -> dict[str, Any]:
    sample_path = Path("data/sample_response.json")
    return json.loads(sample_path.read_text(encoding="utf-8"))


@pytest.fixture
def sample_findings(sample_payload: dict[str, Any]) -> list[dict[str, Any]]:
    return sample_payload["findings"]


def _read_jsonl(output_path: Path) -> list[dict[str, Any]]:
    if not output_path.read_text(encoding="utf-8"):
        return []
    return [
        json.loads(line)
        for line in output_path.read_text(encoding="utf-8").splitlines()
    ]


def test_export_findings_validates_and_writes_jsonl(
    sample_findings: list[dict[str, Any]],
    tmp_path: Path,
) -> None:
    # Arrange
    output_path = tmp_path / "nested" / "findings.jsonl"
    client = FakeSoloditClient(copy.deepcopy(sample_findings[:2]))
    service = FindingExportService(client=client, output_path=output_path)

    # Act
    findings = service.export_findings(page_size=2)
    written_records = _read_jsonl(output_path)

    # Assert
    assert output_path.exists()
    assert len(findings) == 2
    assert written_records[0]["id"] == sample_findings[0]["id"]
    assert written_records[0]["title"] == sample_findings[0]["title"]
    assert written_records[0]["source_payload"]["id"] == sample_findings[0]["id"]
    assert written_records[0]["source_payload_hash"] == stable_payload_hash(
        written_records[0]["source_payload"]
    )
    assert written_records[0]["finder_handles"] == ["Shieldify Security"]
    assert written_records[0]["crawled_at"].endswith("Z")
    assert written_records[0]["loaded_at"].endswith("Z")
    assert client.calls == [
        {
            "page_size": 2,
            "filters": None,
            "pagination": None,
        }
    ]


def test_export_findings_writes_correct_number_of_records(
    sample_findings: list[dict[str, Any]],
    tmp_path: Path,
) -> None:
    # Arrange
    output_path = tmp_path / "findings.jsonl"
    client = FakeSoloditClient(copy.deepcopy(sample_findings))
    service = FindingExportService(client=client, output_path=output_path)

    # Act
    service.export_findings(page_size=5)
    lines = output_path.read_text(encoding="utf-8").splitlines()

    # Assert
    assert len(lines) == len(sample_findings)


def test_export_findings_preserves_unicode_and_markdown(tmp_path: Path) -> None:
    # Arrange
    output_path = tmp_path / "findings.jsonl"
    raw_finding = {
        "id": "unicode-1",
        "title": "Lỗi kiểm tra quyền",
        "slug": "loi-kiem-tra-quyen",
        "impact": "MEDIUM",
        "content": "## Mô tả\n\n- Giữ **Markdown** và tiếng Việt.",
    }
    client = FakeSoloditClient([raw_finding])
    service = FindingExportService(client=client, output_path=output_path)

    # Act
    service.export_findings(page_size=1)
    raw_jsonl = output_path.read_text(encoding="utf-8")
    written_records = _read_jsonl(output_path)

    # Assert
    assert "Lỗi kiểm tra quyền" in raw_jsonl
    assert written_records[0]["content"] == raw_finding["content"]
    assert written_records[0]["source_payload"]["content"] == raw_finding["content"]
    assert written_records[0]["content"].startswith("## Mô tả")
    assert "**Markdown**" in written_records[0]["content"]


def test_export_findings_invalid_finding_raises_validation_error(
    sample_findings: list[dict[str, Any]],
    tmp_path: Path,
) -> None:
    # Arrange
    invalid_finding = copy.deepcopy(sample_findings[0])
    invalid_finding.pop("title")
    output_path = tmp_path / "findings.jsonl"
    client = FakeSoloditClient([invalid_finding])
    service = FindingExportService(client=client, output_path=output_path)

    # Act / Assert
    with pytest.raises(ValidationError):
        service.export_findings(page_size=1)
    assert not output_path.exists()


def test_export_findings_empty_findings_creates_empty_file(tmp_path: Path) -> None:
    # Arrange
    output_path = tmp_path / "findings.jsonl"
    client = FakeSoloditClient([])
    service = FindingExportService(client=client, output_path=output_path)

    # Act
    findings = service.export_findings(page_size=100)

    # Assert
    assert findings == []
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") == ""


def test_export_findings_streaming_writes_pages_and_checkpoint(
    sample_findings: list[dict[str, Any]],
    tmp_path: Path,
) -> None:
    # Arrange
    output_path = tmp_path / "findings.jsonl"
    checkpoint_path = tmp_path / "checkpoints" / "findings_export.json"
    pages = [
        FindingsPage(
            findings=[copy.deepcopy(sample_findings[0])],
            current_page=1,
            total_pages=3,
            page_size=1,
            metadata={},
            response_data={},
        ),
        FindingsPage(
            findings=[copy.deepcopy(sample_findings[1])],
            current_page=2,
            total_pages=3,
            page_size=1,
            metadata={},
            response_data={},
        ),
    ]
    client = StreamingFakeSoloditClient(pages)
    service = FindingExportService(
        client=client,
        output_path=output_path,
        checkpoint_path=checkpoint_path,
    )

    # Act
    result = service.export_findings_streaming(
        page_size=1,
        pagination=PaginationOptions(max_pages=2, request_delay_seconds=0),
    )

    # Assert
    written_records = _read_jsonl(output_path)
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))

    assert [record["id"] for record in written_records] == [
        sample_findings[0]["id"],
        sample_findings[1]["id"],
    ]
    assert result.pages_written == 2
    assert result.records_written == 2
    assert result.next_page == 3
    assert result.completed is False
    assert checkpoint["next_page"] == 3
    assert checkpoint["last_completed_page"] == 2
    assert checkpoint["pages_written"] == 2
    assert checkpoint["records_written"] == 2
    assert checkpoint["completed"] is False


def test_export_findings_streaming_resumes_from_checkpoint(
    sample_findings: list[dict[str, Any]],
    tmp_path: Path,
) -> None:
    # Arrange
    output_path = tmp_path / "findings.jsonl"
    checkpoint_path = tmp_path / "checkpoints" / "findings_export.json"
    first_row = finding_to_bigquery_row(
        Finding.model_validate(copy.deepcopy(sample_findings[0]))
    )
    output_path.write_text(
        json.dumps(first_row, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(
        json.dumps(
            {
                "next_page": 2,
                "last_completed_page": 1,
                "pages_written": 1,
                "records_written": 1,
                "total_pages": 2,
                "completed": False,
            }
        ),
        encoding="utf-8",
    )
    client = StreamingFakeSoloditClient(
        [
            FindingsPage(
                findings=[copy.deepcopy(sample_findings[1])],
                current_page=2,
                total_pages=2,
                page_size=1,
                metadata={},
                response_data={},
            )
        ]
    )
    service = FindingExportService(
        client=client,
        output_path=output_path,
        checkpoint_path=checkpoint_path,
    )

    # Act
    result = service.export_findings_streaming(
        page_size=1,
        pagination=PaginationOptions(start_page=1, request_delay_seconds=0),
        resume=True,
    )

    # Assert
    written_records = _read_jsonl(output_path)
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))

    assert [record["id"] for record in written_records] == [
        sample_findings[0]["id"],
        sample_findings[1]["id"],
    ]
    assert client.calls[0]["pagination"].start_page == 2
    assert result.start_page == 2
    assert result.pages_written == 1
    assert result.records_written == 1
    assert result.completed is True
    assert checkpoint["next_page"] == 3
    assert checkpoint["last_completed_page"] == 2
    assert checkpoint["pages_written"] == 2
    assert checkpoint["records_written"] == 2
    assert checkpoint["completed"] is True
