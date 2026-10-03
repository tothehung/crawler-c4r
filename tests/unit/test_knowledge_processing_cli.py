from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.export_knowledge_contract import example_bundle
from src.repositories.knowledge_store import SQLiteKnowledgeStore

ROOT = Path(__file__).resolve().parents[2]


def test_cli_ingest_apply_results_and_rerun(tmp_path):
    db = tmp_path / "queue.sqlite3"
    config = tmp_path / "config.json"
    snapshots = tmp_path / "snapshots.jsonl"
    manifests = tmp_path / "results.jsonl"
    bundle = example_bundle()
    config.write_text(
        json.dumps({"context_lines": 10, "normalization_version": "identity-v1"}),
        encoding="utf-8",
    )
    snapshots.write_text(
        "\n".join(json.dumps(row) for row in bundle["source_finding_snapshots"]),
        encoding="utf-8",
    )
    rows = []
    for state in bundle["evidence_processing_state"]:
        links = [
            link
            for link in bundle["finding_evidence_links"]
            if link["processing_key"] == state["processing_key"]
        ]
        ids = {link["evidence_id"] for link in links}
        rows.append(
            {
                "processing_key": state["processing_key"],
                "inventory_complete": True,
                "candidate_count": len(links),
                "links": links,
                "evidence": [
                    e for e in bundle["code_evidence"] if e["evidence_id"] in ids
                ],
            }
        )
    manifests.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    def run(*args):
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/process_knowledge.py"),
                "--db",
                str(db),
                *args,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return [json.loads(line) for line in completed.stdout.splitlines()]

    ingest = (
        "ingest",
        "--input",
        str(snapshots),
        "--config",
        str(config),
        "--pipeline-version",
        "evidence-v1",
    )
    assert len(run(*ingest)) == 3
    assert len(run(*ingest)) == 3
    result = run("apply-results", "--input", str(manifests))[0]
    assert result["attempted"] == 3
    assert sorted(state["status"] for state in result["states"]) == [
        "partial",
        "succeeded",
        "succeeded",
    ]
    again = run("apply-results", "--input", str(manifests))[0]
    assert again["attempted"] == 0 and again["skipped"] == 3
    states = run("status", "--limit", "2")
    assert len(states) == 2
    assert len(run("status", "--after", states[-1]["processing_key"])) == 1
    store = SQLiteKnowledgeStore(db)
    assert len(store.states()) == 3
    for row in bundle["code_evidence"]:
        assert store.read("code_evidence", row["evidence_id"]) == row


def test_cli_run_uses_real_resolver_with_recorded_transport(tmp_path):
    from tests.unit.test_evidence_resolver import make_snapshot

    db = tmp_path / "live-resolver.sqlite3"
    input_path = tmp_path / "snapshot.jsonl"
    snapshot = make_snapshot(
        "```solidity\nuint x;\n```\nhttps://github.com/code-423n4/2023-01-astaria/blob/1bfc58b42109b839528ab1c21dc9803d663df898/src/LienToken.sol#L849"
    )
    input_path.write_text(snapshot.model_dump_json() + "\n", encoding="utf-8")
    config = ROOT / "config/knowledge_phase4_recorded.json"
    command = [
        sys.executable,
        str(ROOT / "scripts/process_knowledge.py"),
        "--db",
        str(db),
    ]
    subprocess.run(
        command
        + [
            "ingest",
            "--input",
            str(input_path),
            "--config",
            str(config),
            "--pipeline-version",
            "evidence-resolver-v1",
        ],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    args = [
        "run",
        "--config",
        str(config),
        "--replay-http",
        str(ROOT / "tests/fixtures/evidence_benchmark_v1/http"),
    ]
    first = subprocess.run(
        command + args, cwd=ROOT, capture_output=True, text=True, check=True
    )
    result = json.loads(first.stdout)
    assert result["attempted"] == 1 and result["states"][0]["status"] == "succeeded"
    assert result["states"][0]["resolved_count"] == 2
    second = subprocess.run(
        command + args, cwd=ROOT, capture_output=True, text=True, check=True
    )
    assert json.loads(second.stdout)["attempted"] == 0
