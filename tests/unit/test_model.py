from __future__ import annotations

import json
from pathlib import Path

from src.models import FindingsResponse


def test_findings_response_parses_sample_response() -> None:
    sample_path = Path("data/sample_response.json")
    payload = json.loads(sample_path.read_text(encoding="utf-8"))

    response = FindingsResponse.model_validate(payload)

    assert response.metadata.totalResults == 46135
    assert response.metadata.pageSize == 5
    assert response.rateLimit.remaining == 19
    assert len(response.findings) == 5
    assert response.findings[0].id == "66925"
    assert response.findings[0].auditfirms_auditfirm is not None
    assert response.findings[0].auditfirms_auditfirm.name == "Shieldify"
