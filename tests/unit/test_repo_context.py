from __future__ import annotations

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
)
from src.services.evidence.repo_context import (
    ContextUnavailable,
    capture_bundle,
    enrich_batch,
    enrich_context,
)


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()

    def git(*args):
        return (
            subprocess.run(
                ["git", "-C", str(root), *args], capture_output=True, check=True
            )
            .stdout.decode()
            .strip()
        )

    git("init")
    git("config", "user.name", "Context Fixture")
    git("config", "user.email", "fixture@example.test")
    git("config", "core.autocrlf", "false")
    git("remote", "add", "origin", "https://github.com/fixture/vault.git")
    (root / "Base.sol").write_text(
        "contract Base { uint internal total; modifier guarded() { _; } function helper() internal {} }\n",
        encoding="utf-8",
    )
    snippet = "function withdraw() public guarded { helper(); }"
    (root / "Vault.sol").write_text(
        'import "./Base.sol";\ncontract Vault is Base {\nfunction entry() external { withdraw(); }\n'
        + snippet
        + "\n}\n",
        encoding="utf-8",
    )
    git("add", ".")
    git("-c", "core.hooksPath=NUL", "commit", "-m", "fixture", "--no-gpg-sign")
    commit = git("rev-parse", "HEAD")
    evidence = CodeEvidence.model_construct(
        evidence_id="pending",
        origin_kind="github_file",
        repo="fixture/vault",
        commit_sha=commit,
        path="Vault.sol",
        origin_url=f"https://github.com/fixture/vault/blob/{commit}/Vault.sol#L4",
        locator="L4",
        source_range=LineRange(start_line=4, end_line=4),
        raw_snippet=snippet,
        normalized_snippet=snippet,
        normalization_version="identity-v1",
        extractor_version="test-v1",
        created_at=datetime.now(UTC),
    )
    evidence = CodeEvidence.model_validate(
        evidence.model_dump() | {"evidence_id": evidence.expected_id()}
    )
    return root, evidence, git


def test_capture_uses_commit_blobs_not_dirty_checkout(repository):
    root, evidence, _ = repository
    original = capture_bundle(evidence, root)
    (root / "Vault.sol").write_text("broken uncommitted code", encoding="utf-8")
    (root / "untracked.sol").write_text("not in commit", encoding="utf-8")
    assert capture_bundle(evidence, root) == original
    assert len(original["sources"]) == 2


def test_mismatched_origin_and_evidence_rejected(repository):
    root, evidence, git = repository
    changed = evidence.model_copy(
        update={"raw_snippet": "unrelated code", "normalized_snippet": "unrelated code"}
    )
    with pytest.raises(ContextUnavailable, match="does_not_match"):
        capture_bundle(changed, root)
    git("remote", "set-url", "origin", "https://github.com/other/repo.git")
    with pytest.raises(ContextUnavailable, match="origin_mismatch"):
        capture_bundle(evidence, root)


def test_transformed_evidence_is_not_attached_to_source(repository):
    root, evidence, _ = repository
    with pytest.raises(ContextUnavailable, match="contiguous"):
        capture_bundle(
            evidence.model_copy(update={"transformations": ["strip_diff"]}), root
        )


def test_protocol_failure_does_not_publish_annotation(repository, tmp_path):
    root, evidence, _ = repository

    class WrongEngine:
        binary_hash = "fake"

        def _call(self, *_):
            return {"evidence_id": "wrong"}

    with pytest.raises(EngineValidationError, match="protocol"):
        enrich_context(evidence, WrongEngine(), root, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_missing_repository_report_preserves_evidence(repository, tmp_path):
    _, evidence, _ = repository
    store = SQLiteKnowledgeStore(tmp_path / "store.sqlite3")
    with store.transaction() as tx:
        tx.put("code_evidence", evidence.model_dump(mode="json"))

    class UnusedEngine:
        binary_hash = "fake"

    before = store.evidence()
    report = enrich_batch(store, UnusedEngine(), {}, tmp_path / "output")
    assert report["counts"]["unavailable"] == 1
    assert report["counts"]["error"] == 0
    assert store.evidence() == before
    assert len(list((tmp_path / "output/reports").glob("*.json"))) == 1


@pytest.mark.skipif(
    not os.environ.get("W3GOAUDIT_ENGINE"),
    reason="Set W3GOAUDIT_ENGINE for real engine integration",
)
def test_real_context_end_to_end_and_repeat(repository, tmp_path):
    root, evidence, _ = repository
    validator = EngineValidator(Path(os.environ["W3GOAUDIT_ENGINE"]))
    store = SQLiteKnowledgeStore(tmp_path / "store.sqlite3")
    with store.transaction() as tx:
        tx.put("code_evidence", evidence.model_dump(mode="json"))
    before = store.evidence()
    output = tmp_path / "context"
    first = enrich_batch(store, validator, {"fixture/vault": str(root)}, output)
    second = enrich_batch(store, validator, {"fixture/vault": str(root)}, output)
    assert first == second
    assert first["counts"]["error"] == 0
    assert first["counts"]["available"] + first["counts"]["partial"] == 1
    assert store.evidence() == before
    files = list((output / "annotations").glob("*.json"))
    assert len(files) == 1
    annotation = json.loads(files[0].read_text(encoding="utf-8"))
    fn = annotation["result"]["functions"][0]
    assert fn["id"] == "Vault.sol#Vault.withdraw()"
    assert fn["callers"][0]["from"] == "Vault.sol#Vault.entry()"
    assert any(edge["to"] == "Base.sol#Base.helper()" for edge in fn["callees"])
    assert fn["modifiers"] == ["guarded"]
    assert len(list((output / "bundles").glob("*.json"))) == 1
    repo_map = tmp_path / "repos.json"
    repo_map.write_text(json.dumps({"fixture/vault": str(root)}), encoding="utf-8")
    command = [
        os.sys.executable,
        "scripts/enrich_evidence_context.py",
        "--engine",
        str(validator.executable),
        "--db",
        str(tmp_path / "store.sqlite3"),
        "--repo-map",
        str(repo_map),
        "--output",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)["counts"]["error"] == 0
