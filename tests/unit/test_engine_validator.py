from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.models.knowledge_contract import CodeEvidence, LineRange
from src.repositories.knowledge_store import SQLiteKnowledgeStore
from src.services.evidence.engine_validator import (
    EngineValidationError,
    EngineValidator,
    validate_batch,
)


def make_evidence(
    code="contract Token { function transfer(address to, uint amount) external {} }",
    **fields,
):
    record = CodeEvidence.model_construct(
        evidence_id="pending",
        origin_kind="inline",
        origin_snapshot_id="snapshot",
        locator="body:block:0",
        raw_snippet=code,
        normalized_snippet=code,
        normalization_version="identity-v1",
        extractor_version="test-v1",
        created_at=datetime.now(UTC),
        **fields,
    )
    return CodeEvidence.model_validate(
        record.model_dump() | {"evidence_id": record.expected_id()}
    )


def response_for(payload):
    return {
        "protocol_version": "1.0",
        "parser_version": "test-parser-v1",
        "evidence_id": payload["evidence_id"],
        "input_sha256": hashlib.sha256(payload["content"].encode()).hexdigest(),
        "syntax_status": "parsed",
        "contracts": ["Token"],
        "functions": [
            {
                "contract_name": "Token",
                "function_name": "transfer",
                "function_signature": "transfer(address,uint256)",
                "selector_4byte": "0xa9059cbb",
                "snippet_start_line": 1,
                "snippet_end_line": 1,
            }
        ],
        "diagnostics": [],
    }


@pytest.fixture
def fake_engine(tmp_path, monkeypatch):
    executable = tmp_path / "engine.exe"
    executable.write_bytes(b"synthetic engine binary")
    calls = []
    behavior = [response_for]

    def run(command, **kwargs):
        assert kwargs["shell"] is False
        calls.append((command, kwargs))
        if command[-1] == "--info":
            data = {"protocol_version": "1.0", "parser_version": "test-parser-v1"}
        else:
            data = behavior[0](json.loads(kwargs["input"]))
        return subprocess.CompletedProcess(command, 0, json.dumps(data), "")

    monkeypatch.setattr(subprocess, "run", run)
    return EngineValidator(executable), behavior, calls


def test_annotation_preserves_identity_text_and_versions_binary(fake_engine):
    validator, _, calls = fake_engine
    original = make_evidence()
    annotated, _ = validator.validate(original)
    assert annotated.evidence_id == original.evidence_id
    assert annotated.expected_id() == original.expected_id()
    assert annotated.raw_snippet == original.raw_snippet
    assert annotated.normalized_snippet == original.normalized_snippet
    assert annotated.created_at == original.created_at
    assert annotated.function_signature == "transfer(address,uint256)"
    assert annotated.selector_4byte == "0xa9059cbb"
    assert annotated.syntax_status == "parsed"
    assert "binary-sha256:" in annotated.parser_version
    assert calls[-1][0][1:] == ["validate-evidence"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("evidence_id", "other"),
        ("input_sha256", "bad"),
        ("parser_version", "other"),
        ("syntax_status", "ok"),
    ],
)
def test_mismatched_or_legacy_result_is_rejected(fake_engine, field, value):
    validator, behavior, _ = fake_engine
    behavior[0] = lambda payload: response_for(payload) | {field: value}
    with pytest.raises(EngineValidationError):
        validator.validate(make_evidence())


def test_multiple_functions_do_not_pick_arbitrary_overload(fake_engine):
    validator, behavior, _ = fake_engine

    def multiple(payload):
        result = response_for(payload)
        result["functions"].append(
            result["functions"][0] | {"function_signature": "transfer(address,bytes)"}
        )
        return result

    behavior[0] = multiple
    annotated, _ = validator.validate(make_evidence())
    assert annotated.contract_name == "Token"
    assert annotated.function_name is None and annotated.function_signature is None
    assert annotated.selector_4byte is None
    assert any(
        "multiple_functions" in diagnostic for diagnostic in annotated.diagnostics
    )


def test_source_mapping_and_transformed_snippet(fake_engine):
    validator, behavior, calls = fake_engine

    def mapped(payload):
        result = response_for(payload)
        if payload["source_start_line"]:
            result["functions"][0].update(
                source_start_line=payload["source_start_line"],
                source_end_line=payload["source_start_line"],
            )
        return result

    behavior[0] = mapped
    evidence = make_evidence(source_range=LineRange(start_line=40, end_line=40))
    validator.validate(evidence)
    assert json.loads(calls[-1][1]["input"])["source_start_line"] == 40
    transformed = make_evidence(
        source_range=LineRange(start_line=40, end_line=40),
        transformations=["inline_diff:after"],
    )
    validator.validate(transformed)
    assert json.loads(calls[-1][1]["input"])["source_start_line"] == 0


