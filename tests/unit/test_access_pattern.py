"""Reject misleading execution/provenance in the second curated pattern."""

import copy
from pathlib import Path

import pytest

from scripts.verify_access_pattern import read, validate_cases, validate_reference

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def artifacts():
    return read(ROOT / "tools/access-pattern/pattern.json"), read(ROOT / "data/processed/access-pattern-validation.json")


def test_access_pattern_is_consistent(artifacts):
    card, report = artifacts
    validate_cases(card, report)
    binding = validate_reference(card)
    assert binding["database_binding"] is None
    assert len(binding["citations"]) == 3


@pytest.mark.parametrize("fault", ["stale", "actor", "receipt", "state", "reason", "owner", "context", "coverage", "basis"])
def test_rejects_misleading_access_evidence(artifacts, fault):
    card, report = copy.deepcopy(artifacts)
    row = report["executions"][1]["observations"][0]
    if fault == "stale":
        report["fixture_hashes"]["GuardedFeeConfig.sol"] = "0" * 64
    elif fault == "actor":
        report["accounts"]["outsiderA"] = report["accounts"]["owner"]
    elif fault == "receipt":
        row["transaction_status"] = 1
    elif fault == "state":
        row["after"] = row["recipient"]
    elif fault == "reason":
        row["revert_reason"] = "zero recipient"
    elif fault == "owner":
        report["executions"][1]["observations"][1]["reverted"] = True
    elif fault == "context":
        card["cases"][2]["expected_verdict"] = "confirmed"
    elif fault == "coverage":
        report["executions"].pop()
    elif fault == "basis":
        card["knowledge"]["root_cause"][0]["basis"] = ["invented"]
    with pytest.raises(ValueError):
        validate_cases(card, report)


@pytest.mark.parametrize("fault", ["hash", "citation", "binding"])
def test_rejects_misleading_historical_binding(artifacts, fault):
    card, _ = copy.deepcopy(artifacts)
    reference = card["historical_reference"]
    if fault == "hash":
        reference["manifest_sha256"] = "0" * 64
    elif fault == "citation":
        reference["citations"][0]["start_line"] = 9999
    else:
        reference["database_binding"] = "invented_revision"
    with pytest.raises(ValueError):
        validate_reference(card)
