"""Offline validation/export of the access-control pilot; no database writes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.services.evidence.repo_context import _atomic_json
from src.services.knowledge_builder import REQUIRED

LABELS = {"unsafe": "confirmed", "guarded": "false_positive_for_this_pattern", "fragment": "insufficient_context"}
CONTRACTS = {"UnsafeFeeConfig", "GuardedFeeConfig", "GuardedCaller", "UnguardedCaller"}
SCENARIOS = [("outsiderA", "outsiderA"), ("owner", "outsiderB"), ("outsiderB", "outsiderA"),
             ("owner", "owner"), ("outsiderA", "outsiderB"), ("owner", "outsiderA")]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def local(root, relative):
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()), "source path escapes workspace")
    return path


def validate_cases(card, report, root=ROOT):
    require(card["pattern_id"] == report["pattern_id"] == "SOL-MISSING-ACCESS-CONTROL-001", "pattern mismatch")
    require(card["review_status"] == "needs_review", "pilot is not approved")
    require(set(card["knowledge"]) == REQUIRED, "missing category")
    for claims in card["knowledge"].values():
        require(bool(claims), "empty category")
        for item in claims:
            require(bool(item["text"].strip()) and bool(item["basis"]), "empty claim or basis")
            require(set(item["basis"]) <= card["sources"].keys(), "unknown basis")
    require(len(card["cases"]) == 3 and {c["case_id"]: c["expected_verdict"] for c in card["cases"]} == LABELS,
            "incorrect labels")
    unknown = next(c for c in card["cases"] if c["case_id"] == "fragment")
    require(unknown["contract"] is None and bool(unknown["missing_context"]), "missing context erased")
    require(report["expected_labels"] == LABELS, "incorrect execution labels")
    require(report["synthetic"] is True and report["public_network_used"] is False, "incorrect scope")
    require(report["compiler"].startswith("0.8.24+commit.e11b9ed9") and report["runtime"] == "ganache@7.9.2", "runtime changed")
    require(report["runner_sha256"] == sha(root / "tools/access-pattern/verify.cjs"), "stale runner")
    require(report["dependency_lock_sha256"] == sha(root / "tools/cast-pattern/pnpm-lock.yaml"), "stale dependencies")
    for key in LABELS:
        path = local(root, card["sources"][key])
        require(report["fixture_hashes"].get(path.name) == sha(path), "stale fixture")
    fragment = local(root, card["sources"]["fragment"]).read_bytes().decode("utf-8")
    require(report["generated_context_harness"].count(fragment) == 2, "fragment changed")
    accounts = {k: v.lower() for k, v in report["accounts"].items()}
    require(set(accounts) == {"owner", "outsiderA", "outsiderB"} and len(set(accounts.values())) == 3,
            "actors must be distinct")
    for address in accounts.values():
        require(len(address) == 42 and address.startswith("0x") and int(address, 16) > 0, "invalid actor")
    executions = report["executions"]
    require(len(executions) == 4 and {e["contract"] for e in executions} == CONTRACTS, "missing contract")
    for execution in executions:
        guarded = execution["contract"] in {"GuardedFeeConfig", "GuardedCaller"}
        rows = execution["observations"]
        require(len(rows) == len(SCENARIOS), "missing observations")
        previous = accounts["owner"]
        for row, (caller, recipient_role) in zip(rows, SCENARIOS, strict=True):
            recipient = accounts[recipient_role]
            require(row["caller_role"] == caller and row["caller"].lower() == accounts[caller], "wrong caller")
            require(row["recipient"].lower() == recipient and recipient != previous, "invalid test recipient")
            require(row["before"].lower() == previous, "broken state continuity")
            rejected = guarded and caller != "owner"
            require(row["reverted"] is rejected and row["transaction_status"] == (0 if rejected else 1), "incorrect receipt")
            require(row["revert_reason"] == ("unauthorized" if rejected else None), "incorrect revert reason")
            after = previous if rejected else recipient
            require(row["after"].lower() == after, "incorrect state")
            require(row["unauthorized_change"] is (caller != "owner" and not rejected), "incorrect unauthorized result")
            previous = after
    require(report["checks"] == 24, "incorrect check count")


def validate_reference(card, root=ROOT):
    reference = card["historical_reference"]
    require(reference["database_binding"] is None and reference["storage_status"] == "supplementary_source_only",
            "historical source must not claim a database binding")
    manifest_path = local(root, reference["manifest"])
    require(sha(manifest_path) == reference["manifest_sha256"], "source manifest changed")
    manifest = read(manifest_path)
    for name, digest in manifest["hashes"].items():
        require(sha(local(root, str(manifest_path.parent.relative_to(root) / name))) == digest, "captured source changed")
    issue = read(manifest_path.parent / "issue.json")
    require(issue["html_url"] == reference["source_url"] == manifest["source_url"], "source URL mismatch")
    require(manifest["source_snapshot_id"] == "external_sha256:" + manifest["hashes"]["issue.json"], "snapshot mismatch")
    require(read(manifest_path.parent / "commit.json")["sha"] == manifest["commit_sha"], "commit mismatch")
    require((manifest_path.parent / "report.md").read_bytes().decode("utf-8") == issue["body"], "report body mismatch")
    quotes = []
    for citation in reference["citations"]:
        source = citation["source"]
        expected = "report.md" if source == "historical_report" else "RFPSimpleStrategy.sol"
        require(source in {"historical_report", "historical_code"}, "unknown citation source")
        path = local(root, card["sources"][source])
        require(path == manifest_path.parent / expected, "citation not bound to capture")
        lines = path.read_text(encoding="utf-8").splitlines()
        start, end = citation["start_line"], citation["end_line"]
        require(1 <= start <= end <= len(lines), "invalid citation range")
        quote = "\n".join(lines[start - 1:end])
        require("setPoolActive" in quote, "irrelevant source anchor")
        quotes.append(citation | {"quote": quote, "source_sha256": sha(path)})
    require(len(quotes) == 3, "missing historical citations")
    return {"source_snapshot_id": manifest["source_snapshot_id"], "source_url": manifest["source_url"],
            "commit_sha": manifest["commit_sha"], "code_url": manifest["code_url"],
            "storage_status": reference["storage_status"], "database_binding": None, "citations": quotes}


def build_pack(root=ROOT):
    path = root / "tools/access-pattern/pattern.json"
    card = read(path)
    report_path = local(root, card["sources"]["executions"])
    report = read(report_path)
    validate_cases(card, report, root)
    binding = validate_reference(card, root)
    return {"schema_version": "1.0", "pattern": card, "pattern_sha256": sha(path),
            "source_binding": binding, "status": "validated_candidate",
            "validation": {"checks": report["checks"], "compiler": report["compiler"],
                           "report": card["sources"]["executions"], "sha256": sha(report_path)},
            "local_source_hashes": {key: sha(local(root, source)) for key, source in card["sources"].items()
                                    if not source.startswith("https://")},
            "note": "Technical consistency checked; remains needs_review. No database import or original-protocol PoC."}


if __name__ == "__main__":
    pack = build_pack()
    output = ROOT / "data/processed/access-pattern-pack.json"
    _atomic_json(output, pack)
    print(json.dumps({"output": str(output), "checks": pack["validation"]["checks"], "status": pack["status"]}))
