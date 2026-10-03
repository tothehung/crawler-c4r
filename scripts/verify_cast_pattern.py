"""Validate the curated pilot and export its read-only link to historical KB data."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.models.knowledge_base import GroundedClaim
from src.services.evidence.repo_context import _atomic_json
from src.services.knowledge_builder import REQUIRED, validate_grounding


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_cases(card, report, root=ROOT):
    labels = {
        "unsafe": "confirmed",
        "guarded": "false_positive_for_this_pattern",
        "fragment": "insufficient_context",
    }
    require(card["pattern_id"] == report["pattern_id"], "pattern mismatch")
    require(card["review_status"] == "needs_review", "pilot must remain a candidate")
    require(set(card["knowledge"]) == REQUIRED, "missing knowledge category")
    for claims in card["knowledge"].values():
        require(bool(claims), "empty knowledge category")
        for item in claims:
            require(bool(item["text"].strip()) and bool(item["basis"]), "ungrounded claim")
            require(set(item["basis"]) <= card["sources"].keys(), "unknown source")
    require(len(card["cases"]) == 3, "expected three cases")
    require({c["case_id"]: c["expected_verdict"] for c in card["cases"]} == labels,
            "incorrect case labels")
    require(report["expected_labels"] == labels, "incorrect execution labels")
    require(report["synthetic"] is True and report["public_network_used"] is False,
            "incorrect execution scope")
    require(report["compiler"].startswith("0.8.24+commit.e11b9ed9"), "unexpected compiler")
    for name in labels:
        path = root / card["sources"][name]
        require(digest(path) == report["fixture_hashes"].get(path.name), "stale fixture hash")
    fragment = (root / card["sources"]["fragment"]).read_bytes().decode("utf-8")
    require(report["generated_context_harness"].count(fragment) == 2, "fragment changed")
    expected_contracts = {"UnsafeReserve", "GuardedReserve", "GuardedCaller", "UnguardedCaller"}
    require(len(report["executions"]) == 4 and
            {e["contract"] for e in report["executions"]} == expected_contracts,
            "missing context comparison")
    maximum = (1 << 128) - 1
    inputs = [0, 1, maximum - 1, maximum, maximum + 1, maximum + 2, (1 << 256) - 1]
    for i in range(16):
        value = int(hashlib.sha256(f"cast-pattern-v1:{i}".encode()).hexdigest(), 16)
        inputs.extend([value & maximum, value])
    for execution in report["executions"]:
        observations = execution["observations"]
        require([int(o["input"]) for o in observations] == inputs, "incomplete input coverage")
        previous = 0
        guarded = execution["contract"] in {"GuardedReserve", "GuardedCaller"}
        for row in observations:
            value, before, after = (int(row[key]) for key in ("input", "before", "after"))
            reverted = guarded and value > maximum
            require(before == previous, "broken state continuity")
            require(row["reverted"] is reverted, "incorrect revert result")
            require(row["transaction_status"] == (0 if reverted else 1), "incorrect receipt")
            require(after == (before if reverted else value & maximum), "incorrect stored value")
            require(row["exact_value_preserved"] is (not reverted and value == after),
                    "incorrect exactness result")
            previous = after
    require(report["checks"] == 156, "incorrect check count")


class ReadOnlyRecords:
    def __init__(self, connection):
        self.connection = connection

    def get(self, table, key):
        row = self.connection.execute(
            "SELECT payload FROM records WHERE table_name=? AND record_key=?", (table, key)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def links(self, key):
        rows = self.connection.execute(
            "SELECT payload FROM records WHERE table_name='finding_evidence_links' "
            "AND json_extract(payload, '$.processing_key')=?", (key,)
        )
        return [json.loads(row[0]) for row in rows]


def build_pack(root=ROOT):
    card_path = root / "tools/cast-pattern/pattern.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    report_path = root / card["sources"]["executions"]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    validate_cases(card, report, root)
    historical = card["historical_knowledge"]
    draft = json.loads((root / historical["draft_manifest"]).read_text(encoding="utf-8"))
    db = root / "data/checkpoints/phase4-replay.sqlite3"
    connection = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        records = ReadOnlyRecords(connection)
        revision = records.get("knowledge_revisions", draft["expected_revision_id"])
        require(revision is not None, "historical revision missing")
        require(revision["snapshot_id"] == historical["snapshot_id"], "historical snapshot mismatch")
        snapshot = validate_grounding(
            records, revision["snapshot_id"], revision["processing_key"],
            [GroundedClaim.model_validate(c) for c in revision["claims"]],
            revision["evidence_link_ids"], revision["evidence_bindings"],
        )
        # The draft is a separate artifact: verify its quotes too, not just the saved revision.
        from src.services.knowledge_builder import claim

        validate_grounding(
            records, revision["snapshot_id"], revision["processing_key"],
            [claim(c["category"], c["text"], c["citations"]) for c in draft["claims"]],
            revision["evidence_link_ids"], revision["evidence_bindings"],
        )
    finally:
        connection.close()
    return {
        "schema_version": "1.0", "pattern": card,
        "validation": {"checks": report["checks"], "compiler": report["compiler"],
                       "report": card["sources"]["executions"], "sha256": digest(report_path)},
        "historical_binding": {
            "snapshot_id": snapshot["snapshot_id"], "revision_id": revision["revision_id"],
            "content_hash": revision["content_hash"], "review_status": revision["review_status"],
            "evidence_bindings": revision["evidence_bindings"],
        },
        "local_source_hashes": {
            name: digest(root / source) for name, source in card["sources"].items()
            if not source.startswith("https://")
        },
        "pattern_sha256": digest(card_path),
        "status": "validated_candidate",
        "note": "Technical validation only; no human approval or original-protocol reproduction.",
    }


if __name__ == "__main__":
    pack = build_pack()
    output = ROOT / "data/processed/uint128-pattern-pack.json"
    _atomic_json(output, pack)
    print(json.dumps({"output": str(output), "checks": pack["validation"]["checks"],
                      "status": pack["status"]}))
