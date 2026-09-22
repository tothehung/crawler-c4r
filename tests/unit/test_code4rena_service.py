from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from src.clients.code4rena_client import Code4renaContest
from src.services.code4rena_service import (
    Code4renaCheckpoint,
    Code4renaExportService,
)


def test_code4rena_service_export_with_mock(tmp_path: Path) -> None:
    output_path = tmp_path / "findings_c4.jsonl"
    checkpoint_path = tmp_path / "c4_checkpoint.json"

    # Mock client
    mock_client = MagicMock()
    mock_contests = [
        Code4renaContest(
            slug="2023-05-juicebox",
            title="Juicebox Buyback",
            sponsor="Juicebox",
            date="2023-07-26",
        ),
        Code4renaContest(
            slug="2023-04-caviar",
            title="Caviar Pools",
            sponsor="Caviar",
            date="2023-05-18",
        ),
    ]
    mock_client.fetch_all_contests.return_value = mock_contests

    mock_client.fetch_report_findings.side_effect = [
        [
            {
                "id": "c4-juicebox-m1",
                "kind": "MARKDOWN",
                "title": "[M-01] Juicebox Issue",
                "impact": "MEDIUM",
                "finders_count": 1,
                "content": "Finding details here",
                "slug": "juicebox-m1",
                "firm_name": "Code4rena",
            }
        ],
        [
            {
                "id": "c4-caviar-h1",
                "kind": "MARKDOWN",
                "title": "[H-01] Caviar Issue",
                "impact": "HIGH",
                "finders_count": 2,
                "content": "Caviar details here",
                "slug": "caviar-h1",
                "firm_name": "Code4rena",
            }
        ],
    ]

    service = Code4renaExportService(
        client=mock_client,
        output_path=output_path,
        checkpoint_path=checkpoint_path,
    )

    # 1. Export first contest only
    result1 = service.export_all(max_contests=1, resume=False)
    assert result1.contests_processed == 1
    assert result1.records_written == 1
    assert not result1.completed

    # Check checkpoint file
    assert checkpoint_path.exists()
    cp_data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert cp_data["completed_slugs"] == ["2023-05-juicebox"]
    assert cp_data["records_written"] == 1

    # Check JSONL
    assert output_path.exists()
    lines = [line for line in output_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 1
    row1 = json.loads(lines[0])
    assert row1["id"] == "c4-juicebox-m1"
    assert row1["impact"] == "MEDIUM"

    # 2. Resume to process second contest
    result2 = service.export_all(resume=True)
    assert result2.contests_processed == 1
    assert result2.records_written == 1
    assert result2.completed

    # Check total lines in JSONL is now 2
    lines2 = [line for line in output_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines2) == 2
    row2 = json.loads(lines2[1])
    assert row2["id"] == "c4-caviar-h1"
    assert row2["impact"] == "HIGH"