def test_fake_line_mapping_is_rejected(fake_engine):
    validator, behavior, _ = fake_engine

    def wrong(payload):
        result = response_for(payload)
        result["functions"][0]["source_start_line"] = 50
        return result

    behavior[0] = wrong
    with pytest.raises(EngineValidationError, match="invented"):
        validator.validate(make_evidence())


def test_inconsistent_input_source_range_is_rejected(fake_engine):
    validator, _, _ = fake_engine
    with pytest.raises(EngineValidationError, match="line count"):
        validator.validate(
            make_evidence(source_range=LineRange(start_line=1, end_line=5))
        )


@pytest.mark.parametrize("returncode,stdout", [(2, ""), (0, "not JSON")])
def test_process_exit_or_invalid_json_never_becomes_syntax_result(
    fake_engine, monkeypatch, returncode, stdout
):
    validator, _, _ = fake_engine
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, returncode, stdout, "process failed"
        ),
    )
    with pytest.raises(EngineValidationError):
        validator.validate(make_evidence())


def test_persist_skip_and_timeout_preserves_original(tmp_path, fake_engine):
    validator, behavior, _ = fake_engine
    store = SQLiteKnowledgeStore(tmp_path / "evidence.sqlite3")
    evidence = make_evidence()
    with store.transaction() as tx:
        tx.put("code_evidence", evidence.model_dump(mode="json"))
    first = validate_batch(store, validator)
    assert first["validated"] == 1
    assert validate_batch(store, validator)["skipped"] == 1
    original = store.read("code_evidence", evidence.evidence_id)
    validator.parser_version = "new-parser"

    def timeout(_):
        raise subprocess.TimeoutExpired("engine", 30)

    behavior[0] = timeout
    report = validate_batch(store, validator)
    assert report["errors"] == 1
    assert store.read("code_evidence", evidence.evidence_id) == original


def test_stale_annotation_cannot_overwrite_newer_work(tmp_path, fake_engine):
    validator, behavior, _ = fake_engine
    store = SQLiteKnowledgeStore(tmp_path / "race.sqlite3")
    evidence = make_evidence()
    with store.transaction() as tx:
        tx.put("code_evidence", evidence.model_dump(mode="json"))

    def race(payload):
        with store.transaction() as tx:
            changed = evidence.model_dump(mode="json") | {
                "syntax_status": "invalid",
                "parser_version": "concurrent-parser",
            }
            tx.put("code_evidence", changed)
        return response_for(payload)

    behavior[0] = race
    assert validate_batch(store, validator)["errors"] == 1
    assert (
        store.read("code_evidence", evidence.evidence_id)["parser_version"]
        == "concurrent-parser"
    )


def test_real_go_engine_adapter_and_cli(tmp_path):
    executable = os.getenv("W3GOAUDIT_ENGINE")
    if not executable:
        pytest.skip("Set W3GOAUDIT_ENGINE to run the real engine integration test")
    validator = EngineValidator(Path(executable))
    evidence = make_evidence()
    annotated, detail = validator.validate(evidence)
    assert annotated.syntax_status == "parsed"
    assert annotated.selector_4byte == "0xa9059cbb"
    assert detail.functions[0].function_signature == "transfer(address,uint256)"
    fragment, _ = validator.validate(make_evidence("require(x > 0);"))
    assert fragment.syntax_status == "insufficient_context"
    assert fragment.contract_name is None
    store = SQLiteKnowledgeStore(tmp_path / "real.sqlite3")
    with store.transaction() as tx:
        tx.put("code_evidence", evidence.model_dump(mode="json"))
    import sys

    script = Path(__file__).resolve().parents[2] / "scripts/validate_evidence.py"
    command = [
        sys.executable,
        str(script),
        "--engine",
        executable,
        "--db",
        str(store.path),
    ]
    first = subprocess.run(command, capture_output=True, text=True, check=True)
    second = subprocess.run(command, capture_output=True, text=True, check=True)
    assert json.loads(first.stdout)["validated"] == 1
    assert json.loads(second.stdout)["skipped"] == 1
