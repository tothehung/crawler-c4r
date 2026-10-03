"""Reject stale or misleading evidence in the curated pattern pilot."""

import copy
import json
from pathlib import Path

import pytest

from scripts.verify_cast_pattern import validate_cases

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def artifacts():
    return (
        json.loads((ROOT / "tools/cast-pattern/pattern.json").read_text(encoding="utf-8")),
        json.loads((ROOT / "data/processed/uint128-pattern-validation.json").read_text(encoding="utf-8")),
    )


def test_recorded_pattern_is_consistent(artifacts):
    validate_cases(*artifacts)


@pytest.mark.parametrize("fault", ["stale", "receipt", "state", "context", "source", "coverage"])
def test_rejects_misleading_evidence(artifacts, fault):
    card, report = copy.deepcopy(artifacts)
    if fault == "stale":
        report["fixture_hashes"]["UnsafeReserve.sol"] = "0" * 64
    elif fault == "receipt":
        report["executions"][1]["observations"][4]["transaction_status"] = 1
    elif fault == "state":
        report["executions"][1]["observations"][4]["after"] = "0"
    elif fault == "context":
        card["cases"][2]["expected_verdict"] = "confirmed"
    elif fault == "source":
        card["knowledge"]["root_cause"][0]["basis"] = ["invented"]
    elif fault == "coverage":
        report["executions"][0]["observations"].pop()
    with pytest.raises(ValueError):
        validate_cases(card, report)
